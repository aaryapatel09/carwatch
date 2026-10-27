"""Bounded Expo delivery; service receipts never establish physical phone receipt."""

import time

import httpx

from server.database import connection

EXPO = "https://exp.host/--/api/v2/push/"


class ExpoTransport:
    def __init__(self, access_token):
        self.access_token = access_token

    def _request(self, action, payload):
        # Fixed provider origin, verified TLS, bounded response, no redirects.
        with httpx.Client(timeout=8, follow_redirects=False) as client:
            with client.stream(
                "POST",
                EXPO + action,
                json=payload,
                headers={"Authorization": "Bearer " + self.access_token},
            ) as response:
                if response.status_code == 429 or response.status_code >= 500:
                    return {"retry": True}
                if response.status_code != 200:
                    return {"error": "Provider rejected request"}
                data = b""
                for part in response.iter_bytes():
                    data += part
                    if len(data) > 16384:
                        return {"error": "Provider acknowledgement too large"}
                import json

                result = json.loads(data)
                return result if isinstance(result, dict) else {"error": "Invalid acknowledgement"}

    def send(self, token, event_id):
        payload = {
            "to": token,
            "title": "Carwatch" if event_id else "Carwatch · test notification",
            "body": "New activity is ready to review."
            if event_id
            else "Open Carwatch to check your notification setup.",
            "sound": "default",
            "channelId": "carwatch-activity",
            "ttl": 120,
            "data": {"eventId": event_id} if event_id else {"test": True},
        }
        return self._request("send", payload)

    def receipts(self, ticket):
        return self._request("getReceipts", {"ids": [ticket]})


class PushWorker:
    def __init__(self, path, transport):
        self.path, self.transport = path, transport

    def recover(self):
        with connection(self.path) as db:
            db.execute(
                "UPDATE pushes SET state='unconfirmed', detail='Server restarted during send' WHERE state='sending'"
            )

    def tick(self, now=None):
        now = time.time() if now is None else now
        with connection(self.path) as db:
            db.execute("DELETE FROM sessions WHERE expires < ?", (now,))
            db.execute(
                "UPDATE pushes SET state='expired',detail='Sending window expired' WHERE state IN ('queued','retry') AND created < ?",
                (now - 120,),
            )
            rows = db.execute(
                "SELECT p.*,s.user_id FROM pushes p JOIN installs i ON p.token=i.token JOIN sessions s ON s.hash=i.session_hash WHERE p.state IN ('queued','retry','ticket') AND p.next_at<=? LIMIT 20",
                (now,),
            ).fetchall()
        for row in rows:
            if row["state"] == "ticket":
                self._receipt(row, now)
                continue
            with connection(self.path) as db:
                # Ownership, session and armed state are rechecked immediately before claiming.
                valid = db.execute(
                    "SELECT 1 FROM installs i JOIN sessions s ON s.hash=i.session_hash WHERE i.token=? AND s.expires>?",
                    (row["token"], now),
                ).fetchone()
                if row["event_id"]:
                    valid = (
                        valid
                        and db.execute(
                            "SELECT 1 FROM events e JOIN cameras c ON c.id=e.camera_id WHERE e.id=? AND c.armed=1 AND c.notify=1 AND c.user_id=?",
                            (row["event_id"], row["user_id"]),
                        ).fetchone()
                    )
                if not valid:
                    db.execute(
                        "UPDATE pushes SET state='cancelled',detail='Notifications stopped' WHERE id=?",
                        (row["id"],),
                    )
                    continue
                claimed = db.execute(
                    "UPDATE pushes SET state='sending',attempts=attempts+1 WHERE id=? AND state IN ('queued','retry')",
                    (row["id"],),
                ).rowcount
            if not claimed:
                continue
            try:
                result = self.transport.send(row["token"], row["event_id"])
            except (httpx.HTTPError, ValueError):
                result = {"retry": True}  # May have been accepted; retries can duplicate.
            data = result.get("data", {})
            if (
                isinstance(data, dict)
                and data.get("status") == "ok"
                and isinstance(data.get("id"), str)
                and len(data["id"]) < 200
            ):
                state, detail, ticket = (
                    "ticket",
                    "Accepted by Expo; phone receipt unverified",
                    data["id"],
                )
                next_at = now + 900
            elif result.get("retry") and row["attempts"] < 2:
                state, detail, ticket, next_at = (
                    "retry",
                    "Transient failure; delivery unconfirmed",
                    None,
                    now + 15 * (row["attempts"] + 1),
                )
            else:
                state, detail, ticket, next_at = (
                    "failed",
                    "Delivery failed or acknowledgement invalid",
                    None,
                    now,
                )
            with connection(self.path) as db:
                db.execute(
                    "UPDATE pushes SET state=?,detail=?,ticket=?,next_at=? WHERE id=?",
                    (state, detail, ticket, next_at, row["id"]),
                )
                if (
                    isinstance(data, dict)
                    and isinstance(data.get("details"), dict)
                    and data["details"].get("error") == "DeviceNotRegistered"
                ):
                    db.execute("DELETE FROM installs WHERE token=?", (row["token"],))

    def _receipt(self, row, now):
        if now - row["created"] > 86400:
            result = None
        else:
            try:
                result = self.transport.receipts(row["ticket"])
            except (httpx.HTTPError, ValueError):
                result = {}
        payload = (result or {}).get("data", {})
        receipt = payload.get(row["ticket"]) if isinstance(payload, dict) else None
        if not isinstance(receipt, dict):
            receipt = None
        if receipt and receipt.get("status") in ("ok", "error"):
            state = "provider_received" if receipt["status"] == "ok" else "failed"
            detail = (
                "Push provider receipt; phone display unverified"
                if state == "provider_received"
                else "Provider reported delivery failure"
            )
        elif result is None:
            state, detail = "unconfirmed", "Receipt window expired"
        else:
            state, detail = "ticket", "Awaiting provider receipt"
        with connection(self.path) as db:
            db.execute(
                "UPDATE pushes SET state=?,detail=?,next_at=? WHERE id=?",
                (state, detail, now + 900, row["id"]),
            )
            if (
                receipt
                and isinstance(receipt.get("details"), dict)
                and receipt["details"].get("error") == "DeviceNotRegistered"
            ):
                db.execute("DELETE FROM installs WHERE token=?", (row["token"],))
