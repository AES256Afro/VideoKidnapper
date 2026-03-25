import sys
import threading

import customtkinter as ctk

from videokidnapper.config import PRESETS, EXPORT_FORMATS
from videokidnapper.core.ffmpeg_backend import get_video_info, trim_to_video, trim_to_gif
from videokidnapper.core.koolaid_extractor import extract_video, get_download_info, download_extracted_video
from videokidnapper.core.preview import clear_cache
from videokidnapper.ui.export_dialog import ExportDialog
from videokidnapper.ui.text_layers import TextLayersPanel
from videokidnapper.ui.video_player import VideoPlayer
from videokidnapper.ui.widgets import RangeSlider, TimestampEntry
from videokidnapper.utils.file_naming import generate_export_path
from videokidnapper.utils.time_format import seconds_to_hms, hms_to_seconds


PLATFORM_COLORS = {
    "reddit": "#FF4500",
    "twitter": "#1DA1F2",
    "facebook": "#1877F2",
}


class KoolaidTab(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self.video_path = None
        self.video_info = None
        self._extract_result = None
        self._cancel_event = threading.Event()

        self._build_ui()

    def _build_ui(self):
        # URL input section
        url_frame = ctk.CTkFrame(self, corner_radius=10)
        url_frame.pack(fill="x", padx=10, pady=(10, 5))

        url_header = ctk.CTkLabel(
            url_frame, text="KoolaidGospel Clipper",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        url_header.pack(anchor="w", padx=15, pady=(12, 2))

        platforms_label = ctk.CTkLabel(
            url_frame, text="Supports: Reddit  |  Twitter/X  |  Facebook",
            font=ctk.CTkFont(size=11), text_color="gray",
        )
        platforms_label.pack(anchor="w", padx=15, pady=(0, 5))

        input_row = ctk.CTkFrame(url_frame, fg_color="transparent")
        input_row.pack(fill="x", padx=15, pady=(0, 5))

        self.url_entry = ctk.CTkEntry(
            input_row, placeholder_text="Paste Reddit, Twitter, or Facebook video URL...",
            font=ctk.CTkFont(size=13), height=36,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.url_entry.bind("<Return>", lambda e: self._extract())

        self.extract_btn = ctk.CTkButton(
            input_row, text="  Extract & Download", width=180, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#e84a1a", hover_color="#c43e15",
            command=self._extract,
        )
        self.extract_btn.pack(side="right")

        # Status area
        status_row = ctk.CTkFrame(url_frame, fg_color="transparent")
        status_row.pack(fill="x", padx=15, pady=(0, 4))

        self.platform_badge = ctk.CTkLabel(
            status_row, text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=4, width=0,
        )
        self.platform_badge.pack(side="left")

        self.status_label = ctk.CTkLabel(
            status_row, text="Paste a video URL and click Extract",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self.status_label.pack(side="left", padx=8)

        self.progress_bar = ctk.CTkProgressBar(url_frame, height=8)
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 12))
        self.progress_bar.set(0)

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

        # Text layers panel
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

    def _extract(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(text="Please enter a URL", text_color="#e84a1a")
            return

        self._cancel_event.clear()
        self.extract_btn.configure(state="disabled", text="  Extracting...")
        self.url_entry.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.status_label.configure(text="Extracting video info...", text_color="gray")
        self.platform_badge.configure(text="")
        self.progress_bar.set(0)

        def run():
            # Step 1: Extract video info from API
            result = extract_video(url)

            if result.get("error"):
                if self.winfo_exists():
                    self.after(0, self._on_error, result["error"])
                return

            info = get_download_info(result)

            if self.winfo_exists():
                self.after(0, self._show_platform, info["platform"], info["title"])

            # Step 2: Download the video
            def progress_cb(value, text=""):
                if self.winfo_exists():
                    self.after(0, self._update_progress, value, text)

            dl_result = download_extracted_video(
                info["video_url"],
                audio_url=info.get("audio_url"),
                progress_callback=progress_cb,
                cancel_event=self._cancel_event,
            )

            if self.winfo_exists():
                self.after(0, self._on_download_complete, dl_result, info)

        threading.Thread(target=run, daemon=True).start()

    def _show_platform(self, platform, title):
        color = PLATFORM_COLORS.get(platform, "#666")
        self.platform_badge.configure(
            text=f"  {platform.upper()}  ",
            fg_color=color, text_color="white",
        )
        self.status_label.configure(text=title[:60], text_color="white")

    def _update_progress(self, value, text):
        self.progress_bar.set(value)
        if text:
            self.status_label.configure(text=text)

    def _on_error(self, error_msg):
        print(f"KoolaidGospel error: {error_msg}", file=sys.stderr)
        self.extract_btn.configure(state="normal", text="  Extract & Download")
        self.url_entry.configure(state="normal")
        self.status_label.configure(text=f"Error: {error_msg[:80]}", text_color="#e84a1a")
        self.progress_bar.set(0)

    def _on_download_complete(self, dl_result, info):
        self.extract_btn.configure(state="normal", text="  Extract & Download")
        self.url_entry.configure(state="normal")

        if dl_result.get("error"):
            err = dl_result["error"]
            if err == "cancelled":
                self.status_label.configure(text="Cancelled", text_color="gray")
            else:
                self._on_error(err)
            return

        path = dl_result.get("path")
        if not path:
            self._on_error("No video file downloaded")
            return

        self.video_path = path
        self.progress_bar.set(1.0)

        try:
            self.video_info = get_video_info(path)
        except Exception as e:
            self._on_error(f"Error reading video: {e}")
            return

        dur = self.video_info["duration"]
        res = f"{self.video_info['width']}x{self.video_info['height']}"
        title = info.get("title", "Untitled")
        self.status_label.configure(
            text=f"{title[:40]}  |  {res}  |  {seconds_to_hms(dur)}",
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
        output_path = str(generate_export_path("koolaid", ext))
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
