# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Cross-module private helpers shared by the ffmpeg subpackage.

- Binary resolution + cached paths (``_get_ffmpeg``, ``_get_ffprobe``).
- Windows ``Popen`` flags to hide the console window.
- Hardware encoder detection (``pick_video_encoder``) + quality args.
- Progress-stream parser and failure logger.

These are kept in one small file rather than scattered across modules
so every other submodule has exactly one import-site for "how do I
actually run ffmpeg". The previous ffmpeg_backend.py mixed these with
public API in a 1200-line wall of text.
"""

import os
import re
import subprocess
import sys
from collections import deque

from videokidnapper.utils.ffmpeg_check import find_ffmpeg, find_ffprobe


# Module-level caches — lazy so import time stays cheap.
_ffmpeg = None
_ffprobe = None
_hw_encoders_cache = None


# Priority list: NVENC first (fastest on NVIDIA), then QSV (Intel),
# VideoToolbox (macOS), AMF (AMD). libx264 is the universal fallback.
_HW_H264_ENCODERS = ["h264_nvenc", "h264_qsv", "h264_videotoolbox", "h264_amf"]


# ---------------------------------------------------------------------------
# Binary paths
# ---------------------------------------------------------------------------

def _get_ffmpeg():
    global _ffmpeg
    if _ffmpeg is None:
        _ffmpeg = str(find_ffmpeg())
    return _ffmpeg


def _get_ffprobe():
    global _ffprobe
    if _ffprobe is None:
        _ffprobe = str(find_ffprobe())
    return _ffprobe


def _run_kwargs():
    """Hide the console window on Windows when we Popen ffmpeg."""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# ---------------------------------------------------------------------------
# Hardware encoder detection
# ---------------------------------------------------------------------------

def _probe_encoder(encoder):
    """Try a 0.1s dummy encode to confirm the encoder works on this hardware.

    Listing in ``ffmpeg -encoders`` means the binary was *built* with support
    — it does not mean the runtime can use it. NVENC, for example, shows up
    on any ffmpeg build with NVIDIA's SDK linked in, but fails at encoder
    init with ``CUDA_ERROR_NO_DEVICE`` on machines without an NVIDIA GPU.
    """
    try:
        cmd = [
            _get_ffmpeg(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=black:s=64x36:d=0.1:r=10",
            "-c:v", encoder,
            "-f", "null", "-",
        ]
        result = subprocess.run(
            cmd, capture_output=True, timeout=6, **_run_kwargs(),
        )
        return result.returncode == 0
    except Exception:
        return False


def detect_hardware_encoders():
    """Return the list of H.264 HW encoders that are ACTUALLY usable here."""
    global _hw_encoders_cache
    if _hw_encoders_cache is not None:
        return _hw_encoders_cache
    try:
        result = subprocess.run(
            [_get_ffmpeg(), "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=8,
        )
        out = result.stdout + result.stderr
    except Exception:
        out = ""
    listed = [enc for enc in _HW_H264_ENCODERS if enc in out]
    working = [enc for enc in listed if _probe_encoder(enc)]
    _hw_encoders_cache = working
    return working


def pick_video_encoder(preference="auto"):
    """Decide which encoder to pass to ``-c:v``.

    ``preference``:
      - ``"off"`` → always libx264
      - ``"auto"`` → first available HW encoder, or libx264
      - any other string → that encoder, if detected; else libx264
    """
    if preference == "off":
        return "libx264"
    encoders = detect_hardware_encoders()
    if preference == "auto":
        return encoders[0] if encoders else "libx264"
    if preference in encoders:
        return preference
    return "libx264"


def _encoder_quality_args(encoder, crf):
    """Map a CRF target to the right quality flag for the chosen encoder."""
    if encoder == "libx264":
        return ["-crf", str(crf), "-preset", "medium"]
    if encoder in ("h264_nvenc", "h264_amf"):
        # NVENC/AMF use `-cq` for constant quality; scale roughly 1:1 with CRF.
        return ["-cq", str(crf), "-preset", "p4"] if encoder == "h264_nvenc" \
               else ["-quality", "balanced"]
    if encoder == "h264_qsv":
        return ["-global_quality", str(crf), "-preset", "medium"]
    if encoder == "h264_videotoolbox":
        # VT doesn't take CRF; approximate via quality 0-100 (higher = better).
        q = max(10, min(100, 100 - crf * 2))
        return ["-q:v", str(q)]
    return ["-crf", str(crf)]


# ---------------------------------------------------------------------------
# Progress parsing + failure logging
# ---------------------------------------------------------------------------

_PROGRESS_RE = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")


def _parse_progress(process, duration, callback, cancel_event):
    """Stream ffmpeg's stderr, tracking progress and buffering diagnostic lines.

    Returns the tail of non-progress stderr output so callers can surface
    the actual error message when the process exits non-zero.
    """
    tail = deque(maxlen=40)
    for line in iter(process.stderr.readline, ""):
        stripped = line.rstrip()
        if cancel_event and cancel_event.is_set():
            process.kill()
            return "\n".join(tail)
        match = _PROGRESS_RE.search(stripped)
        if match and callback and duration > 0:
            h, m, s, cs = (int(match.group(i)) for i in (1, 2, 3, 4))
            current = h * 3600 + m * 60 + s + cs / 100
            callback(min(current / duration, 1.0))
        elif stripped:
            tail.append(stripped)
    return "\n".join(tail)


def _log_ffmpeg_failure(cmd, returncode, stderr_tail):
    """Print ffmpeg's actual error to stderr (which the Debug tab captures)."""
    try:
        print(f"ffmpeg failed (rc={returncode})", file=sys.stderr)
        # Only the last portion of the command — full argv can be huge with filters.
        short_cmd = " ".join(str(a) for a in cmd[:3]) + "  [...]  " + str(cmd[-1])
        print(f"  cmd: {short_cmd}", file=sys.stderr)
        if stderr_tail:
            for line in stderr_tail.splitlines()[-12:]:
                print(f"  {line}", file=sys.stderr)
    except Exception:
        pass
