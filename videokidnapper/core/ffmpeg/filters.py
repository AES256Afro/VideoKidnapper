# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Filter-graph string builders.

Every function here is pure: options dict in, filter-string out (or
``None`` when the filter would be a no-op). The encode module picks
these up, joins them with commas, and hands them to ffmpeg via ``-vf``
or ``-filter_complex``.

Ordering convention established by :func:`_assemble_video_filters`:

    aspect-crop → crop → rotate → colour-normalise → color-eq → speed
    → drawtext → [image overlays] → scale

Drawtext and overlays MUST come before scale so fontsize / x:y are
interpreted in layout-frame pixels: the exported frame before the final
downscale. The preview lays captions out in that same frame (see
``core.frame_geometry``), which is what keeps export alignment exact.
"""

import math

from videokidnapper.config import PRESETS
from videokidnapper.core.ffmpeg.color import (
    build_normalize_filter, rgba_to_working_filter,
)
from videokidnapper.utils.coerce import coerce_float, coerce_int
from videokidnapper.utils.ffmpeg_escape import (
    escape_drawtext_value,
    escape_path,
    sanitize_color,
    sanitize_position_expr,
)


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
    # Guard the chaining loops below: a non-positive speed would make
    # ``remaining < 0.5`` forever (each ``/= 0.5`` doubles the magnitude),
    # hanging the encode thread. Clamp to a sane positive range.
    speed = max(0.1, min(100.0, speed))
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


# Shared with the preview canvas — see utils/coerce.py for why these do
# not live next to either consumer. Aliased under the old private names
# so existing callers and tests keep working.
_coerce_int = coerce_int
_coerce_float = coerce_float


def _build_drawtext_filter(layer, fade=0.0, frame_w=None, frame_h=None):
    """One ``drawtext=`` filter for a caption layer.

    ``frame_w``/``frame_h`` is the layout frame (see
    ``core.frame_geometry``). When given, the caption is kept on screen
    exactly the way the preview keeps it: word-wrapped to the width,
    shrunk if it is still too tall, and clamped so no position (a drag
    near an edge, a motion path) can push it off the frame. drawtext
    does none of this itself, so a long caption on a narrow (e.g. 9:16)
    export used to run off both edges.
    """
    # Late import avoids a tk-at-import-time dependency during pytest collection
    # when the font-discovery path pulls in the UI layer.
    from videokidnapper.ui.text_layers import _find_font_path

    # Normalise line endings first: the UI textbox and SRT files can hand
    # us \r\n. drawtext renders embedded \n as line breaks, but a stray
    # \r shows up as a tofu glyph.
    raw_text = str(layer.get("text", "")).replace("\r\n", "\n").replace("\r", "\n")
    raw_font_path = _find_font_path(
        layer.get("font", "Arial"),
        bold=bool(layer.get("bold")),
        italic=bool(layer.get("italic")),
    )
    fontsize = max(1, _coerce_int(layer.get("fontsize", 24), 24))
    if frame_w:
        raw_text, fontsize = _fit_to_frame(
            layer, raw_text, raw_font_path, fontsize, frame_w, frame_h)
    text = escape_drawtext_value(raw_text)
    font_path = escape_path(raw_font_path)
    # Colour options are unquoted in the filter spec, so an unvalidated
    # value escapes the option and injects filter graph — see
    # sanitize_color's docstring.
    fontcolor = sanitize_color(layer.get("fontcolor"), "white")
    # A keyframed motion path (meme-style tracked caption) wins over any
    # static position: compile the piecewise-linear path into
    # time-dependent expressions. The preview resolves the same
    # keyframes with utils.keyframes.position_at, so parity is
    # structural, not coincidental.
    keyframes = layer.get("keyframes") or []
    x_expr = y_expr = None
    if keyframes:
        from videokidnapper.utils.keyframes import compile_axis_expr
        try:
            x_expr = f"'{compile_axis_expr(keyframes, 'x')}'"
            y_expr = f"'{compile_axis_expr(keyframes, 'y')}'"
        except (KeyError, TypeError, ValueError):
            # Corrupt keyframe data (e.g. a hand-edited project) falls
            # back to the static position instead of aborting the encode.
            x_expr = y_expr = None
    if x_expr is None:
        # Position is validated, not escaped: it is interpolated bare
        # into the filter spec, so anything that is not provably a
        # position expression falls back to the default — same contract
        # as sanitize_color. See sanitize_position_expr's docstring.
        pos_expr = sanitize_position_expr(layer.get("position"))
        x_expr, y_expr = pos_expr.split(":", 1)
    if frame_w:
        x_expr = _clamp_expr(x_expr, "w", "tw", layer)
        y_expr = _clamp_expr(y_expr, "h", "th", layer)
    start_t = _coerce_float(layer.get("start", 0))
    end_t = _coerce_float(layer.get("end", 999999), 999999)
    layer_fade = _coerce_float(layer.get("fade", fade))

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

    # Outline (drawtext border). Width 0 means off and is omitted entirely,
    # so pre-existing layer dicts produce byte-identical filter strings.
    borderw = max(0, _coerce_int(layer.get("borderw", 0)))
    if borderw:
        parts.append(f"borderw={borderw}")
        parts.append(
            f"bordercolor={sanitize_color(layer.get('bordercolor'), 'black')}",
        )

    # Drop shadow — off unless either offset is non-zero.
    shadowx = _coerce_int(layer.get("shadowx", 0))
    shadowy = _coerce_int(layer.get("shadowy", 0))
    if shadowx or shadowy:
        parts.append(f"shadowx={shadowx}")
        parts.append(f"shadowy={shadowy}")
        parts.append(
            f"shadowcolor={sanitize_color(layer.get('shadowcolor'), 'black@0.7')}",
        )

    if layer.get("box"):
        boxcolor = sanitize_color(layer.get("boxcolor"), "black@0.6")
        boxborderw = max(0, _coerce_int(layer.get("boxborderw", 8), 8))
        parts.append("box=1")
        parts.append(f"boxcolor={boxcolor}")
        parts.append(f"boxborderw={boxborderw}")

    return ":".join(parts)


def _build_text_filters(text_layers, fade=0.0, frame_w=None, frame_h=None):
    if not text_layers:
        return []
    return [_build_drawtext_filter(layer, fade=fade, frame_w=frame_w, frame_h=frame_h)
            for layer in text_layers if layer.get("text", "").strip()]


def _fit_to_frame(layer, text, font_path, fontsize, frame_w, frame_h):
    """Wrap (and if needed shrink) ``text`` with the font drawtext uses.

    Returns ``(text, fontsize)``. Shares ``utils.text_wrap`` with the
    preview, so both land on the same lines and the same size.
    """
    from videokidnapper.utils.text_wrap import fit_layer_text
    try:
        from PIL import ImageFont

        def make_font(size):
            return ImageFont.truetype(str(font_path), size)

        text, _font, size = fit_layer_text(
            layer, text, make_font, fontsize, frame_w, frame_h)
        return text, size
    except Exception:
        # No usable font file to measure with: export as typed rather
        # than fail. drawtext will fail loudly on its own if the font
        # is really unusable.
        return text, fontsize


def _clamp_expr(expr, frame_var, size_var, layer):
    """Keep a drawtext coordinate inside the frame, outline included.

    ``expr`` may be a preset (``(w-tw)/2``), a dragged pixel value or a
    motion-path expression. Commas are safe inside the single quotes, the
    same way motion paths are already passed.
    """
    from videokidnapper.utils.text_wrap import clamp_margin
    inner = expr[1:-1] if len(expr) > 1 and expr[0] == expr[-1] == "'" else expr
    m = clamp_margin(layer)
    return f"'clip({inner},{m},max({m},{frame_var}-{size_var}-{m}))'"


# ---------------------------------------------------------------------------
# Aspect-ratio crop (sits next to _build_crop_filter conceptually)
# ---------------------------------------------------------------------------

def _aspect_target(preset):
    """'9:16' -> 0.5625, or None for anything that is not a ratio."""
    try:
        a, b = str(preset).split(":")
        return float(a) / float(b)
    except (ValueError, ZeroDivisionError, AttributeError):
        return None


def _aspect_crop_box(preset, info):
    """(w, h, x, y) of the centre crop that gives ``preset``'s ratio.

    None when the ratio cannot be parsed, the source has no size, or the
    source already has that ratio (so no crop is needed).
    """
    target = _aspect_target(preset)
    if target is None:
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
    return max(2, new_w), max(2, new_h), max(0, x), max(0, y)


def _build_aspect_crop(preset, info, explicit_crop):
    """Center-crop to a target aspect ratio like '1:1', '9:16', '16:9', '4:5', '3:4'.

    If the user has already defined an explicit crop rect we defer to that —
    aspect presets are just a convenience on top of no crop.
    """
    if explicit_crop:
        return None
    box = _aspect_crop_box(preset, info)
    if box is None:
        return None
    w, h, x, y = box
    return f"crop={w}:{h}:{x}:{y}"


def _build_aspect_scale(preset_name, aspect, info):
    """Final scale for an export with an aspect preset: an exact box.

    Cropping a 1920x1080 source to 9:16 gives a 607-wide frame; scaling
    that with ``scale=720:-2`` lands on 720x1284, because the crop was
    truncated to a whole pixel and the scale rounded to an even one
    independently. The blur-fill path has the same flaw (606x1080 ->
    720x1282). A "9:16" export that is not 9:16 is exactly the odd-ratio
    complaint, so instead compute the box from the preset width and the
    target ratio: 720x1280, 720x720, 1080x1920. Heights are rounded to
    even for yuv420p, so 16:9 at 720 wide is 720x406 — the same as the
    ``-2`` path gave, which keeps matched-orientation exports unchanged.

    Ultra has no width: use the cropped frame's own width, evened.
    """
    target = _aspect_target(aspect)
    if target is None:
        return None
    preset_width = PRESETS[preset_name]["width"]
    if preset_width is None:
        box = _aspect_crop_box(aspect, info)
        frame_w = box[0] if box else info.get("width", 0)
        if frame_w <= 0:
            return None
        out_w = _even(frame_w)
    else:
        out_w = _even(preset_width)
    # Nearest even, not rounded down: that is what ffmpeg's ``-2`` did,
    # so matched-orientation exports (720x406, 480x854) stay identical.
    out_h = _nearest_even(out_w / target)
    return f"scale={out_w}:{out_h}"


def _even(value):
    """Round down to the nearest even int (min 2) — yuv420p needs even dims."""
    value = int(value)
    return max(2, value - (value % 2))


def _nearest_even(value):
    """Round to the nearest even int (min 2), the way ffmpeg's ``-2`` does.

    Ties round up: 720 wide at 16:9 is exactly 405.0, and ffmpeg gives
    406. Python's ``round`` is banker's rounding and would give 404.
    """
    return max(2, int(math.floor(float(value) / 2.0 + 0.5)) * 2)


def _blur_canvas(preset, info):
    """(canvas_w, canvas_h, blur_radius) for blur fill, or None.

    Shared with ``core.frame_geometry`` so the preview composes the same
    canvas the export does.
    """
    target = _aspect_target(preset)
    if target is None:
        return None
    sw, sh = info.get("width", 0), info.get("height", 0)
    if sw <= 0 or sh <= 0:
        return None
    src_ratio = sw / sh
    if abs(src_ratio - target) < 0.001:
        return None
    # Canvas: keep the constraining source dimension, derive the other
    # from the target ratio. A 16:9 source going 9:16 keeps its height.
    if src_ratio > target:
        canvas_w, canvas_h = _even(sh * target), _even(sh)
    else:
        canvas_w, canvas_h = _even(sw), _even(sw / target)
    # Blur strength scales with the canvas so 480p and 4K look alike.
    radius = max(2, min(canvas_w, canvas_h) // 20)
    return canvas_w, canvas_h, radius


def _build_aspect_fill_blur(preset, info, explicit_crop):
    """Fit the source into a target aspect ratio over a blurred copy of itself.

    The modern Shorts / Reels look for aspect conversion: instead of
    center-cropping (losing pixels) or letterboxing (black bars), the
    bars are filled with a scaled-up, blurred copy of the frame.

    Returns a multi-chain filtergraph segment::

        split=2[bfm][bfb];
        [bfb]scale=W:H:force_original_aspect_ratio=increase,
             crop=W:H,boxblur=R[bfbg];
        [bfm]scale=W:H:force_original_aspect_ratio=decrease[bffg];
        [bfbg][bffg]overlay=(W-w)/2:(H-h)/2

    which is still valid inside a comma-joined ``-vf`` chain: the
    preceding filter's output feeds ``split``, and ``overlay``'s output
    feeds whatever comes next. Same defer-to-explicit-crop and same slot
    in the chain as ``_build_aspect_crop`` — the two are alternative
    modes of the one aspect step, picked by ``aspect_fill_mode``.
    """
    if explicit_crop:
        return None
    canvas = _blur_canvas(preset, info)
    if canvas is None:
        return None
    canvas_w, canvas_h, radius = canvas
    size = f"{canvas_w}:{canvas_h}"
    return (
        f"split=2[bfm][bfb];"
        f"[bfb]scale={size}:force_original_aspect_ratio=increase,"
        f"crop={size},boxblur={radius}[bfbg];"
        f"[bfm]scale={size}:force_original_aspect_ratio=decrease[bffg];"
        f"[bfbg][bffg]overlay=(W-w)/2:(H-h)/2"
    )


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
        # Drag coordinates come from the layer dict — coerce fail-soft so
        # a corrupt project falls back to the anchor instead of aborting
        # the encode.
        try:
            return (f"{max(0, int(x))}", f"{max(0, int(y))}")
        except (TypeError, ValueError):
            pass
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
        # All numerics are coerced fail-soft: a corrupt or hand-edited
        # project file must not abort the encode (same contract as the
        # drawtext builder above).
        scale = _coerce_float(layer.get("scale", 0.25), 0.25)
        scale = max(0.01, min(1.0, scale))
        # Opacity: ffmpeg's colorchannelmixer aa=<alpha>.
        opacity = max(0.0, min(1.0, _coerce_float(layer.get("opacity", 1.0), 1.0)))
        # Timing — clip-relative because the input was already -ss'd.
        start_t = max(0.0, _coerce_float(layer.get("start", 0.0)))
        end_t = _coerce_float(layer.get("end", video_dur or 1e9),
                              video_dur or 1e9)
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
        # The last step converts the RGBA sticker into the video's
        # colour space with the HD matrix. Left to the overlay filter,
        # that conversion used the SD matrix and tinted the sticker.
        parts.append(
            f"[{stream_idx}:v]"
            f"format=rgba,"
            f"scale=iw*{scale:.3f}:-1,"
            f"colorchannelmixer=aa={opacity:.3f},"
            f"{rgba_to_working_filter()}"
            f"[{scaled_label}]"
        )

        # Drag-positioned overlays carry explicit pixel coords that win
        # over the anchor. ``x`` / ``y`` come from the VideoPlayer drag
        # handler in layout-frame space, the same space this overlay
        # runs in (before the final downscale), so they go through
        # directly.
        drag_x = layer.get("x")
        drag_y = layer.get("y")
        x_expr, y_expr = _overlay_position_expr(
            layer.get("position", "top_right"),
            x=drag_x, y=drag_y,
        )
        out_label = f"v_ov{idx}"
        enable = f":enable='between(t\\,{start_t:.3f}\\,{end_t:.3f})'"
        # shortest=1 is load-bearing, not cosmetic. Every overlay input
        # is fed to ffmpeg with -loop 1 (still) or -stream_loop -1
        # (animated), so it never reaches EOF. Any filter that has to
        # buffer the whole stream then waits forever: palettegen, which
        # every GIF export runs, hangs and writes a zero-byte file.
        # Bounding the graph by the main video is also just correct —
        # the overlay should never extend the clip.
        parts.append(
            f"[{current}][{scaled_label}]"
            f"overlay=x={x_expr}:y={y_expr}:shortest=1{enable}[{out_label}]"
        )
        current = out_label

    return ";".join(parts), current, inputs


# ---------------------------------------------------------------------------
# Full video filter chain assembly
# ---------------------------------------------------------------------------

def _assemble_video_filters(preset_name, info, text_layers, options,
                            include_scale=True):
    """Build the video filter chain in the right order.

    Order: (aspect-crop) → crop → rotate → colour-normalise → color-eq
    → speed → drawtext → scale.

    ``drawtext`` MUST come before ``scale`` so fontsize and x/y are
    interpreted in layout-frame pixels, the space the preview lays
    captions out in. If ``scale`` came first (the old order), then on
    a 1920×1080 source with Medium preset (→720-wide), a custom position
    of ``x=960:y=540`` would land at pixel 960 of a 720-wide frame and
    overshoot the right edge.

    ``include_scale=False`` leaves the final scale off, for callers that
    compose image overlays first and scale afterwards (see
    :func:`_build_final_scale`). Stickers placed before the scale land
    where the preview shows them; placed after it, they came out up to
    four times larger relative to the frame.
    """
    from videokidnapper.core.frame_geometry import (
        aspect_after_rotate, export_geometry,
    )

    filters = []
    options = options or {}
    color = build_normalize_filter(info)
    state = {"color": color}

    def add_aspect(frame_info):
        # Aspect preset is a second crop; `_build_aspect_crop` itself
        # defers to any explicit crop. The "blur" fill mode swaps the
        # crop for a fit-over-blurred-background composite at the same
        # chain position.
        aspect = options.get("aspect_preset")
        if not aspect or aspect == "Source":
            return
        if options.get("aspect_fill_mode") == "blur":
            f = _build_aspect_fill_blur(aspect, frame_info, options.get("crop"))
            if f and state["color"]:
                # Blur fill scales and composites; do that on frames
                # that are already in the working colour space.
                filters.append(state["color"])
                state["color"] = None
        else:
            f = _build_aspect_crop(aspect, frame_info, options.get("crop"))
        if f:
            filters.append(f)

    # Turned 90°/270°, the frame's sides swap, so the aspect preset (which
    # describes the output) is applied after the rotation.
    rotate_first = aspect_after_rotate(options)
    if not rotate_first:
        add_aspect(info)

    f = _build_crop_filter(options.get("crop"), info)
    if f:
        filters.append(f)

    f = _build_rotate_filter(options.get("rotate"))
    if f:
        filters.append(f)

    if rotate_first:
        add_aspect(_rotated_info(info))
    color = state["color"]

    # Colour normalisation (HDR tone mapping, full-range / SD-matrix
    # conversion) runs after the pure geometry ops, so it touches only
    # the pixels that survive the crop, and before anything that paints
    # or grades pixels, so those work on the colours the viewer sees.
    if color:
        filters.append(color)

    # Color grade (eq=) runs after the geometric ops but before speed —
    # keeps the per-pixel pass working on already-cropped / rotated
    # frames and avoids interaction with setpts.
    f = _build_eq_filter(options)
    if f:
        filters.append(f)

    f = _build_speed_filter(options.get("speed"))
    if f:
        filters.append(f)

    # Drawtext in layout-frame pixels, fitted inside the layout frame.
    frame_w, frame_h = export_geometry(info, options).size
    filters.extend(_build_text_filters(
        text_layers, fade=options.get("text_fade", 0.0),
        frame_w=frame_w or None, frame_h=frame_h or None,
    ))

    if include_scale:
        f = _build_final_scale(preset_name, info, options)
        if f:
            filters.append(f)

    return filters


def _rotated_info(info):
    """``info`` with width and height swapped, for a 90°/270° turn."""
    rotated = dict(info)
    rotated["width"], rotated["height"] = info.get("height", 0), info.get("width", 0)
    return rotated


def _build_final_scale(preset_name, info, options):
    """The last step: downscale the layout frame to the preset's size.

    With an aspect preset the output must be an exact box (see
    _build_aspect_scale); otherwise a width-only scale preserves whatever
    ratio the source and any crop produced. The width compared against
    the preset is the layout frame's, not the source's, so a crop is
    never blown up past its own resolution.
    """
    from videokidnapper.core.frame_geometry import export_geometry

    from videokidnapper.core.frame_geometry import aspect_after_rotate

    options = options or {}
    aspect = options.get("aspect_preset")
    if aspect and aspect != "Source":
        frame_info = _rotated_info(info) if aspect_after_rotate(options) else info
        return _build_aspect_scale(preset_name, aspect, frame_info)
    layout_w = export_geometry(info, options).size[0] or info.get("width")
    return _build_scale_filter(preset_name, layout_w)


# ---------------------------------------------------------------------------
# GIF palette builders (palettegen / paletteuse)
# ---------------------------------------------------------------------------

# Dither key → paletteuse parameter string. Keys are what the UI / settings
# persist; values are what ffmpeg consumes. Unknown keys fall back to the
# historical default ("bayer") so a hand-edited settings file can't produce
# a command ffmpeg rejects.
GIF_DITHER_PARAMS = {
    "bayer":           "dither=bayer:bayer_scale=5",
    "floyd_steinberg": "dither=floyd_steinberg",
    "sierra2_4a":      "dither=sierra2_4a",
    "none":            "dither=none",
}

GIF_STATS_MODES = ("full", "diff")


def _build_palettegen_filter(max_colors, stats_mode="full"):
    """Build the first-pass ``palettegen`` filter string.

    ``stats_mode=diff`` weights the palette toward pixels that change
    between frames — a quality win for clips with static backgrounds
    (reaction GIFs, screen recordings). ``full`` (the historical
    behavior) weights all pixels equally and is omitted from the
    output so existing commands stay byte-identical.
    """
    max_colors = max(2, min(256, int(max_colors)))
    parts = [f"palettegen=max_colors={max_colors}"]
    if stats_mode in GIF_STATS_MODES and stats_mode != "full":
        parts.append(f"stats_mode={stats_mode}")
    return ":".join(parts)


def _build_paletteuse_filter(dither="bayer"):
    """Build the second-pass ``paletteuse`` filter string.

    ``bayer`` (the historical default) gives the patterned retro look
    and smaller files; ``floyd_steinberg`` smooths gradients at a size
    cost; ``none`` compresses flat-color sources (screen recordings)
    dramatically better.
    """
    params = GIF_DITHER_PARAMS.get(dither, GIF_DITHER_PARAMS["bayer"])
    return f"paletteuse={params}"


def _gif_loop_flag(loop):
    """Normalise a persisted loop value to what ``-loop`` accepts.

    GIF muxer semantics: ``0`` = loop forever, ``-1`` = play once
    (no Netscape loop extension), ``N>0`` = N additional loops.
    Anything unparseable falls back to forever — the historical
    behavior and the least surprising default.
    """
    try:
        value = int(loop)
    except (TypeError, ValueError):
        return 0
    if value < -1:
        return 0
    return value
