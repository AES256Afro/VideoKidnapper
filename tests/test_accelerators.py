# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Accelerators must work on macOS, and never fire from plain typing.

Every app accelerator was bound only as ``<Control-...>`` until 1.8.2,
so on macOS — the one platform shipping a signed DMG — ⌘O, ⌘S and ⌘E
did nothing at all, while the shortcuts overlay advertised "Ctrl+O".

The fix then bound ``<Command-...>`` on every platform, which broke
Windows: Tk's Command is the Mod1 modifier, and Tk on Windows sets Mod1
whenever Num Lock is on. Typing a capital S in a caption opened Save As,
"s" saved, and "o" opened a file instead of marking the out point.
Command is now bound on macOS only.

The undo/redo pair is the subtle part: some Tk builds deliver
Ctrl+Shift+Z as ``<Control-Z>`` rather than ``<Control-Shift-Z>``, so
the bare upper-case form has to mean *redo*. Case-folding it in with
undo (the obvious refactor) silently breaks redo.
"""


import sys

import pytest

from videokidnapper.ui import shortcuts_page


def _find_app_class():
    from videokidnapper import app as app_module

    for name in dir(app_module):
        obj = getattr(app_module, name)
        if isinstance(obj, type) and hasattr(obj, "_bind_accel"):
            return obj
    raise AssertionError("no app class exposing _bind_accel")


# Imported up front: the tests below fake sys.platform, and importing the
# app (and urllib with it) while it claims "darwin" pulls in macOS-only
# modules. _bind_accel reads sys.platform when called, not at import.
_APP = _find_app_class()


def _app_class():
    return _APP


class _Recorder:
    """Stands in for the Tk root; records what would be bound."""

    def __init__(self):
        self.bound = {}

    def bind_all(self, sequence, handler):
        self.bound[sequence] = handler


def _bind(body, handler="H", **kw):
    rec = _Recorder()
    _app_class()._bind_accel(rec, body, handler, **kw)
    return rec.bound


@pytest.fixture
def mac(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")


@pytest.mark.parametrize("body", ["s", "o", "e", "v", "y"])
def test_every_accelerator_binds_command_and_control_on_macos(mac, body):
    bound = _bind(body)
    assert f"<Command-{body}>" in bound, "macOS would have no ⌘ shortcut"
    assert f"<Control-{body}>" in bound, "Ctrl stays live on macOS too"


@pytest.mark.parametrize("platform", ["win32", "linux"])
@pytest.mark.parametrize("body", ["s", "Shift-s", "o", "e", "v", "y", "z", "Z"])
def test_no_command_binding_off_macos(monkeypatch, platform, body):
    """Command is Mod1: Num Lock on Windows, usually Alt on X11."""
    monkeypatch.setattr(sys, "platform", platform)
    bound = _bind(body, both_cases=body not in ("z", "Z"))
    assert bound, "the Ctrl binding itself must remain"
    assert all(seq.startswith("<Control-") for seq in bound), sorted(bound)


@pytest.mark.parametrize("body", ["s", "o", "v"])
def test_both_letter_cases_are_bound(mac, body):
    """Tk treats <Control-s> and <Control-S> as different events."""
    bound = _bind(body)
    assert f"<Control-{body.upper()}>" in bound
    assert f"<Command-{body.upper()}>" in bound


def test_shift_prefix_is_preserved_and_not_case_folded(mac):
    bound = _bind("Shift-s")
    assert "<Control-Shift-s>" in bound
    assert "<Control-Shift-S>" in bound
    assert "<Command-Shift-s>" in bound
    # The modifier itself must not be lower-cased into "<Control-shift-s>".
    assert not any("shift-" in seq for seq in bound)


def test_undo_does_not_capture_the_redo_sequence(mac):
    """The regression guard. <Control-Z> is Ctrl+Shift+Z on some Tk
    builds, so undo must not claim it."""
    undo = _bind("z", "UNDO", both_cases=False)
    assert "<Control-z>" in undo and "<Command-z>" in undo
    assert "<Control-Z>" not in undo, "undo would swallow redo"
    assert "<Command-Z>" not in undo


def test_redo_owns_the_upper_case_form(mac):
    redo = _bind("Z", "REDO", both_cases=False)
    assert "<Control-Z>" in redo and "<Command-Z>" in redo
    assert "<Control-z>" not in redo, "redo would swallow undo"


def test_num_lock_typing_does_not_fire_accelerators(monkeypatch):
    """The reported bug, replayed through real Tk events.

    With Num Lock on, Tk on Windows adds Mod1 to every key event. Typing
    S, s and o into a text field must not reach Save As, Save or Open;
    Ctrl+S must still save.
    """
    tk = pytest.importorskip("tkinter")
    monkeypatch.setattr(sys, "platform", "win32")
    try:
        root = tk.Tk()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no display: {exc}")
    fired = []
    try:
        app = _app_class()
        app._bind_accel(root, "s", lambda e: fired.append("save") or "break")
        app._bind_accel(root, "Shift-s", lambda e: fired.append("save-as") or "break")
        app._bind_accel(root, "o", lambda e: fired.append("open") or "break")
        text = tk.Text(root)
        text.pack()
        root.update()
        text.focus_force()
        root.update()
        shift, control, num_lock = 0x1, 0x4, 0x8
        for keysym, state in (("S", shift | num_lock), ("s", num_lock), ("o", num_lock)):
            text.event_generate("<KeyPress>", keysym=keysym, state=state, when="now")
        root.update()
        assert fired == [], f"plain typing fired {fired}"
        text.event_generate("<KeyPress>", keysym="s", state=control | num_lock, when="now")
        root.update()
        assert fired == ["save"], "Ctrl+S must still save with Num Lock on"
    finally:
        root.destroy()


def test_accel_label_uses_mac_glyphs_on_darwin(monkeypatch):
    monkeypatch.setattr(shortcuts_page.sys, "platform", "darwin")
    assert shortcuts_page.accel_label("Ctrl+S") == "⌘S"
    assert shortcuts_page.accel_label("Ctrl+Shift+S") == "⌘⇧S"
    # Non-modifier labels are left alone.
    assert shortcuts_page.accel_label("Space") == "Space"
    assert shortcuts_page.accel_label("?") == "?"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_accel_label_unchanged_off_darwin(monkeypatch, platform):
    monkeypatch.setattr(shortcuts_page.sys, "platform", platform)
    assert shortcuts_page.accel_label("Ctrl+Shift+S") == "Ctrl+Shift+S"


def test_documented_shortcuts_are_all_labelled():
    """Every row on the shortcuts page renders through accel_label, so
    none of them may crash or come back empty."""
    for group in shortcuts_page.SHORTCUTS.values():
        for sc in group:
            assert shortcuts_page.accel_label(sc.keys)
            assert sc.description
