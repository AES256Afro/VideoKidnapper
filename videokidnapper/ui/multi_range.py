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
from videokidnapper.utils.time_format import format_duration, seconds_to_short


class RangeQueue(ctk.CTkFrame):
    _CHEVRON_OPEN   = "▾"
    _CHEVRON_CLOSED = "▸"

    def __init__(self, master, on_change=None, **kwargs):
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
        # Last column count used, so a <Configure> that changes nothing
        # does not re-grid (which would fire <Configure> again).
        self._chip_columns = 0
        # Fired for any change to the queue — removal or reorder. The
        # parent uses it to re-evaluate the export button and to take an
        # undo snapshot, and both matter equally for a reorder.
        self._on_change = on_change
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
        # Chips used to pack side-by-side in one row, which ran off the
        # edge of the window at three ranges. They now wrap, and rewrap
        # when the window is resized.
        self.chips_frame.bind("<Configure>", self._on_chips_resize)

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
            # No chips left, so no column count applies. Leaving a stale
            # one would make the next resize compare against a layout
            # that no longer exists.
            self._chip_columns = 0
            return

        for i, (start, end) in enumerate(self._ranges):
            chip = ctk.CTkFrame(
                self.chips_frame,
                fg_color=T.BG_RAISED, corner_radius=12,
                border_width=1, border_color=T.BORDER_STRONG,
            )
            # Placed by _reflow_chips once every chip's width is known.

            # Order is not cosmetic: with "Concat ranges" on, this is the
            # order clips are joined in. Before these controls the only
            # way to resequence was to delete rows and re-find every
            # in- and out-point.
            left_btn = ctk.CTkButton(
                chip, text="◀", width=20, height=22,
                fg_color="transparent", hover_color=T.BG_HOVER,
                text_color=T.TEXT_DIM if i > 0 else T.BG_HOVER,
                font=T.font(T.SIZE_SM, "bold"),
                corner_radius=11,
                state="normal" if i > 0 else "disabled",
                command=lambda idx=i: self.move_range(idx, -1),
            )
            left_btn.pack(side="left", padx=(6, 0))

            # Duration is what people actually reason about when
            # sequencing; the timecodes alone make every chip look alike.
            ctk.CTkLabel(
                chip,
                text=(f" #{i + 1}  {seconds_to_short(start)}→{seconds_to_short(end)}"
                      f"  ·  {format_duration(end - start)} "),
                font=T.font(T.SIZE_SM, mono=True),
                text_color=T.TEXT,
            ).pack(side="left", pady=4)

            last = i == len(self._ranges) - 1
            right_btn = ctk.CTkButton(
                chip, text="▶", width=20, height=22,
                fg_color="transparent", hover_color=T.BG_HOVER,
                text_color=T.TEXT_DIM if not last else T.BG_HOVER,
                font=T.font(T.SIZE_SM, "bold"),
                corner_radius=11,
                state="disabled" if last else "normal",
                command=lambda idx=i: self.move_range(idx, 1),
            )
            right_btn.pack(side="left")

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

        self._reflow_chips()

    def _columns_that_fit(self):
        """How many chips fit across the current width."""
        if not self._chip_frames:
            return 1
        available = self.chips_frame.winfo_width()
        if available <= 1:  # not laid out yet — assume one row
            return len(self._chip_frames)
        widest = max(c.winfo_reqwidth() for c in self._chip_frames) + 8
        return max(1, available // max(1, widest))

    def _reflow_chips(self, columns=None):
        """Lay the chips out in a wrapping grid."""
        if not self._chip_frames:
            self._chip_columns = 0
            return
        columns = columns or self._columns_that_fit()
        self._chip_columns = columns
        for index, chip in enumerate(self._chip_frames):
            chip.grid(row=index // columns, column=index % columns,
                      padx=4, pady=2, sticky="w")

    def _on_chips_resize(self, _event=None):
        """Rewrap on resize — but only when the column count changes.

        Re-gridding fires <Configure> again, so reacting to every event
        would loop.
        """
        if not self._chip_frames:
            return
        columns = self._columns_that_fit()
        if columns != self._chip_columns:
            self._reflow_chips(columns)

    def move_range(self, idx, delta):
        """Move one queued range earlier (-1) or later (+1).

        Returns True when the queue changed. Out-of-range moves are a
        no-op rather than an error: the end chips keep their disabled
        buttons, and a stale index from a redrawn chip should not raise.
        """
        target = idx + delta
        if not (0 <= idx < len(self._ranges)) or not (0 <= target < len(self._ranges)):
            return False
        self._ranges[idx], self._ranges[target] = (
            self._ranges[target], self._ranges[idx],
        )
        self._redraw_chips()
        self._update_header()
        if self._on_change:
            self._on_change()
        return True

    def _remove(self, idx):
        if 0 <= idx < len(self._ranges):
            self._ranges.pop(idx)
            if self._on_change:
                self._on_change()
            self._redraw_chips()
            self._update_header()
