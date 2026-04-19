# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Read-only queries against media files: metadata, single frames, waveform.

Nothing in here emits a new video — everything just extracts
information from an existing file. Keeps the encode path (``encode.py``)
free of ffprobe plumbing.
"""

import json
import subprocess

from videokidnapper.core.ffmpeg._internals import (
    _get_ffmpeg, _get_ffprobe, _run_kwargs,
)


class ProbeError(RuntimeError):
    """ffprobe failed to read the file (missing binary, bad media, timeout)."""


def get_video_info(input_path):
    """Return a metadata dict for ``input_path``.

    Raises :class:`ProbeError` with a user-facing message when ffprobe
    can't read the file — callers (TrimTab._load_path, CLI) already
    catch the old generic-Exception path, so this is wire-compatible
    while giving the error funnel something actionable to surface.
    """
    cmd = [
        _get_ffprobe(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    # A corrupt file / missing codec / killed process used to land here
    # as a naked JSONDecodeError and propagate to the Tk event loop. Wrap
    # every failure mode in ProbeError with a short, human-readable reason.
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
    except FileNotFoundError as exc:
        raise ProbeError(f"ffprobe not found on PATH: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(
            f"ffprobe timed out after 10s reading {input_path!r}",
        ) from exc
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-1:] or ["(no stderr)"]
        raise ProbeError(
            f"ffprobe exited {result.returncode}: {tail[0]}",
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(
            f"ffprobe returned non-JSON output for {input_path!r}: {exc}",
        ) from exc
    video_stream = None
    audio_stream = None
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and video_stream is None:
            video_stream = s
        elif s.get("codec_type") == "audio" and audio_stream is None:
            audio_stream = s
    duration = float(data.get("format", {}).get("duration", 0))
    width = int(video_stream.get("width", 0)) if video_stream else 0
    height = int(video_stream.get("height", 0)) if video_stream else 0
    fps_str = video_stream.get("r_frame_rate", "30/1") if video_stream else "30/1"
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        fps = 30.0
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "fps": fps,
        "has_audio": audio_stream is not None,
    }


def extract_frame(input_path, timestamp_seconds):
    """Pull a single PNG-encoded frame at ``timestamp_seconds``.

    Used by the preview cache and thumbnail strip. Returns a PIL
    ``Image`` or ``None`` on failure. No exception on missing frames —
    the caller just shows a placeholder.
    """
    from PIL import Image
    import io

    cmd = [
        _get_ffmpeg(),
        "-ss", str(timestamp_seconds),
        "-i", str(input_path),
        "-vframes", "1",
        "-f", "image2pipe",
        "-vcodec", "png",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=10, **_run_kwargs())
    if result.returncode != 0 or not result.stdout:
        return None
    return Image.open(io.BytesIO(result.stdout))


def extract_waveform(input_path, buckets=400, duration=None):
    """Return a list of ``buckets`` RMS amplitudes in [0, 1].

    Streams mono s16le PCM from ffmpeg at 4 kHz, then buckets by window.
    Empty list if the file has no audio or ffmpeg fails.
    """
    try:
        info = get_video_info(input_path)
    except Exception:
        return []
    if not info.get("has_audio"):
        return []
    duration = duration or info["duration"]
    if duration <= 0:
        return []

    sample_rate = 4000
    cmd = [
        _get_ffmpeg(),
        "-i", str(input_path),
        "-ac", "1",
        "-ar", str(sample_rate),
        "-f", "s16le",
        "-loglevel", "error",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60, **_run_kwargs())
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout:
        return []

    import struct
    raw = result.stdout
    total_samples = len(raw) // 2
    if total_samples < buckets:
        return []

    samples = struct.unpack(f"<{total_samples}h", raw)
    window = total_samples // buckets
    peaks = []
    for i in range(buckets):
        chunk = samples[i * window:(i + 1) * window]
        if not chunk:
            peaks.append(0.0)
            continue
        peak = max(abs(s) for s in chunk) / 32767.0
        peaks.append(min(1.0, peak))
    return peaks
