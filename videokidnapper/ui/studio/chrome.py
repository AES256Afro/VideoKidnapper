# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Window chrome for the Studio layout: the workspace host and switcher.

:class:`WorkspaceHost` stacks one frame per workspace and shows one at a
time. It also answers the small part of the ``CTkTabview`` API that
plugins and scripts used (``add``, ``tab``, ``set``, ``get``), so
``app.tabview`` keeps working for them.

:class:`Page` is the frame for pages opened from the settings menu, such
as Setup and the keyboard shortcuts. They take over the workspace area
instead of opening a window of their own, so the app stays one window.
"""

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button


class WorkspaceHost(ctk.CTkFrame):
    def __init__(self, master, on_switch=None, **kwargs):
        super().__init__(master, fg_color=T.BG_BASE, corner_radius=0, **kwargs)
        self._frames = {}
        self._current = None
        self._on_switch = on_switch

    def add(self, key):
        frame = ctk.CTkFrame(self, fg_color=T.BG_BASE, corner_radius=0)
        self._frames[key] = frame
        return frame

    def tab(self, key):
        return self._frames[key]

    def keys(self):
        return list(self._frames)

    def set(self, key):
        if key not in self._frames or key == self._current:
            return
        if self._current is not None:
            self._frames[self._current].pack_forget()
        self._current = key
        self._frames[key].pack(fill="both", expand=True)
        if self._on_switch:
            self._on_switch(key)

    def get(self):
        return self._current


class Page(ctk.CTkFrame):
    """A page with a bar on top: Back, the page's title, then ``body``.

    Back is the way out, so it says where it goes ("Back to Edit") once
    the app knows. Widgets for the right end of the bar go in
    ``bar_actions``.
    """

    def __init__(self, master, title, on_back, **kwargs):
        super().__init__(master, fg_color=T.BG_BASE, corner_radius=0, **kwargs)
        bar = ctk.CTkFrame(self, fg_color=T.BG_SURFACE, corner_radius=0, height=44)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self.back_button = button(bar, "‹  Back", variant="ghost", height=30,
                                  font=T.font(T.SIZE_SM, "bold"), command=on_back)
        self.back_button.pack(side="left", padx=10)
        ctk.CTkLabel(bar, text=title, font=T.font(T.SIZE_LG, "bold"),
                     text_color=T.TEXT).pack(side="left", padx=(4, 0))
        self.bar_actions = ctk.CTkFrame(bar, fg_color="transparent")
        self.bar_actions.pack(side="right", padx=12)
        ctk.CTkFrame(self, height=1, fg_color=T.BORDER, corner_radius=0).pack(fill="x")

        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True)

    def set_back_label(self, where=None):
        self.back_button.configure(text=f"‹  Back to {where}" if where else "‹  Back")


class WorkspaceSwitcher(ctk.CTkFrame):
    """Pill group of workspace buttons: 1 Import · 2 Edit · 3 Export."""

    def __init__(self, master, items, command, **kwargs):
        super().__init__(master, fg_color=T.BG_RAISED, corner_radius=T.RADIUS_MD,
                         **kwargs)
        self._command = command
        self._buttons = {}
        for key, label in items:
            self.add_item(key, label)

    def add_item(self, key, label):
        btn = ctk.CTkButton(
            self, text=label, height=30, width=10, corner_radius=T.RADIUS_SM,
            font=T.font(T.SIZE_MD), fg_color="transparent",
            hover_color=T.BG_HOVER, text_color=T.TEXT_MUTED,
            command=lambda k=key: self._command(k),
        )
        btn.pack(side="left", padx=3, pady=3)
        self._buttons[key] = btn

    def select(self, key):
        for k, btn in self._buttons.items():
            on = k == key
            btn.configure(
                fg_color=T.BG_SURFACE if on else "transparent",
                hover_color=T.BG_SURFACE if on else T.BG_HOVER,
                text_color=T.TEXT if on else T.TEXT_MUTED,
                font=T.font(T.SIZE_MD, "bold" if on else "normal"),
            )
