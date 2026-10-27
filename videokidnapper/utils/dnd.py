# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
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


def parse_dnd_files(data, splitlist=None):
    """Split tkdnd's drop payload into individual file paths.

    The payload is a Tcl list: paths with spaces or braces come wrapped
    in ``{...}`` (braces inside nest), and a bare path can carry
    backslash escapes. Pass the widget's ``tk.splitlist`` to have Tcl
    parse it; the fallback below follows the same rules. The old parser
    closed a path at its first ``}``, so "Take {2}.mp4" arrived as two
    bogus files. Returns a list; empty on empty input.
    """
    if not data:
        return []
    if splitlist is not None:
        try:
            return [str(item) for item in splitlist(data)]
        except Exception:
            pass
    return _split_tcl_list(str(data))


def _split_tcl_list(data):
    paths = []
    i, n = 0, len(data)
    while i < n:
        while i < n and data[i].isspace():
            i += 1
        if i >= n:
            break
        if data[i] == "{":
            # Braced: everything up to the matching brace, taken as is.
            depth, j = 1, i + 1
            while j < n and depth:
                if data[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if data[j] == "{":
                    depth += 1
                elif data[j] == "}":
                    depth -= 1
                j += 1
            paths.append(data[i + 1:j - 1] if depth == 0 else data[i + 1:])
            i = j
        else:
            # Bare word: up to whitespace, with backslash escapes.
            buf = []
            while i < n and not data[i].isspace():
                if data[i] == "\\" and i + 1 < n:
                    buf.append(data[i + 1])
                    i += 2
                else:
                    buf.append(data[i])
                    i += 1
            paths.append("".join(buf))
    return paths
