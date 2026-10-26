# Contributing

Use Python 3.11 and install `requirements-dev.txt` into an isolated virtual environment. Install ffmpeg separately. Run `ruff check .`, `ruff format --check .`, `python -m pytest`, and `python scripts/check_repository.py` before opening a pull request.

Keep changes focused and add regression tests for behavior changes. Tests must not activate a real camera, send notifications, or require private videos. Use isolated temporary data directories. Mark any model/download integration tests explicitly.

Do not commit recordings, snapshots, credentials, model weights, generated model cards, or local reports. Avoid names, precise locations, faces, license plates and other personal data in issue attachments. Describe reproducible steps with synthetic fixtures whenever possible.

Describe activity, not inferred intention. A wrist overlapping an image region does not prove contact. Do not present generated-pattern accuracy as real-world performance or describe an absence of events as a safety guarantee.

The main CI suite is independent of model downloads. The manual CV integration workflow downloads official public model weights. Both workflows run without repository secrets and use official PyTorch CPU builds constrained by `requirements-cpu.txt`; keep their base versions aligned with `requirements.lock.txt`. Running them on GitHub is required before calling a particular hosted commit green.
