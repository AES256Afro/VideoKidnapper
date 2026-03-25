import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk

from videokidnapper.core.preview import get_frame_at


class VideoPlayer(ctk.CTkFrame):
    """Canvas-based video frame preview with scrubbing."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="gray17", corner_radius=10, **kwargs)
        self.video_path = None
        self.duration = 0
        self.current_time = 0
        self._photo = None

        # Preview canvas
        self.canvas = tk.Canvas(
            self, bg="#1a1a2e", highlightthickness=0, cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        # Placeholder text
        self._placeholder_id = self.canvas.create_text(
            0, 0, text="Open a video file to preview",
            fill="gray50", font=("Segoe UI", 16),
        )
        self.canvas.bind("<Configure>", self._on_resize)

    def _on_resize(self, event=None):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        self.canvas.coords(self._placeholder_id, w // 2, h // 2)
        if self.video_path:
            self.show_frame(self.current_time)

    def load_video(self, video_path, duration):
        self.video_path = video_path
        self.duration = duration
        self.current_time = 0
        self.canvas.delete("placeholder")
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

        # Fit frame to canvas
        fw, fh = frame.size
        scale = min(cw / fw, ch / fh)
        new_w = max(1, int(fw * scale))
        new_h = max(1, int(fh * scale))
        resized = frame.resize((new_w, new_h), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(resized)
        self.canvas.delete("frame")
        self.canvas.delete(self._placeholder_id)
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo, tags="frame")

    def clear(self):
        self.video_path = None
        self.duration = 0
        self._photo = None
        self.canvas.delete("frame")
        self._placeholder_id = self.canvas.create_text(
            self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2,
            text="Open a video file to preview",
            fill="gray50", font=("Segoe UI", 16),
        )
