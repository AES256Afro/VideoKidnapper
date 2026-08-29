# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Shortcut registry contract.

The overlay advertises what the user can press. These tests guard against
the two ways that contract rots:

1. **Registry drift** — an entry in ``SHORTCUTS`` gets renamed or loses
   its description (easy to do during a reformat).
2. **Advertise-but-unbound** — every key advertised here must actually
   map to a ``bind_all`` in ``App._bind_keyboard_shortcuts``. We check
   this by string-matching the source so the test doesn't need a Tk
   root to run in CI.
"""

from __future__ import annotations

from pathlib import Path

from videokidnapper.ui.shortcuts_dialog import SHORTCUTS, Shortcut


def test_registry_categories_are_non_empty():
    assert SHORTCUTS, "registry must not be empty"
    for category, shortcuts in SHORTCUTS.items():
        assert isinstance(category, str) and category.strip(), category
        assert shortcuts, f"{category!r} has no shortcuts"


def test_every_entry_has_keys_and_description():
    for category, shortcuts in SHORTCUTS.items():
        for shortcut in shortcuts:
            assert isinstance(shortcut, Shortcut), (category, shortcut)
            assert shortcut.keys.strip(), (category, shortcut)
            assert shortcut.description.strip(), (category, shortcut)


def test_keys_have_no_trailing_whitespace():
    # Trailing whitespace inside the key-chip label makes the rounded
    # background look lopsided. Catch it before it ships.
    for shortcuts in SHORTCUTS.values():
        for shortcut in shortcuts:
            assert shortcut.keys == shortcut.keys.strip()


# ---------------------------------------------------------------------------
# Cross-reference against app.py's actual bind_all list. We read the source
# to avoid standing up a Tk root just to enumerate bindings.

_APP_SOURCE = (
    Path(__file__).resolve().parent.parent
    / "videokidnapper" / "app.py"
).read_text(encoding="utf-8")


class _BindRecorder:
    """Stands in for the Tk root and records every sequence bound.

    This used to be a regex over app.py looking for ``bind_all("<...>")``
    string literals. Since 1.8.2 the accelerators are built by
    ``_bind_accel`` (so each one binds under Control *and* Command for
    macOS), and a computed sequence is invisible to a source grep — the
    old test passed or failed on how the bindings were spelled rather
    than on what actually got bound. Running the real method against a
    recorder checks the thing we care about.
    """

    def __init__(self):
        self.bound: set[str] = set()

    def bind_all(self, sequence, handler):
        self.bound.add(sequence.strip("<>"))

    def __getattr__(self, name):
        # Handlers are only *referenced* while binding, never called,
        # so any callable will do.
        return lambda *args, **kwargs: None


def _bound_keysyms() -> set[str]:
    """Every keysym the app actually binds at startup."""
    from videokidnapper import app as app_module

    app_cls = next(
        obj for obj in vars(app_module).values()
        if isinstance(obj, type) and hasattr(obj, "_bind_keyboard_shortcuts")
    )
    recorder = _BindRecorder()
    # Bind the real methods to the recorder; everything else falls
    # through __getattr__.
    recorder._bind_accel = app_cls._bind_accel.__get__(recorder)
    app_cls._bind_keyboard_shortcuts(recorder)
    return recorder.bound


# Mapping from a human label ("Ctrl+E") to the Tk keysym it must be
# bound to ("Control-e"). Keep this conservative: only the advertised
# combos need to round-trip, not every possible Tk sugar.
_LABEL_TO_KEYSYM = {
    "Space":         "space",
    "K":             "Key-k",
    "J":             "Key-j",
    "L":             "Key-l",
    "I":             "Key-i",
    "O":             "Key-o",
    "Ctrl+Z":        "Control-z",
    "Ctrl+Y":        "Control-y",
    "Ctrl+Shift+Z":  "Control-Shift-Z",
    "Ctrl+O":        "Control-o",
    "Ctrl+Shift+O":  "Control-Shift-o",
    "Ctrl+S":        "Control-s",
    "Ctrl+Shift+S":  "Control-Shift-s",
    "Ctrl+E":        "Control-e",
    "Ctrl+V":        "Control-v",
    "?":             "Key-question",
    "Shift+/":       "Key-question",  # same physical key on US layouts
}


def test_every_advertised_key_is_actually_bound():
    bound = _bound_keysyms()
    unadvertised_ok = {"Esc"}  # handled locally by the dialog, not globally
    for shortcuts in SHORTCUTS.values():
        for shortcut in shortcuts:
            if shortcut.keys in unadvertised_ok:
                continue
            keysym = _LABEL_TO_KEYSYM.get(shortcut.keys)
            assert keysym is not None, (
                f"{shortcut.keys!r} advertised but missing from "
                f"_LABEL_TO_KEYSYM in this test — either add it or "
                f"remove the shortcut from the registry."
            )
            assert keysym in bound, (
                f"{shortcut.keys!r} advertised in SHORTCUTS but no "
                f"bind_all(<{keysym}>) exists in app.py"
            )
