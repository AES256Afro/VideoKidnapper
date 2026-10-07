# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Small themed controls shared by the Studio panels.

Thin wrappers over customtkinter widgets so every panel gets the same
sizes, colors and spacing without repeating a dozen keyword arguments.
"""

import customtkinter as ctk

from videokidnapper.ui import theme as T


def section_label(parent, text):
    """Small uppercase label that heads a group of controls."""
    return ctk.CTkLabel(
        parent, text=text.upper(), font=T.font(T.SIZE_XS, "bold"),
        text_color=T.TEXT_DIM, anchor="w",
    )


def hint(parent, text, wrap=280):
    return ctk.CTkLabel(
        parent, text=text, font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED,
        anchor="w", justify="left", wraplength=wrap,
    )


def segmented(parent, values, variable=None, command=None, height=28, **kwargs):
    """Connected toggle buttons; the selected one is tinted with the accent."""
    return ctk.CTkSegmentedButton(
        parent, values=values, variable=variable, command=command,
        height=height,
        font=T.font(T.SIZE_SM),
        fg_color=T.BORDER_STRONG,
        selected_color=T.ACCENT_SOFT,
        selected_hover_color=T.ACCENT_SOFT,
        unselected_color=T.BG_SURFACE,
        unselected_hover_color=T.BG_HOVER,
        text_color=T.TEXT,
        corner_radius=T.RADIUS_SM,
        border_width=1,
        dynamic_resizing=False,
        **kwargs,
    )


def option_menu(parent, values, variable=None, command=None, width=140, **kwargs):
    return ctk.CTkOptionMenu(
        parent, values=values, variable=variable, command=command,
        width=width, height=30,
        font=T.font(T.SIZE_SM),
        fg_color=T.BG_SURFACE, button_color=T.BG_RAISED,
        button_hover_color=T.BG_HOVER, text_color=T.TEXT,
        dropdown_fg_color=T.BG_SURFACE, dropdown_text_color=T.TEXT,
        dropdown_hover_color=T.BG_HOVER, dropdown_font=T.font(T.SIZE_SM),
        corner_radius=T.RADIUS_SM,
        **kwargs,
    )


def entry(parent, textvariable=None, width=120, mono=False, **kwargs):
    return ctk.CTkEntry(
        parent, textvariable=textvariable, width=width, height=30,
        font=T.font(T.SIZE_MD, mono=mono),
        fg_color=T.BG_SURFACE, border_color=T.BORDER_STRONG,
        text_color=T.TEXT, corner_radius=T.RADIUS_SM, border_width=1,
        **kwargs,
    )


def switch(parent, text, variable=None, command=None):
    return ctk.CTkSwitch(
        parent, text=text, variable=variable, command=command,
        font=T.font(T.SIZE_MD), text_color=T.TEXT,
        progress_color=T.ACCENT, button_color=T.BG_SURFACE,
        button_hover_color=T.BG_SURFACE, fg_color=T.BORDER_STRONG,
        switch_width=34, switch_height=18,
    )


def checkbox(parent, text, variable=None, command=None):
    return ctk.CTkCheckBox(
        parent, text=text, variable=variable, command=command,
        font=T.font(T.SIZE_MD), text_color=T.TEXT,
        fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
        border_color=T.BORDER_STRONG, checkbox_width=16, checkbox_height=16,
        corner_radius=4, border_width=1,
    )


def slider(parent, from_, to, variable=None, command=None, width=160):
    return ctk.CTkSlider(
        parent, from_=from_, to=to, variable=variable, command=command,
        width=width, height=16,
        fg_color=T.BG_ACTIVE, progress_color=T.ACCENT,
        button_color=T.ACCENT, button_hover_color=T.ACCENT_HOVER,
    )


def panel_header(parent, title, height=40):
    """Header strip with a title on the left; returns (frame, right_slot)."""
    frame = ctk.CTkFrame(parent, fg_color=T.BG_SURFACE, corner_radius=0, height=height)
    frame.pack_propagate(False)
    ctk.CTkLabel(
        frame, text=title, font=T.font(T.SIZE_MD, "bold"), text_color=T.TEXT,
    ).pack(side="left", padx=(14, 8))
    right = ctk.CTkFrame(frame, fg_color="transparent")
    right.pack(side="right", padx=(0, 8))
    return frame, right


def divider(parent, horizontal=True):
    if horizontal:
        return ctk.CTkFrame(parent, height=1, fg_color=T.DIVIDER, corner_radius=0)
    return ctk.CTkFrame(parent, width=1, fg_color=T.DIVIDER, corner_radius=0)


class TimeField(ctk.CTkFrame):
    """Labelled ``HH:MM:SS.mmm`` entry; ``command(text)`` on Enter / blur.

    Same ``set_value`` / ``get_value`` API as the old TimestampEntry so
    editor code that drives it didn't have to change.
    """

    def __init__(self, master, label, command=None, width=118, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.command = command
        ctk.CTkLabel(
            self, text=label, font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED,
            anchor="w",
        ).pack(anchor="w")
        self.var = ctk.StringVar(value="00:00:00.000")
        self.entry = entry(self, textvariable=self.var, width=width, mono=True)
        self.entry.pack(anchor="w", pady=(2, 0))
        self.entry.bind("<Return>", self._fire)
        self.entry.bind("<FocusOut>", self._fire)

    def _fire(self, _event=None):
        if self.command:
            self.command(self.var.get())

    def set_value(self, value):
        self.var.set(value)

    def get_value(self):
        return self.var.get()


class TabStrip(ctk.CTkFrame):
    """Underlined text tabs (Clip · Text · Image · Color).

    ``command(key)`` fires on click; :meth:`select` updates the visuals
    without firing it.
    """

    def __init__(self, master, tabs, command=None, **kwargs):
        super().__init__(master, fg_color=T.BG_SURFACE, corner_radius=0, **kwargs)
        self._command = command
        self._tabs = {}
        for key, label in tabs:
            cell = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
            cell.pack(side="left", padx=(10 if not self._tabs else 2, 2))
            btn = ctk.CTkButton(
                cell, text=label, width=10, height=36,
                font=T.font(T.SIZE_MD), fg_color="transparent",
                hover_color=T.BG_HOVER, text_color=T.TEXT_MUTED,
                corner_radius=T.RADIUS_SM,
                command=lambda k=key: self._clicked(k),
            )
            btn.pack(side="top")
            # width=1: CTkFrame defaults to 200px, which would stretch the tab.
            bar = ctk.CTkFrame(cell, height=2, width=1, fg_color="transparent",
                               corner_radius=0)
            bar.pack(side="top", fill="x", padx=6)
            self._tabs[key] = (btn, bar)
        self.current = tabs[0][0] if tabs else None
        if self.current:
            self.select(self.current)

    def _clicked(self, key):
        self.select(key)
        if self._command:
            self._command(key)

    def select(self, key):
        self.current = key
        for k, (btn, bar) in self._tabs.items():
            on = k == key
            btn.configure(
                text_color=T.TEXT if on else T.TEXT_MUTED,
                font=T.font(T.SIZE_MD, "bold" if on else "normal"),
            )
            bar.configure(fg_color=T.ACCENT if on else "transparent")
