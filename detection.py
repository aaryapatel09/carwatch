"""Shared local detection region with full-image coordinate reconstruction."""

import math

import cv2

from config import validate_zone


def crop_bounds(region, width, height):
    validate_zone(region)
    a, b, c, d = region
    bounds = (
        math.floor(a * width),
        math.floor(b * height),
        math.ceil(c * width),
        math.ceil(d * height),
    )
    if bounds[2] - bounds[0] < 2 or bounds[3] - bounds[1] < 2:
        raise ValueError("Detection region must be at least two pixels wide and high")
    return bounds


def track_frame(model, frame, config):
    h, w = frame.shape[:2]
    left, top, right, bottom = crop_bounds(config.detection_region, w, h)
    crop = frame[top:bottom, left:right].copy()
    ch, cw = crop.shape[:2]
    result = model.track(
        crop,
        persist=True,
        classes=[0],
        conf=config.confidence,
        tracker="bytetrack.yaml",
        verbose=False,
        imgsz=640,
    )[0]
    people = []
    if result.boxes.id is not None:
        poses = result.keypoints.data.cpu().tolist() if result.keypoints is not None else None
        for idx, (tid, box) in enumerate(
            zip(result.boxes.id.cpu().tolist(), result.boxes.xyxy.cpu().tolist())
        ):
            if not all(math.isfinite(v) for v in box):
                continue
            a, b, c, d = box
            if not (0 <= a < c <= cw and 0 <= b < d <= ch):
                continue
            mapped = [(a + left) / w, (b + top) / h, (c + left) / w, (d + top) / h]
            wrists = []
            if poses:
                for k in (9, 10):
                    x, y, confidence = poses[idx][k]
                    if confidence >= 0.5 and 0 < x < cw and 0 < y < ch:
                        wrists.append(((x + left) / w, (y + top) / h))
            people.append((int(tid), mapped, wrists))
    annotated = frame.copy()
    annotated[top:bottom, left:right] = result.plot()
    if (left, top, right, bottom) != (0, 0, w, h):
        cv2.rectangle(annotated, (left, top), (right - 1, bottom - 1), (255, 180, 100), 2)
        cv2.putText(
            annotated,
            "Detection region",
            (left + 4, top + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 180, 100),
            1,
        )
    return people, annotated
