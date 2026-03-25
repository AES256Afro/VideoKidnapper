import tkinter as tk
import customtkinter as ctk


class RangeSlider(ctk.CTkFrame):
    """Dual-handle range slider for selecting start/end points on a timeline."""

    def __init__(self, master, from_=0, to=100, command=None, **kwargs):
        super().__init__(master, height=50, fg_color="transparent", **kwargs)
        self.from_ = from_
        self.to = to
        self.command = command
        self._start_val = from_
        self._end_val = to
        self._dragging = None
        self._handle_radius = 8
        self._track_height = 6

        bg_color = "#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#e8e8e8"
        self.canvas = tk.Canvas(
            self, height=50, bg=bg_color,
            highlightthickness=0, cursor="hand2",
        )
        self.canvas.pack(fill="x", expand=True, padx=5, pady=5)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._render_slider)

    def _val_to_x(self, val):
        w = self.canvas.winfo_width()
        margin = self._handle_radius + 5
        usable = w - 2 * margin
        if self.to == self.from_:
            return margin
        return margin + (val - self.from_) / (self.to - self.from_) * usable

    def _x_to_val(self, x):
        w = self.canvas.winfo_width()
        margin = self._handle_radius + 5
        usable = w - 2 * margin
        val = self.from_ + (x - margin) / usable * (self.to - self.from_)
        return max(self.from_, min(self.to, val))

    def _render_slider(self, event=None):
        self.canvas.delete("all")
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        cy = h // 2
        margin = self._handle_radius + 5
        r = self._handle_radius
        th = self._track_height

        # Background track
        self.canvas.create_round_rect(
            margin, cy - th // 2, w - margin, cy + th // 2,
            radius=th // 2, fill="#404040", outline="",
        ) if hasattr(self.canvas, "create_round_rect") else self.canvas.create_rectangle(
            margin, cy - th // 2, w - margin, cy + th // 2,
            fill="#404040", outline="",
        )

        # Selected range highlight
        x1 = self._val_to_x(self._start_val)
        x2 = self._val_to_x(self._end_val)
        self.canvas.create_rectangle(
            x1, cy - th // 2, x2, cy + th // 2,
            fill="#1a73e8", outline="",
        )

        # Start handle
        self.canvas.create_oval(
            x1 - r, cy - r, x1 + r, cy + r,
            fill="#1a73e8", outline="white", width=2, tags="start_handle",
        )

        # End handle
        self.canvas.create_oval(
            x2 - r, cy - r, x2 + r, cy + r,
            fill="#e84a1a", outline="white", width=2, tags="end_handle",
        )

    def _on_press(self, event):
        x1 = self._val_to_x(self._start_val)
        x2 = self._val_to_x(self._end_val)
        r = self._handle_radius + 4
        if abs(event.x - x1) <= r:
            self._dragging = "start"
        elif abs(event.x - x2) <= r:
            self._dragging = "end"
        else:
            # Click on track: move nearest handle
            if abs(event.x - x1) < abs(event.x - x2):
                self._dragging = "start"
            else:
                self._dragging = "end"
            self._on_drag(event)

    def _on_drag(self, event):
        if not self._dragging:
            return
        val = self._x_to_val(event.x)
        if self._dragging == "start":
            self._start_val = min(val, self._end_val - 0.01)
        else:
            self._end_val = max(val, self._start_val + 0.01)
        self._render_slider()
        if self.command:
            self.command(self._start_val, self._end_val)

    def _on_release(self, event):
        self._dragging = None

    def set_range(self, from_, to):
        self.from_ = from_
        self.to = to
        self._start_val = from_
        self._end_val = to
        self._render_slider()

    def set_values(self, start, end):
        self._start_val = max(self.from_, min(start, self.to))
        self._end_val = max(self.from_, min(end, self.to))
        self._render_slider()

    def get_values(self):
        return self._start_val, self._end_val


class TimestampEntry(ctk.CTkFrame):
    """A labeled timestamp entry field with validation."""

    def __init__(self, master, label="Time", default="00:00:00.000", command=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.command = command

        self.label = ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=12))
        self.label.pack(side="left", padx=(0, 5))

        self.var = ctk.StringVar(value=default)
        self.entry = ctk.CTkEntry(
            self, textvariable=self.var, width=120,
            font=ctk.CTkFont(family="Consolas", size=13),
            justify="center",
        )
        self.entry.pack(side="left")
        self.entry.bind("<Return>", self._on_change)
        self.entry.bind("<FocusOut>", self._on_change)

    def _on_change(self, event=None):
        if self.command:
            self.command(self.var.get())

    def set_value(self, value):
        self.var.set(value)

    def get_value(self):
        return self.var.get()
