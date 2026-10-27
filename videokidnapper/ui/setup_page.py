# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Setup and components: the prerequisites page.

A page inside the main window, opened from the settings menu or from the
first-run landing's "Review details". It used to be a window of its own.

The default path is one click: everything missing is pre-selected, a plan
line says exactly what will be installed and how, and Install streams the
real script output (pip lines, FFmpeg download progress) into the console
on the right, so nothing happens invisibly. When it finishes, the console
shows what changed and the Relaunch button lights up. Going Back while it
runs is fine: the install carries on and the page shows how it ended.

Already-installed rows are disabled and show ✓. The elevated-terminal
route survives as an explicit "Advanced" fallback for users who prefer
their package manager (winget/brew/apt).
"""

import queue
import threading

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.studio import controls as C
from videokidnapper.ui.studio.chrome import Page
from videokidnapper.ui.theme import button
from videokidnapper.utils import prereq_check


# Rows in display order. Each entry:
#   key:      ID used to dispatch install actions
#   label:    Shown to the user
#   feature:  What feature this prereq unlocks (the "why")
#   optional: When True, unchecked by default
#   required: When True, the app is unusable without it (UI emphasizes this)
FEATURES = [
    {
        "key": "ffmpeg", "label": "FFmpeg",
        "feature": "Video trimming, GIF export, MP4 export, screen recording",
        "optional": False, "required": True,
    },
    {
        "key": "yt_dlp", "label": "yt-dlp",
        "feature": "Downloads from YouTube, Instagram, Bluesky, X, Reddit, Facebook",
        "optional": False, "required": True,
    },
    {
        "key": "customtkinter", "label": "customtkinter",
        "feature": "UI widgets (the app itself)",
        "optional": False, "required": True,
    },
    {
        "key": "PIL", "label": "Pillow",
        "feature": "Frame preview + live text-layer overlay",
        "optional": False, "required": True,
    },
    {
        "key": "mss", "label": "mss",
        "feature": "Screen recording",
        "optional": False, "required": True,
    },
    {
        "key": "tkinterdnd2", "label": "tkinterdnd2",
        "feature": "Drag-and-drop video files onto the preview",
        "optional": True, "required": False,
    },
]

# Row key -> the name prereq_check.check_all() reports it under.
_CHECK_NAMES = {
    "ffmpeg":        "FFmpeg",
    "yt_dlp":        "yt-dlp",
    "customtkinter": "customtkinter",
    "PIL":           "Pillow",
    "mss":           "mss",
    "tkinterdnd2":   "tkinterdnd2",
}

INSTALL_LABEL = "  ⬇  Install missing now"


def install_in_background(widget, keys, on_line=None, on_progress=None,
                          on_done=None, poll_ms=100):
    """Install ``keys`` on a worker thread and report back on the Tk thread.

    The worker never touches Tk. It puts each event on a queue, and an
    ``after`` loop on ``widget`` hands them to the callbacks: ``on_line(text)``
    for console output, ``on_progress(fraction, note)``, and finally
    ``on_done(installed, failures)``. Calling Tk from a worker thread only
    works while mainloop happens to be running, and can fail outright
    otherwise. The first-run landing and this page both install through
    here, so they behave the same.
    """
    events = queue.Queue()

    def worker():
        try:
            installed, failures = prereq_check.install_missing(
                keys,
                line_cb=lambda line: events.put(("line", line)),
                progress_cb=lambda frac, note: events.put(("progress", frac, note)),
            )
        except Exception as exc:
            # The installers report their own errors, but the page must
            # never be left saying "Installing..." forever.
            installed = []
            failures = [(key, f"{type(exc).__name__}: {exc}") for key in keys]
        events.put(("done", installed, failures))

    def poll():
        try:
            if not widget.winfo_exists():
                return
        except Exception:
            return  # the app is gone
        while True:
            try:
                kind, *args = events.get_nowait()
            except queue.Empty:
                break
            if kind == "done":
                if on_done:
                    on_done(*args)
                return
            callback = on_line if kind == "line" else on_progress
            if callback:
                callback(*args)
        widget.after(poll_ms, poll)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    widget.after(poll_ms, poll)
    return thread


def _card(parent):
    return ctk.CTkFrame(parent, fg_color=T.BG_SURFACE, corner_radius=T.RADIUS_LG,
                        border_width=1, border_color=T.BORDER)


class SetupPage(Page):
    def __init__(self, master, on_back, on_relaunch=None, **kwargs):
        super().__init__(master, "Setup and components", on_back, **kwargs)
        self._on_relaunch = on_relaunch
        self._rows = {}           # key -> widget refs
        self._selected = {}       # key -> BooleanVar
        self._select_all_var = ctk.BooleanVar(master=self, value=False)
        self._status = {}         # cached check_all() result
        self._installing = False
        self._last_line = None    # the console skips repeats of this

        self._build_ui()
        self._reload_status()

    @property
    def installing(self):
        return self._installing

    def refresh(self):
        """Look again at what is installed, unless an install is running.

        The app calls this each time the page is shown again, so
        something installed elsewhere in the meantime shows up.
        """
        if not self._installing:
            self._reload_status()

    def set_status(self, text, color=None):
        self.status_label.configure(text=text, text_color=color or T.TEXT_MUTED)

    # ------------------------------------------------------------------
    def _build_ui(self):
        button(self.bar_actions, "Refresh", variant="ghost", width=80, height=28,
               font=T.font(T.SIZE_SM), command=self.refresh).pack(side="right")

        # Two columns side by side, so the whole page fits the window
        # without scrolling: what is needed on the left, what is
        # happening on the right.
        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=20, pady=16)
        grid.grid_columnconfigure(0, weight=3, uniform="setup")
        grid.grid_columnconfigure(1, weight=2, uniform="setup")
        grid.grid_rowconfigure(0, weight=1)

        left = _card(grid)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))

        # The plan line: exactly what clicking Install will do.
        self.plan_label = ctk.CTkLabel(
            left, text="",
            font=T.font(T.SIZE_MD, "bold"), text_color=T.ACCENT,
            anchor="w", justify="left", wraplength=520,
        )
        self.plan_label.pack(fill="x", padx=16, pady=(14, 0))
        C.hint(left, "Everything missing is already ticked. Click Install and "
                     "watch it happen on the right.", wrap=520).pack(fill="x", padx=16)

        master_row = ctk.CTkFrame(left, fg_color="transparent")
        master_row.pack(fill="x", padx=16, pady=(8, 4))
        ctk.CTkCheckBox(
            master_row, text="Select all missing",
            variable=self._select_all_var,
            font=T.font(T.SIZE_MD, "bold"),
            text_color=T.TEXT,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.BORDER_STRONG,
            command=self._toggle_select_all,
        ).pack(side="left")

        self.rows_box = ctk.CTkFrame(left, fg_color="transparent")
        self.rows_box.pack(fill="x", padx=12, pady=(0, 12))
        for feat in FEATURES:
            self._build_row(feat)

        right = _card(grid)
        right.grid(row=0, column=1, sticky="nsew")

        C.section_label(right, "Install output").pack(fill="x", padx=16, pady=(14, 6))

        # Action buttons sit at the bottom; packed before the console so
        # the console, not the buttons, gives way on a short window.
        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.pack(side="bottom", fill="x", padx=16, pady=(4, 14))
        top_row = ctk.CTkFrame(actions, fg_color="transparent")
        top_row.pack(fill="x")
        self.install_btn = button(
            top_row, INSTALL_LABEL, variant="primary",
            width=180, command=self._install_selected,
        )
        self.install_btn.pack(side="left")
        self.relaunch_btn = button(
            top_row, "↻  Relaunch to apply", variant="success",
            width=160, command=self._relaunch,
        )
        self.relaunch_btn.configure(state="disabled")
        self.relaunch_btn.pack(side="right")
        # Fallback for users who'd rather use winget/brew/apt themselves.
        self.terminal_btn = button(
            actions, "Advanced: admin terminal", variant="ghost",
            height=28, font=T.font(T.SIZE_SM), command=self._open_admin_terminal,
        )
        self.terminal_btn.pack(anchor="w", pady=(6, 0))

        self.status_label = ctk.CTkLabel(
            right, text="", font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
            anchor="w", justify="left", wraplength=340,
        )
        self.status_label.pack(side="bottom", fill="x", padx=16, pady=(0, 4))
        self.progress = ctk.CTkProgressBar(
            right, height=8, progress_color=T.ACCENT,
            fg_color=T.BG_RAISED, corner_radius=4,
        )
        self.progress.set(0)
        self.progress.pack(side="bottom", fill="x", padx=16, pady=(6, 4))

        # The install script's real output, live. Nothing happens
        # invisibly: pip lines and the FFmpeg download progress land
        # here as they happen.
        self.console = ctk.CTkTextbox(
            right, height=120,
            font=T.font(T.SIZE_XS, mono=True),
            fg_color=T.BG_BASE, text_color=T.TEXT_MUTED,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_SM, wrap="none",
        )
        self.console.insert("end", "· Install output will appear here.\n")
        self.console.configure(state="disabled")
        self.console.pack(fill="both", expand=True, padx=16)

    def _build_row(self, feat):
        frame = ctk.CTkFrame(
            self.rows_box, fg_color=T.BG_RAISED,
            corner_radius=T.RADIUS_MD,
            border_width=1, border_color=T.BORDER,
        )
        frame.pack(fill="x", pady=2, padx=4)

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=5)

        icon = ctk.CTkLabel(
            inner, text="…", width=24,
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT_DIM,
        )
        icon.pack(side="left", padx=(0, 8))

        var = ctk.BooleanVar(master=self, value=False)
        checkbox = ctk.CTkCheckBox(
            inner, text="", variable=var,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.BORDER_STRONG, width=22,
            command=self._sync_master_checkbox,
        )
        checkbox.pack(side="right")

        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)

        title_row = ctk.CTkFrame(text_col, fg_color="transparent")
        title_row.pack(fill="x")

        label = ctk.CTkLabel(
            title_row, text=feat["label"],
            font=T.font(T.SIZE_MD, "bold"),
            text_color=T.TEXT, anchor="w", height=20,
        )
        label.pack(side="left")

        if feat["required"]:
            ctk.CTkLabel(
                title_row, text=" REQUIRED ", height=18,
                font=T.font(T.SIZE_XS, "bold"),
                text_color=T.TEXT_ON_ACCENT,
                fg_color=T.ACCENT, corner_radius=8, padx=6,
            ).pack(side="left", padx=(6, 0))
        else:
            ctk.CTkLabel(
                title_row, text=" OPTIONAL ", height=18,
                font=T.font(T.SIZE_XS, "bold"),
                text_color=T.TEXT_MUTED,
                fg_color=T.BG_HOVER, corner_radius=8, padx=6,
            ).pack(side="left", padx=(6, 0))

        version_label = ctk.CTkLabel(
            title_row, text="", height=20,
            font=T.font(T.SIZE_XS, mono=True),
            text_color=T.TEXT_DIM,
        )
        version_label.pack(side="right", padx=(0, 8))

        ctk.CTkLabel(
            text_col, text=feat["feature"], height=18,
            font=T.font(T.SIZE_SM),
            text_color=T.TEXT_MUTED, anchor="w", justify="left",
            wraplength=460,
        ).pack(fill="x")

        self._rows[feat["key"]] = {
            "frame": frame, "icon": icon, "label": label,
            "version": version_label, "checkbox": checkbox,
        }
        self._selected[feat["key"]] = var

    # ------------------------------------------------------------------
    def _console_write(self, line):
        self.console.configure(state="normal")
        self.console.insert("end", line.rstrip() + "\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def _console_line(self, line):
        # The FFmpeg download reports constantly; only echo a line when it
        # says something new, so the console stays readable.
        if line == self._last_line:
            return
        self._last_line = line
        self._console_write(line)

    def _chosen(self):
        """Ticked rows that are not installed yet, in display order."""
        return [k for k, var in self._selected.items()
                if var.get() and not self._status.get(k, {}).get("installed")]

    def _update_plan(self):
        """Reflect the current checkboxes as a what-will-happen sentence."""
        chosen = self._chosen()
        if chosen:
            self.plan_label.configure(
                text="Will install: " + prereq_check.describe_install_plan(chosen),
                text_color=T.ACCENT,
            )
        elif any(not i.get("installed") for i in self._status.values()):
            self.plan_label.configure(
                text="Nothing selected — tick what you want installed.",
                text_color=T.TEXT_DIM,
            )
        else:
            self.plan_label.configure(
                text="Everything is installed — you're good to go.",
                text_color=T.SUCCESS,
            )

    # ------------------------------------------------------------------
    def _reload_status(self):
        status = prereq_check.check_all()
        self._status = {k: status[name] for k, name in _CHECK_NAMES.items()}

        for feat in FEATURES:
            info = self._status[feat["key"]]
            row = self._rows[feat["key"]]

            if info.get("installed"):
                row["icon"].configure(text="✓", text_color=T.SUCCESS)
                row["checkbox"].configure(state="disabled")
                self._selected[feat["key"]].set(False)
                ver = info.get("version") or ""
                if ver and ver[0].isdigit():
                    row["version"].configure(text=f"v{ver}")
                elif ver or info.get("path"):
                    row["version"].configure(text="detected")
            else:
                icon_color = T.DANGER if feat["required"] else T.WARN
                row["icon"].configure(text="✗" if feat["required"] else "○",
                                      text_color=icon_color)
                row["checkbox"].configure(state="normal")
                # Missing → pre-checked, required or not: installing what's
                # absent is the default; unticking is the opt-out.
                self._selected[feat["key"]].set(True)
                row["version"].configure(text="not installed")

        self._sync_master_checkbox()
        missing = sum(1 for info in self._status.values() if not info.get("installed"))
        if missing:
            self.set_status(f"{missing} prerequisite(s) missing", T.WARN)
        else:
            self.set_status("All prerequisites installed", T.SUCCESS)

    def _sync_master_checkbox(self):
        """Reflect whether every enabled checkbox is currently checked."""
        self._update_plan()
        if not self._installing:
            self.install_btn.configure(state="normal" if self._chosen() else "disabled")
        togglable = [k for k, row in self._rows.items()
                     if str(row["checkbox"].cget("state")) == "normal"]
        if not togglable:
            self._select_all_var.set(False)
            return
        all_on = all(self._selected[k].get() for k in togglable)
        self._select_all_var.set(all_on)

    def _toggle_select_all(self):
        target = bool(self._select_all_var.get())
        for key, var in self._selected.items():
            if str(self._rows[key]["checkbox"].cget("state")) == "normal":
                var.set(target)
        self._sync_master_checkbox()

    # ------------------------------------------------------------------
    def _install_selected(self):
        if self._installing:
            return
        chosen = self._chosen()
        if not chosen:
            self.set_status("Nothing selected to install.")
            return

        self._installing = True
        self.install_btn.configure(state="disabled", text="Installing...")
        self.progress.set(0)
        self._console_write(
            "── Installing: " + prereq_check.describe_install_plan(chosen))
        if "ffmpeg" in chosen:
            self._console_write(
                f"→ FFmpeg portable → {prereq_check.default_ffmpeg_install_dir()}")
        install_in_background(
            self, chosen,
            on_line=self._console_line,
            on_progress=self._set_progress,
            on_done=self._install_finished,
        )

    def _set_progress(self, value, note):
        self.progress.set(max(0, min(1, value)))
        if note:
            self.set_status(note)

    def _install_finished(self, installed, failures):
        self._installing = False
        self._last_line = None
        self.install_btn.configure(text=INSTALL_LABEL)
        self._reload_status()

        # Console summary: exactly what changed.
        if installed:
            self._console_write(
                "── Done. Installed: " + ", ".join(installed))
        if failures:
            self._console_write(
                "── Failed: " + ", ".join(k for k, _ in failures)
                + "  (try the Advanced admin-terminal route)")
            first = failures[0]
            self.set_status(f"Failed: {first[0]} — {first[1][:80]}", T.DANGER)
            if not installed:
                self.progress.set(0)
        if installed and not failures:
            self.set_status("Install complete — hit Relaunch to start using it.",
                            T.SUCCESS)
            self.progress.set(1.0)
        if installed:
            # Anything newly installed needs a restart to be picked up:
            # make the relaunch button the obvious next step.
            self.relaunch_btn.configure(state="normal")
            self.relaunch_btn.focus_set()

    # ------------------------------------------------------------------
    def _open_admin_terminal(self):
        missing_ffmpeg = not self._status.get("ffmpeg", {}).get("installed")
        missing_pip = [
            prereq_check._pip_name_for(k)
            for k in ("yt_dlp", "customtkinter", "PIL", "mss", "tkinterdnd2")
            if self._selected[k].get() and not self._status.get(k, {}).get("installed")
        ]
        commands = prereq_check.build_install_commands(
            missing_ffmpeg=missing_ffmpeg and self._selected["ffmpeg"].get(),
            missing_pip=missing_pip,
        )
        if not commands:
            self.set_status("Nothing selected needs an elevated terminal.")
            return
        # Show exactly what the elevated terminal will run — no surprises.
        self._console_write("── Admin terminal will run:")
        for c in commands:
            self._console_write("  " + c)
        ok, msg = prereq_check.open_admin_terminal(commands)
        self.set_status(
            msg + "  When it finishes, press Refresh.",
            T.SUCCESS if ok else T.DANGER,
        )
        if not ok:
            # Fallback: stash the commands on the clipboard so the user can
            # paste them manually.
            try:
                self.clipboard_clear()
                self.clipboard_append("\n".join(commands))
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _relaunch(self):
        if self._on_relaunch:
            self._on_relaunch()
        else:
            prereq_check.relaunch()
