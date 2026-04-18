# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Thumbnail strip that lives above the waveform on the timeline card.

Thumb extraction runs in a background thread (ffmpeg is slow), results
are downscaled once and held as PhotoImages on the widget to keep them
alive through Tk's refcount GC. Clicking any thumb seeks the timeline.

The widget re-uses ``core.preview.extract_thumbnail_strip``, which is
backed by the same LRU cache as the main preview — so thumbs cost
nothing to regenerate on the same video inside one session.
"""

import threading
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

from videokidnapper.core.preview import extract_thumbnail_strip
from videokidnapper.ui import theme as T


class ThumbnailStrip(ctk.CTkFrame):
    """A single-row strip of thumbnails with a selection overlay.

    Callers use:
      - ``load(path, duration)`` on video load
      - ``set_range(start, end)`` when the trim range changes
      - ``on_seek=callback`` constructor arg; fired with ``timestamp_s``
        on click. Ignored while thumbs are still loading.
    """

    _HEIGHT = 62
    _THUMB_H = 54
    _COUNT = 32

    def __init__(self, master, on_seek=None, **kwargs):
        super().__init__(
            master,
            height=self._HEIGHT,
            fg_color="transparent",
            **kwargs,
        )
        self.pack_propagate(False)

        self._video_path = None
        self._duration = 0.0
        self._thumbs = []      # [(timestamp, PhotoImage)], kept alive on self
        self._thumb_w = 96     # re-derived each render from canvas width
        self._on_seek = on_seek
        self._start = 0.0
        self._end = 0.0
        self._loading = False
        # Generation counter so a late worker from a previous video can't
        # overwrite thumbs produced for the current one.
        self._gen = 0

        self.canvas = tk.Canvas(
            self, height=self._HEIGHT, bg=T.BG_SURFACE,
            highlightthickness=0, cursor="hand2",
        )
        self.canvas.pack(fill="x", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._render())
        self.canvas.bind("<Button-1>", self._on_click)

        self._hint = self.canvas.create_text(
            0, self._HEIGHT // 2,
            text="Thumbnails will appear here",
            fill=T.TEXT_DIM, font=(T.FONT_FAMILY, 10),
            anchor="center",
        )

    # ------------------------------------------------------------------
    def load(self, video_path, duration):
        """Kick off background thumbnail extraction for ``video_path``."""
        self._gen += 1
        gen = self._gen
        self._video_path = video_path
        self._duration = float(duration) if duration else 0.0
        self._thumbs = []
        self._start = 0.0
        self._end = self._duration
        self._loading = True
        self._render()

        def worker():
            try:
                frames = extract_thumbnail_strip(
                    video_path, self._duration, count=self._COUNT,
                )
            except Exception:
                frames = []
            if not self.winfo_exists() or gen != self._gen:
                return
            # Downscale on the worker thread — PhotoImage construction
            # itself has to happen on the main thread.
            target_h = self._THUMB_H
            resized = []
            total = max(1, len(frames))
            for i, frame in enumerate(frames):
                fw, fh = frame.size
                if fh <= 0:
                    continue
                scale = target_h / fh
                new_w = max(1, int(fw * scale))
                thumb = frame.resize((new_w, target_h), Image.LANCZOS)
                ts = (i + 0.5) * self._duration / total
                resized.append((ts, thumb))

            def finish():
                if gen != self._gen or not self.winfo_exists():
                    return
                self._thumbs = [
                    (ts, ImageTk.PhotoImage(img)) for ts, img in resized
                ]
                self._loading = False
                self._render()

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def set_range(self, start, end):
        """Update the selection overlay without rebuilding thumbs."""
        self._start = float(start)
        self._end = float(end)
        self._render_overlay()

    def clear(self):
        """Reset to the empty state (no video loaded)."""
        self._gen += 1
        self._video_path = None
        self._duration = 0.0
        self._thumbs = []
        self._start = 0.0
        self._end = 0.0
        self._loading = False
        self._render()

    # ------------------------------------------------------------------
    def _on_click(self, event):
        if not self._video_path or self._duration <= 0 or self._loading:
            return
        if not self._on_seek:
            return
        w = self.canvas.winfo_width()
        if w < 10:
            return
        ts = max(0.0, min(self._duration, event.x / w * self._duration))
        try:
            self._on_seek(ts)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _render(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 20:
            return
        self.canvas.delete("thumbs")
        self.canvas.delete("overlay")

        if not self._thumbs:
            self.canvas.coords(self._hint, w // 2, h // 2)
            self.canvas.itemconfig(
                self._hint, state="normal",
                text=(
                    "Loading thumbnails..."
                    if self._loading
                    else "Thumbnails will appear here"
                ),
            )
            return
        self.canvas.itemconfig(self._hint, state="hidden")

        n = len(self._thumbs)
        # The available width is split evenly across thumbs; each image
        # is rendered centered in its cell so variable aspect ratios
        # (9:16 clips, etc.) don't push neighbors out of place.
        cell_w = w / n
        for i, (_ts, photo) in enumerate(self._thumbs):
            cx = (i + 0.5) * cell_w
            cy = h // 2
            self.canvas.create_image(cx, cy, image=photo, tags="thumbs")

        self._render_overlay()

    def _render_overlay(self):
        """Redraw only the selection overlay on top of existing thumbs."""
        self.canvas.delete("overlay")
        if not self._thumbs or self._duration <= 0:
            return
        if self._end <= self._start:
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        x1 = (self._start / self._duration) * w
        x2 = (self._end / self._duration) * w
        # Dim areas outside the selection so the in-range thumbs read as
        # "selected". Stipple matches the waveform's treatment.
        if x1 > 0:
            self.canvas.create_rectangle(
                0, 0, x1, h,
                fill=T.BG_BASE, outline="",
                stipple="gray50", tags="overlay",
            )
        if x2 < w:
            self.canvas.create_rectangle(
                x2, 0, w, h,
                fill=T.BG_BASE, outline="",
                stipple="gray50", tags="overlay",
            )
        # Thin accent border around the selected window.
        self.canvas.create_rectangle(
            x1, 1, x2, h - 1,
            outline=T.ACCENT, width=2, tags="overlay",
        )
