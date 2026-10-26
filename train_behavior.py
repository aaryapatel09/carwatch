"""Train a coarse activity baseline on reviewed track summaries, never intent."""

import argparse
import csv
import json
from pathlib import Path

FEATURES = ["dwell_seconds", "zone_entries", "observed_seconds"]


def train(csv_path, out):
    import joblib
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    rows = list(csv.DictReader(open(csv_path)))
    if not rows:
        raise ValueError("No labeled footage. Training requires real reviewed examples.")
    groups = {
        s: {r["session_id"] for r in rows if r["split"] == s} for s in ["train", "val", "test"]
    }
    if any(not g for g in groups.values()):
        raise ValueError("Need train, val and test recording sessions")
    if (
        groups["train"] & groups["val"]
        or groups["train"] & groups["test"]
        or groups["val"] & groups["test"]
    ):
        raise ValueError("Recording-session leakage between splits")
    if any(r["split"] not in groups for r in rows):
        raise ValueError("Unknown split")
    if any(r["label"] not in ["ordinary_activity", "review_activity"] for r in rows):
        raise ValueError("Unknown label")

    def split(name):
        rr = [r for r in rows if r["split"] == name]
        X = np.array([[float(r[k]) for k in FEATURES] for r in rr])
        y = np.array([r["label"] == "review_activity" for r in rr], dtype=int)
        if not np.isfinite(X).all() or (X < 0).any():
            raise ValueError("Invalid numeric features")
        if len(set(y)) < 2:
            raise ValueError("Each split must contain both classes")
        return X, y

    X, y = split("train")
    vx, vy = split("val")
    tx, ty = split("test")
    model = make_pipeline(
        StandardScaler(), LogisticRegression(class_weight="balanced", random_state=42)
    )
    model.fit(X, y)
    report = {
        "status": "experimental baseline; not deployed",
        "features": FEATURES,
        "rows": len(rows),
        "sessions": {k: len(v) for k, v in groups.items()},
    }
    for name, x, y in [("val", vx, vy), ("test", tx, ty)]:
        pred = model.predict(x)
        report[name] = {
            "classification": classification_report(y, pred, output_dict=True, zero_division=0),
            "confusion_matrix": confusion_matrix(y, pred).tolist(),
        }
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out / "behavior.joblib")
    (out / "metrics.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--out", default="runs/behavior")
    a = p.parse_args()
    print(json.dumps(train(a.csv, a.out), indent=2))
