# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Track timeline for the Studio Edit workspace.

One canvas draws every lane so the playhead and the in/out selection can
run straight through all of them:

    ruler   · time labels, playhead head, in/out brackets
    ranges  · saved ranges (click one to load it back into the selection);
              drag across its empty space to choose a new selection
    text    · caption clips (click to select, drag to move, drag an edge
              to retime)
    image   · image-overlay clips (same gestures as text)
    video   · filmstrip of thumbnails
    audio   · waveform

The selection is the part that gets exported. Its two trim handles are
solid tabs on the video and audio lanes, drawn inside the selection so
they can be grabbed even at the very ends of the clip, and the video and
audio outside it are washed out. Shift-dragging anywhere that isn't a
clip also draws a new selection. Clicking or dragging anywhere else
moves the playhead.

The video and audio lanes are each drawn as one picture made with PIL
(the washed-out parts included) rather than as a thousand canvas items.
Thumbnails and waveform peaks load on worker threads and are handed to
Tk through ``after`` polling — PhotoImage construction must stay on the
main thread.

The time↔pixel math lives in module-level functions so it can be tested
without a display.
"""

import sys
import threading
import tkinter as tk
import tkinter.font as tkfont

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from videokidnapper.ui import theme as T


HEADER_W = 112
RULER_H = 26
LANES = (
    # key,     label,    height
    ("ranges", "Ranges", 24),
    ("text",   "Text",   34),
    ("image",  "Image",  34),
    ("video",  "Video",  50),
    ("audio",  "Audio",  42),
)
EDGE_GRAB_PX = 6        # how close to a clip edge counts as "resize"
HANDLE_GRAB_PX = 10     # how close to an in/out line counts as "drag it"
HANDLE_W = 12           # width of the trim handles' tabs on the media lanes
MEDIA_LANES = ("video", "audio")
DRAG_SLOP_PX = 3        # a press that moves less than this is a click
MIN_CLIP_S = 0.1        # shortest a clip can be resized to
MIN_SELECTION_S = 0.05  # shortest selection a drag can make
FADE_OUTSIDE = 0.62     # how far the cut-away video and audio fade out
TICK_STEPS = (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800)
MAX_ZOOM = 40.0

_THUMB_COUNT = 32
_WAVE_BUCKETS = 800
_THUMB_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested)
# ---------------------------------------------------------------------------

def time_to_x(t, view_start, view_end, x0, width):
    """Map a time in seconds to a canvas x inside ``[x0, x0 + width]``."""
    span = max(1e-9, view_end - view_start)
    return x0 + (t - view_start) / span * width


def x_to_time(x, view_start, view_end, x0, width):
    """Inverse of :func:`time_to_x` (unclamped)."""
    span = max(1e-9, view_end - view_start)
    return view_start + (x - x0) / max(1e-9, width) * span


def tick_step(visible_seconds, width_px, min_label_px=70):
    """Smallest step from :data:`TICK_STEPS` that keeps labels apart."""
    if visible_seconds <= 0 or width_px <= 0:
        return TICK_STEPS[-1]
    for step in TICK_STEPS:
        if step / visible_seconds * width_px >= min_label_px:
            return step
    return TICK_STEPS[-1]


def format_tick(t, step):
    """``m:ss`` labels, with tenths when the step is under a second."""
    t = max(0.0, t)
    minutes = int(t // 60)
    seconds = t - minutes * 60
    if step < 1:
        return f"{minutes}:{seconds:04.1f}"
    return f"{minutes}:{int(round(seconds)):02d}"


def view_window(duration, zoom, focus):
    """Visible ``(start, end)`` for a zoom factor, centered near ``focus``.

    Zoom 1 shows the whole clip. Higher zoom narrows the window and keeps
    ``focus`` (usually the playhead) inside it without scrolling past
    either end of the clip.
    """
    duration = max(0.0, float(duration))
    if duration <= 0:
        return 0.0, 1.0
    zoom = max(1.0, min(MAX_ZOOM, float(zoom)))
    span = duration / zoom
    start = float(focus) - span / 2
    start = max(0.0, min(duration - span, start))
    return start, start + span


def clamp_clip(start, end, duration, mode, delta):
    """New ``(start, end)`` after dragging a clip.

    ``mode`` is ``"move"`` (shift both, keep length), ``"start"`` or
    ``"end"`` (resize that edge). Results stay inside ``[0, duration]``
    and never shorter than :data:`MIN_CLIP_S`.
    """
    length = end - start
    if mode == "move":
        new_start = max(0.0, min(duration - length, start + delta))
        return new_start, new_start + length
    if mode == "start":
        new_start = max(0.0, min(end - MIN_CLIP_S, start + delta))
        return new_start, end
    if mode == "end":
        new_end = min(duration, max(start + MIN_CLIP_S, end + delta))
        return start, new_end
    return start, end


def clip_grab_mode(x, xa, xb, edge_px=EDGE_GRAB_PX):
    """``"start"``, ``"end"`` or ``"move"`` for a press at ``x`` on a clip.

    The edge zones shrink on a short clip so its middle third always
    moves it. With fixed 6 px zones a clip under about 12 px wide (a
    two-second caption on a long video) could only ever be resized.
    """
    width = max(0.0, xb - xa)
    edge = min(edge_px, width / 3)
    if x <= xa + edge:
        return "start"
    if x >= xb - edge:
        return "end"
    return "move"


def handle_at(x, lane, sx1, sx2):
    """Which trim handle a press at ``x`` in ``lane`` grabs: "in", "out" or None.

    On the video and audio lanes each handle is a tab drawn just inside
    the selection, so it can be grabbed at the very ends of the clip;
    elsewhere it is the line itself, give or take :data:`HANDLE_GRAB_PX`.
    When both are in reach (a very short selection), the side of the
    middle the press is on decides.
    """
    if lane in MEDIA_LANES:
        in_hit = sx1 - 3 <= x <= sx1 + HANDLE_W + 2
        out_hit = sx2 - HANDLE_W - 2 <= x <= sx2 + 3
    else:
        in_hit = abs(x - sx1) <= HANDLE_GRAB_PX
        out_hit = abs(x - sx2) <= HANDLE_GRAB_PX
    if in_hit and out_hit:
        return "in" if x < (sx1 + sx2) / 2 else "out"
    if in_hit:
        return "in"
    if out_hit:
        return "out"
    return None


def drag_selection(anchor, t, duration, min_len=MIN_SELECTION_S):
    """``(start, end)`` for a selection dragged from ``anchor`` to ``t``.

    Either direction works, the result stays inside the clip, and it is
    never shorter than ``min_len`` (it grows the way the mouse went).
    """
    duration = max(0.0, float(duration))
    lo, hi = sorted((max(0.0, min(anchor, duration)), max(0.0, min(t, duration))))
    if hi - lo < min_len:
        if t >= anchor:
            hi = min(duration, lo + min_len)
            lo = max(0.0, hi - min_len)
        else:
            lo = max(0.0, hi - min_len)
            hi = min(duration, lo + min_len)
    return lo, hi


def render_filmstrip(thumbs, duration, view, width, height, background):
    """The video lane as one picture: thumbnails laid along ``view``.

    Each thumbnail covers an equal share of the clip and is repeated
    across its share when zoomed in, as the canvas tiles used to be.
    """
    strip = Image.new("RGB", (max(1, int(width)), max(1, int(height))), background)
    if not thumbs or duration <= 0:
        return strip
    v0, v1 = view
    cell = duration / len(thumbs)
    for i, thumb in enumerate(thumbs):
        cs = time_to_x(i * cell, v0, v1, 0, width)
        ce = time_to_x((i + 1) * cell, v0, v1, 0, width)
        if ce < 0 or cs > width:
            continue
        tile_w = max(1, thumb.width)
        x = max(0.0, cs)
        while x < ce and x < width:
            # Clip the tile to its own share so the next one isn't covered.
            visible = min(tile_w, int(round(ce - x)) or 1)
            piece = thumb if visible >= tile_w else thumb.crop((0, 0, visible, thumb.height))
            strip.paste(piece, (int(x), max(0, (strip.height - thumb.height) // 2)))
            x += tile_w
    return strip


def render_waveform(peaks, duration, view, width, height, fill, wave):
    """The audio lane as one picture: one bar per two pixels of width."""
    width, height = max(1, int(width)), max(1, int(height))
    img = Image.new("RGB", (width, height), fill)
    if not peaks or duration <= 0:
        return img
    draw = ImageDraw.Draw(img)
    v0, v1 = view
    n = len(peaks)
    mid = (height - 1) / 2
    half = max(1.0, height / 2 - 2)
    bars = max(1, width // 2)
    for b in range(bars):
        t = v0 + (b + 0.5) / bars * (v1 - v0)
        idx = min(n - 1, max(0, int(t / duration * n)))
        amp = max(0.04, min(1.0, float(peaks[idx]))) * half
        x = int(b * width / bars)
        draw.line([(x, mid - amp), (x, mid + amp)], fill=wave)
    return img


def fade_outside(img, keep_from, keep_to, toward, amount=FADE_OUTSIDE):
    """``img`` faded toward ``toward`` except the columns ``[keep_from, keep_to)``."""
    faded = Image.blend(img, Image.new("RGB", img.size, toward), amount)
    a = max(0, min(img.width, int(round(keep_from))))
    b = max(a, min(img.width, int(round(keep_to))))
    if b > a:
        faded.paste(img.crop((a, 0, b, img.height)), (a, 0))
    return faded


def lane_at(y):
    """Lane key under canvas ``y`` (``"ruler"`` above the lanes), or None."""
    if y < RULER_H:
        return "ruler"
    top = RULER_H
    for key, _label, height in LANES:
        if top <= y < top + height:
            return key
        top += height
    return None


def lane_top(key):
    top = RULER_H
    for k, _label, height in LANES:
        if k == key:
            return top, height
        top += height
    raise KeyError(key)


def total_height():
    return RULER_H + sum(h for _k, _l, h in LANES)


# ---------------------------------------------------------------------------
# Transport (the row under the preview)
# ---------------------------------------------------------------------------

def _clock(seconds, hours):
    # Split whole milliseconds, so 2.8 reads 02.800 (not 02.799) and
    # 2.9996 rounds up to 03.000 instead of wrapping to 02.000.
    total_ms = int(round(max(0.0, float(seconds)) * 1000))
    rem, ms = divmod(total_ms, 1000)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}" if hours else f"{m:02d}:{s:02d}.{ms:03d}"


def transport_timecode(playhead, duration, compact=False):
    """``playhead / duration`` for the transport row.

    Compact drops the hours (unless the clip is an hour or longer) and the
    wide spacing, for a preview panel too narrow for the full readout.
    ``None`` for either value draws dashes in the same shape, so the label
    keeps its width before a video is loaded.
    """
    hours = not compact or (duration or 0) >= 3600
    sep = " / " if compact else "   /   "
    if playhead is None or duration is None:
        dash = "--:--:--.---" if hours else "--:--.---"
        return f"{dash}{sep}{dash}"
    return f"{_clock(playhead, hours)}{sep}{_clock(duration, hours)}"


def transport_play_x(width, left, play, right, gap=12):
    """Where to centre the play controls in a transport row ``width`` wide.

    ``left`` and ``right`` are the space the timecode and the in/out
    buttons take at either end. The controls sit at the true centre when
    that clears both by ``gap``, otherwise in the middle of the free space
    between them. ``None`` means they don't fit even there.
    """
    centre = width / 2
    if centre - play / 2 >= left + gap and centre + play / 2 <= width - right - gap:
        return centre
    lo, hi = left + gap, width - right - gap
    if hi - lo >= play:
        return (lo + hi) / 2
    return None


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

class TimelineView(ctk.CTkFrame):
    """Multi-lane timeline. See module docstring for the gestures.

    Callbacks (all optional):
      - ``on_seek(t)`` — playhead moved by a click or scrub
      - ``on_selection_change(start, end)`` — a trim handle was dragged or
        a new selection drawn
      - ``on_clip_select(kind, index)`` — a text/image clip was clicked
      - ``on_clip_change(kind, index, start, end, final)`` — a clip was
        moved or resized; ``final`` is True on mouse release
      - ``on_range_click(index)`` — a saved range chip was clicked
      - ``on_zoom_change(zoom)`` — Ctrl+wheel changed the zoom
    """

    def __init__(self, master, on_seek=None, on_selection_change=None,
                 on_clip_select=None, on_clip_change=None,
                 on_range_click=None, on_zoom_change=None, on_clip_menu=None,
                 **kwargs):
        super().__init__(master, fg_color=T.BG_SURFACE, corner_radius=0, **kwargs)
        self._on_seek = on_seek
        self._on_selection_change = on_selection_change
        self._on_clip_select = on_clip_select
        self._on_clip_change = on_clip_change
        self._on_range_click = on_range_click
        self._on_zoom_change = on_zoom_change
        # on_clip_menu(kind, index, x_root, y_root): a clip was right-clicked.
        self._on_clip_menu = on_clip_menu

        self.duration = 0.0
        self.sel_start = 0.0
        self.sel_end = 0.0
        self.playhead = 0.0
        self.zoom = 1.0
        self._view = (0.0, 1.0)
        self.ranges = []
        self.text_clips = []     # [{"start", "end", "label"}]
        self.image_clips = []
        self.selected = None     # ("text" | "image", index) or None

        self._thumb_images = []  # PIL thumbnails, lane height
        self._peaks = []
        self._media_gen = 0
        self._loading = False
        self._drag = None
        self._hover_edge = None  # trim handle under the mouse
        # Rendered video/audio lanes, keyed on what they show, and the
        # PhotoImages on the canvas (kept alive here).
        self._media_base = {}
        self._media_shown = {}
        self._redraw_after = None

        self._font = tkfont.Font(family=T.FONT_FAMILY, size=9)
        self._font_bold = tkfont.Font(family=T.FONT_FAMILY, size=9, weight="bold")
        self._font_mono = tkfont.Font(family=T.FONT_MONO, size=9)

        self.canvas = tk.Canvas(
            self, height=total_height() + 2, bg=T.BG_SURFACE,
            highlightthickness=0, cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover_edge(None))
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)
        for button in (("<Button-2>", "<Button-3>") if sys.platform == "darwin"
                       else ("<Button-3>",)):
            self.canvas.bind(button, self._on_context)

    # ------------------------------------------------------------------
    # Data API
    # ------------------------------------------------------------------
    def load(self, video_path, duration):
        """Reset to a new clip and start loading thumbnails + waveform."""
        self._media_gen += 1
        gen = self._media_gen
        self.duration = max(0.0, float(duration or 0.0))
        self.sel_start, self.sel_end = 0.0, self.duration
        self.playhead = 0.0
        self.zoom = 1.0
        self.ranges, self.text_clips, self.image_clips = [], [], []
        self.selected = None
        self._thumb_images, self._peaks = [], []
        self._media_base, self._media_shown = {}, {}
        self._loading = True
        self.redraw()

        # Workers only touch this dict; the main-thread poll below picks
        # the results up and redraws.
        state = {"thumbs": None, "peaks": None,
                 "thumbs_done": False, "peaks_done": False}
        lane_h = lane_top("video")[1] - 10
        duration = self.duration

        def thumbs_worker():
            from videokidnapper.core.preview import extract_thumbnail_strip
            resized = []
            # The preview cache hands out shared PIL images; two loads in
            # flight (open a project right after a file) must not decode
            # the same image on two threads at once.
            with _THUMB_LOCK:
                if gen == self._media_gen:
                    try:
                        # Fetched at lane height: full frames cost about a
                        # second per ten and up to 25 MB each in the cache.
                        frames = extract_thumbnail_strip(
                            video_path, duration, count=_THUMB_COUNT,
                            height=lane_h)
                    except Exception:
                        frames = []
                    for frame in frames:
                        if gen != self._media_gen:
                            break
                        try:
                            fw, fh = frame.size
                            if fh <= 0:
                                continue
                            resized.append(frame.convert("RGB").resize(
                                (max(1, int(fw * lane_h / fh)), lane_h), Image.LANCZOS))
                        except Exception:
                            continue
            state["thumbs"] = resized
            state["thumbs_done"] = True

        def peaks_worker():
            from videokidnapper.core.ffmpeg_backend import extract_waveform
            try:
                peaks = extract_waveform(
                    video_path, buckets=_WAVE_BUCKETS, duration=duration)
            except Exception:
                peaks = []
            state["peaks"] = peaks
            state["peaks_done"] = True

        def poll():
            if gen != self._media_gen or not self.winfo_exists():
                return
            changed = False
            if state["thumbs_done"] and state["thumbs"] is not None:
                self._thumb_images = list(state["thumbs"])
                state["thumbs"] = None
                changed = True
            if state["peaks_done"] and state["peaks"] is not None:
                self._peaks = list(state["peaks"])
                state["peaks"] = None
                changed = True
            finished = state["thumbs_done"] and state["peaks_done"]
            if finished and self._loading:
                self._loading = False
                changed = True
            if changed:
                self.redraw()
            if not finished:
                self.after(150, poll)

        threading.Thread(target=thumbs_worker, daemon=True).start()
        threading.Thread(target=peaks_worker, daemon=True).start()
        self.after(150, poll)

    def clear(self):
        self._media_gen += 1
        self.duration = 0.0
        self.sel_start = self.sel_end = self.playhead = 0.0
        self.ranges, self.text_clips, self.image_clips = [], [], []
        self.selected = None
        self._thumb_images, self._peaks = [], []
        self._media_base, self._media_shown = {}, {}
        self._loading = False
        self.redraw()

    def set_selection(self, start, end):
        self.sel_start = max(0.0, min(float(start), self.duration))
        self.sel_end = max(self.sel_start, min(float(end), self.duration))
        self.redraw()

    # RangeSlider-compatible aliases so editor code reads naturally.
    def get_values(self):
        return self.sel_start, self.sel_end

    def set_values(self, start, end):
        self.set_selection(start, end)

    def set_playhead(self, t):
        t = max(0.0, min(float(t), self.duration))
        if abs(t - self.playhead) < 1e-4:
            return
        self.playhead = t
        start, end = self._view
        if self.zoom > 1.0 and not (start <= t <= end):
            self.redraw()          # scroll the window to keep it in view
            return
        self._draw_playhead()

    def set_ranges(self, ranges):
        self.ranges = [(float(s), float(e)) for s, e in ranges]
        self.redraw()

    def set_clips(self, text=None, images=None):
        before = (self.text_clips, self.image_clips, self.selected)
        if text is not None:
            self.text_clips = list(text)
        if images is not None:
            self.image_clips = list(images)
        if self.selected:
            kind, index = self.selected
            clips = self.text_clips if kind == "text" else self.image_clips
            if index >= len(clips):
                self.selected = None
        # Sticker drags and most keystrokes change nothing drawn here.
        if (self.text_clips, self.image_clips, self.selected) != before:
            self.redraw()

    def set_selected(self, kind, index):
        self.selected = (kind, index) if kind else None
        self.redraw()

    def set_zoom(self, factor):
        self.zoom = max(1.0, min(MAX_ZOOM, float(factor)))
        self.redraw()

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------
    def _lanes_box(self):
        w = self.canvas.winfo_width()
        return HEADER_W, max(1, w - HEADER_W - 8)

    def _t2x(self, t):
        x0, width = self._lanes_box()
        return time_to_x(t, self._view[0], self._view[1], x0, width)

    def _x2t(self, x):
        x0, width = self._lanes_box()
        t = x_to_time(x, self._view[0], self._view[1], x0, width)
        return max(0.0, min(self.duration, t))

    def _px_to_seconds(self, dx):
        _x0, width = self._lanes_box()
        return dx / max(1, width) * (self._view[1] - self._view[0])

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def _on_configure(self, _event=None):
        """Redraw once a window resize settles, not on every pixel of it."""
        if self._redraw_after is not None:
            try:
                self.after_cancel(self._redraw_after)
            except Exception:
                pass

        def run():
            self._redraw_after = None
            self.redraw()

        self._redraw_after = self.after(30, run)

    def redraw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 50:
            return
        frozen = (self._drag or {}).get("view")
        if frozen:
            # Dragging an in/out edge moves the playhead with it. Re-centring
            # on it every motion event shifted the time under the mouse, so
            # on a zoomed timeline the edge ran away from the cursor.
            self._view = frozen
        else:
            self._view = view_window(self.duration, self.zoom, self.playhead)
        x0, width = self._lanes_box()
        x1 = x0 + width

        # Ruler band + header column backgrounds.
        c.create_rectangle(0, 0, w, RULER_H, fill=T.PANEL_HEADER, outline="")
        c.create_rectangle(0, RULER_H, HEADER_W - 1, h, fill=T.BG_SURFACE, outline="")
        c.create_line(HEADER_W - 1, 0, HEADER_W - 1, h, fill=T.DIVIDER)
        c.create_line(0, RULER_H, w, RULER_H, fill=T.DIVIDER)

        top = RULER_H
        for key, label, height in LANES:
            c.create_line(0, top + height, w, top + height, fill=T.DIVIDER)
            swatch = {
                "ranges": T.ACCENT, "text": T.TRACK_TEXT_EDGE,
                "image": T.TRACK_IMAGE_EDGE, "video": T.TRACK_VIDEO_EDGE,
                "audio": T.TRACK_AUDIO_WAVE,
            }[key]
            cy = top + height / 2
            c.create_rectangle(12, cy - 4, 20, cy + 4, fill=swatch, outline="")
            c.create_text(28, cy, text=label, anchor="w",
                          fill=T.TEXT_MUTED, font=self._font)
            top += height

        if self.duration <= 0:
            c.create_text(
                x0 + width / 2, RULER_H + (h - RULER_H) / 2,
                text="Open a video to see its timeline",
                fill=T.TEXT_DIM, font=self._font,
            )
            return

        # Selection band behind everything in the lanes.
        sx1, sx2 = self._t2x(self.sel_start), self._t2x(self.sel_end)
        band_l, band_r = max(x0, sx1), min(x1, sx2)
        if band_r > band_l:
            c.create_rectangle(band_l, RULER_H + 1, band_r, h,
                               fill=T.SELECTION, outline="")

        self._draw_ruler(x0, width)
        self._draw_ranges()
        self._draw_clips("text", self.text_clips, T.TRACK_TEXT_FILL,
                         T.TRACK_TEXT_EDGE, T.TRACK_TEXT_INK)
        self._draw_clips("image", self.image_clips, T.TRACK_IMAGE_FILL,
                         T.TRACK_IMAGE_EDGE, T.TRACK_IMAGE_INK)
        self._draw_media(sx1 - x0, sx2 - x0)
        self._draw_trim(sx1, sx2, h)
        self._draw_drag_time()
        self._draw_playhead()

    def _draw_ruler(self, x0, width):
        c = self.canvas
        start, end = self._view
        step = tick_step(end - start, width)
        minor = step / 5
        t = (int(start / minor)) * minor
        while t <= end + 1e-9:
            x = self._t2x(t)
            if x >= x0:
                is_major = abs(round(t / step) * step - t) < minor / 2
                if is_major:
                    c.create_line(x, RULER_H - 10, x, RULER_H, fill=T.BORDER_STRONG)
                    c.create_text(x + 3, 4, text=format_tick(t, step), anchor="nw",
                                  fill=T.TEXT_MUTED, font=self._font_mono)
                else:
                    c.create_line(x, RULER_H - 4, x, RULER_H, fill=T.BORDER)
            t += minor

    def _clip_label(self, text, max_px):
        if max_px < 14:
            return ""
        if self._font.measure(text) <= max_px:
            return text
        while text and self._font.measure(text + "…") > max_px:
            text = text[:-1]
        return text + "…" if text else ""

    def _draw_ranges(self):
        c = self.canvas
        top, height = lane_top("ranges")
        if not self.ranges:
            x0, width = self._lanes_box()
            hint = self._clip_label(
                "Drag here to choose the part to keep, or drag the blue handles",
                width - 24)
            if hint:
                c.create_text(x0 + width / 2, top + height / 2, text=hint,
                              fill=T.TEXT_DIM, font=self._font)
            return
        for i, (s, e) in enumerate(self.ranges):
            xa, xb = self._t2x(s), self._t2x(e)
            if xb < HEADER_W or xa > self.canvas.winfo_width():
                continue
            xa = max(HEADER_W + 1, xa)
            c.create_rectangle(xa, top + 4, xb, top + height - 4,
                               fill=T.ACCENT_SOFT, outline=T.ACCENT,
                               tags=("range", f"range:{i}"))
            label = self._clip_label(f"{i + 1}  ·  {e - s:.1f}s", xb - xa - 10)
            if label:
                c.create_text(xa + 6, top + height / 2, text=label, anchor="w",
                              fill=T.ACCENT_SOFT_TEXT, font=self._font_bold)

    def _draw_clips(self, kind, clips, fill, edge, ink):
        c = self.canvas
        top, height = lane_top(kind)
        for i, clip in enumerate(clips):
            xa, xb = self._t2x(clip["start"]), self._t2x(clip["end"])
            if xb < HEADER_W or xa > self.canvas.winfo_width():
                continue
            xa = max(HEADER_W + 1, xa)
            selected = self.selected == (kind, i)
            c.create_rectangle(
                xa, top + 4, max(xa + 3, xb), top + height - 4,
                fill=fill, outline=edge, width=2 if selected else 1,
            )
            if selected:
                for ex in (xa, xb):
                    c.create_rectangle(ex - 2, top + 9, ex + 2, top + height - 9,
                                       fill=edge, outline="")
            label = self._clip_label(clip.get("label") or "", xb - xa - 12)
            if label:
                c.create_text(xa + 7, top + height / 2, text=label, anchor="w",
                              fill=ink, font=self._font_bold if selected else self._font)

    def _media_picture(self, lane, keep_from, keep_to):
        """The PhotoImage for a media lane, faded outside the selection.

        The lane itself is rendered once per view and width; a redraw for
        a moved handle only redoes the fade, and one that changes neither
        (a caption edit, say) reuses the PhotoImage already made.
        """
        _x0, width = self._lanes_box()
        _top, lane_h = lane_top(lane)
        height = lane_h - 10
        base_key = (lane, self._view, width, height, self.duration,
                    len(self._thumb_images) if lane == "video" else len(self._peaks))
        base = self._media_base.get(lane)
        if base is None or base[0] != base_key:
            if lane == "video":
                img = render_filmstrip(self._thumb_images, self.duration, self._view,
                                       width, height, T.ACCENT_SOFT)
            else:
                img = render_waveform(self._peaks, self.duration, self._view,
                                      width, height, T.TRACK_AUDIO_FILL,
                                      T.TRACK_AUDIO_WAVE)
            base = (base_key, img)
            self._media_base[lane] = base
        shown_key = (base_key, int(round(keep_from)), int(round(keep_to)))
        shown = self._media_shown.get(lane)
        if shown is None or shown[0] != shown_key:
            img = fade_outside(base[1], keep_from, keep_to, T.BG_BASE)
            shown = (shown_key, ImageTk.PhotoImage(img, master=self.canvas))
            self._media_shown[lane] = shown
        return shown[1]

    def _draw_media(self, keep_from, keep_to):
        """Filmstrip and waveform, washed out where the export cuts them."""
        c = self.canvas
        x0, width = self._lanes_box()
        for lane, edge in (("video", T.TRACK_VIDEO_EDGE), ("audio", T.TRACK_AUDIO_WAVE)):
            top, height = lane_top(lane)
            y1, y2 = top + 5, top + height - 5
            empty = not (self._thumb_images if lane == "video" else self._peaks)
            if empty:
                fill = T.ACCENT_SOFT if lane == "video" else T.TRACK_AUDIO_FILL
                c.create_rectangle(x0, y1, x0 + width, y2, fill=fill, outline=edge)
                if lane == "video":
                    text = "Loading frames…" if self._loading else ""
                    ink = T.ACCENT_SOFT_TEXT
                else:
                    text = "Loading audio…" if self._loading else "No audio track"
                    ink = T.TRACK_AUDIO_WAVE
                c.create_text(x0 + 8, (y1 + y2) / 2, anchor="w", text=text,
                              fill=ink, font=self._font)
                continue
            photo = self._media_picture(lane, keep_from, keep_to)
            c.create_image(x0, y1, image=photo, anchor="nw")
            c.create_rectangle(x0, y1, x0 + width, y2, outline=edge, width=1)

    def _draw_trim(self, sx1, sx2, h):
        """The selection's lines, ruler brackets and grab tabs."""
        c = self.canvas
        x0, width = self._lanes_box()
        x1 = x0 + width
        top = lane_top("video")[0] + 2
        a_top, a_h = lane_top("audio")
        bottom = a_top + a_h - 2

        # A frame along the kept part of the video and audio.
        fl, fr = max(x0, sx1), min(x1, sx2)
        if fr > fl:
            c.create_line(fl, top, fr, top, fill=T.ACCENT, width=3)
            c.create_line(fl, bottom, fr, bottom, fill=T.ACCENT, width=3)

        for edge, x in (("in", sx1), ("out", sx2)):
            if not (x0 - 1 <= x <= x1 + 1):
                continue
            c.create_line(x, RULER_H, x, h, fill=T.ACCENT, width=2)
            if edge == "in":
                pts = (x, 4, x + 9, 4, x + 9, 8, x + 3, 8, x + 3, RULER_H - 2, x, RULER_H - 2)
                tab = (x, top - 1, x + HANDLE_W, bottom + 1)
            else:
                pts = (x, 4, x - 9, 4, x - 9, 8, x - 3, 8, x - 3, RULER_H - 2, x, RULER_H - 2)
                tab = (x - HANDLE_W, top - 1, x, bottom + 1)
            c.create_polygon(*pts, fill=T.ACCENT, outline="")
            active = self._hover_edge == edge or (self._drag or {}).get("edge") == edge
            c.create_rectangle(*tab, fill=T.ACCENT_ACTIVE if active else T.ACCENT,
                               outline="", tags=("handle", f"handle:{edge}"))
            cx, cy = (tab[0] + tab[2]) / 2, (tab[1] + tab[3]) / 2
            for dx in (-2, 2):
                c.create_line(cx + dx, cy - 8, cx + dx, cy + 8,
                              fill=T.TEXT_ON_ACCENT, tags=("handle", f"handle:{edge}"))

    def _draw_drag_time(self):
        """While a handle moves, show where it is in the ruler."""
        drag = self._drag or {}
        if drag.get("kind") not in ("handle", "select") or not drag.get("moved"):
            return
        t = self.sel_start if drag.get("edge") == "in" else self.sel_end
        x = self._t2x(t)
        text = f"{_clock(t, self.duration >= 3600)}  ·  {self.sel_end - self.sel_start:.1f}s"
        x0, width = self._lanes_box()
        half = self._font_bold.measure(text) / 2 + 7
        cx = max(x0 + half, min(x0 + width - half, x))
        c = self.canvas
        c.create_rectangle(cx - half, 2, cx + half, RULER_H - 3,
                           fill=T.ACCENT, outline="")
        c.create_text(cx, (RULER_H - 1) / 2, text=text, fill=T.TEXT_ON_ACCENT,
                      font=self._font_bold)

    def _draw_playhead(self):
        c = self.canvas
        c.delete("playhead")
        if self.duration <= 0:
            return
        x = self._t2x(self.playhead)
        x0, width = self._lanes_box()
        if not (x0 - 1 <= x <= x0 + width + 1):
            return
        h = c.winfo_height()
        c.create_line(x, 0, x, h, fill=T.PLAYHEAD, width=2, tags="playhead")
        c.create_polygon(x - 6, 0, x + 6, 0, x + 6, 8, x, 14, x - 6, 8,
                         fill=T.PLAYHEAD, outline="", tags="playhead")

    # ------------------------------------------------------------------
    # Hit-testing
    # ------------------------------------------------------------------
    def _hit(self, x, y, shift=False):
        """What a press at (x, y) grabs, as a drag-state dict or None."""
        if self.duration <= 0 or x < HEADER_W:
            return None
        lane = lane_at(y)
        if lane in ("text", "image"):
            clips = self.text_clips if lane == "text" else self.image_clips
            # Last-drawn wins, matching what's visually on top.
            for i in range(len(clips) - 1, -1, -1):
                xa, xb = self._t2x(clips[i]["start"]), self._t2x(clips[i]["end"])
                if xa - EDGE_GRAB_PX <= x <= xb + EDGE_GRAB_PX:
                    return {"kind": lane, "index": i,
                            "mode": clip_grab_mode(x, xa, xb),
                            "x": x, "start": clips[i]["start"],
                            "end": clips[i]["end"]}
        if lane == "ranges" and not shift:
            for i, (s, e) in enumerate(self.ranges):
                if self._t2x(s) <= x <= self._t2x(e):
                    return {"kind": "range", "index": i}
        sx1, sx2 = self._t2x(self.sel_start), self._t2x(self.sel_end)
        edge = None if shift else handle_at(x, lane, sx1, sx2)
        if edge:
            # The view stays put for the whole drag (see redraw), and the
            # handle keeps its offset from the mouse instead of jumping.
            return {"kind": "handle", "edge": edge, "view": self._view,
                    "grab_dx": x - (sx1 if edge == "in" else sx2)}
        if shift or lane == "ranges":
            return {"kind": "select", "x": x, "anchor": self._x2t(x),
                    "view": self._view}
        return {"kind": "seek"}

    def _set_hover_edge(self, edge):
        if edge == self._hover_edge:
            return
        self._hover_edge = edge
        for side in ("in", "out"):
            on = side == edge
            for item in self.canvas.find_withtag(f"handle:{side}"):
                if self.canvas.type(item) == "rectangle":
                    self.canvas.itemconfigure(
                        item, fill=T.ACCENT_ACTIVE if on else T.ACCENT)

    def _on_hover(self, event):
        hit = self._hit(event.x, event.y, shift=bool(getattr(event, "state", 0) & 0x1))
        cursor = "hand2"
        edge = None
        if hit:
            if hit["kind"] == "handle":
                cursor = "sb_h_double_arrow"
                edge = hit["edge"]
            elif hit.get("mode") in ("start", "end"):
                cursor = "sb_h_double_arrow"
            elif hit.get("mode") == "move":
                cursor = "fleur"
            elif hit["kind"] == "select":
                cursor = "crosshair"
        self._set_hover_edge(edge)
        self.canvas.configure(cursor=cursor)

    # ------------------------------------------------------------------
    # Gestures
    # ------------------------------------------------------------------
    def _on_press(self, event):
        shift = bool(getattr(event, "state", 0) & 0x1)
        hit = self._hit(event.x, event.y, shift=shift)
        self._drag = hit
        if not hit:
            return
        kind = hit["kind"]
        if kind in ("text", "image"):
            self.selected = (kind, hit["index"])
            if self._on_clip_select:
                self._on_clip_select(kind, hit["index"])
            self.redraw()
        elif kind == "range":
            if self._on_range_click:
                self._on_range_click(hit["index"])
            self._drag = None
        elif kind == "seek":
            self._seek_to(self._x2t(event.x))

    def _on_context(self, event):
        """Right-click on a caption or image clip: pick it, offer its menu."""
        hit = self._hit(event.x, event.y)
        if not hit or hit["kind"] not in ("text", "image"):
            return
        self.selected = (hit["kind"], hit["index"])
        if self._on_clip_select:
            self._on_clip_select(hit["kind"], hit["index"])
        self.redraw()
        if self._on_clip_menu:
            self._on_clip_menu(hit["kind"], hit["index"], event.x_root, event.y_root)

    def _on_motion(self, event):
        drag = self._drag
        if not drag:
            return
        kind = drag["kind"]
        if kind == "seek":
            self._seek_to(self._x2t(event.x))
        elif kind == "handle":
            t = self._x2t(event.x - drag.get("grab_dx", 0))
            if drag["edge"] == "in":
                self.sel_start = max(0.0, min(t, self.sel_end - MIN_SELECTION_S))
            else:
                self.sel_end = min(self.duration, max(t, self.sel_start + MIN_SELECTION_S))
            self.playhead = self.sel_start if drag["edge"] == "in" else self.sel_end
            drag["moved"] = True
            self.redraw()
            if self._on_selection_change:
                self._on_selection_change(self.sel_start, self.sel_end)
        elif kind == "select":
            if not drag.get("moved") and abs(event.x - drag["x"]) < DRAG_SLOP_PX:
                return
            drag["moved"] = True
            t = self._x2t(event.x)
            self.sel_start, self.sel_end = drag_selection(
                drag["anchor"], t, self.duration)
            # The playhead follows the end being drawn, so the preview
            # shows the frame there; the label in the ruler names it.
            drag["edge"] = "out" if t >= drag["anchor"] else "in"
            self.playhead = self.sel_end if drag["edge"] == "out" else self.sel_start
            self.redraw()
            if self._on_selection_change:
                self._on_selection_change(self.sel_start, self.sel_end)
        elif kind in ("text", "image"):
            delta = self._px_to_seconds(event.x - drag["x"])
            start, end = clamp_clip(drag["start"], drag["end"], self.duration,
                                    drag["mode"], delta)
            clips = self.text_clips if kind == "text" else self.image_clips
            if drag["index"] < len(clips):
                clips[drag["index"]] = dict(clips[drag["index"]], start=start, end=end)
            drag["moved"] = True
            self.redraw()
            if self._on_clip_change:
                self._on_clip_change(kind, drag["index"], start, end, False)

    def _on_release(self, _event):
        drag, self._drag = self._drag, None
        if not drag:
            return
        if drag["kind"] in ("text", "image") and drag.get("moved"):
            clips = self.text_clips if drag["kind"] == "text" else self.image_clips
            if drag["index"] < len(clips) and self._on_clip_change:
                clip = clips[drag["index"]]
                self._on_clip_change(drag["kind"], drag["index"],
                                     clip["start"], clip["end"], True)
        elif drag["kind"] == "select" and not drag.get("moved"):
            # A click on the empty Ranges lane moves the playhead, as a
            # click anywhere else does.
            self._seek_to(drag["anchor"])
        elif drag["kind"] in ("handle", "select"):
            self.redraw()          # drop the time label from the ruler

    def _seek_to(self, t):
        self.playhead = t
        self._draw_playhead()
        if self._on_seek:
            self._on_seek(t)

    def _on_wheel(self, event):
        """Plain wheel pans the zoomed view by moving the playhead focus."""
        if self.zoom <= 1.0 or self.duration <= 0:
            return
        span = self._view[1] - self._view[0]
        step = span * 0.1 * (-1 if event.delta > 0 else 1)
        self._seek_to(max(0.0, min(self.duration, self.playhead + step)))
        self.redraw()

    def _on_ctrl_wheel(self, event):
        factor = 1.25 if event.delta > 0 else 0.8
        self.set_zoom(self.zoom * factor)
        if self._on_zoom_change:
            self._on_zoom_change(self.zoom)
