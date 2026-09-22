# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Word-wrap captions to the width of the exported frame.

ffmpeg's drawtext never wraps: a caption wider than the frame just runs
off both edges. That is most visible on a 9:16 export of landscape
video, where the frame is a third as wide as the one the caption was
typed against. Captions are now wrapped to the layout frame, in the
export and in the preview alike, using the same font file and size, so
the lines break in the same places on both sides.

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
