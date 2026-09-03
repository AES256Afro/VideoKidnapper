# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Every theme must be complete, valid, and readable.

Themes are dicts of hex tokens that widgets bake in at construction, so
a missing key is a crash at startup and a low-contrast pair is text
nobody can read — and neither shows up until someone actually picks
that theme. These tests catch both without a display.

Contrast is WCAG 2 relative luminance. Body text is held to 4.5:1;
muted text, accents and danger to 3:1 (the large-text / UI-component
threshold), because those are labels and controls, not paragraphs.
"""

import re

import pytest

from videokidnapper.ui import theme


HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

REQUIRED_KEYS = set(theme._DARK)

# (foreground, background, minimum ratio)
CONTRAST_RULES = [
    ("TEXT",           "BG_BASE",    4.5),
    ("TEXT",           "BG_SURFACE", 4.5),
    ("TEXT",           "BG_RAISED",  4.5),
    ("TEXT_MUTED",     "BG_SURFACE", 3.0),
    ("TEXT_ON_ACCENT", "ACCENT",     3.0),
    ("ACCENT",         "BG_SURFACE", 3.0),
    ("DANGER",         "BG_SURFACE", 3.0),
]


def _luminance(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("key", sorted(theme.PALETTES))
def test_palette_has_every_token(key):
    palette = theme.PALETTES[key]
    missing = REQUIRED_KEYS - set(palette)
    extra = set(palette) - REQUIRED_KEYS
    assert not missing, f"{key} is missing {sorted(missing)}"
    assert not extra, f"{key} has unknown tokens {sorted(extra)}"


@pytest.mark.parametrize("key", sorted(theme.PALETTES))
def test_palette_values_are_valid(key):
    palette = theme.PALETTES[key]
    for token, value in palette.items():
        if token == "CTK_MODE":
            assert value in ("dark", "light"), f"{key}.{token} = {value!r}"
        else:
            assert HEX.match(value), f"{key}.{token} = {value!r} is not #RRGGBB"


@pytest.mark.parametrize("key", sorted(theme.PALETTES))
@pytest.mark.parametrize("fg,bg,minimum", CONTRAST_RULES)
def test_palette_is_readable(key, fg, bg, minimum):
    palette = theme.PALETTES[key]
    ratio = contrast(palette[fg], palette[bg])
    assert ratio >= minimum, (
        f"{key}: {fg} {palette[fg]} on {bg} {palette[bg]} is {ratio:.2f}:1, "
        f"needs {minimum}:1"
    )


def test_every_palette_has_a_label():
    assert set(theme.THEME_LABELS) == set(theme.PALETTES)
    assert all(theme.THEME_LABELS.values())


def test_default_is_a_real_theme():
    assert theme.DEFAULT_THEME in theme.PALETTES
    assert theme.DEFAULT_THEME == "cream"


def test_settings_default_matches_theme_default():
    """Two places declare the default; they must agree or a fresh install
    gets one theme from settings and another from the palette lookup."""
    from videokidnapper.utils import settings

    assert settings._DEFAULTS["theme"] == theme.DEFAULT_THEME


def test_unknown_theme_falls_back_instead_of_raising(monkeypatch):
    """A settings file from a newer build may name a theme this one
    lacks. That must not crash startup."""
    monkeypatch.setattr(theme.settings, "get", lambda k, d=None: "from-the-future")
    assert theme._select_palette() is theme.PALETTES[theme.DEFAULT_THEME]
    assert theme.current_theme() == theme.DEFAULT_THEME


def test_set_theme_rejects_garbage(monkeypatch):
    stored = {}
    monkeypatch.setattr(theme.settings, "set", lambda k, v: stored.__setitem__(k, v))
    theme.set_theme("nonsense")
    assert stored["theme"] == theme.DEFAULT_THEME
    theme.set_theme("fallout")
    assert stored["theme"] == "fallout"


def test_set_mode_alias_still_works(monkeypatch):
    stored = {}
    monkeypatch.setattr(theme.settings, "set", lambda k, v: stored.__setitem__(k, v))
    theme.set_mode("dark")
    assert stored["theme"] == "dark"
