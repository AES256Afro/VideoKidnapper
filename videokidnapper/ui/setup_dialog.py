"""Setup / Prerequisites dialog.

Shows each prerequisite as a row: status icon, feature it enables, and a
checkbox to opt into installing it. A "Select all missing" master checkbox
toggles every unchecked row at once.

Required items are pre-checked; optional items start unchecked so the user
has to opt in. Already-installed rows are disabled and show ✓.

Install runs in a background thread; progress is piped back to the UI. On
completion the user can Relaunch or just close.
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
        self.geometry("680x560")
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
            text="Pick the features you want and install their requirements.",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(anchor="w")

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
            actions, "  Install Selected", variant="primary",
            width=170, command=self._install_selected,
        )
        self.install_btn.pack(side="left")

        self.terminal_btn = button(
            actions, "Open Admin Terminal", variant="secondary",
            width=180, command=self._open_admin_terminal,
        )
        self.terminal_btn.pack(side="left", padx=(8, 0))

        self.relaunch_btn = button(
            actions, "Relaunch", variant="success",
            width=120, command=self._relaunch,
        )
        self.relaunch_btn.configure(state="disabled")
        self.relaunch_btn.pack(side="right")

        button(
            actions, "Close", variant="ghost",
            width=100, command=self.destroy,
        ).pack(side="right", padx=(0, 6))

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
                if info.get("version"):
                    row["version"].configure(text=f"v{info['version']}")
                elif info.get("path"):
                    row["version"].configure(text="detected")
            else:
                icon_color = T.DANGER if feat["required"] else T.WARN
                row["icon"].configure(text="✗" if feat["required"] else "○",
                                      text_color=icon_color)
                row["checkbox"].configure(state="normal")
                # Required + missing → pre-check. Optional stays unchecked.
                self._selected[feat["key"]].set(feat["required"])
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
        total = len(chosen)

        def step_progress(base, frac, note):
            overall = (base + frac) / total
            if self.winfo_exists():
                self.after(0, self._set_progress, overall, note)

        for idx, key in enumerate(chosen):
            if key == "ffmpeg":
                ok, msg = prereq_check.install_ffmpeg_portable(
                    prereq_check.default_ffmpeg_install_dir(),
                    progress_cb=lambda p, note, i=idx: step_progress(i, p, note),
                )
            else:
                step_progress(idx, 0.1, f"Installing {key}...")
                ok, msg = prereq_check.pip_install(
                    prereq_check._pip_name_for(key),
                )
                step_progress(idx, 0.9, f"{key} {'OK' if ok else 'failed'}")
            if not ok:
                failures.append((key, msg))

        if self.winfo_exists():
            self.after(0, self._install_finished, failures)

    def _set_progress(self, value, note):
        self.progress.set(max(0, min(1, value)))
        if note:
            self.status_label.configure(text=note, text_color=T.TEXT_MUTED)

    def _install_finished(self, failures):
        self._installing = False
        self.install_btn.configure(state="normal", text="  Install Selected")
        self._reload_status()
        if failures:
            first = failures[0]
            self.status_label.configure(
                text=f"Failed: {first[0]} — {first[1][:80]}",
                text_color=T.DANGER,
            )
        else:
            self.status_label.configure(
                text="Install complete — relaunch to pick up changes.",
                text_color=T.SUCCESS,
            )
            self.progress.set(1.0)
            self.relaunch_btn.configure(state="normal")

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
