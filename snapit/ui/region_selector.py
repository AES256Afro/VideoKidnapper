import tkinter as tk

import mss
from PIL import Image, ImageTk


class RegionSelector(tk.Toplevel):
    """Fullscreen transparent overlay for selecting a screen region."""

    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.start_x = 0
        self.start_y = 0
        self.rect_id = None
        self.dim_label_id = None

        # Capture full screenshot for background
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # Full virtual screen
            screenshot = sct.grab(monitor)
            self._bg_image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            self._monitor = monitor

        # Fullscreen window
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(
            f"{self._monitor['width']}x{self._monitor['height']}"
            f"+{self._monitor['left']}+{self._monitor['top']}"
        )

        # Canvas with screenshot background (dimmed)
        self.canvas = tk.Canvas(
            self, cursor="crosshair", highlightthickness=0,
            width=self._monitor["width"], height=self._monitor["height"],
        )
        self.canvas.pack(fill="both", expand=True)

        # Dim the background
        dimmed = self._bg_image.copy()
        overlay = Image.new("RGBA", dimmed.size, (0, 0, 0, 120))
        dimmed = Image.alpha_composite(dimmed.convert("RGBA"), overlay)
        self._bg_photo = ImageTk.PhotoImage(dimmed)
        self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo)

        # Instructions text
        self.canvas.create_text(
            self._monitor["width"] // 2, 40,
            text="Click and drag to select a region  |  Press ESC to cancel",
            fill="white", font=("Segoe UI", 16, "bold"),
        )

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Escape>", self._on_cancel)
        self.focus_force()

    def _on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.dim_label_id:
            self.canvas.delete(self.dim_label_id)

    def _on_drag(self, event):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        if self.dim_label_id:
            self.canvas.delete(self.dim_label_id)

        x0, y0 = self.start_x, self.start_y
        x1, y1 = event.x, event.y

        self.rect_id = self.canvas.create_rectangle(
            x0, y0, x1, y1,
            outline="#1a73e8", width=2,
            fill="#1a73e833",
        )

        w = abs(x1 - x0)
        h = abs(y1 - y0)
        self.dim_label_id = self.canvas.create_text(
            min(x0, x1) + w // 2, min(y0, y1) - 15,
            text=f"{w} x {h}",
            fill="white", font=("Segoe UI", 12, "bold"),
        )

    def _on_release(self, event):
        x0 = min(self.start_x, event.x)
        y0 = min(self.start_y, event.y)
        x1 = max(self.start_x, event.x)
        y1 = max(self.start_y, event.y)

        w = x1 - x0
        h = y1 - y0

        if w < 10 or h < 10:
            self._on_cancel()
            return

        # Adjust for monitor offset
        x0 += self._monitor["left"]
        y0 += self._monitor["top"]

        self.destroy()
        self.callback((x0, y0, w, h))

    def _on_cancel(self, event=None):
        self.destroy()
        self.callback(None)
