# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
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


def icon_button(parent, name, command=None, size=32, icon_size=14,
                variant="ghost", **kwargs):
    """A square, icon-only button. Callers pass a tooltip-like ``text``
    nowhere — the glyph is the label, so keep icon choices obvious."""
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
    return ctk.CTkButton(
        parent, text=glyph(name), width=size, height=size,
        font=icon_font(icon_size), command=command, **style,
    )
