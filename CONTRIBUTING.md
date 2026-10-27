# Contributing

## Development setup

Use Python 3.11 and follow the [platform-specific setup](README.md#quick-start), including ffmpeg. Install development tools into the same isolated environment:

```sh
# macOS
python -m pip install -r requirements-dev.txt

# Linux CPU environment, after installing the CPU builds from the quick start
python -m pip install -r requirements-dev.txt -c requirements-cpu.txt
```

Before opening a pull request, run:

```sh
ruff check .
ruff format --check .
python -m pytest
python scripts/check_repository.py
```

## Proposing a change

For a bug, include the platform, Python version, reproduction steps, and expected versus observed behavior. For an experiment, explain the observation you want to measure and how you will evaluate it independently. The issue templates help capture both.

Fork the repository, make a focused branch, and open a pull request against `master`. Explain what changed and which checks you ran. See [the test map](docs/TESTING.md) for optional integration checks; these may download public weights or data. Contributions are made under the project's [AGPL-3.0-only license](LICENSE).

Keep changes focused and add regression tests for behavior changes. Tests must not activate a real camera, send notifications, or require private videos. Use isolated temporary data directories. Mark any model/download integration tests explicitly.

Do not commit recordings, snapshots, credentials, model weights, generated model cards, or local reports. Avoid names, precise locations, faces, license plates and other personal data in issue attachments. Describe reproducible steps with synthetic fixtures whenever possible.

Describe activity, not inferred intention. A wrist overlapping an image region does not prove contact. Do not present generated-pattern accuracy as real-world performance or describe an absence of events as a safety guarantee.

The main CI suite is independent of model downloads. The manual CV integration workflow downloads official public model weights. Both workflows run without repository secrets and use official PyTorch CPU builds constrained by `requirements-cpu.txt`; keep their base versions aligned with `requirements.lock.txt`. Running them on GitHub is required before calling a particular hosted commit green.
