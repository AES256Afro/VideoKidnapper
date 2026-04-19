# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Keyboard-shortcuts help overlay.

Opens via the ``?`` key or the header button. The shortcut registry is
the single source of truth for which keybinds the app advertises — the
actual bindings live in ``app.py`` alongside their dispatch targets, but
this module is what users see when they ask "what can I press?".

Keep the two lists aligned: every ``bind_all`` in ``App._bind_keyboard_shortcuts``
should have a matching ``SHORTCUTS`` entry here, and vice versa, so the
overlay never lies about what the app supports.
"""

from __future__ import annotations

from typing import NamedTuple

import customtkinter as ctk

from videokidnapper.ui import theme as T


class Shortcut(NamedTuple):
    keys: str         # Visible label, e.g. "Ctrl+Shift+Z"
    description: str  # One-line plain-English action


SHORTCUTS: dict[str, list[Shortcut]] = {
    "Playback": [
        Shortcut("Space",           "Play / pause"),
        Shortcut("K",               "Play / pause"),
        Shortcut("J",               "Nudge playhead back 1 second"),
        Shortcut("L",               "Nudge playhead forward 1 second"),
    ],
    "Trim": [
        Shortcut("I",               "Set in-point to current playhead"),
        Shortcut("O",               "Set out-point to current playhead"),
    ],
    "Edit": [
        Shortcut("Ctrl+Z",          "Undo"),
        Shortcut("Ctrl+Y",          "Redo"),
        Shortcut("Ctrl+Shift+Z",    "Redo"),
    ],
    "File & Export": [
        Shortcut("Ctrl+O",          "Open video file"),
        Shortcut("Ctrl+E",          "Export current trim"),
        Shortcut("Ctrl+V",          "Paste — URL into URL tab, clipboard image as overlay on Trim tab"),
    ],
    "Help": [
        Shortcut("?",               "Show this overlay"),
        Shortcut("Shift+/",         "Show this overlay"),
        Shortcut("Esc",             "Close this overlay"),
    ],
}


class ShortcutsDialog(ctk.CTkToplevel):
    """Modal "cheat sheet" for every advertised key binding."""

    _W = 520
    _H = 560

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Keyboard Shortcuts")
        self.geometry(f"{self._W}x{self._H}")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.configure(fg_color=T.BG_BASE)

        self.update_idletasks()
        pw = master.winfo_toplevel()
        x = pw.winfo_x() + (pw.winfo_width() - self._W) // 2
        y = pw.winfo_y() + (pw.winfo_height() - self._H) // 2
        self.geometry(f"+{x}+{y}")

        self._build_ui()

        # Esc and `?` both dismiss — if the user hits `?` a second time
        # it feels like a toggle rather than opening a nested dialog.
        self.bind("<Escape>",    lambda _e: self._close())
        self.bind("<Key-question>", lambda _e: self._close())
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self) -> None:
        card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 6))

        ctk.CTkLabel(
            header, text="⌨",
            font=T.font(T.SIZE_HERO, "bold"),
            text_color=T.ACCENT,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            header, text="Keyboard Shortcuts",
            font=T.font(T.SIZE_HERO, "bold"),
            text_color=T.TEXT, anchor="w",
        ).pack(side="left")

        ctk.CTkLabel(
            card,
            text="Bindings ignore typing into text entries — so you can still edit captions without hitting J/L.",
            font=T.font(T.SIZE_XS),
            text_color=T.TEXT_DIM,
            wraplength=self._W - 60,
            justify="left",
        ).pack(fill="x", padx=20, pady=(0, 10))

        scroll = ctk.CTkScrollableFrame(
            card, fg_color="transparent",
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        for category, shortcuts in SHORTCUTS.items():
            self._render_category(scroll, category, shortcuts)

        close_btn = ctk.CTkButton(
            card, text="Close  (Esc)",
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT,
            font=T.font(T.SIZE_MD, "bold"),
            corner_radius=T.RADIUS_SM,
            width=140, height=34,
            command=self._close,
        )
        close_btn.pack(side="bottom", pady=(4, 16))

    def _render_category(self, parent, title: str, shortcuts: list[Shortcut]) -> None:
        ctk.CTkLabel(
            parent, text=title,
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.ACCENT,
            anchor="w",
        ).pack(fill="x", padx=8, pady=(10, 4))

        for shortcut in shortcuts:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)

            kbd = ctk.CTkLabel(
                row, text=f" {shortcut.keys} ",
                font=T.font(T.SIZE_SM, "bold", mono=True),
                text_color=T.TEXT,
                fg_color=T.BG_RAISED,
                corner_radius=T.RADIUS_SM,
                width=140, anchor="center",
            )
            kbd.pack(side="left", padx=(0, 12))

            ctk.CTkLabel(
                row, text=shortcut.description,
                font=T.font(T.SIZE_MD),
                text_color=T.TEXT_MUTED,
                anchor="w",
            ).pack(side="left", fill="x", expand=True)

    def _close(self) -> None:
        self.grab_release()
        self.destroy()
