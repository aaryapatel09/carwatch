import copy
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from config import CameraConfig
from demo import synthetic_dataset
from features import validate_sequence
from live import LiveMonitor
from store import new_run, read_json, save_event_review, save_review, write_json
from temporal import Predictor, fit, validate_dataset


@pytest.mark.parametrize(
    "kwargs",
    [
        {"repeat": True},
        {"repeat": 2.5},
        {"pose": "false"},
        {"zone": None},
        {"zone": [0, 0, "1", 1]},
        {"name": None},
        {"confidence": True},
    ],
)
def test_invalid_config_types(kwargs):
    with pytest.raises(ValueError):
        CameraConfig(**kwargs).validate()


def test_concurrent_reviews_preserve_both_updates(tmp_path):
    write_json(tmp_path / "windows.json", [dict(id="a"), dict(id="b")])
    write_json(
        tmp_path / "report.json",
        dict(events=[dict(id="a", review="unreviewed"), dict(id="b", review="unreviewed")]),
    )
    with ThreadPoolExecutor(4) as pool:
        futures = [
            pool.submit(save_review, tmp_path, "a", "lingering"),
            pool.submit(save_review, tmp_path, "b", "ordinary_activity"),
            pool.submit(save_event_review, tmp_path, "a", "useful observation"),
            pool.submit(save_event_review, tmp_path, "b", "tracking error"),
        ]
        for f in futures:
            f.result()
    assert [w["label"] for w in read_json(tmp_path / "windows.json")] == [
        "lingering",
        "ordinary_activity",
    ]
    assert [e["review"] for e in read_json(tmp_path / "report.json")["events"]] == [
        "useful observation",
        "tracking error",
    ]


def test_atomic_json_failure_does_not_destroy_existing(tmp_path):
    target = tmp_path / "file.json"
    write_json(target, {"old": True})
    with pytest.raises(ValueError):
        write_json(target, {"invalid": float("nan")})
    assert read_json(target) == {"old": True} and list(tmp_path.iterdir()) == [target]


def test_failed_copy_does_not_leave_run(tmp_path, monkeypatch):
    source = tmp_path / "x.mp4"
    source.write_bytes(b"fixture")

    def fail(*a):
        raise OSError("disk full")

    monkeypatch.setattr("store.shutil.copyfile", fail)
    with pytest.raises(OSError):
        new_run(source, CameraConfig().to_dict(), "session", root=tmp_path)
    assert not list((tmp_path / "runs").glob("*"))


def test_duplicate_video_reanalysis_cannot_inflate_dataset():
    rows = synthetic_dataset(per_class=2)
    for r in rows:
        r["run_id"] = "original"
    duplicate = copy.deepcopy(rows[0])
    duplicate["run_id"] = "reanalysis"
    duplicate["track"] = 999
    with pytest.raises(ValueError, match="Duplicate recording"):
        validate_dataset(rows + [duplicate], True)


@pytest.mark.parametrize("column,value", [(0, 0.5), (2, 2), (8, 5), (4, 0)])
def test_invalid_feature_domains(column, value):
    sequence = synthetic_dataset(per_class=2)[-1]["sequence"]
    sequence[10][column] = value
    with pytest.raises(ValueError):
        validate_sequence(sequence)


def test_checkpoint_integrity_and_label_order(tmp_path):
    fit(synthetic_dataset(per_class=2), tmp_path, epochs=1, allow_synthetic=True)
    card = read_json(tmp_path / "model.json")
    card["labels"] = list(reversed(card["labels"]))
    write_json(tmp_path / "model.json", card)
    with pytest.raises(ValueError, match="schema"):
        Predictor(tmp_path, allow_demo=True)
    with (tmp_path / card["weights_file"]).open("ab") as f:
        f.write(b"changed")
    with pytest.raises(ValueError, match="integrity"):
        Predictor(tmp_path, allow_demo=True)


def hung_worker(camera, config, minutes, stop, messages, out):
    # Simulate a device driver ignoring stop; no camera or model is opened.
    while True:
        time.sleep(0.1)


def clean_worker(camera, config, minutes, stop, messages, out):
    write_json(
        Path(out) / "session.json",
        dict(status="stopped", events=[], frame=None, error=None, elapsed=0, last_frame=None),
    )


def test_blocked_capture_is_terminated_and_can_restart(tmp_path):
    monitor = LiveMonitor(root=tmp_path, worker=hung_worker)
    monitor.start(0, CameraConfig())
    process = monitor.process
    try:
        with pytest.raises(ValueError, match="already running"):
            monitor.start(0, CameraConfig())
        before = time.monotonic()
        monitor.stop()
        assert time.monotonic() - before < 6 and not process.is_alive()
        state = monitor.snapshot()
        assert state["status"] == "stopped" and "forced stop" in state["warning"]
        monitor.worker = clean_worker
        monitor.start(0, CameraConfig())
        monitor.process.join(timeout=10)
        assert not monitor.process.is_alive()
        assert monitor.snapshot()["status"] == "stopped"
    finally:
        monitor.stop()


def test_invalid_detection_breaks_continuous_evidence():
    from engine import ActivityEngine

    engine = ActivityEngine(dwell=1)
    box = (0.4, 0.3, 0.6, 0.8)
    engine.update(0, [(1, box)])
    engine.update(0.5, [(1, (float("nan"), 0, 1, 1))])
    assert not engine.update(1, [(1, box)])
    with pytest.raises(ValueError, match="unique"):
        engine.update(1.5, [(1, box), (1, box)])
