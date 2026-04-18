"""Share panel shown inside ExportDialog after a successful export.

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
    def __init__(self, master, file_path, on_instruction=None, **kwargs):
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

        for platform in PLATFORM_ORDER:
            self._make_button(btn_row, platform).pack(side="left", padx=2)

        self.hint_label = ctk.CTkLabel(
            self,
            text="Click a platform to copy the file and open its upload page.",
            font=T.font(T.SIZE_XS),
            text_color=T.TEXT_DIM,
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self.hint_label.pack(anchor="w", pady=(6, 0), fill="x")

    def _make_button(self, parent, platform):
        color = T.PLATFORM_COLORS.get(platform, T.ACCENT)
        glyph = T.PLATFORM_GLYPHS.get(platform, "●")
        return ctk.CTkButton(
            parent,
            text=f"  {glyph}  {platform}  ",
            font=T.font(T.SIZE_SM, "bold"),
            fg_color=T.BG_RAISED,
            hover_color=color,
            border_color=color,
            border_width=1,
            text_color=T.TEXT,
            corner_radius=14,
            height=30,
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
