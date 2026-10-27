"""Small custom GRU activity classifier, with provenance and grouped evaluation."""

import copy
import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

import numpy as np
import torch
from filelock import FileLock
from torch import nn

from config import finite_number
from features import LABELS, MIN_OBSERVED_FRAMES, NAMES, SCHEMA, validate_sequence
from store import write_json


class ActivityNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.gru = nn.GRU(len(NAMES), 32, batch_first=True)
        self.head = nn.Linear(32, len(LABELS))

    def forward(self, x):
        output, _ = self.gru(x)
        return self.head(output.mean(dim=1))


def validate_dataset(rows, allow_synthetic=False):
    if not rows:
        raise ValueError("No human-labeled clips yet. Review recordings first.")
    sessions = {}
    hashes = {}
    seen = set()
    video_runs = {}
    for row in rows:
        if row.get("schema") != SCHEMA:
            raise ValueError("Feature schema mismatch")
        sequence = validate_sequence(row["sequence"])
        if sequence[:, 0].sum() < MIN_OBSERVED_FRAMES:
            raise ValueError("Each window needs at least four observed frames")
        if row.get("label") not in LABELS:
            raise ValueError("Unsupported activity label")
        if row.get("split") not in ("train", "val", "test"):
            raise ValueError("Invalid dataset split")
        if not row.get("session_id") or not row.get("video_hash"):
            raise ValueError("Missing session or recording fingerprint")
        if not all(isinstance(row[k], str) for k in ("session_id", "video_hash")):
            raise ValueError("Session and recording fingerprints must be strings")
        if (
            type(row.get("track")) is not int
            or not all(finite_number(row.get(k)) for k in ("start", "end"))
            or not 0 <= row["start"] < row["end"] <= row["start"] + 8
        ):
            raise ValueError("Invalid track/window interval")
        if row.get("run_id"):
            old_run = video_runs.setdefault(row["video_hash"], row["run_id"])
            if old_run != row["run_id"]:
                raise ValueError("Duplicate recording analysis; label only one run for each video")
        if row.get("origin") != "real" and not allow_synthetic:
            raise ValueError("Real-data training excludes synthetic and example footage")
        if not allow_synthetic and row.get("label_source") != "human":
            raise ValueError("Real-data training requires human-reviewed labels")
        for table, key in [(sessions, row["session_id"]), (hashes, row["video_hash"])]:
            old = table.setdefault(key, row["split"])
            if old != row["split"]:
                raise ValueError("Recording/session leakage between dataset splits")
        key = (row["video_hash"], row["track"], row["start"])
        if key in seen:
            raise ValueError("Duplicate recording window; remove duplicate analysis labels")
        seen.add(key)
    counts = {
        split: {
            label: sum(r["split"] == split and r["label"] == label for r in rows)
            for label in LABELS
        }
        for split in ("train", "val", "test")
    }
    if any(n < 2 for c in counts.values() for n in c.values()):
        raise ValueError(
            "Need at least 2 reviewed clips of each of the 4 activities in each split (24 clips minimum). This is only a training floor, not sufficient validation."
        )
    return counts


def classification_metrics(y, pred):
    from sklearn.metrics import classification_report, confusion_matrix

    return dict(
        report=classification_report(
            y,
            pred,
            labels=list(range(len(LABELS))),
            target_names=LABELS,
            output_dict=True,
            zero_division=0,
        ),
        confusion_matrix=confusion_matrix(y, pred, labels=list(range(len(LABELS)))).tolist(),
    )


def fit(rows, out, epochs=60, allow_synthetic=False, progress=None):
    if type(epochs) is not int or not 1 <= epochs <= 300:
        raise ValueError("Epochs must be between 1 and 300")
    counts = validate_dataset(rows, allow_synthetic)
    torch.manual_seed(42)
    torch.set_num_threads(2)

    def split(name):
        data = [r for r in rows if r["split"] == name]
        return torch.tensor(
            np.array([r["sequence"] for r in data]), dtype=torch.float32
        ), torch.tensor([LABELS.index(r["label"]) for r in data])

    x, y = split("train")
    vx, vy = split("val")
    tx, ty = split("test")
    # Fit standardization on observed TRAIN frames only; keep missing rows zero.
    visible = x[:, :, 0] > 0
    mean = x[visible].mean(0)
    std = x[visible].std(0, unbiased=False).clamp(min=0.05)
    mean[0] = 0
    std[0] = 1

    def normalize(a):
        return ((a - mean) / std) * a[:, :, :1]

    x, vx, tx = normalize(x), normalize(vx), normalize(tx)
    model = ActivityNet()
    weights = 1 / torch.bincount(y, minlength=len(LABELS)).float()
    loss_fn = nn.CrossEntropyLoss(weight=weights / weights.mean())
    opt = torch.optim.AdamW(model.parameters(), lr=0.008, weight_decay=0.001)
    best = copy.deepcopy(model.state_dict())
    best_loss = float("inf")
    best_epoch = 0
    history = []
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(x))
        losses = []
        for idx in order.split(32):
            opt.zero_grad()
            loss = loss_fn(model(x[idx]), y[idx])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            losses.append(float(loss.detach()))
        model.eval()
        with torch.no_grad():
            val_loss = float(loss_fn(model(vx), vy))
        history.append(
            dict(epoch=epoch + 1, train_loss=sum(losses) / len(losses), val_loss=val_loss)
        )
        if val_loss < best_loss:
            best_loss = val_loss
            best = copy.deepcopy(model.state_dict())
            best_epoch = epoch + 1
        if progress:
            progress((epoch + 1) / epochs, history[-1])
    model.load_state_dict(best)
    model.eval()
    origin = "synthetic_demo" if any(r["origin"] != "real" for r in rows) else "real_experimental"
    report = dict(
        schema=SCHEMA,
        origin=origin,
        status="research only; not safety validated",
        labels=LABELS,
        features=NAMES,
        counts=counts,
        epochs=epochs,
        best_epoch=best_epoch,
        history=history,
        sessions={s: sorted({r["session_id"] for r in rows if r["split"] == s}) for s in counts},
        dataset_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        limitations=[
            "Window classification, not intent or confirmed contact",
            "Test clips must be from separate recording sessions",
            "No deployment false-alert rate measured",
        ],
    )
    with torch.no_grad():
        for name, a, b in [("val", vx, vy), ("test", tx, ty)]:
            logits = model(a)
            pred = logits.argmax(1)
            report[name] = classification_metrics(b.numpy(), pred.numpy())
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    # State dict only; inference uses weights_only to avoid arbitrary pickle objects.
    with tempfile.TemporaryDirectory(dir=out.parent, prefix=".model-") as tmp:
        staged = Path(tmp)
        generation = uuid.uuid4().hex
        report["weights_file"] = f"weights-{generation}.pt"
        report["manifest_file"] = f"dataset-{generation}.json"
        torch.save({"state_dict": best, "mean": mean, "std": std}, staged / report["weights_file"])
        report["weights_sha256"] = hashlib.sha256(
            (staged / report["weights_file"]).read_bytes()
        ).hexdigest()
        write_json(staged / "model.json", report)
        write_json(
            staged / report["manifest_file"],
            [{k: v for k, v in r.items() if k != "sequence"} for r in rows],
        )
        with FileLock(str(out.parent / (out.name + ".lock"))):
            published = []
            try:
                for name in (report["weights_file"], report["manifest_file"]):
                    os.replace(staged / name, out / name)
                    published.append(out / name)
                # Commit the complete generation with one atomic replacement. Never
                # overwrite artifacts referenced by the currently published card.
                os.replace(staged / "model.json", out / "model.json")
            except BaseException:
                for path in published:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass  # Unreferenced files cannot invalidate the old model.
                raise
    return report


class Predictor:
    def __init__(self, path, allow_demo=False):
        path = Path(path)
        with FileLock(str(path.parent / (path.name + ".lock"))):
            self.card = json.loads((path / "model.json").read_text())
            name = self.card.get("weights_file", "weights.pt")
            if (
                not isinstance(name, str)
                or Path(name).name != name
                or "\\" in name
                or not name.endswith(".pt")
            ):
                raise ValueError("Invalid checkpoint filename")
            weights_path = path / name
            if (
                self.card.get("weights_sha256")
                != hashlib.sha256(weights_path.read_bytes()).hexdigest()
            ):
                raise ValueError(
                    "Checkpoint integrity mismatch; retrain or restore the complete model"
                )
            weights = torch.load(weights_path, map_location="cpu", weights_only=True)
        if (
            self.card.get("schema") != SCHEMA
            or self.card.get("features") != NAMES
            or self.card.get("labels") != LABELS
        ):
            raise ValueError("Model feature schema mismatch")
        if self.card.get("origin") not in ("real_experimental", "synthetic_demo") or (
            self.card["origin"] != "real_experimental" and not allow_demo
        ):
            raise ValueError("Synthetic demo models cannot score real footage")
        self.mean, self.std = weights["mean"], weights["std"]
        if (
            self.mean.shape != (len(NAMES),)
            or self.std.shape != (len(NAMES),)
            or not torch.isfinite(self.mean).all()
            or not torch.isfinite(self.std).all()
            or (self.std <= 0).any()
        ):
            raise ValueError("Invalid checkpoint normalization")
        self.model = ActivityNet()
        self.model.load_state_dict(weights["state_dict"])
        self.model.eval()

    def predict(self, sequence):
        sequence = validate_sequence(sequence)
        observed = int(sequence[:, 0].sum())
        if observed < MIN_OBSERVED_FRAMES:
            raise ValueError("Prediction requires at least four observed frames")
        x = torch.tensor(sequence).unsqueeze(0)
        x = ((x - self.mean) / self.std) * x[:, :, :1]
        with torch.no_grad():
            probs = self.model(x).softmax(1)[0].tolist()
        i = int(np.argmax(probs))
        return dict(
            label=LABELS[i],
            score=round(probs[i], 4),
            scores=dict(zip(LABELS, probs)),
            observed_frames=observed,
            note="Uncalibrated model score; not probability of danger",
        )
