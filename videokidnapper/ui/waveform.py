# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Canvas-based audio waveform strip.

Ffmpeg extraction is slow, so the widget caches peaks per video path and
re-renders instantly on resize and on range changes.
"""

import threading
import tkinter as tk

import customtkinter as ctk

from videokidnapper.core.ffmpeg_backend import extract_waveform
from videokidnapper.ui import theme as T


class WaveformStrip(ctk.CTkFrame):
    """Draws a vertical-bar waveform; highlights the selected [start, end]."""

    _BUCKETS = 400
    _HEIGHT = 46

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", height=self._HEIGHT, **kwargs)
        self._video_path = None
        self._duration = 0.0
        self._peaks = []
        self._start = 0.0
        self._end = 0.0
        self._loading = False

        self.canvas = tk.Canvas(
            self, height=self._HEIGHT, bg=T.BG_SURFACE, highlightthickness=0,
        )
        self.canvas.pack(fill="x", expand=True)
        self.canvas.bind("<Configure>", self._render)

        self._hint = self.canvas.create_text(
            0, self._HEIGHT // 2, text="Waveform will appear here",
            fill=T.TEXT_DIM, font=(T.FONT_FAMILY, 10), anchor="w",
        )

    # ------------------------------------------------------------------
    def load(self, video_path, duration):
        """Kick off ffmpeg extraction in the background."""
        self._video_path = video_path
        self._duration = duration
        self._peaks = []
        self._start = 0.0
        self._end = duration
        self._loading = True
        self._update_hint("Loading waveform...")

        def worker():
            peaks = extract_waveform(video_path, buckets=self._BUCKETS, duration=duration)
            self._peaks = peaks
            self._loading = False
            if self.winfo_exists():
                self.after(0, self._render)

        threading.Thread(target=worker, daemon=True).start()

    def set_range(self, start, end):
        self._start = start
        self._end = end
        self._render()

    def clear(self):
        self._video_path = None
        self._peaks = []
        self._start = 0
        self._end = 0
        self._render()
        self._update_hint("Waveform will appear here")

    # ------------------------------------------------------------------
    def _update_hint(self, text):
        self.canvas.itemconfig(self._hint, text=text)

    def _render(self, _event=None):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 20:
            return
        self.canvas.delete("bars")
        self.canvas.delete("overlay")

        if not self._peaks:
            # Keep hint centered in the visible area
            self.canvas.coords(self._hint, w // 2, h // 2)
            self.canvas.itemconfig(self._hint, anchor="center",
                                   state="normal",
                                   text=("Loading waveform..." if self._loading
                                         else "No audio track"))
            return
        self.canvas.itemconfig(self._hint, state="hidden")

        n = len(self._peaks)
        bar_w = max(1, w / n)
        mid = h // 2
        for i, peak in enumerate(self._peaks):
            bar_h = int(peak * (h - 4))
            x = i * bar_w
            self.canvas.create_rectangle(
                x, mid - bar_h // 2, x + max(1, bar_w - 1), mid + bar_h // 2,
                fill=T.BG_HOVER, outline="", tags="bars",
            )

        # Selection overlay
        if self._duration > 0 and self._end > self._start:
            x1 = (self._start / self._duration) * w
            x2 = (self._end / self._duration) * w
            # Dim the outside
            self.canvas.create_rectangle(
                0, 0, x1, h,
                fill=T.BG_BASE, outline="", stipple="gray50", tags="overlay",
            )
            self.canvas.create_rectangle(
                x2, 0, w, h,
                fill=T.BG_BASE, outline="", stipple="gray50", tags="overlay",
            )
            # Re-draw selected bars in accent
            for i, peak in enumerate(self._peaks):
                x = i * bar_w
                if x < x1 - bar_w or x > x2:
                    continue
                bar_h = int(peak * (h - 4))
                self.canvas.create_rectangle(
                    x, mid - bar_h // 2, x + max(1, bar_w - 1), mid + bar_h // 2,
                    fill=T.ACCENT, outline="", tags="overlay",
                )
