# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import sys
import tkinter as tk
import traceback
from pathlib import Path

import customtkinter as ctk

from videokidnapper.config import APP_NAME, APP_VERSION, WINDOW_SIZE, MIN_WINDOW_SIZE
from videokidnapper.ui import theme as T
from videokidnapper.ui.studio.chrome import WorkspaceHost, WorkspaceSwitcher
from videokidnapper.ui.studio.icons import icon_button
from videokidnapper.ui.theme import button
from videokidnapper.ui.widgets import Toast
from videokidnapper.utils import project_files, settings
from videokidnapper.utils.dnd import enable_dnd_for
from videokidnapper.utils.ffmpeg_check import check_ffmpeg
from videokidnapper.utils.github_update import check_async
from videokidnapper.utils.urltools import looks_like_media_url

# The three main workspaces, in the order the header shows them. Each
# one is a step in the app's flow: bring a clip in, edit it, export it.
WORKSPACES = (("import", "1  Import"), ("edit", "2  Edit"), ("export", "3  Export"))
# Keys of the editor, the deferred Export sub-pages and the debug log.
# Batch files and History are built on first view (see _ensure_tab).
TAB_STUDIO = "edit"
TAB_BATCH = "batch"
TAB_HISTORY = "history"
TAB_DEBUG = "log"
# Shortcuts that only make sense while looking at the editor.
_EDIT_ONLY = {
    "keyboard_play_pause", "keyboard_nudge", "keyboard_mark_in",
    "keyboard_mark_out", "keyboard_save_range", "keyboard_paste_url",
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._is_first_run = settings.is_first_run()
        T.configure_global()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(self._initial_geometry())
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

    def _initial_geometry(self):
        """Studio wants room: up to 1440x900, centered, within the screen."""
        try:
            want_w, want_h = (int(v) for v in WINDOW_SIZE.split("x"))
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w = max(MIN_WINDOW_SIZE[0], min(want_w, sw - 60))
            h = max(MIN_WINDOW_SIZE[1], min(want_h, sh - 90))
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2 - 20)
            return f"{w}x{h}+{x}+{y}"
        except Exception:
            return WINDOW_SIZE

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
        self._build_statusbar()
        self._build_workspaces()

        # Only the eagerly-built tabs. Deferred tabs receive the toast
        # in their own constructor — reaching for them here would build
        # them and undo the deferral.
        if hasattr(self.trim_tab, "set_toast"):
            self.trim_tab.set_toast(self.status_bar)

    # ------------------------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(self, height=54, corner_radius=0, fg_color=T.BG_SURFACE)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        self.header = header

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.pack(side="left", padx=(16, 18))
        ctk.CTkLabel(
            brand, text="▶", width=26, height=26, corner_radius=6,
            fg_color=T.TEXT, text_color=T.BG_SURFACE, font=T.font(T.SIZE_SM, "bold"),
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(brand, text=APP_NAME, font=T.font(T.SIZE_LG, "bold"),
                     text_color=T.TEXT).pack(side="left")

        self.switcher = WorkspaceSwitcher(header, WORKSPACES, command=self.show_workspace)
        self.switcher.pack(side="left", pady=11)

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right", padx=(0, 12))
        self.quick_export_btn = button(
            right, "Quick export", variant="primary", height=36, width=150,
            font=T.font(T.SIZE_MD, "bold"),
            command=lambda: self.trim_tab.keyboard_export(),
        )
        self.quick_export_btn.pack(side="right", padx=(8, 0))
        self.settings_btn = icon_button(right, "settings", command=self._open_settings_menu)
        self.settings_btn.pack(side="right", padx=1)
        icon_button(right, "help", command=self._open_shortcuts_dialog).pack(side="right", padx=1)
        icon_button(right, "redo",
                    command=lambda: self.trim_tab.keyboard_redo()).pack(side="right", padx=1)
        icon_button(right, "undo",
                    command=lambda: self.trim_tab.keyboard_undo()).pack(side="right", padx=1)
        self.project_btn = button(
            right, "Untitled project", variant="ghost", height=32,
            font=T.font(T.SIZE_MD, "bold"), text_color=T.TEXT,
            command=lambda: self.trim_tab.open_project_hub(),
        )
        self.project_btn.pack(side="right", padx=(0, 8))

        # Update-available chip (hidden until check_async fires)
        self.update_chip = ctk.CTkButton(
            right, text="", fg_color=T.ACCENT_SOFT, hover_color=T.BG_HOVER,
            text_color=T.ACCENT_SOFT_TEXT, font=T.font(T.SIZE_SM, "bold"),
            corner_radius=14, height=28, width=0,
            command=self._open_update_link,
        )
        # not packed until there is something to show

        self._settings_menu = tk.Menu(
            self, tearoff=0, bg=T.BG_SURFACE, fg=T.TEXT,
            activebackground=T.ACCENT_SOFT, activeforeground=T.TEXT,
            font=(T.FONT_FAMILY, 10), bd=1, relief="solid",
        )

        ctk.CTkFrame(self, height=1, fg_color=T.BORDER, corner_radius=0).pack(
            fill="x", side="top")

    def _build_workspaces(self):
        from videokidnapper.ui.debug_tab import DebugTab
        from videokidnapper.ui.studio.export_workspace import ExportWorkspace
        from videokidnapper.ui.studio.import_workspace import ImportWorkspace
        from videokidnapper.ui.trim_tab import TrimTab

        self.workspaces = WorkspaceHost(self, on_switch=self._on_workspace_switched)
        self.workspaces.pack(fill="both", expand=True)
        # Plugins and scripts reach the host through the old attribute.
        self.tabview = self.workspaces

        # The debug log starts first so it captures everything after it.
        log = self.workspaces.add("log")
        log_bar = ctk.CTkFrame(log, fg_color=T.BG_SURFACE, corner_radius=0, height=44)
        log_bar.pack(fill="x")
        log_bar.pack_propagate(False)
        button(log_bar, "‹  Back to editing", variant="ghost", height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=lambda: self.show_workspace("edit")).pack(side="left", padx=10)
        self.debug_tab = DebugTab(log, self)
        self.debug_tab.pack(fill="both", expand=True, padx=12, pady=12)

        self.trim_tab = TrimTab(self.workspaces.add("edit"), self)
        self.trim_tab.pack(fill="both", expand=True)

        self.import_workspace = ImportWorkspace(self.workspaces.add("import"), self, self.trim_tab)
        self.import_workspace.pack(fill="both", expand=True)

        # Batch files and History are built the first time they are shown.
        # Constructing them up front cost about half the window build
        # (Batch 365 ms, History 93 ms, measured in situ), for two pages
        # most sessions never open. The Export workspace asks for them
        # through _ensure_tab when one of its sub-tabs is picked.
        self._lazy_tabs = {
            TAB_BATCH: self._construct_batch_tab,
            TAB_HISTORY: self._construct_history_tab,
        }
        self._built_tabs = {}
        self.export_workspace = ExportWorkspace(self.workspaces.add("export"), self, self.trim_tab)
        self.export_workspace.pack(fill="both", expand=True)

        self.trim_tab.add_state_listener(self._refresh_quick_export)
        self.trim_tab.options.add_listener(self._refresh_quick_export)
        self._refresh_quick_export()
        self.show_workspace("edit" if self.trim_tab.video_path else "import")

    def show_workspace(self, key):
        self.workspaces.set(key)

    def _on_workspace_switched(self, key):
        self.switcher.select(key)
        if key == "import":
            self.import_workspace.refresh()
        elif key == "export":
            self.export_workspace.refresh()

    def _refresh_quick_export(self):
        editor = self.trim_tab
        fmt = "MP3" if editor.options.audio_only_var.get() else editor.format_var.get()
        self.quick_export_btn.configure(
            text=f"Quick export  ·  {fmt} {editor.quality_var.get()}",
            state="normal" if editor.video_path else "disabled",
            width=0,
        )

    # -- lazy page construction ---------------------------------------
    def _on_tab_changed(self, name=None):
        """Build a deferred page the first time it is selected.

        ``name`` defaults to the Export workspace's current sub-page.
        Returns the page, or None when there is none or it failed to
        build: a page that fails must not wedge switching, so the error
        goes to the debug log instead of propagating.
        """
        try:
            return self._ensure_tab(name or self.export_workspace.current)
        except Exception:
            try:
                self.debug_tab.add_log(
                    f"Could not open {name!r}:\n{traceback.format_exc()}", "ERROR")
            except Exception:
                pass
            return None

    def _ensure_tab(self, name):
        """Return a lazily-built page, constructing it on first use."""
        if name in self._built_tabs:
            return self._built_tabs[name]
        factory = self._lazy_tabs.get(name)
        if factory is None:
            return None
        widget = factory()
        self._built_tabs[name] = widget
        return widget

    def _tab_if_built(self, name):
        """The page, or None when it has not been constructed yet.

        For callers that want to poke an already-open page but have no
        reason to pay for building it — refreshing History after an
        export, for instance. History reads its data when it is built,
        so a refresh it never receives is not a refresh it needed.
        """
        return self._built_tabs.get(name)

    def _construct_batch_tab(self):
        from videokidnapper.ui.batch_export_tab import BatchExportTab

        tab = BatchExportTab(self.export_workspace.page_host, self)
        if hasattr(tab, "set_toast") and hasattr(self, "status_bar"):
            tab.set_toast(self.status_bar)
        return tab

    def _construct_history_tab(self):
        from videokidnapper.ui.history_tab import HistoryTab

        tab = HistoryTab(self.export_workspace.page_host, self)
        if hasattr(tab, "set_toast") and hasattr(self, "status_bar"):
            tab.set_toast(self.status_bar)
        return tab

    @property
    def batch_export_tab(self):
        return self._ensure_tab(TAB_BATCH)

    @property
    def history_tab(self):
        return self._ensure_tab(TAB_HISTORY)

    # ------------------------------------------------------------------
    def _build_statusbar(self):
        self.status_bar = Toast(self)
        self.status_bar.pack(fill="x", side="bottom")
        ctk.CTkFrame(self, height=1, fg_color=T.BORDER, corner_radius=0).pack(
            fill="x", side="bottom")
        self.status_bar.show(
            "Ready · Space play · J/L step · I/O mark in/out · Q save range · "
            "Ctrl+E export · ? shortcuts",
            "success",
        )

    def set_project_status(self, name, dirty):
        if not hasattr(self, "project_btn"):
            return
        untitled = not name or name == "Untitled"
        label = "Untitled project" if untitled else name
        if len(label) > 26:
            label = f"{label[:23]}…"
        editor = getattr(self, "trim_tab", None)
        has_video = bool(editor is not None and editor.video_path)
        # "Saved" only means something once the project has a file.
        state = "Edited" if dirty else ("" if untitled else "Saved")
        self.project_btn.configure(
            text=f"{label}  ·  {state}" if has_video and state else label,
        )

    # ------------------------------------------------------------------
    # Settings menu (gear)
    # ------------------------------------------------------------------
    def _open_settings_menu(self):
        menu = self._settings_menu
        menu.delete(0, "end")
        menu.add_command(label="Setup and components…", command=self._open_setup_dialog)
        menu.add_command(label="Check for updates", command=self._check_updates_now)
        menu.add_separator()
        menu.add_cascade(label="Theme", menu=self._build_theme_menu(menu))
        menu.add_separator()
        menu.add_command(label="Keyboard shortcuts", command=self._open_shortcuts_dialog)
        menu.add_command(label="Export history", command=self._show_history)
        menu.add_command(label="Debug log", command=lambda: self.show_workspace("log"))
        btn = self.settings_btn
        try:
            menu.tk_popup(btn.winfo_rootx() - 160, btn.winfo_rooty() + btn.winfo_height())
        finally:
            menu.grab_release()

    def _show_history(self):
        self.show_workspace("export")
        self.export_workspace.show("history")

    def _check_updates_now(self):
        self.status_bar.show("Checking GitHub for a newer version…", "info")

        def on_update(tag, link):
            if self.winfo_exists():
                self.after(0, self._show_update_chip, tag, link)

        def report_if_current():
            if not getattr(self, "_update_tag", None):
                self.status_bar.show(f"You're up to date (v{APP_VERSION})", "success")

        check_async(APP_VERSION, on_update)
        self.after(5000, report_if_current)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def _bind_accel(self, body, handler, both_cases=True):
        """Bind one app accelerator under every platform's modifier key.

        Tk exposes Ctrl and Cmd as separate modifiers, and until 1.8.2
        only ``<Control-...>`` was bound — so on macOS every accelerator
        in the app was dead. ⌘O, ⌘S and ⌘E did nothing, on the one
        platform that ships a signed DMG, while the shortcuts overlay
        cheerfully advertised "Ctrl+O".

        Both modifiers are bound everywhere rather than switching on
        ``sys.platform``: Command never fires on Windows or Linux, and
        leaving Control live on macOS costs nothing and helps anyone
        arriving with Windows muscle memory.

        Tk also treats ``<Control-s>`` and ``<Control-S>`` as different
        events, because Shift changes the keysym — so each letter is
        bound in both cases by default. A ``Shift-`` prefix in ``body``
        is passed through untouched and only the letter is case-folded.

        ``both_cases=False`` is for the undo/redo pair. Some Tk builds
        deliver Ctrl+Shift+Z as ``<Control-Z>`` rather than
        ``<Control-Shift-Z>``, so the upper-case form has to mean redo;
        folding it in with undo would make redo undo instead.
        """
        prefix, _, key = body.rpartition("-")
        prefix = f"{prefix}-" if prefix else ""
        cases = {key.lower(), key.upper()} if both_cases else {key}
        for modifier in ("Control", "Command"):
            for case in cases:
                self.bind_all(f"<{modifier}-{prefix}{case}>", handler)

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
        self.bind_all("<Key-q>",   lambda e: self._shortcut(e, "keyboard_save_range"))
        self.bind_all("<Key-Q>",   lambda e: self._shortcut(e, "keyboard_save_range"))
        self._bind_accel("e", lambda e: self._shortcut(e, "keyboard_export"))
        self._bind_accel("o", lambda e: self._shortcut(e, "keyboard_open"))
        self._bind_accel("s", self._save_project_shortcut)
        self._bind_accel("Shift-s", self._save_project_as_shortcut)
        self._bind_accel("Shift-o", self._open_project_shortcut)
        # Ctrl+V routes by what's on the clipboard: a web link opens the
        # downloader from any workspace; an image becomes an overlay in
        # Edit. Entries keep native paste because _editing_in_entry
        # short-circuits.
        self._bind_accel("v", self._paste_shortcut)
        # Undo / redo. `<Control-Z>` fires on Ctrl+Shift+Z; pair with
        # `<Control-y>` so users coming from any editor convention work.
        # Case matters here — see _bind_accel's both_cases note. The
        # upper-case bare form is Ctrl+Shift+Z on some Tk builds, so it
        # must map to redo, not undo.
        self._bind_accel("z", lambda e: self._shortcut(e, "keyboard_undo"),
                         both_cases=False)
        self._bind_accel("Z", lambda e: self._shortcut(e, "keyboard_redo"),
                         both_cases=False)
        self._bind_accel("Shift-z", lambda e: self._shortcut(e, "keyboard_redo"))
        self._bind_accel("y", lambda e: self._shortcut(e, "keyboard_redo"))
        # `?` opens the shortcuts overlay. Not routed through _shortcut()
        # because the target is the app itself, not the editor.
        self.bind_all("<Key-question>", self._shortcut_shortcuts_overlay)

    def _editing_in_entry(self, event):
        widget = event.widget
        if not widget:
            return False
        try:
            cls = widget.winfo_class()
        except Exception:
            return False
        return cls in ("Entry", "Text", "TEntry", "TCombobox")

    def _shortcut(self, event, method, *args):
        if self._editing_in_entry(event):
            return None
        editor = getattr(self, "trim_tab", None)
        if editor is None:
            return None
        if method in _EDIT_ONLY and self.workspaces.get() != "edit":
            return None
        fn = getattr(editor, method, None)
        if callable(fn):
            fn(*args)
            # Space would otherwise also "click" whatever button has focus.
            return "break"
        return None

    def _paste_shortcut(self, event):
        """Ctrl+V, clipboard-aware: a pasted link kidnaps from anywhere.

        A single http(s)/www link opens Import with the URL filled in,
        regardless of the current workspace. Everything else (images,
        plain text) defers to the editor's own paste handler.
        """
        if self._editing_in_entry(event):
            return
        try:
            data = self.clipboard_get()
        except Exception:
            data = ""
        if looks_like_media_url(data or ""):
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
        self.update_chip.configure(text=f"  Update to {tag}  ")
        self.update_chip.pack(side="right", padx=(0, 10), before=self.project_btn)
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
        """Add a workspace contributed by a plugin.

        Parameters
        ----------
        display_name : str
            Shown on the header's workspace switcher after Import, Edit
            and Export. Keep it short so the header doesn't crowd.
        factory : callable
            ``factory(parent_frame) -> widget``. The widget is packed
            fill="both", expand=True inside the tab's frame.
        glyph : str
            Single-character icon prefix. Defaults to a diamond so
            plugin tabs are visually distinct from built-in tabs.

        Returns the widget produced by ``factory``, or ``None`` if the
        factory raised (the failure is logged to the Debug tab).
        """
        key = f"plugin:{display_name}"
        try:
            parent = self.workspaces.add(key)
            self.switcher.add_item(key, f"{glyph}  {display_name}")
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
    # Theme picker
    # ------------------------------------------------------------------
    #
    # A live theme swap would need us to walk every widget in the app
    # and .configure() its colors — CustomTkinter bakes color tokens at
    # widget-construction time. Hundreds of widgets, brittle, and the
    # status-bar "restart to apply" toast was easy to miss and made the
    # button feel broken (issue from user feedback: "This button does
    # nothing"). Trade: confirm-to-restart, which makes the click
    # visibly do *something* every time.
    def _build_theme_menu(self, parent):
        """Submenu of every theme, the current one checked."""
        if getattr(self, "_theme_menu", None) is None:
            self._theme_menu = tk.Menu(
                parent, tearoff=0, bg=T.BG_SURFACE, fg=T.TEXT,
                activebackground=T.ACCENT_SOFT, activeforeground=T.TEXT,
                selectcolor=T.ACCENT, font=(T.FONT_FAMILY, 10),
            )
            # Kept on self: a StringVar that gets collected while the menu
            # is open loses the check mark on the current entry.
            self._theme_menu_var = tk.StringVar(master=self)
            for key, label in T.THEME_LABELS.items():
                self._theme_menu.add_radiobutton(
                    label=label, value=key, variable=self._theme_menu_var,
                    command=lambda k=key: self._pick_theme(k),
                )
        self._theme_menu_var.set(T.current_theme())
        return self._theme_menu

    def _pick_theme(self, key):
        if key == T.current_theme():
            return
        T.set_theme(key)
        label = T.THEME_LABELS.get(key, key)
        if self._confirm_theme_restart(label):
            self._restart_app()
            return
        if self.status_bar:
            self.status_bar.show(
                f"Theme set to {label} — restart VideoKidnapper to apply.",
                "info",
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
                    f"Error: {exc_type.__name__}: {exc_value} (details: Settings › Debug log)",
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
        """Explain missing prerequisites and wait for install consent."""
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
                 else "Checking prerequisites…",
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

        # Offer the automatic install only where it can actually work.
        # It used to be offered on every platform and then fail on macOS
        # and Linux with the reason hidden behind "Open Setup".
        needs_manual_ffmpeg = (
            "ffmpeg" in missing and not prereq_check.can_auto_install_ffmpeg()
        )
        if needs_manual_ffmpeg:
            command = prereq_check.build_install_commands(
                missing_ffmpeg=True, missing_pip=[])[0]
            detail = (
                "Automatic FFmpeg install is not available on this system. "
                f"Install it with:\n{command}\nthen check again."
            )
        elif "ffmpeg" in missing:
            detail = (
                "Nothing downloads until you approve. FFmpeg comes from "
                f"{prereq_check.ffmpeg_download_source()}, is checked "
                "against its SHA-256 digest, and installs without admin access."
            )
        else:
            detail = (
                "Nothing installs until you approve. Python packages use this "
                "Python installation and do not require admin access."
            )
        self._setup_detail = ctk.CTkLabel(
            self._setup_frame, text=detail,
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
            justify="center", wraplength=520,
        )
        self._setup_detail.pack(pady=(10, 0), before=self._setup_btnrow)

        from videokidnapper.ui.theme import button
        if needs_manual_ffmpeg:
            button(
                self._setup_btnrow, "Check again", variant="primary",
                width=150, command=self._recheck_setup,
            ).pack(side="left", padx=4)
        else:
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

    def _recheck_setup(self):
        """The user installed something by hand: look again."""
        from videokidnapper.utils import prereq_check
        if not prereq_check.missing_required():
            self._finish_setup_and_launch()
            return
        self._setup_frame.destroy()
        self._setup_frame = None
        self._show_setup_landing()

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
        # Say why. The reason used to be visible only inside the Setup
        # dialog's console, which most people never opened.
        reason = str(failures[0][1] or "").strip()
        if len(reason) > 220:
            reason = reason[:217] + "..."
        self._setup_icon.configure(text="⚠", text_color=T.WARN)
        self._setup_title.configure(text="Couldn't finish setup")
        self._setup_msg.configure(
            text=f"Automatic install failed for: {names}.\n"
                 + (f"{reason}\n" if reason else "")
                 + "Open Setup for the full log and other options, or retry.",
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
