# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""High-level encode entry points.

Each function in this module produces a new output file:

- :func:`trim_to_video` — MP4 / MP3 from a trim range, with text layers,
  image overlays, color grade, speed change, rotate, crop, etc.
- :func:`trim_to_gif` — GIF via the ``palettegen`` + ``paletteuse`` two
  pass (better color than single-pass gif encoding).
- :func:`frames_to_video` / :func:`frames_to_gif` — turn a directory
  of PNG frames into a video / GIF. Used by the screen-record flow.

The actual filter-graph construction lives in :mod:`filters`; this
module's job is just to wire filters + options into an ffmpeg argv and
manage the subprocess lifecycle (progress parsing, cancellation, exit
codes).
"""

import subprocess
import tempfile
from pathlib import Path

from videokidnapper.config import PRESETS
from videokidnapper.core.ffmpeg._internals import (
    _encoder_quality_args, _get_ffmpeg, _log_ffmpeg_failure,
    _parse_progress, _run_kwargs, pick_video_encoder,
)
from videokidnapper.core.ffmpeg.filters import (
    _assemble_video_filters, _build_audio_speed,
    _build_image_overlay_chain, _build_scale_filter,
)
from videokidnapper.core.ffmpeg.probe import get_video_info


# ---------------------------------------------------------------------------
# Trim entry points — the app's primary export paths
# ---------------------------------------------------------------------------

def trim_to_video(input_path, start, end, preset_name, output_path,
                  text_layers=None, image_layers=None,
                  progress_callback=None, cancel_event=None,
                  options=None):
    preset = PRESETS[preset_name]
    duration = max(0.001, end - start)
    info = get_video_info(input_path)
    options = options or {}

    audio_only = bool(options.get("audio_only"))
    mute_audio = bool(options.get("mute"))
    speed = options.get("speed", 1.0)

    if audio_only:
        cmd = [
            _get_ffmpeg(), "-y",
            "-ss", str(start),
            "-i", str(input_path),
            "-t", str(duration),
            "-vn",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
        ]
        audio_tempo = _build_audio_speed(speed)
        if audio_tempo:
            cmd += ["-filter:a", audio_tempo]
        cmd += [str(output_path)]
        process = subprocess.Popen(
            cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
            **_run_kwargs(),
        )
        tail = _parse_progress(process, duration, progress_callback, cancel_event)
        process.wait()
        if process.returncode != 0:
            _log_ffmpeg_failure(cmd, process.returncode, tail)
            return None
        return output_path

    filters = _assemble_video_filters(preset_name, info, text_layers, options)

    # If there are image overlays we switch from -vf to -filter_complex
    # and add one -i per image. The existing video filter chain becomes
    # the first stage; the overlay chain composes on top of its output.
    valid_images = [L for L in (image_layers or []) if (L or {}).get("path")]

    encoder = pick_video_encoder(options.get("hw_encoder", "auto"))
    cmd = [
        _get_ffmpeg(), "-y",
        "-ss", str(start),
        "-i", str(input_path),
    ]
    # Image overlay inputs land after the main video input. They're NOT
    # -ss'd because PNGs don't have a timeline — ffmpeg loops them and
    # the per-layer enable='between(t,...)' handles when they show.
    for img_path in (L["path"] for L in valid_images):
        cmd += ["-loop", "1", "-i", str(img_path)]

    cmd += [
        "-t", str(duration),
        "-r", str(preset["fps"]),
        "-c:v", encoder,
    ]
    cmd += _encoder_quality_args(encoder, preset["video_crf"])

    if mute_audio or not info.get("has_audio"):
        cmd += ["-an"]
    else:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
        audio_tempo = _build_audio_speed(speed)
        if audio_tempo:
            cmd += ["-filter:a", audio_tempo]

    if valid_images:
        # filter_complex path: pipe the video chain into a labelled
        # output, then overlay each image on top.
        base_chain = ",".join(filters) if filters else "null"
        overlay_chain, final_label, _inputs = _build_image_overlay_chain(
            valid_images, base_label="vbase", video_dur=duration,
        )
        fc = f"[0:v]{base_chain}[vbase];{overlay_chain}"
        cmd += [
            "-filter_complex", fc,
            "-map", f"[{final_label}]",
        ]
        # Explicitly map audio from input 0 (optional — ``?`` lets
        # ffmpeg skip when the source has no audio).
        cmd += ["-map", "0:a?"]
    elif filters:
        cmd += ["-vf", ",".join(filters)]
    cmd += ["-movflags", "+faststart", str(output_path)]

    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        **_run_kwargs(),
    )
    tail = _parse_progress(process, duration, progress_callback, cancel_event)
    process.wait()
    if process.returncode != 0:
        _log_ffmpeg_failure(cmd, process.returncode, tail)
        return None
    return output_path


def trim_to_gif(input_path, start, end, preset_name, output_path,
                text_layers=None, progress_callback=None, cancel_event=None,
                options=None):
    preset = PRESETS[preset_name]
    duration = max(0.001, end - start)
    info = get_video_info(input_path)
    options = options or {}

    palette_path = Path(tempfile.mktemp(suffix=".png"))

    filters = [f"fps={preset['fps']}"]
    filters.extend(_assemble_video_filters(preset_name, info, text_layers, options))
    filter_str = ",".join(filters)

    cmd1 = [
        _get_ffmpeg(), "-y",
        "-ss", str(start),
        "-i", str(input_path),
        "-t", str(duration),
        "-vf", f"{filter_str},palettegen=max_colors={preset['gif_colors']}",
        str(palette_path),
    ]
    subprocess.run(cmd1, capture_output=True, timeout=180, **_run_kwargs())

    if cancel_event and cancel_event.is_set():
        palette_path.unlink(missing_ok=True)
        return None

    if progress_callback:
        progress_callback(0.3)

    cmd2 = [
        _get_ffmpeg(), "-y",
        "-ss", str(start),
        "-i", str(input_path),
        "-i", str(palette_path),
        "-t", str(duration),
        "-lavfi", f"{filter_str} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
        "-loop", "0",
        str(output_path),
    ]
    process = subprocess.Popen(
        cmd2, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        **_run_kwargs(),
    )

    def gif_progress(p):
        if progress_callback:
            progress_callback(0.3 + p * 0.7)

    tail = _parse_progress(process, duration, gif_progress, cancel_event)
    process.wait()
    palette_path.unlink(missing_ok=True)
    if process.returncode != 0:
        _log_ffmpeg_failure(cmd2, process.returncode, tail)
        return None
    return output_path


# ---------------------------------------------------------------------------
# Frame-directory helpers (screen-record export path)
# ---------------------------------------------------------------------------

def frames_to_video(frame_dir, fps, preset_name, output_path,
                    progress_callback=None, cancel_event=None):
    preset = PRESETS[preset_name]
    frame_dir = Path(frame_dir)
    frames = sorted(frame_dir.glob("frame_*.png"))
    if not frames:
        return None

    duration = len(frames) / fps

    filters = []
    scale = _build_scale_filter(preset_name)
    if scale:
        filters.append(scale)

    cmd = [
        _get_ffmpeg(), "-y",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%06d.png"),
        "-r", str(preset["fps"]),
        "-c:v", "libx264",
        "-crf", str(preset["video_crf"]),
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
    ]
    if filters:
        cmd += ["-vf", ",".join(filters)]
    cmd += ["-movflags", "+faststart", str(output_path)]

    process = subprocess.Popen(
        cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        **_run_kwargs(),
    )
    tail = _parse_progress(process, duration, progress_callback, cancel_event)
    process.wait()
    if process.returncode != 0:
        _log_ffmpeg_failure(cmd, process.returncode, tail)
        return None
    return output_path


def frames_to_gif(frame_dir, fps, preset_name, output_path,
                  progress_callback=None, cancel_event=None):
    preset = PRESETS[preset_name]
    frame_dir = Path(frame_dir)
    frames = sorted(frame_dir.glob("frame_*.png"))
    if not frames:
        return None

    duration = len(frames) / fps
    palette_path = Path(tempfile.mktemp(suffix=".png"))

    filters = [f"fps={preset['fps']}"]
    scale = _build_scale_filter(preset_name)
    if scale:
        filters.append(scale)
    filter_str = ",".join(filters)

    cmd1 = [
        _get_ffmpeg(), "-y",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%06d.png"),
        "-vf", f"{filter_str},palettegen=max_colors={preset['gif_colors']}",
        str(palette_path),
    ]
    subprocess.run(cmd1, capture_output=True, timeout=180, **_run_kwargs())

    if cancel_event and cancel_event.is_set():
        palette_path.unlink(missing_ok=True)
        return None

    if progress_callback:
        progress_callback(0.3)

    cmd2 = [
        _get_ffmpeg(), "-y",
        "-framerate", str(fps),
        "-i", str(frame_dir / "frame_%06d.png"),
        "-i", str(palette_path),
        "-lavfi", f"{filter_str} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
        "-loop", "0",
        str(output_path),
    ]
    process = subprocess.Popen(
        cmd2, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True,
        **_run_kwargs(),
    )

    def gif_progress(p):
        if progress_callback:
            progress_callback(0.3 + p * 0.7)

    tail = _parse_progress(process, duration, gif_progress, cancel_event)
    process.wait()
    palette_path.unlink(missing_ok=True)
    if process.returncode != 0:
        _log_ffmpeg_failure(cmd2, process.returncode, tail)
        return None
    return output_path
