# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Setup / Prerequisites dialog.

The default path is one click: everything missing is pre-selected, a plan
line says exactly what will be installed and how, and Install streams the
real script output (pip lines, FFmpeg download progress) into an in-app
console so nothing happens invisibly. When it finishes, the console shows
what changed and the Relaunch button lights up.

Already-installed rows are disabled and show ✓. The elevated-terminal
route survives as an explicit "Advanced" fallback for users who prefer
their package manager (winget/brew/apt).
"""

import threading

import customtkinter as ctk

from videokidnapper.ui import theme as T
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
        "feature": "Dark-themed UI widgets (the app itself)",
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


class SetupDialog(ctk.CTkToplevel):
    def __init__(self, master, on_relaunch=None, **kwargs):
        super().__init__(master, **kwargs)
        self.title("VideoKidnapper — Setup")
        self.geometry("700x680")
        self.configure(fg_color=T.BG_BASE)
        self.transient(master.winfo_toplevel() if master else None)
        self.grab_set()

        self._on_relaunch = on_relaunch
        self._rows = {}           # key -> widget refs
        self._selected = {}       # key -> BooleanVar
        self._select_all_var = ctk.BooleanVar(value=False)
        self._status = {}         # cached check_all() result
        self._installing = False

        self._build_ui()
        self._reload_status()

    # ------------------------------------------------------------------
    def _build_ui(self):
        card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            header, text="Prerequisites",
            font=T.font(T.SIZE_XL, "bold"), text_color=T.TEXT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Everything missing is already selected — click Install and "
                 "watch it happen in the console below.",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(anchor="w")

        # The plan line: exactly what clicking Install will do.
        self.plan_label = ctk.CTkLabel(
            header, text="",
            font=T.font(T.SIZE_SM, "bold"), text_color=T.ACCENT,
            anchor="w", justify="left", wraplength=620,
        )
        self.plan_label.pack(anchor="w", pady=(4, 0))

        # "Select all missing" master checkbox
        master_row = ctk.CTkFrame(card, fg_color="transparent")
        master_row.pack(fill="x", padx=16, pady=(10, 2))

        ctk.CTkCheckBox(
            master_row, text="Select all missing",
            variable=self._select_all_var,
            font=T.font(T.SIZE_MD, "bold"),
            text_color=T.TEXT,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.BORDER_STRONG,
            command=self._toggle_select_all,
        ).pack(side="left")

        ctk.CTkButton(
            master_row, text="Refresh",
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_MUTED, font=T.font(T.SIZE_SM),
            corner_radius=T.RADIUS_SM, width=80, height=26,
            command=self._reload_status,
        ).pack(side="right")

        # Feature rows live in a scrollable area so we can grow later.
        self.body = ctk.CTkScrollableFrame(
            card, fg_color="transparent",
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        self.body.pack(fill="both", expand=True, padx=12, pady=(6, 6))

        for feat in FEATURES:
            self._build_row(feat)

        # In-app console: the install script's real output, live. Nothing
        # happens invisibly — pip lines and the FFmpeg download progress
        # land here as they happen.
        self.console = ctk.CTkTextbox(
            card, height=150,
            font=T.font(T.SIZE_XS, mono=True),
            fg_color="#0A0D12", text_color=T.TEXT_MUTED,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_SM, wrap="none",
        )
        self.console.insert("end", "· Install output will appear here.\n")
        self.console.configure(state="disabled")
        self.console.pack(fill="x", padx=16, pady=(6, 2))

        # Progress + status footer
        self.progress = ctk.CTkProgressBar(
            card, height=8, progress_color=T.ACCENT,
            fg_color=T.BG_RAISED, corner_radius=4,
        )
        self.progress.set(0)
        self.progress.pack(fill="x", padx=16, pady=(6, 2))

        self.status_label = ctk.CTkLabel(
            card, text="",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM, anchor="w",
        )
        self.status_label.pack(fill="x", padx=16, pady=(0, 6))

        # Action buttons
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(4, 14))

        self.install_btn = button(
            actions, "  ⬇  Install missing now", variant="primary",
            width=190, command=self._install_selected,
        )
        self.install_btn.pack(side="left")

        # Fallback for users who'd rather use winget/brew/apt themselves.
        self.terminal_btn = button(
            actions, "Advanced: admin terminal", variant="ghost",
            width=180, command=self._open_admin_terminal,
        )
        self.terminal_btn.pack(side="left", padx=(8, 0))

        self.relaunch_btn = button(
            actions, "↻  Relaunch to apply", variant="success",
            width=170, command=self._relaunch,
        )
        self.relaunch_btn.configure(state="disabled")
        self.relaunch_btn.pack(side="right")

        button(
            actions, "Close", variant="ghost",
            width=100, command=self.destroy,
        ).pack(side="right", padx=(0, 6))

    # ------------------------------------------------------------------
    def _console_write(self, line):
        self.console.configure(state="normal")
        self.console.insert("end", line.rstrip() + "\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def _console_write_threadsafe(self, line):
        if self.winfo_exists():
            self.after(0, self._console_write, line)

    def _update_plan(self):
        """Reflect the current checkboxes as a what-will-happen sentence."""
        chosen = [k for k, var in self._selected.items()
                  if var.get() and not self._status.get(k, {}).get("installed")]
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

    def _build_row(self, feat):
        frame = ctk.CTkFrame(
            self.body, fg_color=T.BG_RAISED,
            corner_radius=T.RADIUS_MD,
            border_width=1, border_color=T.BORDER,
        )
        frame.pack(fill="x", pady=4, padx=2)

        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)

        icon = ctk.CTkLabel(
            inner, text="…", width=24,
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT_DIM,
        )
        icon.pack(side="left", padx=(0, 8))

        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True)

        title_row = ctk.CTkFrame(text_col, fg_color="transparent")
        title_row.pack(fill="x")

        label = ctk.CTkLabel(
            title_row, text=feat["label"],
            font=T.font(T.SIZE_MD, "bold"),
            text_color=T.TEXT, anchor="w",
        )
        label.pack(side="left")

        if feat["required"]:
            ctk.CTkLabel(
                title_row, text=" REQUIRED ",
                font=T.font(T.SIZE_XS, "bold"),
                text_color=T.TEXT_ON_ACCENT,
                fg_color=T.ACCENT, corner_radius=8, padx=6,
            ).pack(side="left", padx=(6, 0))
        else:
            ctk.CTkLabel(
                title_row, text=" OPTIONAL ",
                font=T.font(T.SIZE_XS, "bold"),
                text_color=T.TEXT_MUTED,
                fg_color=T.BG_HOVER, corner_radius=8, padx=6,
            ).pack(side="left", padx=(6, 0))

        version_label = ctk.CTkLabel(
            title_row, text="",
            font=T.font(T.SIZE_XS, mono=True),
            text_color=T.TEXT_DIM,
        )
        version_label.pack(side="right")

        ctk.CTkLabel(
            text_col, text=feat["feature"],
            font=T.font(T.SIZE_SM),
            text_color=T.TEXT_MUTED, anchor="w", justify="left",
            wraplength=440,
        ).pack(fill="x", pady=(2, 0))

        var = ctk.BooleanVar(value=False)
        checkbox = ctk.CTkCheckBox(
            inner, text="", variable=var,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.BORDER_STRONG, width=22,
            command=self._sync_master_checkbox,
        )
        checkbox.pack(side="right")

        self._rows[feat["key"]] = {
            "frame": frame, "icon": icon, "label": label,
            "version": version_label, "checkbox": checkbox,
        }
        self._selected[feat["key"]] = var

    # ------------------------------------------------------------------
    def _reload_status(self):
        mapping = {
            "ffmpeg":        "FFmpeg",
            "yt_dlp":        "yt-dlp",
            "customtkinter": "customtkinter",
            "PIL":           "Pillow",
            "mss":           "mss",
            "tkinterdnd2":   "tkinterdnd2",
        }
        status = prereq_check.check_all()
        self._status = {k: status[display] for k, display in mapping.items()}

        for feat in FEATURES:
            info = self._status[feat["key"]]
            row = self._rows[feat["key"]]
            installed = info.get("installed")

            if installed:
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
            self.status_label.configure(
                text=f"{missing} prerequisite(s) missing",
                text_color=T.WARN,
            )
        else:
            self.status_label.configure(
                text="All prerequisites installed",
                text_color=T.SUCCESS,
            )

    def _sync_master_checkbox(self):
        """Reflect whether every enabled checkbox is currently checked."""
        self._update_plan()
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

    # ------------------------------------------------------------------
    def _install_selected(self):
        if self._installing:
            return
        chosen = [k for k, var in self._selected.items()
                  if var.get() and not self._status.get(k, {}).get("installed")]
        if not chosen:
            self.status_label.configure(
                text="Nothing selected to install.", text_color=T.TEXT_MUTED,
            )
            return

        self._installing = True
        self.install_btn.configure(state="disabled", text="Installing...")
        self.progress.set(0)

        threading.Thread(target=self._run_install, args=(chosen,), daemon=True).start()

    def _run_install(self, chosen):
        failures = []
        installed = []
        total = len(chosen)

        def step_progress(base, frac, note):
            overall = (base + frac) / total
            if self.winfo_exists():
                self.after(0, self._set_progress, overall, note)

        self._console_write_threadsafe(
            "── Installing: " + prereq_check.describe_install_plan(chosen))

        for idx, key in enumerate(chosen):
            if key == "ffmpeg":
                dest = prereq_check.default_ffmpeg_install_dir()
                self._console_write_threadsafe(f"→ FFmpeg portable → {dest}")

                # The download hook fires constantly; only echo distinct
                # notes to the console so it stays readable.
                last_note = [""]

                def ff_progress(p, note, i=idx):
                    step_progress(i, p, note)
                    if note != last_note[0]:
                        last_note[0] = note
                        self._console_write_threadsafe("  " + note)

                ok, msg = prereq_check.install_ffmpeg_portable(
                    dest, progress_cb=ff_progress,
                )
            else:
                pkg = prereq_check._pip_name_for(key)
                step_progress(idx, 0.1, f"Installing {pkg}...")
                ok, msg = prereq_check.pip_install_streaming(
                    pkg, line_cb=self._console_write_threadsafe,
                )
                step_progress(idx, 0.9, f"{pkg} {'OK' if ok else 'failed'}")

            if ok:
                installed.append(key)
                self._console_write_threadsafe(f"✓ {key} installed")
            else:
                failures.append((key, msg))
                self._console_write_threadsafe(f"✗ {key} FAILED — {msg}")

        if self.winfo_exists():
            self.after(0, self._install_finished, failures, installed)

    def _set_progress(self, value, note):
        self.progress.set(max(0, min(1, value)))
        if note:
            self.status_label.configure(text=note, text_color=T.TEXT_MUTED)

    def _install_finished(self, failures, installed):
        self._installing = False
        self.install_btn.configure(state="normal", text="  ⬇  Install missing now")
        self._reload_status()

        # Console summary: exactly what changed.
        if installed:
            self._console_write(
                "── Done. Installed: " + ", ".join(installed))
        if failures:
            self._console_write(
                "── Failed: " + ", ".join(k for k, _ in failures)
                + "  (try the Advanced admin-terminal route)")

        if failures:
            first = failures[0]
            self.status_label.configure(
                text=f"Failed: {first[0]} — {first[1][:80]}",
                text_color=T.DANGER,
            )
        if installed and not failures:
            self.status_label.configure(
                text="Install complete — hit Relaunch to start using it.",
                text_color=T.SUCCESS,
            )
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
            self.status_label.configure(
                text="Nothing selected needs an elevated terminal.",
                text_color=T.TEXT_MUTED,
            )
            return
        # Show exactly what the elevated terminal will run — no surprises.
        self._console_write("── Admin terminal will run:")
        for c in commands:
            self._console_write("  " + c)
        ok, msg = prereq_check.open_admin_terminal(commands)
        color = T.SUCCESS if ok else T.DANGER
        self.status_label.configure(
            text=msg + "  (reopen Setup and hit Refresh when done.)",
            text_color=color,
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
