# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Make the test run safe to start on someone's own computer.

- **A throwaway home folder.** Settings, the autosave and recent projects
  live in the home folder, and a test that builds the real app wrote to
  the developer's own settings file. The folder is set before any
  ``videokidnapper`` module computes its paths.
- **No visible windows.** Several tests need a mapped Tk window to get
  real widget sizes. Every root and toplevel is made fully transparent,
  moved off screen and kept off the taskbar the moment it exists, so a
  test run does not flash windows over whatever the developer is doing.
"""

import os
import sys
import tempfile
import tkinter

_HOME = tempfile.mkdtemp(prefix="videokidnapper-tests-home-")
os.environ["HOME"] = _HOME
os.environ["USERPROFILE"] = _HOME


def _hide(window):
    # Raw Tcl, not window.attributes(): CustomTkinter overrides those and
    # they fail before its own __init__ has finished.
    try:
        window.tk.call("wm", "attributes", window._w, "-alpha", 0.0)
        if sys.platform == "win32":
            window.tk.call("wm", "attributes", window._w, "-toolwindow", 1)
        window.tk.call("wm", "geometry", window._w, "+-4000+-4000")
    except tkinter.TclError:
        pass


def _hidden(init):
    def wrapper(self, *args, **kwargs):
        init(self, *args, **kwargs)
        _hide(self)
    return wrapper


tkinter.Tk.__init__ = _hidden(tkinter.Tk.__init__)
tkinter.Toplevel.__init__ = _hidden(tkinter.Toplevel.__init__)
