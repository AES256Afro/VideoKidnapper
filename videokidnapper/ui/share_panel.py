# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Share panel shown under the Export button after a successful export.

For platforms that accept a caption via query param (Facebook sharer, X
intent/tweet, Reddit submit) the typed caption is prefilled. Other
platforms ignore the caption but still receive the file on the clipboard.
"""

import urllib.parse

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.utils import share


PLATFORM_ORDER = ["YouTube", "Instagram", "Bluesky", "Twitter/X", "Reddit", "Facebook"]

# Platforms whose compose URL can take a ?text=/?title=/?quote= pre-fill
# for the caption.
CAPTION_QUERY = {
    "Twitter/X": ("https://x.com/intent/tweet", "text"),
    "Reddit":    ("https://www.reddit.com/submit", "title"),
    "Facebook":  ("https://www.facebook.com/sharer/sharer.php", "quote"),
}


class SharePanel(ctk.CTkFrame):
    def __init__(self, master, file_path, on_instruction=None, columns=None,
                 wrap=380, **kwargs):
        """``columns`` lays the platform buttons out in a grid that many
        wide, for narrow places; by default they sit in a single row. The
        grid version also keeps the hint line hidden until there is an
        instruction to show, to stay short."""
        super().__init__(master, fg_color="transparent", **kwargs)
        self._file_path = file_path
        self._on_instruction = on_instruction

        title = ctk.CTkLabel(
            self, text="Share to",
            font=T.font(T.SIZE_SM, "bold"),
            text_color=T.TEXT_MUTED,
        )
        title.pack(anchor="w", pady=(0, 4))

        self.caption_entry = ctk.CTkEntry(
            self,
            placeholder_text="Optional caption (used by X, Reddit, Facebook)…",
            font=T.font(T.SIZE_SM),
            height=28,
            fg_color=T.BG_RAISED,
            border_color=T.BORDER_STRONG,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
        )
        self.caption_entry.pack(fill="x", pady=(0, 6))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x")

        for i, platform in enumerate(PLATFORM_ORDER):
            btn = self._make_button(btn_row, platform, compact=bool(columns))
            if columns:
                btn.grid(row=i // columns, column=i % columns, sticky="ew",
                         padx=2, pady=2)
            else:
                btn.pack(side="left", padx=2)
        if columns:
            btn_row.grid_columnconfigure(tuple(range(columns)), weight=1,
                                         uniform="share")

        self.hint_label = ctk.CTkLabel(
            self,
            text="Click a platform to copy the file and open its upload page.",
            font=T.font(T.SIZE_XS),
            text_color=T.TEXT_DIM,
            anchor="w",
            justify="left",
            wraplength=wrap,
        )
        if not columns:
            self.hint_label.pack(anchor="w", pady=(6, 0), fill="x")

    def _make_button(self, parent, platform, compact=False):
        color = T.PLATFORM_COLORS.get(platform, T.ACCENT)
        glyph = T.PLATFORM_GLYPHS.get(platform, "●")
        # Compact buttons stretch to their grid cell instead of asking
        # for CTkButton's default 140 px, which would widen the card.
        size = dict(width=10, height=28) if compact else dict(height=30)
        return ctk.CTkButton(
            parent,
            text=f"{glyph} {platform}" if compact else f"  {glyph}  {platform}  ",
            font=T.font(T.SIZE_SM, "bold"),
            fg_color=T.BG_RAISED,
            hover_color=color,
            border_color=color,
            border_width=1,
            text_color=T.TEXT,
            corner_radius=14,
            **size,
            command=lambda p=platform: self._share(p),
        )

    def _share(self, platform):
        caption = self.caption_entry.get().strip()
        try:
            share.copy_file_to_clipboard(self._file_path)
            url, instructions = self._build_share_url(platform, caption)
            share.open_in_browser(url)
        except Exception as e:
            instructions = f"Could not open share target: {e}"
        self.hint_label.configure(
            text=f"{platform}: {instructions}",
            text_color=T.TEXT,
        )
        if not self.hint_label.winfo_manager():
            self.hint_label.pack(anchor="w", pady=(6, 0), fill="x")
        if self._on_instruction:
            self._on_instruction(platform, instructions)

    def _build_share_url(self, platform, caption):
        """If the platform supports a caption query param, prefill it."""
        if platform in CAPTION_QUERY and caption:
            base, param = CAPTION_QUERY[platform]
            url = f"{base}?{param}={urllib.parse.quote(caption)}"
            _, instructions = share.build_share_url(platform, self._file_path)
            return url, instructions
        return share.build_share_url(platform, self._file_path)
