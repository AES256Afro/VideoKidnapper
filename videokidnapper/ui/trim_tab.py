import threading
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.config import PRESETS, SUPPORTED_VIDEO_EXTENSIONS, EXPORT_FORMATS
from videokidnapper.core.ffmpeg_backend import get_video_info, trim_to_video, trim_to_gif
from videokidnapper.core.preview import clear_cache
from videokidnapper.ui.export_dialog import ExportDialog
from videokidnapper.ui.text_layers import TextLayersPanel
from videokidnapper.ui.video_player import VideoPlayer
from videokidnapper.ui.widgets import RangeSlider, TimestampEntry
from videokidnapper.utils.file_naming import generate_export_path
from videokidnapper.utils.time_format import seconds_to_hms, hms_to_seconds


class TrimTab(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self.video_path = None
        self.video_info = None

        self._build_ui()

    def _build_ui(self):
        # Top controls
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 5))

        self.open_btn = ctk.CTkButton(
            top, text="  Open Video File", width=180, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._open_file,
        )
        self.open_btn.pack(side="left")

        self.file_label = ctk.CTkLabel(
            top, text="No file loaded",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self.file_label.pack(side="left", padx=15)

        # Video preview
        self.player = VideoPlayer(self)
        self.player.pack(fill="both", expand=True, padx=10, pady=5)

        # Timeline slider
        slider_frame = ctk.CTkFrame(self, fg_color="transparent")
        slider_frame.pack(fill="x", padx=10, pady=5)

        self.range_slider = RangeSlider(
            slider_frame, from_=0, to=100,
            command=self._on_slider_change,
        )
        self.range_slider.pack(fill="x")

        # Timestamp entries
        time_frame = ctk.CTkFrame(self, fg_color="transparent")
        time_frame.pack(fill="x", padx=10, pady=5)

        self.start_entry = TimestampEntry(
            time_frame, label="Start:", default="00:00:00.000",
            command=self._on_start_entry,
        )
        self.start_entry.pack(side="left", padx=(0, 20))

        self.end_entry = TimestampEntry(
            time_frame, label="End:", default="00:00:00.000",
            command=self._on_end_entry,
        )
        self.end_entry.pack(side="left", padx=(0, 20))

        self.duration_label = ctk.CTkLabel(
            time_frame, text="Duration: --",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self.duration_label.pack(side="left")

        # Text layers panel (collapsible)
        self.text_layers = TextLayersPanel(self)
        self.text_layers.pack(fill="x", padx=10, pady=5)

        # Export controls
        export_frame = ctk.CTkFrame(self, fg_color="transparent")
        export_frame.pack(fill="x", padx=10, pady=(5, 10))

        ctk.CTkLabel(export_frame, text="Quality:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 5))
        self.quality_var = ctk.StringVar(value="Medium")
        self.quality_menu = ctk.CTkOptionMenu(
            export_frame, variable=self.quality_var,
            values=list(PRESETS.keys()), width=120,
        )
        self.quality_menu.pack(side="left", padx=(0, 15))

        ctk.CTkLabel(export_frame, text="Format:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(0, 5))
        self.format_var = ctk.StringVar(value="GIF")
        self.format_menu = ctk.CTkOptionMenu(
            export_frame, variable=self.format_var,
            values=EXPORT_FORMATS, width=100,
        )
        self.format_menu.pack(side="left", padx=(0, 15))

        self.export_btn = ctk.CTkButton(
            export_frame, text="  Export", width=140, height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1a73e8", hover_color="#1557b0",
            command=self._export, state="disabled",
        )
        self.export_btn.pack(side="right")

    def _open_file(self):
        exts = " ".join(f"*{e}" for e in SUPPORTED_VIDEO_EXTENSIONS)
        path = filedialog.askopenfilename(
            title="Open Video File",
            filetypes=[("Video files", exts), ("All files", "*.*")],
        )
        if not path:
            return

        self.video_path = path
        try:
            self.video_info = get_video_info(path)
        except Exception as e:
            self.file_label.configure(text=f"Error: {e}", text_color="#e84a1a")
            return

        name = path.split("/")[-1].split("\\")[-1]
        dur = self.video_info["duration"]
        res = f"{self.video_info['width']}x{self.video_info['height']}"
        self.file_label.configure(
            text=f"{name}  |  {res}  |  {seconds_to_hms(dur)}",
            text_color="white",
        )

        clear_cache()
        self.range_slider.set_range(0, dur)
        self.start_entry.set_value(seconds_to_hms(0))
        self.end_entry.set_value(seconds_to_hms(dur))
        self._update_duration_label(0, dur)
        self.text_layers.set_duration(dur)

        self.player.load_video(path, dur)
        self.export_btn.configure(state="normal")

    def _on_slider_change(self, start_val, end_val):
        self.start_entry.set_value(seconds_to_hms(start_val))
        self.end_entry.set_value(seconds_to_hms(end_val))
        self._update_duration_label(start_val, end_val)
        self.player.show_frame(start_val)

    def _on_start_entry(self, value):
        try:
            start_sec = hms_to_seconds(value)
            _, end_val = self.range_slider.get_values()
            self.range_slider.set_values(start_sec, end_val)
            self._update_duration_label(start_sec, end_val)
            self.player.show_frame(start_sec)
        except ValueError:
            pass

    def _on_end_entry(self, value):
        try:
            end_sec = hms_to_seconds(value)
            start_val, _ = self.range_slider.get_values()
            self.range_slider.set_values(start_val, end_sec)
            self._update_duration_label(start_val, end_sec)
        except ValueError:
            pass

    def _update_duration_label(self, start, end):
        dur = max(0, end - start)
        self.duration_label.configure(text=f"Duration: {seconds_to_hms(dur)}")

    def _export(self):
        if not self.video_path:
            return

        start, end = self.range_slider.get_values()
        preset = self.quality_var.get()
        fmt = self.format_var.get()
        ext = "gif" if fmt == "GIF" else "mp4"
        output_path = str(generate_export_path("trim", ext))
        layers = self.text_layers.get_all_layers()

        dialog = ExportDialog(self, title=f"Exporting {fmt}...")

        def run_export():
            def progress_cb(p):
                if dialog.winfo_exists():
                    dialog.after(0, dialog.update_progress, p, f"Encoding {fmt}...")

            try:
                if fmt == "GIF":
                    result = trim_to_gif(
                        self.video_path, start, end, preset, output_path,
                        text_layers=layers,
                        progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                    )
                else:
                    result = trim_to_video(
                        self.video_path, start, end, preset, output_path,
                        text_layers=layers,
                        progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                    )
                if result and dialog.winfo_exists():
                    dialog.after(0, dialog.export_complete, str(result))
                elif dialog.winfo_exists():
                    dialog.after(0, dialog.export_failed, "Export failed or was cancelled")
            except Exception as e:
                if dialog.winfo_exists():
                    dialog.after(0, dialog.export_failed, f"Error: {e}")

        threading.Thread(target=run_export, daemon=True).start()
