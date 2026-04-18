# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Enable drag-and-drop file support when tkinterdnd2 is installed.

We do NOT monkey-patch ``tkinter.Tk`` with ``TkinterDnD.Tk`` — that causes
infinite recursion, because TkinterDnD.Tk's ``__init__`` calls
``tkinter.Tk.__init__``.

Instead we:

  1. Ask tkinterdnd2 to load the tkdnd Tcl extension into the live
     interpreter via its ``_require`` helper.
  2. Copy the DnD methods from ``TkinterDnD.DnDWrapper`` onto
     ``tk.Canvas`` / ``tk.Widget`` so widgets gain
     ``drop_target_register`` / ``dnd_bind`` at runtime.

Must be called *before* any widget that wants DnD is constructed, because
those widgets call ``drop_target_register`` during ``__init__``.
"""

import tkinter as tk


def enable_dnd_for(root):
    try:
        from tkinterdnd2 import TkinterDnD
    except ImportError:
        return False

    try:
        TkinterDnD._require(root)
    except Exception:
        return False

    wrapper = TkinterDnD.DnDWrapper
    for cls in (tk.Widget, tk.Canvas, tk.Frame, tk.Toplevel, tk.Tk):
        for name in (
            "drop_target_register", "drop_target_unregister",
            "drag_source_register", "drag_source_unregister",
            "dnd_bind",
        ):
            impl = getattr(wrapper, name, None)
            if impl and not hasattr(cls, name):
                setattr(cls, name, impl)
    return True


def parse_dnd_files(data):
    """Split tkdnd's drop payload into individual file paths.

    Paths containing spaces come back wrapped in ``{...}``; bare paths are
    separated by spaces. Returns a list; empty on empty input.
    """
    if not data:
        return []
    paths = []
    buf = ""
    in_brace = False
    for ch in data:
        if ch == "{" and not in_brace:
            in_brace = True
        elif ch == "}" and in_brace:
            in_brace = False
            if buf:
                paths.append(buf)
                buf = ""
        elif ch == " " and not in_brace:
            if buf:
                paths.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        paths.append(buf)
    return paths
