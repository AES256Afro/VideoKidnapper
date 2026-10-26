# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Every console program the app starts must start without a window.

The Windows build is windowed, so a console program started without
CREATE_NO_WINDOW gets a console window of its own. Playback's sound
decoder did that, and a terminal popped up over the editor on every
Play. This walks the source for process launches and fails on any that
neither passes ``creationflags`` nor spreads a kwargs helper such as
``_run_kwargs()``.
"""

import ast
from pathlib import Path

import pytest


PACKAGE = Path(__file__).resolve().parent.parent / "videokidnapper"
LAUNCHERS = {"Popen", "run", "call", "check_call", "check_output"}
# GUI programs (no console to show) and macOS/Linux-only tools.
WINDOWLESS = {"explorer", "open", "xdg-open", "osascript", "pbcopy", "xclip"}
# Launches that start a GUI program held in a variable.
ALLOWED = {
    ("app.py", "_relaunch"),            # the app itself, windowed
    ("prereq_check.py", "open_admin_terminal"),  # Linux terminal emulators
}


def _launches():
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(func):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr in LAUNCHERS
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"):
                    yield path, func.name, node


def _program(call):
    if call.args and isinstance(call.args[0], ast.List) and call.args[0].elts:
        first = call.args[0].elts[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def test_the_scan_finds_launches():
    assert sum(1 for _ in _launches()) > 20


@pytest.mark.parametrize(
    "path,func,call",
    [pytest.param(p, f, c, id=f"{p.name}:{c.lineno}") for p, f, c in _launches()],
)
def test_console_programs_start_hidden(path, func, call):
    if _program(call) in WINDOWLESS or (path.name, func) in ALLOWED:
        return
    hidden = any(kw.arg == "creationflags" or kw.arg is None for kw in call.keywords)
    assert hidden, (
        f"{path.name}:{call.lineno} in {func}() starts a process without "
        "creationflags=CREATE_NO_WINDOW; on Windows it opens a console window"
    )
