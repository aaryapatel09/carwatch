import queue
import threading
from types import SimpleNamespace

import numpy as np
import pytest
import torch
import ultralytics

import live
from config import CameraConfig
from store import read_json


class Messages(queue.Queue):
    def cancel_join_thread(self):
        pass


class FakeCamera:
    def __init__(self, opened=True):
        self.opened = opened
        self.released = False
        self.remaining = 5

    def isOpened(self):
        return self.opened

    def read(self):
        self.remaining -= 1
        return (
            (True, np.zeros((64, 64, 3), dtype=np.uint8)) if self.remaining >= 0 else (False, None)
        )

    def release(self):
        self.released = True


class FakePose:
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


@pytest.mark.parametrize("phone_alerts", [False, True])
def test_worker_activity_disk_evidence_and_disconnect(tmp_path, monkeypatch, phone_alerts):
    cap = FakeCamera()
    clock = [0.0]

    def tick():
        clock[0] += 0.25
        return clock[0]

    monkeypatch.setattr(live.time, "monotonic", tick)
    monkeypatch.setattr(live.cv2, "VideoCapture", lambda _: cap)
    monkeypatch.setattr(ultralytics, "YOLO", lambda _: FakePose())
    notifications = []

    class Dispatcher:
        def __init__(self, config, path, stop_signal):
            pass

        def start(self):
            pass

        def enqueue(self, event_id, kind):
            # Evidence is durable before anything is eligible for external delivery.
            saved = read_json(tmp_path / "session.json")
            assert any(e["id"] == event_id for e in saved["events"])
            notifications.append((event_id, kind))

        def snapshot(self):
            return {"queued": len(notifications)}

        def close(self):
            pass

    monkeypatch.setattr(live, "AlertDispatcher", Dispatcher)
    monkeypatch.setattr(live.AlertConfig, "from_env", lambda: object())
    messages = Messages(2)
    live._camera_worker(
        0,
        CameraConfig(dwell=1, hand_seconds=0.25).to_dict(),
        1,
        threading.Event(),
        messages,
        tmp_path,
        phone_alerts,
    )
    state = read_json(tmp_path / "session.json")
    assert state["status"] == "error" and "stopped delivering" in state["error"]
    assert cap.released and state["frame"] is None and len(state["events"]) == 2
    assert all((tmp_path / e["image"]).is_file() for e in state["events"])
    assert messages.qsize() <= 2
    assert len(notifications) == (2 if phone_alerts else 0)


def test_worker_device_unavailable_and_pre_stopped(tmp_path, monkeypatch):
    cap = FakeCamera(opened=False)
    monkeypatch.setattr(live.cv2, "VideoCapture", lambda _: cap)
    monkeypatch.setattr(ultralytics, "YOLO", lambda _: FakePose())
    live._camera_worker(0, CameraConfig().to_dict(), 1, threading.Event(), Messages(2), tmp_path)
    assert cap.released and read_json(tmp_path / "session.json")["status"] == "error"
    stop = threading.Event()
    stop.set()
    monkeypatch.setattr(live.cv2, "VideoCapture", lambda _: pytest.fail("must not open"))
    live._camera_worker(0, CameraConfig().to_dict(), 1, stop, Messages(2), tmp_path)
    assert read_json(tmp_path / "session.json")["status"] == "stopped"
