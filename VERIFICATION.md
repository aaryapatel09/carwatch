# Verification — 2026-10-26

Story: load a recording, calibrate its view, run pose tracking, review saved evidence, label track windows, then train/evaluate a custom activity classifier. Local camera mode is a separately opt-in path.

## Current evidence

- **72 tests passed** in a separate clean Python 3.11 environment installed from `requirements-dev.txt` and the checked-in runtime lock. `pip check` found no broken requirements.
- Selected core-module statement/branch coverage is **88%**. This includes rule logic, feature extraction, storage, training, media, vision and live-control modules; it is not whole-product accuracy or safety coverage.
- All six interface sections render in an isolated Streamlit AppTest process. Label saves persist; sample footage is excluded from real training; Start camera is disabled without explicit consent.
- Lint, formatting and `git diff --check` pass. Workflow definitions pass official **actionlint v1.7.12** after fixing a disallowed expression context.
- `pip-audit` queried **68 pinned runtime packages** and reported **zero known vulnerabilities** at check time. This is not a guarantee of absence of vulnerabilities; development/system tools are outside that audit.
- A Linux/Python 3.11 wheel-resolution dry run succeeded. This is not a Linux runtime test; platform-marker behavior and hosted CI still require validation on the runner.
- Actual YOLO11n-pose inference processed 40 samples from a 10-second replay of a bundled photo, producing 6 events and 8 windows. Event clips, a selected-track overlay clip, persisted human review and dataset export passed. These counts concern the fixture only.
- A 12-frame blank video passed actual detector/tracker processing and JSON export.
- A custom 32-unit GRU trained for 50 epochs on 192 generated sequences. Validation-based checkpoint selection, held-out generated-pattern evaluation and prediction completed. The synthetic model cannot score real footage.

## Regressions fixed

- A blocked camera driver can no longer indefinitely hold the UI's Stop operation: capture runs in a separate process with a parent watchdog and force-stop fallback. Tests kill and restart an intentionally hung fake worker without opening a camera.
- Camera unavailable/disconnect paths preserve an error state and release the device. Preview queue size and frame dimensions are bounded.
- Repeated Stop calls are harmless. Stop and the watchdog reconcile the final saved session before reporting completion, preserving events and disconnect errors even if the last queue message was dropped.
- Invalid detections break continuous-presence evidence instead of bridging a detection gap.
- Model load failures occur before opening video; detector and callback errors release video resources.
- Failed screenshot writes cannot report successful evidence capture. Failed ffmpeg exports preserve any previous clip and clean partial files.
- Independent labels from concurrent browser sessions are merged under a file lock rather than replacing a stale whole report.
- Duplicate analyses of the same recording cannot inflate a training dataset by changing track IDs.
- Custom models validate feature/label order, normalization, and weight checksum. Each update publishes uniquely named artifacts before atomically switching the model card; fault injection at all three publication steps confirms the old model remains usable after failure. Previous fixed-filename checkpoints remain readable.
- Recording fingerprints are calculated from the saved copy, so a source change during import cannot leave a fingerprint describing different bytes.
- Tests and optional CV integration use isolated data directories. No user camera was activated.

## Outstanding evidence

No GitHub remote or hosted workflow run exists. No physical camera acquisition, real car-door training data, independent behavior benchmark, field false-alert rate, phone delivery, LTE integration, universal mounting, or power/heat qualification has been verified. Those gaps prevent a claim of complete product readiness or “100% perfection.”

See [test map](docs/TESTING.md) and [release-readiness audit](docs/READINESS.md). Local generated evidence lives under the configured data directory and is excluded from Git.
