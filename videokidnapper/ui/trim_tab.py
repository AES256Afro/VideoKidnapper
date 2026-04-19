# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.config import PRESETS, SUPPORTED_VIDEO_EXTENSIONS, EXPORT_FORMATS
from videokidnapper.core.ffmpeg_backend import (
    concat_clips_with_transition, frames_to_video,
    get_video_info, trim_to_gif, trim_to_video,
)
from videokidnapper.core.preview import clear_cache
from videokidnapper.core.screen_capture import record_screen
from videokidnapper.ui import theme as T
from videokidnapper.ui.export_dialog import ExportDialog
from videokidnapper.ui.export_options import ExportOptionsPanel
from videokidnapper.ui.image_layers import ImageLayersPanel
from videokidnapper.ui.multi_range import RangeQueue
from videokidnapper.ui.text_layers import TextLayersPanel
from videokidnapper.ui.theme import button
from videokidnapper.ui.thumbnail_strip import ThumbnailStrip
from videokidnapper.ui.video_player import VideoPlayer
from videokidnapper.ui.waveform import WaveformStrip
from videokidnapper.ui.widgets import RangeSlider, TimestampEntry
from videokidnapper.utils import settings
from videokidnapper.utils.file_naming import generate_export_path
from videokidnapper.utils.size_estimator import estimate_bytes, human_bytes
from videokidnapper.utils.srt_parser import parse_srt_file, srt_to_text_layers
from videokidnapper.utils.time_format import seconds_to_hms, hms_to_seconds
from videokidnapper.utils.undo import UndoStack


class TrimTab(ctk.CTkScrollableFrame):
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
        self._toast = None

        # Undo/redo machinery. ``_restoring`` guards the widget callbacks
        # that would otherwise record a new snapshot while we're applying
        # one; ``_snapshot_after_id`` debounces rapid-fire edits (typing,
        # slider scrub) into a single history entry per settled state.
        self._undo_stack = UndoStack(cap=50)
        self._restoring = False
        self._snapshot_after_id = None
        self._snapshot_debounce_ms = 350

        self._build_ui()

    def set_toast(self, toast):
        self._toast = toast

    def _notify(self, message, level="info"):
        if self._toast:
            self._toast.show(message, level)

    # ------------------------------------------------------------------
    def _build_ui(self):
        source_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        source_card.pack(fill="x", padx=12, pady=(12, 6))

        src_inner = ctk.CTkFrame(source_card, fg_color="transparent")
        src_inner.pack(fill="x", padx=14, pady=12)

        self.open_btn = button(
            src_inner, "  ⇪  Open Video File", variant="primary",
            width=170, command=self._open_file,
        )
        self.open_btn.pack(side="left")

        button(
            src_inner, "  ⊞  Record Screen", variant="secondary",
            width=160, height=36, command=self._record_screen,
        ).pack(side="left", padx=(8, 0))

        button(
            src_inner, "  ⇪  Import SRT", variant="ghost",
            width=130, height=36, command=self._import_srt,
        ).pack(side="left", padx=(4, 0))

        # Whisper auto-captions — only enabled once a video is loaded.
        # Clicking kicks off a background transcription; result feeds
        # into the same text-layers panel the SRT importer targets.
        self.captions_btn = button(
            src_inner, "  🗣  Auto-captions", variant="ghost",
            width=150, height=36, command=self._auto_caption,
        )
        self.captions_btn.pack(side="left", padx=(4, 0))

        self.file_label = ctk.CTkLabel(
            src_inner, text="No file loaded   ·   Ctrl+O, drag a file, or click the preview",
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_DIM,
        )
        self.file_label.pack(side="left", padx=15)

        # Preview (clickable + DnD-aware). Fixed height inside a scrollable
        # tab — the player letterboxes to preserve aspect ratio.
        self.player = VideoPlayer(
            self,
            on_empty_click=self._open_file,
            on_file_dropped=self._on_file_dropped,
            height=380,
        )
        self.player.pack(fill="x", padx=12, pady=6)
        self.player.pack_propagate(False)
        self.player.set_text_layers_provider(self._current_text_layers)
        # Image overlays share the same provider pattern as text layers —
        # the player composites PNG files on top of the frame in source-
        # resolution space so the preview matches the exported output.
        self.player.set_image_layers_provider(self._current_image_layers)
        # Click-drag on the preview moves the active layer. The panel owns
        # the widget state, so we forward via its set_layer_position entry.
        self.player.set_text_position_callback(
            lambda i, x, y: self.text_layers.set_layer_position(i, x, y),
        )

        # Waveform + timeline card
        timeline_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        timeline_card.pack(fill="x", padx=12, pady=6)

        # Thumbnail strip sits above the waveform — click to seek. It
        # extracts in the background so it never blocks video load.
        self.thumbnail_strip = ThumbnailStrip(
            timeline_card, on_seek=self._seek_from_thumbnail,
        )
        self.thumbnail_strip.pack(fill="x", padx=14, pady=(10, 2))

        self.waveform = WaveformStrip(timeline_card)
        self.waveform.pack(fill="x", padx=14, pady=(2, 4))

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

        # Multi-range queue
        self.range_queue = RangeQueue(self, on_remove=self._on_range_removed)
        self.range_queue.pack(fill="x", padx=12, pady=6)

        # Text layers
        self.text_layers = TextLayersPanel(self, on_change=self._on_text_layers_changed)
        self.text_layers.pack(fill="x", padx=12, pady=6)

        # Image overlays — same collapsible card pattern as text layers.
        # Each row carries a PNG path + anchor + scale + opacity + timing.
        # The export path passes the list through to trim_to_video, which
        # switches to -filter_complex when any are present. The on_change
        # callback triggers a preview refresh so slider drags show live.
        self.image_layers = ImageLayersPanel(self, on_change=self._on_image_layers_changed)
        self.image_layers.pack(fill="x", padx=12, pady=6)

        # Export options (size estimate updates when options change)
        self.export_options = ExportOptionsPanel(self, on_change=self._update_size_estimate)
        self.export_options.pack(fill="x", padx=12, pady=6)

        # Export card
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
    def _current_image_layers(self):
        # Only layers whose path is a real file — the ffmpeg export path
        # applies the same filter, so the preview matches. Using
        # include_empty=False skips half-configured rows where the user
        # hasn't picked a file yet.
        return self.image_layers.get_all_layers()

    def _current_text_layers(self):
        # include_empty keeps the list index aligned with panel.layers so
        # the VideoPlayer's hit-test can call back with the right widget index.
        return self.text_layers.get_all_layers(include_empty=True)

    def _on_text_layers_changed(self):
        self.player.refresh_overlay()

    def _on_image_layers_changed(self):
        # Drop the image cache so newly-picked files aren't shadowed by a
        # previous failure, and re-render the current frame.
        self.player._image_cache.clear()
        self.player.refresh_overlay()
        # Debounce: typing into a text entry fires on every keystroke —
        # we only want one undo entry per "pause".
        self._request_snapshot(immediate=False)

    def _on_range_removed(self):
        self._update_export_enabled()
        self._request_snapshot(immediate=True)

    def _seek_from_thumbnail(self, timestamp):
        """Click on the thumbnail strip → move the trim start to that time."""
        if not self.video_path or not self.video_info:
            return
        end_val = self.range_slider.get_values()[1]
        new_start = max(0.0, min(timestamp, end_val - 0.05))
        self.range_slider.set_values(new_start, end_val)
        self._on_slider_change(new_start, end_val)

    # ------------------------------------------------------------------
    def _open_file(self):
        exts = " ".join(f"*{e}" for e in SUPPORTED_VIDEO_EXTENSIONS)
        path = filedialog.askopenfilename(
            title="Open Video File",
            filetypes=[("Video files", exts), ("All files", "*.*")],
        )
        if path:
            self._load_path(path)

    def _on_file_dropped(self, path):
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_VIDEO_EXTENSIONS:
            self._notify(f"Unsupported file type: {ext}", "warn")
            return
        self._load_path(path)

    def _load_path(self, path):
        # _restoring suppresses undo/redo recording during the flurry of
        # callbacks that fires as we reset every widget below. The stack
        # is re-baselined at the end.
        self._restoring = True
        try:
            self.video_path = path
            # A crop rectangle from a previous video's source pixels doesn't
            # transfer — clear it so the export doesn't choke on out-of-bounds
            # coordinates.
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
                self.file_label.configure(text=f"Error: {e}", text_color=T.DANGER)
                self._notify(f"Could not read video: {e}", "error")
                return

            name = os.path.basename(path)
            dur = self.video_info["duration"]
            res = f"{self.video_info['width']}x{self.video_info['height']}"
            self.file_label.configure(
                text=f"{name}   ·   {res}   ·   {seconds_to_hms(dur)}",
                text_color=T.TEXT,
            )

            clear_cache()
            self.range_slider.set_range(0, dur)
            self.start_entry.set_value(seconds_to_hms(0))
            self.end_entry.set_value(seconds_to_hms(dur))
            self._update_duration_label(0, dur)
            self.text_layers.clear_layers()
            self.text_layers.set_duration(dur)
            self.image_layers.set_duration(dur)
            self.range_queue.clear()

            self.player.load_video(path, dur)
            self.waveform.load(path, dur)
            self.thumbnail_strip.load(path, dur)
            self._update_export_enabled()
            self._notify(f"Loaded {name}", "success")
        finally:
            self._restoring = False
        # Baseline undo history against the freshly-loaded state.
        self._undo_stack.reset(self._snapshot())

    def _on_slider_change(self, start_val, end_val):
        self.start_entry.set_value(seconds_to_hms(start_val))
        self.end_entry.set_value(seconds_to_hms(end_val))
        self._update_duration_label(start_val, end_val)
        self.player.show_frame(start_val)
        self.waveform.set_range(start_val, end_val)
        self.thumbnail_strip.set_range(start_val, end_val)
        self._request_snapshot(immediate=False)

    def _on_start_entry(self, value):
        try:
            start_sec = hms_to_seconds(value)
            _, end_val = self.range_slider.get_values()
            self.range_slider.set_values(start_sec, end_val)
            self._update_duration_label(start_sec, end_val)
            self.player.show_frame(start_sec)
            self.waveform.set_range(start_sec, end_val)
            self.thumbnail_strip.set_range(start_sec, end_val)
            self._request_snapshot(immediate=True)
        except ValueError:
            pass

    def _on_end_entry(self, value):
        try:
            end_sec = hms_to_seconds(value)
            start_val, _ = self.range_slider.get_values()
            self.range_slider.set_values(start_val, end_sec)
            self._update_duration_label(start_val, end_sec)
            self.waveform.set_range(start_val, end_sec)
            self.thumbnail_strip.set_range(start_val, end_sec)
            self._request_snapshot(immediate=True)
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

    # ------------------------------------------------------------------
    def _queue_range(self):
        if not self.video_path:
            return
        start, end = self.range_slider.get_values()
        if self.range_queue.add_range(start, end):
            self._notify(f"Queued range {seconds_to_hms(start)} → {seconds_to_hms(end)}", "success")
            self._update_size_estimate()
            self._request_snapshot(immediate=True)

    # ------------------------------------------------------------------
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
            # Clear any in-progress rect so the next export isn't cropped.
            settings.set("crop", None)
            self.player.set_crop(None)
            self._notify("Crop cleared", "info")

    def _on_crop_changed(self, rect):
        settings.set("crop", rect)
        self._update_size_estimate()
        self._request_snapshot(immediate=True)

    # ------------------------------------------------------------------
    def _auto_caption(self):
        """Run Whisper over the trim range and import the result as layers."""
        if not self.video_path:
            self._notify("Load a video first", "warn")
            return
        # Late-import so the app still runs when faster-whisper isn't installed.
        from videokidnapper.core import whisper_captions

        if not whisper_captions.is_available():
            self._notify(
                "Auto-captions needs faster-whisper. "
                "Install with:  pip install faster-whisper",
                "error",
            )
            return

        # Small dialog: pick model size. Larger = slower + more accurate.
        dialog = ctk.CTkToplevel(self)
        dialog.title("Auto-captions")
        dialog.geometry("360x200")
        dialog.resizable(False, False)
        dialog.configure(fg_color=T.BG_BASE)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        card = ctk.CTkFrame(
            dialog, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            card, text="Generate captions with Whisper",
            font=T.font(T.SIZE_LG, "bold"), text_color=T.TEXT,
        ).pack(pady=(16, 8))

        model_var = ctk.StringVar(value="base")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(pady=4)
        ctk.CTkLabel(
            row, text="Model:", font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(
            row, variable=model_var,
            values=list(whisper_captions.MODEL_SIZES),
            width=100,
            fg_color=T.BG_RAISED, button_color=T.BG_HOVER,
            button_hover_color=T.BG_ACTIVE, text_color=T.TEXT,
        ).pack(side="left")

        ctk.CTkLabel(
            card,
            text=(
                "Transcribes the current trim range only.\n"
                "First run downloads the model (~75 MB for base)."
            ),
            font=T.font(T.SIZE_XS), text_color=T.TEXT_DIM,
            justify="center",
        ).pack(pady=(8, 4))

        def start():
            model_size = model_var.get()
            dialog.destroy()
            self._run_whisper_in_background(model_size)

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=10)
        button(btns, "Start", variant="primary", width=120,
               command=start).pack(side="left", padx=4)
        button(btns, "Cancel", variant="secondary", width=120,
               command=dialog.destroy).pack(side="left", padx=4)

    def _run_whisper_in_background(self, model_size):
        """Worker thread: transcribe then marshal the result back to Tk."""
        from videokidnapper.core import whisper_captions

        start, end = self.range_slider.get_values()
        self._notify(f"Transcribing with Whisper ({model_size})…", "info")
        self.captions_btn.configure(state="disabled")

        def worker():
            try:
                entries = whisper_captions.transcribe(
                    self.video_path,
                    model_size=model_size,
                    start=start, end=end,
                )
            except Exception as exc:
                self.after(0, self._on_captions_failed, str(exc))
                return
            self.after(0, self._on_captions_done, entries)

        threading.Thread(target=worker, daemon=True).start()

    def _on_captions_done(self, entries):
        from videokidnapper.utils.srt_parser import srt_to_text_layers
        self.captions_btn.configure(state="normal")
        if not entries:
            self._notify("Whisper produced no text (silent clip?)", "warn")
            return
        self.text_layers.import_srt_layers(srt_to_text_layers(entries))
        self._notify(f"Imported {len(entries)} caption line(s)", "success")

    def _on_captions_failed(self, error):
        self.captions_btn.configure(state="normal")
        self._notify(f"Auto-captions failed: {error}", "error")

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
    def _record_screen(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Record Screen")
        dialog.geometry("360x200")
        dialog.resizable(False, False)
        dialog.configure(fg_color=T.BG_BASE)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        card = ctk.CTkFrame(
            dialog, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            card, text="Record primary monitor",
            font=T.font(T.SIZE_LG, "bold"), text_color=T.TEXT,
        ).pack(pady=(18, 8))

        dur_var = ctk.StringVar(value="10")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(pady=4)
        ctk.CTkLabel(row, text="Duration (sec):",
                     font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED).pack(side="left")
        ctk.CTkEntry(row, textvariable=dur_var, width=80, height=28,
                     font=T.font(T.SIZE_MD, mono=True),
                     fg_color=T.BG_RAISED, text_color=T.TEXT,
                     corner_radius=T.RADIUS_SM).pack(side="left", padx=6)

        def start():
            try:
                seconds = max(1, min(120, int(dur_var.get())))
            except ValueError:
                seconds = 10
            dialog.destroy()
            self._run_screen_recording(seconds)

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=14)
        button(btns, "Start", variant="primary", width=120,
               command=start).pack(side="left", padx=4)
        button(btns, "Cancel", variant="secondary", width=120,
               command=dialog.destroy).pack(side="left", padx=4)

    def _run_screen_recording(self, duration_seconds):
        self._notify(f"Recording {duration_seconds}s — window will minimize...", "info")
        self.winfo_toplevel().iconify()
        time.sleep(0.4)  # let the window minimize before capture begins

        def worker():
            try:
                frame_dir, fps, count = record_screen(
                    duration_seconds, fps=15,
                    progress_callback=None,
                )
            except Exception as e:
                self.after(0, self._on_record_failed, str(e))
                return
            if count < 2:
                self.after(0, self._on_record_failed, "No frames captured")
                return
            output = generate_export_path(
                "record", "mp4",
                base_dir=self.export_options.get_output_folder(),
            )
            preset = self.quality_var.get()
            result = frames_to_video(str(frame_dir), fps, preset, str(output))
            self.after(0, self._on_record_done, str(result) if result else None)

        threading.Thread(target=worker, daemon=True).start()

    def _on_record_done(self, path):
        self.winfo_toplevel().deiconify()
        if not path:
            self._notify("Recording failed during encoding", "error")
            return
        self._notify(f"Recorded {os.path.basename(path)}", "success")
        self._load_path(path)

    def _on_record_failed(self, error):
        self.winfo_toplevel().deiconify()
        self._notify(f"Recording failed: {error}", "error")

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
            # Poll to reset label when playback ends naturally
            self.after(200, self._poll_play_state)

    def _poll_play_state(self):
        if not self.player._playing:
            self.play_btn.configure(text="▶  Play")
            return
        self.after(200, self._poll_play_state)

    # ------------------------------------------------------------------
    # Keyboard shortcuts bound by App
    # ------------------------------------------------------------------
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
        self._open_file()

    def keyboard_undo(self):
        """Restore the last recorded snapshot (Ctrl+Z)."""
        # Flush any pending debounced edit so the user undoes the most
        # recent "settled" state, not whatever was there 350ms ago.
        self._flush_pending_snapshot()
        snap = self._undo_stack.undo()
        if snap is None:
            self._notify("Nothing to undo", "info")
            return
        self._apply_snapshot(snap)
        self._notify("Undo", "info")

    def keyboard_redo(self):
        """Re-apply a snapshot previously popped by undo (Ctrl+Y / Ctrl+Shift+Z)."""
        self._flush_pending_snapshot()
        snap = self._undo_stack.redo()
        if snap is None:
            self._notify("Nothing to redo", "info")
            return
        self._apply_snapshot(snap)
        self._notify("Redo", "info")

    # ------------------------------------------------------------------
    # Undo/redo snapshot plumbing
    # ------------------------------------------------------------------
    def _snapshot(self):
        """Capture the slice of editor state that undo/redo should restore.

        Export preferences (quality, format, output folder, fade, etc.)
        are intentionally excluded — they're settings, not edits, and
        users don't expect Ctrl+Z to toggle them.
        """
        crop = self.player.get_crop() if hasattr(self, "player") else None
        return {
            "range":  tuple(self.range_slider.get_values()),
            "queued": list(self.range_queue.get_ranges()),
            "crop":   dict(crop) if crop else None,
            "layers": [
                dict(layer)
                for layer in self.text_layers.get_all_layers(include_empty=True)
            ],
        }

    def _request_snapshot(self, immediate=False):
        """Schedule (or immediately commit) a new undo-history entry."""
        if self._restoring or not self.video_path:
            return
        if self._snapshot_after_id is not None:
            try:
                self.after_cancel(self._snapshot_after_id)
            except Exception:
                pass
            self._snapshot_after_id = None
        if immediate:
            self._commit_snapshot()
        else:
            self._snapshot_after_id = self.after(
                self._snapshot_debounce_ms, self._commit_snapshot,
            )

    def _commit_snapshot(self):
        self._snapshot_after_id = None
        if self._restoring or not self.video_path:
            return
        self._undo_stack.record(self._snapshot())

    def _flush_pending_snapshot(self):
        if self._snapshot_after_id is None:
            return
        try:
            self.after_cancel(self._snapshot_after_id)
        except Exception:
            pass
        self._snapshot_after_id = None
        self._commit_snapshot()

    def _apply_snapshot(self, snap):
        """Restore editor state from ``snap`` without re-recording."""
        if not snap:
            return
        self._restoring = True
        try:
            # Trim range — update slider, both entries, waveform, thumbnails.
            start, end = snap["range"]
            self.range_slider.set_values(start, end)
            self.start_entry.set_value(seconds_to_hms(start))
            self.end_entry.set_value(seconds_to_hms(end))
            self._update_duration_label(start, end)
            self.waveform.set_range(start, end)
            self.thumbnail_strip.set_range(start, end)

            # Queued ranges — rebuild from scratch. Poke the queue's
            # internal list directly so we don't re-notify on each add.
            self.range_queue._ranges = [
                (float(s), float(e)) for s, e in snap.get("queued", [])
            ]
            self.range_queue._redraw_chips()
            self.range_queue._update_header()

            # Crop rect.
            self.player.set_crop(snap.get("crop"))
            settings.set("crop", snap.get("crop"))

            # Text layers — destroy existing widgets and rebuild from dicts.
            self.text_layers.clear_layers()
            for data in snap.get("layers", []):
                self.text_layers._add_layer(preset_data=data)

            # Show the frame at the new start and refresh the overlay.
            self.player.show_frame(start)
            self._update_export_enabled()
        finally:
            self._restoring = False

    # ------------------------------------------------------------------
    def _gather_ranges(self):
        """Queued ranges + current slider range = ranges to export."""
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
        image_layers = self.image_layers.get_all_layers()
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
                output_path = str(generate_export_path("trim", ext, base_dir=output_dir))

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
                        # GIF + image overlays encodes an intermediate MP4
                        # first (see ffmpeg_backend.trim_to_gif) — slower
                        # but keeps the filter-graph plumbing simple.
                        result = trim_to_gif(
                            self.video_path, start, end, preset, output_path,
                            text_layers=layers, image_layers=image_layers,
                            options=options,
                            progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                        )
                    else:
                        result = trim_to_video(
                            self.video_path, start, end, preset, output_path,
                            text_layers=layers, image_layers=image_layers,
                            options=options,
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
                    "trim_concat", ext, base_dir=output_dir,
                ))
                # Pick transition from Export Options. "cut" stays on the
                # fast lossless concat demuxer path; anything else re-
                # encodes via filter_complex xfade + acrossfade.
                transition = options.get("concat_transition", "cut")
                trans_dur = options.get("concat_transition_duration", 0.5)
                merged = concat_clips_with_transition(
                    produced, combined,
                    transition=transition, duration=trans_dur,
                )
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
            "mode":      "trim",
        })
        if hasattr(self.app, "history_tab") and self.app.history_tab.winfo_exists():
            self.app.history_tab.after(0, self.app.history_tab.refresh)
