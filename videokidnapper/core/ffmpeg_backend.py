# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

from videokidnapper.config import PRESETS
from videokidnapper.utils.ffmpeg_check import find_ffmpeg, find_ffprobe
from videokidnapper.utils.ffmpeg_escape import escape_drawtext_value, escape_path

_ffmpeg = None
_ffprobe = None
_hw_encoders_cache = None


# ---------------------------------------------------------------------------
# Hardware encoder detection
# ---------------------------------------------------------------------------

# Priority list: try NVENC first (fastest on NVIDIA), then QSV (Intel), then
# VideoToolbox (macOS), then AMF (AMD). Fall back to libx264 if none found.
_HW_H264_ENCODERS = ["h264_nvenc", "h264_qsv", "h264_videotoolbox", "h264_amf"]


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


def get_video_info(input_path):
    cmd = [
        _get_ffprobe(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    data = json.loads(result.stdout)
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


# ---------------------------------------------------------------------------
# Filter construction
# ---------------------------------------------------------------------------

def _build_scale_filter(preset_name, input_width=None):
    preset = PRESETS[preset_name]
    target_width = preset["width"]
    if target_width is None or (input_width and input_width <= target_width):
        return None
    return f"scale={target_width}:-2"


def _build_crop_filter(crop, info):
    """`crop` is a dict with `x`, `y`, `w`, `h` in source pixels.

    Returns ``None`` when the crop is absent or invalid — including rects
    that don't fit inside the video. Stale crops (e.g. set on a previous
    video with different dimensions) would otherwise crash ffmpeg.
    """
    if not crop:
        return None
    vw = int(info.get("width", 0))
    vh = int(info.get("height", 0))
    if vw < 2 or vh < 2:
        return None
    w = int(max(2, min(crop.get("w", vw), vw)))
    h = int(max(2, min(crop.get("h", vh), vh)))
    x = int(max(0, min(crop.get("x", 0), vw - w)))
    y = int(max(0, min(crop.get("y", 0), vh - h)))
    if w < 2 or h < 2:
        return None
    return f"crop={w}:{h}:{x}:{y}"


def _build_rotate_filter(rotate):
    rotate = int(rotate or 0) % 360
    if rotate == 90:
        return "transpose=1"
    if rotate == 180:
        return "transpose=1,transpose=1"
    if rotate == 270:
        return "transpose=2"
    return None


def _build_speed_filter(speed):
    """Video-side setpts for speed change; see `_build_audio_speed` for audio."""
    try:
        speed = float(speed or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    if abs(speed - 1.0) < 0.001:
        return None
    pts_ratio = 1.0 / speed
    return f"setpts={pts_ratio:.4f}*PTS"


def _build_audio_speed(speed):
    """Audio atempo supports 0.5–2.0; chain it for more extreme values."""
    try:
        speed = float(speed or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    if abs(speed - 1.0) < 0.001:
        return None
    stages = []
    remaining = speed
    while remaining > 2.0:
        stages.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        stages.append("atempo=0.5")
        remaining /= 0.5
    stages.append(f"atempo={remaining:.4f}")
    return ",".join(stages)


def _fade_alpha_expr(start, end, fade):
    """Build a drawtext ``alpha=`` expression with a symmetric fade in/out.

    Returns ``None`` if fade <= 0, letting the caller keep drawtext simple.
    """
    if fade <= 0:
        return None
    # Clamp so the fade never consumes the whole window.
    f = min(fade, max(0.01, (end - start) / 2 - 0.01))
    return (
        f"'if(lt(t\\,{start})\\,0\\,"
        f"if(lt(t\\,{start + f})\\,(t-{start})/{f}\\,"
        f"if(lt(t\\,{end - f})\\,1\\,"
        f"if(lt(t\\,{end})\\,({end}-t)/{f}\\,0))))'"
    )


def _build_drawtext_filter(layer, fade=0.0):
    from videokidnapper.ui.text_layers import _find_font_path

    text = escape_drawtext_value(layer.get("text", ""))
    font_path = escape_path(_find_font_path(layer.get("font", "Arial")))
    fontsize = int(layer.get("fontsize", 24))
    fontcolor = layer.get("fontcolor", "white")
    pos_expr = layer.get("position", "(w-tw)/2:h-th-20")
    x_expr, y_expr = pos_expr.split(":", 1)
    start_t = float(layer.get("start", 0))
    end_t = float(layer.get("end", 999999))
    layer_fade = float(layer.get("fade", fade) or 0.0)

    parts = [
        f"drawtext=text='{text}'",
        f"fontfile='{font_path}'",
        f"fontsize={fontsize}",
        f"fontcolor={fontcolor}",
        f"x={x_expr}",
        f"y={y_expr}",
        f"enable='between(t\\,{start_t}\\,{end_t})'",
    ]

    alpha = _fade_alpha_expr(start_t, end_t, layer_fade)
    if alpha:
        parts.append(f"alpha={alpha}")

    if layer.get("box"):
        boxcolor = layer.get("boxcolor", "black@0.6")
        boxborderw = int(layer.get("boxborderw", 8))
        parts.append("box=1")
        parts.append(f"boxcolor={boxcolor}")
        parts.append(f"boxborderw={boxborderw}")

    return ":".join(parts)


def _build_text_filters(text_layers, fade=0.0):
    if not text_layers:
        return []
    return [_build_drawtext_filter(layer, fade=fade)
            for layer in text_layers if layer.get("text", "").strip()]


def _assemble_video_filters(preset_name, info, text_layers, options):
    """Build the video filter chain in the right order.

    Order: (aspect-crop) → crop → rotate → speed → drawtext → scale.

    ``drawtext`` MUST come before ``scale`` so fontsize and x/y are
    interpreted in source-frame pixels — that's what the UI preview uses,
    so exports match 1:1. If ``scale`` came first (the old order), then on
    a 1920×1080 source with Medium preset (→720-wide), a custom position
    of ``x=960:y=540`` would land at pixel 960 of a 720-wide frame and
    overshoot the right edge.
    """
    filters = []
    options = options or {}

    # Aspect preset is a second crop; `_build_aspect_crop` itself defers
    # to any explicit crop, so putting aspect first is harmless.
    aspect = options.get("aspect_preset")
    if aspect and aspect != "Source":
        f = _build_aspect_crop(aspect, info, options.get("crop"))
        if f:
            filters.append(f)

    f = _build_crop_filter(options.get("crop"), info)
    if f:
        filters.append(f)

    f = _build_rotate_filter(options.get("rotate"))
    if f:
        filters.append(f)

    f = _build_speed_filter(options.get("speed"))
    if f:
        filters.append(f)

    # Drawtext at source-coord resolution — matches the preview exactly.
    filters.extend(_build_text_filters(text_layers, fade=options.get("text_fade", 0.0)))

    # Scale LAST so text and frame are resized together.
    f = _build_scale_filter(preset_name, info["width"])
    if f:
        filters.append(f)

    return filters


def _build_aspect_crop(preset, info, explicit_crop):
    """Center-crop to a target aspect ratio like '1:1', '9:16', '16:9', '4:5', '3:4'.

    If the user has already defined an explicit crop rect we defer to that —
    aspect presets are just a convenience on top of no crop.
    """
    if explicit_crop:
        return None
    try:
        a, b = preset.split(":")
        target = float(a) / float(b)
    except (ValueError, ZeroDivisionError, AttributeError):
        return None
    sw, sh = info.get("width", 0), info.get("height", 0)
    if sw <= 0 or sh <= 0:
        return None
    src_ratio = sw / sh
    if abs(src_ratio - target) < 0.001:
        return None
    if src_ratio > target:
        new_w = int(sh * target)
        new_h = sh
        x = (sw - new_w) // 2
        y = 0
    else:
        new_w = sw
        new_h = int(sw / target)
        x = 0
        y = (sh - new_h) // 2
    return f"crop={max(2, new_w)}:{max(2, new_h)}:{max(0, x)}:{max(0, y)}"


# ---------------------------------------------------------------------------
# Progress parsing
# ---------------------------------------------------------------------------

def _parse_progress(process, duration, callback, cancel_event):
    """Stream ffmpeg's stderr, tracking progress and buffering diagnostic lines.

    Returns the tail of non-progress stderr output so callers can surface
    the actual error message when the process exits non-zero.
    """
    pattern = re.compile(r"time=(\d+):(\d+):(\d+)\.(\d+)")
    tail = deque(maxlen=40)
    for line in iter(process.stderr.readline, ""):
        stripped = line.rstrip()
        if cancel_event and cancel_event.is_set():
            process.kill()
            return "\n".join(tail)
        match = pattern.search(stripped)
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


# ---------------------------------------------------------------------------
# Public trim entry points
# ---------------------------------------------------------------------------

def trim_to_video(input_path, start, end, preset_name, output_path,
                  text_layers=None, progress_callback=None, cancel_event=None,
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

    encoder = pick_video_encoder(options.get("hw_encoder", "auto"))
    cmd = [
        _get_ffmpeg(), "-y",
        "-ss", str(start),
        "-i", str(input_path),
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
# Concat demuxer — joins N clips into one output
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Waveform extraction
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Frame-dir helpers (unchanged API, kept for screen-record flows)
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
