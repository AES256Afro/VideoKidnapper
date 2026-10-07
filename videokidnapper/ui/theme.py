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
#
# Beyond the base surface/text/accent tokens, every palette carries the
# Studio tokens: soft accent fills for selected rows and chips, the panel
# header strip, the preview monitor backdrop, the playhead, and one hue per
# timeline track (text, image, video, audio) that also differs in lightness.

# Studio: the default. Neutral cool greys so the video is the most colorful
# thing on screen, and one blue accent.
_LIGHT = {
    "BG_BASE":      "#E8EAED",
    "BG_SURFACE":   "#FFFFFF",
    "BG_RAISED":    "#F3F4F6",
    "BG_HOVER":     "#EAECEF",
    "BG_ACTIVE":    "#DFE3E8",
    "BORDER":       "#D6DAE0",
    "BORDER_STRONG":"#C4CAD2",
    "ACCENT":       "#1D5BD8",
    "ACCENT_HOVER": "#174BB3",
    "ACCENT_ACTIVE":"#123E99",
    "ACCENT_GLOW":  "#5B8DEF",
    "SUCCESS":      "#1E7A4C",
    "WARN":         "#8A5300",
    "DANGER":       "#C62A20",
    "DANGER_HOVER": "#A1271D",
    "TEXT":         "#14171B",
    "TEXT_MUTED":   "#4A525C",
    "TEXT_DIM":     "#66707C",
    "TEXT_ON_ACCENT": "#FFFFFF",
    "ACCENT_SOFT":  "#E3ECFC",
    "ACCENT_SOFT_TEXT": "#123E99",
    "PANEL_HEADER": "#F5F6F8",
    "DIVIDER":      "#E6E9ED",
    "MONITOR_BG":   "#DCDFE4",
    "PLAYHEAD":     "#D9342B",
    "SELECTION":    "#E8EFFC",
    "WARN_SOFT":    "#FFF6E5",
    "WARN_EDGE":    "#E8C98A",
    "TRACK_TEXT_FILL":  "#ECE3FC",
    "TRACK_TEXT_EDGE":  "#6B3FD0",
    "TRACK_TEXT_INK":   "#3F1F8F",
    "TRACK_IMAGE_FILL": "#FDEBCB",
    "TRACK_IMAGE_EDGE": "#B86200",
    "TRACK_IMAGE_INK":  "#6B3A00",
    "TRACK_VIDEO_EDGE": "#1D5BD8",
    "TRACK_AUDIO_FILL": "#DDF2E7",
    "TRACK_AUDIO_WAVE": "#1E7A4C",
    "CTK_MODE":     "light",
}

# Graphite: the dark option. Neutral greys rather than navy-black, same
# blue accent and track hues as Studio.
_DARK = {
    "BG_BASE":      "#1E1F22",
    "BG_SURFACE":   "#2A2B2F",
    "BG_RAISED":    "#323338",
    "BG_HOVER":     "#3A3B40",
    "BG_ACTIVE":    "#45464C",
    "BORDER":       "#3A3B40",
    "BORDER_STRONG":"#4A4B52",
    "ACCENT":       "#3D74E0",
    "ACCENT_HOVER": "#3363C4",
    "ACCENT_ACTIVE":"#2A53A6",
    "ACCENT_GLOW":  "#6E9BF0",
    "SUCCESS":      "#3FB97A",
    "WARN":         "#E0A33C",
    "DANGER":       "#F05A4F",
    "DANGER_HOVER": "#D84438",
    "TEXT":         "#ECECEE",
    "TEXT_MUTED":   "#B4B5BA",
    "TEXT_DIM":     "#9A9CA2",
    "TEXT_ON_ACCENT": "#FFFFFF",
    "ACCENT_SOFT":  "#24324D",
    "ACCENT_SOFT_TEXT": "#BCD0FA",
    "PANEL_HEADER": "#26272B",
    "DIVIDER":      "#36373C",
    "MONITOR_BG":   "#17181A",
    "PLAYHEAD":     "#F05A4F",
    "SELECTION":    "#2C3A55",
    "WARN_SOFT":    "#3A2F1A",
    "WARN_EDGE":    "#7A5A20",
    "TRACK_TEXT_FILL":  "#3A2C5C",
    "TRACK_TEXT_EDGE":  "#9B6BDF",
    "TRACK_TEXT_INK":   "#E6DAFF",
    "TRACK_IMAGE_FILL": "#4A3519",
    "TRACK_IMAGE_EDGE": "#D18A3C",
    "TRACK_IMAGE_INK":  "#FFE3C2",
    "TRACK_VIDEO_EDGE": "#4C7FD1",
    "TRACK_AUDIO_FILL": "#1F3B2E",
    "TRACK_AUDIO_WAVE": "#3FA372",
    "CTK_MODE":     "dark",
}

# Cream retro tech: warm beige plastic and burnt-orange accents, the look
# of late-70s / 80s computing hardware. Text is a dark warm brown rather
# than black so nothing reads as pure contrast.
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
    "ACCENT_SOFT":  "#F2DCC6",
    "ACCENT_SOFT_TEXT": "#7A3A0F",
    "PANEL_HEADER": "#F1E8D6",
    "DIVIDER":      "#E2D5BB",
    "MONITOR_BG":   "#DDD0B5",
    "PLAYHEAD":     "#B0392A",
    "SELECTION":    "#F0E0C8",
    "WARN_SOFT":    "#F6E7C4",
    "WARN_EDGE":    "#D4B36A",
    "TRACK_TEXT_FILL":  "#E8DDEE",
    "TRACK_TEXT_EDGE":  "#6E4AA8",
    "TRACK_TEXT_INK":   "#3F2670",
    "TRACK_IMAGE_FILL": "#F5DEB8",
    "TRACK_IMAGE_EDGE": "#A8620F",
    "TRACK_IMAGE_INK":  "#5E3505",
    "TRACK_VIDEO_EDGE": "#C9641E",
    "TRACK_AUDIO_FILL": "#DFE8D0",
    "TRACK_AUDIO_WAVE": "#4F7A2E",
    "CTK_MODE":     "light",
}

# Fallout: Pip-Boy phosphor, near-black green with a bright green accent.
# SUCCESS shares the accent hue on purpose; the whole screen is one colour
# of light and "good" should not introduce a second one. Tracks stay in the
# same light and differ by brightness, with the image track in amber.
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
    "ACCENT_SOFT":  "#173D24",
    "ACCENT_SOFT_TEXT": "#B5FFC8",
    "PANEL_HEADER": "#0E1F15",
    "DIVIDER":      "#1A3A25",
    "MONITOR_BG":   "#06100A",
    "PLAYHEAD":     "#FF5A4A",
    "SELECTION":    "#1A4428",
    "WARN_SOFT":    "#2A2710",
    "WARN_EDGE":    "#7A6A1A",
    "TRACK_TEXT_FILL":  "#173A26",
    "TRACK_TEXT_EDGE":  "#7DFFA0",
    "TRACK_TEXT_INK":   "#C8FFD6",
    "TRACK_IMAGE_FILL": "#2E2B10",
    "TRACK_IMAGE_EDGE": "#E8C22E",
    "TRACK_IMAGE_INK":  "#FFF1A8",
    "TRACK_VIDEO_EDGE": "#2EE868",
    "TRACK_AUDIO_FILL": "#10291A",
    "TRACK_AUDIO_WAVE": "#2EE868",
    "CTK_MODE":     "dark",
}

# Retro: 80s synthwave, deep violet with hot pink and cyan.
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
    "ACCENT_SOFT":  "#3D1640",
    "ACCENT_SOFT_TEXT": "#FFB8DE",
    "PANEL_HEADER": "#170C29",
    "DIVIDER":      "#2E1F4A",
    "MONITOR_BG":   "#0B0514",
    "PLAYHEAD":     "#2EE6D6",
    "SELECTION":    "#3A1F55",
    "WARN_SOFT":    "#3A2A14",
    "WARN_EDGE":    "#8A6A2A",
    "TRACK_TEXT_FILL":  "#3A2366",
    "TRACK_TEXT_EDGE":  "#B07CFF",
    "TRACK_TEXT_INK":   "#EADCFF",
    "TRACK_IMAGE_FILL": "#4A2A1A",
    "TRACK_IMAGE_EDGE": "#FFB347",
    "TRACK_IMAGE_INK":  "#FFE4C2",
    "TRACK_VIDEO_EDGE": "#FF3EA5",
    "TRACK_AUDIO_FILL": "#13343A",
    "TRACK_AUDIO_WAVE": "#2EE6D6",
    "CTK_MODE":     "dark",
}

#: key -> palette. Adding a theme is one entry here plus a label below;
#: the picker, the setting and tests/test_themes.py all read from this.
PALETTES = {
    "light":   _LIGHT,
    "dark":    _DARK,
    "cream":   _CREAM,
    "fallout": _FALLOUT,
    "retro":   _RETRO,
}

#: key -> what the picker shows. Order here is the order in the menu.
THEME_LABELS = {
    "light":   "Studio",
    "dark":    "Graphite",
    "cream":   "Cream retro tech",
    "fallout": "Fallout",
    "retro":   "Retro",
}

DEFAULT_THEME = "light"


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
ACCENT_SOFT   = _PALETTE["ACCENT_SOFT"]
ACCENT_SOFT_TEXT = _PALETTE["ACCENT_SOFT_TEXT"]
PANEL_HEADER  = _PALETTE["PANEL_HEADER"]
DIVIDER       = _PALETTE["DIVIDER"]
MONITOR_BG    = _PALETTE["MONITOR_BG"]
PLAYHEAD      = _PALETTE["PLAYHEAD"]
SELECTION     = _PALETTE["SELECTION"]
WARN_SOFT     = _PALETTE["WARN_SOFT"]
WARN_EDGE     = _PALETTE["WARN_EDGE"]
TRACK_TEXT_FILL  = _PALETTE["TRACK_TEXT_FILL"]
TRACK_TEXT_EDGE  = _PALETTE["TRACK_TEXT_EDGE"]
TRACK_TEXT_INK   = _PALETTE["TRACK_TEXT_INK"]
TRACK_IMAGE_FILL = _PALETTE["TRACK_IMAGE_FILL"]
TRACK_IMAGE_EDGE = _PALETTE["TRACK_IMAGE_EDGE"]
TRACK_IMAGE_INK  = _PALETTE["TRACK_IMAGE_INK"]
TRACK_VIDEO_EDGE = _PALETTE["TRACK_VIDEO_EDGE"]
TRACK_AUDIO_FILL = _PALETTE["TRACK_AUDIO_FILL"]
TRACK_AUDIO_WAVE = _PALETTE["TRACK_AUDIO_WAVE"]


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
            "fg_color": BG_SURFACE,
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
            "hover_color": SUCCESS,
            "text_color": TEXT_ON_ACCENT,
        },
    }


BUTTON_VARIANTS = _button_variants()


def button(parent, text, variant="primary", **kwargs):
    style = dict(_button_variants().get(variant, _button_variants()["primary"]))
    style.setdefault("corner_radius", RADIUS_SM)
    style.setdefault("height", BUTTON_HEIGHT)
    style.setdefault("font", font(SIZE_MD, "bold"))
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
