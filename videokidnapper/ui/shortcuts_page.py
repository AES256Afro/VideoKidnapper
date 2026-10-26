# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Keyboard shortcuts page.

Opened with the ``?`` key, the header's ? button or the settings menu,
and closed the same way, with Esc, or with Back. It is a page inside the
main window; it used to be a window of its own. The shortcut registry is
the single source of truth for which keybinds the app advertises — the
actual bindings live in ``app.py`` alongside their dispatch targets, but
this module is what users see when they ask "what can I press?".

Keep the two lists aligned: every ``bind_all`` in ``App._bind_keyboard_shortcuts``
should have a matching ``SHORTCUTS`` entry here, and vice versa, so the
page never lies about what the app supports.
"""

from __future__ import annotations

from typing import NamedTuple

import sys

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.studio import controls as C
from videokidnapper.ui.studio.chrome import Page


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
        Shortcut("Q",               "Save the selection as a range"),
    ],
    "Edit": [
        Shortcut("Ctrl+Z",          "Undo"),
        Shortcut("Ctrl+Y",          "Redo"),
        Shortcut("Ctrl+Shift+Z",    "Redo"),
    ],
    "File & Export": [
        Shortcut("Ctrl+O",          "Open video file"),
        Shortcut("Ctrl+Shift+O",    "Open project"),
        Shortcut("Ctrl+S",          "Save project"),
        Shortcut("Ctrl+Shift+S",    "Save project as"),
        Shortcut("Ctrl+E",          "Export current trim"),
        Shortcut("Ctrl+V",          "Paste — a video/GIF link opens Import from anywhere; a clipboard image becomes an overlay in Edit"),
    ],
    "Help": [
        Shortcut("?",               "Show or hide this page"),
        Shortcut("Esc",             "Go back to where you were"),
    ],
}


def accel_label(keys: str) -> str:
    """Render a shortcut label in the host platform's own vocabulary.

    The table above is written in Windows/Linux terms because that is
    where most users are. macOS spells the same accelerators ⌘ and ⇧,
    and as of 1.8.2 the app binds Command there — so showing "Ctrl+S"
    on a Mac would now be describing a key combination that is not the
    documented one.
    """
    if sys.platform != "darwin":
        return keys
    return keys.replace("Ctrl+Shift+", "⌘⇧").replace("Ctrl+", "⌘")


def split_columns(groups):
    """Split ``(title, shortcuts)`` groups into two columns, keeping order.

    The split point is the one that leaves the columns closest in rows,
    so the page fits the window without scrolling and still reads top
    to bottom, left to right.
    """
    groups = list(groups)
    if len(groups) < 2:
        return [groups, []]
    sizes = [len(shortcuts) + 1 for _title, shortcuts in groups]  # +1 for the heading
    total = sum(sizes)
    best = min(range(1, len(groups)),
               key=lambda k: abs(total - 2 * sum(sizes[:k])))
    return [groups[:best], groups[best:]]


class ShortcutsPage(Page):
    """Every advertised key binding, on one screen."""

    def __init__(self, master, on_back, **kwargs):
        super().__init__(master, "Keyboard shortcuts", on_back, **kwargs)
        ctk.CTkLabel(
            self.bar_actions, text="Press ? or Esc to go back",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(side="right")

        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=28, pady=18)
        for index, column in enumerate(split_columns(SHORTCUTS.items())):
            grid.grid_columnconfigure(index, weight=1, uniform="shortcuts")
            card = ctk.CTkFrame(grid, fg_color=T.BG_SURFACE, corner_radius=T.RADIUS_LG,
                                border_width=1, border_color=T.BORDER)
            card.grid(row=0, column=index, sticky="new", padx=(0, 16) if index == 0 else 0)
            for title, shortcuts in column:
                self._render_group(card, title, shortcuts)
            ctk.CTkFrame(card, height=10, fg_color="transparent").pack()

        C.hint(
            grid,
            "Shortcuts are ignored while you type in a text box, so a "
            "caption can still have J, L or ? in it.",
            wrap=600,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def _render_group(self, parent, title, shortcuts):
        C.section_label(parent, title).pack(fill="x", padx=18, pady=(10, 2))
        for shortcut in shortcuts:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=2)

            ctk.CTkLabel(
                row, text=f" {accel_label(shortcut.keys)} ",
                font=T.font(T.SIZE_SM, "bold", mono=True),
                text_color=T.TEXT,
                fg_color=T.BG_RAISED,
                corner_radius=T.RADIUS_SM,
                width=120, height=24, anchor="center",
            ).pack(side="left", anchor="n", padx=(0, 12))

            ctk.CTkLabel(
                row, text=shortcut.description,
                font=T.font(T.SIZE_MD),
                text_color=T.TEXT_MUTED,
                anchor="w", justify="left", height=24, wraplength=300,
            ).pack(side="left", fill="x", expand=True)
