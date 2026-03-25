import sys
import threading

import customtkinter as ctk

from videokidnapper.config import PRESETS, EXPORT_FORMATS
from videokidnapper.core.downloader import download_video, get_video_info_from_url, cleanup_temp
from videokidnapper.core.ffmpeg_backend import get_video_info, trim_to_video, trim_to_gif
from videokidnapper.core.preview import clear_cache
from videokidnapper.ui.export_dialog import ExportDialog
from videokidnapper.ui.text_layers import TextLayersPanel
from videokidnapper.ui.video_player import VideoPlayer
from videokidnapper.ui.widgets import RangeSlider, TimestampEntry
from videokidnapper.utils.file_naming import generate_export_path
from videokidnapper.utils.time_format import seconds_to_hms, hms_to_seconds


class UrlTab(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self.video_path = None
        self.video_info = None
        self._download_cancel = threading.Event()

        self._build_ui()

    def _build_ui(self):
        # URL input section
        url_frame = ctk.CTkFrame(self, corner_radius=10)
        url_frame.pack(fill="x", padx=10, pady=(10, 5))

        url_header = ctk.CTkLabel(
            url_frame, text="YouTube URL",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        url_header.pack(anchor="w", padx=15, pady=(12, 5))

        input_row = ctk.CTkFrame(url_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=15, pady=(0, 5))

        self.url_entry = ctk.CTkEntry(
            input_row, placeholder_text="Paste YouTube URL here...",
            font=ctk.CTkFont(size=13), height=36,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.url_entry.bind("<Return>", lambda e: self._download())

        self.download_btn = ctk.CTkButton(
            input_row, text="  Download", width=140, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#e84a1a", hover_color="#c43e15",
            command=self._download,
        )
        self.download_btn.pack(side="right")

        # Download status
        status_row = ctk.CTkFrame(url_frame, fg_color="transparent")
        status_row.pack(fill="x", padx=15, pady=(0, 8))

        self.status_label = ctk.CTkLabel(
            status_row, text="Enter a YouTube URL and click Download",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self.status_label.pack(side="left")

        self.download_progress = ctk.CTkProgressBar(url_frame, width=350, height=8)
        self.download_progress.pack(fill="x", padx=15, pady=(0, 12))
        self.download_progress.set(0)

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

    def _download(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(text="Please enter a URL", text_color="#e84a1a")
            return

        self._download_cancel.clear()
        self.download_btn.configure(state="disabled", text="  Downloading...")
        self.url_entry.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.status_label.configure(text="Fetching video info...", text_color="gray")
        self.download_progress.set(0)

        def run_download():
            def progress_cb(value, text=""):
                if self.winfo_exists():
                    self.after(0, self._update_download_progress, value, text)

            result = download_video(
                url,
                progress_callback=progress_cb,
                cancel_event=self._download_cancel,
            )

            if self.winfo_exists():
                self.after(0, self._on_download_complete, result)

        threading.Thread(target=run_download, daemon=True).start()

    def _update_download_progress(self, value, text):
        self.download_progress.set(value)
        if text:
            self.status_label.configure(text=text)

    def _on_download_complete(self, result):
        self.download_btn.configure(state="normal", text="  Download")
        self.url_entry.configure(state="normal")

        if result.get("error"):
            if result["error"] == "cancelled":
                self.status_label.configure(text="Download cancelled", text_color="gray")
            else:
                print(f"Download error: {result['error']}", file=sys.stderr)
                self.status_label.configure(
                    text=f"Error: {result['error'][:80]}", text_color="#e84a1a",
                )
            self.download_progress.set(0)
            return

        path = result.get("path")
        title = result.get("title", "Unknown")

        if not path:
            self.status_label.configure(text="Error: No file downloaded", text_color="#e84a1a")
            return

        self.video_path = path
        self.download_progress.set(1.0)

        try:
            self.video_info = get_video_info(path)
        except Exception as e:
            self.status_label.configure(text=f"Error reading video: {e}", text_color="#e84a1a")
            return

        dur = self.video_info["duration"]
        res = f"{self.video_info['width']}x{self.video_info['height']}"
        self.status_label.configure(
            text=f"{title}  |  {res}  |  {seconds_to_hms(dur)}",
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
        output_path = str(generate_export_path("url", ext))
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

    def destroy(self):
        self._download_cancel.set()
        cleanup_temp()
        super().destroy()
