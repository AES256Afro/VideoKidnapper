# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Icon glyphs for the Studio chrome.

Windows ships two icon fonts with the same codepoints: Segoe Fluent Icons
(Windows 11) and Segoe MDL2 Assets (Windows 10+). We use whichever is
installed; elsewhere each icon falls back to a plain Unicode symbol in
the UI font, so macOS and Linux builds still get readable buttons.
"""

import tkinter.font as tkfont

import customtkinter as ctk

from videokidnapper.ui import theme as T


# name: (icon-font codepoint, plain fallback)
ICONS = {
    "play":       ("", "▶"),
    "pause":      ("", "❚❚"),
    "stop":       ("", "■"),
    "to_start":   ("", "⏮"),
    "to_end":     ("", "⏭"),
    "back":       ("", "‹"),
    "forward":    ("", "›"),
    "undo":       ("", "↶"),
    "redo":       ("", "↷"),
    "settings":   ("", "⚙"),
    "help":       ("", "?"),
    "folder":     ("", "▤"),
    "link":       ("", "⛓"),
    "download":   ("", "↓"),
    "upload":     ("", "↑"),
    "add":        ("", "+"),
    "close":      ("", "✕"),
    "delete":     ("", "✕"),
    "copy":       ("", "⧉"),
    "crop":       ("", "⌗"),
    "text":       ("", "T"),
    "image":      ("", "▣"),
    "captions":   ("", "CC"),
    "volume":     ("", "♪"),
    "mute":       ("", "♪̸"),
    "screen":     ("", "▭"),
    "color":      ("", "◐"),
    "pointer":    ("", "↖"),
    "trim":       ("", "✂"),
    "zoom":       ("", "+"),
    "history":    ("", "◷"),
    "package":    ("", "↑"),
    "check":      ("", "✓"),
    "chevron":    ("", "▾"),
    "open_new":   ("", "↗"),
    "more":       ("", "…"),
    "bug":        ("", "!"),
    "info":       ("", "i"),
    "warning":    ("", "!"),
}

_ICON_FAMILY = None
_RESOLVED = False


def _icon_family():
    global _ICON_FAMILY, _RESOLVED
    if not _RESOLVED:
        try:
            families = set(tkfont.families())
        except Exception:
            families = set()
        for name in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
            if name in families:
                _ICON_FAMILY = name
                break
        _RESOLVED = True
    return _ICON_FAMILY


def glyph(name):
    """The character to draw for icon ``name`` on this machine."""
    code, fallback = ICONS.get(name, ("", "?"))
    return code if _icon_family() else fallback


def icon_font(size=14):
    family = _icon_family()
    if family:
        return ctk.CTkFont(family=family, size=size)
    return T.font(size)


# Where icon buttons say what they do while the mouse is over them: the
# status bar (see App). ``handler(text)`` shows it, ``handler(None)`` puts
# back what was there. Not a tooltip window; the app keeps to one window.
_hint_handler = None


def set_hint_handler(handler):
    global _hint_handler
    _hint_handler = handler


def _hint(text):
    if _hint_handler is not None:
        try:
            _hint_handler(text)
        except Exception:
            pass


def icon_button(parent, name, command=None, size=32, icon_size=14,
                variant="ghost", hint=None, **kwargs):
    """A square, icon-only button.

    ``hint`` says in words what it does, in the status bar on hover; a
    bare glyph (the same arrow collapses a panel, steps a second and
    picks the next caption) didn't say enough.
    """
    styles = {
        "ghost": dict(fg_color="transparent", hover_color=T.BG_HOVER,
                      text_color=T.TEXT_MUTED),
        "solid": dict(fg_color=T.TEXT, hover_color=T.TEXT_MUTED,
                      text_color=T.BG_SURFACE),
        "secondary": dict(fg_color=T.BG_SURFACE, hover_color=T.BG_HOVER,
                          text_color=T.TEXT, border_width=1,
                          border_color=T.BORDER_STRONG),
        "accent": dict(fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
                       text_color=T.TEXT_ON_ACCENT),
    }
    style = dict(styles.get(variant, styles["ghost"]))
    style.update(kwargs)
    style.setdefault("corner_radius", T.RADIUS_SM)
    btn = ctk.CTkButton(
        parent, text=glyph(name), width=size, height=size,
        font=icon_font(icon_size), command=command, **style,
    )
    if hint:
        btn.bind("<Enter>", lambda _e: _hint(hint), add="+")
        btn.bind("<Leave>", lambda _e: _hint(None), add="+")
    return btn
