import threading
import time

import customtkinter as ctk

from snapit.config import PRESETS, EXPORT_FORMATS
from snapit.core.ffmpeg_backend import frames_to_video, frames_to_gif
from snapit.core.recorder import Recorder
from snapit.ui.export_dialog import ExportDialog
from snapit.ui.region_selector import RegionSelector
from snapit.utils.file_naming import generate_export_path
from snapit.utils.time_format import seconds_to_hms


class RecordTab(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self.recorder = Recorder()
        self.region = None
        self._timer_running = False

        self._build_ui()

    def _build_ui(self):
        # Region selection section
        region_frame = ctk.CTkFrame(self, corner_radius=10)
        region_frame.pack(fill="x", padx=10, pady=(10, 5))

        region_header = ctk.CTkLabel(
            region_frame, text="Screen Region",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        region_header.pack(anchor="w", padx=15, pady=(12, 5))

        region_controls = ctk.CTkFrame(region_frame, fg_color="transparent")
        region_controls.pack(fill="x", padx=15, pady=(0, 12))

        self.select_btn = ctk.CTkButton(
            region_controls, text="  Select Region", width=160, height=36,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._select_region,
        )
        self.select_btn.pack(side="left")

        self.region_label = ctk.CTkLabel(
            region_controls, text="No region selected",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self.region_label.pack(side="left", padx=15)

        # Recording section
        rec_frame = ctk.CTkFrame(self, corner_radius=10)
        rec_frame.pack(fill="x", padx=10, pady=5)

        rec_header = ctk.CTkLabel(
            rec_frame, text="Recording",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        rec_header.pack(anchor="w", padx=15, pady=(12, 5))

        rec_controls = ctk.CTkFrame(rec_frame, fg_color="transparent")
        rec_controls.pack(fill="x", padx=15, pady=(0, 12))

        self.record_btn = ctk.CTkButton(
            rec_controls, text="  Record", width=140, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#e84a1a", hover_color="#c43e15",
            command=self._toggle_record, state="disabled",
        )
        self.record_btn.pack(side="left")

        self.timer_label = ctk.CTkLabel(
            rec_controls, text="00:00:00.000",
            font=ctk.CTkFont(family="Consolas", size=20, weight="bold"),
            text_color="#e84a1a",
        )
        self.timer_label.pack(side="left", padx=20)

        self.frames_label = ctk.CTkLabel(
            rec_controls, text="0 frames",
            font=ctk.CTkFont(size=12), text_color="gray",
        )
        self.frames_label.pack(side="left")

        # Preview area for recording status
        self.status_frame = ctk.CTkFrame(self, corner_radius=10, height=200)
        self.status_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.status_icon = ctk.CTkLabel(
            self.status_frame, text="",
            font=ctk.CTkFont(size=48),
        )
        self.status_icon.place(relx=0.5, rely=0.35, anchor="center")

        self.status_text = ctk.CTkLabel(
            self.status_frame, text="Select a screen region to start recording",
            font=ctk.CTkFont(size=14), text_color="gray",
        )
        self.status_text.place(relx=0.5, rely=0.55, anchor="center")

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

    def _select_region(self):
        self.app.withdraw()
        self.after(200, self._open_selector)

    def _open_selector(self):
        RegionSelector(self, self._on_region_selected)

    def _on_region_selected(self, region):
        self.app.deiconify()
        if region is None:
            return

        self.region = region
        x, y, w, h = region
        self.region_label.configure(
            text=f"{w} x {h}  at  ({x}, {y})",
            text_color="white",
        )
        self.record_btn.configure(state="normal")
        self.status_text.configure(text="Ready to record. Click Record to begin.")
        self.status_icon.configure(text="")

    def _toggle_record(self):
        if self.recorder.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        if not self.region:
            return

        self.export_btn.configure(state="disabled")
        self.select_btn.configure(state="disabled")
        self.record_btn.configure(text="  Stop", fg_color="#cc0000", hover_color="#990000")
        self.status_text.configure(text="Recording...", text_color="#e84a1a")
        self.status_icon.configure(text="REC", text_color="#e84a1a")

        fps = PRESETS[self.quality_var.get()]["fps"]
        self.recorder.start(self.region, fps=fps)
        self._timer_running = True
        self._update_timer()

    def _stop_recording(self):
        self._timer_running = False
        frame_dir, frame_count, elapsed = self.recorder.stop()

        self.record_btn.configure(
            text="  Record", fg_color="#e84a1a", hover_color="#c43e15",
        )
        self.select_btn.configure(state="normal")
        self.status_text.configure(
            text=f"Recorded {frame_count} frames in {elapsed:.1f}s",
            text_color="white",
        )
        self.status_icon.configure(text="", text_color="white")

        if frame_count > 0:
            self.export_btn.configure(state="normal")

    def _update_timer(self):
        if not self._timer_running:
            return
        elapsed = self.recorder.elapsed
        self.timer_label.configure(text=seconds_to_hms(elapsed))
        self.frames_label.configure(text=f"{self.recorder.frame_count} frames")
        self.after(50, self._update_timer)

    def _export(self):
        if not self.recorder.frame_dir:
            return

        preset = self.quality_var.get()
        fmt = self.format_var.get()
        ext = "gif" if fmt == "GIF" else "mp4"
        output_path = str(generate_export_path("record", ext))
        actual_fps = self.recorder.get_actual_fps()

        dialog = ExportDialog(self, title=f"Exporting {fmt}...")

        def run_export():
            def progress_cb(p):
                if dialog.winfo_exists():
                    dialog.after(0, dialog.update_progress, p, f"Encoding {fmt}...")

            try:
                if fmt == "GIF":
                    result = frames_to_gif(
                        self.recorder.frame_dir, actual_fps, preset, output_path,
                        progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                    )
                else:
                    result = frames_to_video(
                        self.recorder.frame_dir, actual_fps, preset, output_path,
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
