"""Opt-in camera monitoring in a killable process, isolated from the UI server."""

import multiprocessing as mp
import queue
import threading
import time
import uuid
from pathlib import Path

import cv2

from alerts import AlertConfig, AlertDispatcher, cancel_pending
from config import CameraConfig, finite_number
from detection import track_frame
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


def _camera_worker(camera, config_data, minutes, stop, messages, out, phone_alerts=False):
    state = _idle_state()
    cap = None
    dispatcher = None
    started = time.monotonic()
    out = Path(out)
    try:
        notification_config = AlertConfig.from_env() if phone_alerts else None
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
        if phone_alerts:
            dispatcher = AlertDispatcher(notification_config, out / "alerts.json", stop_signal=stop)
            dispatcher.start()
            state["alerts"] = {}
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
            people, annotated = track_frame(model, frame, config)
            new = engine.update(t, people)
            saved_events = []
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
                    event["observed_at"] = time.time()
                    if not cv2.imwrite(str(out / event["image"]), annotated):
                        raise OSError("Could not save event snapshot")
                    state["events"].append(event)
                    saved_events.append(event)
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
            if dispatcher:
                for event in saved_events:
                    dispatcher.enqueue(event["id"], event["kind"])
                state["alerts"] = dispatcher.snapshot()
            _emit(messages, state)
    except Exception as exc:
        state.update(status="error", error=str(exc))
    finally:
        if dispatcher:
            try:
                dispatcher.close()
                state["alerts"] = dispatcher.snapshot()
            except Exception:
                state.update(status="error", error="Could not finalize the notification journal")
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
                if (self.out / "alerts.json").exists():
                    self._state["alerts"] = cancel_pending(self.out / "alerts.json")
            snapshot = {**self._state, "events": [e.copy() for e in self._state["events"]]}
            if "alerts" in snapshot:
                snapshot["alerts"] = snapshot["alerts"].copy()
            return snapshot

    def start(self, camera, config, minutes=2, phone_alerts=False):
        if type(camera) is not int or not 0 <= camera <= 9:
            raise ValueError("Choose a local camera index between 0 and 9")
        if not finite_number(minutes) or not 1 <= minutes <= 10:
            raise ValueError("Live sessions must last 1–10 minutes")
        config_data = config.to_dict()
        if type(phone_alerts) is not bool:
            raise ValueError("Phone alerts must be explicitly enabled or disabled")
        if phone_alerts:
            AlertConfig.from_env()  # Validate before starting a camera or worker.
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
                )
                + ((True,) if phone_alerts else ()),
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
            if self.messages is None and not self.process.is_alive():
                return  # Repeated Stop and an already-fired watchdog are harmless.
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
            if self.messages is not None:
                self.messages.close()
            self.messages = None
            if self.process.is_alive():
                self._state.update(
                    status="stopping",
                    frame=None,
                    error="Camera process did not exit; stop is not confirmed",
                )
            else:
                # The queue's final update can be dropped during worker shutdown.
                # Read the durable record before saving any parent-side stop state.
                final = read_json(self.out / "session.json", {})
                self._state.update(final, frame=None)
                if self._state["status"] not in ("stopped", "error"):
                    self._state["status"] = "stopped" if forced else "error"
                    if not forced:
                        self._state["error"] = "Camera process exited before reporting completion"
                if (self.out / "alerts.json").exists():
                    self._state["alerts"] = cancel_pending(self.out / "alerts.json")
            if forced:
                self._state["warning"] = (
                    "Camera process required a forced stop; the latest unsaved frame may be lost"
                )
            write_json(
                self.out / "session.json",
                {k: v for k, v in self._state.items() if k != "frame"},
            )
