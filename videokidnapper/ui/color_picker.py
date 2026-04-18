# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Color picker dialog — blocks until the user picks or cancels.

Wraps ``tkinter.colorchooser`` which returns ``(rgb, hex)``. We only need
the hex, but we validate and fall back to the caller's current color on
cancel so the callsite can just replace unconditionally.
"""

from tkinter import colorchooser


def ask_color(parent, initial="#FFFFFF", title="Choose color"):
    """Return a hex color string like '#1A73E8', or None if cancelled."""
    try:
        result = colorchooser.askcolor(initialcolor=initial, title=title,
                                       parent=parent)
    except Exception:
        return None
    if not result or result[1] is None:
        return None
    return result[1].upper()
