"""A bounded MEVA actor-visibility probe, not an activity/safety benchmark."""

import hashlib
import math
import urllib.request
import uuid
from pathlib import Path

import numpy as np
import yaml
from scipy.optimize import linear_sum_assignment

from config import CameraConfig
from store import ROOT, read_json, write_json

BASE = "https://mevadata-public-01.s3.amazonaws.com/"
STEM = "2018-03-12.10-00-02.10-05-02.school.G339"
VIDEO_KEY = f"drops-123-r13/2018-03-12/10/{STEM}.r13.avi"
VIDEO_HASH = "f76858fd66fd38500d7e7a716ee15662f557d0af54bd06489c6acd94d24ac020"
ATTRIBUTION = "Multiview Extended Video with Activities (MEVA), Kitware Inc. and IARPA"
LICENSE_URL = "https://mevadata.org/resources/MEVA-data-license.txt"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(key, directory, max_bytes, allow_download=False, expected_hash=None):
    """Download only a fixed fixture key supplied by this module, with a size cap."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / Path(key).name
    if not path.exists():
        if not allow_download:
            raise ValueError("Public fixture missing; use --download to fetch the licensed data")
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".download")
        try:
            with urllib.request.urlopen(BASE + key, timeout=45) as response:
                if int(response.headers.get("Content-Length", 0)) > max_bytes:
                    raise ValueError("Public fixture exceeds the download limit")
                count = 0
                with temporary.open("wb") as file:
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > max_bytes:
                            raise ValueError("Public fixture exceeds the download limit")
                        file.write(chunk)
            if expected_hash and sha256(temporary) != expected_hash:
                raise ValueError("Public fixture checksum changed; inspect the source before use")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    if path.stat().st_size > max_bytes or (expected_hash and sha256(path) != expected_hash):
        raise ValueError("Public fixture size or checksum mismatch")
    return path


def person_annotations(types_path, geometry_path, width, height, fps):
    """Use supplied frame indices; do not interpolate absent ground truth."""
    types = yaml.safe_load(Path(types_path).read_text())
    people = {
        r["types"]["id1"]
        for r in types
        if "types" in r and r["types"].get("cset3", {}).get("Person") == 1.0
    }
    frames = {}
    seen = set()
    for row in yaml.safe_load(Path(geometry_path).read_text()):
        g = row.get("geom")
        if not g or g["id1"] not in people:
            continue
        frame = g["ts0"]
        if type(frame) is not int or frame < 0 or abs(g["ts1"] - frame / fps) > 1 / fps:
            raise ValueError("Annotation frame/timestamp alignment mismatch")
        box = [float(v) for v in g["g0"].split()]
        if len(box) != 4 or not all(math.isfinite(v) for v in box):
            raise ValueError("Invalid annotation geometry")
        a, b, c, d = box
        if not (0 <= a < c <= width and 0 <= b < d <= height):
            raise ValueError("Annotation geometry does not fit this video")
        key = (frame, g["id1"])
        if key in seen:
            raise ValueError("Duplicate actor/frame annotation")
        seen.add(key)
        frames.setdefault(frame, []).append([a / width, b / height, c / width, d / height])
    if not frames:
        raise ValueError("No person ground truth found")
    return frames


def match_boxes(truth, predictions, threshold=0.5):
    """Maximum one-to-one match count, with IoU as a secondary preference."""
    if not truth or not predictions:
        return []
    overlaps = np.zeros((len(truth), len(predictions)))
    for i, (a, b, c, d) in enumerate(truth):
        for j, (e, f, g, h) in enumerate(predictions):
            intersection = max(0, min(c, g) - max(a, e)) * max(0, min(d, h) - max(b, f))
            union = (c - a) * (d - b) + (g - e) * (h - f) - intersection
            overlaps[i, j] = intersection / union if union > 0 else 0
    score = np.where(overlaps >= threshold, 1 + overlaps / (min(overlaps.shape) + 1), 0)
    rows, cols = linear_sum_assignment(score, maximize=True)
    return [(int(i), int(j)) for i, j in zip(rows, cols) if overlaps[i, j] >= threshold]


def measure_samples(samples, annotations, fps):
    observed = matched = wrists = frames = 0
    seen = set()
    for sample in samples:
        frame = round(sample["time"] * fps)
        if frame in seen:
            raise ValueError("Duplicate sampled frame")
        seen.add(frame)
        truth = annotations.get(frame, [])
        if not truth:
            continue
        frames += 1
        predicted = []
        for p in sample["people"]:
            v = p["features"]
            x, y, w, h = v[2], v[3], v[6], v[7]
            predicted.append([x - w / 2, y - h, x + w / 2, y])
        matches = match_boxes(truth, predicted)
        observed += len(truth)
        matched += len(matches)
        wrists += sum(sample["people"][j]["features"][4] == 1 for _, j in matches)
    if not observed:
        raise ValueError("No sampled frames overlap the supplied person annotations")
    return dict(
        annotated_sampled_frames=frames,
        annotated_person_samples=observed,
        matched_person_samples=matched,
        person_match_fraction=matched / observed,
        matched_samples_with_estimated_wrist=wrists,
        iou_threshold=0.5,
    )


def run_probe(allow_download=False, root=ROOT, focused=False):
    import cv2

    from vision import analyze

    directory = Path(root) / "public-data" / "meva"
    video = fetch(VIDEO_KEY, directory, 200_000_000, allow_download, VIDEO_HASH)
    annotations = {
        suffix: fetch(
            f"examples/annotations/2018-03-12/10/{STEM}.{suffix}.yml",
            directory,
            100_000,
            allow_download,
        )
        for suffix in ("activities", "types", "geom")
    }
    cap = cv2.VideoCapture(str(video))
    try:
        shape = (cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not cap.isOpened() or shape != (1920, 1080) or fps != 30:
            raise ValueError("Public video metadata changed; annotation alignment needs review")
    finally:
        cap.release()
    truth = person_annotations(annotations["types"], annotations["geom"], *shape, fps)
    out = directory / ("probe-" + uuid.uuid4().hex)
    config = CameraConfig(
        name="MEVA public car-door probe",
        zone=(0.12, 0.20, 0.26, 0.41),
        hand_zone=(0.15, 0.25, 0.18, 0.32),
        pose=True,
        detection_region=(190 / 1920, 180 / 1080, 540 / 1920, 490 / 1080)
        if focused
        else (0, 0, 1, 1),
    )
    report = analyze(video, out, config=config, max_seconds=106)
    measurement = measure_samples(read_json(out / "samples.json"), truth, fps)
    result = dict(
        status="measurement_complete",
        source_url=BASE + VIDEO_KEY,
        source_sha256=VIDEO_HASH,
        attribution=ATTRIBUTION,
        license="CC BY 4.0",
        license_url=LICENSE_URL,
        annotations_sha256={k: sha256(v) for k, v in annotations.items()},
        ground_truth="MEVA example Person boxes during annotated door opening/closing",
        sampling_hz=4,
        analyzed_seconds=report["duration_seconds"],
        detector="yolo11n-pose.pt",
        confidence=config.confidence,
        image_size=640,
        detection_region=config.detection_region,
        measurement=measurement,
        output_directory=str(out),
        modifications="Derived evidence clips are silent, scaled and annotated by Carwatch",
        limitations=[
            "One daytime camera and two short annotated interactions; no deployment generalization",
            "Only supplied actor/frame boxes are scored; absent annotations are not negatives",
            "Other detections are unscored; this does not measure precision or false alerts per hour",
            "Wrist visibility is a model output, without wrist ground truth",
            "No activity-class, physical-contact, danger, or intent accuracy measured",
            "This is development data: the focused region was chosen after viewing the full-frame failure",
            "No model weights were trained on these results",
        ],
    )
    write_json(out / "measurement.json", result)
    write_json(directory / "latest-measurement.json", result)
    return result
