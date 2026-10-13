# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Batch files — export whole files with one set of settings.

Lives in the Export workspace. Complements Edit (one video, many ranges)
and Import's batch download (many links). This page targets the "I
already have 10 local files and want to recompress / reformat / resize
them all the same way" workflow — podcasts, stream exports, lectures.

Layout: a queue table on the left (each row can override the target
platform), and on the right the settings every file shares. Speed,
rotate, frame shape and color come from the same settings Edit uses,
so there's exactly one place to change them.

No per-file trim: each file is exported from 0 to its full duration.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.config import PRESETS, SUPPORTED_VIDEO_EXTENSIONS
from videokidnapper.core.ffmpeg_backend import get_video_info, trim_to_video
from videokidnapper.ui import theme as T
from videokidnapper.ui.platform_presets import PLATFORM_CHOICES, get_preset
from videokidnapper.ui.studio import controls as C
from videokidnapper.ui.studio.icons import icon_button
from videokidnapper.ui.theme import button
from videokidnapper.utils import settings
from videokidnapper.utils.threads import wait_for_thread
from videokidnapper.utils.batch import (
    PLATFORM_INHERIT,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    BatchJob,
    extend_batch_jobs,
    replan_outputs,
    summarise,
)
from videokidnapper.utils.dnd import parse_dnd_files
from videokidnapper.utils.size_estimator import human_bytes


# "Inherit" is the default per-row platform option; everything else
# comes from the shared platform-preset registry. Sorted so "Inherit"
# appears first regardless of dict ordering.
_ROW_PLATFORM_CHOICES = [PLATFORM_INHERIT] + [
    p for p in PLATFORM_CHOICES if p != "Custom"
]
BATCH_FORMATS = ["MP4", "MP3"]
QUALITY_DETAIL = {
    name: f"{p['width'] or 'Full'} wide · {p['fps']} fps" for name, p in PRESETS.items()
}
# Column widths shared by the header and every row so they line up.
_COL_PLATFORM = 156
_COL_STATUS = 190


def status_text(job: BatchJob) -> str:
    """Plain-English status for a queue row."""
    if job.status == STATUS_PROCESSING:
        return f"Exporting · {int(job.progress * 100)}%"
    if job.status == STATUS_DONE:
        try:
            size = Path(job.output_path).stat().st_size
            return f"Done · {human_bytes(size)}"
        except OSError:
            return "Done"
    if job.status == STATUS_FAILED:
        return f"Failed · {job.error[:40]}" if job.error else "Failed"
    if job.status == STATUS_CANCELLED:
        return "Stopped"
    return "Waiting"


def _discard_partial(path, since: float) -> None:
    """Remove an output this attempt wrote but did not finish.

    Only a file written since ``since``: one left from an earlier run
    (when the encode failed before ffmpeg started) is not ours to delete.
    The encoder already removes what it leaves on failure; this covers a
    failure that escapes it.
    """
    try:
        out = Path(path)
        if out.is_file() and out.stat().st_mtime >= since - 2:
            out.unlink()
    except OSError:
        pass


def _status_color(status):
    return {
        STATUS_DONE:       T.SUCCESS,
        STATUS_FAILED:     T.DANGER,
        STATUS_CANCELLED:  T.TEXT_DIM,
        STATUS_PROCESSING: T.ACCENT,
        STATUS_QUEUED:     T.TEXT_MUTED,
    }.get(status, T.TEXT_MUTED)


class BatchExportTab(ctk.CTkFrame):
    """Multi-file batch exporter."""

    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color=T.BG_BASE, corner_radius=0, **kwargs)
        self.app = app
        self._toast = None

        self._jobs: list[BatchJob] = []
        # The folder the rows' outputs were last planned in; a change of
        # "Save to" re-plans them (see _on_options_changed).
        self._planned_dir: str | None = None
        self._job_rows: list[dict] = []  # parallel to _jobs; UI handles
        self._worker: threading.Thread | None = None
        # Two ways to stop: _stop_after lets the file being exported
        # finish (the Stop button's first click), _cancel kills it too
        # (a second click, or closing the app via stop_export).
        self._cancel = threading.Event()
        self._stop_after = threading.Event()
        # Suppress persistence writes during bulk ops (initial restore,
        # _rebuild_rows from worker callbacks). _persist_jobs is cheap
        # but the JSON lock + atomic rename add up on a per-row basis.
        self._suspend_persist = False

        # Edit's settings model, so speed / rotate / frame / color have one
        # home. A bare model covers the (test-only) case of no editor.
        editor = getattr(app, "trim_tab", None)
        if editor is not None and hasattr(editor, "options"):
            self.export_options = editor.options
        else:
            from videokidnapper.ui.editor_options import EditorOptions
            self.export_options = EditorOptions(self)

        self.quality_var = ctk.StringVar(
            value=settings.get("batch_quality", settings.get("quality", "Medium")),
        )
        self.format_var = ctk.StringVar(
            value="MP3" if settings.get("batch_format") == "MP3" else "MP4",
        )

        self._build_ui()
        self.export_options.add_listener(self._refresh_inherited)
        self.export_options.add_listener(self._on_options_changed)
        self._restore_persisted_queue()

    def set_toast(self, toast):
        self._toast = toast

    def _notify(self, message: str, level: str = "info") -> None:
        if self._toast:
            self._toast.show(message, level)

    def _running(self) -> bool:
        return bool(self._worker and self._worker.is_alive())

    def export_in_progress(self) -> bool:
        return self._running()

    def stop_export(self, timeout: float = 3.0) -> None:
        """Cancel the batch and give ffmpeg a moment to be killed."""
        self._cancel.set()
        wait_for_thread(self, self._worker, timeout)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        page = ctk.CTkFrame(self, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=28, pady=22)
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, minsize=340)
        page.grid_rowconfigure(0, weight=1)

        # -- Queue --------------------------------------------------------
        queue = ctk.CTkFrame(page, fg_color=T.BG_SURFACE, corner_radius=T.RADIUS_LG,
                             border_width=1, border_color=T.BORDER)
        queue.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
        self.queue_card = queue

        head = ctk.CTkFrame(queue, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(16, 10))
        ctk.CTkLabel(head, text="Queue", font=T.font(T.SIZE_XL, "bold"),
                     text_color=T.TEXT).pack(side="left")
        self.count_label = ctk.CTkLabel(head, text="", font=T.font(T.SIZE_MD),
                                        text_color=T.TEXT_MUTED)
        self.count_label.pack(side="left", padx=(10, 0))
        button(head, "Clear", variant="ghost", width=64, height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._clear_jobs).pack(side="right")
        button(head, "Add files…", variant="secondary", width=96, height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._add_files).pack(side="right", padx=(0, 6))

        cols = ctk.CTkFrame(queue, fg_color=T.PANEL_HEADER, corner_radius=0, height=30)
        cols.pack(fill="x")
        self._grid_columns(cols)
        for col, text in ((1, "File"), (2, "Made for"), (3, "Status")):
            C.section_label(cols, text).grid(row=0, column=col, sticky="w",
                                             pady=8, padx=(0, 8))

        self.job_frame = ctk.CTkScrollableFrame(
            queue, fg_color="transparent",
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        self.job_frame.pack(fill="both", expand=True, padx=(0, 4), pady=(0, 4))
        self._build_empty_state()

        C.divider(queue).pack(fill="x")
        self.summary_label = ctk.CTkLabel(
            queue, text="", font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED, anchor="w",
        )
        self.summary_label.pack(fill="x", padx=18, pady=10)

        # Drag-drop anywhere on the queue enqueues every dropped file.
        for widget in (queue, self.job_frame):
            self._register_dnd(widget)

        # -- Settings ------------------------------------------------------
        side = ctk.CTkFrame(page, fg_color=T.BG_SURFACE, corner_radius=T.RADIUS_LG,
                            border_width=1, border_color=T.BORDER)
        side.grid(row=0, column=1, sticky="new")
        ctk.CTkLabel(side, text="Settings for every file", font=T.font(T.SIZE_XL, "bold"),
                     text_color=T.TEXT, anchor="w").pack(fill="x", padx=18, pady=(16, 4))
        C.hint(side, "A row's “Made for” choice overrides quality and frame "
                     "shape for that file.", wrap=300).pack(anchor="w", padx=18)

        C.section_label(side, "Quality").pack(fill="x", padx=18, pady=(14, 6))
        C.segmented(side, list(PRESETS.keys()), variable=self.quality_var, height=32,
                    command=self._quality_changed).pack(fill="x", padx=18)
        self.quality_hint = C.hint(side, "", wrap=300)
        self.quality_hint.pack(anchor="w", padx=18, pady=(4, 0))

        C.section_label(side, "Format").pack(fill="x", padx=18, pady=(14, 6))
        C.segmented(side, BATCH_FORMATS, variable=self.format_var, height=32,
                    command=self._format_changed).pack(fill="x", padx=18)
        C.hint(side, "MP3 keeps just the audio.", wrap=300).pack(
            anchor="w", padx=18, pady=(4, 0))

        C.section_label(side, "Save to").pack(fill="x", padx=18, pady=(14, 6))
        folder = ctk.CTkFrame(side, fg_color="transparent")
        folder.pack(fill="x", padx=18)
        C.entry(folder, textvariable=self.export_options.output_folder_var, width=180,
                mono=True).pack(side="left", fill="x", expand=True)
        button(folder, "Change", variant="secondary", width=70, height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._pick_folder).pack(side="left", padx=(6, 0))

        C.section_label(side, "Also applied, from Edit").pack(fill="x", padx=18, pady=(14, 6))
        self.inherited_label = ctk.CTkLabel(
            side, text="", font=T.font(T.SIZE_MD), text_color=T.TEXT,
            justify="left", anchor="w", wraplength=300,
        )
        self.inherited_label.pack(fill="x", padx=18)
        button(side, "Change in Edit", variant="ghost", height=28, anchor="w",
               text_color=T.ACCENT, font=T.font(T.SIZE_SM, "bold"),
               command=lambda: self._show_edit_clip()).pack(anchor="w", padx=12, pady=(2, 0))

        actions = ctk.CTkFrame(side, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(16, 18))
        self.start_btn = button(actions, "Run queue", variant="primary", height=44,
                                font=T.font(T.SIZE_LG, "bold"),
                                command=self._start_batch)
        self.start_btn.pack(fill="x")
        self.stop_btn = button(actions, "Stop after this file", variant="secondary",
                               height=34, font=T.font(T.SIZE_SM, "bold"),
                               command=self._stop_batch, state="disabled")
        self.stop_btn.pack(fill="x", pady=(8, 0))

        self._quality_changed(self.quality_var.get())
        self._refresh_inherited()

    def _grid_columns(self, frame):
        frame.grid_columnconfigure(0, minsize=34)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, minsize=_COL_PLATFORM)
        frame.grid_columnconfigure(3, minsize=_COL_STATUS)
        frame.grid_columnconfigure(4, minsize=40)

    def _build_empty_state(self):
        self.empty_label = ctk.CTkFrame(self.job_frame, fg_color="transparent")
        self.empty_label.pack(fill="both", expand=True, pady=70)
        ctk.CTkLabel(self.empty_label, text="Drop video files here",
                     font=T.font(T.SIZE_XL, "bold"), text_color=T.TEXT).pack()
        C.hint(self.empty_label, "Each file is exported start to finish with the "
                                 "settings on the right.", wrap=420).pack(pady=(4, 12))
        button(self.empty_label, "Add files…", variant="secondary", width=110,
               height=32, command=self._add_files).pack()

    def _show_edit_clip(self):
        show = getattr(self.app, "show_workspace", None)
        if callable(show):
            show("edit")
            editor = getattr(self.app, "trim_tab", None)
            if editor is not None:
                editor.inspector.show("clip")

    def _quality_changed(self, value):
        settings.set("batch_quality", value)
        self.quality_hint.configure(text=QUALITY_DETAIL.get(value, ""))

    def _format_changed(self, value):
        settings.set("batch_format", value)
        self._replan()

    def _on_options_changed(self):
        # Any Edit option fires this; only "Save to" moves the outputs.
        if self._output_dir() != self._planned_dir:
            self._replan()

    def _output_dir(self) -> str:
        return self.export_options.get_output_folder() \
            or str(Path.home() / "Downloads")

    def _extension(self) -> str:
        return "mp3" if self.format_var.get() == "MP3" else "mp4"

    def _replan(self) -> None:
        """Point unfinished rows at the current folder and format.

        A running queue keeps its plan (the worker is using it); the
        rows left over are re-planned when it finishes, and Run re-plans
        before it starts.
        """
        if self._running() or not self.winfo_exists():
            return
        self._planned_dir = self._output_dir()
        if self._jobs and replan_outputs(self._jobs, self._planned_dir, self._extension()):
            self._refresh_all_rows()
            self._persist_jobs()

    def _refresh_inherited(self):
        if not self.winfo_exists():
            return
        opts = self.export_options.get_options()
        color = self.export_options.color_summary()
        lines = [
            f"Speed {opts['speed']:g}×  ·  Rotate {opts['rotate']}°",
            f"Frame shape: {opts['aspect_preset']}",
            color.replace("Color grade on: ", "Color: ") if color else "Color: unchanged",
        ]
        self.inherited_label.configure(
            text="\n".join(lines), text_color=T.WARN if color else T.TEXT)

    def _pick_folder(self):
        var = self.export_options.output_folder_var
        folder = filedialog.askdirectory(
            title="Choose where batch exports go",
            initialdir=var.get() or str(Path.home() / "Downloads"),
        )
        if folder:
            var.set(folder)

    # ------------------------------------------------------------------
    # Job management
    # ------------------------------------------------------------------
    def _add_files(self) -> None:
        exts = " ".join(f"*{e}" for e in SUPPORTED_VIDEO_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            title="Add video files to the batch",
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
        """Wire TkinterDnD onto ``widget``. Silent no-op if DnD isn't
        available — Add files still works, so the page degrades gracefully."""
        try:
            widget.drop_target_register("DND_Files")  # type: ignore[attr-defined]
            widget.dnd_bind("<<Drop>>", self._on_dnd_event)  # type: ignore[attr-defined]
        except (AttributeError, tk.TclError):
            pass

    def _on_dnd_event(self, event) -> None:
        paths = parse_dnd_files(event.data or "", splitlist=self.tk.splitlist)
        if paths:
            self._on_files_dropped(paths)

    def _enqueue(self, paths: list[str]) -> None:
        if self._running():
            self._notify("The queue is running. Wait for it or stop it first.", "warn")
            return

        output_dir = self._output_dir()
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        self._planned_dir = output_dir

        ext = self._extension()
        previous_count = len(self._jobs)
        # extend_batch_jobs preserves per-row state (status, error,
        # platform_override) on rows that were already in the queue —
        # a re-drop of an existing file is a no-op, not a reset.
        self._jobs = extend_batch_jobs(self._jobs, paths, output_dir, ext)

        added = len(self._jobs) - previous_count
        self._rebuild_rows()
        self._persist_jobs()
        if added > 0:
            self._notify(f"Queued {added} file(s)", "success")
        else:
            self._notify("No new files queued (duplicates or unsupported types)", "warn")

    def _clear_jobs(self) -> None:
        if self._running():
            self._notify("Stop the queue first to clear it", "warn")
            return
        self._jobs = []
        self._rebuild_rows()
        self._persist_jobs()

    def _rebuild_rows(self) -> None:
        for row in self._job_rows:
            row["frame"].destroy()
        self._job_rows.clear()

        if self._jobs:
            self.empty_label.pack_forget()
            for job in self._jobs:
                self._job_rows.append(self._render_row(job))
        else:
            self.empty_label.pack(fill="both", expand=True, pady=70)

        self._update_summary()

    def _render_row(self, job: BatchJob) -> dict:
        frame = ctk.CTkFrame(self.job_frame, fg_color="transparent", corner_radius=0)
        frame.pack(fill="x")
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", pady=8)
        self._grid_columns(inner)
        C.divider(frame).pack(fill="x")

        dot = ctk.CTkLabel(inner, text="●", font=T.font(T.SIZE_SM),
                           text_color=T.TEXT_DIM, width=34)
        dot.grid(row=0, column=0)

        info_col = ctk.CTkFrame(inner, fg_color="transparent")
        info_col.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        name_lbl = ctk.CTkLabel(
            info_col, text=job.display_name, font=T.font(T.SIZE_MD, "bold"),
            text_color=T.TEXT, anchor="w",
        )
        name_lbl.pack(fill="x")
        out_lbl = ctk.CTkLabel(
            info_col, text=f"→ {Path(job.output_path).name}",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED, anchor="w",
        )
        out_lbl.pack(fill="x")

        # Per-row platform override. "Inherit" means "use the batch-wide
        # quality and frame shape"; anything else uses that preset's
        # quality + aspect for this file alone.
        platform_var = ctk.StringVar(value=job.platform_override)
        platform_menu = C.option_menu(
            inner, _ROW_PLATFORM_CHOICES, variable=platform_var,
            width=_COL_PLATFORM - 12,
            command=lambda v, j=job: self._on_row_platform_change(j, v),
        )
        platform_menu.grid(row=0, column=2, sticky="w")

        status_col = ctk.CTkFrame(inner, fg_color="transparent", width=_COL_STATUS)
        status_col.grid(row=0, column=3, sticky="ew", padx=(10, 6))
        status_lbl = ctk.CTkLabel(status_col, text="", font=T.font(T.SIZE_SM),
                                  text_color=T.TEXT_MUTED, anchor="w")
        status_lbl.pack(fill="x")
        progress = ctk.CTkProgressBar(status_col, height=5, width=150,
                                      progress_color=T.ACCENT, fg_color=T.BG_ACTIVE)
        progress.set(0)

        remove_btn = icon_button(inner, "close", size=28, icon_size=11,
                                 command=lambda j=job: self._remove_job(j))
        remove_btn.grid(row=0, column=4)

        row = {
            "frame": frame,
            "dot": dot,
            "name": name_lbl,
            "out": out_lbl,
            "status": status_lbl,
            "progress": progress,
            "platform_menu": platform_menu,
            "platform_var": platform_var,
            "remove_btn": remove_btn,
            "input_path": job.input_path,
        }
        self._apply_row_state(row, job)

        # Right-click anywhere on the row (except the interactive
        # controls) opens the context menu.
        for widget in (frame, inner, dot, info_col, name_lbl, out_lbl, status_col, status_lbl):
            widget.bind(
                "<Button-3>",
                lambda e, j=job: self._show_row_context_menu(e, j),
            )
        return row

    def _update_summary(self) -> None:
        count = len(self._jobs)
        self.count_label.configure(text=f"{count} file{'s' if count != 1 else ''}" if count else "")
        self.summary_label.configure(
            text=summarise(self._jobs) if count else
            "Right-click a row to reveal its output or reset it.")

    # ------------------------------------------------------------------
    # Per-row platform override
    # ------------------------------------------------------------------
    def _on_row_platform_change(self, job: BatchJob, value: str) -> None:
        if value != PLATFORM_INHERIT and get_preset(value) is None:
            # A stale dropdown value snuck in — ignore silently and let
            # the var revert. Defensive: the menu only offers valid keys.
            return
        job.platform_override = value
        self._persist_jobs()

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------
    def _show_row_context_menu(self, event, job: BatchJob) -> None:
        menu = tk.Menu(self, tearoff=0, bg=T.BG_SURFACE, fg=T.TEXT,
                       activebackground=T.ACCENT_SOFT, activeforeground=T.TEXT)

        output_exists = bool(job.output_path) and Path(job.output_path).exists()
        menu.add_command(
            label="Show output in folder",
            state="normal" if output_exists else "disabled",
            command=lambda: self._reveal_output(job),
        )
        menu.add_command(
            label="Open source folder",
            command=lambda: self._open_source_folder(job),
        )
        menu.add_separator()
        menu.add_command(
            label="Export this file again",
            state="disabled" if job.status == STATUS_QUEUED else "normal",
            command=lambda: self._reset_row_status(job),
        )
        menu.add_command(
            label="Remove from queue",
            state="disabled" if self._running() else "normal",
            command=lambda: self._remove_job(job),
        )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _reveal_output(self, job: BatchJob) -> None:
        if not job.output_path or not Path(job.output_path).exists():
            self._notify("No output file yet (this row hasn't finished)", "warn")
            return
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", job.output_path])
        else:
            subprocess.Popen(["xdg-open", str(Path(job.output_path).parent)])

    def _open_source_folder(self, job: BatchJob) -> None:
        parent = str(Path(job.input_path).parent)
        if not Path(parent).exists():
            self._notify("Source folder no longer exists", "warn")
            return
        if os.name == "nt":
            os.startfile(parent)  # noqa: S606 — user-chosen path
        else:
            subprocess.Popen(["xdg-open", parent])

    def _reset_row_status(self, job: BatchJob) -> None:
        if self._running():
            self._notify("Can't reset rows while the queue is running", "warn")
            return
        job.status = STATUS_QUEUED
        job.error = None
        job.progress = 0.0
        self._refresh_row(job)
        self._persist_jobs()

    def _remove_job(self, job: BatchJob) -> None:
        if self._running():
            self._notify("Can't remove rows while the queue is running", "warn")
            return
        self._jobs = [x for x in self._jobs if x.input_path != job.input_path]
        self._rebuild_rows()
        self._persist_jobs()

    # ------------------------------------------------------------------
    # Queue persistence
    # ------------------------------------------------------------------
    def _persist_jobs(self) -> None:
        if self._suspend_persist:
            return
        try:
            settings.set("batch_jobs", [job.to_dict() for job in self._jobs])
        except Exception as exc:
            # Persistence is a quality-of-life feature, never a blocker.
            # Log and move on — the user's queue remains in memory.
            if self.app and hasattr(self.app, "debug_tab"):
                try:
                    self.app.debug_tab.add_log(
                        f"Failed to persist batch queue: {exc}", "WARN",
                    )
                except Exception:
                    pass

    def _restore_persisted_queue(self) -> None:
        raw = settings.get("batch_jobs", []) or []
        if not isinstance(raw, list) or not raw:
            return
        restored: list[BatchJob] = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                restored.append(BatchJob.from_dict(entry))
            except Exception:
                # Malformed row — drop it, keep the rest.
                continue
        if not restored:
            return
        self._suspend_persist = True
        try:
            self._jobs = restored
            # Reindex + normalise in case a partial write left gaps.
            for i, job in enumerate(self._jobs):
                job.index = i
            self._rebuild_rows()
        finally:
            self._suspend_persist = False
        # A restored queue was planned for the folder of its session.
        self._replan()
        self._notify(f"Restored {len(restored)} queued file(s)", "info")

    # ------------------------------------------------------------------
    # Batch worker
    # ------------------------------------------------------------------
    def _start_batch(self) -> None:
        if self._running():
            return
        if not self._jobs:
            self._notify("Add files first", "warn")
            return
        # Reset any terminal statuses from a previous run so "Run" on a
        # partially-done queue re-runs failed + stopped rows cleanly.
        for job in self._jobs:
            if job.status in (STATUS_FAILED, STATUS_CANCELLED):
                job.status = STATUS_QUEUED
                job.error = None
                job.progress = 0.0
        # Plan for the folder and format on screen now, never over a file
        # that appeared since (or a restored queue's old folder).
        output_dir = self._output_dir()
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._notify(f"Can't use that folder: {exc}", "error")
            return
        self._planned_dir = output_dir
        replan_outputs(self._jobs, output_dir, self._extension())
        self._refresh_all_rows()
        self._persist_jobs()

        self._cancel.clear()
        self._stop_after.clear()
        self.start_btn.configure(state="disabled", text="Running…")
        self.stop_btn.configure(state="normal", text="Stop after this file")

        # Read the settings here, on the Tk thread; the worker must not.
        batch_preset = self.quality_var.get()
        batch_options = dict(self.export_options.get_options())
        batch_options["audio_only"] = self.format_var.get() == "MP3"
        self._worker = threading.Thread(
            target=self._run_batch, args=(batch_preset, batch_options), daemon=True)
        self._worker.start()

    def _stop_batch(self) -> None:
        """First click: finish the file being exported, then stop. It used
        to kill that file too, despite the label, and mark it Stopped.
        Second click: stop that file as well."""
        if not self._running():
            return
        if not self._stop_after.is_set():
            self._stop_after.set()
            self.stop_btn.configure(text="Stop now")
            self._notify("The queue will stop after this file", "warn")
        else:
            self._cancel.set()
            self.stop_btn.configure(state="disabled")
            self._notify("Stopping the queue…", "warn")

    def _run_batch(self, batch_preset: str, batch_options: dict) -> None:
        for job in self._jobs:
            if self._cancel.is_set() or self._stop_after.is_set():
                if job.status == STATUS_QUEUED:
                    job.status = STATUS_CANCELLED
                self._post(self._refresh_row, job)
                self._post(self._persist_jobs)
                continue
            if job.status == STATUS_DONE:
                continue  # already succeeded in an earlier run

            # Per-row platform override wins over the batch-wide preset.
            # Format stays batch-wide (switching it would invalidate the
            # already-displayed output_path), but quality + aspect flip
            # per row. Inherit leaves both alone.
            preset = batch_preset
            options = dict(batch_options)
            override = get_preset(job.platform_override) \
                if job.platform_override != PLATFORM_INHERIT else None
            if override:
                preset = override["quality"]
                options["aspect_preset"] = override["aspect"]

            job.status = STATUS_PROCESSING
            job.progress = 0.0
            self._post(self._refresh_row, job)
            started = time.time()

            try:
                info = get_video_info(job.input_path)
                duration = float(info.get("duration") or 0.0)
                if duration <= 0.0:
                    raise ValueError("zero-duration source")

                def progress_cb(p: float, j: BatchJob = job) -> None:
                    j.progress = max(0.0, min(1.0, p))
                    self._post(self._refresh_row, j)

                result = trim_to_video(
                    job.input_path, 0.0, duration, preset, job.output_path,
                    text_layers=[], image_layers=[], options=options,
                    progress_callback=progress_cb, cancel_event=self._cancel,
                )
                if result:
                    job.status = STATUS_DONE
                    job.progress = 1.0
                    self._post(self._record_history, job, preset,
                               bool(options.get("audio_only")))
                else:
                    # trim_to_video returns None on cancellation or
                    # silent failure; pick the status that matches.
                    job.status = STATUS_CANCELLED if self._cancel.is_set() else STATUS_FAILED
                    if job.status == STATUS_FAILED:
                        job.error = "export returned no output"
            except Exception as exc:
                job.status = STATUS_FAILED
                job.error = str(exc)
            if job.status != STATUS_DONE:
                _discard_partial(job.output_path, started)

            self._post(self._refresh_row, job)
            # Persist after each row so a crash mid-batch preserves
            # everything up to the currently-processing job.
            self._post(self._persist_jobs)

        self._post(self._finish_batch)

    def _post(self, fn, *args) -> None:
        """Run ``fn(*args)`` on the Tk thread; the one Tk call the worker
        makes. It fails once the window is closing (stop_export waits
        for the worker then), which a late worker has no reason to report.
        """
        try:
            self.after(0, fn, *args)
        except (RuntimeError, tk.TclError):
            pass

    def _record_history(self, job: BatchJob, preset: str, audio_only: bool) -> None:
        """Finished batch files show up in History next to Edit exports."""
        from datetime import datetime
        try:
            size = Path(job.output_path).stat().st_size
        except OSError:
            size = 0
        settings.add_history_entry({
            "path":       job.output_path,
            "format":     "MP3" if audio_only else "MP4",
            "preset":     preset,
            "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M"),
            "size_bytes": size,
            "mode":       "batch",
        })
        # Non-forcing: History is built on first view and loads its data
        # then, so there is nothing to refresh until it exists.
        from videokidnapper.app import TAB_HISTORY

        history = getattr(self.app, "_tab_if_built", lambda _n: None)(TAB_HISTORY)
        if history is not None and history.winfo_exists():
            history.refresh()

    def _finish_batch(self) -> None:
        self.start_btn.configure(state="normal", text="Run queue")
        self.stop_btn.configure(state="disabled", text="Stop after this file")
        self._update_summary()
        self._persist_jobs()
        # Settings changed while it ran apply to the rows still to do.
        # (_finish_batch runs before the worker thread has quite ended.)
        self.after(50, self._replan)
        done = sum(1 for j in self._jobs if j.status == STATUS_DONE)
        failed = sum(1 for j in self._jobs if j.status == STATUS_FAILED)
        if failed:
            self._notify(f"Queue finished: {done} done, {failed} failed", "warn")
        else:
            self._notify(f"Queue finished: {done} done", "success")

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
        color = _status_color(job.status)
        row["status"].configure(text=status_text(job), text_color=color)
        row["dot"].configure(text_color=color)
        if job.status == STATUS_PROCESSING:
            row["progress"].set(job.progress)
            if not row["progress"].winfo_ismapped():
                row["progress"].pack(anchor="w", pady=(4, 0))
        else:
            row["progress"].pack_forget()
        row["out"].configure(text=f"→ {Path(job.output_path).name}")

    # ------------------------------------------------------------------
    # Public hooks (for plugins / smoke tests)
    # ------------------------------------------------------------------
    def get_jobs(self) -> list[BatchJob]:
        return list(self._jobs)

    def reveal_output(self, job: BatchJob) -> None:
        """Open the output file's folder."""
        if not job.output_path:
            return
        folder = str(Path(job.output_path).parent)
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", job.output_path])
        else:
            subprocess.Popen(["xdg-open", folder])
