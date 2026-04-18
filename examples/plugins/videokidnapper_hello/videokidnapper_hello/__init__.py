# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Reference plugin: adds a "Hello" tab to VideoKidnapper.

This is deliberately the smallest plugin that exercises every wiring
step (entry-point discovery, on_app_ready, register_tab, a real widget
using the host's theme tokens). Copy it, rename, and edit.
"""

from videokidnapper.plugins import Plugin


class HelloPlugin(Plugin):
    name = "Hello"
    version = "0.1.0"
    min_app_version = "1.1.0"   # uses app.register_tab, added in 1.1.0

    def on_app_ready(self, app):
        """Register a single tab labeled "Hello"."""
        app.register_tab("Hello", self._build_tab, glyph="✦")

    def _build_tab(self, parent):
        # Imported lazily so the plugin module is importable in
        # non-GUI contexts (tests, `python -c "import ..."`, etc.)
        import customtkinter as ctk
        from videokidnapper.ui import theme as T

        frame = ctk.CTkFrame(parent, fg_color="transparent")

        ctk.CTkLabel(
            frame,
            text="✦  Hello from a plugin!",
            font=T.font(T.SIZE_HERO, "bold"),
            text_color=T.ACCENT,
        ).pack(pady=(32, 8))

        ctk.CTkLabel(
            frame,
            text=(
                "This tab was added by the videokidnapper_hello example plugin.\n"
                "See docs/PLUGINS.md for the full plugin API."
            ),
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED,
            justify="center",
        ).pack(pady=(0, 16))
        return frame
