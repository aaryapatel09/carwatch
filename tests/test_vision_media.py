"""Codec and pipeline regressions without a camera or model download."""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
import torch
import ultralytics

import media
import vision
from config import CameraConfig
from store import read_json


class Capture:
    def __init__(self, frames=12, fps=4, total=None):
        self.frames = frames
        self.fps = fps
        self.total = frames if total is None else total
        self.reads = 0
        self.released = False

    def isOpened(self):
        return True

    def get(self, key):
        return {cv2.CAP_PROP_FPS: self.fps, cv2.CAP_PROP_FRAME_COUNT: self.total}.get(key, 64)

    def read(self):
        self.reads += 1
        return (
            (True, np.zeros((64, 64, 3), dtype=np.uint8))
            if self.reads <= self.frames
            else (False, None)
        )

    def release(self):
        self.released = True


class Detector:
    def track(self, frame, **kwargs):
        pose = torch.zeros((1, 17, 3))
        pose[0, 9] = torch.tensor([32, 32, 0.9])
        return [
            SimpleNamespace(
                boxes=SimpleNamespace(id=torch.tensor([1]), xyxy=torch.tensor([[16, 8, 48, 56]])),
                keypoints=SimpleNamespace(data=pose),
                plot=lambda: frame.copy(),
            )
        ]


@pytest.fixture
def pipeline(monkeypatch):
    cap = Capture()
    monkeypatch.setattr(vision.cv2, "VideoCapture", lambda _: cap)
    monkeypatch.setattr(ultralytics, "YOLO", lambda _: Detector())

    def clip(source, dest, *args):
        Path(dest).write_bytes(b"clip fixture")
        return dest

    monkeypatch.setattr(vision, "extract_track_clip", clip)
    return cap


def test_pose_to_windows_report_and_evidence(pipeline, tmp_path):
    config = CameraConfig(dwell=1, hand_seconds=0.25)
    seen = []
    report = vision.analyze(
        "fixture", tmp_path, config=config, progress=lambda p, img: seen.append(p)
    )
    assert pipeline.released and report["sampled_frames"] == 12 and seen
    assert {e["kind"] for e in report["events"]} == {"lingering", "hand_near_zone"}
    assert all((tmp_path / e["clip"]).exists() for e in report["events"])
    assert read_json(tmp_path / "windows.json")[0]["sequence"][0][5] == 1
    assert read_json(tmp_path / "report.json")["status"] == "processed"


def test_decoder_metadata_nan_and_empty(pipeline, tmp_path):
    pipeline.fps = float("nan")
    with pytest.raises(ValueError, match="frame rate"):
        vision.analyze("fixture", tmp_path)
    assert pipeline.released
    pipeline.fps = 4
    pipeline.frames = 0
    pipeline.total = float("nan")
    pipeline.released = False
    with pytest.raises(ValueError, match="no decodable"):
        vision.analyze("fixture", tmp_path)
    assert pipeline.released


def test_model_failure_releases_video(pipeline, tmp_path, monkeypatch):
    def fail(_):
        raise RuntimeError("load failed")

    monkeypatch.setattr(ultralytics, "YOLO", fail)
    with pytest.raises(RuntimeError, match="load failed"):
        vision.analyze("fixture", tmp_path)
    assert pipeline.released


def test_bad_custom_model_does_not_open_camera(tmp_path, monkeypatch):
    def forbidden(_):
        raise AssertionError("capture must not open")

    monkeypatch.setattr(vision.cv2, "VideoCapture", forbidden)
    with pytest.raises(FileNotFoundError):
        vision.analyze("fixture", tmp_path, config=CameraConfig(), model_path=tmp_path / "missing")


def test_failed_image_write_is_not_success(pipeline, tmp_path, monkeypatch):
    monkeypatch.setattr(vision.cv2, "imwrite", lambda *a: False)
    with pytest.raises(OSError, match="preview"):
        vision.analyze("fixture", tmp_path)
    assert pipeline.released and not (tmp_path / "report.json").exists()


def test_clip_failure_preserves_report_and_still(pipeline, tmp_path, monkeypatch):
    def failed(*args):
        raise RuntimeError("encoder unavailable")

    monkeypatch.setattr(vision, "extract_track_clip", failed)
    report = vision.analyze("fixture", tmp_path, config=CameraConfig(dwell=1))
    assert report["events"] and report["warnings"] == ["encoder unavailable"]
    assert all(e["clip"] is None and (tmp_path / e["image"]).exists() for e in report["events"])


@pytest.mark.parametrize("limit", [0, -1, 301, float("inf"), float("nan"), "60"])
def test_analysis_duration_rejected_before_io(tmp_path, limit, monkeypatch):
    monkeypatch.setattr(vision.cv2, "VideoCapture", lambda _: pytest.fail("must not open"))
    with pytest.raises(ValueError, match="duration"):
        vision.analyze("fixture", tmp_path, max_seconds=limit)


def test_duration_cap_and_unknown_frame_count(pipeline, tmp_path):
    pipeline.total = 0
    report = vision.analyze("fixture", tmp_path, max_seconds=1)
    assert report["sampled_frames"] == 4 and report["duration_seconds"] == 1


@pytest.mark.parametrize(
    "start,end", [(-1, 2), (1, 1), (0, 301), (float("nan"), 2), (0, float("inf"))]
)
def test_media_bad_intervals(tmp_path, start, end):
    with pytest.raises(ValueError):
        media.extract_track_clip("missing", tmp_path / "x.mp4", start, end, [], 1)


def test_failed_ffmpeg_preserves_previous_clip(tmp_path, monkeypatch):
    dest = tmp_path / "clip.mp4"
    dest.write_bytes(b"old")
    monkeypatch.setattr(media.shutil, "which", lambda _: "/fake/ffmpeg")

    def fail(cmd, **kwargs):
        Path(cmd[-1]).write_bytes(b"partial")
        raise subprocess.TimeoutExpired(cmd, 120)

    monkeypatch.setattr(media.subprocess, "run", fail)
    with pytest.raises(subprocess.TimeoutExpired):
        media.extract_clip("input", dest, 0, 1)
    assert dest.read_bytes() == b"old" and list(tmp_path.iterdir()) == [dest]


def test_real_silent_codec_and_track_overlay(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg unavailable")
    source = tmp_path / "input.avi"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 4, (64, 64))
    assert writer.isOpened()
    for _ in range(8):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    samples = [
        dict(time=i / 4, people=[dict(track=1, features=[1, 1, 0.5, 0.8, 0, 0, 0.4, 0.7, 0, 0])])
        for i in range(8)
    ]
    out = media.extract_track_clip(source, tmp_path / "review.mp4", 0, 2, samples, 1)
    cap = cv2.VideoCapture(str(out))
    ok, frame = cap.read()
    cap.release()
    assert ok and frame.mean() > 1  # selected-track overlay on black input
    if shutil.which("ffprobe"):
        result = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(out),
            ]
        )
        assert b"video" in result and b"audio" not in result
