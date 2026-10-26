"""Local persisted runs. No public listener or external data service."""

import hashlib
import json
import os
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock, Timeout

from config import CameraConfig

ROOT = Path(
    os.environ.get("CARWATCH_DATA_DIR", Path(__file__).resolve().parent / "runtime")
).resolve()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(data, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def run_dir(run_id, root=ROOT):
    if (
        not isinstance(run_id, str)
        or len(run_id) != 32
        or any(c not in "0123456789abcdef" for c in run_id)
    ):
        raise ValueError("Invalid run ID")
    return Path(root) / "runs" / run_id


def new_run(source, config, session_id, split="train", origin="real", root=ROOT):
    config = CameraConfig.from_dict(config).to_dict()
    if split not in ("train", "val", "test"):
        raise ValueError("Invalid dataset split")
    if (
        origin not in ("real", "synthetic", "sample")
        or not isinstance(session_id, str)
        or not session_id.strip()
        or len(session_id) > 200
    ):
        raise ValueError("Recording group and origin are required")
    source = Path(source)
    run_id = uuid.uuid4().hex
    out = run_dir(run_id, root)
    out.mkdir(parents=True)
    source_name = "source" + source.suffix.lower()
    info = dict(
        id=run_id,
        created=datetime.now(timezone.utc).isoformat(),
        status="queued",
        camera=config["name"],
        session_id=session_id.strip(),
        split=split,
        origin=origin,
        source=source_name,
        config=config,
    )
    try:
        shutil.copyfile(source, out / source_name)
        # Fingerprint the saved snapshot, even if the source changed during import.
        h = hashlib.sha256()
        with (out / source_name).open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        info["video_hash"] = h.hexdigest()
        write_json(out / "meta.json", info)
    except Exception:
        shutil.rmtree(out)
        raise
    return info, out


def list_runs(root=ROOT):
    result = []
    for path in (Path(root) / "runs").glob("*/meta.json"):
        item = read_json(path)
        if item:
            if item.get("status") == "processing" and item.get("analysis_lease") == 1:
                try:
                    with _run_lock(path.parent):
                        # A released OS lock is evidence that this analysis no
                        # longer owns the run, even after an ungraceful exit.
                        item = read_json(path)
                        if item and item.get("status") == "processing":
                            item["status"] = "interrupted"
                except Timeout:
                    pass
            if item:
                result.append(item)
    return sorted(result, key=lambda x: x["created"], reverse=True)


def set_status(out, status, **fields):
    info = read_json(Path(out) / "meta.json")
    info.update(status=status, **fields)
    write_json(Path(out) / "meta.json", info)


def _run_lock(out, timeout=0):
    out = Path(out)
    # Keep the lock outside the deletable directory to preserve one lock inode.
    locks = out.parent / ".locks"
    locks.mkdir(parents=True, exist_ok=True)
    return FileLock(str(locks / (out.name + ".lock")), timeout=timeout)


@contextmanager
def analysis_session(out):
    """Own a run until complete; OS locks also release if the process crashes."""
    out = Path(out)
    lock = _run_lock(out)
    try:
        lock.acquire()
    except Timeout as exc:
        raise ValueError("This recording is already being analyzed") from exc
    try:
        if not (out / "meta.json").is_file():
            raise ValueError("Recording has been deleted")
        set_status(out, "processing", analysis_lease=1, error=None)
        try:
            yield
        except BaseException as exc:
            set_status(out, "failed", error=str(exc) or type(exc).__name__)
            raise
        else:
            set_status(out, "complete", error=None)
    finally:
        lock.release()


def save_review(out, window_id, label):
    from features import LABELS

    if label not in LABELS + ["unreviewed", "exclude"]:
        raise ValueError("Unknown activity label")
    out = Path(out)
    with _run_lock(out, timeout=10):
        if not out.is_dir():
            raise ValueError("Recording has been deleted")
        data = read_json(out / "windows.json", [])
        item = next((item for item in data if item["id"] == window_id), None)
        if item is None:
            raise ValueError("Window not found")
        item.update(
            label=label,
            label_source="human" if label not in ("unreviewed", "exclude") else None,
        )
        write_json(out / "windows.json", data)


def save_event_review(out, event_id, review):
    if review not in (
        "unreviewed",
        "useful observation",
        "ordinary activity",
        "tracking error",
    ):
        raise ValueError("Unknown event review")
    out = Path(out)
    with _run_lock(out, timeout=10):
        if not out.is_dir():
            raise ValueError("Recording has been deleted")
        report = read_json(out / "report.json", {})
        event = next((item for item in report.get("events", []) if item["id"] == event_id), None)
        if event is None:
            raise ValueError("Event not found")
        event["review"] = review
        write_json(out / "report.json", report)


def dataset_rows(root=ROOT, real_only=False):
    rows = []
    for meta in list_runs(root):
        if meta["status"] != "complete" or (real_only and meta["origin"] != "real"):
            continue
        for w in read_json(run_dir(meta["id"], root) / "windows.json", []):
            if w.get("label_source") != "human" or w["label"] in (
                "unreviewed",
                "exclude",
            ):
                continue
            rows.append(
                {
                    **w,
                    **{k: meta[k] for k in ("session_id", "split", "origin", "video_hash")},
                    "run_id": meta["id"],
                }
            )
    return rows


def delete_run(run_id, root=ROOT):
    out = run_dir(run_id, root)
    try:
        with _run_lock(out):
            if out.exists():
                meta = read_json(out / "meta.json", {})
                if meta.get("status") == "processing" and meta.get("analysis_lease") != 1:
                    raise ValueError("Stop analysis before deleting a recording")
                shutil.rmtree(out)
    except Timeout as exc:
        raise ValueError(
            "Wait for analysis or review to finish before deleting a recording"
        ) from exc
