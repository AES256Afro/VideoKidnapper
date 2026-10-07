# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Window chrome for the Studio layout: the workspace host and switcher.

:class:`WorkspaceHost` stacks one frame per workspace and shows one at a
time. It also answers the small part of the ``CTkTabview`` API that
plugins and scripts used (``add``, ``tab``, ``set``, ``get``), so
``app.tabview`` keeps working for them.
"""

import customtkinter as ctk

from videokidnapper.ui import theme as T


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
