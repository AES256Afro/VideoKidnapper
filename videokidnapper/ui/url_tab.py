import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.config import PRESETS, EXPORT_FORMATS, SUPPORTED_PLATFORMS
from videokidnapper.core.downloader import (
    cleanup_temp, detect_platform, download_video,
)
from videokidnapper.core.ffmpeg_backend import (
    concat_clips, get_video_info, trim_to_gif, trim_to_video,
)
from videokidnapper.core.preview import clear_cache
from videokidnapper.ui import theme as T
from videokidnapper.ui.batch_queue import BatchPanel
from videokidnapper.ui.export_dialog import ExportDialog
from videokidnapper.ui.export_options import ExportOptionsPanel
from videokidnapper.ui.multi_range import RangeQueue
from videokidnapper.ui.text_layers import TextLayersPanel
from videokidnapper.ui.theme import button
from videokidnapper.ui.video_player import VideoPlayer
from videokidnapper.ui.waveform import WaveformStrip
from videokidnapper.ui.widgets import PlatformChip, RangeSlider, TimestampEntry
from videokidnapper.utils import settings
from videokidnapper.utils.file_naming import generate_export_path
from videokidnapper.utils.size_estimator import estimate_bytes, human_bytes
from videokidnapper.utils.srt_parser import parse_srt_file, srt_to_text_layers
from videokidnapper.utils.time_format import seconds_to_hms, hms_to_seconds


BROWSER_CHOICES = ["(no cookies)", "chrome", "firefox", "edge", "brave", "opera"]


class UrlTab(ctk.CTkScrollableFrame):
    """Scrollable tab body — prevents the Export row from clipping at small heights."""

    def __init__(self, master, app, **kwargs):
        super().__init__(
            master,
            fg_color="transparent",
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
            **kwargs,
        )
        self.app = app
        self.video_path = None
        self.video_info = None
        self._download_cancel = threading.Event()
        self._toast = None
        self._platform_chips = {}

        self._build_ui()

    def set_toast(self, toast):
        self._toast = toast

    def _notify(self, message, level="info"):
        if self._toast:
            self._toast.show(message, level)

    # ------------------------------------------------------------------
    def _build_ui(self):
        url_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        url_card.pack(fill="x", padx=12, pady=(12, 6))

        header_row = ctk.CTkFrame(url_card, fg_color="transparent")
        header_row.pack(fill="x", padx=14, pady=(12, 0))

        ctk.CTkLabel(
            header_row, text="Video URL",
            font=T.font(T.SIZE_XL, "bold"), text_color=T.TEXT,
        ).pack(side="left")

        self.platform_badge = ctk.CTkLabel(
            header_row, text="",
            font=T.font(T.SIZE_SM, "bold"),
            text_color=T.TEXT_ON_ACCENT,
            fg_color=T.BG_RAISED,
            corner_radius=10,
            padx=10,
        )
        self.platform_badge.pack(side="right")

        chip_row = ctk.CTkFrame(url_card, fg_color="transparent")
        chip_row.pack(fill="x", padx=14, pady=(6, 0))
        ctk.CTkLabel(
            chip_row, text="Supports",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(side="left", padx=(0, 8))
        for platform in SUPPORTED_PLATFORMS.keys():
            chip = PlatformChip(chip_row, platform, on_click=None)
            chip.pack(side="left", padx=3)
            self._platform_chips[platform] = chip

        # Input row
        input_row = ctk.CTkFrame(url_card, fg_color="transparent")
        input_row.pack(fill="x", padx=14, pady=(10, 4))

        self.url_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Paste a URL  (Ctrl+V to paste, Enter to download)",
            font=T.font(T.SIZE_MD),
            height=T.INPUT_HEIGHT,
            fg_color=T.BG_RAISED,
            border_color=T.BORDER_STRONG,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.url_entry.bind("<Return>", lambda e: self._download())
        self.url_entry.bind("<KeyRelease>", self._on_url_typed)

        button(
            input_row, "Paste", variant="secondary",
            width=80, height=32, command=self._paste_from_clipboard,
        ).pack(side="left", padx=(0, 6))

        self.download_btn = button(
            input_row, "  ⬇  Download", variant="primary",
            width=140, height=34, command=self._download,
        )
        self.download_btn.pack(side="left")

        # Cookies row
        cookie_row = ctk.CTkFrame(url_card, fg_color="transparent")
        cookie_row.pack(fill="x", padx=14, pady=(4, 4))

        ctk.CTkLabel(
            cookie_row, text="Cookies from",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(side="left", padx=(0, 4))
        initial = settings.get("cookies_browser") or "(no cookies)"
        self.cookies_var = ctk.StringVar(value=initial)
        ctk.CTkOptionMenu(
            cookie_row, variable=self.cookies_var, values=BROWSER_CHOICES, width=130,
            fg_color=T.BG_RAISED, button_color=T.BG_HOVER,
            button_hover_color=T.BG_ACTIVE, text_color=T.TEXT,
            dropdown_fg_color=T.BG_RAISED, dropdown_text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
            command=self._on_cookies_change,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            cookie_row,
            text="(needed for some Instagram / private X videos)",
            font=T.font(T.SIZE_XS), text_color=T.TEXT_DIM,
        ).pack(side="left")

        # Status + progress
        self.status_label = ctk.CTkLabel(
            url_card, text="Enter a video URL and click Download",
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_DIM, anchor="w",
        )
        self.status_label.pack(fill="x", padx=14, pady=(6, 4))

        self.download_progress = ctk.CTkProgressBar(
            url_card, height=8,
            progress_color=T.ACCENT,
            fg_color=T.BG_RAISED,
            corner_radius=4,
        )
        self.download_progress.pack(fill="x", padx=14, pady=(0, 12))
        self.download_progress.set(0)

        # Batch panel (collapsible)
        self.batch = BatchPanel(
            self,
            get_cookies=self._get_cookies,
            on_video_selected=self._load_downloaded_path,
        )
        self.batch.pack(fill="x", padx=12, pady=6)

        # Preview + waveform + timeline + layers + export. Fixed height —
        # the player letterboxes to preserve aspect ratio.
        self.player = VideoPlayer(self, height=380)
        self.player.pack(fill="x", padx=12, pady=6)
        self.player.pack_propagate(False)
        self.player.set_text_layers_provider(self._current_text_layers)

        timeline_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        timeline_card.pack(fill="x", padx=12, pady=6)

        self.waveform = WaveformStrip(timeline_card)
        self.waveform.pack(fill="x", padx=14, pady=(10, 4))

        self.range_slider = RangeSlider(
            timeline_card, from_=0, to=100,
            command=self._on_slider_change,
        )
        self.range_slider.pack(fill="x", padx=14, pady=(0, 6))

        time_row = ctk.CTkFrame(timeline_card, fg_color="transparent")
        time_row.pack(fill="x", padx=14, pady=(0, 10))

        self.start_entry = TimestampEntry(
            time_row, label="Start", default="00:00:00.000",
            command=self._on_start_entry,
        )
        self.start_entry.pack(side="left", padx=(0, 20))

        self.end_entry = TimestampEntry(
            time_row, label="End", default="00:00:00.000",
            command=self._on_end_entry,
        )
        self.end_entry.pack(side="left", padx=(0, 20))

        self.duration_label = ctk.CTkLabel(
            time_row, text="Duration  —",
            font=T.font(T.SIZE_MD, "bold", mono=True),
            text_color=T.TEXT_MUTED,
        )
        self.duration_label.pack(side="left")

        self.play_btn = button(
            time_row, "▶  Play", variant="secondary",
            width=90, height=32, command=self._toggle_play,
        )
        self.play_btn.pack(side="right", padx=(4, 0))

        button(
            time_row, "◉  System", variant="ghost",
            width=90, height=32, command=self._play_in_system,
        ).pack(side="right", padx=(4, 0))

        self.crop_btn = button(
            time_row, "⬚  Crop", variant="secondary",
            width=80, height=32, command=self._toggle_crop_mode,
        )
        self.crop_btn.pack(side="right", padx=(4, 0))

        button(
            time_row, "+ Queue", variant="secondary",
            width=90, height=32, command=self._queue_range,
        ).pack(side="right", padx=(4, 0))

        button(
            time_row, "⇪ SRT", variant="ghost",
            width=70, height=32, command=self._import_srt,
        ).pack(side="right", padx=(4, 0))

        self.range_queue = RangeQueue(self, on_remove=self._update_export_enabled)
        self.range_queue.pack(fill="x", padx=12, pady=6)

        self.text_layers = TextLayersPanel(self, on_change=self._on_text_layers_changed)
        self.text_layers.pack(fill="x", padx=12, pady=6)

        self.export_options = ExportOptionsPanel(self, on_change=self._update_size_estimate)
        self.export_options.pack(fill="x", padx=12, pady=6)

        export_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        export_card.pack(fill="x", padx=12, pady=(6, 12))

        exp_inner = ctk.CTkFrame(export_card, fg_color="transparent")
        exp_inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(
            exp_inner, text="Quality",
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))
        self.quality_var = ctk.StringVar(value=settings.get("quality", "Medium"))
        self.quality_menu = ctk.CTkOptionMenu(
            exp_inner, variable=self.quality_var,
            values=list(PRESETS.keys()), width=120,
            fg_color=T.BG_RAISED, button_color=T.BG_HOVER,
            button_hover_color=T.BG_ACTIVE, text_color=T.TEXT,
            dropdown_fg_color=T.BG_RAISED, dropdown_text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
            command=lambda v: settings.set("quality", v),
        )
        self.quality_menu.pack(side="left", padx=(0, 18))

        ctk.CTkLabel(
            exp_inner, text="Format",
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))
        self.format_var = ctk.StringVar(value=settings.get("format", "GIF"))
        self.format_menu = ctk.CTkOptionMenu(
            exp_inner, variable=self.format_var,
            values=EXPORT_FORMATS, width=100,
            fg_color=T.BG_RAISED, button_color=T.BG_HOVER,
            button_hover_color=T.BG_ACTIVE, text_color=T.TEXT,
            dropdown_fg_color=T.BG_RAISED, dropdown_text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
            command=lambda v: settings.set("format", v),
        )
        self.format_menu.pack(side="left")

        self.export_btn = button(
            exp_inner, "  Export  ▸  (Ctrl+E)", variant="primary",
            width=200, command=self._export,
        )
        self.export_btn.configure(state="disabled")
        self.export_btn.pack(side="right")

        self.size_label = ctk.CTkLabel(
            exp_inner, text="",
            font=T.font(T.SIZE_SM, mono=True),
            text_color=T.TEXT_DIM,
        )
        self.size_label.pack(side="right", padx=(0, 12))

    # ------------------------------------------------------------------
    # Text layers / player helpers
    # ------------------------------------------------------------------
    def _current_text_layers(self):
        return self.text_layers.get_all_layers(include_empty=False)

    def _on_text_layers_changed(self):
        self.player.refresh_overlay()

    # ------------------------------------------------------------------
    # Cookies
    # ------------------------------------------------------------------
    def _on_cookies_change(self, value):
        if value == "(no cookies)":
            settings.set("cookies_browser", "")
        else:
            settings.set("cookies_browser", value)

    def _get_cookies(self):
        browser = settings.get("cookies_browser") or ""
        if browser:
            return {"browser": browser}
        return None

    # ------------------------------------------------------------------
    # URL entry + paste
    # ------------------------------------------------------------------
    def _paste_from_clipboard(self):
        try:
            data = self.clipboard_get()
        except Exception:
            data = ""
        if data:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, data.strip())
            self._on_url_typed()

    def _set_active_chip(self, platform):
        for name, chip in self._platform_chips.items():
            chip.set_active(name == platform)

    def _on_url_typed(self, _event=None):
        url = self.url_entry.get().strip()
        platform = detect_platform(url)
        self._set_active_chip(platform)

        if platform:
            color = T.PLATFORM_COLORS.get(platform, T.ACCENT)
            self.platform_badge.configure(
                text=f" {platform} ",
                fg_color=color,
                text_color=T.TEXT_ON_ACCENT,
            )
        elif url:
            self.platform_badge.configure(
                text=" Unrecognized ",
                fg_color=T.BG_RAISED,
                text_color=T.TEXT_DIM,
            )
        else:
            self.platform_badge.configure(
                text="", fg_color=T.BG_RAISED, text_color=T.TEXT_DIM,
            )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def _download(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(text="Please enter a URL", text_color=T.DANGER)
            self._notify("No URL provided", "warn")
            return

        platform = detect_platform(url)
        if not platform:
            self.status_label.configure(
                text="Unrecognized URL — trying yt-dlp anyway...",
                text_color=T.WARN,
            )

        self._download_cancel.clear()
        self.download_btn.configure(state="disabled", text="  Downloading...")
        self.url_entry.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        label = f"Fetching {platform} video..." if platform else "Fetching video..."
        self.status_label.configure(text=label, text_color=T.TEXT_MUTED)
        self.download_progress.set(0)
        self._notify(label, "info")

        cookies = self._get_cookies()

        def run_download():
            def progress_cb(value, text=""):
                if self.winfo_exists():
                    self.after(0, self._update_download_progress, value, text)

            result = download_video(
                url,
                progress_callback=progress_cb,
                cancel_event=self._download_cancel,
                cookies=cookies,
            )

            if self.winfo_exists():
                self.after(0, self._on_download_complete, result)

        threading.Thread(target=run_download, daemon=True).start()

    def _update_download_progress(self, value, text):
        self.download_progress.set(value)
        if text:
            self.status_label.configure(text=text, text_color=T.TEXT_MUTED)

    def _on_download_complete(self, result):
        self.download_btn.configure(state="normal", text="  ⬇  Download")
        self.url_entry.configure(state="normal")

        if result.get("error"):
            if result["error"] == "cancelled":
                self.status_label.configure(text="Download cancelled", text_color=T.TEXT_DIM)
                self._notify("Download cancelled", "warn")
            else:
                print(f"Download error: {result['error']}", file=sys.stderr)
                self.status_label.configure(
                    text=f"Error: {result['error'][:80]}", text_color=T.DANGER,
                )
                self._notify(f"Download failed: {result['error'][:60]}", "error")
            self.download_progress.set(0)
            return

        path = result.get("path")
        if not path:
            self.status_label.configure(text="Error: No file downloaded", text_color=T.DANGER)
            self._notify("No file downloaded", "error")
            return

        title = result.get("title", "Unknown")
        platform = result.get("platform") or "Video"
        self.download_progress.set(1.0)
        self._load_downloaded_path(path, platform=platform, title=title)

    def _load_downloaded_path(self, path, platform=None, title=None):
        self.video_path = path
        # Crop rects are source-pixel specific; carrying one over from a
        # previous video will make ffmpeg reject the export.
        settings.set("crop", None)
        self.player.set_crop(None)
        self._crop_on = False
        if hasattr(self, "crop_btn"):
            self.crop_btn.configure(
                text="⬚  Crop", fg_color=T.BG_RAISED, text_color=T.TEXT,
            )
        try:
            self.video_info = get_video_info(path)
        except Exception as e:
            self.status_label.configure(text=f"Error reading video: {e}", text_color=T.DANGER)
            self._notify(f"Could not read video: {e}", "error")
            return

        dur = self.video_info["duration"]
        res = f"{self.video_info['width']}x{self.video_info['height']}"
        label_title = title or os.path.basename(path)
        self.status_label.configure(
            text=f"{label_title}   ·   {res}   ·   {seconds_to_hms(dur)}",
            text_color=T.TEXT,
        )

        clear_cache()
        self.range_slider.set_range(0, dur)
        self.start_entry.set_value(seconds_to_hms(0))
        self.end_entry.set_value(seconds_to_hms(dur))
        self._update_duration_label(0, dur)
        self.text_layers.set_duration(dur)
        self.range_queue.clear()

        self.player.load_video(path, dur)
        self.waveform.load(path, dur)
        self._update_export_enabled()
        if platform:
            self._notify(f"Loaded from {platform}", "success")

    # ------------------------------------------------------------------
    def _on_slider_change(self, start_val, end_val):
        self.start_entry.set_value(seconds_to_hms(start_val))
        self.end_entry.set_value(seconds_to_hms(end_val))
        self._update_duration_label(start_val, end_val)
        self.player.show_frame(start_val)
        self.waveform.set_range(start_val, end_val)

    def _on_start_entry(self, value):
        try:
            start_sec = hms_to_seconds(value)
            _, end_val = self.range_slider.get_values()
            self.range_slider.set_values(start_sec, end_val)
            self._update_duration_label(start_sec, end_val)
            self.player.show_frame(start_sec)
            self.waveform.set_range(start_sec, end_val)
        except ValueError:
            pass

    def _on_end_entry(self, value):
        try:
            end_sec = hms_to_seconds(value)
            start_val, _ = self.range_slider.get_values()
            self.range_slider.set_values(start_val, end_sec)
            self._update_duration_label(start_val, end_sec)
            self.waveform.set_range(start_val, end_sec)
        except ValueError:
            pass

    def _update_duration_label(self, start, end):
        dur = max(0, end - start)
        self.duration_label.configure(text=f"Duration  {seconds_to_hms(dur)}")

    def _update_export_enabled(self):
        enabled = self.video_path is not None
        self.export_btn.configure(state="normal" if enabled else "disabled")
        self._update_size_estimate()

    def _update_size_estimate(self):
        if not self.video_path or not self.video_info:
            self.size_label.configure(text="")
            return
        ranges = self._gather_ranges()
        duration = sum(max(0.0, e - s) for s, e in ranges)
        fmt = self.format_var.get()
        opts = self.export_options.get_options()
        est = estimate_bytes(
            duration, self.quality_var.get(),
            "MP3" if opts.get("audio_only") else fmt,
            self.video_info.get("width", 0),
            self.video_info.get("height", 0),
            audio_only=opts.get("audio_only"),
        )
        self.size_label.configure(text=f"~{human_bytes(est)}")

    def _queue_range(self):
        if not self.video_path:
            return
        start, end = self.range_slider.get_values()
        if self.range_queue.add_range(start, end):
            self._notify(f"Queued range {seconds_to_hms(start)} → {seconds_to_hms(end)}", "success")
            self._update_size_estimate()

    def _play_in_system(self):
        if not self.video_path:
            return
        if os.name == "nt":
            os.startfile(self.video_path)  # noqa: S606
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", self.video_path])
        else:
            subprocess.Popen(["xdg-open", self.video_path])

    def _toggle_crop_mode(self):
        is_on = not getattr(self, "_crop_on", False)
        self._crop_on = is_on
        self.player.enable_crop_mode(is_on, on_change=self._on_crop_changed)
        self.crop_btn.configure(
            text="⬚  Crop" if not is_on else "■  Crop ON",
            fg_color=T.BG_RAISED if not is_on else T.ACCENT,
            text_color=T.TEXT if not is_on else T.TEXT_ON_ACCENT,
        )
        if not is_on:
            settings.set("crop", None)
            self.player.set_crop(None)
            self._notify("Crop cleared", "info")

    def _on_crop_changed(self, rect):
        settings.set("crop", rect)
        self._update_size_estimate()

    def _import_srt(self):
        path = filedialog.askopenfilename(
            title="Import SRT subtitles",
            filetypes=[("SRT / VTT", "*.srt *.vtt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            entries = parse_srt_file(path)
            if not entries:
                self._notify("No subtitle entries found", "warn")
                return
            self.text_layers.import_srt_layers(srt_to_text_layers(entries))
            self._notify(f"Imported {len(entries)} subtitle line(s)", "success")
        except Exception as e:
            self._notify(f"SRT import failed: {e}", "error")

    # ------------------------------------------------------------------
    def _toggle_play(self):
        if not self.video_path:
            return
        if self.player._playing:
            self.player.stop()
            self.play_btn.configure(text="▶  Play")
        else:
            start, end = self.range_slider.get_values()
            self.player.play(start=start, end=end)
            self.play_btn.configure(text="■  Stop")
            self.after(200, self._poll_play_state)

    def _poll_play_state(self):
        if not self.player._playing:
            self.play_btn.configure(text="▶  Play")
            return
        self.after(200, self._poll_play_state)

    # Keyboard shortcuts dispatched by App
    def keyboard_play_pause(self):
        self._toggle_play()

    def keyboard_nudge(self, delta_seconds):
        if not self.video_path:
            return
        start, end = self.range_slider.get_values()
        new_start = max(0, min(self.video_info["duration"], start + delta_seconds))
        self.range_slider.set_values(new_start, end)
        self._on_slider_change(new_start, end)

    def keyboard_mark_in(self):
        if not self.video_path:
            return
        self.range_slider.set_values(self.player.current_time,
                                     self.range_slider.get_values()[1])
        s, e = self.range_slider.get_values()
        self._on_slider_change(s, e)

    def keyboard_mark_out(self):
        if not self.video_path:
            return
        self.range_slider.set_values(self.range_slider.get_values()[0],
                                     self.player.current_time)
        s, e = self.range_slider.get_values()
        self._on_slider_change(s, e)

    def keyboard_export(self):
        if self.video_path:
            self._export()

    def keyboard_open(self):
        """URL tab has no 'open file' — focus the URL entry instead."""
        self.url_entry.focus_set()

    # ------------------------------------------------------------------
    def _gather_ranges(self):
        ranges = list(self.range_queue.get_ranges())
        start, end = self.range_slider.get_values()
        ranges.append((start, end))
        return ranges

    def _export(self):
        if not self.video_path:
            return

        preset = self.quality_var.get()
        fmt = self.format_var.get()
        options = self.export_options.get_options()
        ext = "mp3" if options.get("audio_only") else ("gif" if fmt == "GIF" else "mp4")
        output_dir = Path(self.export_options.get_output_folder())
        output_dir.mkdir(parents=True, exist_ok=True)

        layers = self.text_layers.get_all_layers()
        ranges = self._gather_ranges()
        concat = options.get("concat") and len(ranges) > 1 and fmt != "GIF" \
                 and not options.get("audio_only")

        title_suffix = " (concat)" if concat else ""
        dialog = ExportDialog(
            self,
            title=f"Exporting {len(ranges)} clip{'s' if len(ranges) != 1 else ''}{title_suffix}...",
        )
        self._notify(f"Exporting {len(ranges)} clip(s) [{preset}]{title_suffix}...", "info")

        def run_export():
            produced = []
            for i, (start, end) in enumerate(ranges, 1):
                if dialog.cancel_event.is_set():
                    break
                output_path = str(generate_export_path("url", ext, base_dir=output_dir))

                def progress_cb(p, i=i):
                    if dialog.winfo_exists():
                        prog = ((i - 1) + p) / len(ranges)
                        dialog.after(0, dialog.update_progress, prog,
                                     f"Clip {i}/{len(ranges)} — encoding {fmt}...")
                try:
                    if options.get("audio_only"):
                        result = trim_to_video(
                            self.video_path, start, end, preset, output_path,
                            text_layers=layers, options=options,
                            progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                        )
                    elif fmt == "GIF":
                        result = trim_to_gif(
                            self.video_path, start, end, preset, output_path,
                            text_layers=layers, options=options,
                            progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                        )
                    else:
                        result = trim_to_video(
                            self.video_path, start, end, preset, output_path,
                            text_layers=layers, options=options,
                            progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                        )
                    if result:
                        produced.append(str(result))
                    else:
                        if dialog.winfo_exists():
                            dialog.after(0, dialog.export_failed,
                                         f"Clip {i} failed — aborting")
                        return
                except Exception as e:
                    if dialog.winfo_exists():
                        dialog.after(0, dialog.export_failed, f"Error: {e}")
                        self._notify(f"Export error: {e}", "error")
                    return

            final_path = None
            if concat and len(produced) > 1:
                combined = str(generate_export_path(
                    "url_concat", ext, base_dir=output_dir,
                ))
                merged = concat_clips(produced, combined)
                if merged:
                    final_path = str(merged)
                    for p in produced:
                        try:
                            Path(p).unlink()
                        except OSError:
                            pass
            if not final_path:
                final_path = produced[-1] if produced else None

            if final_path and dialog.winfo_exists():
                settings.set("last_export", final_path)
                self._record_history(final_path, fmt, preset, options)
                dialog.after(0, dialog.export_complete, final_path)
                self._notify(f"Exported {len(ranges)} clip(s)", "success")
            elif dialog.winfo_exists():
                dialog.after(0, dialog.export_failed, "Cancelled")
                self._notify("Export cancelled", "warn")

        threading.Thread(target=run_export, daemon=True).start()

    def _record_history(self, path, fmt, preset, options):
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = 0
        settings.add_history_entry({
            "path":      path,
            "format":    "MP3" if options.get("audio_only") else fmt,
            "preset":    preset,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "size_bytes": size,
            "mode":      "url",
        })
        if hasattr(self.app, "history_tab") and self.app.history_tab.winfo_exists():
            self.app.history_tab.after(0, self.app.history_tab.refresh)

    def destroy(self):
        self._download_cancel.set()
        cleanup_temp()
        super().destroy()
