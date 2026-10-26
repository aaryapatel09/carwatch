import math
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from config import finite_number


def _validate_interval(start, end):
    if not all(finite_number(v) for v in (start, end)) or start < 0 or not 0 < end - start <= 300:
        raise ValueError("Invalid clip interval (maximum 300 seconds)")


def extract_clip(source, dest, start, end):
    """Encode short silent H.264 evidence clips for browser playback."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for review clips.")
    _validate_interval(start, end)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temporary = dest.with_name(f".{dest.stem}-{uuid.uuid4().hex}.mp4")
    try:
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(start),
                "-i",
                str(source),
                "-t",
                str(end - start),
                "-an",
                "-vf",
                r"scale=trunc(min(960\,iw)/2)*2:-2",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "25",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(temporary),
            ],
            capture_output=True,
            timeout=120,
        )
        if result.returncode or not temporary.exists() or not temporary.stat().st_size:
            raise RuntimeError(
                "Clip encoding failed: " + result.stderr.decode(errors="replace")[-300:]
            )
        os.replace(temporary, dest)
    finally:
        temporary.unlink(missing_ok=True)
    return dest


def extract_track_clip(source, dest, start, end, samples, track):
    """Overlay only the selected track, using saved detection samples, then encode."""
    import bisect
    import tempfile

    import cv2

    _validate_interval(start, end)
    times = [s["time"] for s in samples]
    if not all(finite_number(t) and t >= 0 for t in times) or times != sorted(times):
        raise ValueError("Detection timestamps must be finite and ordered")
    cap = cv2.VideoCapture(str(source))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not cap.isOpened() or not math.isfinite(fps) or not 0 < fps <= 240:
        cap.release()
        raise ValueError("Cannot decode source clip")
    writer = None
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        dimensions = [
            cap.get(cv2.CAP_PROP_FRAME_WIDTH),
            cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
        ]
        if not all(math.isfinite(v) and v >= 2 for v in dimensions):
            raise ValueError("Invalid video dimensions")
        width, height = map(int, dimensions)
        scale = min(1.0, 960 / max(width, height))
        size = (
            max(2, int(width * scale) // 2 * 2),
            max(2, int(height * scale) // 2 * 2),
        )
        with tempfile.TemporaryDirectory(prefix="carwatch-overlay-") as temp:
            raw = Path(temp) / "annotated.avi"
            writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
            if not writer.isOpened():
                raise RuntimeError("Unable to create annotated review clip")
            frame_index = 0
            while start + frame_index / fps < end:
                ok, frame = cap.read()
                if not ok:
                    break
                t = start + frame_index / fps
                frame = cv2.resize(frame, size)
                idx = bisect.bisect_right(times, t) - 1
                if idx >= 0 and t - times[idx] < 0.4:
                    for p in samples[idx]["people"]:
                        if p["track"] != track:
                            continue
                        v = p["features"]
                        x, y, bw, bh = v[2], v[3], v[6], v[7]
                        a = (
                            max(0, int((x - bw / 2) * size[0])),
                            max(0, int((y - bh) * size[1])),
                        )
                        b = (
                            min(size[0] - 1, int((x + bw / 2) * size[0])),
                            min(size[1] - 1, int(y * size[1])),
                        )
                        cv2.rectangle(frame, a, b, (125, 225, 165), 2)
                        cv2.putText(
                            frame,
                            f"Review track {track}",
                            (a[0], max(20, a[1] - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (125, 225, 165),
                            2,
                        )
                cv2.putText(
                    frame,
                    f"{t:.2f}s",
                    (12, size[1] - 16),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (240, 240, 240),
                    1,
                )
                writer.write(frame)
                frame_index += 1
            writer.release()
            writer = None
            if not frame_index:
                raise ValueError("No frames in review interval")
            return extract_clip(raw, dest, 0, frame_index / fps)
    finally:
        cap.release()
        if writer is not None:
            writer.release()
