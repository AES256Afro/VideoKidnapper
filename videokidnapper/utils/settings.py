# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Persistent user preferences, stored as JSON next to the temp dir.

The `_version` key tracks the schema; see `_migrate` for the progression.
If the file is missing or malformed we return defaults — never crash the
app over preferences.
"""

import json
from pathlib import Path


_SETTINGS_PATH = Path.home() / ".videokidnapper_settings.json"
_CURRENT_SCHEMA = 2

_DEFAULTS = {
    "_version":         _CURRENT_SCHEMA,
    "quality":          "Medium",
    "format":           "GIF",
    "output_folder":    str(Path.home() / "Downloads"),
    "last_export":      "",
    "cookies_browser":  "",
    "cookies_file":     "",
    "auto_update_check": True,
    "mute_audio":       False,
    "audio_only":       False,
    "speed":            1.0,
    "rotate":           0,
    "crop":             None,
    "theme":            "dark",         # "dark" | "light"
    "aspect_preset":    "Source",        # see ASPECT_PRESETS in config
    "concat_ranges":    False,
    "text_fade":        0.0,             # seconds
    "hw_encoder":       "auto",          # "auto" | "off" | specific encoder
    "history":          [],              # list[dict]: recent exports
}

_HISTORY_MAX = 25


def _migrate(data):
    """Bring the loaded dict up to `_CURRENT_SCHEMA`.

    Migrations should be idempotent and additive — renames or drops need a
    new schema bump so future readers can see the transition.
    """
    version = data.get("_version", 0)
    if version < 1:
        # Schema 1: introduced. Nothing to migrate from 0 (empty or brand-new).
        version = 1
    if version < 2:
        # Schema 2: added theme, aspect_preset, concat_ranges, text_fade,
        # hw_encoder, history.
        data.setdefault("theme", "dark")
        data.setdefault("aspect_preset", "Source")
        data.setdefault("concat_ranges", False)
        data.setdefault("text_fade", 0.0)
        data.setdefault("hw_encoder", "auto")
        data.setdefault("history", [])
        version = 2
    data["_version"] = version
    return data


def _read():
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return _migrate(data)
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write(data):
    try:
        _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass


def get(key, default=None):
    data = _read()
    if key in data:
        return data[key]
    if key in _DEFAULTS:
        return _DEFAULTS[key]
    return default


def set(key, value):   # noqa: A001 — deliberate shadow of builtin
    data = _read()
    data[key] = value
    data["_version"] = _CURRENT_SCHEMA
    _write(data)


def update(mapping):
    data = _read()
    data.update(mapping)
    data["_version"] = _CURRENT_SCHEMA
    _write(data)


def all_settings():
    merged = dict(_DEFAULTS)
    merged.update(_read())
    return merged


def reset():
    try:
        _SETTINGS_PATH.unlink(missing_ok=True)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# History — recent exports
# ---------------------------------------------------------------------------

def add_history_entry(entry):
    """`entry` is a dict; we keep `_HISTORY_MAX` most recent."""
    history = list(get("history", []) or [])
    history.insert(0, entry)
    del history[_HISTORY_MAX:]
    set("history", history)


def get_history():
    return list(get("history", []) or [])


def clear_history():
    set("history", [])
