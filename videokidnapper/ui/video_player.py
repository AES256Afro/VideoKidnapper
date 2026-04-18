"""Video preview canvas with Play/Pause, live text-layer overlay, and DnD.

Playback is frame-scrub based (re-runs ffmpeg per tick) rather than true
decode — the frame cache makes repeated seeks cheap. It targets ~8 fps,
plenty for previewing trims. For glitch-free full-rate playback we'd need
PyAV or imageio-ffmpeg, which is out of scope.
"""

import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageTk

from videokidnapper.core.preview import get_frame_at
from videokidnapper.ui import theme as T


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
        self._playing = False
        self._play_after_id = None
        self._play_end = None

        # Crop state: a rect in SOURCE pixel coords, or None when disabled.
        self._crop_mode = False
        self._crop_rect = None        # {"x","y","w","h"} in source pixels
        self._crop_drag_start = None  # (canvas_x, canvas_y)
        self._crop_change_cb = None
        self._last_frame_rect = None  # (cx, cy, dw, dh, fw, fh) for mapping canvas↔source

        # Text-layer drag state. `_text_bboxes` is rebuilt on each overlay
        # render so hit-testing uses the exact rendered position.
        self._text_bboxes = []        # [(index, src_x1, src_y1, src_x2, src_y2)]
        self._dragging_text_index = None
        self._text_drag_offset = (0, 0)  # (src dx, src dy) from click to text origin
        self._text_position_cb = None    # callback(index, src_x, src_y)

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
    # Text-layer live preview
    # ------------------------------------------------------------------
    def set_text_layers_provider(self, provider):
        """`provider` is a zero-arg callable returning the current layer list."""
        self._text_layers_provider = provider

    def refresh_overlay(self):
        """Re-render the current frame with latest text overlays."""
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
        idx = self._hit_test_text(event.x, event.y)
        if idx is not None:
            self._begin_text_drag(idx, event)

    def _on_canvas_drag(self, event):
        if self._crop_mode and self._crop_drag_start is not None:
            self._on_crop_drag(event)
            return
        if self._dragging_text_index is not None:
            self._on_text_drag(event)

    def _on_canvas_release(self, event):
        if self._crop_mode:
            self._on_crop_release(event)
            return
        if self._dragging_text_index is not None:
            self._on_text_release(event)

    def _on_canvas_hover(self, event):
        # Cursor feedback: hand when hovering over a draggable text layer,
        # crosshair otherwise (leave crop-mode cursor alone).
        if self._crop_mode or not self.video_path:
            return
        idx = self._hit_test_text(event.x, event.y)
        self.canvas.configure(cursor="fleur" if idx is not None else "crosshair")

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

        fw, fh = frame.size
        scale = min(cw / fw, ch / fh)
        new_w = max(1, int(fw * scale))
        new_h = max(1, int(fh * scale))

        # Draw text overlays onto the SOURCE-sized frame, then resize the
        # whole composite. This is what ffmpeg does at export time, so the
        # preview matches the export proportionally regardless of source
        # resolution or preset scaling.
        composited = self._apply_text_overlay(frame, timestamp)
        rendered = composited.resize((new_w, new_h), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(rendered)
        self.canvas.delete("frame")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo, tags="frame")

        # Record the mapping so click→source-pixel conversions stay accurate.
        self._last_frame_rect = (
            cw // 2 - new_w // 2, ch // 2 - new_h // 2, new_w, new_h, fw, fh,
        )
        self._draw_crop_overlay()

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
        draw = ImageDraw.Draw(overlay)
        w, h = overlay.size

        # Rebuild the bbox table every time so hit-testing stays in sync with
        # whatever's actually on screen.
        self._text_bboxes = []

        for idx, layer in enumerate(layers):
            text = (layer.get("text") or "").strip()
            if not text:
                continue
            start = layer.get("start", 0)
            end = layer.get("end", 1e9)
            if not (start <= timestamp <= end):
                continue

            fontsize = max(6, int(layer.get("fontsize", 24)))
            try:
                font_path = _font_path_for_preview(layer.get("font", "Arial"))
                font = ImageFont.truetype(font_path, fontsize)
            except Exception:
                font = ImageFont.load_default()

            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except AttributeError:
                tw, th = draw.textsize(text, font=font)

            x, y = _resolve_position(
                layer.get("position", ""), w, h, tw, th, pad=20,
            )

            if layer.get("box"):
                # Match ffmpeg drawtext's boxborderw=8 default for Subtitle.
                pad = int(layer.get("boxborderw", 8))
                draw.rectangle(
                    (x - pad, y - pad, x + tw + pad, y + th + pad),
                    fill=(0, 0, 0, 160),
                )

            color = _parse_color(layer.get("fontcolor", "white"))
            draw.text((x, y), text, fill=color, font=font)

            # Record the hit-test bbox in source-pixel space; include the
            # box border so users can grab the edge comfortably.
            pad = int(layer.get("boxborderw", 8)) if layer.get("box") else 2
            self._text_bboxes.append(
                (idx, x - pad, y - pad, x + tw + pad, y + th + pad),
            )

        return overlay.convert("RGB")

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
        self._tick()

    def stop(self):
        self._playing = False
        if self._play_after_id is not None:
            try:
                self.after_cancel(self._play_after_id)
            except Exception:
                pass
            self._play_after_id = None

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
        src = self._canvas_to_source(canvas_x, canvas_y)
        if not src:
            return None
        sx, sy = src
        for idx, x1, y1, x2, y2 in reversed(self._text_bboxes):
            if x1 <= sx <= x2 and y1 <= sy <= y2:
                return idx
        return None

    def _begin_text_drag(self, idx, event):
        src = self._canvas_to_source(event.x, event.y)
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
        src = self._canvas_to_source(event.x, event.y)
        if not src:
            return
        dx, dy = self._text_drag_offset
        new_x = max(0, int(src[0] - dx))
        new_y = max(0, int(src[1] - dy))
        if self._text_position_cb:
            try:
                self._text_position_cb(self._dragging_text_index, new_x, new_y)
            except Exception:
                pass

    def _on_text_release(self, _event):
        self._dragging_text_index = None
        self.canvas.configure(cursor="crosshair")

    # ------------------------------------------------------------------
    # Crop overlay
    # ------------------------------------------------------------------
    def enable_crop_mode(self, enabled, on_change=None):
        self._crop_mode = bool(enabled)
        self._crop_change_cb = on_change
        self.canvas.configure(cursor="tcross" if enabled else "crosshair")
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

def _font_path_for_preview(font_name):
    from videokidnapper.ui.text_layers import _find_font_path
    return _find_font_path(font_name)


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
