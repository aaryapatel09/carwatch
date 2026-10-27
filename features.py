"""Fixed-duration pose/track sequences shared by extraction, training and inference."""

import math

import numpy as np

from engine import inside

SCHEMA = "carwatch-sequence-v1"
RATE = 4
STEPS = 32
MIN_OBSERVED_FRAMES = 4
SECONDS = STEPS / RATE
NAMES = [
    "visible",
    "in_zone",
    "foot_x",
    "foot_y",
    "wrist_visible",
    "wrist_in_zone",
    "box_width",
    "box_height",
    "velocity_x",
    "velocity_y",
]
LABELS = ["ordinary_activity", "lingering", "repeated_approach", "hand_near_zone"]


def vector(box, wrists, zone, hand_zone, previous=None, dt=0.25):
    x1, y1, x2, y2 = box
    x, y = (x1 + x2) / 2, y2
    dx, dy = (0.0, 0.0) if previous is None else ((x - previous[0]) / dt, (y - previous[1]) / dt)
    return [
        1.0,
        float(inside((x, y), zone)),
        x,
        y,
        float(bool(wrists)),
        float(any(inside(p, hand_zone) for p in wrists)),
        x2 - x1,
        y2 - y1,
        max(-4.0, min(4.0, dx)),
        max(-4.0, min(4.0, dy)),
    ]


def make_windows(samples):
    """Nonoverlapping 8 s windows; absent detections remain explicitly zero/masked."""
    buckets = {}
    for sample in samples:
        index = int(math.floor(sample["time"] * RATE + 1e-4))
        block, slot = divmod(index, STEPS)
        for person in sample["people"]:
            key = (int(person["track"]), block)
            arr = buckets.setdefault(key, np.zeros((STEPS, len(NAMES)), dtype=np.float32))
            arr[slot] = person["features"]
    result = []
    for (track, block), arr in sorted(buckets.items()):
        if arr[:, 0].sum() < MIN_OBSERVED_FRAMES:
            continue
        result.append(
            dict(
                id=f"t{track}-w{block}",
                track=track,
                start=block * SECONDS,
                end=(block + 1) * SECONDS,
                schema=SCHEMA,
                sequence=arr.tolist(),
                label="unreviewed",
                label_source=None,
            )
        )
    return result


def validate_sequence(sequence):
    a = np.asarray(sequence, dtype=np.float32)
    if a.shape != (STEPS, len(NAMES)) or not np.isfinite(a).all():
        raise ValueError(f"Sequences must be finite {STEPS} × {len(NAMES)} arrays.")
    if not np.isin(a[:, [0, 1, 4, 5]], [0, 1]).all():
        raise ValueError("Visibility and zone flags must be binary")
    if np.any(a[a[:, 0] == 0] != 0):
        raise ValueError("Missing detections must be zero-filled")
    if np.any(a[:, 5] > a[:, 4]):
        raise ValueError("A wrist cannot be in a zone unless it is visible")
    if np.any(a[:, 2:8] < 0) or np.any(a[:, 2:8] > 1) or np.any(abs(a[:, 8:]) > 4):
        raise ValueError("Feature values are outside their normalized ranges")
    return a
