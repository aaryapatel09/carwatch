# Verification — 2026-10-26

Story: an operator loads a recording, calibrates a view, runs pose tracking, reviews saved evidence, labels track windows, and trains/evaluates a custom activity classifier.

## Confirmed

- 21 tests cover event timing, missing observations, entry debounce, wrist visibility, invalid input, feature windows, dataset leakage, duplicate windows, data provenance, checkpoint loading, synthetic/real model separation, review persistence, deletion, and camera opt-in behavior.
- All six app sections render through Streamlit AppTest.
- UI label save persists across reruns; real-data training stays disabled with no eligible labels.
- Actual YOLO11n-pose inference processed 40 sampled frames from a 10-second replay of a bundled photo. It produced 6 events and 8 windows.
- Event clips and a selected-track overlay clip encoded, decoded, and were saved successfully.
- Human review reached dataset export, then was reset to unreviewed. The demonstration recording remains marked sample.
- A custom 32-unit GRU trained for 50 epochs on 192 generated sequences. Checkpoints, validation-based selection, held-out generated-pattern evaluation and inference completed.
- Browser review showed the running dashboard and saved event video. The old server initially retained a stale import; restarting cleared it.

## Not established

- No real car-door behavior model has been trained or validated.
- No real motion/interaction, night, rain, crowd, camera-placement or physical-contact benchmark was run.
- No live camera was activated. The local camera screen and validation paths were tested without accessing hardware; device acquisition and capture are unverified.
- No phone push, remote authentication, LTE, multi-camera live synchronization, field false-alert rate or safety effectiveness was tested or implemented.
- No software cue should be read as evidence of criminal intent or a guarantee of safety.

Machine-readable integration evidence: runtime/verification.json. Synthetic model card: runtime/models/synthetic-demo/model.json. Both are local, ignored artifacts.
