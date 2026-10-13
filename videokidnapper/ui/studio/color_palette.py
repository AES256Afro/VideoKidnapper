# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Inline colour picker: the preset swatches plus a hex entry.

This replaced the operating system's colour dialog, which opened a
window of its own. Colours are ``#RRGGBB`` strings, the same thing that
dialog returned, so captions are stored exactly as before.
"""

import re

import customtkinter as ctk

from videokidnapper.config import TEXT_COLORS
from videokidnapper.ui import theme as T
from videokidnapper.ui.studio import controls as C

_HEX = re.compile(r"#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})")
# The two presets ffmpeg knows by name rather than by hex.
_NAMED = {"white": "#FFFFFF", "black": "#000000"}


def normalize_hex(value):
    """``value`` as an upper-case ``#RRGGBB``, or None if it isn't a colour.

    Takes ``#rgb`` or ``#rrggbb`` with or without the ``#``, and the
    names and values of the caption presets (``White``, ``white``,
    ``#ff0000``), so whatever a layer has stored can be shown.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    named = _NAMED.get(text.lower())
    if named:
        return named
    for name, preset in TEXT_COLORS.items():
        if text.lower() == name.lower():
            return normalize_hex(preset)
    match = _HEX.fullmatch(text)
    if not match:
        return None
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return f"#{digits.upper()}"


# (name, "#RRGGBB") for each caption preset, in the order the menu had.
PRESETS = tuple((name, normalize_hex(value)) for name, value in TEXT_COLORS.items())


def preset_name(value):
    """The preset with this colour, or None for a custom one."""
    hex_value = normalize_hex(value)
    for name, preset in PRESETS:
        if preset == hex_value:
            return name
    return None


class ColorPalette(ctk.CTkFrame):
    """The current colour and a hex entry, with the preset swatches below.

    ``command(hex)`` runs when the user picks a swatch or enters a
    different valid code; :meth:`set` shows a colour without running it.
    """

    SWATCH = 22

    def __init__(self, master, command=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._command = command
        self._value = "#FFFFFF"

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x")
        self.current = ctk.CTkFrame(top, width=26, height=26, corner_radius=T.RADIUS_SM,
                                    border_width=1, border_color=T.BORDER_STRONG,
                                    fg_color=self._value)
        self.current.pack(side="left")
        self.var = ctk.StringVar(value=self._value)
        self.entry = C.entry(top, textvariable=self.var, width=84, mono=True)
        self.entry.pack(side="left", padx=(6, 0))
        self.entry.bind("<Return>", self._entered)
        self.entry.bind("<FocusOut>", self._entered)
        self.name_label = ctk.CTkLabel(top, text="", font=T.font(T.SIZE_SM),
                                       text_color=T.TEXT_MUTED, anchor="w")
        self.name_label.pack(side="left", padx=(8, 0))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        self.swatches = {}
        for name, value in PRESETS:
            swatch = ctk.CTkButton(
                row, text="", width=self.SWATCH, height=self.SWATCH,
                corner_radius=self.SWATCH // 2, fg_color=value, hover_color=value,
                border_width=1, border_color=T.BORDER_STRONG, cursor="hand2",
                command=lambda v=value: self._picked(v),
            )
            swatch.pack(side="left", padx=(0, 4))
            self.swatches[value] = swatch
        self._show()

    def get(self):
        return self._value

    def set(self, value):
        """Show ``value``; anything that isn't a colour is ignored.

        The Inspector calls this on every caption edit, typing included,
        so an unchanged colour skips the redraw (and leaves a half-typed
        code in the entry alone).
        """
        hex_value = normalize_hex(value)
        if hex_value is not None and hex_value != self._value:
            self._value = hex_value
            self._show()

    # ------------------------------------------------------------------
    def _picked(self, value):
        if value == self._value:
            self._show()  # tidies the entry after a rejected code
            return
        self._value = value
        self._show()
        if self._command:
            self._command(value)

    def _entered(self, _event=None):
        hex_value = normalize_hex(self.var.get())
        if hex_value is None:
            # Put the working colour back and flag the entry until the
            # next good value, rather than guessing what was meant.
            self.var.set(self._value)
            self.entry.configure(border_color=T.DANGER)
            return
        self._picked(hex_value)

    def _show(self):
        self.current.configure(fg_color=self._value)
        self.var.set(self._value)
        self.entry.configure(border_color=T.BORDER_STRONG)
        self.name_label.configure(text=preset_name(self._value) or "Custom")
        for value, swatch in self.swatches.items():
            on = value == self._value
            swatch.configure(border_width=2 if on else 1,
                             border_color=T.ACCENT if on else T.BORDER_STRONG)
