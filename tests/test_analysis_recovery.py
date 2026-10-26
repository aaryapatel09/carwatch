import multiprocessing as mp
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from config import CameraConfig
from store import (
    analysis_session,
    delete_run,
    list_runs,
    new_run,
    read_json,
    save_review,
    write_json,
)


def held_analysis(out, ready):
    with analysis_session(out):
        ready.set()
        mp.Event().wait(60)


def fixture_run(tmp_path):
    source = tmp_path / "fixture.mp4"
    source.write_bytes(b"simulated recording; no decoder or camera opened")
    return new_run(source, CameraConfig().to_dict(), "recovery-test", root=tmp_path)


def test_crashed_analysis_is_recoverable_but_active_analysis_is_protected(tmp_path):
    meta, out = fixture_run(tmp_path)
    context = mp.get_context("spawn")
    ready = context.Event()
    worker = context.Process(target=held_analysis, args=(out, ready))
    worker.start()
    try:
        assert ready.wait(10)
        assert list_runs(tmp_path)[0]["status"] == "processing"
        with pytest.raises(ValueError, match="before deleting"):
            delete_run(meta["id"], tmp_path)
        with pytest.raises(ValueError, match="already being analyzed"):
            with analysis_session(out):
                pytest.fail("Two owners must never analyze one run")
        worker.terminate()
        worker.join(timeout=5)
        assert not worker.is_alive()
        assert read_json(out / "meta.json")["status"] == "processing"
        assert list_runs(tmp_path)[0]["status"] == "interrupted"
        delete_run(meta["id"], tmp_path)
        assert not out.exists() and not list_runs(tmp_path)
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=5)


def test_analysis_lifecycle_failure_retry_and_missing_recording(tmp_path):
    meta, out = fixture_run(tmp_path)
    with pytest.raises(RuntimeError, match="decoder failed"):
        with analysis_session(out):
            raise RuntimeError("decoder failed")
    assert list_runs(tmp_path)[0]["status"] == "failed"
    assert read_json(out / "meta.json")["error"] == "decoder failed"
    with analysis_session(out):
        assert list_runs(tmp_path)[0]["status"] == "processing"
    assert list_runs(tmp_path)[0]["status"] == "complete"
    assert read_json(out / "meta.json")["error"] is None
    delete_run(meta["id"], tmp_path)
    with pytest.raises(ValueError, match="deleted"):
        with analysis_session(out):
            pytest.fail("Deleted runs must not be recreated")
    assert not out.exists()


def test_delete_cannot_race_a_review_or_resurrect_removed_data(tmp_path, monkeypatch):
    meta, out = fixture_run(tmp_path)
    write_json(out / "windows.json", [dict(id="window")])
    saving, release = threading.Event(), threading.Event()

    def paused_write(path, data):
        saving.set()
        assert release.wait(5)
        write_json(path, data)

    monkeypatch.setattr("store.write_json", paused_write)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(save_review, out, "window", "ordinary_activity")
        try:
            assert saving.wait(5)
            with pytest.raises(ValueError, match="before deleting"):
                delete_run(meta["id"], tmp_path)
        finally:
            release.set()
        future.result(timeout=5)
    delete_run(meta["id"], tmp_path)
    with pytest.raises(ValueError, match="deleted"):
        save_review(out, "window", "lingering")
    assert not out.exists()
