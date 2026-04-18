# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Multi-range trim panel.

Collapsible by the same pattern as TextLayersPanel: clicking the header
toggles the chip body. Body is auto-hidden when empty and auto-expanded
when the first range gets queued, so the idle state is a thin one-line
header instead of a ~400px placeholder block.
"""

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.utils.time_format import seconds_to_hms


class RangeQueue(ctk.CTkFrame):
    _CHEVRON_OPEN   = "▾"
    _CHEVRON_CLOSED = "▸"

    def __init__(self, master, on_remove=None, **kwargs):
        super().__init__(
            master,
            fg_color=T.BG_SURFACE,
            border_width=1,
            border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
            **kwargs,
        )
        self._ranges = []   # list of (start, end)
        self._chip_frames = []
        self._on_remove = on_remove
        self._expanded = False
        self._user_collapsed = False  # respect explicit user collapse even after new adds

        # ---- Collapsible header ----------------------------------------
        self.toggle_btn = ctk.CTkButton(
            self,
            text=self._header_text(),
            font=T.font(T.SIZE_LG, "bold"),
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_MD,
            height=36, anchor="w",
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", padx=4, pady=4)

        # ---- Body (chip row) -------------------------------------------
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        # Not packed initially — the toggle or `add_range` will reveal it.

        self.hint = ctk.CTkLabel(
            self.body,
            text="Adjust the timeline and press '+ Queue'.",
            font=T.font(T.SIZE_SM),
            text_color=T.TEXT_DIM,
            anchor="w",
        )
        self.hint.pack(fill="x", padx=12, pady=(2, 6))

        self.chips_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        self.chips_frame.pack(fill="x", padx=10, pady=(0, 8))

    # ------------------------------------------------------------------
    def _header_text(self):
        chev = self._CHEVRON_OPEN if self._expanded else self._CHEVRON_CLOSED
        count = len(self._ranges)
        return f"  {chev}   Queued ranges  ·  {count}"

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()
            self._user_collapsed = True
        self.toggle_btn.configure(text=self._header_text())

    def _update_header(self):
        self.toggle_btn.configure(text=self._header_text())

    # ------------------------------------------------------------------
    def add_range(self, start, end):
        if end - start < 0.05:
            return False
        self._ranges.append((float(start), float(end)))
        self._redraw_chips()
        # Auto-expand the first time a range is queued, but don't fight
        # a user who collapsed it on purpose.
        if not self._expanded and not self._user_collapsed:
            self._expanded = True
            self.body.pack(fill="x")
        self._update_header()
        return True

    def clear(self):
        self._ranges.clear()
        self._redraw_chips()
        self._update_header()
        # Returning to empty state: collapse and forget the user's previous choice.
        if self._expanded:
            self._expanded = False
            self.body.pack_forget()
        self._user_collapsed = False
        self._update_header()

    def get_ranges(self):
        return list(self._ranges)

    # ------------------------------------------------------------------
    def _redraw_chips(self):
        for frame in self._chip_frames:
            frame.destroy()
        self._chip_frames.clear()

        self.hint.pack_forget()
        if not self._ranges:
            self.hint.pack(fill="x", padx=12, pady=(2, 6))
            return

        for i, (start, end) in enumerate(self._ranges):
            chip = ctk.CTkFrame(
                self.chips_frame,
                fg_color=T.BG_RAISED, corner_radius=12,
                border_width=1, border_color=T.BORDER_STRONG,
            )
            chip.pack(side="left", padx=4, pady=2)

            ctk.CTkLabel(
                chip,
                text=f"  #{i + 1}  {seconds_to_hms(start)} → {seconds_to_hms(end)}  ",
                font=T.font(T.SIZE_SM, mono=True),
                text_color=T.TEXT,
            ).pack(side="left", pady=4)

            remove_btn = ctk.CTkButton(
                chip, text="✕", width=22, height=22,
                fg_color="transparent", hover_color=T.DANGER,
                text_color=T.TEXT_DIM,
                font=T.font(T.SIZE_SM, "bold"),
                corner_radius=11,
                command=lambda idx=i: self._remove(idx),
            )
            remove_btn.pack(side="left", padx=(0, 6))

            self._chip_frames.append(chip)

    def _remove(self, idx):
        if 0 <= idx < len(self._ranges):
            self._ranges.pop(idx)
            if self._on_remove:
                self._on_remove()
            self._redraw_chips()
            self._update_header()
