"""Centralized design tokens for VideoKidnapper.

Tokens are selected once at import time from the dark or light palette
based on ``settings.get("theme")``. Changing the theme requires a restart
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


def _select_palette():
    mode = settings.get("theme", "dark")
    return _LIGHT if mode == "light" else _DARK


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
    return _PALETTE["CTK_MODE"]


def set_mode(mode):
    """Persist a new theme preference. Caller must restart the app to apply."""
    if mode not in ("dark", "light"):
        mode = "dark"
    settings.set("theme", mode)
