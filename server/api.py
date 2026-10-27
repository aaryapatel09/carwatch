"""Private account, camera pairing, evidence and push API for the native pilot."""

import asyncio
import base64
import hashlib
import hmac
import io
import os
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field

from server.database import connection, digest, initialize, uid
from server.push import ExpoTransport, PushWorker

AUTH = HTTPBearer(auto_error=False)
KINDS = {
    "lingering": "Sustained presence",
    "repeated_approach": "Repeated entry",
    "hand_near_zone": "Hand near selected region",
}


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Credentials(Input):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)


class Registration(Credentials):
    invite: str = Field(min_length=20, max_length=100)


class Camera(Input):
    name: str = Field(min_length=1, max_length=60)


class CameraState(Input):
    armed: bool
    notify: bool


class Pair(Input):
    code: str = Field(min_length=20, max_length=100)


class Heartbeat(Input):
    capture: Literal["ready", "starting", "running", "stopped", "error"]


class Event(Input):
    source_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9:_-]+$")
    kind: Literal["lingering", "repeated_approach", "hand_near_zone"]
    observed_at: float
    origin: Literal["live", "demo"] = "live"
    snapshot: str | None = Field(default=None, max_length=300000)


class Review(Input):
    review: Literal["useful", "ordinary", "unclear", "unreviewed"]


class PushToken(Input):
    token: str = Field(pattern=r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_-]{10,200}\]$")


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ":" + value


def create_app(path=None, push_enabled=None, transport=None, background=True):
    path = Path(path or os.environ.get("CARWATCH_API_DB", "runtime/api/carwatch.sqlite3"))
    initialize(path)
    enabled = (
        os.environ.get("CARWATCH_PUSH_ENABLED") == "1" if push_enabled is None else push_enabled
    )
    access = os.environ.get("CARWATCH_EXPO_ACCESS_TOKEN", "")
    if enabled and not access and transport is None:
        raise RuntimeError("Configure the Expo access token before enabling delivery")
    worker = PushWorker(path, transport or ExpoTransport(access))

    @asynccontextmanager
    async def lifespan(app):
        task = None
        if enabled and background:
            worker.recover()

            async def run():
                while True:
                    try:
                        await asyncio.to_thread(worker.tick)
                    except Exception:
                        # Do not log provider payloads or credentials.
                        import logging

                        logging.getLogger("carwatch").error(
                            "Push worker cycle failed; queue retained"
                        )
                    await asyncio.sleep(2)

            task = asyncio.create_task(run())
        yield
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="Carwatch companion API", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.worker = worker
    origins = [
        s.strip() for s in os.environ.get("CARWATCH_ALLOWED_ORIGINS", "").split(",") if s.strip()
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
    limits = {}

    @app.middleware("http")
    async def bounds(request, call_next):
        now = time.time()
        bucket = int(now // 60)
        ip = request.client.host if request.client else "unknown"
        key = (
            ip,
            bucket,
            request.url.path.startswith("/v1/auth") or request.url.path == "/v1/device/pair",
        )
        if len(limits) > 2000:
            for k in list(limits):
                if k[1] != bucket:
                    del limits[k]
        if len(limits) > 4000:
            return JSONResponse({"detail": "Service busy"}, status_code=429)
        limits[key] = limits.get(key, 0) + 1
        if limits[key] > (20 if key[2] else 300):
            return JSONResponse({"detail": "Try again in a minute"}, status_code=429)
        total = 0
        parts = []
        async for part in request.stream():
            total += len(part)
            if total > 320000:
                return JSONResponse({"detail": "Request too large"}, status_code=413)
            parts.append(part)
        request._body = b"".join(parts)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"detail": "Invalid request fields"}, status_code=422)

    def user(credentials: HTTPAuthorizationCredentials | None = Depends(AUTH)):
        if credentials is None:
            raise HTTPException(401, "Sign in required")
        token = digest(credentials.credentials)
        with connection(path) as db:
            row = db.execute(
                "SELECT s.*,u.username FROM sessions s JOIN users u ON u.id=s.user_id WHERE hash=? AND expires>?",
                (token, time.time()),
            ).fetchone()
        if not row:
            raise HTTPException(401, "Session expired. Sign in again.")
        return dict(row)

    def device(credentials: HTTPAuthorizationCredentials | None = Depends(AUTH)):
        if credentials is None:
            raise HTTPException(401, "Pairing required")
        with connection(path) as db:
            row = db.execute(
                "SELECT * FROM cameras WHERE device_hash=?", (digest(credentials.credentials),)
            ).fetchone()
        if not row:
            raise HTTPException(401, "Device revoked or unpaired")
        return dict(row)

    def camera_owned(db, camera_id, account):
        row = db.execute(
            "SELECT * FROM cameras WHERE id=? AND user_id=?", (camera_id, account["user_id"])
        ).fetchone()
        if not row:
            raise HTTPException(404, "Camera unavailable")
        return row

    def event_owned(db, event_id, account):
        row = db.execute(
            "SELECT e.*,c.name AS camera_name FROM events e JOIN cameras c ON c.id=e.camera_id WHERE e.id=? AND c.user_id=?",
            (event_id, account["user_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Event unavailable")
        return row

    def public_camera(row):
        return {k: row[k] for k in ("id", "name", "armed", "notify", "last_seen", "capture")} | {
            "paired": bool(row["device_hash"])
        }

    def public_event(row):
        return {
            k: row[k]
            for k in ("id", "camera_id", "camera_name", "kind", "observed_at", "origin", "review")
        } | {"has_snapshot": bool(row["snapshot"]), "title": KINDS[row["kind"]]}

    def new_session(db, user_id, username):
        token = secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO sessions VALUES (?,?,?)",
            (digest(token), user_id, time.time() + 30 * 86400),
        )
        return {"token": token, "username": username}

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "carwatch", "api_version": 1}

    @app.post("/v1/auth/register", status_code=201)
    def register(body: Registration):
        hashed = password_hash(body.password)
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            valid = db.execute(
                "DELETE FROM invites WHERE hash=? AND expires>?", (digest(body.invite), time.time())
            ).rowcount
            if not valid:
                raise HTTPException(403, "Invite invalid or expired")
            user_id = uid()
            try:
                db.execute(
                    "INSERT INTO users VALUES (?,?,?)", (user_id, body.username.lower(), hashed)
                )
            except sqlite3.IntegrityError:
                raise HTTPException(409, "Username unavailable") from None
            return new_session(db, user_id, body.username.lower())

    @app.post("/v1/auth/login")
    def login(body: Credentials):
        with connection(path) as db:
            row = db.execute(
                "SELECT * FROM users WHERE username=?", (body.username.lower(),)
            ).fetchone()
            expected = row["password"] if row else "00" * 16 + ":" + "00" * 64
            actual = password_hash(body.password, expected.split(":")[0])
            if not row or not hmac.compare_digest(actual, expected):
                raise HTTPException(401, "Username or password incorrect")
            return new_session(db, row["id"], row["username"])

    @app.post("/v1/auth/logout")
    def logout(account=Depends(user)):
        with connection(path) as db:
            db.execute("DELETE FROM sessions WHERE hash=?", (account["hash"],))
        return {"signed_out": True}

    @app.get("/v1/me")
    def me(account=Depends(user)):
        with connection(path) as db:
            registered = bool(
                db.execute(
                    "SELECT 1 FROM installs WHERE session_hash=?", (account["hash"],)
                ).fetchone()
            )
        return {
            "username": account["username"],
            "push_configured": enabled,
            "push_registered": registered,
        }

    @app.delete("/v1/me")
    def delete_account(account=Depends(user)):
        with connection(path) as db:
            db.execute("DELETE FROM users WHERE id=?", (account["user_id"],))
        return {"deleted": True}

    @app.get("/v1/cameras")
    def cameras(account=Depends(user)):
        with connection(path) as db:
            return [
                public_camera(r)
                for r in db.execute(
                    "SELECT * FROM cameras WHERE user_id=? ORDER BY rowid", (account["user_id"],)
                )
            ]

    @app.post("/v1/cameras", status_code=201)
    def add_camera(body: Camera, account=Depends(user)):
        if not body.name.strip():
            raise HTTPException(422, "Camera name required")
        with connection(path) as db:
            if (
                db.execute(
                    "SELECT count(*) FROM cameras WHERE user_id=?", (account["user_id"],)
                ).fetchone()[0]
                >= 5
            ):
                raise HTTPException(409, "Pilot supports up to five cameras")
            camera_id = uid()
            db.execute(
                "INSERT INTO cameras (id,user_id,name) VALUES (?,?,?)",
                (camera_id, account["user_id"], body.name.strip()),
            )
            return public_camera(camera_owned(db, camera_id, account))

    @app.patch("/v1/cameras/{camera_id}")
    def set_camera(camera_id: str, body: CameraState, account=Depends(user)):
        with connection(path) as db:
            camera_owned(db, camera_id, account)
            db.execute(
                "UPDATE cameras SET armed=?,notify=? WHERE id=?",
                (body.armed, body.notify, camera_id),
            )
            if not body.armed or not body.notify:
                db.execute(
                    "UPDATE pushes SET state='cancelled',detail='Monitoring or alerts paused' WHERE event_id IN (SELECT id FROM events WHERE camera_id=?) AND state IN ('queued','retry')",
                    (camera_id,),
                )
            return public_camera(camera_owned(db, camera_id, account))

    @app.post("/v1/cameras/{camera_id}/pairing")
    def pairing(camera_id: str, account=Depends(user)):
        code = secrets.token_urlsafe(24)
        expires = time.time() + 600
        with connection(path) as db:
            row = camera_owned(db, camera_id, account)
            if row["device_hash"]:
                raise HTTPException(409, "Remove this camera before replacing its paired device")
            db.execute(
                "UPDATE cameras SET pair_hash=?,pair_expires=? WHERE id=?",
                (digest(code), expires, camera_id),
            )
        return {"code": code, "expires_at": expires}

    @app.delete("/v1/cameras/{camera_id}")
    def delete_camera(camera_id: str, account=Depends(user)):
        with connection(path) as db:
            camera_owned(db, camera_id, account)
            db.execute("DELETE FROM cameras WHERE id=?", (camera_id,))
        return {"deleted": True}

    @app.post("/v1/device/pair")
    def claim(body: Pair):
        token = secrets.token_urlsafe(32)
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id FROM cameras WHERE pair_hash=? AND pair_expires>? AND device_hash IS NULL",
                (digest(body.code), time.time()),
            ).fetchone()
            if not row:
                raise HTTPException(403, "Pairing code invalid or expired")
            db.execute(
                "UPDATE cameras SET device_hash=?,pair_hash=NULL,pair_expires=NULL,capture='ready',last_seen=? WHERE id=?",
                (digest(token), time.time(), row["id"]),
            )
        return {"token": token, "camera_id": row["id"]}

    @app.post("/v1/device/heartbeat")
    def heartbeat(body: Heartbeat, paired=Depends(device)):
        with connection(path) as db:
            db.execute(
                "UPDATE cameras SET capture=?,last_seen=? WHERE id=?",
                (body.capture, time.time(), paired["id"]),
            )
            row = db.execute(
                "SELECT armed,notify FROM cameras WHERE id=?", (paired["id"],)
            ).fetchone()
        if not row:
            raise HTTPException(401, "Device revoked or unpaired")
        return {"armed": bool(row["armed"]), "notify": bool(row["notify"])}

    @app.post("/v1/device/events", status_code=201)
    def ingest(body: Event, paired=Depends(device)):
        now = time.time()
        if not now - 120 <= body.observed_at <= now + 15:
            raise HTTPException(422, "Event timestamp outside the live sending window")
        snapshot = None
        if body.snapshot:
            try:
                raw = base64.b64decode(body.snapshot, validate=True)
                with Image.open(io.BytesIO(raw)) as im:
                    if im.format != "JPEG" or im.width * im.height > 2_000_000:
                        raise ValueError()
                    im.load()
                    im.thumbnail((960, 960))
                    out = io.BytesIO()
                    im.convert("RGB").save(out, format="JPEG", quality=80)
                    snapshot = out.getvalue()
            except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
                raise HTTPException(422, "Invalid JPEG snapshot") from None
        with connection(path) as db:
            db.execute("BEGIN IMMEDIATE")
            camera = db.execute("SELECT * FROM cameras WHERE id=?", (paired["id"],)).fetchone()
            if not camera or not camera["armed"]:
                raise HTTPException(409, "Monitoring is paused")
            existing = db.execute(
                "SELECT id FROM events WHERE camera_id=? AND source_id=?",
                (paired["id"], body.source_id),
            ).fetchone()
            if existing:
                return {"id": existing["id"], "duplicate": True}
            if (
                db.execute(
                    "SELECT count(*) FROM events WHERE camera_id=?", (paired["id"],)
                ).fetchone()[0]
                >= 1000
            ):
                raise HTTPException(
                    409,
                    "Pilot event limit reached; remove and pair a new camera after exporting needed evidence",
                )
            event_id = uid()
            recent = db.execute(
                "SELECT 1 FROM events WHERE camera_id=? AND kind=? AND origin='live' AND created>?",
                (paired["id"], body.kind, now - 30),
            ).fetchone()
            db.execute(
                "INSERT INTO events (id,camera_id,source_id,kind,observed_at,created,origin,snapshot) VALUES (?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    paired["id"],
                    body.source_id,
                    body.kind,
                    body.observed_at,
                    now,
                    body.origin,
                    snapshot,
                ),
            )
            if enabled and camera["notify"] and body.origin == "live" and not recent:
                for install in db.execute(
                    "SELECT i.token FROM installs i JOIN sessions s ON s.hash=i.session_hash WHERE s.user_id=? AND s.expires>? LIMIT 5",
                    (paired["user_id"], now),
                ):
                    db.execute(
                        "INSERT INTO pushes (id,token,event_id,created,next_at) VALUES (?,?,?,?,?)",
                        (uid(), install["token"], event_id, now, now),
                    )
        return {"id": event_id, "duplicate": False}

    @app.get("/v1/events")
    def events(account=Depends(user)):
        with connection(path) as db:
            return [
                public_event(r)
                for r in db.execute(
                    "SELECT e.*,c.name AS camera_name FROM events e JOIN cameras c ON c.id=e.camera_id WHERE c.user_id=? ORDER BY e.observed_at DESC LIMIT 100",
                    (account["user_id"],),
                )
            ]

    @app.get("/v1/events/{event_id}")
    def detail(event_id: str, account=Depends(user)):
        with connection(path) as db:
            event = public_event(event_owned(db, event_id, account))
            event["delivery"] = [
                dict(r)
                for r in db.execute("SELECT state,detail FROM pushes WHERE event_id=?", (event_id,))
            ]
            return event

    @app.get("/v1/events/{event_id}/snapshot")
    def snapshot(event_id: str, account=Depends(user)):
        with connection(path) as db:
            row = event_owned(db, event_id, account)
            if not row["snapshot"]:
                raise HTTPException(404, "No snapshot recorded")
            return Response(row["snapshot"], media_type="image/jpeg")

    @app.post("/v1/events/{event_id}/review")
    def review(event_id: str, body: Review, account=Depends(user)):
        with connection(path) as db:
            event_owned(db, event_id, account)
            db.execute("UPDATE events SET review=? WHERE id=?", (body.review, event_id))
        return {"review": body.review}

    @app.post("/v1/push")
    def register_push(body: PushToken, account=Depends(user)):
        if not enabled:
            raise HTTPException(503, "Push delivery is not configured on this server")
        with connection(path) as db:
            db.execute("DELETE FROM installs WHERE session_hash=?", (account["hash"],))
            existing = db.execute(
                "SELECT s.user_id FROM installs i JOIN sessions s ON s.hash=i.session_hash WHERE i.token=?",
                (body.token,),
            ).fetchone()
            if existing and existing["user_id"] != account["user_id"]:
                raise HTTPException(
                    409, "This installation is registered to another account; sign out there first"
                )
            count = db.execute(
                "SELECT count(*) FROM installs i JOIN sessions s ON s.hash=i.session_hash WHERE s.user_id=?",
                (account["user_id"],),
            ).fetchone()[0]
            if count >= 5:
                raise HTTPException(409, "Five notification devices are already registered")
            db.execute("DELETE FROM installs WHERE token=?", (body.token,))
            db.execute("INSERT INTO installs VALUES (?,?)", (body.token, account["hash"]))
        return {"registered": True}

    @app.delete("/v1/push")
    def disable_push(account=Depends(user)):
        with connection(path) as db:
            db.execute("DELETE FROM installs WHERE session_hash=?", (account["hash"],))
        return {"registered": False}

    @app.post("/v1/push/test")
    def test_push(account=Depends(user)):
        now = time.time()
        if not enabled:
            raise HTTPException(503, "Push delivery is not configured")
        with connection(path) as db:
            install = db.execute(
                "SELECT token FROM installs WHERE session_hash=?", (account["hash"],)
            ).fetchone()
            if not install:
                raise HTTPException(409, "Enable notifications on this device first")
            if db.execute(
                "SELECT 1 FROM pushes WHERE token=? AND created>?", (install["token"], now - 30)
            ).fetchone():
                raise HTTPException(429, "Wait 30 seconds before sending another test")
            db.execute(
                "INSERT INTO pushes (id,token,created,next_at) VALUES (?,?,?,?)",
                (uid(), install["token"], now, now),
            )
        return {"queued": True, "detail": "Test queued; confirm receipt on your phone"}

    return app
