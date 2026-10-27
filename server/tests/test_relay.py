"""Exercise the station without opening hardware or sending a network request."""

import json
import sys
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from server import relay


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example",
        "https://user:secret@example.com",
        "https://example.com/path",
        "https://example.com?token=a",
    ],
)
def test_rejects_unsafe_station_destination(url):
    with pytest.raises(ValueError):
        relay.valid_url(url)


def test_one_minute_station_starts_only_when_armed_and_stops_on_disconnect(tmp_path, monkeypatch):
    credential = tmp_path / "station.json"
    credential.write_text(json.dumps({"server": "https://api.example", "token": "fixture"}))
    profile = tmp_path / "profile.json"
    profile.write_text("{}")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "relay",
            "--server",
            "https://api.example",
            "--credential",
            str(credential),
            "--profile",
            str(profile),
            "--minutes",
            "1",
        ],
    )
    clock = [0.0]
    monkeypatch.setattr(relay.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        relay.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )

    class Monitor:
        status = "idle"
        starts = 0
        stops = 0

        def snapshot(self):
            return {"status": self.status, "events": []}

        def start(self, camera, config, minutes):
            assert 1 <= minutes <= 10
            self.starts += 1
            self.status = "running"

        def stop(self):
            self.stops += 1
            self.status = "stopped"

    monitor = Monitor()
    monkeypatch.setitem(sys.modules, "live", SimpleNamespace(LiveMonitor=lambda: monitor))
    monkeypatch.setitem(
        sys.modules,
        "config",
        SimpleNamespace(CameraConfig=SimpleNamespace(from_dict=lambda data: data)),
    )
    calls = []

    def request(url, path, body, token):
        assert path == "/v1/device/heartbeat"
        calls.append(body)
        if len(calls) == 1:
            assert monitor.starts == 0
            return {"armed": False}
        if len(calls) == 2:
            assert monitor.starts == 0
            return {"armed": True}
        raise URLError("fixture connection loss")

    monkeypatch.setattr(relay, "api", request)
    with pytest.raises(URLError):
        relay.main()
    assert monitor.starts == 1
    assert monitor.status == "stopped"
    assert calls[-1] == {"capture": "stopped"}


def test_pairing_stores_private_credential_without_opening_camera(tmp_path, monkeypatch):
    dest = tmp_path / "station.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["relay", "--server", "https://api.example", "--pair", "--credential", str(dest)],
    )
    monkeypatch.setattr(relay.getpass, "getpass", lambda prompt: "fixture-code")

    def request(url, path, body):
        assert body == {"code": "fixture-code"}
        assert path == "/v1/device/pair"
        return {"token": "fixture-device-token", "camera_id": "fixture-camera"}

    monkeypatch.setattr(relay, "api", request)
    relay.main()
    assert dest.stat().st_mode & 0o777 == 0o600
    assert json.loads(dest.read_text())["server"] == "https://api.example"
