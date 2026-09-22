# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Video preview canvas with Play/Pause, live text-layer overlay, and DnD.

Two playback modes coexist:

- **Real-time A/V playback** via ``core.playback.AudioVideoPlayer`` when
  the optional ``imageio-ffmpeg`` + ``sounddevice`` + ``numpy`` deps are
  available. Audio is decoded to PCM and played through the OS sound
  device; video frames come from a persistent ``ffmpeg`` pipe and are
  synced to the audio clock. This is what users actually want — Play
  now sounds like Play.

- **Frame-scrub fallback** at ~8 fps when any of those deps is missing.
  The original behavior: re-run ffmpeg per tick, cache frames in the
  LRU, no audio. The core app still works on a bare ``pip install``.

The code branches on :func:`core.playback.is_available` once in
``play()``; ``stop()`` handles both modes so keyboard nudges, slider
moves, and the Stop button all behave the same regardless of which
path started the playback.
"""

import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from videokidnapper.utils.text_wrap import drawtext_vmetrics

from videokidnapper.utils.coerce import coerce_float, coerce_int
from videokidnapper.core import playback
from videokidnapper.core.preview import get_frame_at
from videokidnapper.ui import theme as T
from videokidnapper.utils.snap import apply_snap, build_targets


class VideoPlayer(ctk.CTkFrame):
    _PLAY_FPS = 8
    _PLAY_MS = int(1000 / _PLAY_FPS)

    def __init__(self, master, on_empty_click=None, on_file_dropped=None, **kwargs):
        super().__init__(
            master,
            fg_color=T.BG_SURFACE,
            border_width=1,
            border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
            **kwargs,
        )
        self.video_path = None
        self.duration = 0
        self.current_time = 0
        self._photo = None
        self._on_empty_click = on_empty_click
        self._on_file_dropped = on_file_dropped
        self._placeholder_ids = []
        self._text_layers_provider = None
        # Image overlays live alongside text layers: a callable returning
        # the current list of overlay dicts. Loaded PIL images are memoized
        # by path so panning through frames doesn't re-read them from disk.
        self._image_layers_provider = None
        self._image_cache = {}  # path → PIL.Image (RGBA)
        # path → (frames, durations_ms) for animated stickers, or
        # None once a path is known to be a still. Decoding every
        # frame is done once per file, not once per preview tick.
        self._image_anim_cache = {}
        self._playing = False
        self._play_after_id = None
        self._play_end = None
        # Real-time A/V player (None until play() creates one).
        self._av_player = None
        self._av_time_after_id = None

        # Crop state: a rect in SOURCE pixel coords, or None when disabled.
        self._crop_mode = False
        self._crop_rect = None        # {"x","y","w","h"} in source pixels
        self._crop_drag_start = None  # (canvas_x, canvas_y)
        self._crop_change_cb = None
        self._last_frame_rect = None  # (cx, cy, dw, dh, fw, fh) for mapping canvas↔source

        # Layout space: the exported frame before the final downscale,
        # where captions and stickers live (see core.frame_geometry). In
        # the context view the displayed image is the whole source and
        # the layout frame is a window onto it at ``_layout_offset``; in
        # the output view the displayed image IS the layout frame.
        self._export_options_provider = None
        self._geometry = None
        self._layout_offset = (0, 0)
        self._layout_size = (0, 0)

        # Text-layer drag state. `_text_bboxes` is rebuilt on each overlay
        # render so hit-testing uses the exact rendered position.
        self._text_bboxes = []        # [(index, src_x1, src_y1, src_x2, src_y2)]
        self._dragging_text_index = None
        self._text_drag_offset = (0, 0)  # (src dx, src dy) from click to text origin
        self._text_position_cb = None    # callback(index, src_x, src_y)

        # Image-overlay drag state — parallel to text. ``_image_bboxes``
        # is rebuilt by ``_apply_image_overlay`` on every frame render
        # so hit-testing uses the exact rendered position, including
        # drag overrides that may have arrived since the last repaint.
        self._image_bboxes = []        # [(index, src_x1, src_y1, src_x2, src_y2)]
        self._dragging_image_index = None
        self._image_drag_offset = (0, 0)  # (src dx, src dy) from click to image top-left
        self._image_position_cb = None    # callback(index, src_x, src_y)

        self.canvas = tk.Canvas(
            self,
            bg=T.BG_BASE,
            highlightthickness=0,
            cursor="hand2" if on_empty_click else "crosshair",
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas.bind("<Configure>", self._on_resize)

        # Single dispatcher per event — routes into empty-click, crop, or
        # text-drag depending on state. Keeps the precedence explicit and
        # avoids multiple overlapping bindings fighting each other.
        self.canvas.bind("<ButtonPress-1>",   self._on_canvas_press)
        self.canvas.bind("<B1-Motion>",       self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>",          self._on_canvas_hover)

        self._register_dnd()
        self._draw_placeholder()

    # ------------------------------------------------------------------
    # DnD (tkinterdnd2 if available)
    # ------------------------------------------------------------------
    def _register_dnd(self):
        if not self._on_file_dropped:
            return
        try:
            self.canvas.drop_target_register("DND_Files")  # type: ignore[attr-defined]
            self.canvas.dnd_bind("<<Drop>>", self._on_drop)  # type: ignore[attr-defined]
        except (AttributeError, tk.TclError):
            # tkinterdnd2 not active; silently skip
            pass

    def _on_drop(self, event):
        from videokidnapper.utils.dnd import parse_dnd_files
        paths = parse_dnd_files(event.data or "")
        if paths and self._on_file_dropped:
            self._on_file_dropped(paths[0])

    # ------------------------------------------------------------------
    # Text-layer + image-overlay live preview
    # ------------------------------------------------------------------
    def set_text_layers_provider(self, provider):
        """`provider` is a zero-arg callable returning the current layer list."""
        self._text_layers_provider = provider

    def set_image_layers_provider(self, provider):
        """`provider` is a zero-arg callable returning the image-overlay list.

        Same shape as ``set_text_layers_provider`` but for PNG/JPG
        overlays. Returning ``None`` or an empty list is the "no
        overlays" case and produces no extra rendering work.
        """
        self._image_layers_provider = provider

    def get_text_source_bbox(self, index):
        """Source-pixel ``(x1, y1, x2, y2)`` of a text layer as last
        rendered, or None. Feeds auto-tracking: the tracked region is
        the patch of video currently under the caption. The caption is
        rendered in layout space, so the box is mapped back through the
        export geometry to the source video the tracker reads."""
        for idx, x1, y1, x2, y2 in self._text_bboxes:
            if idx == index:
                return tuple(int(round(v)) for v in
                             self.layout_rect_to_source(x1, y1, x2, y2))
        return None

    def set_export_options_provider(self, provider):
        """``provider() -> dict`` of export options (aspect, rotate, crop).

        With it, the preview shows the frame the export will produce, so
        captions and stickers are placed, sized and wrapped exactly as
        they will come out.
        """
        self._export_options_provider = provider

    def _current_geometry(self, frame_size):
        from videokidnapper.core.frame_geometry import export_geometry

        options = {}
        if self._export_options_provider:
            try:
                options = dict(self._export_options_provider() or {})
            except Exception:
                options = {}
        # The live crop rect: settings only learn it on mouse release.
        options["crop"] = self._crop_rect if self._crop_mode else None
        if self._crop_mode:
            # The crop tool is drawn on the unrotated source, so show that.
            options["rotate"] = 0
        w, h = frame_size
        return export_geometry({"width": w, "height": h}, options)

    def layout_rect_to_source(self, x1, y1, x2, y2):
        """Map a layout-space rectangle to source pixels (for tracking)."""
        if self._geometry is None:
            return x1, y1, x2, y2
        return self._geometry.layout_rect_to_source(x1, y1, x2, y2)

    def source_rect_to_layout(self, x1, y1, x2, y2):
        if self._geometry is None:
            return x1, y1, x2, y2
        return self._geometry.source_rect_to_layout(x1, y1, x2, y2)

    def refresh_overlay(self):
        """Re-render the current frame with latest text + image overlays."""
        if self.video_path:
            self.show_frame(self.current_time)

    # ------------------------------------------------------------------
    # Placeholder
    # ------------------------------------------------------------------
    def _draw_placeholder(self):
        for item in self._placeholder_ids:
            self.canvas.delete(item)
        self._placeholder_ids.clear()

        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            return

        cx, cy = w // 2, h // 2

        for gx in range(40, w, 80):
            for gy in range(40, h, 80):
                self._placeholder_ids.append(
                    self.canvas.create_oval(
                        gx - 1, gy - 1, gx + 1, gy + 1,
                        fill=T.BG_SURFACE, outline="",
                    )
                )

        icon_w, icon_h = 110, 72
        ix1, iy1 = cx - icon_w // 2, cy - icon_h // 2 - 24
        ix2, iy2 = cx + icon_w // 2, cy + icon_h // 2 - 24
        self._placeholder_ids.append(
            self.canvas.create_rectangle(
                ix1, iy1, ix2, iy2,
                fill=T.BG_SURFACE, outline=T.BORDER_STRONG, width=2,
            )
        )
        hole_w, gap = 10, 6
        for i in range(5):
            hx1 = ix1 + gap + i * (hole_w + gap)
            hx2 = hx1 + hole_w
            self._placeholder_ids.append(
                self.canvas.create_rectangle(
                    hx1, iy1 + 6, hx2, iy1 + 14,
                    fill=T.BG_BASE, outline="",
                )
            )
            self._placeholder_ids.append(
                self.canvas.create_rectangle(
                    hx1, iy2 - 14, hx2, iy2 - 6,
                    fill=T.BG_BASE, outline="",
                )
            )
        pcx, pcy = cx, cy - 24
        size = 14
        self._placeholder_ids.append(
            self.canvas.create_polygon(
                pcx - size + 4, pcy - size,
                pcx - size + 4, pcy + size,
                pcx + size,     pcy,
                fill=T.ACCENT, outline="",
            )
        )

        self._placeholder_ids.append(
            self.canvas.create_text(
                cx, cy + 40,
                text="No video loaded",
                fill=T.TEXT,
                font=(T.FONT_FAMILY, 16, "bold"),
            )
        )
        hint = (
            "Click here, drag a file, or use Open Video File"
            if self._on_empty_click
            else "Load a video or download one from a URL"
        )
        self._placeholder_ids.append(
            self.canvas.create_text(
                cx, cy + 64,
                text=hint,
                fill=T.TEXT_DIM,
                font=(T.FONT_FAMILY, 11),
            )
        )

    def _maybe_empty_click(self, _event):
        if self.video_path is None and self._on_empty_click:
            self._on_empty_click()

    # ------------------------------------------------------------------
    # Unified canvas event dispatcher — empty-click → crop → text drag.
    # ------------------------------------------------------------------
    def _on_canvas_press(self, event):
        if self.video_path is None:
            self._maybe_empty_click(event)
            return
        if self._crop_mode:
            self._on_crop_press(event)
            return
        # Text layers win hit-testing when they overlap an image —
        # text sits on top of images in the render order, so the
        # topmost-pixel-wins convention matches user expectation.
        txt_idx = self._hit_test_text(event.x, event.y)
        if txt_idx is not None:
            self._begin_text_drag(txt_idx, event)
            return
        img_idx = self._hit_test_image(event.x, event.y)
        if img_idx is not None:
            self._begin_image_drag(img_idx, event)

    def _on_canvas_drag(self, event):
        if self._crop_mode and self._crop_drag_start is not None:
            self._on_crop_drag(event)
            return
        if self._dragging_text_index is not None:
            self._on_text_drag(event)
            return
        if self._dragging_image_index is not None:
            self._on_image_drag(event)

    def _on_canvas_release(self, event):
        if self._crop_mode:
            self._on_crop_release(event)
            return
        if self._dragging_text_index is not None:
            self._on_text_release(event)
            return
        if self._dragging_image_index is not None:
            self._on_image_release(event)

    def _on_canvas_hover(self, event):
        # Cursor feedback: ``fleur`` (four-arrow move) when hovering
        # anything draggable (text or image), crosshair otherwise.
        # Crop-mode keeps its own cursor.
        if self._crop_mode or not self.video_path:
            return
        hit = (
            self._hit_test_text(event.x, event.y) is not None
            or self._hit_test_image(event.x, event.y) is not None
        )
        self.canvas.configure(cursor="fleur" if hit else "crosshair")

    def _on_resize(self, _event=None):
        if self.video_path:
            self.show_frame(self.current_time)
        else:
            self._draw_placeholder()

    # ------------------------------------------------------------------
    # Video API
    # ------------------------------------------------------------------
    def load_video(self, video_path, duration):
        self.stop()
        self.video_path = video_path
        self.duration = duration
        self.current_time = 0
        for item in self._placeholder_ids:
            self.canvas.delete(item)
        self._placeholder_ids.clear()
        self.canvas.configure(cursor="crosshair")
        self.show_frame(0)

    def show_frame(self, timestamp):
        if not self.video_path:
            return
        self.current_time = timestamp
        frame = get_frame_at(self.video_path, timestamp)
        if frame is None:
            return

        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return

        # Draw text + image overlays onto the LAYOUT frame (the export's
        # frame before its final downscale), then resize the composite
        # for display. That is what ffmpeg does at export time, so the
        # preview matches the export regardless of aspect preset, crop,
        # blur fill, rotation or quality preset. Ordering matters —
        # overlays run AFTER drawtext at export time, so images sit on
        # top. We mirror that order here.
        geom = self._current_geometry(frame.size)
        self._geometry = geom
        if geom.is_subrect:
            # Context view: show the whole source, compose the kept
            # window in place, and dim what the export throws away.
            region = geom.crop_source(frame)
            region = self._apply_text_overlay(region, timestamp)
            region = self._apply_image_overlay(region, timestamp)
            if region.size == frame.size:
                composited = region
            else:
                composited = frame.convert("RGB")
                composited.paste(region, geom.offset)
            self._layout_offset = geom.offset
            self._layout_size = region.size
        else:
            # Output view: rotation or blur fill reshapes the frame, so
            # show the exported frame itself.
            composited = geom.render(frame.convert("RGB"))
            composited = self._apply_text_overlay(composited, timestamp)
            composited = self._apply_image_overlay(composited, timestamp)
            self._layout_offset = (0, 0)
            self._layout_size = composited.size

        fw, fh = composited.size
        scale = min(cw / fw, ch / fh)
        new_w = max(1, int(fw * scale))
        new_h = max(1, int(fh * scale))
        rendered = composited.resize((new_w, new_h), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(rendered)
        self.canvas.delete("frame")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo, tags="frame")

        # Record the mapping so click→source-pixel conversions stay accurate.
        self._last_frame_rect = (
            cw // 2 - new_w // 2, ch // 2 - new_h // 2, new_w, new_h, fw, fh,
        )
        self._draw_layout_dim()
        self._draw_crop_overlay()

    def _draw_layout_dim(self):
        """Dim the parts of the source an aspect-preset crop discards."""
        self.canvas.delete("layoutdim")
        if self._crop_mode or not self._last_frame_rect:
            return  # the crop tool draws its own dimming
        _ox, _oy, _dw, _dh, fw, fh = self._last_frame_rect
        lx, ly = self._layout_offset
        lw, lh = self._layout_size
        if (lx, ly, lw, lh) == (0, 0, fw, fh):
            return
        x1, y1 = self._source_to_canvas(lx, ly)
        x2, y2 = self._source_to_canvas(lx + lw, ly + lh)
        ox, oy, dw, dh, _, _ = self._last_frame_rect
        for rect in (
            (ox, oy, ox + dw, y1),
            (ox, y2, ox + dw, oy + dh),
            (ox, y1, x1, y2),
            (x2, y1, ox + dw, y2),
        ):
            if rect[2] > rect[0] and rect[3] > rect[1]:
                self.canvas.create_rectangle(
                    *rect, fill=T.BG_BASE, outline="",
                    stipple="gray50", tags="layoutdim",
                )
        self.canvas.create_rectangle(
            x1, y1, x2, y2, outline=T.ACCENT, width=1, dash=(4, 3),
            tags="layoutdim",
        )

    def _apply_text_overlay(self, image, timestamp):
        """Render drawtext layers onto ``image`` at its native resolution.

        This is called with the source-sized frame so fontsize, position
        expressions, and box padding all use the same pixel space ffmpeg
        uses at export time. The caller resizes the composite for display
        — no scale-then-draw-then-scale math that desyncs preview/export.
        """
        if not self._text_layers_provider:
            return image
        try:
            layers = self._text_layers_provider() or []
        except Exception:
            return image
        if not layers:
            return image

        overlay = image.convert("RGBA")
        measure = ImageDraw.Draw(overlay)
        w, h = overlay.size

        # Rebuild the bbox table every time so hit-testing stays in sync with
        # whatever's actually on screen.
        self._text_bboxes = []

        for idx, layer in enumerate(layers):
            text = (layer.get("text") or "").strip()
            if not text:
                continue
            # Coerced, not compared raw: a project with "start": "soon"
            # would otherwise raise TypeError comparing str to float and
            # take down the preview, while the export renders it fine.
            start = coerce_float(layer.get("start", 0), 0.0)
            end = coerce_float(layer.get("end", 1e9), 1e9)
            if not (start <= timestamp <= end):
                continue

            # Normalise line endings the same way the drawtext builder does
            # so the preview and the export wrap identically.
            text = text.replace("\r\n", "\n").replace("\r", "\n")

            fontsize = max(6, coerce_int(layer.get("fontsize", 24), 24))
            from videokidnapper.utils.text_wrap import clamp_margin, fit_layer_text
            try:
                font_path = _font_path_for_preview(
                    layer.get("font", "Arial"),
                    bold=bool(layer.get("bold")),
                    italic=bool(layer.get("italic")),
                )
                # Keep the caption on screen exactly as the export does:
                # wrap to the layout width, shrink if still too tall.
                # utils.text_wrap is shared with the drawtext builder.
                text, font, _size = fit_layer_text(
                    layer, text,
                    lambda size, fp=font_path: ImageFont.truetype(fp, size),
                    fontsize, w, h,
                )
            except Exception:
                font = ImageFont.load_default()

            # `ink_dx/dy` is why the preview used to sit a few pixels
            # below the export, by an amount that grew with font size.
            # textbbox measures the INK, but multiline_text draws with
            # the ascender box's top-left at the given point — so the
            # glyphs land lower by the internal leading. ffmpeg's
            # drawtext positions by the ink, so subtracting the offset
            # is what makes `h-th-20` mean the same thing on both sides.
            ink_dx = ink_dy = 0
            try:
                bbox = measure.multiline_textbbox((0, 0), text, font=font,
                                                  spacing=0)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                ink_dx, ink_dy = bbox[0], bbox[1]
            except AttributeError:
                tw, th = measure.textsize(text, font=font)

            # Multi-line captions follow drawtext's line model instead of
            # Pillow's: every line is one "max glyph height" tall (the
            # ink from the tallest ascender to the deepest descender in
            # the whole caption), and th is that times the line count.
            # Pillow spaces lines tighter, so wrapped captions previewed
            # up to ~20 px lower than they exported.
            lines = text.split("\n")
            vmetrics = drawtext_vmetrics(font, text) if len(lines) > 1 else None
            if vmetrics:
                th = vmetrics[2] * len(lines)

            keyframes = layer.get("keyframes") or []
            if keyframes:
                # Motion path: the SAME interpolation the export compiles
                # into drawtext expressions, evaluated at this frame time.
                from videokidnapper.utils.keyframes import position_at
                kx, ky = position_at(keyframes, timestamp)
                x, y = int(round(kx)), int(round(ky))
            else:
                x, y = _resolve_position(
                    layer.get("position", ""), w, h, tw, th, pad=20,
                )
            # Same clamp as the export: no position (a drag near an edge,
            # a motion path) can push the caption or its outline off.
            m = clamp_margin(layer)
            x = min(max(x, m), max(m, w - tw - m))
            y = min(max(y, m), max(m, h - th - m))

            # Each layer renders on its own transparent scratch image that
            # is alpha-composited onto the frame. Drawing translucent fills
            # straight onto the frame does NOT blend — PIL's ImageDraw
            # overwrites pixels — so the box / shadow / `white@0.5`
            # watermark would preview opaque while exporting translucent.
            scratch = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(scratch)

            # Draw order mirrors ffmpeg's drawtext: box, then shadow,
            # then bordered glyphs.
            if layer.get("box"):
                # Match ffmpeg drawtext's boxborderw=8 default for Subtitle.
                pad = coerce_int(layer.get("boxborderw", 8), 8)
                draw.rectangle(
                    (x - pad, y - pad, x + tw + pad, y + th + pad),
                    fill=(0, 0, 0, 160),
                )

            color = _parse_color_rgba(layer.get("fontcolor", "white"))
            try:
                sx = coerce_int(layer.get("shadowx", 0))
                sy = coerce_int(layer.get("shadowy", 0))
                borderw = max(0, coerce_int(layer.get("borderw", 0)))
            except (TypeError, ValueError):
                sx = sy = borderw = 0

            def paint(dx, dy, fill, **kw):
                if vmetrics:
                    y_max, _y_min, line_h = vmetrics
                    for i, line in enumerate(lines):
                        draw.text(
                            (x + dx - ink_dx, y + dy + y_max + i * line_h),
                            line, fill=fill, font=font, anchor="ls", **kw,
                        )
                else:
                    draw.multiline_text(
                        (x + dx - ink_dx, y + dy - ink_dy), text,
                        fill=fill, font=font, spacing=0, **kw,
                    )

            if sx or sy:
                paint(sx, sy, _parse_color_rgba(
                    layer.get("shadowcolor", "black@0.7")))

            if borderw:
                paint(0, 0, color, stroke_width=borderw,
                      stroke_fill=_parse_color_rgba(
                          layer.get("bordercolor", "black")))
            else:
                paint(0, 0, color)

            overlay = Image.alpha_composite(overlay, scratch)

            # Record the hit-test bbox in source-pixel space; include the
            # box border so users can grab the edge comfortably.
            pad = coerce_int(layer.get("boxborderw", 8), 8) if layer.get("box") else 2
            self._text_bboxes.append(
                (idx, x - pad, y - pad, x + tw + pad, y + th + pad),
            )

        return overlay.convert("RGB")

    def _apply_image_overlay(self, image, timestamp):
        """Composite image-overlay layers onto ``image`` at native resolution.

        Mirrors what ``ffmpeg_backend._build_image_overlay_chain`` does
        at export time: for each layer, load the file (memoized by path),
        scale it by ``scale`` relative to the IMAGE'S OWN width (same as
        ffmpeg — the scale filter can't see the main video's width from
        inside the overlay input chain), apply opacity via alpha
        multiplication, then paste at the anchored position.

        Layers with an empty / missing path or an unreadable file are
        silently skipped. Timing obeys ``start`` / ``end`` the same way
        text layers do.
        """
        # Reset hit-test table before any early exit so a previous
        # frame's bboxes don't stick around once the layer list empties.
        self._image_bboxes = []

        if not self._image_layers_provider:
            return image
        try:
            layers = self._image_layers_provider() or []
        except Exception:
            return image
        # Filter to layers that are (a) renderable now and (b) have a real path.
        # ``idx`` is carried through so the drag-callback can address the
        # correct row in the source list even when some layers are
        # skipped here (empty path, out-of-range timing).
        visible = []
        for idx, L in enumerate(layers):
            if not L.get("path"):
                continue
            if not (coerce_float(L.get("start", 0), 0.0)
                    <= timestamp
                    <= coerce_float(L.get("end", 1e9), 1e9)):
                continue
            visible.append((idx, L))
        if not visible:
            return image

        composite = image.convert("RGBA")
        W, H = composite.size

        for idx, layer in visible:
            path = layer.get("path")
            # Cache hit? Use it. Cache miss: load once and remember.
            # Animated sticker? Pick the frame the export would show at
            # this instant. ffmpeg loops the overlay continuously from
            # the start of the encode, so the frame follows the timeline
            # position modulo the loop length — see frame_index_at.
            # Without this the preview sat on frame 0 while the exported
            # file moved, the one place preview/export parity did not
            # hold.
            if path not in self._image_anim_cache:
                from videokidnapper.utils.animated_media import (
                    load_animation_frames,
                )
                self._image_anim_cache[path] = load_animation_frames(path)
            animation = self._image_anim_cache[path]

            if animation is not None:
                from videokidnapper.utils.animated_media import frame_index_at

                frames, durations = animation
                src = frames[frame_index_at(durations, timestamp)]
            else:
                src = self._image_cache.get(path)
                if src is None:
                    try:
                        src = Image.open(path).convert("RGBA")
                    except Exception:
                        # Bad path / unreadable file — cache the failure
                        # as None so we don't retry every frame tick.
                        self._image_cache[path] = None
                        continue
                    self._image_cache[path] = src
                elif src is None:
                    continue  # previously-failed load

            # Scale relative to the image's own width (matches ffmpeg).
            scale = max(0.01, min(1.0, coerce_float(layer.get("scale", 0.25), 0.25)))
            sw, sh = src.size
            new_w = max(1, int(sw * scale))
            new_h = max(1, int(sh * scale))
            scaled = src.resize((new_w, new_h), Image.LANCZOS)

            # Opacity: pre-multiply alpha into the overlay's alpha band.
            opacity = max(0.0, min(1.0, coerce_float(layer.get("opacity", 1.0), 1.0)))
            if opacity < 0.999:
                alpha = scaled.split()[3]
                alpha = alpha.point(lambda v, o=opacity: int(v * o))
                scaled.putalpha(alpha)

            # Position — drag-override wins when present; otherwise
            # use the anchor, same way the ffmpeg overlay filter does.
            drag_x = layer.get("x")
            drag_y = layer.get("y")
            if isinstance(drag_x, int) and isinstance(drag_y, int) \
                    and drag_x >= 0 and drag_y >= 0:
                x, y = drag_x, drag_y
            else:
                x, y = _overlay_anchor_to_xy(
                    layer.get("position", "top_right"), W, H, new_w, new_h,
                )

            composite.alpha_composite(scaled, dest=(x, y))

            # Record bbox in source-pixel space so clicks on this
            # overlay in subsequent frames can be hit-tested.
            self._image_bboxes.append(
                (idx, x, y, x + new_w, y + new_h),
            )

        return composite.convert("RGB")

    def clear(self):
        self.stop()
        self.video_path = None
        self.duration = 0
        self._photo = None
        self.canvas.delete("frame")
        self.canvas.configure(cursor="hand2" if self._on_empty_click else "crosshair")
        self._draw_placeholder()

    # ------------------------------------------------------------------
    # Play / Pause
    # ------------------------------------------------------------------
    def toggle_play(self, start=None, end=None):
        if self._playing:
            self.stop()
        else:
            self.play(start=start, end=end)

    def play(self, start=None, end=None):
        if not self.video_path:
            return
        if start is not None:
            self.current_time = start
        self._play_end = end if end is not None else self.duration
        self._playing = True

        # Prefer real-time A/V playback when the optional deps are
        # installed. Falls through to the scrub loop on ImportError or
        # on the audio-device-missing path inside AudioVideoPlayer.
        if playback.is_available():
            self._start_av_playback(start or 0.0, self._play_end)
        else:
            self._tick()

    def stop(self):
        self._playing = False
        if self._play_after_id is not None:
            try:
                self.after_cancel(self._play_after_id)
            except Exception:
                pass
            self._play_after_id = None
        # A/V player cleanup — safe to call even when one isn't running.
        if self._av_player is not None:
            try:
                self._av_player.stop()
            except Exception:
                pass
            self._av_player = None
        if self._av_time_after_id is not None:
            try:
                self.after_cancel(self._av_time_after_id)
            except Exception:
                pass
            self._av_time_after_id = None

    # ------------------------------------------------------------------
    # Real-time A/V playback branch
    # ------------------------------------------------------------------
    def _start_av_playback(self, start, end):
        """Launch an AudioVideoPlayer and wire its frame output to the canvas."""
        def on_frame(img, ts):
            # Called from the video decode thread — marshal to Tk main.
            if not self.winfo_exists():
                return
            self.after(0, self._av_render_frame, img, ts)

        def on_finished(reason):
            if not self.winfo_exists():
                return
            self.after(0, self._av_on_finished, reason)

        try:
            self._av_player = playback.AudioVideoPlayer(
                self.video_path,
                render_callback=on_frame,
                on_finished=on_finished,
            )
            self._av_player.play(start=start, end=end)
        except Exception:
            # Construction failed (bad path, missing deps at runtime).
            # Fall back to the scrub loop so the Play button still works.
            self._av_player = None
            self._tick()
            return
        # Poll the A/V clock a few times a second so ``current_time``
        # stays in sync — keyboard-nudge / slider-mark reads it, and we
        # don't want those reading a stale value while playback runs.
        self._av_poll_time()

    def _av_render_frame(self, img, ts):
        """Main-thread render path for a frame produced by AudioVideoPlayer."""
        if not self._playing or self._av_player is None:
            return
        self.current_time = ts
        cw = self.canvas.winfo_width()
        ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10:
            return
        fw, fh = img.size
        scale = min(cw / fw, ch / fh)
        new_w = max(1, int(fw * scale))
        new_h = max(1, int(fh * scale))
        # Match the scrub path: composite overlays onto the source-sized
        # frame, then resize. Keeps preview-matches-export alignment.
        composited = self._apply_text_overlay(img, ts)
        rendered = composited.resize((new_w, new_h), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(rendered)
        self.canvas.delete("frame")
        self.canvas.create_image(
            cw // 2, ch // 2, image=self._photo, tags="frame",
        )
        self._last_frame_rect = (
            cw // 2 - new_w // 2, ch // 2 - new_h // 2, new_w, new_h, fw, fh,
        )
        self._draw_crop_overlay()

    def _av_poll_time(self):
        """Mirror the A/V player's clock into ``self.current_time``."""
        if self._av_player is None or not self._playing:
            return
        try:
            self.current_time = self._av_player.current_time()
        except Exception:
            pass
        # 200ms is fine for the external consumers (keyboard nudge, etc.)
        self._av_time_after_id = self.after(200, self._av_poll_time)

    def _av_on_finished(self, reason):
        """Tear down when the A/V player reports end-of-clip or stop."""
        self._playing = False
        self._av_player = None
        if self._av_time_after_id is not None:
            try:
                self.after_cancel(self._av_time_after_id)
            except Exception:
                pass
            self._av_time_after_id = None

    def _tick(self):
        if not self._playing:
            return
        self.show_frame(self.current_time)
        step = 1.0 / self._PLAY_FPS
        self.current_time += step
        if self._play_end is not None and self.current_time >= self._play_end:
            self.stop()
            return
        self._play_after_id = self.after(self._PLAY_MS, self._tick)

    # ------------------------------------------------------------------
    # Text-layer drag
    # ------------------------------------------------------------------
    def set_text_position_callback(self, callback):
        """Register ``callback(index, src_x, src_y)`` to persist drags."""
        self._text_position_cb = callback

    def _hit_test_text(self, canvas_x, canvas_y):
        """Return the layer index whose rendered bbox contains the click.

        Top-most (last-drawn) wins when layers overlap. Returns ``None`` if
        the click isn't on any text.
        """
        if not self._text_bboxes:
            return None
        src = self._canvas_to_layout(canvas_x, canvas_y)
        if not src:
            return None
        sx, sy = src
        for idx, x1, y1, x2, y2 in reversed(self._text_bboxes):
            if x1 <= sx <= x2 and y1 <= sy <= y2:
                return idx
        return None

    def _begin_text_drag(self, idx, event):
        src = self._canvas_to_layout(event.x, event.y)
        if not src:
            return
        bbox = next((b for b in self._text_bboxes if b[0] == idx), None)
        if bbox is None:
            return
        _, x1, y1, _, _ = bbox
        self._dragging_text_index = idx
        # Offset from click to text origin, in source pixels.
        self._text_drag_offset = (src[0] - x1, src[1] - y1)
        self.canvas.configure(cursor="fleur")

    def _on_text_drag(self, event):
        src = self._canvas_to_layout(event.x, event.y)
        if not src:
            return
        dx, dy = self._text_drag_offset
        new_x = int(src[0] - dx)
        new_y = int(src[1] - dy)

        # Snap against frame center / padded edges / peer-layer edges.
        snapped_x, snapped_y, hits = self._snap_to_guides(new_x, new_y)
        snapped_x = max(0, snapped_x)
        snapped_y = max(0, snapped_y)
        self._draw_snap_guides(hits)

        if self._text_position_cb:
            try:
                self._text_position_cb(
                    self._dragging_text_index, snapped_x, snapped_y,
                )
            except Exception:
                pass

    def _on_text_release(self, _event):
        self._dragging_text_index = None
        self.canvas.configure(cursor="crosshair")
        self.canvas.delete("snap")

    # ------------------------------------------------------------------
    # Image-overlay drag — same shape as text drag. No snap-to-guides
    # pass: images are typically large (logos, stickers) and snapping
    # them to the same targets as small text looks wrong. A dedicated
    # image-snap with its own targets is a future enhancement.
    # ------------------------------------------------------------------
    def set_image_position_callback(self, callback):
        """Register ``callback(index, src_x, src_y)`` to persist drags."""
        self._image_position_cb = callback

    def _hit_test_image(self, canvas_x, canvas_y):
        """Return the image-layer index whose rendered bbox contains the click.

        Top-most (last-drawn) wins when layers overlap. Returns ``None``
        if the click isn't on any image overlay.
        """
        if not self._image_bboxes:
            return None
        src = self._canvas_to_layout(canvas_x, canvas_y)
        if not src:
            return None
        sx, sy = src
        for idx, x1, y1, x2, y2 in reversed(self._image_bboxes):
            if x1 <= sx <= x2 and y1 <= sy <= y2:
                return idx
        return None

    def _begin_image_drag(self, idx, event):
        src = self._canvas_to_layout(event.x, event.y)
        if not src:
            return
        bbox = next((b for b in self._image_bboxes if b[0] == idx), None)
        if bbox is None:
            return
        _, x1, y1, _, _ = bbox
        self._dragging_image_index = idx
        # Offset from click to image top-left, in source pixels. This
        # keeps the image from "jumping" on first mouse movement — the
        # same grab-point stays under the cursor for the whole drag.
        self._image_drag_offset = (src[0] - x1, src[1] - y1)
        self.canvas.configure(cursor="fleur")

    def _on_image_drag(self, event):
        src = self._canvas_to_layout(event.x, event.y)
        if not src:
            return
        dx, dy = self._image_drag_offset
        new_x = max(0, int(src[0] - dx))
        new_y = max(0, int(src[1] - dy))
        if self._image_position_cb:
            try:
                self._image_position_cb(
                    self._dragging_image_index, new_x, new_y,
                )
            except Exception:
                pass

    def _on_image_release(self, _event):
        self._dragging_image_index = None
        self.canvas.configure(cursor="crosshair")

    def _snap_to_guides(self, new_x, new_y):
        """Apply snap-math against the current set of peer layer bboxes.

        Returns ``(snapped_x, snapped_y, hits)`` where ``hits`` is the
        list the caller uses to draw guide lines. The dragged layer
        itself is excluded from peer targets so it can't snap to its
        own edges.
        """
        if not self._last_frame_rect:
            return new_x, new_y, []
        fw, fh = self._layout_size
        if fw <= 0 or fh <= 0:
            return new_x, new_y, []
        dragged_idx = self._dragging_text_index

        # Size of the dragged layer's bbox (source-pixel space). Take
        # it from the last render so it reflects the current fontsize.
        tw = th = 0
        for idx, x1, y1, x2, y2 in self._text_bboxes:
            if idx == dragged_idx:
                tw, th = x2 - x1, y2 - y1
                break
        if tw <= 0 or th <= 0:
            return new_x, new_y, []

        others = [b for b in self._text_bboxes if b[0] != dragged_idx]
        targets = build_targets(fw, fh, others, edge_pad=20)
        return apply_snap(new_x, new_y, tw, th, targets, threshold=8)

    def _draw_snap_guides(self, hits):
        """Overlay dashed guide lines on the canvas for active snap axes."""
        self.canvas.delete("snap")
        if not hits or not self._last_frame_rect:
            return
        lx, ly = self._layout_offset
        lw, lh = self._layout_size
        x_top, y_top = self._source_to_canvas(lx, ly)
        x_bot, y_bot = self._source_to_canvas(lx + lw, ly + lh)
        for hit in hits:
            if hit.axis == "x":
                # Layout x → canvas x via the same linear map used for
                # clicks. Draw a vertical line across the layout frame.
                cx, _ = self._source_to_canvas(lx + hit.position, ly)
                self.canvas.create_line(
                    cx, y_top, cx, y_bot,
                    fill=T.ACCENT, width=1, dash=(4, 3), tags="snap",
                )
            else:
                _, cy = self._source_to_canvas(lx, ly + hit.position)
                self.canvas.create_line(
                    x_top, cy, x_bot, cy,
                    fill=T.ACCENT, width=1, dash=(4, 3), tags="snap",
                )

    # ------------------------------------------------------------------
    # Crop overlay
    # ------------------------------------------------------------------
    def enable_crop_mode(self, enabled, on_change=None):
        self._crop_mode = bool(enabled)
        self._crop_change_cb = on_change
        self.canvas.configure(cursor="tcross" if enabled else "crosshair")
        # Re-render: crop mode switches between the output and context
        # views and changes the layout frame captions are placed in.
        self.refresh_overlay()
        self._draw_crop_overlay()

    def set_crop(self, crop_rect):
        """Programmatic crop update; `crop_rect` is source-pixel dict or None."""
        self._crop_rect = crop_rect
        self._draw_crop_overlay()

    def get_crop(self):
        return self._crop_rect

    def _canvas_to_source(self, cx, cy):
        """Map a canvas coordinate to source-video pixel space."""
        if not self._last_frame_rect:
            return None
        ox, oy, dw, dh, fw, fh = self._last_frame_rect
        if dw <= 0 or dh <= 0:
            return None
        # Clamp to the displayed frame area.
        rx = min(max(cx - ox, 0), dw)
        ry = min(max(cy - oy, 0), dh)
        return int(rx * fw / dw), int(ry * fh / dh)

    def _canvas_to_layout(self, cx, cy):
        """Map a canvas coordinate to layout-frame pixels (captions, stickers)."""
        disp = self._canvas_to_source(cx, cy)
        if not disp:
            return None
        lx, ly = self._layout_offset
        lw, lh = self._layout_size
        x = min(max(disp[0] - lx, 0), max(0, lw))
        y = min(max(disp[1] - ly, 0), max(0, lh))
        return int(x), int(y)

    def _source_to_canvas(self, sx, sy):
        if not self._last_frame_rect:
            return (0, 0)
        ox, oy, dw, dh, fw, fh = self._last_frame_rect
        return ox + sx * dw / fw, oy + sy * dh / fh

    def _on_crop_press(self, event):
        if not self._crop_mode or not self.video_path:
            return
        pt = self._canvas_to_source(event.x, event.y)
        if not pt:
            return
        self._crop_drag_start = pt

    def _on_crop_drag(self, event):
        if not self._crop_mode or not self._crop_drag_start:
            return
        pt = self._canvas_to_source(event.x, event.y)
        if not pt:
            return
        x0, y0 = self._crop_drag_start
        x1, y1 = pt
        x, y = min(x0, x1), min(y0, y1)
        w, h = abs(x1 - x0), abs(y1 - y0)
        self._crop_rect = {"x": x, "y": y, "w": max(2, w), "h": max(2, h)}
        self._draw_crop_overlay()

    def _on_crop_release(self, _event):
        if not self._crop_mode:
            return
        self._crop_drag_start = None
        if self._crop_change_cb:
            try:
                self._crop_change_cb(self._crop_rect)
            except Exception:
                pass
        # Captions re-flow into the new crop window.
        self.refresh_overlay()

    def _draw_crop_overlay(self):
        self.canvas.delete("crop")
        if not self._crop_rect or not self._last_frame_rect:
            return
        cr = self._crop_rect
        x1, y1 = self._source_to_canvas(cr["x"], cr["y"])
        x2, y2 = self._source_to_canvas(cr["x"] + cr["w"], cr["y"] + cr["h"])
        # Dim outside the crop with four rectangles.
        ox, oy, dw, dh, _, _ = self._last_frame_rect
        outer = (ox, oy, ox + dw, oy + dh)
        for rect in (
            (outer[0], outer[1], outer[2], y1),
            (outer[0], y2, outer[2], outer[3]),
            (outer[0], y1, x1, y2),
            (x2, y1, outer[2], y2),
        ):
            self.canvas.create_rectangle(
                *rect, fill=T.BG_BASE, outline="",
                stipple="gray50", tags="crop",
            )
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline=T.ACCENT, width=2, tags="crop",
        )


# ---------------------------------------------------------------------------
# Helpers for the preview overlay
# ---------------------------------------------------------------------------

def _font_path_for_preview(font_name, bold=False, italic=False):
    from videokidnapper.ui.text_layers import _find_font_path
    return _find_font_path(font_name, bold=bold, italic=italic)


def _pos_map(pad):
    return {
        "bottom_center": lambda w, h, tw, th: ((w - tw) // 2, h - th - pad),
        "top_center":    lambda w, h, tw, th: ((w - tw) // 2, pad),
        "center":        lambda w, h, tw, th: ((w - tw) // 2, (h - th) // 2),
        "top_left":      lambda w, h, tw, th: (pad, pad),
        "top_right":     lambda w, h, tw, th: (w - tw - pad, pad),
        "bottom_left":   lambda w, h, tw, th: (pad, h - th - pad),
        "bottom_right":  lambda w, h, tw, th: (w - tw - pad, h - th - pad),
    }


def _resolve_position(pos_expr, w, h, tw, th, pad=20):
    """Approximate ffmpeg's drawtext position expressions for preview only."""
    # Custom positions stored as raw pixel coords ``"<x>:<y>"`` — handle them
    # first so the preset pattern-matching below never swallows them.
    numeric = _parse_numeric_position(pos_expr)
    if numeric is not None:
        return numeric

    pos_map = _pos_map(pad)
    # ffmpeg expressions we build look like "(w-tw)/2:h-th-20" — pattern-match
    # against each one so positions stay accurate regardless of the pad value.
    if "h-th-20" in pos_expr and "w-tw" in pos_expr and "/2" in pos_expr:
        return pos_map["bottom_center"](w, h, tw, th)
    if pos_expr.endswith(":20") and "w-tw" in pos_expr and "/2" in pos_expr:
        return pos_map["top_center"](w, h, tw, th)
    if "h-th" in pos_expr and "w-tw" in pos_expr and "/2" in pos_expr:
        return pos_map["center"](w, h, tw, th)
    if pos_expr == "20:20":
        return pos_map["top_left"](w, h, tw, th)
    if pos_expr.startswith("w-tw-20:20"):
        return pos_map["top_right"](w, h, tw, th)
    if pos_expr.startswith("20:h-th-20"):
        return pos_map["bottom_left"](w, h, tw, th)
    if "w-tw-20" in pos_expr and "h-th-20" in pos_expr:
        return pos_map["bottom_right"](w, h, tw, th)
    return pos_map["bottom_center"](w, h, tw, th)


def _parse_numeric_position(pos_expr):
    """Return ``(int_x, int_y)`` if ``pos_expr`` is a plain ``"<x>:<y>"`` pair.

    Returns ``None`` for anything that contains an ffmpeg variable or function
    (``w``, ``h``, ``tw``, ``th``, parentheses, arithmetic operators), so preset
    expressions keep flowing through the pattern-matched branches.
    """
    if not pos_expr or ":" not in pos_expr:
        return None
    parts = pos_expr.split(":", 1)
    if len(parts) != 2:
        return None
    try:
        return int(float(parts[0])), int(float(parts[1]))
    except ValueError:
        return None


_OVERLAY_PAD = 20  # mirror ffmpeg_backend._OVERLAY_PAD


def _overlay_anchor_to_xy(anchor, main_w, main_h, overlay_w, overlay_h):
    """Resolve an overlay-anchor name to a ``(x, y)`` top-left pixel pair.

    Computes the same positions ``ffmpeg_backend._overlay_position_expr``
    produces as filter-expression strings — just in concrete pixel
    values here because the preview uses PIL, not lavfi. Keeping these
    in lockstep is what makes the live preview match the export.
    """
    pad = _OVERLAY_PAD
    return {
        "top_left":      (pad,                      pad),
        "top_right":     (main_w - overlay_w - pad, pad),
        "bottom_left":   (pad,                      main_h - overlay_h - pad),
        "bottom_right":  (main_w - overlay_w - pad, main_h - overlay_h - pad),
        "center":        ((main_w - overlay_w) // 2, (main_h - overlay_h) // 2),
        "top_center":    ((main_w - overlay_w) // 2, pad),
        "bottom_center": ((main_w - overlay_w) // 2, main_h - overlay_h - pad),
    }.get(anchor, (main_w - overlay_w - pad, pad))


_NAMED_COLORS = {
    "white":  (255, 255, 255),
    "black":  (0, 0, 0),
}


def _parse_color(value):
    if not value:
        return (255, 255, 255)
    v = value.split("@")[0].strip()
    if v.startswith("#") and len(v) == 7:
        try:
            return tuple(int(v[i:i + 2], 16) for i in (1, 3, 5))
        except ValueError:
            return (255, 255, 255)
    return _NAMED_COLORS.get(v.lower(), (255, 255, 255))


def _parse_color_rgba(value, default_alpha=255):
    """Like ``_parse_color`` but honours ffmpeg's ``color@alpha`` suffix.

    ``black@0.7`` resolves to ``(0, 0, 0, 178)`` so shadows composite with
    the same translucency the export renders.
    """
    rgb = _parse_color(value)
    alpha = default_alpha
    if value and "@" in value:
        try:
            alpha = max(0, min(255, int(float(value.split("@", 1)[1]) * 255)))
        except ValueError:
            pass
    return (*rgb, alpha)
