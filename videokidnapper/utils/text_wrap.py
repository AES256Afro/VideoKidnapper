# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Keep captions inside the exported frame: wrap, shrink, clamp.

ffmpeg's drawtext never wraps: a caption wider than the frame just runs
off both edges. That is most visible on a 9:16 export of landscape
video, where the frame is a third as wide as the one the caption was
typed against. Captions are now wrapped to the layout frame, shrunk if
they are still too tall, and clamped so no position can push them off,
in the export and in the preview alike, using the same font file and
size, so both land on the same pixels.

The caption text the user typed is never modified; wrapping happens at
render time, so changing the aspect preset re-wraps automatically.
"""

from videokidnapper.utils.coerce import coerce_int

#: Edge margin, matching the 20 px the position presets use.
EDGE_PAD = 20

# Never wrap narrower than this share of the frame. A caption dragged
# almost to the right edge should not collapse into one word per line.
_MIN_SHARE = 0.25


def wrap_text(text, measure, max_width):
    """Insert line breaks so no line is wider than ``max_width``.

    ``measure(str) -> float`` gives a line's rendered width in pixels.
    Explicit newlines are kept. Words longer than a whole line (long
    URLs, or scripts written without spaces) are broken between
    characters.
    """
    if max_width <= 0 or not text:
        return text
    out = []
    for paragraph in text.split("\n"):
        out.extend(_wrap_paragraph(paragraph, measure, max_width))
    return "\n".join(out)


def _wrap_paragraph(paragraph, measure, max_width):
    if not paragraph.strip() or measure(paragraph) <= max_width:
        return [paragraph]
    lines = []
    current = ""
    for word in paragraph.split(" "):
        candidate = f"{current} {word}" if current else word
        if measure(candidate) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if measure(word) <= max_width:
            current = word
            continue
        # A single word wider than the line: break it by characters.
        piece = ""
        for ch in word:
            if piece and measure(piece + ch) > max_width:
                lines.append(piece)
                piece = ch
            else:
                piece += ch
        current = piece
    if current:
        lines.append(current)
    return lines or [paragraph]


def available_width(layer, frame_w, position_xy=None):
    """How wide a caption may be before it must wrap.

    Anchored and centred captions get the frame minus a margin on each
    side. A caption dragged to ``x`` gets the room to the right of it,
    but never less than a quarter of the frame. The outline and the
    background box are drawn outside the text, so their widths come off
    the budget too.
    """
    frame_w = int(frame_w or 0)
    if frame_w <= 0:
        return 0
    width = frame_w - 2 * EDGE_PAD
    if position_xy is not None and not (layer.get("keyframes") or []):
        x = position_xy[0]
        width = max(frame_w - int(x) - EDGE_PAD, int(frame_w * _MIN_SHARE))
    borderw = max(0, coerce_int(layer.get("borderw", 0)))
    width -= 2 * borderw
    if layer.get("box"):
        width -= 2 * max(0, coerce_int(layer.get("boxborderw", 8), 8))
    return max(1, width)


def numeric_position(position):
    """``(x, y)`` for a dragged ``"x:y"`` position, else ``None``."""
    if not position or ":" not in str(position):
        return None
    a, _, b = str(position).partition(":")
    try:
        return float(a), float(b)
    except ValueError:
        return None


def drawtext_vmetrics(font, text):
    """``(y_max, y_min, line_h)`` the way ffmpeg's drawtext measures them.

    drawtext takes the highest glyph top and the lowest glyph bottom over
    the whole caption (y up, baseline 0), and advances every line by the
    difference, so a caption is ``line_h * lines`` tall. Newlines are not
    glyphs. ``None`` if the font can't be measured.
    """
    y_max = y_min = 0
    try:
        for ch in set(text) - {"\n"}:
            _l, top, _r, bottom = font.getbbox(ch, anchor="ls")
            y_max = max(y_max, -top)
            y_min = min(y_min, -bottom)
    except Exception:
        return None
    line_h = y_max - y_min
    return (y_max, y_min, line_h) if line_h > 0 else None


def edge_margin(layer):
    """Pixels the outline or background box reach beyond the glyphs."""
    margin = max(0, coerce_int(layer.get("borderw", 0)))
    if layer.get("box"):
        margin = max(margin, coerce_int(layer.get("boxborderw", 8), 8))
    return margin


def clamp_margin(layer):
    """Closest a caption may sit to the frame edge when kept on screen.

    The outline/box reach, plus 2 px so the glyphs' anti-aliased edge is
    never the frame's last row or column.
    """
    return edge_margin(layer) + 2


#: Smallest size a caption is shrunk to while fitting it into the frame.
MIN_FIT_SIZE = 10


def fit_layer_text(layer, text, make_font, fontsize, frame_w, frame_h):
    """Wrap a caption, and shrink it if needed, so it fits the frame.

    Wrapping keeps it inside the frame's width. A caption can still be
    too tall (many lines, or a big font on a small frame), or have a
    single character wider than the frame; then the font steps down 10%
    at a time until it fits, to no smaller than ``MIN_FIT_SIZE``.

    ``make_font(size)`` returns a Pillow FreeType font. The export and
    the preview both call this with the same font file, so they agree on
    the lines and the size. Returns ``(text, font, size)``.
    """
    size = max(1, int(fontsize))
    font = make_font(size)
    if layer.get("wrap") is False or not frame_w:
        return text, font, size
    budget_h = (frame_h or 0) - 2 * EDGE_PAD - 2 * edge_margin(layer)
    while True:
        wrapped = wrap_layer_text(layer, text, font, frame_w)
        if size <= MIN_FIT_SIZE or _fits(layer, wrapped, font, frame_w, budget_h):
            return wrapped, font, size
        size = max(MIN_FIT_SIZE, int(size * 0.9))
        font = make_font(size)


def _fits(layer, wrapped, font, frame_w, budget_h):
    lines = wrapped.split("\n")
    width_budget = frame_w - 2 * edge_margin(layer)
    try:
        widest = max(font.getlength(line) for line in lines)
    except Exception:
        return True
    if widest > width_budget:
        return False
    if budget_h <= 0:
        return True
    metrics = drawtext_vmetrics(font, wrapped)
    return metrics is None or metrics[2] * len(lines) <= budget_h


def wrap_layer_text(layer, text, font, frame_w):
    """Wrap ``text`` for ``layer`` rendered with a Pillow ``font``.

    ``font`` is an ``ImageFont.FreeTypeFont`` at the layer's size. The
    export measures with the same font file through FreeType, which is
    what drawtext renders with, so line widths agree.
    """
    if layer.get("wrap") is False or not frame_w:
        return text
    budget = available_width(layer, frame_w, numeric_position(layer.get("position")))
    if budget <= 0:
        return text

    def measure(s):
        try:
            return font.getlength(s)
        except AttributeError:  # very old Pillow
            return font.getsize(s)[0]

    return wrap_text(text, measure, budget)
