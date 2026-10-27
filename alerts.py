"""Explicitly enabled, text-only ntfy publishing for bounded live sessions."""

import http.client
import json
import os
import re
import ssl
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

from store import read_json, write_json

MESSAGES = {
    "lingering": "A sustained-presence cue was recorded in the selected image zone.",
    "repeated_approach": "A repeated-entry cue was recorded in the selected image zone.",
    "hand_near_zone": "An estimated-wrist cue was recorded near the selected region. Contact is unconfirmed.",
}
PENDING = {"queued", "retry", "sending"}


@dataclass(frozen=True)
class AlertConfig:
    server: str = field(repr=False)
    topic: str = field(repr=False)
    token: str = field(repr=False)

    def validate(self):
        if not all(isinstance(v, str) for v in (self.server, self.topic, self.token)):
            raise ValueError("Notification configuration must contain text values")
        try:
            url = urlsplit(self.server)
            port = url.port
        except ValueError as exc:
            raise ValueError("Invalid notification server URL") from exc
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or (port is not None and not 1 <= port <= 65535)
            or any(ord(c) < 33 or ord(c) > 126 for c in self.server)
        ):
            raise ValueError(
                "Notification server must be an HTTPS origin without credentials or a path"
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,64}", self.topic):
            raise ValueError(
                "Notification topic must contain 3–64 letters, digits, hyphens or underscores"
            )
        if not re.fullmatch(r"[!-~]{8,512}", self.token):
            raise ValueError("A valid notification access token is required")
        return self

    @classmethod
    def from_env(cls):
        if os.environ.get("CARWATCH_NTFY_PRIVATE") != "1":
            raise ValueError("Configure and confirm a private ntfy topic before enabling alerts")
        return cls(
            os.environ.get("CARWATCH_NTFY_SERVER", ""),
            os.environ.get("CARWATCH_NTFY_TOPIC", ""),
            os.environ.get("CARWATCH_NTFY_TOKEN", ""),
        ).validate()


def publish(config, kind, observed_at, *, context=None):
    """Report service acceptance, never phone receipt. Redirects are not followed."""
    config.validate()
    if kind not in MESSAGES:
        raise ValueError("Unsupported notification cue")
    url = urlsplit(config.server)
    connection = http.client.HTTPSConnection(
        url.hostname, url.port, timeout=3, context=context or ssl.create_default_context()
    )
    stamp = datetime.fromtimestamp(observed_at, timezone.utc).isoformat(timespec="seconds")
    body = (
        MESSAGES[kind]
        + f" Observed at {stamp}. Review local evidence; this is not a safety assessment."
    ).encode()
    try:
        connection.request(
            "POST",
            "/" + config.topic,
            body=body,
            headers={
                "Authorization": "Bearer " + config.token,
                "Content-Type": "text/plain; charset=utf-8",
                "Title": "Carwatch activity",
                "Priority": "3",
            },
        )
        response = connection.getresponse()
        if response.status in (408, 429) or response.status >= 500:
            return "retry", "Notification service temporarily unavailable"
        if not 200 <= response.status < 300:
            return "failed", f"Notification service rejected the request (HTTP {response.status})"
        data = response.read(8193)
        if len(data) > 8192:
            return "unconfirmed", "Service response exceeded the acknowledgement limit"
        acknowledgement = json.loads(data)
        if (
            not isinstance(acknowledgement, dict)
            or acknowledgement.get("event") != "message"
            or acknowledgement.get("topic") != config.topic
            or not isinstance(acknowledgement.get("id"), str)
            or not acknowledgement["id"]
        ):
            return "unconfirmed", "Service returned no valid message acknowledgement"
        return "accepted", "Accepted by notification service; phone receipt is unverified"
    except ssl.SSLCertVerificationError:
        return "failed", "Notification server certificate could not be verified"
    except (OSError, http.client.HTTPException):
        # Do not persist exception text: it may contain the private URL or token.
        return "retry", "Network error; delivery is unconfirmed and a retry may duplicate it"
    except ValueError:
        return "unconfirmed", "Service returned an unreadable acknowledgement"
    finally:
        connection.close()


def cancel_pending(path):
    """Call only after the dispatcher/owning camera process has stopped."""
    rows = read_json(path, [])
    for row in rows:
        if row["status"] in PENDING:
            row["status"] = "unconfirmed" if row["attempts"] else "cancelled"
            row["detail"] = "Session stopped; no further attempts will be made"
    if rows:
        write_json(path, rows)
    return dict(Counter(row["status"] for row in rows))


class AlertDispatcher:
    """At most 100 cues/session, one per kind/30s, three attempts within 60s.

    Network work runs outside capture. Pending messages never resume after a
    restart or Stop. Journal entries contain no credentials, URLs, or media.
    """

    def __init__(
        self, config, path, sender=publish, clock=time.monotonic, wall=time.time, stop_signal=None
    ):
        self.config = config.validate()
        self.path, self.sender, self.clock, self.wall = path, sender, clock, wall
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.stop_signal = stop_signal
        self.rows, self.schedule, self.last_kind = {}, {}, {}
        self.thread = None
        self.error = None

    def _stopped(self):
        return self.stop_event.is_set() or (
            self.stop_signal is not None and self.stop_signal.is_set()
        )

    def _save(self):
        write_json(self.path, list(self.rows.values()))

    def enqueue(self, event_id, kind):
        if kind not in MESSAGES or not isinstance(event_id, str) or not 1 <= len(event_id) <= 80:
            raise ValueError("Invalid notification event")
        with self.lock:
            if self._stopped() or event_id in self.rows or len(self.rows) >= 100:
                return False
            now = self.clock()
            suppressed = now - self.last_kind.get(kind, -float("inf")) < 30
            self.rows[event_id] = dict(
                event_id=event_id,
                kind=kind,
                observed_at=self.wall(),
                status="suppressed" if suppressed else "queued",
                attempts=0,
                detail="Same cue is within the 30-second cooldown"
                if suppressed
                else "Waiting to send",
            )
            if not suppressed:
                self.last_kind[kind] = now
                self.schedule[event_id] = (now, now + 60)
            self._save()
            return not suppressed

    def step(self):
        with self.lock:
            if self._stopped():
                return False
            now = self.clock()
            chosen = None
            for event_id, (due, expiry) in list(self.schedule.items()):
                row = self.rows[event_id]
                if row["status"] not in ("queued", "retry"):
                    continue
                if now >= expiry:
                    row.update(status="expired", detail="Alert expired before service acceptance")
                    del self.schedule[event_id]
                    self._save()
                elif now >= due and chosen is None:
                    chosen = event_id
            if chosen is None:
                return False
            row = self.rows[chosen]
            row.update(status="sending", attempts=row["attempts"] + 1)
            self._save()
            kind, observed_at = row["kind"], row["observed_at"]
        try:
            status, detail = self.sender(self.config, kind, observed_at)
        except Exception:
            status, detail = "unconfirmed", "Notification transport failed; delivery is unconfirmed"
        with self.lock:
            if self._stopped():
                row.update(status="unconfirmed", detail="Session stopped during a delivery attempt")
            elif status == "retry" and row["attempts"] >= 3:
                row.update(
                    status="unconfirmed", detail="Retry limit reached; phone receipt is unverified"
                )
            else:
                row.update(status=status, detail=detail)
            if row["status"] == "retry":
                self.schedule[chosen] = (
                    self.clock() + (1 if row["attempts"] == 1 else 5),
                    self.schedule[chosen][1],
                )
            else:
                self.schedule.pop(chosen, None)
            self._save()
        return True

    def start(self):
        def run():
            try:
                while not self.stop_event.wait(0.1):
                    if self._stopped():
                        break
                    self.step()
            except Exception:
                # A journal/storage failure must stop new outbound attempts.
                self.error = "Notification worker stopped after a journal failure"
                self.stop_event.set()

        with self.lock:
            if self.thread is not None or self._stopped():
                raise ValueError("Notification dispatcher cannot be restarted")
            self.thread = threading.Thread(target=run, daemon=True)
            self.thread.start()

    def snapshot(self):
        with self.lock:
            summary = dict(Counter(row["status"] for row in self.rows.values()))
            if self.error:
                summary["error"] = self.error
            return summary

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=0.2)
        with self.lock:
            for row in self.rows.values():
                if row["status"] in PENDING:
                    row["status"] = "unconfirmed" if row["attempts"] else "cancelled"
                    row["detail"] = "Session stopped; no further attempts will be made"
            self.schedule.clear()
            self._save()
