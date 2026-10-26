import copy

import pytest

from config import CameraConfig
from demo import synthetic_dataset
from engine import ActivityEngine
from features import NAMES, make_windows, vector
from store import (
    dataset_rows,
    delete_run,
    new_run,
    run_dir,
    save_review,
    set_status,
    write_json,
)
from temporal import Predictor, fit, validate_dataset

IN = (0.4, 0.3, 0.6, 0.8)
OUT = (0.8, 0.3, 1.0, 0.8)


def test_single_missing_frame_breaks_dwell():
    e = ActivityEngine(dwell=1)
    e.update(0, [(1, IN)])
    e.update(0.5, [])
    assert not e.update(1, [(1, IN)])


def test_jitter_does_not_create_repeated_visits():
    e = ActivityEngine(repeat=2)
    e.update(0, [(1, IN)])
    e.update(0.25, [(1, OUT)])
    assert not e.update(0.5, [(1, IN)])


def test_hand_visibility_and_continuity():
    e = ActivityEngine(hand_zone=(0.4, 0.3, 0.6, 0.6), hand_seconds=0.5)
    hand = [(0.5, 0.5)]
    e.update(0, [(1, IN, hand)])
    assert e.update(0.5, [(1, IN, hand)])[0]["kind"] == "hand_near_zone"
    assert not e.update(0.75, [(1, IN, hand)])
    e.update(1, [(1, IN, [])])
    assert not e.update(1.25, [(1, IN, hand)])


def test_nan_rejected():
    with pytest.raises(ValueError):
        CameraConfig(dwell=float("nan")).validate()
    with pytest.raises(ValueError):
        ActivityEngine().update(float("nan"), [])


def test_feature_windows_missing_values_masked():
    v = vector(IN, [], (0.3, 0.2, 0.7, 0.95), (0.4, 0.3, 0.6, 0.6))
    samples = [
        dict(time=t / 4, people=[dict(track=2, features=v)]) for t in [0, 1, 2, 3, 33, 34, 35, 36]
    ]
    w = make_windows(samples)
    assert len(w) == 2 and w[0]["sequence"][4] == [0.0] * len(NAMES)
    assert w[1]["start"] == 8


def test_dataset_rejects_synthetic_and_duplicate():
    rows = synthetic_dataset(per_class=2)
    with pytest.raises(ValueError, match="excludes"):
        validate_dataset(rows)
    validate_dataset(rows, True)
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_dataset(rows, True)


def test_hash_leakage_even_if_group_renamed():
    rows = synthetic_dataset(per_class=2)
    rows[-1]["video_hash"] = rows[0]["video_hash"]
    with pytest.raises(ValueError, match="leakage"):
        validate_dataset(rows, True)


def test_model_roundtrip_and_demo_isolation(tmp_path):
    rows = synthetic_dataset(per_class=2)
    card = fit(rows, tmp_path, epochs=2, allow_synthetic=True)
    assert card["origin"] == "synthetic_demo"
    with pytest.raises(ValueError, match="cannot score real"):
        Predictor(tmp_path)
    pred = Predictor(tmp_path, allow_demo=True).predict(rows[0]["sequence"])
    assert abs(sum(pred["scores"].values()) - 1) < 1e-5


def test_saved_review_to_dataset_and_delete(tmp_path):
    source = tmp_path / "input.mp4"
    source.write_bytes(b"placeholder")
    info, out = new_run(source, CameraConfig().to_dict(), "session-one", root=tmp_path)
    sample = synthetic_dataset(per_class=2)[0]
    sample.update(label="unreviewed", label_source=None)
    write_json(out / "windows.json", [sample])
    set_status(out, "complete")
    assert not dataset_rows(tmp_path)
    save_review(out, sample["id"], "ordinary_activity")
    rows = dataset_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["label_source"] == "human" and rows[0]["origin"] == "real"
    delete_run(info["id"], tmp_path)
    assert not out.exists()
    with pytest.raises(ValueError):
        run_dir("../escape", tmp_path)


def test_live_idle_never_opens_camera(monkeypatch):
    import live
    from live import LiveMonitor

    def forbidden(*args):
        raise AssertionError("Camera should not be activated")

    monkeypatch.setattr(live.cv2, "VideoCapture", forbidden)
    monitor = LiveMonitor()
    assert monitor.snapshot()["status"] == "idle"
    monitor.stop()
    with pytest.raises(ValueError):
        monitor.start(-1, CameraConfig())


def test_live_invalid_index_rejected_before_access():
    from live import LiveMonitor

    monitor = LiveMonitor()
    with pytest.raises(ValueError):
        monitor.start("rtsp://example", CameraConfig())
    with pytest.raises(ValueError):
        monitor.start(0, CameraConfig(), 11)


def test_example_labels_are_omitted_from_real_dataset(tmp_path):
    source = tmp_path / "sample.avi"
    source.write_bytes(b"sample fixture")
    meta, out = new_run(source, CameraConfig().to_dict(), "example", origin="sample", root=tmp_path)
    w = synthetic_dataset(per_class=2)[0]
    w.update(label="ordinary_activity", label_source="human")
    write_json(out / "windows.json", [w])
    set_status(out, "complete")
    assert len(dataset_rows(tmp_path)) == 1
    assert not dataset_rows(tmp_path, real_only=True)
