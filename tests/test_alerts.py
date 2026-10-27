import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import alerts
from alerts import AlertConfig, AlertDispatcher, cancel_pending, publish
from config import CameraConfig
from live import LiveMonitor
from store import read_json, write_json


@pytest.fixture
def config():
    return AlertConfig("https://notify.example.invalid", "private-topic", "fixture-token")


@pytest.mark.parametrize(
    "server,topic,token",
    [
        ("http://host", "topic", "fixture-token"),
        ("https://user:password@host", "topic", "fixture-token"),
        ("https://host/path", "topic", "fixture-token"),
        ("https://host?secret=value", "topic", "fixture-token"),
        ("https://host", "../topic", "fixture-token"),
        ("https://host", "topic", "bad\r\nheader"),
        ("https://host", "topic", ""),
        (None, "topic", "fixture-token"),
    ],
)
def test_alert_configuration_rejects_unsafe_destinations(server, topic, token):
    with pytest.raises(ValueError):
        AlertConfig(server, topic, token).validate()


def test_alerts_require_explicit_configuration_before_camera_access(tmp_path, monkeypatch):
    monkeypatch.delenv("CARWATCH_NTFY_PRIVATE", raising=False)
    with pytest.raises(ValueError, match="private"):
        AlertConfig.from_env()
    monitor = LiveMonitor(root=tmp_path)
    with pytest.raises(ValueError, match="private"):
        monitor.start(0, CameraConfig(), phone_alerts=True)
    assert monitor.process is None and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "code,payload,expected",
    [
        (200, {"id": "ack", "event": "message", "topic": "private-topic"}, "accepted"),
        (200, {"id": "ack", "event": "message", "topic": "wrong"}, "unconfirmed"),
        (200, [], "unconfirmed"),
        (200, b"not-json", "unconfirmed"),
        (200, b"x" * 9000, "unconfirmed"),
        (401, {}, "failed"),
        (302, {}, "failed"),
        (429, {}, "retry"),
        (503, {}, "retry"),
    ],
)
def test_publish_protocol_acknowledgements_and_no_redirect(
    config, monkeypatch, code, payload, expected
):
    calls = []
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    class Connection:
        def __init__(self, host, port, timeout, context):
            assert host == "notify.example.invalid" and timeout == 3
            assert context.check_hostname and context.verify_mode == 2
            self.status = code

        def request(self, method, path, body, headers):
            calls.append((method, path, body, headers))

        def getresponse(self):
            return self

        def read(self, limit):
            return data[:limit]

        def close(self):
            self.closed = True

    monkeypatch.setattr(alerts.http.client, "HTTPSConnection", Connection)
    status, detail = publish(config, "hand_near_zone", 1700000000)
    assert status == expected and len(calls) == 1
    method, path, body, headers = calls[0]
    assert method == "POST" and path == "/private-topic"
    assert headers["Authorization"] == "Bearer fixture-token"
    assert b"Contact is unconfirmed" in body and b"2023-11-14" in body
    assert "fixture-token" not in detail and "private-topic" not in detail
    assert "fixture-token" not in repr(config)


def test_retry_limit_dedup_cooldown_and_expiry(config, tmp_path):
    now = [0.0]
    calls = []

    def fail(*args):
        calls.append(args)
        return "retry", "offline"

    dispatcher = AlertDispatcher(config, tmp_path / "alerts.json", fail, lambda: now[0])
    assert dispatcher.enqueue("e1", "lingering")
    assert not dispatcher.enqueue("e1", "lingering")
    assert not dispatcher.enqueue("e2", "lingering")
    assert dispatcher.step() and not dispatcher.step()
    now[0] = 1
    assert dispatcher.step()
    now[0] = 6
    assert dispatcher.step()
    assert len(calls) == 3 and dispatcher.snapshot() == {"unconfirmed": 1, "suppressed": 1}
    assert dispatcher.enqueue("e3", "hand_near_zone")
    now[0] = 66
    assert not dispatcher.step()
    assert dispatcher.snapshot()["expired"] == 1
    assert "fixture-token" not in (tmp_path / "alerts.json").read_text()
    assert "notify.example" not in (tmp_path / "alerts.json").read_text()


def test_stop_cancels_unsent_and_preserves_ambiguous_attempt(config, tmp_path):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def slow(*args):
        calls.append(args)
        entered.set()
        assert release.wait(3)
        return "accepted", "service accepted"

    dispatcher = AlertDispatcher(config, tmp_path / "alerts.json", slow)
    dispatcher.enqueue("e1", "lingering")
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(dispatcher.step)
        assert entered.wait(3)
        assert not dispatcher.step()  # An in-flight event cannot be sent a second time.
        dispatcher.enqueue("e2", "hand_near_zone")
        dispatcher.close()
        release.set()
        pending.result(timeout=3)
    assert not dispatcher.enqueue("e3", "repeated_approach")
    assert not dispatcher.step()
    assert dispatcher.snapshot() == {"unconfirmed": 1, "cancelled": 1}
    assert len(calls) == 1


def test_stopped_journal_never_resumes(config, tmp_path):
    path = tmp_path / "alerts.json"
    dispatcher = AlertDispatcher(config, path, lambda *a: ("retry", "offline"))
    dispatcher.enqueue("e1", "lingering")
    dispatcher.step()
    dispatcher.enqueue("e2", "hand_near_zone")
    assert cancel_pending(path) == {"unconfirmed": 1, "cancelled": 1}
    assert all(row["status"] not in alerts.PENDING for row in read_json(path))


def incomplete_alert_worker(camera, config, minutes, stop, messages, out):
    write_json(out / "session.json", dict(status="running", events=[]))
    write_json(
        out / "alerts.json",
        [
            dict(event_id="e1", status="sending", attempts=1),
            dict(event_id="e2", status="queued", attempts=0),
        ],
    )


def test_unexpected_camera_process_exit_cancels_pending_alerts(tmp_path):
    monitor = LiveMonitor(root=tmp_path, worker=incomplete_alert_worker)
    monitor.start(0, CameraConfig())
    try:
        monitor.process.join(timeout=10)
        assert not monitor.process.is_alive()
        state = monitor.snapshot()
        assert state["status"] == "error"
        assert state["alerts"] == {"unconfirmed": 1, "cancelled": 1}
    finally:
        monitor.stop()


def test_network_exceptions_never_persist_credentials(config, monkeypatch):
    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            raise OSError("fixture-token at https://notify.example.invalid/private-topic")

        def close(self):
            pass

    monkeypatch.setattr(alerts.http.client, "HTTPSConnection", Connection)
    status, detail = publish(config, "lingering", 1700000000)
    assert status == "retry"
    assert "fixture-token" not in detail and "example.invalid" not in detail


def test_camera_stop_signal_prevents_new_attempts_even_if_capture_is_blocked(config, tmp_path):
    stop = threading.Event()
    dispatcher = AlertDispatcher(
        config,
        tmp_path / "alerts.json",
        sender=lambda *a: pytest.fail("must not send"),
        stop_signal=stop,
    )
    dispatcher.enqueue("e1", "lingering")
    stop.set()
    assert not dispatcher.step()
    assert not dispatcher.enqueue("e2", "hand_near_zone")
    dispatcher.close()
    assert dispatcher.snapshot() == {"cancelled": 1}
