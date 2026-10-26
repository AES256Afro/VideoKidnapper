# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The shape of the exported frame, shared by the export and the preview.

Captions and stickers are placed in *layout space*: the exported frame
after aspect crop / manual crop / blur fill / rotation, but before the
final downscale. That is where ffmpeg's drawtext runs, so it is the only
space in which a caption's position and size mean one thing.

The preview used to draw captions on the raw source frame instead. On
any export that changed the frame (a 9:16 preset on landscape video, a
manual crop, blur fill, rotation), the caption the user placed was not
the caption that got exported: centred text wider than the new frame
was sliced off at both edges, and dragged positions landed offset by the
crop. This module describes the geometry once, as the same ordered
steps ``filters._assemble_video_filters`` emits, so both sides agree.

Everything here is pure except :meth:`FrameGeometry.render`, which uses
Pillow (already a hard dependency) and no Tk.
"""

from dataclasses import dataclass, field
from typing import Tuple

from videokidnapper.core.ffmpeg.filters import _aspect_crop_box, _blur_canvas


@dataclass(frozen=True)
class Step:
    """One geometric step. ``in_w``/``in_h`` is the frame it receives."""

    kind: str                  # "crop" | "blur" | "rotate"
    in_w: int
    in_h: int
    box: Tuple[int, int, int, int] = (0, 0, 0, 0)   # crop x,y,w,h; blur fg
    canvas: Tuple[int, int] = (0, 0)                # blur canvas w,h
    radius: int = 0                                 # blur radius
    degrees: int = 0                                # rotate

    @property
    def out_size(self):
        if self.kind == "crop":
            return self.box[2], self.box[3]
        if self.kind == "blur":
            return self.canvas
        if self.kind == "rotate" and self.degrees in (90, 270):
            return self.in_h, self.in_w
        return self.in_w, self.in_h

    # Points are continuous coordinates, so rectangles map exactly.
    # transpose=1 turns the frame 90° clockwise, transpose=2 anticlockwise.
    def forward(self, x, y):
        if self.kind == "crop":
            return x - self.box[0], y - self.box[1]
        if self.kind == "blur":
            fx, fy, fw, fh = self.box
            return fx + x * fw / max(1, self.in_w), fy + y * fh / max(1, self.in_h)
        if self.kind == "rotate":
            w, h = self.in_w, self.in_h
            if self.degrees == 90:
                return h - y, x
            if self.degrees == 180:
                return w - x, h - y
            if self.degrees == 270:
                return y, w - x
        return x, y

    def backward(self, x, y):
        if self.kind == "crop":
            return x + self.box[0], y + self.box[1]
        if self.kind == "blur":
            fx, fy, fw, fh = self.box
            return (x - fx) * self.in_w / max(1, fw), (y - fy) * self.in_h / max(1, fh)
        if self.kind == "rotate":
            w, h = self.in_w, self.in_h
            if self.degrees == 90:
                return y, h - x
            if self.degrees == 180:
                return w - x, h - y
            if self.degrees == 270:
                return w - y, x
        return x, y


@dataclass(frozen=True)
class FrameGeometry:
    """How a source frame becomes the export's layout frame."""

    src_w: int
    src_h: int
    steps: Tuple[Step, ...] = field(default_factory=tuple)

    @property
    def size(self):
        """(width, height) of the layout frame."""
        return self.steps[-1].out_size if self.steps else (self.src_w, self.src_h)

    @property
    def is_subrect(self):
        """True when the layout frame is a plain window onto the source.

        The preview then shows the whole source with the discarded part
        dimmed, which tells the user what the export cuts away.
        """
        return all(s.kind == "crop" for s in self.steps)

    @property
    def offset(self):
        """Top-left of the layout frame in source pixels (sub-rect only)."""
        x = y = 0
        for s in self.steps:
            if s.kind == "crop":
                x, y = x + s.box[0], y + s.box[1]
        return x, y

    def source_to_layout(self, x, y):
        x, y = float(x), float(y)
        for s in self.steps:
            x, y = s.forward(x, y)
        return x, y

    def layout_to_source(self, x, y):
        x, y = float(x), float(y)
        for s in reversed(self.steps):
            x, y = s.backward(x, y)
        return x, y

    def layout_rect_to_source(self, x1, y1, x2, y2):
        """Map a rectangle; corners are re-sorted after rotation."""
        ax, ay = self.layout_to_source(x1, y1)
        bx, by = self.layout_to_source(x2, y2)
        return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)

    def source_rect_to_layout(self, x1, y1, x2, y2):
        ax, ay = self.source_to_layout(x1, y1)
        bx, by = self.source_to_layout(x2, y2)
        return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)

    def crop_source(self, image):
        """The part of a source-sized image the export keeps (sub-rect)."""
        x, y = self.offset
        w, h = self.size
        if (x, y, w, h) == (0, 0, image.width, image.height):
            return image
        return image.crop((x, y, x + w, y + h))

    def render(self, image):
        """Turn a source frame into the layout frame, as the export does.

        ``image`` may be the source decoded smaller (playback decodes
        frames near the size they are shown at). Every step then runs at
        that scale, and the result is the layout frame shrunk alike,
        instead of first blowing the frame back up to full size.
        """
        from PIL import Image, ImageFilter

        out = image
        for s in self.steps:
            # How much smaller than the step's input this frame is.
            kx = out.width / max(1, s.in_w)
            ky = out.height / max(1, s.in_h)
            if s.kind == "crop":
                x, y, w, h = _scaled_box(s.box, kx, ky)
                out = out.crop((x, y, x + w, y + h))
            elif s.kind == "blur":
                cw = max(1, round(s.canvas[0] * kx))
                ch = max(1, round(s.canvas[1] * ky))
                # Background: cover the canvas, centre-crop, blur twice
                # (ffmpeg's boxblur applies its box twice by default).
                scale = max(cw / out.width, ch / out.height)
                bw = max(cw, int(round(out.width * scale)))
                bh = max(ch, int(round(out.height * scale)))
                bg = out.resize((bw, bh), Image.BILINEAR)
                left, top = (bw - cw) // 2, (bh - ch) // 2
                bg = bg.crop((left, top, left + cw, top + ch))
                radius = s.radius and max(1, round(s.radius * kx))
                if radius:
                    blur = ImageFilter.BoxBlur(radius)
                    bg = bg.filter(blur).filter(blur)
                fx, fy, fw, fh = _scaled_box(s.box, kx, ky)
                bg.paste(out.resize((fw, fh), Image.BILINEAR), (fx, fy))
                out = bg
            elif s.kind == "rotate":
                out = out.transpose({
                    90: Image.Transpose.ROTATE_270,
                    180: Image.Transpose.ROTATE_180,
                    270: Image.Transpose.ROTATE_90,
                }[s.degrees])
        return out


def _scaled_box(box, kx, ky):
    """An (x, y, w, h) box for a frame ``kx`` x ``ky`` times the size."""
    if kx == 1 and ky == 1:
        return box
    x, y, w, h = box
    return (round(x * kx), round(y * ky),
            max(1, round(w * kx)), max(1, round(h * ky)))


def _crop_box(crop, w, h):
    """Clamp a manual crop exactly the way ``_build_crop_filter`` does."""
    if not crop or w < 2 or h < 2:
        return None
    try:
        cw = int(max(2, min(crop.get("w", w), w)))
        ch = int(max(2, min(crop.get("h", h), h)))
        x = int(max(0, min(crop.get("x", 0), w - cw)))
        y = int(max(0, min(crop.get("y", 0), h - ch)))
    except (TypeError, ValueError, AttributeError):
        return None
    return x, y, cw, ch


def rotation_of(options):
    """Rotation in degrees, normalised to 0/90/180/270."""
    try:
        r = int((options or {}).get("rotate") or 0) % 360
    except (TypeError, ValueError):
        return 0
    return r if r in (90, 180, 270) else 0


def aspect_after_rotate(options):
    """True when the aspect step must run on the rotated frame.

    An aspect preset describes the *output*. Turned 90° or 270°, the
    frame's width and height swap, so the preset has to be applied after
    the rotation. Applied before (the old order), a 9:16 preset on
    landscape video rotated 90° produced a landscape strip that the final
    scale then stretched into 9:16.
    """
    return rotation_of(options) in (90, 270)


def _aspect_step(options, w, h):
    aspect = options.get("aspect_preset")
    if not aspect or aspect == "Source":
        return None
    info = {"width": w, "height": h}
    if options.get("aspect_fill_mode") == "blur":
        canvas = _blur_canvas(aspect, info)
        if not canvas:
            return None
        cw, ch, radius = canvas
        # scale=...:force_original_aspect_ratio=decrease rounds to the
        # nearest pixel; overlay truncates its x/y to even for yuv420.
        fw = min(int(round(ch * w / h)), cw)
        fh = min(int(round(cw * h / w)), ch)
        fx = int((cw - fw) / 2) & ~1
        fy = int((ch - fh) / 2) & ~1
        return Step("blur", w, h, box=(fx, fy, fw, fh), canvas=(cw, ch), radius=radius)
    abox = _aspect_crop_box(aspect, info)
    if not abox:
        return None
    bw, bh, bx, by = abox
    return Step("crop", w, h, box=(bx, by, bw, bh))


def export_geometry(info, options=None, include_crop=True):
    """Describe the layout frame an export with ``options`` will produce.

    ``include_crop=False`` ignores the manual crop, for callers that need
    the frame the crop tool is drawn on.
    """
    info = info or {}
    options = options or {}
    sw = int(info.get("width") or 0)
    sh = int(info.get("height") or 0)
    if sw <= 0 or sh <= 0:
        return FrameGeometry(sw, sh)

    steps = []
    w, h = sw, sh
    rotate = rotation_of(options)
    manual = _crop_box(options.get("crop"), w, h) if include_crop else None

    if manual:
        # A manual crop is drawn on the source and wins over any aspect
        # preset, which defers to it (same precedence as the filters).
        steps.append(Step("crop", w, h, box=manual))
        w, h = steps[-1].out_size
    elif not aspect_after_rotate(options):
        step = _aspect_step(options, w, h)
        if step:
            steps.append(step)
            w, h = step.out_size

    if rotate:
        steps.append(Step("rotate", w, h, degrees=rotate))
        w, h = steps[-1].out_size

    if not manual and aspect_after_rotate(options):
        step = _aspect_step(options, w, h)
        if step:
            steps.append(step)

    return FrameGeometry(sw, sh, tuple(steps))


def frame_change_note(info, options):
    """One line on how the frame shape reshapes the picture, or None.

    A platform preset sets the frame shape along with the quality, and
    the Export page didn't say so: "YouTube 1080p" on a vertical clip
    cut most of it away, shown only on the Edit preview.
    """
    options = options or {}
    aspect = options.get("aspect_preset")
    if not aspect or aspect == "Source":
        return None
    info = info or {}
    w, h = int(info.get("width") or 0), int(info.get("height") or 0)
    if _crop_box(options.get("crop"), w, h):
        return None  # a manual crop wins over the frame shape
    step = next((s for s in export_geometry(info, options).steps
                 if s.kind in ("blur", "crop")), None)
    if step is None:
        return None
    if step.kind == "blur":
        return f"Frame {aspect}: the whole picture, with blurred bars around it."
    _x, _y, w, h = step.box
    if (w, h) == (step.in_w, step.in_h):
        return None
    kept = round(100 * w * h / (step.in_w * step.in_h))
    cut = "the sides" if w < step.in_w else "the top and bottom"
    return f"Frame {aspect}: cuts off {cut}, keeping {kept}% of the picture."
