import base64
import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from server.api import create_app
from server.database import connection, invite


class Transport:
    def __init__(self):
        self.messages = []
        self.result = {"data": {"status": "ok", "id": "fixture-ticket"}}

    def send(self, token, event_id):
        self.messages.append((token, event_id))
        return self.result

    def receipts(self, ticket):
        return {"data": {ticket: {"status": "ok"}}}


@pytest.fixture
def pilot(tmp_path):
    db = tmp_path / "test.sqlite3"
    transport = Transport()
    app = create_app(db, push_enabled=True, transport=transport, background=False)
    with TestClient(app) as client:
        yield client, db, app.state.worker, transport


def account(client, db, name="alice"):
    code = invite(db)
    response = client.post(
        "/v1/auth/register",
        json={"username": name, "password": "fixture-passphrase-123", "invite": code},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": "Bearer " + response.json()["token"]}


def station(client, auth):
    camera = client.post("/v1/cameras", headers=auth, json={"name": "Driver side"}).json()
    camera_id = camera["id"]
    code = client.post(f"/v1/cameras/{camera_id}/pairing", headers=auth).json()["code"]
    paired = client.post("/v1/device/pair", json={"code": code})
    assert paired.status_code == 200
    assert client.post("/v1/device/pair", json={"code": code}).status_code == 403
    device = {"Authorization": "Bearer " + paired.json()["token"]}
    client.patch(f"/v1/cameras/{camera_id}", headers=auth, json={"armed": True, "notify": True})
    return camera_id, device


def body(key="first", origin="live"):
    out = io.BytesIO()
    Image.new("RGB", (80, 60), "green").save(out, "JPEG")
    return {
        "source_id": key,
        "kind": "lingering",
        "observed_at": time.time(),
        "origin": origin,
        "snapshot": base64.b64encode(out.getvalue()).decode(),
    }


def test_private_end_to_end_evidence_pairing_push_review(pilot):
    client, db, worker, transport = pilot
    alice, bob = account(client, db), account(client, db, "bob")
    camera, device = station(client, alice)
    assert client.get("/v1/events").status_code == 401
    assert client.get("/v1/cameras", headers=bob).json() == []
    assert client.post(f"/v1/cameras/{camera}/pairing", headers=bob).status_code == 404
    assert client.get("/v1/events", headers=device).status_code == 401
    heartbeat = client.post("/v1/device/heartbeat", headers=device, json={"capture": "running"})
    assert heartbeat.json()["armed"] is True
    token = "ExpoPushToken[fixture_install_12345]"
    assert client.post("/v1/push", headers=alice, json={"token": token}).status_code == 200
    event = client.post("/v1/device/events", headers=device, json=body())
    assert event.status_code == 201, event.text
    eid = event.json()["id"]
    assert client.post("/v1/device/events", headers=device, json=body()).json()["duplicate"]
    assert len(client.get("/v1/events", headers=alice).json()) == 1
    for suffix in ["", "/snapshot"]:
        assert client.get("/v1/events/" + eid + suffix, headers=bob).status_code == 404
    snap = client.get("/v1/events/" + eid + "/snapshot", headers=alice)
    assert snap.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(snap.content)).size == (80, 60)
    assert (
        client.post(
            "/v1/events/" + eid + "/review", headers=alice, json={"review": "ordinary"}
        ).status_code
        == 200
    )
    worker.tick()
    assert transport.messages == [(token, eid)]
    assert client.get("/v1/events/" + eid, headers=alice).json()["delivery"][0]["state"] == "ticket"
    worker.tick(time.time() + 901)
    assert (
        client.get("/v1/events/" + eid, headers=alice).json()["delivery"][0]["state"]
        == "provider_received"
    )


def test_pause_logout_and_revoke_prevent_future_delivery(pilot):
    client, db, worker, transport = pilot
    auth = account(client, db)
    cid, device = station(client, auth)
    client.post("/v1/push", headers=auth, json={"token": "ExpoPushToken[fixture_install_12345]"})
    client.post("/v1/device/events", headers=device, json=body())
    client.patch("/v1/cameras/" + cid, headers=auth, json={"armed": False, "notify": True})
    worker.tick()
    assert not transport.messages
    assert client.post("/v1/device/events", headers=device, json=body("two")).status_code == 409
    client.patch("/v1/cameras/" + cid, headers=auth, json={"armed": True, "notify": True})
    client.post("/v1/auth/logout", headers=auth)
    assert client.get("/v1/me", headers=auth).status_code == 401
    assert client.post("/v1/device/events", headers=device, json=body("three")).status_code == 201
    worker.tick()
    assert not transport.messages


def test_account_deletion_revokes_camera_and_cascades_private_data(pilot):
    client, db, worker, _ = pilot
    auth = account(client, db)
    _, device = station(client, auth)
    client.post("/v1/device/events", headers=device, json=body())
    assert client.delete("/v1/me", headers=auth).status_code == 200
    assert (
        client.post("/v1/device/heartbeat", headers=device, json={"capture": "running"}).status_code
        == 401
    )
    with connection(db) as conn:
        for table in ("users", "sessions", "cameras", "events", "pushes", "installs"):
            assert conn.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0


def test_demo_events_and_stale_events_do_not_send(pilot):
    client, db, worker, transport = pilot
    auth = account(client, db)
    _, device = station(client, auth)
    client.post("/v1/push", headers=auth, json={"token": "ExpoPushToken[fixture_install_12345]"})
    assert (
        client.post("/v1/device/events", headers=device, json=body(origin="demo")).status_code
        == 201
    )
    stale = body("stale")
    stale["observed_at"] -= 200
    assert client.post("/v1/device/events", headers=device, json=stale).status_code == 422
    invalid = body("image")
    invalid["snapshot"] = base64.b64encode(b"<svg/>").decode()
    assert client.post("/v1/device/events", headers=device, json=invalid).status_code == 422
    worker.tick()
    assert not transport.messages


def test_invite_single_use_password_and_tokens_are_not_plaintext(pilot):
    client, db, _, _ = pilot
    code = invite(db)
    data = {"username": "alice", "password": "fixture-passphrase-123", "invite": code}
    reply = client.post("/v1/auth/register", json=data)
    assert reply.status_code == 201
    assert client.post("/v1/auth/register", json={**data, "username": "bob"}).status_code == 403
    assert (
        client.post(
            "/v1/auth/login", json={"username": "alice", "password": "wrong-passphrase"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/auth/login", json={"username": "alice", "password": data["password"]}
        ).status_code
        == 200
    )
    with connection(db) as conn:
        assert conn.execute("SELECT password FROM users").fetchone()[0] != data["password"]
        assert (
            conn.execute("SELECT hash FROM sessions LIMIT 1").fetchone()[0] != reply.json()["token"]
        )
    bad = client.post("/v1/auth/login", json={"username": "alice", "password": "secret"})
    assert "secret" not in bad.text


def test_pairing_expiry_and_install_ownership(pilot):
    client, db, _, _ = pilot
    alice, bob = account(client, db), account(client, db, "bob")
    cid = client.post("/v1/cameras", headers=alice, json={"name": "Camera"}).json()["id"]
    code = client.post("/v1/cameras/" + cid + "/pairing", headers=alice).json()["code"]
    with connection(db) as conn:
        conn.execute("UPDATE cameras SET pair_expires=0")
    assert client.post("/v1/device/pair", json={"code": code}).status_code == 403
    token = {"token": "ExpoPushToken[fixture_install_12345]"}
    assert client.post("/v1/push", headers=alice, json=token).status_code == 200
    assert client.post("/v1/push", headers=bob, json=token).status_code == 409
    assert client.delete("/v1/push", headers=alice).status_code == 200
    assert client.post("/v1/push", headers=bob, json=token).status_code == 200


def test_retry_expiry_cooldown_and_crash_recovery(pilot):
    client, db, worker, transport = pilot
    auth = account(client, db)
    _, device = station(client, auth)
    client.post("/v1/push", headers=auth, json={"token": "ExpoPushToken[fixture_install_12345]"})
    client.post("/v1/device/events", headers=device, json=body())
    client.post("/v1/device/events", headers=device, json=body("second"))
    transport.result = {"retry": True}
    now = time.time()
    worker.tick(now)
    worker.tick(now + 16)
    worker.tick(now + 47)
    assert len(transport.messages) == 3
    with connection(db) as conn:
        assert conn.execute("SELECT count(*) FROM pushes").fetchone()[0] == 1
        assert conn.execute("SELECT state FROM pushes").fetchone()[0] == "failed"
        conn.execute("UPDATE pushes SET state='sending'")
    worker.recover()
    with connection(db) as conn:
        assert conn.execute("SELECT state FROM pushes").fetchone()[0] == "unconfirmed"
        conn.execute("UPDATE pushes SET state='queued'")
    worker.tick(now + 121)
    assert len(transport.messages) == 3
    with connection(db) as conn:
        assert conn.execute("SELECT state FROM pushes").fetchone()[0] == "expired"


def test_request_bounds_and_push_disabled(tmp_path):
    db = tmp_path / "off.sqlite3"
    with TestClient(create_app(db, push_enabled=False, background=False)) as client:
        auth = account(client, db)
        assert client.get("/v1/me", headers=auth).json()["push_configured"] is False
        assert (
            client.post(
                "/v1/push", headers=auth, json={"token": "ExpoPushToken[fixture_install_12345]"}
            ).status_code
            == 503
        )
        assert client.post("/v1/auth/login", content=b"x" * 320001).status_code == 413
        for _ in range(21):
            result = client.post("/v1/auth/login", json={})
        assert result.status_code == 429


def test_push_payload_is_generic_and_transport_rejects_redirect(monkeypatch):
    import json

    import httpx

    from server.push import ExpoTransport

    calls = []
    real_client = httpx.Client

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={"data": {"status": "ok", "id": "ticket"}})
        return httpx.Response(302, headers={"Location": "https://example.invalid/untrusted"})

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    service = ExpoTransport("fixture-access-token")
    assert (
        service.send("ExpoPushToken[fixture_install_12345]", "event-123")["data"]["status"] == "ok"
    )
    payload = json.loads(calls[0].content)
    assert payload["data"] == {"eventId": "event-123"}
    assert payload["ttl"] == 120
    assert "image" not in payload and "camera" not in payload and "location" not in payload
    assert calls[0].headers["authorization"] == "Bearer fixture-access-token"
    assert service.send("ExpoPushToken[fixture_install_12345]", "event-123")["error"]
    assert len(calls) == 2


def test_malformed_receipt_remains_unconfirmed(pilot):
    client, db, worker, transport = pilot
    auth = account(client, db)
    _, device = station(client, auth)
    client.post("/v1/push", headers=auth, json={"token": "ExpoPushToken[fixture_install_12345]"})
    client.post("/v1/device/events", headers=device, json=body())
    worker.tick()
    transport.receipts = lambda ticket: {"data": None}
    worker.tick(time.time() + 901)
    with connection(db) as conn:
        assert conn.execute("SELECT state FROM pushes").fetchone()[0] == "ticket"
