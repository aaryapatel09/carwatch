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
| Interface | All sections through Streamlit AppTest in a separate process and data directory; label persistence; camera/training gates | Every browser or screen size |
| Repository | Lint/format, dependency audit, tracked-file artifact/credential checks, actionlint | Hosted CI execution or absence of every vulnerability |

Run `python scripts/verify_flow.py` for actual pretrained pose inference on a bundled still-image replay. It downloads official weights on first use, uses a temporary recording directory, and saves a small verification report under the configured data directory. `--keep-sample` retains the synthetic replay for manual inspection. Do not confuse that still-image test with a motion or car-door benchmark.

Run `python demo.py` to train the synthetic-only demonstration model. It is deliberately prevented from scoring real videos.

A code-coverage percentage is a guide to unexercised paths, not a measure of correctness or safety. Tests using fakes and generated data verify software contracts, not the quality of real observations. See [release readiness](READINESS.md) for remaining evidence.
