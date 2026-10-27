"""Verify alert dispatch against a loopback HTTPS fixture, never a real service."""

import json
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alerts import AlertConfig, AlertDispatcher, publish
from store import read_json


def main():
    with tempfile.TemporaryDirectory(prefix="carwatch-alert-check-") as temp:
        root = Path(temp)
        certificate, key = root / "fixture.pem", root / "fixture.key"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(certificate),
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost",
            ],
            check=True,
            capture_output=True,
            timeout=20,
        )
        requests = []

        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                requests.append((self.path, body, self.headers.get("Authorization")))
                response = json.dumps(
                    dict(id="fixture-ack", event="message", topic="test-only")
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Receiver)
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(certificate, key)
        server.socket = server_context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = AlertConfig(
            f"https://localhost:{server.server_port}", "test-only", "fixture-local-token"
        )
        context = ssl.create_default_context(cafile=str(certificate))
        dispatcher = AlertDispatcher(
            config,
            root / "alerts.json",
            sender=lambda *args: publish(*args, context=context),
        )
        try:
            dispatcher.enqueue("test-only-event", "hand_near_zone")
            dispatcher.start()
            deadline = time.monotonic() + 5
            while dispatcher.snapshot().get("accepted") != 1 and time.monotonic() < deadline:
                time.sleep(0.05)
            assert dispatcher.snapshot() == {"accepted": 1}, dispatcher.snapshot()
            dispatcher.close()
            assert len(requests) == 1
            path, body, authorization = requests[0]
            assert path == "/test-only" and authorization == "Bearer fixture-local-token"
            assert b"Contact is unconfirmed" in body and b"Observed at" in body
            assert "fixture-local-token" not in (root / "alerts.json").read_text()
            assert read_json(root / "alerts.json")[0]["attempts"] == 1
            # The fixture certificate is trusted only through the explicit test CA.
            status, _ = publish(config, "lingering", time.time())
            assert status == "failed" and len(requests) == 1
            print(
                dict(
                    status="passed",
                    receiver="loopback HTTPS fixture",
                    checks=[
                        "explicit dispatch",
                        "TLS verification",
                        "bearer authorization",
                        "text-only cue",
                        "service acknowledgement",
                        "journal redaction",
                        "untrusted certificate rejected",
                    ],
                    limitation="No external service, physical camera, or phone receipt tested",
                )
            )
        finally:
            dispatcher.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    main()
