# Verification — 2026-10-26

Story: load a recording, calibrate its view, run pose tracking, review saved evidence, label track windows, then train/evaluate a custom activity classifier. Local camera mode is a separately opt-in path.

## Current evidence

- **112 tests passed** locally after adding opt-in notification delivery and its failure-path checks. `pip check` found no broken requirements in the installed environment.
- Selected-module statement/branch coverage is **87%**. This includes rule logic, feature extraction, storage, training, media, vision, live control, notification delivery and the public-video probe; it is not whole-product accuracy or safety coverage.
- All six interface sections render in an isolated Streamlit AppTest process. Label saves persist; sample footage is excluded from real training; Start camera is disabled without explicit consent.
- Lint, formatting and `git diff --check` pass. Workflow definitions pass official **actionlint v1.7.12** after fixing a disallowed expression context.
- `pip-audit` queried **68 pinned runtime packages** and reported **zero known vulnerabilities** at check time. This is not a guarantee of absence of vulnerabilities; development/system tools are outside that audit.
- Linux/Python 3.11 hosted execution passed for commit `ba2e8bb`: 86 tests, dependency audit, actual CV integration and both nano-model public-video configurations. Later changes require their own hosted run.
- Actual YOLO11n-pose inference processed 40 samples from a 10-second replay of a bundled photo, producing 6 events and 8 windows. Event clips, a selected-track overlay clip, persisted human review and dataset export passed. These counts concern the fixture only.
- A 12-frame blank video passed actual detector/tracker processing and JSON export.
- A custom 32-unit GRU trained for 50 epochs on 192 generated sequences. Validation-based checkpoint selection, held-out generated-pattern evaluation and prediction completed. The synthetic model cannot score real footage.
- Real MEVA parking-lot footage was analyzed with its supplied actor annotations: the full-image setup matched 0/17 annotated samples; an explicitly focused region selected during development matched 7/17 at IoU ≥ 0.5. Remaining misses are recorded in the [public-video report](docs/PUBLIC-VIDEO.md); this is not independent field validation.
- The larger YOLO11s-pose model matched 9/17 on the same focused development region. It took 54.84 seconds versus the earlier nano run's 26.24 seconds on this computer. The default remains unchanged; this comparison is not independent accuracy validation.
- Commit `0e0aeb1` passed [hosted CV integration](https://github.com/aaryapatel09/carwatch/actions/runs/40425565468), reproducing 0/17, 7/17 and 9/17 for all three configurations. Its separate test runner was still installing media dependencies when this evidence was recorded.
- The optional notification dispatcher completed a real HTTPS request to a local fixture server using test credentials, verified the acknowledgement and redacted journal, and rejected the fixture's certificate without its explicit test CA. No trust-store changes, external ntfy calls, camera activation or phone messages occurred.

## Regressions fixed

- A blocked camera driver can no longer indefinitely hold the UI's Stop operation: capture runs in a separate process with a parent watchdog and force-stop fallback. Tests kill and restart an intentionally hung fake worker without opening a camera.
- Camera unavailable/disconnect paths preserve an error state and release the device. Preview queue size and frame dimensions are bounded.
- Repeated Stop calls are harmless. Stop and the watchdog reconcile the final saved session before reporting completion, preserving events and disconnect errors even if the last queue message was dropped.
- Invalid detections break continuous-presence evidence instead of bridging a detection gap.
- Direct sequence prediction rejects fewer than four observed frames, matching extraction and training's existing minimum. Before the fix, an entirely empty sequence could return a confident activity label. Boundary checks cover zero, one, three and four observed frames. Four observations remain an execution floor, not sufficient evidence of reliability.
- Review charts include track visibility, so missing detections can be distinguished from observed activity outside the zone. The isolated UI test verifies the accompanying explanation.
- Model load failures occur before opening video; detector and callback errors release video resources.
- Failed screenshot writes cannot report successful evidence capture. Failed ffmpeg exports preserve any previous clip and clean partial files.
- Independent labels from concurrent browser sessions are merged under a file lock rather than replacing a stale whole report.
- Analysis uses an OS-held run lock. A killed analysis process releases ownership; interrupted runs can be identified and removed. Deletion cannot race a label save or recreate deleted data. Regression tests terminate a real test subprocess to verify recovery.
- Duplicate analyses of the same recording cannot inflate a training dataset by changing track IDs.
- Custom models validate feature/label order, normalization, and weight checksum. Each update publishes uniquely named artifacts before atomically switching the model card; fault injection at all three publication steps confirms the old model remains usable after failure. Previous fixed-filename checkpoints remain readable.
- Recording fingerprints are calculated from the saved copy, so a source change during import cannot leave a fingerprint describing different bytes.
- Video and live capture share one detection-region transform. Tests verify person boxes, wrists and annotated previews return to full-image coordinates, and legacy profiles retain full-frame defaults.
- Tests and optional CV integration use isolated data directories. No user camera was activated.
- Notification tests cover absent configuration, opt-in gating, durable evidence before enqueue, protected payloads, HTTP rejection/redirect/rate-limit behavior, retries/expiry/cooldown/deduplication, cancellation on Stop or worker exit, and an interrupted send remaining unconfirmed. Notifications remain off by default. These tests do not establish real mobile receipt.

## Outstanding evidence

The private [GitHub repository](https://github.com/aaryapatel09/carwatch) exists. The first hosted test run exhausted the runner's disk while installing CUDA dependencies; the workflows now select the pinned official CPU builds. Commit `ba2e8bb` passed [86 tests, lint and dependency checks on Linux](https://github.com/aaryapatel09/carwatch/actions/runs/40424356587) and [actual CV integration with the public-video probe](https://github.com/aaryapatel09/carwatch/actions/runs/40424356486). Check the [repository workflow](https://github.com/aaryapatel09/carwatch/actions/workflows/ci.yml) and [CV integration workflow](https://github.com/aaryapatel09/carwatch/actions/workflows/cv-integration.yml) for later commits.

No physical camera acquisition, real car-door training data, independent behavior benchmark, field false-alert rate, phone delivery, LTE integration, universal mounting, or power/heat qualification has been verified. Those gaps prevent a claim of complete product readiness or “100% perfection.”

See [test map](docs/TESTING.md) and [release-readiness audit](docs/READINESS.md). Local generated evidence lives under the configured data directory and is excluded from Git.
