"""Explicitly started USB camera station for the native pilot. No unattended start."""

import argparse
import base64
import getpass
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(url, path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(url + path, data=json.dumps(body).encode(), headers=headers, method="POST")
    with build_opener(NoRedirect).open(req, timeout=8) as response:
        raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError("Response too large")
        return json.loads(raw)


def valid_url(value):
    url = urlsplit(value)
    local = url.hostname in ("127.0.0.1", "localhost")
    if (
        url.username
        or url.password
        or url.path not in ("", "/")
        or url.query
        or url.fragment
        or not url.hostname
        or (url.scheme != "https" and not (local and url.scheme == "http"))
    ):
        raise ValueError("Use HTTPS (HTTP is allowed only for loopback development)")
    return value.rstrip("/")


def main():
    parser = argparse.ArgumentParser(
        description="Run a consenting, supervised camera pilot for at most ten minutes."
    )
    parser.add_argument("--server", required=True)
    parser.add_argument("--pair", action="store_true")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--minutes", type=int, choices=range(1, 11), default=2)
    parser.add_argument(
        "--profile", type=Path, help="JSON CameraConfig from a calibrated local view"
    )
    parser.add_argument("--credential", type=Path, default=Path("runtime/station.json"))
    args = parser.parse_args()
    url = valid_url(args.server)
    if args.pair:
        result = api(url, "/v1/device/pair", {"code": getpass.getpass("Single-use pairing code: ")})
        args.credential.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.credential, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"server": url, **result}, f)
        args.credential.chmod(0o600)
        print("Station paired. Start it again without --pair when ready to monitor.")
        return
    credential = json.loads(args.credential.read_text())
    if credential["server"] != url:
        raise ValueError("Credential belongs to another server")
    if not args.profile:
        raise ValueError(
            "Supply --profile with a calibrated CameraConfig JSON before camera monitoring"
        )
    from config import CameraConfig
    from live import LiveMonitor

    profile = CameraConfig.from_dict(json.loads(args.profile.read_text()))
    token = credential["token"]
    monitor = LiveMonitor()
    seen = set()
    deadline = time.monotonic() + args.minutes * 60
    print("Station ready. Camera opens only while monitoring is requested in your app.")
    print("Event snapshots will be uploaded to your configured server. Ctrl+C stops the station.")
    try:
        while time.monotonic() < deadline:
            state = monitor.snapshot()
            response = api(
                url,
                "/v1/device/heartbeat",
                {
                    "capture": state["status"]
                    if state["status"] in ("starting", "running", "stopped", "error")
                    else "ready"
                },
                token,
            )
            if not response["armed"]:
                monitor.stop()
            elif state["status"] in ("idle", "stopped") and deadline - time.monotonic() >= 1:
                monitor.start(
                    args.camera,
                    profile,
                    minutes=max(1, min(10, (deadline - time.monotonic()) / 60)),
                )
            elif state["status"] == "error":
                raise RuntimeError(
                    "Camera stopped with an error; inspect the local session journal"
                )
            elif response["armed"]:
                for event in state["events"]:
                    key = Path(state["output"]).name + ":" + event["id"]
                    if key in seen:
                        continue
                    # Existing local monitor already validates and writes this JPEG.
                    import cv2

                    image = cv2.imread(str(Path(state["output"]) / event["image"]))
                    if image is None:
                        continue
                    scale = min(1, 640 / max(image.shape[:2]))
                    image = cv2.resize(
                        image, (int(image.shape[1] * scale), int(image.shape[0] * scale))
                    )
                    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 70])
                    if not ok or len(data) > 220000:
                        continue
                    api(
                        url,
                        "/v1/device/events",
                        {
                            "source_id": key,
                            "kind": event["kind"],
                            "observed_at": event.get("observed_at", time.time()),
                            "origin": "live",
                            "snapshot": base64.b64encode(data).decode(),
                        },
                        token,
                    )
                    seen.add(key)
            time.sleep(2)
    finally:
        monitor.stop()
        try:
            api(url, "/v1/device/heartbeat", {"capture": "stopped"}, token)
        except (HTTPError, URLError, OSError):
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Station stopped.")
    except (HTTPError, URLError, ValueError, OSError, RuntimeError):
        raise SystemExit(
            "Station stopped. Check server connection, pairing, profile and local camera logs. No further events will be sent."
        ) from None
