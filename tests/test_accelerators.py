# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Accelerators must work on macOS, not just Windows and Linux.

Every app accelerator was bound only as ``<Control-...>`` until 1.8.2,
so on macOS — the one platform shipping a signed DMG — ⌘O, ⌘S and ⌘E
did nothing at all, while the shortcuts overlay advertised "Ctrl+O".

The undo/redo pair is the subtle part: some Tk builds deliver
Ctrl+Shift+Z as ``<Control-Z>`` rather than ``<Control-Shift-Z>``, so
the bare upper-case form has to mean *redo*. Case-folding it in with
undo (the obvious refactor) silently breaks redo.
"""


import pytest

from videokidnapper.ui import shortcuts_dialog


def _app_class():
    from videokidnapper import app as app_module

    for name in dir(app_module):
        obj = getattr(app_module, name)
        if isinstance(obj, type) and hasattr(obj, "_bind_accel"):
            return obj
    raise AssertionError("no app class exposing _bind_accel")


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


@pytest.mark.parametrize("body", ["s", "o", "e", "v", "y"])
def test_every_accelerator_binds_command_and_control(body):
    bound = _bind(body)
    assert f"<Command-{body}>" in bound, "macOS would have no ⌘ shortcut"
    assert f"<Control-{body}>" in bound, "Windows/Linux must keep Ctrl"


@pytest.mark.parametrize("body", ["s", "o", "v"])
def test_both_letter_cases_are_bound(body):
    """Tk treats <Control-s> and <Control-S> as different events."""
    bound = _bind(body)
    assert f"<Control-{body.upper()}>" in bound
    assert f"<Command-{body.upper()}>" in bound


def test_shift_prefix_is_preserved_and_not_case_folded():
    bound = _bind("Shift-s")
    assert "<Control-Shift-s>" in bound
    assert "<Control-Shift-S>" in bound
    assert "<Command-Shift-s>" in bound
    # The modifier itself must not be lower-cased into "<Control-shift-s>".
    assert not any("shift-" in seq for seq in bound)


def test_undo_does_not_capture_the_redo_sequence():
    """The regression guard. <Control-Z> is Ctrl+Shift+Z on some Tk
    builds, so undo must not claim it."""
    undo = _bind("z", "UNDO", both_cases=False)
    assert "<Control-z>" in undo and "<Command-z>" in undo
    assert "<Control-Z>" not in undo, "undo would swallow redo"
    assert "<Command-Z>" not in undo


def test_redo_owns_the_upper_case_form():
    redo = _bind("Z", "REDO", both_cases=False)
    assert "<Control-Z>" in redo and "<Command-Z>" in redo
    assert "<Control-z>" not in redo, "redo would swallow undo"


def test_accel_label_uses_mac_glyphs_on_darwin(monkeypatch):
    monkeypatch.setattr(shortcuts_dialog.sys, "platform", "darwin")
    assert shortcuts_dialog.accel_label("Ctrl+S") == "⌘S"
    assert shortcuts_dialog.accel_label("Ctrl+Shift+S") == "⌘⇧S"
    # Non-modifier labels are left alone.
    assert shortcuts_dialog.accel_label("Space") == "Space"
    assert shortcuts_dialog.accel_label("?") == "?"


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_accel_label_unchanged_off_darwin(monkeypatch, platform):
    monkeypatch.setattr(shortcuts_dialog.sys, "platform", platform)
    assert shortcuts_dialog.accel_label("Ctrl+Shift+S") == "Ctrl+Shift+S"


def test_documented_shortcuts_are_all_labelled():
    """Every row in the overlay renders through accel_label, so none of
    them may crash or come back empty."""
    for group in shortcuts_dialog.SHORTCUTS.values():
        for sc in group:
            assert shortcuts_dialog.accel_label(sc.keys)
            assert sc.description
