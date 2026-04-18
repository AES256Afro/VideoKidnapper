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

    def _snap_to_guides(self, new_x, new_y):
        """Apply snap-math against the current set of peer layer bboxes.

        Returns ``(snapped_x, snapped_y, hits)`` where ``hits`` is the
        list the caller uses to draw guide lines. The dragged layer
        itself is excluded from peer targets so it can't snap to its
        own edges.
        """
        if not self._last_frame_rect:
            return new_x, new_y, []
        _ox, _oy, _dw, _dh, fw, fh = self._last_frame_rect
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
        ox, oy, dw, dh, fw, fh = self._last_frame_rect
        for hit in hits:
            if hit.axis == "x":
                # Source-pixel x → canvas x via the same linear map used
                # for clicks. Draw a vertical line across the frame.
                cx = ox + hit.position * dw / fw
                self.canvas.create_line(
                    cx, oy, cx, oy + dh,
                    fill=T.ACCENT, width=1, dash=(4, 3), tags="snap",
                )
            else:
                cy = oy + hit.position * dh / fh
                self.canvas.create_line(
                    ox, cy, ox + dw, cy,
                    fill=T.ACCENT, width=1, dash=(4, 3), tags="snap",
                )

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
