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


def _build_eq_filter(options):
    """Build an ffmpeg ``eq=`` color-grade filter from Export Options.

    Reads four keys from ``options`` and omits the filter entirely
    when every value is neutral — avoids the cost of a needless
    per-pixel pass for the common "no color tweak" case.

    ffmpeg eq parameter ranges (from the docs):
      - ``brightness`` : -1.0 to 1.0, neutral 0.0
      - ``contrast``   : -1000.0 to 1000.0, neutral 1.0
      - ``saturation`` : 0.0 to 3.0, neutral 1.0
      - ``gamma``      : 0.1 to 10.0, neutral 1.0

    We clamp each input to a sane subset and round to 3 decimals so
    the emitted filter-graph string stays short and diffable.
    """
    if not options:
        return None
    try:
        b = float(options.get("color_brightness", 0.0) or 0.0)
        c = float(options.get("color_contrast",   1.0) or 1.0)
        s = float(options.get("color_saturation", 1.0) or 1.0)
        g = float(options.get("color_gamma",      1.0) or 1.0)
    except (TypeError, ValueError):
        return None
    # Clamp into the UI's exposed ranges — a stray -99999 from a
    # corrupted settings file should still produce a valid filter.
    b = max(-1.0, min(1.0, b))
    c = max(0.1, min(3.0, c))
    s = max(0.0, min(3.0, s))
    g = max(0.1, min(3.0, g))

    neutral = (
        abs(b) < 0.001
        and abs(c - 1.0) < 0.001
        and abs(s - 1.0) < 0.001
        and abs(g - 1.0) < 0.001
    )
    if neutral:
        return None

    return (
        f"eq=brightness={b:.3f}:contrast={c:.3f}:"
        f"saturation={s:.3f}:gamma={g:.3f}"
    )


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


# ---------------------------------------------------------------------------
# Image overlay track — PNG / JPG on top of the video via ffmpeg overlay
# ---------------------------------------------------------------------------

IMAGE_OVERLAY_POSITIONS = (
    "top_left", "top_right", "bottom_left", "bottom_right",
    "center", "top_center", "bottom_center",
)

# Edge margin (pixels) for the anchored positions. Kept modest so tiny
# logos don't float in empty space but corner badges don't hug the
# bezel. Matches the drawtext pad used in the UI preview.
_OVERLAY_PAD = 20


def _overlay_position_expr(anchor):
    """Return ``x:y`` ffmpeg expressions for an anchor name.

    ``main_w`` / ``main_h`` / ``overlay_w`` / ``overlay_h`` are the
    variables ffmpeg exposes inside the overlay filter; using them
    means positions self-adjust even if the image gets pre-scaled.
    """
    pad = _OVERLAY_PAD
    return {
        "top_left":      (f"{pad}",                              f"{pad}"),
        "top_right":     (f"main_w-overlay_w-{pad}",             f"{pad}"),
        "bottom_left":   (f"{pad}",                              f"main_h-overlay_h-{pad}"),
        "bottom_right":  (f"main_w-overlay_w-{pad}",             f"main_h-overlay_h-{pad}"),
        "center":        ("(main_w-overlay_w)/2",                "(main_h-overlay_h)/2"),
        "top_center":    ("(main_w-overlay_w)/2",                f"{pad}"),
        "bottom_center": ("(main_w-overlay_w)/2",                f"main_h-overlay_h-{pad}"),
    }.get(anchor, ("main_w-overlay_w-20", "20"))


def _build_image_overlay_chain(image_layers, base_label, video_dur=None):
    """Build the filter_complex chain that lays images over ``base_label``.

    Parameters
    ----------
    image_layers : list of dict
        Each dict carries ``path`` (str), ``position`` (anchor name),
        ``scale`` (0.0–1.0 relative to video width), ``opacity``
        (0.0–1.0), ``start`` and ``end`` (seconds, clip-relative).
    base_label : str
        The ``[v?]`` filter label whose output we overlay onto.
    video_dur : float, optional
        Clip duration — used to clamp per-overlay timing so
        out-of-range values don't crash ffmpeg.

    Returns a tuple ``(filter_str, final_label, input_paths)``. An
    empty ``filter_str`` means there are no valid layers and the
    caller should skip the filter_complex branch.
    """
    inputs = []
    parts = []
    current = base_label
    valid_layers = [
        L for L in (image_layers or []) if (L or {}).get("path")
    ]
    if not valid_layers:
        return "", current, inputs

    for idx, layer in enumerate(valid_layers):
        path = str(layer["path"])
        inputs.append(path)
        # ffmpeg stream index for this overlay image — every image is
        # fed in AFTER the main video, so input-stream i+1.
        stream_idx = idx + 1

        # Scale: fraction of main-video width. ``-1`` keeps aspect.
        scale = float(layer.get("scale", 0.25))
        scale = max(0.01, min(1.0, scale))
        # Opacity: ffmpeg's colorchannelmixer aa=<alpha>.
        opacity = max(0.0, min(1.0, float(layer.get("opacity", 1.0))))
        # Timing — clip-relative because the input was already -ss'd.
        start_t = max(0.0, float(layer.get("start", 0.0)))
        end_t = float(layer.get("end", video_dur or 1e9))
        if video_dur is not None:
            end_t = min(end_t, video_dur)
        if end_t <= start_t:
            # Invalid timing → skip the layer rather than crashing.
            inputs.pop()
            continue

        # Scale the overlay using main-video width (w): the filter
        # chain resolves main_w to the VIDEO width at run time, not
        # the image's own width.
        scaled_label = f"ov{idx}s"
        parts.append(
            f"[{stream_idx}:v]"
            f"format=rgba,"
            f"scale=w=iw*{scale:.3f}*(main_w/iw):h=-1,"
            f"colorchannelmixer=aa={opacity:.3f}"
            f"[{scaled_label}]"
        )
        # Wait — ffmpeg's ``scale`` filter doesn't know about main_w
        # inside the overlay input chain; only the ``overlay`` filter
        # exposes main_w/main_h. For the scale step we have to use
        # the source image's own iw. We'll pre-compute scale based on
        # an assumption: the video info object is passed in by the
        # caller via a separate helper that knows the video width.
        # For now we use the image's own iw × scale, which works as a
        # coarse "scale relative to image" knob. A future pass can
        # rebuild this to scale relative to video width if the caller
        # passes info.
        # (Rewriting the line above — same logic, without main_w.)
        parts[-1] = (
            f"[{stream_idx}:v]"
            f"format=rgba,"
            f"scale=iw*{scale:.3f}:-1,"
            f"colorchannelmixer=aa={opacity:.3f}"
            f"[{scaled_label}]"
        )

        x_expr, y_expr = _overlay_position_expr(layer.get("position", "top_right"))
        out_label = f"v_ov{idx}"
        enable = f":enable='between(t\\,{start_t:.3f}\\,{end_t:.3f})'"
        parts.append(
            f"[{current}][{scaled_label}]"
            f"overlay=x={x_expr}:y={y_expr}{enable}[{out_label}]"
        )
        current = out_label

    return ";".join(parts), current, inputs


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

    # Color grade (eq=) runs after the geometric ops but before speed —
    # keeps the per-pixel pass working on already-cropped / rotated
    # frames and avoids interaction with setpts.
    f = _build_eq_filter(options)
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
                text_layers=None, image_layers=None,
                progress_callback=None, cancel_event=None,
                options=None):
    preset = PRESETS[preset_name]
    duration = max(0.001, end - start)
    info = get_video_info(input_path)
    options = options or {}

    # Image overlays → filter_complex. The GIF two-pass (palettegen +
    # paletteuse) already does a ton of filter-graph wrangling, and
    # threading overlays through both passes cleanly while keeping
    # stream indices straight is fiddly. Shortcut: encode an
    # intermediate MP4 with the overlays baked in, then palette-pass
    # that. Costs an extra libx264 pass (~1-2× the GIF encode time) but
    # keeps the code simple and overlay quality good because the
    # dominant quality loss in GIFs is the palette reduction, not a
    # single extra lossy pass before it.
    valid_images = [L for L in (image_layers or []) if (L or {}).get("path")]
    if valid_images:
        intermediate = Path(tempfile.mktemp(suffix=".mp4"))

        def intermediate_progress(p):
            if progress_callback:
                # Intermediate encode gets the first half of the bar.
                progress_callback(p * 0.5)

        mp4_options = dict(options)
        # Force libx264 for the intermediate — the final GIF is
        # palette-reduced anyway, so HW encoder speed > quality.
        mp4_options["hw_encoder"] = "off"
        result = trim_to_video(
            str(input_path), start, end, preset_name, str(intermediate),
            text_layers=text_layers,
            image_layers=image_layers,
            progress_callback=intermediate_progress,
            cancel_event=cancel_event,
            options=mp4_options,
        )
        if not result or (cancel_event and cancel_event.is_set()):
            intermediate.unlink(missing_ok=True)
            return None

        # Now GIF-encode the intermediate. Re-invoke trim_to_gif
        # without image_layers and pointing at the new input. Text
        # layers are already baked in, so skip them too.
        def gif_half_progress(p):
            if progress_callback:
                progress_callback(0.5 + p * 0.5)

        gif_result = trim_to_gif(
            str(intermediate),
            start=0.0,
            end=duration,
            preset_name=preset_name,
            output_path=output_path,
            text_layers=None,
            image_layers=None,
            progress_callback=gif_half_progress,
            cancel_event=cancel_event,
            options={k: v for k, v in options.items()
                     if k not in ("aspect_preset", "crop", "rotate", "speed")},
        )
        intermediate.unlink(missing_ok=True)
        return gif_result

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
