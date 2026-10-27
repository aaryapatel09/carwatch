# Test map

Run `python -m pytest --cov --cov-report=term-missing` after installing `requirements-dev.txt`. No test activates a real camera or sends an external message.

| Area | Automated evidence | What it does not prove |
|---|---|---|
| Activity rules | Missing/invalid frames, entry debounce, continuous dwell, wrist visibility, timestamp and configuration validation | Real-world event accuracy |
| Vision pipeline | Fake detector with real frame arrays; decoding/error/resource handling; evidence export | Learned detector quality |
| Detection region | Pixel bounds, box/wrist coordinate reconstruction, preview composition, legacy full-frame defaults | Visibility of people outside the chosen region |
| Public-video measurement | One-to-one matching, incomplete-label handling, timestamp checks, bounded/explicit download and cached-file integrity | Full-scene precision, field accuracy, or independent generalization |
| Codecs | Real local OpenCV + ffmpeg encoding/decoding; selected-track overlay; silent output | All camera codecs or corrupted-video security |
| Model training | Small generated fixtures, split/hash leakage checks, duplicate-analysis rejection, checksum/schema checks, checkpoint round-trip, publication failure at each commit step, old-checkpoint compatibility | Training-data quality, field generalization, or power-loss durability |
| Local storage | Atomic JSON writes, saved-copy fingerprints, failed-copy cleanup, concurrent independent reviews, sample-data filtering, process-crash recovery, review/deletion exclusion | Multi-user access control |
| Live capture | Simulated device availability/disconnection, bounded queues, event persistence, actual kill/restart of a deliberately hung subprocess, repeat Stop, final-record reconciliation | Camera-driver/device interoperability |
| Notifications | Explicit configuration/opt-in, fixed payloads, authorization, TLS and acknowledgement checks, duplicate/cooldown suppression, bounded retries/expiry, stopping during a send, process-exit cancellation and credential redaction | External service permissions, physical-phone receipt or mobile background delivery |
| Interface | All sections through Streamlit AppTest in a separate process and data directory; label persistence; camera/training gates | Every browser or screen size |
| Repository | Lint/format, dependency audit, tracked-file artifact/credential checks, actionlint | Hosted CI execution or absence of every vulnerability |

Run `python scripts/verify_flow.py` for actual pretrained pose inference on a bundled still-image replay. It downloads official weights on first use, uses a temporary recording directory, and saves a small verification report under the configured data directory. `--keep-sample` retains the synthetic replay for manual inspection. Do not confuse that still-image test with a motion or car-door benchmark.

Run `python demo.py` to train the synthetic-only demonstration model. It is deliberately prevented from scoring real videos.

Run `python scripts/verify_alerts.py` for a real HTTPS round trip against an ephemeral loopback receiver with test credentials. It verifies dispatch, service acknowledgement, journal redaction and rejection of an untrusted certificate. OpenSSL must be available to create the temporary fixture certificate. The certificate is trusted only by this test client, never installed into the system trust store. No external notification is sent. The opt-in CV workflow also runs this check.

A code-coverage percentage is a guide to unexercised paths, not a measure of correctness or safety. Tests using fakes and generated data verify software contracts, not the quality of real observations. See [release readiness](READINESS.md) for remaining evidence.
