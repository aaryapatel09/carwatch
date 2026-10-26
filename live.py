"""Opt-in camera monitoring in a killable process, isolated from the UI server."""

import multiprocessing as mp
import queue
import threading
import time
import uuid
from pathlib import Path

import cv2

from config import CameraConfig, finite_number
from engine import ActivityEngine
from store import ROOT, read_json, write_json


def _idle_state():
    return dict(status="idle", frame=None, events=[], error=None, elapsed=0.0, last_frame=None)


def _emit(messages, state):
    """Keep only the most recent observations; a slow UI must not grow memory."""
    try:
        messages.put_nowait(state.copy())
    except queue.Full:
        try:
            messages.get_nowait()
        except queue.Empty:
            pass
        try:
            messages.put_nowait(state.copy())
        except queue.Full:
            pass


def _camera_worker(camera, config_data, minutes, stop, messages, out):
    state = _idle_state()
    cap = None
    started = time.monotonic()
    out = Path(out)
    try:
        from ultralytics import YOLO

        config = CameraConfig.from_dict(config_data)
        model = YOLO(
            str(Path(__file__).parent / ("yolo11n-pose.pt" if config.pose else "yolo11n.pt"))
        )
        if stop.is_set():
            return
        cap = cv2.VideoCapture(camera)
        if not cap.isOpened():
            raise RuntimeError(
                "Camera could not be opened. Check the device and camera permission."
            )
        engine = ActivityEngine(
            zone=config.zone,
            dwell=config.dwell,
            repeat=config.repeat,
            window=config.window,
            hand_zone=config.hand_zone if config.pose else None,
            hand_seconds=config.hand_seconds,
        )
        next_sample = 0.0
        while not stop.is_set() and time.monotonic() - started < minutes * 60:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Camera stopped delivering frames")
            t = time.monotonic() - started
            if t < next_sample:
                stop.wait(0.01)
                continue
            next_sample = t + 0.25
            h, w = frame.shape[:2]
            r = model.track(
                frame,
                persist=True,
                classes=[0],
                conf=config.confidence,
                tracker="bytetrack.yaml",
                verbose=False,
            )[0]
            people = []
            if r.boxes.id is not None:
                poses = r.keypoints.data.cpu().tolist() if r.keypoints is not None else None
                for idx, (tid, box) in enumerate(
                    zip(r.boxes.id.cpu().tolist(), r.boxes.xyxy.cpu().tolist())
                ):
                    b = [box[0] / w, box[1] / h, box[2] / w, box[3] / h]
                    wrists = []
                    if poses:
                        for k in (9, 10):
                            x, y, confidence = poses[idx][k]
                            if confidence >= 0.5 and 0 < x < w and 0 < y < h:
                                wrists.append((x / w, y / h))
                    people.append((int(tid), b, wrists))
            new = engine.update(t, people)
            annotated = r.plot()
            for rect, color in [
                (config.zone, (125, 225, 165)),
                (config.hand_zone, (80, 180, 250)),
            ]:
                a, b, c, d = rect
                cv2.rectangle(
                    annotated,
                    (int(a * w), int(b * h)),
                    (int(c * w), int(d * h)),
                    color,
                    2,
                )
            for event in new:
                if len(state["events"]) < 100:
                    event["id"] = f"e{len(state['events']):04d}"
                    event["image"] = event["id"] + ".jpg"
                    if not cv2.imwrite(str(out / event["image"]), annotated):
                        raise OSError("Could not save event snapshot")
                    state["events"].append(event)
                else:
                    state["warning"] = "Event limit reached (100); additional events are not saved"
            # Bound preview memory and queue message size even with high-resolution cameras.
            ratio = min(1.0, 960 / max(w, h))
            preview = cv2.resize(annotated, (max(1, int(w * ratio)), max(1, int(h * ratio))))
            ok, encoded = cv2.imencode(".jpg", preview)
            if not ok:
                raise RuntimeError("Could not encode live preview")
            state.update(
                status="running",
                frame=encoded.tobytes(),
                elapsed=t,
                last_frame=time.time(),
                output=str(out),
            )
            write_json(out / "session.json", {k: v for k, v in state.items() if k != "frame"})
            _emit(messages, state)
    except Exception as exc:
        state.update(status="error", error=str(exc))
    finally:
        if cap is not None:
            cap.release()
        if state["status"] != "error":
            state["status"] = "stopped"
        state["frame"] = None
        try:
            write_json(out / "session.json", state)
        finally:
            _emit(messages, state)
            # Do not let an unread preview queue hold a completed process alive.
            messages.cancel_join_thread()


class LiveMonitor:
    def __init__(self, root=ROOT, worker=None):
        self.root = Path(root)
        self.context = mp.get_context("spawn")
        self.worker = worker or _camera_worker
        self.lock = threading.RLock()
        self.process = None
        self.messages = None
        self.stop_event = None
        self.timer = None
        self.out = None
        self._state = _idle_state()

    def _drain(self):
        if self.messages is not None:
            while True:
                try:
                    self._state = self.messages.get_nowait()
                except (queue.Empty, ValueError, OSError):
                    break

    def snapshot(self):
        with self.lock:
            self._drain()
            if (
                self.process is not None
                and not self.process.is_alive()
                and self._state["status"] in ("starting", "running", "stopping")
            ):
                final = read_json(self.out / "session.json", {})
                if final.get("status") in ("stopped", "error"):
                    self._state.update(final, frame=None)
                else:
                    self._state.update(
                        status="error",
                        frame=None,
                        error="Camera process exited before reporting completion",
                    )
            return {**self._state, "events": [e.copy() for e in self._state["events"]]}

    def start(self, camera, config, minutes=2):
        if type(camera) is not int or not 0 <= camera <= 9:
            raise ValueError("Choose a local camera index between 0 and 9")
        if not finite_number(minutes) or not 1 <= minutes <= 10:
            raise ValueError("Live sessions must last 1–10 minutes")
        config_data = config.to_dict()
        with self.lock:
            if self.process is not None and self.process.is_alive():
                raise ValueError("A camera session is already running")
            if self.timer:
                self.timer.cancel()
            if self.messages:
                self.messages.close()
            self.out = self.root / "live" / uuid.uuid4().hex
            self.out.mkdir(parents=True)
            self.messages = self.context.Queue(maxsize=2)
            self.stop_event = self.context.Event()
            self._state = {
                **_idle_state(),
                "status": "starting",
                "output": str(self.out),
            }
            write_json(
                self.out / "session.json",
                {k: v for k, v in self._state.items() if k != "frame"},
            )
            self.process = self.context.Process(
                target=self.worker,
                args=(
                    camera,
                    config_data,
                    minutes,
                    self.stop_event,
                    self.messages,
                    self.out,
                ),
                daemon=True,
            )
            try:
                self.process.start()
            except Exception as exc:
                self._state.update(status="error", error=str(exc))
                write_json(self.out / "session.json", self._state)
                self.process = None
                raise
            # Parent watchdog bounds time even if OpenCV blocks in camera open/read.
            self.timer = threading.Timer(minutes * 60, self.stop, args=(self.process,))
            self.timer.daemon = True
            self.timer.start()

    def stop(self, expected_process=None):
        with self.lock:
            if self.process is None or (
                expected_process is not None and expected_process is not self.process
            ):
                return
            if self.timer:
                self.timer.cancel()
            self.stop_event.set()
            self._drain()
            self.process.join(timeout=1.0)
            forced = self.process.is_alive()
            if forced:
                self.process.terminate()
                self.process.join(timeout=2.0)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2.0)
            # A terminated producer can corrupt its pipe; do not read it after force-stop.
            if not forced:
                self._drain()
            self.messages.close()
            self.messages = None
            self._state.update(status="stopped", frame=None)
            if forced:
                self._state["warning"] = (
                    "Camera process required a forced stop; the latest unsaved frame may be lost"
                )
            write_json(
                self.out / "session.json",
                {k: v for k, v in self._state.items() if k != "frame"},
            )
