import hashlib
import shutil
from pathlib import Path

import pytest

from config import CameraConfig
from demo import synthetic_dataset
from live import LiveMonitor
from store import new_run, read_json, write_json
from temporal import Predictor, fit


def test_recording_fingerprint_matches_saved_bytes(tmp_path, monkeypatch):
    source = tmp_path / "recording.mp4"
    source.write_bytes(b"before copying")
    copyfile = shutil.copyfile

    def changed_source(src, dst):
        Path(src).write_bytes(b"changed before copying")
        return copyfile(src, dst)

    monkeypatch.setattr("store.shutil.copyfile", changed_source)
    meta, out = new_run(source, CameraConfig().to_dict(), "session", root=tmp_path)
    assert meta["video_hash"] == hashlib.sha256((out / meta["source"]).read_bytes()).hexdigest()


@pytest.mark.parametrize("failed_file", ["weights", "dataset", "model"])
def test_failed_model_publish_preserves_previous_model(tmp_path, monkeypatch, failed_file):
    import temporal

    rows = synthetic_dataset(per_class=2)
    out = tmp_path / "model"
    original_card = fit(rows, out, epochs=1, allow_synthetic=True)
    original_prediction = Predictor(out, allow_demo=True).predict(rows[0]["sequence"])
    replace = temporal.os.replace

    def interrupted_publish(src, dst):
        dest = Path(dst)
        if dest.parent == out and dest.stem.startswith(failed_file):
            raise OSError("simulated publication failure")
        return replace(src, dst)

    with monkeypatch.context() as patch:
        patch.setattr(temporal.os, "replace", interrupted_publish)
        with pytest.raises(OSError, match="publication failure"):
            fit(rows, out, epochs=2, allow_synthetic=True)
    assert read_json(out / "model.json") == original_card
    assert Predictor(out, allow_demo=True).predict(rows[0]["sequence"]) == original_prediction
    # A failed replacement must not prevent a later successful retraining.
    new_card = fit(rows, out, epochs=2, allow_synthetic=True)
    assert read_json(out / "model.json") == new_card
    assert Predictor(out, allow_demo=True).predict(rows[0]["sequence"])["scores"]


def test_legacy_checkpoint_remains_readable(tmp_path):
    rows = synthetic_dataset(per_class=2)
    card = fit(rows, tmp_path, epochs=1, allow_synthetic=True)
    original = Predictor(tmp_path, allow_demo=True).predict(rows[0]["sequence"])
    shutil.copyfile(tmp_path / card.pop("weights_file"), tmp_path / "weights.pt")
    shutil.copyfile(tmp_path / card.pop("manifest_file"), tmp_path / "dataset_manifest.json")
    write_json(tmp_path / "model.json", card)
    assert Predictor(tmp_path, allow_demo=True).predict(rows[0]["sequence"]) == original


@pytest.mark.parametrize("name", ["../escape.pt", "..\\escape.pt", "/escape.pt", None])
def test_checkpoint_filename_stays_in_model_directory(tmp_path, name):
    write_json(tmp_path / "model.json", dict(weights_file=name))
    with pytest.raises(ValueError, match="filename"):
        Predictor(tmp_path)


def final_error_worker(camera, config, minutes, stop, messages, out):
    # The final queue message may be absent; the durable record remains authoritative.
    write_json(
        Path(out) / "session.json",
        dict(
            status="error",
            events=[dict(id="e0000", kind="lingering", time=1.5, track=1)],
            frame=None,
            error="simulated camera disconnect",
            elapsed=1.5,
            last_frame=None,
        ),
    )


def test_stop_preserves_completed_worker_record(tmp_path):
    monitor = LiveMonitor(root=tmp_path, worker=final_error_worker)
    try:
        monitor.start(0, CameraConfig())
        monitor.process.join(timeout=10)
        assert not monitor.process.is_alive()
        expected = read_json(monitor.out / "session.json")
        # Stop may come from the watchdog even after the camera has disconnected.
        monitor.stop()
        assert monitor.snapshot()["events"] == expected["events"]
        assert monitor.snapshot()["status"] == "error"
        assert read_json(monitor.out / "session.json")["error"] == expected["error"]
        monitor.stop()
        assert read_json(monitor.out / "session.json")["status"] == "error"
    finally:
        monitor.stop()
