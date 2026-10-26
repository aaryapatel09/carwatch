import math
import subprocess
import time
from pathlib import Path

import cv2

from config import CameraConfig, finite_number
from engine import ActivityEngine
from features import RATE, make_windows, vector
from media import extract_track_clip
from store import write_json


def analyze(
    source,
    output,
    zone=None,
    dwell=10,
    progress=None,
    weights=None,
    config=None,
    max_seconds=300,
    model_path=None,
):
    """One fixed camera recording. Actual timestamps are derived from source FPS."""
    from ultralytics import YOLO

    config = config or CameraConfig(zone=zone or (0.3, 0.2, 0.7, 0.95), dwell=dwell, pose=False)
    config.validate()
    if not finite_number(max_seconds) or not 0 < max_seconds <= 300:
        raise ValueError("Analysis duration must be between 0 and 300 seconds")
    if model_path and not config.pose:
        raise ValueError(
            "Custom sequence scoring requires pose tracking to preserve wrist features"
        )
    predictor = None
    if model_path:
        from temporal import Predictor

        predictor = Predictor(model_path)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    total = int(frame_count) if math.isfinite(frame_count) and frame_count > 0 else 0
    if not cap.isOpened() or not math.isfinite(fps) or not (0 < fps <= 240):
        cap.release()
        raise ValueError("Cannot decode video or determine a supported frame rate")
    weights = weights or ("yolo11n-pose.pt" if config.pose else "yolo11n.pt")
    engine = ActivityEngine(
        zone=config.zone,
        dwell=config.dwell,
        repeat=config.repeat,
        window=config.window,
        hand_zone=config.hand_zone if config.pose else None,
        hand_seconds=config.hand_seconds,
    )
    events = []
    samples = []
    previous = {}
    n = 0
    sampled = 0
    next_sample = 0.0
    warnings = []
    started = time.monotonic()
    try:
        model = YOLO(
            str(Path(__file__).parent / weights) if not Path(weights).is_absolute() else weights
        )
        while n / fps < max_seconds:
            ok, frame = cap.read()
            if not ok:
                break
            t = n / fps
            n += 1
            if t + 1e-6 < next_sample:
                continue
            next_sample = (math.floor(t * RATE + 1e-6) + 1) / RATE
            h, w = frame.shape[:2]
            result = model.track(
                frame,
                persist=True,
                classes=[0],
                conf=config.confidence,
                tracker="bytetrack.yaml",
                verbose=False,
                imgsz=640,
            )[0]
            people = []
            features = []
            if result.boxes.id is not None:
                boxes = result.boxes.xyxy.cpu().tolist()
                ids = result.boxes.id.cpu().tolist()
                poses = (
                    result.keypoints.data.cpu().tolist() if result.keypoints is not None else None
                )
                for idx, (tid, b) in enumerate(zip(ids, boxes)):
                    tid = int(tid)
                    box = [b[0] / w, b[1] / h, b[2] / w, b[3] / h]
                    wrists = []
                    if poses:
                        for k in (9, 10):
                            x, y, confidence = poses[idx][k]
                            if confidence >= 0.5 and 0 < x < w and 0 < y < h:
                                wrists.append((x / w, y / h))
                    people.append((tid, box, wrists))
                    prior = previous.get(tid)
                    last = prior[1] if prior and 0 < t - prior[0] <= 0.6 else None
                    dt = t - prior[0] if last else 1 / RATE
                    values = vector(box, wrists, config.zone, config.hand_zone, last, dt)
                    features.append(dict(track=tid, features=values))
                    previous[tid] = (t, ((box[0] + box[2]) / 2, box[3]))
            samples.append(dict(time=t, people=features))
            new = engine.update(t, people)
            annotated = result.plot()
            for rect, color in [
                (config.zone, (125, 225, 165)),
                (config.hand_zone, (80, 180, 250)),
            ]:
                a, b, c, d = rect
                cv2.rectangle(
                    annotated,
                    (int(a * w), int(b * h)),
                    (int(c * w), int(d * h)),
                    color,
                    2,
                )
            if sampled == 0:
                if not cv2.imwrite(str(output / "preview.jpg"), annotated):
                    raise OSError("Could not save preview image")
            for event in new:
                if len(events) >= 100:
                    if "Event limit reached (100)" not in warnings:
                        warnings.append("Event limit reached (100)")
                    break
                event.update(id=f"e{len(events):04d}", image=f"event-{len(events):04d}.jpg")
                if not cv2.imwrite(str(output / event["image"]), annotated):
                    raise OSError("Could not save event evidence image")
                events.append(event)
            sampled += 1
            if progress and sampled % 4 == 0:
                progress(min(n / max(1, min(total, max_seconds * fps)), 0.99), annotated)
        if not sampled:
            raise ValueError("Video contained no decodable frames")
        duration = n / fps
        if n < total:
            warnings.append(
                f"Processed first {duration:.1f}s only; source reports {total / fps:.1f}s"
            )
        windows = make_windows(samples)
        for window in windows:
            window["end"] = min(window["end"], duration)
            if predictor:
                window["prediction"] = predictor.predict(window["sequence"])
        for event in events:
            event["clip"] = None
            try:
                name = event["id"] + ".mp4"
                extract_track_clip(
                    source,
                    output / name,
                    max(0, event["time"] - 3),
                    min(duration, event["time"] + 3),
                    samples,
                    event["track"],
                )
                event["clip"] = name
            except (
                ValueError,
                RuntimeError,
                TimeoutError,
                subprocess.TimeoutExpired,
            ) as exc:
                warnings.append(str(exc))
        write_json(output / "windows.json", windows)
        write_json(output / "samples.json", samples)
        report = dict(
            status="processed",
            frames=n,
            sampled_frames=sampled,
            duration_seconds=duration,
            processing_seconds=round(time.monotonic() - started, 2),
            zone=config.zone,
            config=config.to_dict(),
            events=events,
            model=weights,
            behavior_model=str(model_path) if model_path else "deterministic zone and wrist rules",
            warnings=sorted(set(warnings)),
            limitations=[
                "Tracking IDs may switch",
                "Image zones do not establish physical contact",
                "No intent, identity or threat inference",
            ],
        )
        write_json(output / "report.json", report)
        return report
    finally:
        cap.release()
