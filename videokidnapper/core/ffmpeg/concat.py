# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Joining multiple clips into one output.

Two public entry points:

- :func:`concat_clips` — lossless ``-c copy`` via ffmpeg's concat
  demuxer. Fast; requires every input to share codec + resolution + fps
  (which our trim pipeline guarantees).
- :func:`concat_clips_with_transition` — drop-in super-set. Delegates
  to :func:`concat_clips` when ``transition="cut"`` (keeps the lossless
  path); otherwise re-encodes via ``filter_complex`` using ``xfade`` for
  video + chained ``acrossfade`` for audio.

The ``xfade`` offset math is cumulative across N clips so a 5-clip
crossfade lines up perfectly: transition k starts at
``sum(durations[0..k-1]) - k * transition_duration``.
"""

import subprocess
import tempfile
from pathlib import Path

from videokidnapper.core.ffmpeg._internals import (
    _encoder_quality_args, _get_ffmpeg, _get_ffprobe,
    _run_kwargs, pick_video_encoder,
)
from videokidnapper.core.ffmpeg.probe import get_video_info


# Supported transition kinds for ``concat_clips_with_transition``:
#   - "cut"       : no transition (lossless concat demuxer path)
#   - "fade"      : fade-to-black between clips (xfade transition=fade)
#   - "crossfade" : dissolve blend (xfade transition=dissolve)
#   - "fadeblack" : alias for "fade", explicit in the UI for clarity
#   - "fadewhite" : fade through white between clips
CONCAT_TRANSITIONS = ("cut", "fade", "fadeblack", "fadewhite", "crossfade")


def _xfade_transition_name(kind):
    """Map our UI name to the ffmpeg ``xfade=transition=`` value."""
    return {
        "fade":       "fade",
        "fadeblack":  "fadeblack",
        "fadewhite":  "fadewhite",
        "crossfade":  "dissolve",
    }.get(kind, "fade")


def _probe_clip_duration(path):
    """Return the duration in seconds of an already-encoded clip.

    Uses ffprobe with a short timeout. Falls back to 0.0 on any error —
    callers should treat 0.0 as "unknown, skip transitions to this clip".
    """
    try:
        result = subprocess.run(
            [
                _get_ffprobe(), "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nokey=1:noprint_wrappers=1",
                str(path),
            ],
            capture_output=True, text=True, timeout=10,
            **_run_kwargs(),
        )
        if result.returncode != 0:
            return 0.0
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return 0.0


def _build_xfade_filter_complex(
    durations, has_audio, transition="fade", duration=0.5,
):
    """Build the ``-filter_complex`` string that joins N clips with transitions.

    xfade requires all inputs share codec / resolution / framerate — which
    our trim pipeline guarantees because every queued clip flows through
    the same preset. The offset for each transition is measured on the
    combined output timeline:

        transition k (between clip k-1 and clip k) starts at
        sum(durations[0..k-1]) - k * transition_duration

    Audio uses ``acrossfade`` chained pairwise. When ``has_audio`` is
    False we emit video-only chains and the caller passes ``-an``.
    """
    n = len(durations)
    if n < 2:
        return "", None, None
    t = max(0.05, float(duration))
    ffmpeg_kind = _xfade_transition_name(transition)

    parts = []
    last_v = "0:v"
    cumulative = 0.0
    for i in range(1, n):
        cumulative += durations[i - 1]
        offset = max(0.0, cumulative - i * t)
        out = f"v{i}" if i < n - 1 else "vout"
        parts.append(
            f"[{last_v}][{i}:v]xfade=transition={ffmpeg_kind}"
            f":duration={t:.3f}:offset={offset:.3f}[{out}]"
        )
        last_v = out

    if has_audio:
        last_a = "0:a"
        for i in range(1, n):
            out = f"a{i}" if i < n - 1 else "aout"
            parts.append(
                f"[{last_a}][{i}:a]acrossfade=d={t:.3f}[{out}]"
            )
            last_a = out

    filter_complex = ";".join(parts)
    v_map = "[vout]"
    a_map = "[aout]" if has_audio else None
    return filter_complex, v_map, a_map


def concat_clips_with_transition(
    input_paths, output_path, transition="cut", duration=0.5,
    progress_callback=None, cancel_event=None,
):
    """Concatenate ``input_paths`` using the requested transition kind.

    ``transition="cut"`` → delegates to the existing lossless concat
    demuxer (``-c copy``). Any other value re-encodes via filter_complex
    with xfade + acrossfade. The re-encode path is slower but unavoidable
    — xfade needs decoded frames to blend.
    """
    if transition not in CONCAT_TRANSITIONS:
        transition = "cut"
    if transition == "cut" or len(input_paths) < 2:
        return concat_clips(
            input_paths, output_path,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    durations = [_probe_clip_duration(p) for p in input_paths]
    if any(d <= 0 for d in durations):
        # One or more clips failed probe — safer to fall back to the
        # lossless cut path than emit a filter-graph that ffmpeg rejects.
        return concat_clips(
            input_paths, output_path,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    # Any clip shorter than the transition can't sustain it — clamp the
    # effective transition duration to half the shortest clip.
    min_dur = min(durations)
    t = max(0.05, min(float(duration), min_dur / 2 - 0.01))

    # Assume audio presence from the first clip (they all share the same
    # source pipeline so this matches the other clips in practice).
    first_info = {}
    try:
        first_info = get_video_info(input_paths[0])
    except Exception:
        first_info = {}
    has_audio = bool(first_info.get("has_audio"))

    filter_complex, v_map, a_map = _build_xfade_filter_complex(
        durations, has_audio, transition=transition, duration=t,
    )
    if not filter_complex:
        return concat_clips(
            input_paths, output_path,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )

    encoder = pick_video_encoder("auto")
    q_args = _encoder_quality_args(encoder, 20)

    cmd = [_get_ffmpeg(), "-y", "-hide_banner", "-loglevel", "error"]
    for p in input_paths:
        cmd += ["-i", str(p)]
    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", v_map]
    if has_audio:
        cmd += ["-map", a_map, "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", encoder, *q_args, "-movflags", "+faststart", str(output_path)]

    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        **_run_kwargs(),
    )
    while process.poll() is None:
        if cancel_event and cancel_event.is_set():
            process.kill()
            return None
        if progress_callback:
            progress_callback(0.5)
    if progress_callback:
        progress_callback(1.0)
    return output_path if process.returncode == 0 else None


def concat_clips(input_paths, output_path, progress_callback=None, cancel_event=None):
    """Losslessly concatenate `input_paths` using ffmpeg's concat demuxer.

    Only works when every input shares the same codec, resolution, and fps —
    which our trim pipeline guarantees because all clips flow through the
    same preset. If that ever stops being true, switch to the concat filter
    (re-encode path) and drop the ``-c copy``.
    """
    if not input_paths:
        return None
    list_path = Path(tempfile.mktemp(suffix=".txt"))
    try:
        with open(list_path, "w", encoding="utf-8") as fh:
            for p in input_paths:
                # ffmpeg's concat demuxer needs single-quoted paths with any
                # embedded single quotes escaped.
                safe = str(p).replace("\\", "/").replace("'", r"'\''")
                fh.write(f"file '{safe}'\n")

        cmd = [
            _get_ffmpeg(), "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        process = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
            **_run_kwargs(),
        )
        # No accurate progress for copy-only concat — just poll completion.
        while process.poll() is None:
            if cancel_event and cancel_event.is_set():
                process.kill()
                return None
            if progress_callback:
                progress_callback(0.5)
        if progress_callback:
            progress_callback(1.0)
        return output_path if process.returncode == 0 else None
    finally:
        list_path.unlink(missing_ok=True)
