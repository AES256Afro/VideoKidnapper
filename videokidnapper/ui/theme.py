# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Centralized design tokens for VideoKidnapper.

Tokens are selected once at import time from the palette named by
``settings.get("theme")`` — see ``PALETTES``. Changing the theme requires a restart
because ctk widgets bake their colors at construction — reconfiguring them
live is brittle and not worth the complexity.
"""

import customtkinter as ctk

from videokidnapper.utils import settings


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

_DARK = {
    "BG_BASE":      "#0D1117",
    "BG_SURFACE":   "#161B22",
    "BG_RAISED":    "#1F262E",
    "BG_HOVER":     "#2A313A",
    "BG_ACTIVE":    "#353D47",
    "BORDER":       "#30363D",
    "BORDER_STRONG":"#3D444D",
    "ACCENT":       "#4F8CFF",
    "ACCENT_HOVER": "#3A75E8",
    "ACCENT_ACTIVE":"#2860D0",
    "ACCENT_GLOW":  "#6FA4FF",
    "SUCCESS":      "#3FB950",
    "WARN":         "#D29922",
    "DANGER":       "#F85149",
    "DANGER_HOVER": "#DA3633",
    "TEXT":         "#E6EDF3",
    "TEXT_MUTED":   "#8B949E",
    "TEXT_DIM":     "#6E7681",
    "TEXT_ON_ACCENT": "#FFFFFF",
    "CTK_MODE":     "dark",
}

_LIGHT = {
    "BG_BASE":      "#F4F7FB",
    "BG_SURFACE":   "#FFFFFF",
    "BG_RAISED":    "#EDF1F7",
    "BG_HOVER":     "#E3E9F2",
    "BG_ACTIVE":    "#D6DEEA",
    "BORDER":       "#D0D7DE",
    "BORDER_STRONG":"#ABB7C3",
    "ACCENT":       "#1F6FEB",
    "ACCENT_HOVER": "#1859C4",
    "ACCENT_ACTIVE":"#124499",
    "ACCENT_GLOW":  "#54A0FF",
    "SUCCESS":      "#1A7F37",
    "WARN":         "#9A6700",
    "DANGER":       "#CF222E",
    "DANGER_HOVER": "#A40E26",
    "TEXT":         "#1F2328",
    "TEXT_MUTED":   "#57606A",
    "TEXT_DIM":     "#8B949E",
    "TEXT_ON_ACCENT": "#FFFFFF",
    "CTK_MODE":     "light",
}

# Cream retro tech — the default. Warm beige plastic and burnt-orange
# accents: the look of late-70s / 80s computing hardware. Text is a dark
# warm brown rather than black so nothing reads as pure contrast.
_CREAM = {
    "BG_BASE":      "#EFE6D3",
    "BG_SURFACE":   "#F7F0E1",
    "BG_RAISED":    "#E6DAC2",
    "BG_HOVER":     "#DCCEB2",
    "BG_ACTIVE":    "#D0BF9E",
    "BORDER":       "#C9B994",
    "BORDER_STRONG":"#A8956C",
    "ACCENT":       "#C9641E",
    "ACCENT_HOVER": "#B1551A",
    "ACCENT_ACTIVE":"#964614",
    "ACCENT_GLOW":  "#E8894A",
    "SUCCESS":      "#4F7A2E",
    "WARN":         "#9A6B0A",
    "DANGER":       "#B0392A",
    "DANGER_HOVER": "#922E22",
    "TEXT":         "#3B2F23",
    "TEXT_MUTED":   "#6A5A46",
    "TEXT_DIM":     "#8E7C5E",
    "TEXT_ON_ACCENT": "#FFF8EC",
    "CTK_MODE":     "light",
}

# Fallout — Pip-Boy phosphor: near-black green with a bright green
# accent. SUCCESS shares the accent hue on purpose; the whole screen is
# one colour of light and "good" should not introduce a second one.
_FALLOUT = {
    "BG_BASE":      "#0B1A0F",
    "BG_SURFACE":   "#10231A",
    "BG_RAISED":    "#163021",
    "BG_HOVER":     "#1E3D2A",
    "BG_ACTIVE":    "#274B33",
    "BORDER":       "#1F4A2E",
    "BORDER_STRONG":"#2E6B41",
    "ACCENT":       "#2EE868",
    "ACCENT_HOVER": "#26C956",
    "ACCENT_ACTIVE":"#1FA847",
    "ACCENT_GLOW":  "#7DFFA0",
    "SUCCESS":      "#2EE868",
    "WARN":         "#E8C22E",
    "DANGER":       "#FF5A4A",
    "DANGER_HOVER": "#D9463A",
    "TEXT":         "#9CFFB5",
    "TEXT_MUTED":   "#5FCB7E",
    "TEXT_DIM":     "#3F9459",
    "TEXT_ON_ACCENT": "#04120A",
    "CTK_MODE":     "dark",
}

# Retro — 80s synthwave: deep violet with hot pink and cyan.
_RETRO = {
    "BG_BASE":      "#12081F",
    "BG_SURFACE":   "#1A0F2E",
    "BG_RAISED":    "#24163D",
    "BG_HOVER":     "#2F1E4D",
    "BG_ACTIVE":    "#3A275E",
    "BORDER":       "#3C2A5E",
    "BORDER_STRONG":"#5A3F8A",
    "ACCENT":       "#FF3EA5",
    "ACCENT_HOVER": "#E52F92",
    "ACCENT_ACTIVE":"#C7237C",
    "ACCENT_GLOW":  "#FF7CC4",
    "SUCCESS":      "#2EE6D6",
    "WARN":         "#FFB347",
    "DANGER":       "#FF4D6D",
    "DANGER_HOVER": "#D93A57",
    "TEXT":         "#F2E9FF",
    "TEXT_MUTED":   "#B49BD6",
    "TEXT_DIM":     "#8A75A8",
    "TEXT_ON_ACCENT": "#1A0A14",
    "CTK_MODE":     "dark",
}

#: key -> palette. Adding a theme is one entry here plus a label below;
#: the picker, the setting and tests/test_themes.py all read from this.
PALETTES = {
    "cream":   _CREAM,
    "dark":    _DARK,
    "light":   _LIGHT,
    "fallout": _FALLOUT,
    "retro":   _RETRO,
}

#: key -> what the picker shows. Order here is the order in the menu.
THEME_LABELS = {
    "cream":   "Cream retro tech",
    "dark":    "Dark",
    "light":   "Light",
    "fallout": "Fallout",
    "retro":   "Retro",
}

DEFAULT_THEME = "cream"


def _select_palette():
    """Palette for the stored preference, or the default when the value
    is missing or names a theme this build does not have (a settings
    file written by a newer version, say)."""
    key = settings.get("theme", DEFAULT_THEME)
    return PALETTES.get(key, PALETTES[DEFAULT_THEME])


_PALETTE = _select_palette()

# Publish palette values as module-level constants so existing imports like
# `from videokidnapper.ui import theme as T; T.ACCENT` keep working.
BG_BASE       = _PALETTE["BG_BASE"]
BG_SURFACE    = _PALETTE["BG_SURFACE"]
BG_RAISED     = _PALETTE["BG_RAISED"]
BG_HOVER      = _PALETTE["BG_HOVER"]
BG_ACTIVE     = _PALETTE["BG_ACTIVE"]
BORDER        = _PALETTE["BORDER"]
BORDER_STRONG = _PALETTE["BORDER_STRONG"]
ACCENT        = _PALETTE["ACCENT"]
ACCENT_HOVER  = _PALETTE["ACCENT_HOVER"]
ACCENT_ACTIVE = _PALETTE["ACCENT_ACTIVE"]
ACCENT_GLOW   = _PALETTE["ACCENT_GLOW"]
SUCCESS       = _PALETTE["SUCCESS"]
WARN          = _PALETTE["WARN"]
DANGER        = _PALETTE["DANGER"]
DANGER_HOVER  = _PALETTE["DANGER_HOVER"]
TEXT          = _PALETTE["TEXT"]
TEXT_MUTED    = _PALETTE["TEXT_MUTED"]
TEXT_DIM      = _PALETTE["TEXT_DIM"]
TEXT_ON_ACCENT = _PALETTE["TEXT_ON_ACCENT"]


# ---------- Platform brand colors (share + URL tab chips) --------------------
PLATFORM_COLORS = {
    "YouTube":   "#FF0033",
    "Instagram": "#E1306C",
    "Bluesky":   "#0085FF",
    "Twitter/X": "#1DA1F2",
    "Reddit":    "#FF4500",
    "Facebook":  "#1877F2",
}

PLATFORM_GLYPHS = {
    "YouTube":   "▶",
    "Instagram": "◉",
    "Bluesky":   "☁",
    "Twitter/X": "✕",
    "Reddit":    "◆",
    "Facebook":  "f",
}

# ---------- Typography --------------------------------------------------------
FONT_FAMILY = "Segoe UI"
FONT_MONO   = "Consolas"

SIZE_XS  = 10
SIZE_SM  = 11
SIZE_MD  = 12
SIZE_LG  = 14
SIZE_XL  = 16
SIZE_HERO = 22

# ---------- Spacing & geometry ------------------------------------------------
RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 12

PAD_SM = 6
PAD_MD = 10
PAD_LG = 16

BUTTON_HEIGHT      = 36
BUTTON_HEIGHT_SM   = 28
INPUT_HEIGHT       = 34


# ---------- Helpers ----------------------------------------------------------
def font(size=SIZE_MD, weight="normal", mono=False):
    family = FONT_MONO if mono else FONT_FAMILY
    return ctk.CTkFont(family=family, size=size, weight=weight)


def _button_variants():
    """Rebuilt on demand so themed tokens reflect the selected palette."""
    return {
        "primary": {
            "fg_color": ACCENT,
            "hover_color": ACCENT_HOVER,
            "text_color": TEXT_ON_ACCENT,
        },
        "secondary": {
            "fg_color": BG_RAISED,
            "hover_color": BG_HOVER,
            "text_color": TEXT,
            "border_width": 1,
            "border_color": BORDER_STRONG,
        },
        "ghost": {
            "fg_color": "transparent",
            "hover_color": BG_HOVER,
            "text_color": TEXT_MUTED,
        },
        "danger": {
            "fg_color": DANGER,
            "hover_color": DANGER_HOVER,
            "text_color": TEXT_ON_ACCENT,
        },
        "success": {
            "fg_color": SUCCESS,
            "hover_color": "#2EA043",
            "text_color": TEXT_ON_ACCENT,
        },
    }


BUTTON_VARIANTS = _button_variants()


def button(parent, text, variant="primary", **kwargs):
    style = dict(_button_variants().get(variant, _button_variants()["primary"]))
    style.setdefault("corner_radius", RADIUS_MD)
    style.setdefault("height", BUTTON_HEIGHT)
    style.setdefault("font", font(SIZE_LG, "bold"))
    style.update(kwargs)
    return ctk.CTkButton(parent, text=text, **style)


def configure_global():
    ctk.set_appearance_mode(_PALETTE["CTK_MODE"])
    ctk.set_default_color_theme("blue")


def current_mode():
    """CustomTkinter appearance mode ("dark" / "light") of the active palette."""
    return _PALETTE["CTK_MODE"]


def current_theme():
    """Key of the active palette (see PALETTES)."""
    key = settings.get("theme", DEFAULT_THEME)
    return key if key in PALETTES else DEFAULT_THEME


def set_theme(key):
    """Persist a theme preference. Caller must restart the app to apply.

    An unknown key falls back to the default rather than raising: this
    is reached from a settings file as well as from the picker.
    """
    if key not in PALETTES:
        key = DEFAULT_THEME
    settings.set("theme", key)


# Older name kept for anything still calling it.
set_mode = set_theme
