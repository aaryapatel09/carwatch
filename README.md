# Carwatch — local activity lab

A working research prototype for reviewing activity around parked cars. It processes recorded video locally and supports a complete recording → pose tracking → activity cues → evidence clips → manual labels → custom sequence-model training → held-out evaluation workflow.

## Start

```sh
cd /Users/aaryapatel/carwatch
.venv/bin/streamlit run app.py --server.port 8517
```

Open http://127.0.0.1:8517. Python 3.11, dependencies from requirements.lock.txt, public YOLO11 person/pose weights, and ffmpeg are installed on this machine. A fresh installation needs Python 3.11+, `pip install -r requirements.lock.txt`, and ffmpeg on PATH. First inference can download model weights. The server binds only to localhost.

## What works

- Saved per-camera calibration and thresholds, without assuming a particular car model.
- Local video upload (up to 300 MB), 4 Hz sampled person/pose tracking, and a configurable processing cap up to 300 seconds.
- Presence, repeated entry, and estimated-wrist-in-region cues. Wrist visibility is required; image overlap does **not** confirm physical contact.
- Timestamped evidence images and silent H.264 event clips with pre/post context.
- Persistent recording history, human event review, annotated per-track training clips, and activity labels.
- Nonoverlapping 8-second training windows with explicit missing-detection masks.
- A custom PyTorch GRU with train-only feature normalization, validation-selected checkpoints, and separately reported test confusion matrices.
- Dataset split checks by recording group and exact video hash; duplicate-window and synthetic-data checks.
- Optional real experimental model scoring on new video windows. Scores do not automatically trigger alerts.
- Opt-in local USB/webcam monitor with explicit Start/Stop, a 1–10 minute session limit, local event snapshots, and delayed-frame status. Hardware capture has not been exercised on this machine.
- Local JSON/ZIP export, model cards, dataset fingerprints, camera settings, recording deletion, and model deletion.
- Batch processing of multiple camera recordings under one session group. Views are processed independently, without cross-camera identity matching or synchronization.

## Try the app

1. **Overview:** see saved recordings and review progress.
2. **Analyze video:** choose or save a camera profile; mark ground and handle image regions. Upload permissioned footage. Use one recording group for all cameras and clips from a filming session. Assign train/val/test before analysis. Green is the ground zone; amber is the handle region.
3. **Review & label:** inspect event clips and save event feedback. In Training windows, prepare an annotated clip, check the selected track, and choose a human activity label. Event feedback and training labels are separate.
4. **Train models:** review label counts and dataset checks. Train on actual reviewed recordings when ready. Real models appear in the model registry and the analysis selector.
5. **Live camera:** explicitly start a local camera only when ready. It saves event snapshots and logs, not full video or audio. Stop manually or use the session time limit. Closing the tab does not stop an active session.
6. **Settings:** manage local data. Deleting a recording does not untrain an existing model; delete/retrain affected models separately.

The included example recording is a replay of a bundled Ultralytics example photo, explicitly marked `sample`. It verifies the CV pipeline but is **not** car-security validation and is excluded from real-data training.

## What was actually trained

`runtime/models/synthetic-demo/` contains a custom GRU trained for 50 epochs on 192 generated feature sequences (4 classes × 16 examples × 3 splits). It learns generated movement patterns. Its reported scores are only on held-out generated patterns, not on real footage. The app refuses to apply this model to real recordings.

The person/pose detector is pretrained YOLO11n, not custom-trained by this project. **No custom model has yet been trained on real car-door activity.** Real training requires footage and reviewed labels. The minimum of two examples per class per split is an execution sanity check, not sufficient data for reliable deployment.

Classes: ordinary_activity, lingering, repeated_approach, hand_near_zone. They describe visible activity, not criminal intent, gender, identity, weapons, or threat level. Use Exclude for tracking failures, occlusion, ambiguous mixtures, or clips that cannot be confidently labeled. Human definitions of ordinary activity and lingering can overlap; create a consistent annotation protocol before collecting a large dataset.

## Training and batch CLI

```sh
.venv/bin/python demo.py
.venv/bin/python cli.py export reviewed-windows.json
.venv/bin/python cli.py train --epochs 60 --name experiment-01
.venv/bin/python cli.py batch data/batch.example.json
```

The batch manifest is an example: replace file paths and calibration with actual recordings. Keep all views of the same session in the same split. Keep actors, cars and locations separate across splits where practical. Exact hashes cannot detect differently cropped/reencoded versions of the same recording; correct session grouping remains necessary.

The older `train_behavior.py` CSV logistic-regression baseline remains available for comparison, but is not used by the dashboard. Its model is not loaded by the new pipeline.

## Validation

```sh
.venv/bin/python -m pytest -q
.venv/bin/python smoke_video.py
.venv/bin/python scripts/verify_flow.py
```

The integration script runs actual pose CV on a bundled still-image replay, verifies event clips, annotated review clips, persistence and dataset export, then restores its training label to unreviewed. It leaves a clearly named sample run to inspect. It is not a motion, car-contact, night-vision or field benchmark.

Before field use, evaluate full independent recordings, including ordinary negative footage, owners, neighboring-car loading, children, carts, pets, rain, shadows, low light and occlusion. Measure false alerts per hour, event recall, alert delay, tracking continuity and blind spots. Window classification accuracy alone cannot establish these. Reusing the test split for model selection invalidates its held-out role; reserve fresh sessions for later experiments.

## Data and privacy

Everything is under `runtime/`, ignored by Git: uploaded source video, event/track clips, features, human labels, models, and manifests. Source audio is not included in derived clips but remains in the saved original. No face recognition, reidentification across cameras, external video upload, remote notification service, or weapon actuation is connected. Model downloads are inbound only. Local files are not encrypted by this app; use device storage protection as appropriate. Data is retained until deletion in Settings.

## Remaining product work

This is a local research app with recorded-video analysis and an untested-on-hardware local camera monitor. Universal mounting, automotive power/temperature qualification, robust multi-camera live ingestion, authenticated remote access, LTE/offline behavior, phone push delivery, production retention/access controls, real behavior training, and field evaluation are not complete. No absence of alerts should be displayed as a guarantee of safety.

## Sources and licensing

- Ultralytics pose API and keypoint mapping: https://docs.ultralytics.com/tasks/pose/
- Tracking API: https://docs.ultralytics.com/modes/track/
- PyTorch GRU: https://docs.pytorch.org/docs/stable/generated/torch.nn.GRU.html
- Ultralytics code and pretrained models have AGPL-3.0 / enterprise licensing conditions: https://www.ultralytics.com/license

The bundled sample photo comes from the installed Ultralytics package and is used solely for a local integration check. Review code, model, example-media and training-data licenses before distributing a product. No proprietary-commercial readiness is asserted.
