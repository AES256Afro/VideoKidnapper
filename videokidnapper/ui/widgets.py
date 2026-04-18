import tkinter as tk
import customtkinter as ctk

from videokidnapper.ui import theme as T


# ---------------------------------------------------------------------------
# RangeSlider — dual-handle timeline scrubber
# ---------------------------------------------------------------------------

class RangeSlider(ctk.CTkFrame):
    """Dual-handle range slider with a rounded capsule track.

    Both handles share the accent color; the active (dragged or hovered)
    handle gets a glow ring. The range between them is filled with the
    accent color.
    """

    _TRACK_H = 6
    _HANDLE_R = 9
    _HANDLE_HIT = 14  # click tolerance

    def __init__(self, master, from_=0, to=100, command=None, **kwargs):
        super().__init__(master, height=44, fg_color="transparent", **kwargs)
        self.from_ = from_
        self.to = to
        self.command = command
        self._start_val = from_
        self._end_val = to
        self._dragging = None
        self._hover = None

        self.canvas = tk.Canvas(
            self, height=44, bg=T.BG_SURFACE,
            highlightthickness=0, cursor="hand2",
        )
        self.canvas.pack(fill="x", expand=True)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Configure>", self._render)

    # -- math ----------------------------------------------------------------
    def _val_to_x(self, val):
        w = self.canvas.winfo_width()
        margin = self._HANDLE_R + 6
        usable = w - 2 * margin
        if self.to == self.from_:
            return margin
        return margin + (val - self.from_) / (self.to - self.from_) * usable

    def _x_to_val(self, x):
        w = self.canvas.winfo_width()
        margin = self._HANDLE_R + 6
        usable = max(1, w - 2 * margin)
        val = self.from_ + (x - margin) / usable * (self.to - self.from_)
        return max(self.from_, min(self.to, val))

    # -- drawing -------------------------------------------------------------
    def _capsule(self, x1, y1, x2, y2, fill):
        """Draw a rounded capsule by combining a rectangle with two circles."""
        r = (y2 - y1) / 2
        self.canvas.create_oval(x1 - r, y1, x1 + r, y2, fill=fill, outline="")
        self.canvas.create_oval(x2 - r, y1, x2 + r, y2, fill=fill, outline="")
        self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline="")

    def _handle(self, cx, cy, r, which):
        """Draw a handle with optional glow ring when active/hovered."""
        active = self._dragging == which or self._hover == which
        if active:
            ring = r + 5
            self.canvas.create_oval(
                cx - ring, cy - ring, cx + ring, cy + ring,
                fill=T.ACCENT, outline="",
            )
        core_fill = T.ACCENT_GLOW if active else T.ACCENT
        self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            fill=core_fill, outline=T.TEXT, width=2,
            tags=f"{which}_handle",
        )

    def _render(self, event=None):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10:
            return
        cy = h // 2
        margin = self._HANDLE_R + 6
        th = self._TRACK_H

        # Background track
        self._capsule(margin, cy - th // 2, w - margin, cy + th // 2, T.BG_RAISED)

        # Selection fill
        x1 = self._val_to_x(self._start_val)
        x2 = self._val_to_x(self._end_val)
        if x2 > x1:
            self._capsule(x1, cy - th // 2, x2, cy + th // 2, T.ACCENT)

        # Handles
        self._handle(x1, cy, self._HANDLE_R, "start")
        self._handle(x2, cy, self._HANDLE_R, "end")

    # -- interaction ---------------------------------------------------------
    def _which_handle_near(self, x):
        x1 = self._val_to_x(self._start_val)
        x2 = self._val_to_x(self._end_val)
        d1 = abs(x - x1)
        d2 = abs(x - x2)
        if d1 > self._HANDLE_HIT and d2 > self._HANDLE_HIT:
            return "start" if d1 < d2 else "end"
        return "start" if d1 <= d2 else "end"

    def _on_press(self, event):
        self._dragging = self._which_handle_near(event.x)
        self._on_drag(event)

    def _on_drag(self, event):
        if not self._dragging:
            return
        val = self._x_to_val(event.x)
        if self._dragging == "start":
            self._start_val = min(val, self._end_val - 0.01)
        else:
            self._end_val = max(val, self._start_val + 0.01)
        self._render()
        if self.command:
            self.command(self._start_val, self._end_val)

    def _on_release(self, _event):
        self._dragging = None
        self._render()

    def _on_hover(self, event):
        prev = self._hover
        x1 = self._val_to_x(self._start_val)
        x2 = self._val_to_x(self._end_val)
        self._hover = None
        if abs(event.x - x1) <= self._HANDLE_HIT:
            self._hover = "start"
        elif abs(event.x - x2) <= self._HANDLE_HIT:
            self._hover = "end"
        if self._hover != prev:
            self._render()

    def _on_leave(self, _event):
        if self._hover:
            self._hover = None
            self._render()

    # -- API -----------------------------------------------------------------
    def set_range(self, from_, to):
        self.from_ = from_
        self.to = to
        self._start_val = from_
        self._end_val = to
        self._render()

    def set_values(self, start, end):
        self._start_val = max(self.from_, min(start, self.to))
        self._end_val = max(self.from_, min(end, self.to))
        self._render()

    def get_values(self):
        return self._start_val, self._end_val


# ---------------------------------------------------------------------------
# TimestampEntry — monospace time input
# ---------------------------------------------------------------------------

class TimestampEntry(ctk.CTkFrame):
    def __init__(self, master, label="Time", default="00:00:00.000", command=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.command = command

        self.label = ctk.CTkLabel(
            self, text=label,
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED,
        )
        self.label.pack(side="left", padx=(0, 6))

        self.var = ctk.StringVar(value=default)
        self.entry = ctk.CTkEntry(
            self, textvariable=self.var, width=130, height=T.INPUT_HEIGHT,
            font=T.font(T.SIZE_LG, mono=True),
            justify="center",
            fg_color=T.BG_RAISED,
            border_color=T.BORDER_STRONG,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
        )
        self.entry.pack(side="left")
        self.entry.bind("<Return>", self._on_change)
        self.entry.bind("<FocusOut>", self._on_change)

    def _on_change(self, _event=None):
        if self.command:
            self.command(self.var.get())

    def set_value(self, value):
        self.var.set(value)

    def get_value(self):
        return self.var.get()


# ---------------------------------------------------------------------------
# Toast — transient status strip
# ---------------------------------------------------------------------------

class Toast(ctk.CTkFrame):
    """Bottom-of-window status strip that fades between messages.

    It never dismisses itself — call `show()`/`clear()` explicitly so callers
    can keep a persistent message visible (e.g. 'Downloading...').
    """

    _COLORS = {
        "info":    T.TEXT_MUTED,
        "success": T.SUCCESS,
        "warn":    T.WARN,
        "error":   T.DANGER,
    }

    def __init__(self, master, **kwargs):
        super().__init__(
            master, fg_color=T.BG_SURFACE,
            corner_radius=0, height=32,
            **kwargs,
        )
        self.pack_propagate(False)

        self._dot = ctk.CTkLabel(
            self, text="●", font=T.font(T.SIZE_MD, "bold"),
            text_color=T.TEXT_DIM, width=14,
        )
        self._dot.pack(side="left", padx=(14, 6))

        self._label = ctk.CTkLabel(
            self, text="Ready", font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED, anchor="w",
        )
        self._label.pack(side="left", fill="x", expand=True)

    def show(self, message, level="info"):
        color = self._COLORS.get(level, T.TEXT_MUTED)
        self._dot.configure(text_color=color)
        self._label.configure(text=message, text_color=color)

    def clear(self):
        self._dot.configure(text_color=T.TEXT_DIM)
        self._label.configure(text="Ready", text_color=T.TEXT_MUTED)


# ---------------------------------------------------------------------------
# PlatformChip — small brand-colored pill for the URL tab
# ---------------------------------------------------------------------------

class PlatformChip(ctk.CTkButton):
    """Clickable pill showing a supported platform."""

    def __init__(self, master, platform, on_click=None, **kwargs):
        color = T.PLATFORM_COLORS.get(platform, T.ACCENT)
        glyph = T.PLATFORM_GLYPHS.get(platform, "●")
        super().__init__(
            master,
            text=f" {glyph}  {platform} ",
            font=T.font(T.SIZE_SM, "bold"),
            fg_color=T.BG_RAISED,
            hover_color=color,
            text_color=T.TEXT,
            border_color=color,
            border_width=1,
            corner_radius=14,
            height=26,
            command=(lambda: on_click(platform)) if on_click else None,
            **kwargs,
        )
        self._color = color
        self._active = False

    def set_active(self, active):
        if active == self._active:
            return
        self._active = active
        self.configure(
            fg_color=self._color if active else T.BG_RAISED,
            text_color=T.TEXT_ON_ACCENT if active else T.TEXT,
        )
