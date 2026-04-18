# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import sys
import traceback
import webbrowser

import customtkinter as ctk

from videokidnapper.config import APP_NAME, APP_VERSION, WINDOW_SIZE, MIN_WINDOW_SIZE
from videokidnapper.ui import theme as T
from videokidnapper.ui.widgets import Toast
from videokidnapper.utils import settings
from videokidnapper.utils.dnd import enable_dnd_for
from videokidnapper.utils.ffmpeg_check import check_ffmpeg
from videokidnapper.utils.github_update import check_async


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        T.configure_global()

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)
        self.configure(fg_color=T.BG_BASE)

        # Turn DnD on BEFORE any widget is created so their
        # drop_target_register() calls succeed during __init__.
        self.dnd_enabled = enable_dnd_for(self)

        self.ffmpeg_path, self.ffprobe_path = check_ffmpeg()

        if not self.ffmpeg_path:
            self._show_setup_landing()
            return

        self._build_ui()
        self._bind_keyboard_shortcuts()
        self._install_exception_handler()
        self._maybe_check_for_update()

    # ------------------------------------------------------------------
    def _build_ui(self):
        self._build_header()
        self._build_tabs()
        self._build_statusbar()

        for tab in (self.trim_tab, self.url_tab):
            if hasattr(tab, "set_toast"):
                tab.set_toast(self.status_bar)

    # ------------------------------------------------------------------
    def _build_header(self):
        header = ctk.CTkFrame(
            self, height=72, corner_radius=0, fg_color=T.BG_SURFACE,
        )
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        accent = ctk.CTkFrame(header, width=4, fg_color=T.ACCENT, corner_radius=0)
        accent.pack(side="left", fill="y")

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(side="left", fill="both", expand=True, padx=18, pady=10)

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
            text="Clip, trim, and export GIFs or MP4s — from any supported platform.",
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED,
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # Setup button — prereqs checklist
        self.setup_btn = ctk.CTkButton(
            header, text="⚙ Setup",
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT, font=T.font(T.SIZE_SM, "bold"),
            corner_radius=14, width=82, height=28,
            command=self._open_setup_dialog,
        )
        self.setup_btn.place(relx=1.0, rely=0, anchor="ne", x=-104, y=16)

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
        self.tabview.pack(fill="both", expand=True, padx=18, pady=(14, 0))

        self.tabview._segmented_button.configure(
            font=T.font(T.SIZE_LG, "bold"), height=36,
        )

        self.tabview.add("  ✂  Trim Video  ")
        self.tabview.add("  ↓  URL Download  ")
        self.tabview.add("  ⌛  History  ")
        self.tabview.add("  ⚙  Debug  ")

        from videokidnapper.ui.debug_tab import DebugTab
        from videokidnapper.ui.history_tab import HistoryTab
        from videokidnapper.ui.trim_tab import TrimTab
        from videokidnapper.ui.url_tab import UrlTab

        self.debug_tab = DebugTab(self.tabview.tab("  ⚙  Debug  "), self)
        self.debug_tab.pack(fill="both", expand=True)

        self.trim_tab = TrimTab(self.tabview.tab("  ✂  Trim Video  "), self)
        self.trim_tab.pack(fill="both", expand=True)

        self.url_tab = UrlTab(self.tabview.tab("  ↓  URL Download  "), self)
        self.url_tab.pack(fill="both", expand=True)

        self.history_tab = HistoryTab(self.tabview.tab("  ⌛  History  "), self)
        self.history_tab.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    def _build_statusbar(self):
        divider = ctk.CTkFrame(self, height=1, fg_color=T.BORDER, corner_radius=0)
        divider.pack(fill="x", side="bottom", pady=(10, 0))

        self.status_bar = Toast(self)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.show(
            "Ready · Space play · J/L step · I/O set in-out · Ctrl+E export",
            "success",
        )

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def _active_tab(self):
        name = self.tabview.get()
        if "Trim" in name:
            return self.trim_tab
        if "URL" in name:
            return self.url_tab
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
        # Ctrl+V on the URL tab pastes the clipboard into the URL entry.
        # Entries keep native paste because _editing_in_entry short-circuits
        # the dispatcher; this binding only fires when focus is elsewhere.
        self.bind_all("<Control-v>", lambda e: self._shortcut(e, "keyboard_paste_url"))
        self.bind_all("<Control-V>", lambda e: self._shortcut(e, "keyboard_paste_url"))

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
        self._update_link = link
        self.update_chip.configure(text=f"  ↑ Update {tag}  ", width=140)
        self.update_chip.place(relx=1.0, rely=0, anchor="ne", x=-16, y=16)
        if self.status_bar:
            self.status_bar.show(f"Update available: {tag}", "success")

    def _open_update_link(self):
        link = getattr(self, "_update_link", None)
        if link:
            webbrowser.open(link)

    # ------------------------------------------------------------------
    # Setup dialog
    # ------------------------------------------------------------------
    def _open_setup_dialog(self):
        from videokidnapper.ui.setup_dialog import SetupDialog
        SetupDialog(self)

    # ------------------------------------------------------------------
    # Theme toggle
    # ------------------------------------------------------------------
    def _toggle_theme(self, mode):
        T.set_mode(mode)
        if self.status_bar:
            self.status_bar.show(
                f"Theme set to {mode} — restart VideoKidnapper to apply.",
                "info",
            )

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
        """Shown when FFmpeg is missing — funnels the user into Setup."""
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            frame, text="⚠",
            font=T.font(48, "bold"),
            text_color=T.WARN,
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            frame, text="Prerequisites Missing",
            font=T.font(T.SIZE_HERO, "bold"),
            text_color=T.TEXT,
        ).pack(pady=(0, 6))

        ctk.CTkLabel(
            frame,
            text=(
                "VideoKidnapper can install what it needs for you.\n"
                "Open Setup to pick features and install their requirements."
            ),
            font=T.font(T.SIZE_LG),
            text_color=T.TEXT_MUTED,
            justify="center",
        ).pack(pady=(0, 20))

        from videokidnapper.ui.theme import button
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack()

        button(
            btn_row, "  Open Setup", variant="primary",
            width=160, command=self._open_setup_dialog,
        ).pack(side="left", padx=4)

        button(
            btn_row, "Exit", variant="secondary",
            width=100, command=self.destroy,
        ).pack(side="left", padx=4)
