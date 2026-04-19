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

import re
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


def _bound_keysyms() -> set[str]:
    """Extract the bracketed keysym from every ``bind_all`` call."""
    return set(re.findall(r'bind_all\("<([^"]+)>"', _APP_SOURCE))


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
