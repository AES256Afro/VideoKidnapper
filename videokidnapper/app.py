# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import sys
import traceback
from pathlib import Path

import customtkinter as ctk

from videokidnapper.config import APP_NAME, APP_VERSION, WINDOW_SIZE, MIN_WINDOW_SIZE
from videokidnapper.ui import theme as T
from videokidnapper.ui.widgets import Toast
from videokidnapper.utils import project_files, settings
from videokidnapper.utils.dnd import enable_dnd_for
from videokidnapper.utils.ffmpeg_check import check_ffmpeg
from videokidnapper.utils.github_update import check_async
from videokidnapper.utils.urltools import looks_like_media_url

# Tab titles in one place — position in _build_tabs decides order, and
# CTkTabview selects the first tab added. One studio tab does it all:
# open a file, record the screen, or kidnap from a link — same trim /
# caption / export pipeline either way.
TAB_STUDIO  = "  ⬇  Kidnap & Trim  "
TAB_BATCH   = "  ⎆  Batch Export  "
TAB_HISTORY = "  ⌛  History  "
TAB_DEBUG   = "  ⚙  Debug  "


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._is_first_run = settings.is_first_run()
        T.configure_global()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)
        self.configure(fg_color=T.BG_BASE)
        self._set_window_icon()
        self.protocol("WM_DELETE_WINDOW", self._request_close)

        # Turn DnD on BEFORE any widget is created so their
        # drop_target_register() calls succeed during __init__.
        self.dnd_enabled = enable_dnd_for(self)

        self.ffmpeg_path, self.ffprobe_path = check_ffmpeg()

        if not self.ffmpeg_path:
            # Missing prereqs → auto-install and continue, no dead-end.
            self._show_setup_landing()
            return

        self._start_main_ui()

    def _start_main_ui(self):
        """Build the real app UI. Called on boot when prereqs are present,
        or from the landing after a successful auto-install."""
        self.plugins = []   # [DiscoveredPlugin] — populated by _load_plugins

        self._build_ui()
        self._bind_keyboard_shortcuts()
        self._install_exception_handler()
        self._load_plugins()
        self._maybe_check_for_update()
        if not self._maybe_offer_recovery():
            self._maybe_show_onboarding()

    def _maybe_offer_recovery(self):
        recovery_file = project_files.autosave_path()
        if not recovery_file.is_file():
            return False

        def show():
            if not self.winfo_exists():
                return
            from videokidnapper.ui.project_dialog import RecoveryDialog
            self._recovery_dialog = RecoveryDialog(self, self.trim_tab)

        self.after(250, show)
        return True

    def _maybe_show_onboarding(self):
        if not self._is_first_run or settings.get("onboarding_complete", False):
            return

        def show():
            if not self.winfo_exists():
                return
            from videokidnapper.ui.onboarding_dialog import OnboardingDialog
            self._onboarding_dialog = OnboardingDialog(self, self.trim_tab)

        self.after(350, show)

    # ------------------------------------------------------------------
    def _set_window_icon(self):
        """Apply the packaged robber-head icon to the window / taskbar.

        Never fatal: headless test environments, exotic Tk builds, or a
        stripped install simply keep the default icon. On Windows the
        .ico path wins (crisp multi-size taskbar rendering); iconphoto
        covers Linux/macOS. CustomTkinter re-asserts its own default
        icon shortly after startup on Windows, so we re-apply ours a
        beat later.
        """
        assets = Path(__file__).resolve().parent / "assets"
        ico, png = assets / "icon.ico", assets / "icon.png"
        try:
            if sys.platform == "win32" and ico.exists():
                self.iconbitmap(str(ico))
                self.after(300, lambda: self.iconbitmap(str(ico)))
            if png.exists():
                import tkinter as tk

                # Keep a reference — Tk drops the icon if the PhotoImage
                # is garbage-collected.
                self._icon_image = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_image)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _build_ui(self):
        self._build_header()
        self._build_tabs()
        self._build_statusbar()

        for tab in (self.trim_tab, self.batch_export_tab):
            if hasattr(tab, "set_toast"):
                tab.set_toast(self.status_bar)

    # ------------------------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(
            self, height=60, corner_radius=0, fg_color=T.BG_SURFACE,
        )
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        accent = ctk.CTkFrame(header, width=4, fg_color=T.ACCENT, corner_radius=0)
        accent.pack(side="left", fill="y")

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(side="left", fill="both", expand=True, padx=16, pady=6)

        title_row = ctk.CTkFrame(inner, fg_color="transparent")
        title_row.pack(anchor="w")

        logo = ctk.CTkLabel(
            title_row, text="▶",
            font=T.font(T.SIZE_HERO, "bold"),
            text_color=T.ACCENT,
        )
        logo.pack(side="left", padx=(0, 8))

        title = ctk.CTkLabel(
            title_row, text=APP_NAME,
            font=T.font(T.SIZE_HERO, "bold"),
            text_color=T.TEXT,
        )
        title.pack(side="left")

        version_chip = ctk.CTkLabel(
            title_row, text=f" v{APP_VERSION} ",
            font=T.font(T.SIZE_XS, "bold"),
            text_color=T.TEXT_MUTED,
            fg_color=T.BG_RAISED,
            corner_radius=10,
            padx=6,
        )
        version_chip.pack(side="left", padx=(10, 0), pady=(6, 0))

        subtitle = ctk.CTkLabel(
            inner,
            text="Grab a video from the web, cut the part you want, caption it, export a GIF or MP4.",
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED,
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # Setup button — prereqs checklist
        self.project_btn = ctk.CTkButton(
            header, text="Project",
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT, font=T.font(T.SIZE_SM, "bold"),
            corner_radius=14, width=84, height=28,
            command=lambda: self.trim_tab.open_project_hub(),
        )
        self.project_btn.place(relx=1.0, rely=0, anchor="ne", x=-244, y=16)

        self.setup_btn = ctk.CTkButton(
            header, text="⚙ Setup",
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT, font=T.font(T.SIZE_SM, "bold"),
            corner_radius=14, width=82, height=28,
            command=self._open_setup_dialog,
        )
        self.setup_btn.place(relx=1.0, rely=0, anchor="ne", x=-150, y=16)

        # Keyboard shortcuts overlay — discoverable at a glance instead
        # of buried in the status-bar hint that scrolls away after 4s.
        self.shortcuts_btn = ctk.CTkButton(
            header, text="⌨",
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT, font=T.font(T.SIZE_LG, "bold"),
            corner_radius=14, width=36, height=28,
            command=self._open_shortcuts_dialog,
        )
        self.shortcuts_btn.place(relx=1.0, rely=0, anchor="ne", x=-104, y=16)

        # Theme toggle (takes effect on restart)
        current = T.current_mode()
        next_mode = "light" if current == "dark" else "dark"
        self.theme_btn = ctk.CTkButton(
            header, text="☾" if current == "dark" else "☀",
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT, font=T.font(T.SIZE_LG, "bold"),
            corner_radius=14, width=36, height=28,
            command=lambda: self._toggle_theme(next_mode),
        )
        self.theme_btn.place(relx=1.0, rely=0, anchor="ne", x=-56, y=16)

        # Update-available chip (hidden until check_async fires)
        self.update_chip = ctk.CTkButton(
            header, text="", fg_color=T.SUCCESS, hover_color="#2EA043",
            text_color=T.TEXT_ON_ACCENT,
            font=T.font(T.SIZE_SM, "bold"),
            corner_radius=12, height=28, width=0,
            command=self._open_update_link,
        )
        # not packed until there is something to show

        divider = ctk.CTkFrame(self, height=1, fg_color=T.BORDER, corner_radius=0)
        divider.pack(fill="x", side="top")

    # ------------------------------------------------------------------
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=T.RADIUS_LG,
            fg_color=T.BG_SURFACE,
            border_width=1,
            border_color=T.BORDER,
            segmented_button_fg_color=T.BG_RAISED,
            segmented_button_selected_color=T.ACCENT,
            segmented_button_selected_hover_color=T.ACCENT_HOVER,
            segmented_button_unselected_color=T.BG_RAISED,
            segmented_button_unselected_hover_color=T.BG_HOVER,
            text_color=T.TEXT,
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(8, 0))

        self.tabview._segmented_button.configure(
            font=T.font(T.SIZE_MD, "bold"), height=32,
        )

        self.tabview.add(TAB_STUDIO)   # first added = leftmost + default
        self.tabview.add(TAB_BATCH)
        self.tabview.add(TAB_HISTORY)
        self.tabview.add(TAB_DEBUG)

        from videokidnapper.ui.batch_export_tab import BatchExportTab
        from videokidnapper.ui.debug_tab import DebugTab
        from videokidnapper.ui.history_tab import HistoryTab
        from videokidnapper.ui.trim_tab import TrimTab

        self.debug_tab = DebugTab(self.tabview.tab(TAB_DEBUG), self)
        self.debug_tab.pack(fill="both", expand=True)

        self.trim_tab = TrimTab(self.tabview.tab(TAB_STUDIO), self)
        self.trim_tab.pack(fill="both", expand=True)

        self.batch_export_tab = BatchExportTab(
            self.tabview.tab(TAB_BATCH), self,
        )
        self.batch_export_tab.pack(fill="both", expand=True)

        self.history_tab = HistoryTab(self.tabview.tab(TAB_HISTORY), self)
        self.history_tab.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    def _build_statusbar(self):
        divider = ctk.CTkFrame(self, height=1, fg_color=T.BORDER, corner_radius=0)
        divider.pack(fill="x", side="bottom", pady=(6, 0))

        self.status_bar = Toast(self)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.show(
            "Ready · Space play · J/L step · I/O set in-out · "
            "Ctrl+S project · Ctrl+Z/Y undo/redo · Ctrl+E export · ? shortcuts",
            "success",
        )

    def set_project_status(self, name, dirty):
        if not hasattr(self, "project_btn"):
            return
        label = name if name and name != "Untitled" else "Project"
        if len(label) > 14:
            label = f"{label[:11]}..."
        if dirty:
            label = f"{label} *"
        self.project_btn.configure(text=label)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def _active_tab(self):
        name = self.tabview.get()
        if "Trim" in name:
            return self.trim_tab
        return None

    def _bind_keyboard_shortcuts(self):
        # Using bind_all so entries don't swallow them; the _editing_in_entry
        # guard keeps typing in text fields from triggering scrubs.
        self.bind_all("<space>",   lambda e: self._shortcut(e, "keyboard_play_pause"))
        self.bind_all("<Key-j>",   lambda e: self._shortcut(e, "keyboard_nudge", -1.0))
        self.bind_all("<Key-J>",   lambda e: self._shortcut(e, "keyboard_nudge", -1.0))
        self.bind_all("<Key-l>",   lambda e: self._shortcut(e, "keyboard_nudge",  1.0))
        self.bind_all("<Key-L>",   lambda e: self._shortcut(e, "keyboard_nudge",  1.0))
        self.bind_all("<Key-k>",   lambda e: self._shortcut(e, "keyboard_play_pause"))
        self.bind_all("<Key-K>",   lambda e: self._shortcut(e, "keyboard_play_pause"))
        self.bind_all("<Key-i>",   lambda e: self._shortcut(e, "keyboard_mark_in"))
        self.bind_all("<Key-I>",   lambda e: self._shortcut(e, "keyboard_mark_in"))
        self.bind_all("<Key-o>",   lambda e: self._shortcut(e, "keyboard_mark_out"))
        self.bind_all("<Key-O>",   lambda e: self._shortcut(e, "keyboard_mark_out"))
        self.bind_all("<Control-e>", lambda e: self._shortcut(e, "keyboard_export"))
        self.bind_all("<Control-E>", lambda e: self._shortcut(e, "keyboard_export"))
        self.bind_all("<Control-o>", lambda e: self._shortcut(e, "keyboard_open"))
        self.bind_all("<Control-O>", lambda e: self._shortcut(e, "keyboard_open"))
        self.bind_all("<Control-s>", self._save_project_shortcut)
        self.bind_all("<Control-S>", self._save_project_shortcut)
        self.bind_all("<Control-Shift-s>", self._save_project_as_shortcut)
        self.bind_all("<Control-Shift-S>", self._save_project_as_shortcut)
        self.bind_all("<Control-Shift-o>", self._open_project_shortcut)
        self.bind_all("<Control-Shift-O>", self._open_project_shortcut)
        # Ctrl+V routes by what's on the clipboard: a web link opens the
        # Kidnap downloader from ANY tab; anything else falls through to
        # the active tab's own paste (clipboard image → overlay on Trim).
        # Entries keep native paste because _editing_in_entry short-circuits.
        self.bind_all("<Control-v>", self._paste_shortcut)
        self.bind_all("<Control-V>", self._paste_shortcut)
        # Undo / redo. `<Control-Z>` fires on Ctrl+Shift+Z; pair with
        # `<Control-y>` so users coming from any editor convention work.
        self.bind_all("<Control-z>",       lambda e: self._shortcut(e, "keyboard_undo"))
        self.bind_all("<Control-Shift-Z>", lambda e: self._shortcut(e, "keyboard_redo"))
        self.bind_all("<Control-y>",       lambda e: self._shortcut(e, "keyboard_redo"))
        self.bind_all("<Control-Y>",       lambda e: self._shortcut(e, "keyboard_redo"))
        # `?` opens the shortcuts overlay. Not routed through _shortcut()
        # because the target is the app itself, not the active tab.
        self.bind_all("<Key-question>", self._shortcut_shortcuts_overlay)

    def _editing_in_entry(self, event):
        widget = event.widget
        if not widget:
            return False
        cls = widget.winfo_class()
        return cls in ("Entry", "Text", "TEntry", "TCombobox")

    def _shortcut(self, event, method, *args):
        if self._editing_in_entry(event):
            return
        tab = self._active_tab()
        if tab is None:
            return
        fn = getattr(tab, method, None)
        if callable(fn):
            fn(*args)

    def _paste_shortcut(self, event):
        """Ctrl+V, clipboard-aware: a pasted link kidnaps from anywhere.

        A single http(s)/www link switches to the downloader tab with the
        URL filled in, regardless of which tab is active. Everything else
        (images, plain text) defers to the active tab's own
        keyboard_paste_url handler.
        """
        if self._editing_in_entry(event):
            return
        try:
            data = self.clipboard_get()
        except Exception:
            data = ""
        if looks_like_media_url(data or ""):
            self.tabview.set(TAB_STUDIO)
            self.trim_tab.receive_url(data.strip())
            return
        self._shortcut(event, "keyboard_paste_url")

    def _shortcut_shortcuts_overlay(self, event):
        # `?` inside a text entry should still type a literal `?`.
        if self._editing_in_entry(event):
            return
        self._open_shortcuts_dialog()

    def _save_project_shortcut(self, _event):
        self.trim_tab.save_project()
        return "break"

    def _save_project_as_shortcut(self, _event):
        self.trim_tab.save_project(save_as=True)
        return "break"

    def _open_project_shortcut(self, _event):
        self.trim_tab.choose_and_open_project()
        return "break"

    def _request_close(self):
        editor = getattr(self, "trim_tab", None)
        if editor is not None and not editor.request_close():
            return
        self.destroy()

    # ------------------------------------------------------------------
    # Update check
    # ------------------------------------------------------------------
    def _maybe_check_for_update(self):
        if not settings.get("auto_update_check", True):
            return

        def on_update(tag, link):
            if self.winfo_exists():
                self.after(0, self._show_update_chip, tag, link)

        check_async(APP_VERSION, on_update)

    def _show_update_chip(self, tag, link):
        self._update_tag = tag
        self._update_link = link
        self.update_chip.configure(text=f"  ↑ Update {tag}  ", width=140)
        self.update_chip.place(relx=1.0, rely=0, anchor="ne", x=-16, y=16)
        # Make room for the update action instead of covering Setup.
        self.setup_btn.place_configure(x=-292)
        self.shortcuts_btn.place_configure(x=-246)
        self.theme_btn.place_configure(x=-198)
        self.project_btn.place_configure(x=-386)
        if self.status_bar:
            self.status_bar.show(f"Update available: {tag}", "success")

    def _open_update_link(self):
        link = getattr(self, "_update_link", None)
        if link:
            from videokidnapper.ui.update_dialog import UpdateDialog
            self._update_dialog = UpdateDialog(
                self, APP_VERSION, getattr(self, "_update_tag", "new"), link,
            )

    # ------------------------------------------------------------------
    # Plugin API
    # ------------------------------------------------------------------
    def register_tab(self, display_name, factory, glyph="◆"):
        """Append a tab contributed by a plugin.

        Parameters
        ----------
        display_name : str
            Shown on the tab's segmented button. Kept short — CTkTabview
            centers the label and long strings wrap awkwardly.
        factory : callable
            ``factory(parent_frame) -> widget``. The widget is packed
            fill="both", expand=True inside the tab's frame.
        glyph : str
            Single-character icon prefix. Defaults to a diamond so
            plugin tabs are visually distinct from built-in tabs.

        Returns the widget produced by ``factory``, or ``None`` if the
        factory raised (the failure is logged to the Debug tab).
        """
        label = f"  {glyph}  {display_name}  "
        try:
            self.tabview.add(label)
            parent = self.tabview.tab(label)
            widget = factory(parent)
            if widget is not None:
                widget.pack(fill="both", expand=True)
            return widget
        except Exception as exc:
            if hasattr(self, "debug_tab"):
                try:
                    self.debug_tab.add_log(
                        f"Failed to register plugin tab {display_name!r}: {exc}",
                        "ERROR",
                    )
                except Exception:
                    pass
            return None

    def _load_plugins(self):
        """Discover entry-point plugins and fire their ``on_app_ready`` hook.

        Runs after ``_build_ui`` + exception handler install so a
        misbehaving plugin hits the global handler instead of the bare
        Tk loop. Each plugin is called in its own try/except so one
        bad actor doesn't prevent the rest from loading.
        """
        from videokidnapper.plugins import discover_plugins

        discovered = discover_plugins(app_version=APP_VERSION)
        self.plugins = discovered

        loaded = 0
        for entry in discovered:
            if entry.error or entry.plugin is None:
                if hasattr(self, "debug_tab"):
                    try:
                        self.debug_tab.add_log(
                            f"Skipped plugin {entry.name!r}: {entry.error}",
                            "WARN",
                        )
                    except Exception:
                        pass
                continue
            try:
                entry.plugin.on_app_ready(self)
                loaded += 1
                if hasattr(self, "debug_tab"):
                    try:
                        self.debug_tab.add_log(
                            f"Loaded plugin {entry.name!r} "
                            f"({entry.plugin.name} v{entry.plugin.version})",
                            "INFO",
                        )
                    except Exception:
                        pass
            except Exception as exc:
                if hasattr(self, "debug_tab"):
                    try:
                        self.debug_tab.add_log(
                            f"Plugin {entry.name!r} on_app_ready failed: {exc}",
                            "ERROR",
                        )
                    except Exception:
                        pass
        if loaded and self.status_bar:
            self.status_bar.show(
                f"Loaded {loaded} plugin{'s' if loaded != 1 else ''}",
                "success",
            )

    # ------------------------------------------------------------------
    # Setup dialog
    # ------------------------------------------------------------------
    def _open_setup_dialog(self):
        from videokidnapper.ui.setup_dialog import SetupDialog
        SetupDialog(self, on_relaunch=self._restart_app)

    # ------------------------------------------------------------------
    # Shortcuts overlay (? key / header chip)
    # ------------------------------------------------------------------
    def _open_shortcuts_dialog(self):
        from videokidnapper.ui.shortcuts_dialog import ShortcutsDialog
        ShortcutsDialog(self)

    # ------------------------------------------------------------------
    # Theme toggle
    # ------------------------------------------------------------------
    #
    # A live theme swap would need us to walk every widget in the app
    # and .configure() its colors — CustomTkinter bakes color tokens at
    # widget-construction time. Hundreds of widgets, brittle, and the
    # status-bar "restart to apply" toast was easy to miss and made the
    # button feel broken (issue from user feedback: "This button does
    # nothing"). Trade: confirm-to-restart, which makes the click
    # visibly do *something* every time.
    def _toggle_theme(self, mode):
        T.set_mode(mode)
        # Flip the button icon immediately so the user sees the click
        # registered even if they pick "Later". Also flip the closure
        # mode so a second click in the same session inverts again.
        self._refresh_theme_btn(mode)
        if self._confirm_theme_restart(mode):
            self._restart_app()
            return
        if self.status_bar:
            self.status_bar.show(
                f"Theme set to {mode} — restart VideoKidnapper to apply.",
                "info",
            )

    def _refresh_theme_btn(self, saved_mode):
        """Rebind the theme button so its icon + command reflect ``saved_mode``.

        ``saved_mode`` is the preference we just persisted. The button
        should now display the OPPOSITE (what the next click would flip
        to) so the icon matches the button's action, not the current
        state. Matches the initial-construction convention.
        """
        next_mode = "light" if saved_mode == "dark" else "dark"
        self.theme_btn.configure(
            text="☾" if saved_mode == "dark" else "☀",
            command=lambda: self._toggle_theme(next_mode),
        )

    def _confirm_theme_restart(self, mode):
        """Modal yes/no for the restart prompt. Returns True if the user
        chose Restart, False for Later. Falls through to False if a Tk
        error swallows the dialog (extremely unlikely but would rather
        skip the restart than crash)."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Restart to apply theme")
        dialog.geometry("380x170")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(fg_color=T.BG_BASE)

        # Center on the main window.
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 380) // 2
        y = self.winfo_y() + (self.winfo_height() - 170) // 2
        dialog.geometry(f"+{x}+{y}")

        card = ctk.CTkFrame(
            dialog, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(
            card, text=f"Theme set to {mode}.",
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT,
        ).pack(pady=(18, 4))
        ctk.CTkLabel(
            card,
            text="VideoKidnapper needs a restart to re-theme every panel.",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED,
        ).pack(pady=(0, 14))

        choice = {"restart": False}

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(pady=(0, 14))

        def pick(restart):
            choice["restart"] = restart
            dialog.grab_release()
            dialog.destroy()

        ctk.CTkButton(
            btn_row, text="Later",
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT, font=T.font(T.SIZE_MD, "bold"),
            corner_radius=T.RADIUS_SM, width=110, height=34,
            command=lambda: pick(False),
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="Restart now",
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            text_color=T.TEXT_ON_ACCENT, font=T.font(T.SIZE_MD, "bold"),
            corner_radius=T.RADIUS_SM, width=130, height=34,
            command=lambda: pick(True),
        ).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", lambda: pick(False))
        # Block until the user picks.
        self.wait_window(dialog)
        return choice["restart"]

    def _restart_app(self):
        """Relaunch the current process cleanly.

        Works for three launch shapes: ``python main.py`` (dev),
        ``python -m videokidnapper`` (module), and the PyInstaller
        one-file ``.exe`` (frozen). The frozen case needs sys.argv[1:]
        instead of sys.argv because argv[0] is the exe path itself and
        prepending sys.executable would pass it twice.
        """
        import subprocess
        if getattr(sys, "frozen", False):
            args = [sys.executable, *sys.argv[1:]]
        else:
            args = [sys.executable, *sys.argv]
        # close_fds keeps the spawned process clean of our Tk handles.
        subprocess.Popen(args, close_fds=True)
        # destroy() ends the Tk mainloop; any pending after() callbacks
        # get dropped, which is what we want — we're replacing the
        # process with a fresh one anyway.
        self.destroy()

    # ------------------------------------------------------------------
    # Uncaught-exception routing — keep the app alive and surface errors.
    # ------------------------------------------------------------------
    def _install_exception_handler(self):
        def report(exc_type, exc_value, tb):
            text = "".join(traceback.format_exception(exc_type, exc_value, tb))
            try:
                self.debug_tab.add_log(f"Uncaught exception:\n{text}", "ERROR")
            except Exception:
                pass
            if self.status_bar:
                self.status_bar.show(
                    f"Error: {exc_type.__name__}: {exc_value} (see Debug tab)",
                    "error",
                )

        def tk_report(exc_type, exc_value, tb):
            report(exc_type, exc_value, tb)

        # `report_callback_exception` catches errors raised from Tk callbacks
        # (button clicks, after() handlers, etc.) without killing the event loop.
        self.report_callback_exception = tk_report  # type: ignore[assignment]

        _previous_hook = sys.excepthook

        def excepthook(exc_type, exc_value, tb):
            report(exc_type, exc_value, tb)
            _previous_hook(exc_type, exc_value, tb)

        sys.excepthook = excepthook

    # ------------------------------------------------------------------
    def _show_setup_landing(self):
        """Explain components needing attention and wait for install consent."""
        from videokidnapper.utils import prereq_check
        self._setup_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._setup_frame.place(relx=0.5, rely=0.5, anchor="center")

        self._setup_icon = ctk.CTkLabel(
            self._setup_frame, text="⚙",
            font=T.font(48, "bold"), text_color=T.ACCENT,
        )
        self._setup_icon.pack(pady=(0, 8))

        self._setup_title = ctk.CTkLabel(
            self._setup_frame, text="Setting up VideoKidnapper",
            font=T.font(T.SIZE_HERO, "bold"), text_color=T.TEXT,
        )
        self._setup_title.pack(pady=(0, 6))

        missing = prereq_check.missing_required()
        plan = prereq_check.describe_install_plan(missing)
        self._setup_msg = ctk.CTkLabel(
            self._setup_frame,
            text=f"Needed to continue: {plan}" if plan
                 else "Checking components…",
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
            justify="center", wraplength=460,
        )
        self._setup_msg.pack(pady=(0, 14))

        self._setup_progress = ctk.CTkProgressBar(
            self._setup_frame, width=380, height=8,
            progress_color=T.ACCENT, fg_color=T.BG_RAISED, corner_radius=4,
        )
        self._setup_progress.set(0)
        self._setup_progress.pack(pady=(0, 16))

        self._setup_btnrow = ctk.CTkFrame(self._setup_frame, fg_color="transparent")
        self._setup_btnrow.pack()

        self._setup_detail = ctk.CTkLabel(
            self._setup_frame,
            text=(
                "Nothing downloads until you approve. FFmpeg comes from "
                f"{prereq_check.FFMPEG_DOWNLOAD_SOURCE}, is checked with the "
                "publisher's SHA-256 digest, and installs without admin access."
                if "ffmpeg" in missing else
                "Nothing installs until you approve. Python packages use this "
                "Python installation and do not require admin access."
            ),
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
            justify="center", wraplength=520,
        )
        self._setup_detail.pack(pady=(10, 0), before=self._setup_btnrow)

        from videokidnapper.ui.theme import button
        button(
            self._setup_btnrow, "Install and continue", variant="primary",
            width=180, command=lambda: self._confirm_setup_install(missing),
        ).pack(side="left", padx=4)
        button(
            self._setup_btnrow, "Review details", variant="secondary",
            width=140, command=self._open_setup_dialog,
        ).pack(side="left", padx=4)
        button(
            self._setup_btnrow, "Exit", variant="ghost",
            width=80, command=self.destroy,
        ).pack(side="left", padx=4)

    def _confirm_setup_install(self, missing):
        for widget in self._setup_btnrow.winfo_children():
            widget.destroy()
        self._setup_detail.configure(
            text="Downloading and verifying. You can close the app to cancel.",
        )
        self._auto_install_prereqs(missing)

    def _auto_install_prereqs(self, missing):
        from videokidnapper.utils import prereq_check
        if not missing:
            # Nothing actually missing (e.g. a probe false-negative that
            # the detection fix already resolved) — just go.
            self._finish_setup_and_launch()
            return

        # Worker thread NEVER touches Tk. It writes progress into a plain
        # dict; a main-thread poller (after-loop) reads it and updates the
        # UI. This is the only thread-safe way to drive Tk from a worker.
        self._install_state = {
            "frac": 0.0, "note": "", "done": False,
            "installed": None, "failures": None,
        }

        def progress(frac, note):
            self._install_state["frac"] = max(0.0, min(1.0, frac))
            if note:
                self._install_state["note"] = note

        def worker():
            installed, failures = prereq_check.install_missing(
                missing, progress_cb=progress,
            )
            self._install_state["installed"] = installed
            self._install_state["failures"] = failures
            self._install_state["done"] = True

        import threading
        threading.Thread(target=worker, daemon=True).start()
        self._poll_install()

    def _poll_install(self):
        st = getattr(self, "_install_state", None)
        if st is None or not self.winfo_exists():
            return
        self._setup_progress.set(st["frac"])
        if st["note"]:
            self._setup_msg.configure(text=st["note"])
        if st["done"]:
            self._on_auto_install_done(st["installed"], st["failures"])
            return
        self.after(120, self._poll_install)

    def _on_auto_install_done(self, installed, failures):
        from videokidnapper.utils import prereq_check
        if failures:
            self._setup_install_failed(failures)
            return
        # Re-detect FFmpeg for the encode path, then either restart (source
        # build that installed pip packages) or continue in-process.
        self.ffmpeg_path, self.ffprobe_path = check_ffmpeg()
        if prereq_check.install_needs_restart(installed):
            self._setup_msg.configure(text="Installed — restarting…")
            self.after(600, self._restart_app)
        else:
            self._finish_setup_and_launch()

    def _finish_setup_and_launch(self):
        """Tear down the landing and build the real UI in the same process."""
        if getattr(self, "_setup_frame", None) is not None:
            self._setup_frame.destroy()
            self._setup_frame = None
        if not self.ffmpeg_path:
            self.ffmpeg_path, self.ffprobe_path = check_ffmpeg()
        self._start_main_ui()

    def _retry_setup(self):
        from videokidnapper.utils import prereq_check
        self._setup_icon.configure(text="⚙", text_color=T.ACCENT)
        self._setup_title.configure(text="Setting up VideoKidnapper")
        for w in self._setup_btnrow.winfo_children():
            w.destroy()
        missing = prereq_check.missing_required()
        self._setup_msg.configure(
            text=f"Needed to continue: {prereq_check.describe_install_plan(missing)}",
            text_color=T.TEXT_MUTED,
        )
        self._setup_detail.configure(
            text="Ready to retry. Nothing downloads until you approve.",
        )
        from videokidnapper.ui.theme import button
        button(
            self._setup_btnrow, "Retry install", variant="primary",
            width=150, command=lambda: self._confirm_setup_install(missing),
        ).pack(side="left", padx=4)
        button(
            self._setup_btnrow, "Exit", variant="ghost",
            width=80, command=self.destroy,
        ).pack(side="left", padx=4)

    def _setup_install_failed(self, failures):
        from videokidnapper.ui.theme import button
        names = ", ".join(k for k, _ in failures)
        self._setup_icon.configure(text="⚠", text_color=T.WARN)
        self._setup_title.configure(text="Couldn't finish setup")
        self._setup_msg.configure(
            text=f"Automatic install failed for: {names}.\n"
                 "Open Setup to see the details and try the advanced options, "
                 "or retry.",
            text_color=T.TEXT_MUTED,
        )
        for w in self._setup_btnrow.winfo_children():
            w.destroy()
        button(
            self._setup_btnrow, "  Open Setup", variant="primary",
            width=150, command=self._open_setup_dialog,
        ).pack(side="left", padx=4)
        button(
            self._setup_btnrow, "Retry", variant="secondary",
            width=90, command=self._retry_setup,
        ).pack(side="left", padx=4)
        button(
            self._setup_btnrow, "Exit", variant="ghost",
            width=90, command=self.destroy,
        ).pack(side="left", padx=4)
