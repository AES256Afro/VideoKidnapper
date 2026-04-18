"""Screen-recorder using `mss` for fast cross-platform capture.

Frames are written as PNGs into a temp folder and then stitched into an
MP4 by `ffmpeg_backend.frames_to_video`. Recording happens on a daemon
thread so the UI stays responsive; the caller passes a `cancel_event`
and a `progress_callback(elapsed_seconds)` if it wants live status.
"""

import threading
import time
import uuid
from pathlib import Path


def _get_mss():
    import mss  # imported lazily so unit tests without mss still work
    return mss


def available_displays():
    """Return list of dicts describing each monitor (mss-style)."""
    try:
        with _get_mss().mss() as sct:
            return list(sct.monitors)
    except Exception:
        return []


def record_screen(
    duration_seconds,
    fps=15,
    region=None,
    cancel_event=None,
    progress_callback=None,
    temp_base=None,
):
    """Capture screen frames to a temp PNG sequence; return the folder path.

    ``region`` is either None (primary monitor), or a dict ``{"left", "top",
    "width", "height"}`` — same shape mss expects.
    """
    from videokidnapper.config import TEMP_DIR

    base = Path(temp_base or TEMP_DIR) / f"record_{uuid.uuid4().hex[:8]}"
    base.mkdir(parents=True, exist_ok=True)
    cancel_event = cancel_event or threading.Event()

    interval = 1.0 / max(1, fps)
    start = time.time()
    frame_idx = 0

    mss_mod = _get_mss()
    with mss_mod.mss() as sct:
        target = region or sct.monitors[1]
        while not cancel_event.is_set():
            elapsed = time.time() - start
            if elapsed >= duration_seconds:
                break

            shot = sct.grab(target)
            frame_path = base / f"frame_{frame_idx:06d}.png"
            mss_mod.tools.to_png(shot.rgb, shot.size, output=str(frame_path))
            frame_idx += 1

            if progress_callback:
                progress_callback(elapsed)

            next_tick = start + frame_idx * interval
            sleep_for = next_tick - time.time()
            if sleep_for > 0:
                time.sleep(sleep_for)

    return base, fps, frame_idx
