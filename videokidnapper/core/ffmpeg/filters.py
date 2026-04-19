# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Filter-graph string builders.

Every function here is pure: options dict in, filter-string out (or
``None`` when the filter would be a no-op). The encode module picks
these up, joins them with commas, and hands them to ffmpeg via ``-vf``
or ``-filter_complex``.

Ordering convention established by :func:`_assemble_video_filters`:

    aspect-crop → crop → rotate → color-eq → speed → drawtext → scale

Drawtext MUST come before scale so fontsize / x:y are interpreted in
source-frame pixels (that's what the preview overlay uses, which keeps
export alignment pixel-exact).
"""

from videokidnapper.config import PRESETS
from videokidnapper.utils.ffmpeg_escape import escape_drawtext_value, escape_path


# ---------------------------------------------------------------------------
# Simple per-filter builders
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
    # Late import avoids a tk-at-import-time dependency during pytest collection
    # when the font-discovery path pulls in the UI layer.
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
# Aspect-ratio crop (sits next to _build_crop_filter conceptually)
# ---------------------------------------------------------------------------

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
# Image overlay track
# ---------------------------------------------------------------------------

IMAGE_OVERLAY_POSITIONS = (
    "top_left", "top_right", "bottom_left", "bottom_right",
    "center", "top_center", "bottom_center",
)

# Edge margin (pixels) for the anchored positions. Kept modest so tiny
# logos don't float in empty space but corner badges don't hug the
# bezel. Matches the drawtext pad used in the UI preview.
_OVERLAY_PAD = 20


def _overlay_position_expr(anchor, x=None, y=None):
    """Return ``x:y`` ffmpeg expressions for an overlay position.

    When ``x`` and ``y`` are both set (drag-positioned overlay), they
    win over ``anchor`` and go through as literal integer pixel offsets
    in source-video coordinate space. Negative values are clamped to 0
    so a drag to the edge can't generate an off-canvas overlay.

    Otherwise ``main_w`` / ``main_h`` / ``overlay_w`` / ``overlay_h``
    are ffmpeg variables available inside the overlay filter; using
    them means anchored positions self-adjust if the image is pre-
    scaled or the main video is cropped.
    """
    if x is not None and y is not None:
        return (f"{max(0, int(x))}", f"{max(0, int(y))}")
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

        # Scale step uses the source image's own iw — ffmpeg's scale
        # filter can't see main_w from inside an overlay input chain
        # (only the overlay= filter itself has main_w/main_h in scope).
        # So this is "scale relative to image" rather than "scale
        # relative to video width"; a future pass could rebuild to
        # take video width via a separate computed fraction.
        scaled_label = f"ov{idx}s"
        parts.append(
            f"[{stream_idx}:v]"
            f"format=rgba,"
            f"scale=iw*{scale:.3f}:-1,"
            f"colorchannelmixer=aa={opacity:.3f}"
            f"[{scaled_label}]"
        )

        # Drag-positioned overlays carry explicit pixel coords that win
        # over the anchor. ``x`` / ``y`` come from the VideoPlayer drag
        # handler in source-video coordinate space, so they go through
        # the overlay filter directly without a scale transform.
        drag_x = layer.get("x")
        drag_y = layer.get("y")
        x_expr, y_expr = _overlay_position_expr(
            layer.get("position", "top_right"),
            x=drag_x, y=drag_y,
        )
        out_label = f"v_ov{idx}"
        enable = f":enable='between(t\\,{start_t:.3f}\\,{end_t:.3f})'"
        parts.append(
            f"[{current}][{scaled_label}]"
            f"overlay=x={x_expr}:y={y_expr}{enable}[{out_label}]"
        )
        current = out_label

    return ";".join(parts), current, inputs


# ---------------------------------------------------------------------------
# Full video filter chain assembly
# ---------------------------------------------------------------------------

def _assemble_video_filters(preset_name, info, text_layers, options):
    """Build the video filter chain in the right order.

    Order: (aspect-crop) → crop → rotate → color-eq → speed → drawtext → scale.

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
