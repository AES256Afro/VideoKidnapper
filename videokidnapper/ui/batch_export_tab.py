# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Batch Export tab — apply shared export settings to many files at once.

Complements the Trim tab (one video, many ranges) and the URL tab's
Batch Download panel (download many URLs). This tab targets the "I
already have 10 local files and want to recompress / reformat / resize
them all with the same settings" workflow — podcasts, stream exports,
lecture recordings, etc.

No per-file trim: each file is exported from 0 to its full duration.
Users wanting per-file trim should stay in the Trim tab.
"""

from __future__ import annotations

import os
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.config import PRESETS, SUPPORTED_VIDEO_EXTENSIONS
from videokidnapper.core.ffmpeg_backend import get_video_info, trim_to_video
from videokidnapper.ui import theme as T
from videokidnapper.ui.export_options import ExportOptionsPanel
from videokidnapper.ui.theme import button
from videokidnapper.utils import settings
from videokidnapper.utils.batch import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    BatchJob,
    plan_batch_jobs,
    summarise,
)
from videokidnapper.utils.dnd import parse_dnd_files


class BatchExportTab(ctk.CTkScrollableFrame):
    """Multi-file batch exporter."""

    def __init__(self, master, app, **kwargs):
        super().__init__(
            master,
            fg_color="transparent",
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
            **kwargs,
        )
        self.app = app
        self._toast = None

        self._jobs: list[BatchJob] = []
        self._job_rows: list[dict] = []  # parallel to _jobs; UI handles
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()

        self._build_ui()

    def set_toast(self, toast):
        self._toast = toast

    def _notify(self, message: str, level: str = "info") -> None:
        if self._toast:
            self._toast.show(message, level)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # --- Source card: add files -----------------------------------
        src_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        src_card.pack(fill="x", padx=12, pady=(12, 6))

        src_inner = ctk.CTkFrame(src_card, fg_color="transparent")
        src_inner.pack(fill="x", padx=14, pady=12)

        button(
            src_inner, "  ⇪  Add Files", variant="primary",
            width=140, command=self._add_files,
        ).pack(side="left")

        button(
            src_inner, "Clear", variant="ghost",
            width=90, height=36, command=self._clear_jobs,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            src_inner,
            text="Drop video files here to queue them · each is exported with the shared settings below",
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_DIM,
        ).pack(side="left", padx=15)

        # Drag-drop onto the source card enqueues every dropped file.
        self._register_dnd(src_card)

        # --- Quality/format + shared export options -------------------
        fmt_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        fmt_card.pack(fill="x", padx=12, pady=6)

        fmt_inner = ctk.CTkFrame(fmt_card, fg_color="transparent")
        fmt_inner.pack(fill="x", padx=14, pady=12)

        ctk.CTkLabel(
            fmt_inner, text="Quality",
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))
        self.quality_var = ctk.StringVar(
            value=settings.get("batch_quality", settings.get("quality", "Medium")),
        )
        self.quality_menu = ctk.CTkOptionMenu(
            fmt_inner, variable=self.quality_var,
            values=list(PRESETS.keys()), width=120,
            fg_color=T.BG_RAISED, button_color=T.BG_HOVER,
            button_hover_color=T.BG_ACTIVE, text_color=T.TEXT,
            dropdown_fg_color=T.BG_RAISED, dropdown_text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
            command=lambda v: settings.set("batch_quality", v),
        )
        self.quality_menu.pack(side="left", padx=(0, 18))

        # Format is fixed to MP4 for batch — GIF batch is niche and the
        # existing GIF pipeline doesn't benefit from per-file scaling.
        # Audio-only is handled via the Export Options "Audio only (MP3)"
        # toggle, which flips the extension at run time.
        ctk.CTkLabel(
            fmt_inner, text="Format",
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            fmt_inner, text="MP4   (audio-only honored from Export Options)",
            font=T.font(T.SIZE_MD), text_color=T.TEXT,
        ).pack(side="left")

        # Reuse the existing ExportOptionsPanel — writes to the same
        # settings keys the Trim tab does, so changes propagate both ways.
        self.export_options = ExportOptionsPanel(self)
        self.export_options.pack(fill="x", padx=12, pady=6)

        # --- Controls card --------------------------------------------
        ctrl_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        ctrl_card.pack(fill="x", padx=12, pady=6)

        ctrl_inner = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl_inner.pack(fill="x", padx=14, pady=12)

        self.start_btn = button(
            ctrl_inner, "  ▶  Start Batch", variant="primary",
            width=170, command=self._start_batch,
        )
        self.start_btn.pack(side="left")

        self.stop_btn = button(
            ctrl_inner, "Stop", variant="danger",
            width=90, height=36, command=self._stop_batch, state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(8, 0))

        self.summary_label = ctk.CTkLabel(
            ctrl_inner, text="empty",
            font=T.font(T.SIZE_SM, mono=True),
            text_color=T.TEXT_DIM,
        )
        self.summary_label.pack(side="right")

        # --- Job list card --------------------------------------------
        list_card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        list_card.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        ctk.CTkLabel(
            list_card, text="Queue",
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 2))

        self.job_frame = ctk.CTkScrollableFrame(
            list_card, fg_color="transparent", height=260,
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        self.job_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.empty_label = ctk.CTkLabel(
            self.job_frame,
            text="No files queued — click Add Files or drop videos here.",
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_DIM,
        )
        self.empty_label.pack(pady=40)

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------
    def _add_files(self) -> None:
        exts = " ".join(f"*{e}" for e in SUPPORTED_VIDEO_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            title="Add video files to batch",
            filetypes=[("Video files", exts), ("All files", "*.*")],
        )
        if paths:
            self._enqueue(list(paths))

    def _on_files_dropped(self, paths) -> None:
        """DnD callback: accept one path or a list of paths."""
        if not paths:
            return
        if isinstance(paths, str):
            paths = [paths]
        self._enqueue(paths)

    def _register_dnd(self, widget) -> None:
        """Wire TkinterDnD onto ``widget``. Silent no-op if DnD isn't available —
        the Add Files button still works, so the tab degrades gracefully."""
        try:
            widget.drop_target_register("DND_Files")  # type: ignore[attr-defined]
            widget.dnd_bind("<<Drop>>", self._on_dnd_event)  # type: ignore[attr-defined]
        except (AttributeError, tk.TclError):
            pass

    def _on_dnd_event(self, event) -> None:
        paths = parse_dnd_files(event.data or "")
        if paths:
            self._on_files_dropped(paths)

    def _enqueue(self, paths: list[str]) -> None:
        if self._worker and self._worker.is_alive():
            self._notify("Batch is running — wait for it to finish or Stop it first", "warn")
            return

        # Seed the planner with our existing input paths so output-path
        # collisions across adds get a unique numeric suffix.
        output_dir = self.export_options.get_output_folder() \
            or str(Path.home() / "Downloads")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        existing_inputs = {job.input_path for job in self._jobs}
        combined_inputs = [j.input_path for j in self._jobs] + [
            p for p in paths if p not in existing_inputs
        ]

        options = self.export_options.get_options()
        ext = "mp3" if options.get("audio_only") else "mp4"
        new_plan = plan_batch_jobs(combined_inputs, output_dir, ext)

        added = len(new_plan) - len(self._jobs)
        self._jobs = new_plan
        self._rebuild_rows()
        if added > 0:
            self._notify(f"Queued {added} file(s)", "success")
        else:
            self._notify("No new files queued (duplicates or unsupported types)", "warn")

    def _clear_jobs(self) -> None:
        if self._worker and self._worker.is_alive():
            self._notify("Batch is running — Stop it first to clear", "warn")
            return
        self._jobs = []
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        for row in self._job_rows:
            row["frame"].destroy()
        self._job_rows.clear()

        if hasattr(self, "empty_label") and self.empty_label.winfo_exists():
            self.empty_label.destroy()

        if not self._jobs:
            self.empty_label = ctk.CTkLabel(
                self.job_frame,
                text="No files queued — click Add Files or drop videos here.",
                font=T.font(T.SIZE_MD),
                text_color=T.TEXT_DIM,
            )
            self.empty_label.pack(pady=40)
        else:
            for job in self._jobs:
                self._job_rows.append(self._render_row(job))

        self._update_summary()

    def _render_row(self, job: BatchJob) -> dict:
        frame = ctk.CTkFrame(
            self.job_frame,
            fg_color=T.BG_RAISED,
            corner_radius=T.RADIUS_SM,
        )
        frame.pack(fill="x", pady=2)

        dot = ctk.CTkLabel(
            frame, text="●",
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT_DIM, width=24,
        )
        dot.pack(side="left", padx=(8, 6))

        info_col = ctk.CTkFrame(frame, fg_color="transparent")
        info_col.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=6)

        name_lbl = ctk.CTkLabel(
            info_col, text=job.display_name,
            font=T.font(T.SIZE_MD, "bold", mono=True),
            text_color=T.TEXT, anchor="w",
        )
        name_lbl.pack(fill="x")

        out_lbl = ctk.CTkLabel(
            info_col, text=f"→ {Path(job.output_path).name}",
            font=T.font(T.SIZE_XS, mono=True),
            text_color=T.TEXT_DIM, anchor="w",
        )
        out_lbl.pack(fill="x")

        status_lbl = ctk.CTkLabel(
            frame, text=job.status,
            font=T.font(T.SIZE_SM),
            text_color=T.TEXT_DIM, width=100,
        )
        status_lbl.pack(side="left", padx=6)

        def remove(j=job):
            if self._worker and self._worker.is_alive():
                self._notify("Cannot remove rows while batch is running", "warn")
                return
            self._jobs = [x for x in self._jobs if x.input_path != j.input_path]
            self._rebuild_rows()

        remove_btn = ctk.CTkButton(
            frame, text="✕",
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_MUTED, font=T.font(T.SIZE_MD, "bold"),
            corner_radius=T.RADIUS_SM,
            width=30, height=28,
            command=remove,
        )
        remove_btn.pack(side="right", padx=(0, 6))

        return {
            "frame": frame,
            "dot": dot,
            "name": name_lbl,
            "out": out_lbl,
            "status": status_lbl,
            "remove_btn": remove_btn,
            "input_path": job.input_path,
        }

    def _update_summary(self) -> None:
        self.summary_label.configure(text=summarise(self._jobs))

    # ------------------------------------------------------------------
    # Batch worker
    # ------------------------------------------------------------------
    def _start_batch(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        if not self._jobs:
            self._notify("Add files first", "warn")
            return
        # Reset any terminal statuses from a previous run so "Start" on a
        # partially-done queue re-runs failed + queued rows cleanly.
        for job in self._jobs:
            if job.status in (STATUS_FAILED, STATUS_CANCELLED):
                job.status = STATUS_QUEUED
                job.error = None
                job.progress = 0.0
        self._refresh_all_rows()

        self._cancel.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        self._worker = threading.Thread(target=self._run_batch, daemon=True)
        self._worker.start()

    def _stop_batch(self) -> None:
        if self._worker and self._worker.is_alive():
            self._cancel.set()
            self._notify("Cancelling remaining jobs...", "warn")

    def _run_batch(self) -> None:
        preset = self.quality_var.get()
        options = self.export_options.get_options()

        for job in self._jobs:
            if self._cancel.is_set():
                if job.status == STATUS_QUEUED:
                    job.status = STATUS_CANCELLED
                self.after(0, self._refresh_row, job)
                continue
            if job.status == STATUS_DONE:
                continue  # already succeeded in an earlier run

            job.status = STATUS_PROCESSING
            job.progress = 0.0
            self.after(0, self._refresh_row, job)

            try:
                info = get_video_info(job.input_path)
                duration = float(info.get("duration") or 0.0)
                if duration <= 0.0:
                    raise ValueError("zero-duration source")

                def progress_cb(p: float, j: BatchJob = job) -> None:
                    j.progress = max(0.0, min(1.0, p))
                    self.after(0, self._refresh_row, j)

                result = trim_to_video(
                    job.input_path, 0.0, duration, preset, job.output_path,
                    text_layers=[], image_layers=[], options=options,
                    progress_callback=progress_cb, cancel_event=self._cancel,
                )
                if result:
                    job.status = STATUS_DONE
                    job.progress = 1.0
                else:
                    # trim_to_video returns None on cancellation or
                    # silent failure; pick the status that matches.
                    job.status = STATUS_CANCELLED if self._cancel.is_set() else STATUS_FAILED
                    if job.status == STATUS_FAILED:
                        job.error = "export returned no output"
            except Exception as exc:
                job.status = STATUS_FAILED
                job.error = str(exc)

            self.after(0, self._refresh_row, job)

        self.after(0, self._finish_batch)

    def _finish_batch(self) -> None:
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self._update_summary()
        done = sum(1 for j in self._jobs if j.status == STATUS_DONE)
        failed = sum(1 for j in self._jobs if j.status == STATUS_FAILED)
        if failed:
            self._notify(
                f"Batch finished: {done} done, {failed} failed", "warn",
            )
        else:
            self._notify(f"Batch finished: {done} done", "success")

    # ------------------------------------------------------------------
    def _refresh_all_rows(self) -> None:
        for job, row in zip(self._jobs, self._job_rows):
            self._apply_row_state(row, job)
        self._update_summary()

    def _refresh_row(self, job: BatchJob) -> None:
        for row in self._job_rows:
            if row["input_path"] == job.input_path:
                self._apply_row_state(row, job)
                break
        self._update_summary()

    def _apply_row_state(self, row: dict, job: BatchJob) -> None:
        status_text = job.status
        if job.status == STATUS_PROCESSING:
            status_text = f"{int(job.progress * 100)}%"
        elif job.status == STATUS_FAILED and job.error:
            status_text = f"✕ {job.error[:32]}"
        elif job.status == STATUS_DONE:
            status_text = "✓ done"
        color = {
            STATUS_DONE:       T.SUCCESS,
            STATUS_FAILED:     T.DANGER,
            STATUS_CANCELLED:  T.TEXT_DIM,
            STATUS_PROCESSING: T.ACCENT,
            STATUS_QUEUED:     T.TEXT_DIM,
        }.get(job.status, T.TEXT_DIM)
        row["status"].configure(text=status_text, text_color=color)
        row["dot"].configure(text_color=color)

    # ------------------------------------------------------------------
    # Public hooks (for future plugin use / smoke tests)
    # ------------------------------------------------------------------
    def get_jobs(self) -> list[BatchJob]:
        return list(self._jobs)

    def reveal_output(self, job: BatchJob) -> None:
        """Open the output file's folder. Wired from the row's right-click
        menu in a follow-up; exposed now so tests can validate the path."""
        if not job.output_path:
            return
        folder = str(Path(job.output_path).parent)
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", job.output_path])
        else:
            subprocess.Popen(["xdg-open", folder])
