# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The Export button and the inline progress area under it.

Exporting used to open a separate progress window. Now the Export
workspace shows it in place: the button turns into Stop while a run is
going, and the outcome (open the file, show it in its folder, share it,
or what went wrong) stays under the button until the next export or
until it's dismissed.

Each run gets an :class:`ExportJob`. The export thread talks to it with
the same calls the old window answered (``update_progress``,
``export_complete``, ``export_failed``, ``cancel_event``,
``winfo_exists``, ``after``), so the worker code barely changed. A job
that is no longer the current one is ignored, so a slow thread from an
earlier run can never overwrite what a newer run is showing.
"""

import os
import subprocess
import sys
import threading

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.share_panel import SharePanel
from videokidnapper.ui.studio.icons import icon_button
from videokidnapper.ui.theme import button
from videokidnapper.utils.progress_stats import EtaEstimator

IDLE = "idle"
RUNNING = "running"
STOPPING = "stopping"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

# States in which a run is still going; the button is Stop, not Export.
BUSY = (RUNNING, STOPPING)


class ExportJob:
    """One export run's handle on the progress area."""

    def __init__(self, panel):
        self._panel = panel
        self.cancel_event = threading.Event()

    @property
    def current(self):
        return self._panel._job is self

    def winfo_exists(self):
        if not self.current:
            return False
        try:
            return bool(self._panel.winfo_exists())
        except Exception:
            # The window is already gone (the app is closing).
            return False

    def after(self, ms, func, *args):
        return self._panel.after(ms, func, *args)

    def update_progress(self, value, status_text=None):
        if self.current:
            self._panel._show_progress(value, status_text)

    def export_complete(self, output_path):
        if self.current:
            self._panel._show_done(output_path)

    def export_failed(self, error_msg="Export failed"):
        if not self.current:
            return
        # After Stop, whatever the worker reports (a clip that "failed"
        # because ffmpeg was killed, or a plain "Cancelled") is a stop.
        if self.cancel_event.is_set():
            self._panel._show_cancelled()
        else:
            self._panel._show_failed(error_msg)


class ExportProgress(ctk.CTkFrame):
    """Export / Stop button with the run's progress and result below it."""

    def __init__(self, master, on_export, on_state_change=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_export = on_export
        self._on_state_change = on_state_change
        self._job = None
        self._eta = EtaEstimator()
        self.state = IDLE
        self.output_path = None
        self._ready = ("Export", False)

        self.button = button(self, "Export", variant="primary", height=44,
                             font=T.font(T.SIZE_LG, "bold"),
                             command=self._button_clicked)
        self.button.pack(fill="x")

        # Everything below the button: packed only while there is
        # something to show, so an idle card stays as small as before.
        self.area = ctk.CTkFrame(self, fg_color="transparent")
        head = ctk.CTkFrame(self.area, fg_color="transparent")
        head.pack(fill="x")
        self.icon_label = ctk.CTkLabel(head, text="↑", width=18,
                                       font=T.font(T.SIZE_LG, "bold"),
                                       text_color=T.ACCENT)
        self.icon_label.pack(side="left", padx=(0, 6), anchor="n")
        self.dismiss_btn = icon_button(head, "close", size=24, icon_size=10,
                                       command=self.dismiss)
        self.status_label = ctk.CTkLabel(head, text="", font=T.font(T.SIZE_MD, "bold"),
                                         text_color=T.TEXT, anchor="w", justify="left",
                                         wraplength=260)
        self.status_label.pack(side="left", fill="x", expand=True)

        self.bar = ctk.CTkProgressBar(self.area, height=8, progress_color=T.ACCENT,
                                      fg_color=T.BG_RAISED, corner_radius=4)
        self.bar.set(0)
        # Time left on the left, percent on the right. A percentage says
        # "how far", not "how long"; without the estimate a slow export
        # looks the same as a stuck one.
        self.meta = ctk.CTkFrame(self.area, fg_color="transparent")
        self.eta_label = ctk.CTkLabel(self.meta, text="", font=T.font(T.SIZE_SM),
                                      text_color=T.TEXT_DIM, anchor="w")
        self.eta_label.pack(side="left")
        self.percent_label = ctk.CTkLabel(self.meta, text="0%",
                                          font=T.font(T.SIZE_SM, mono=True),
                                          text_color=T.TEXT_DIM, anchor="e")
        self.percent_label.pack(side="right")

        self.result_row = ctk.CTkFrame(self.area, fg_color="transparent")
        small = dict(height=28, font=T.font(T.SIZE_SM, "bold"))
        button(self.result_row, "Open file", variant="secondary", width=86,
               command=self.open_file, **small).pack(side="left")
        button(self.result_row, "Show in folder", variant="secondary", width=110,
               command=self.show_in_folder, **small).pack(side="left", padx=(6, 0))
        self.share_panel = None

    # ------------------------------------------------------------------
    @property
    def running(self):
        return self.state in BUSY

    def set_ready(self, text, enabled):
        """What the button says when no export is running."""
        self._ready = (text, bool(enabled))
        if not self.running:
            self._style_button()

    def begin(self, title):
        """Start showing a new run; returns the job the worker reports to."""
        self._job = ExportJob(self)
        self._eta.reset()
        self.output_path = None
        self._drop_share_panel()
        self.icon_label.configure(text="↑", text_color=T.ACCENT)
        self.status_label.configure(text=title, text_color=T.TEXT)
        self.bar.set(0)
        self.percent_label.configure(text="0%")
        self.eta_label.configure(text="")
        self._set_state(RUNNING)
        return self._job

    def stop(self):
        """Ask the running export to stop; the worker reports when it has."""
        if self.state != RUNNING or self._job is None:
            return
        self._job.cancel_event.set()
        self.status_label.configure(text="Stopping…", text_color=T.TEXT)
        self.eta_label.configure(text="")
        self._set_state(STOPPING)

    def dismiss(self):
        """Clear a finished run's result; a running export can't be dismissed."""
        if self.running:
            return
        self._drop_share_panel()
        self._set_state(IDLE)

    def open_file(self):
        if self.output_path and os.path.exists(self.output_path):
            _open_path(self.output_path)

    def show_in_folder(self):
        if self.output_path:
            _reveal_path(self.output_path)

    # -- reports from the job (main thread) -----------------------------
    def _show_progress(self, value, status_text=None):
        if not self.running:
            return
        value = max(0.0, min(1.0, float(value)))
        self.bar.set(value)
        self.percent_label.configure(text=f"{int(value * 100)}%")
        if status_text and self.state == RUNNING:
            self.status_label.configure(text=status_text)
        # Empty while the rate is still unknown, and again if the job
        # stalls: better than a stale countdown implying progress.
        self.eta_label.configure(
            text=self._eta.update(value).eta_text if self.state == RUNNING else "")

    def _show_done(self, output_path):
        self.output_path = output_path
        name = os.path.basename(output_path) if output_path else "Unknown"
        self.icon_label.configure(text="✓", text_color=T.SUCCESS)
        self.status_label.configure(text=f"Saved {name}", text_color=T.SUCCESS)
        if output_path:
            self.share_panel = SharePanel(self.area, file_path=output_path,
                                          columns=3, wrap=280)
        self._set_state(DONE)

    def _show_failed(self, message):
        self.icon_label.configure(text="⚠", text_color=T.DANGER)
        self.status_label.configure(text=message or "Export failed", text_color=T.DANGER)
        self._set_state(FAILED)

    def _show_cancelled(self):
        self.icon_label.configure(text="■", text_color=T.TEXT_MUTED)
        self.status_label.configure(text="Export stopped.", text_color=T.TEXT_MUTED)
        self._set_state(CANCELLED)

    # -- layout -----------------------------------------------------------
    def _set_state(self, state):
        self.state = state
        for child in (self.bar, self.meta, self.result_row, self.dismiss_btn):
            child.pack_forget()
        if self.share_panel is not None:
            self.share_panel.pack_forget()
        if state == IDLE:
            self.area.pack_forget()
        else:
            self.area.pack(fill="x", pady=(12, 0))
            if state in BUSY:
                self.bar.pack(fill="x", pady=(8, 2))
                self.meta.pack(fill="x")
            else:
                self.dismiss_btn.pack(side="right", anchor="n", before=self.status_label)
            if state == DONE:
                self.result_row.pack(fill="x", pady=(6, 0))
                if self.share_panel is not None:
                    self.share_panel.pack(fill="x", pady=(8, 0))
        self._style_button()
        if self._on_state_change:
            self._on_state_change(state)

    def _style_button(self):
        if self.state == RUNNING:
            self.button.configure(text="Stop export", state="normal",
                                  **T.BUTTON_VARIANTS["danger"])
        elif self.state == STOPPING:
            self.button.configure(text="Stopping…", state="disabled",
                                  **T.BUTTON_VARIANTS["danger"])
        else:
            text, enabled = self._ready
            self.button.configure(text=text, state="normal" if enabled else "disabled",
                                  **T.BUTTON_VARIANTS["primary"])

    def _button_clicked(self):
        if self.state == RUNNING:
            self.stop()
        elif self.state != STOPPING:
            self._on_export()

    def _drop_share_panel(self):
        if self.share_panel is not None:
            self.share_panel.destroy()
            self.share_panel = None


def _open_path(path):
    if os.name == "nt":
        os.startfile(path)  # noqa: S606 - the file this export just wrote
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _reveal_path(path):
    if os.name == "nt":
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])
