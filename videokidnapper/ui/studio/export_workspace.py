# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Studio Export workspace.

"This project" gathers every export decision in one place: what to
export (the selection plus saved ranges, optionally joined), how (made
for a platform, format, quality, GIF and encoder options) and where.
"Batch files" and "History" are the old Batch Export and History tabs,
reached from here instead of from top-level tabs. Both are built the
first time they are shown, by the app (see ``App._ensure_tab``).
"""

import os
import subprocess
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.config import PRESETS
from videokidnapper.ui import theme as T
from videokidnapper.ui.editor_options import (
    GIF_DITHER_CHOICES, GIF_LOOP_CHOICES, GIF_STATS_CHOICES, HW_CHOICES,
    TRANSITION_CHOICES,
)
from videokidnapper.ui.platform_presets import PLATFORM_CHOICES
from videokidnapper.ui.studio import controls as C
from videokidnapper.ui.theme import button
from videokidnapper.utils.file_naming import NAMING_STYLES
from videokidnapper.utils.time_format import seconds_to_hms

FORMAT_SEGMENTS = ["MP4", "GIF", "MP3"]
QUALITY_DETAIL = {
    name: f"{p['width'] or 'Full'} wide · {p['fps']} fps" for name, p in PRESETS.items()
}
TRANSITION_DURATIONS = ["0.25s", "0.5s", "1s", "1.5s"]


def _card(parent, title=None):
    card = ctk.CTkFrame(parent, fg_color=T.BG_SURFACE, corner_radius=T.RADIUS_LG,
                        border_width=1, border_color=T.BORDER)
    if title:
        ctk.CTkLabel(card, text=title, font=T.font(T.SIZE_XL, "bold"),
                     text_color=T.TEXT, anchor="w").pack(fill="x", padx=18, pady=(16, 10))
    return card


class ExportWorkspace(ctk.CTkFrame):
    def __init__(self, master, app, editor, **kwargs):
        super().__init__(master, fg_color=T.BG_BASE, corner_radius=0, **kwargs)
        self.app = app
        self.editor = editor

        nav = ctk.CTkFrame(self, fg_color=T.BG_SURFACE, corner_radius=0, height=48)
        nav.pack(fill="x")
        nav.pack_propagate(False)
        self.sub_tabs = C.TabStrip(
            nav, (("project", "This project"), ("batch", "Batch files"),
                  ("history", "History")),
            command=self.show,
        )
        self.sub_tabs.pack(side="left", fill="y", padx=(16, 0))
        C.divider(self).pack(fill="x")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        # Parent for the deferred pages the app builds on first view.
        self.page_host = body
        self.pages = {"project": self._build_project_page(body)}
        self.current = None
        self.show("project")

        editor.add_state_listener(self.refresh)
        editor.options.add_listener(self.refresh)
        self.refresh()

    @property
    def batch_page(self):
        return self.app._ensure_tab("batch")

    @property
    def history_page(self):
        return self.app._ensure_tab("history")

    def show(self, key):
        if key == self.current:
            return
        page = self.pages.get(key)
        fresh = False
        if page is None:
            page = self.app._on_tab_changed(key)
            if page is None:
                return
            self.pages[key] = page
            fresh = True
        if self.current:
            self.pages[self.current].pack_forget()
        self.current = key
        self.sub_tabs.select(key)
        page.pack(fill="both", expand=True)
        if key == "history" and not fresh:
            # A fresh page has just read the history; an old one may be stale.
            page.refresh()
        elif key == "project":
            self.refresh()

    # ------------------------------------------------------------------
    def _build_project_page(self, master):
        page = ctk.CTkScrollableFrame(master, fg_color="transparent",
                                      scrollbar_button_color=T.BG_HOVER,
                                      scrollbar_button_hover_color=T.BG_ACTIVE)
        grid = ctk.CTkFrame(page, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=28, pady=24)
        grid.grid_columnconfigure(0, weight=1, minsize=300)
        grid.grid_columnconfigure(1, weight=1, minsize=380)
        opts = self.editor.options
        left = ctk.CTkFrame(grid, fg_color="transparent")
        left.grid(row=0, column=0, sticky="new", padx=(0, 16))

        # -- What ------------------------------------------------------
        what = _card(left, "What to export")
        what.pack(fill="x")
        self.selection_row = ctk.CTkFrame(what, fg_color=T.ACCENT_SOFT,
                                          corner_radius=T.RADIUS_MD)
        self.selection_row.pack(fill="x", padx=18)
        self.selection_label = ctk.CTkLabel(
            self.selection_row, text="", font=T.font(T.SIZE_MD), justify="left",
            text_color=T.ACCENT_SOFT_TEXT, anchor="w",
        )
        self.selection_label.pack(side="left", fill="x", expand=True, padx=12, pady=10)
        button(self.selection_row, "Edit", variant="ghost", width=50, height=28,
               text_color=T.ACCENT, font=T.font(T.SIZE_SM, "bold"),
               command=lambda: self.app.show_workspace("edit")).pack(side="right", padx=6)
        self.ranges_box = ctk.CTkFrame(what, fg_color="transparent")
        self.ranges_box.pack(fill="x", padx=18, pady=(8, 0))

        join = ctk.CTkFrame(what, fg_color="transparent")
        join.pack(fill="x", padx=18, pady=(14, 18))
        C.divider(join).pack(fill="x", pady=(0, 12))
        C.switch(join, "Join everything into one video",
                 variable=opts.concat_var).pack(anchor="w")
        C.hint(join, "MP4 only. Between parts:", wrap=320).pack(anchor="w", pady=(6, 4))
        C.segmented(join, [label for label, _k in TRANSITION_CHOICES],
                    variable=opts.transition_var).pack(fill="x")
        dur_row = ctk.CTkFrame(join, fg_color="transparent")
        dur_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(dur_row, text="Transition length", font=T.font(T.SIZE_SM),
                     text_color=T.TEXT_MUTED).pack(side="left")
        self.transition_dur_menu = C.option_menu(
            dur_row, TRANSITION_DURATIONS, width=90,
            command=lambda v: opts.transition_duration_var.set(float(v.rstrip("s"))))
        self.transition_dur_menu.pack(side="left", padx=(8, 0))

        # -- How -------------------------------------------------------
        how = _card(grid, "How to export")
        how.grid(row=0, column=1, sticky="new")
        C.section_label(how, "Made for").pack(fill="x", padx=18)
        plat = ctk.CTkFrame(how, fg_color="transparent")
        plat.pack(fill="x", padx=18, pady=(6, 0))
        self.platform_buttons = {}
        for i, name in enumerate(PLATFORM_CHOICES):
            btn = ctk.CTkButton(
                plat, text=name, height=32, corner_radius=T.RADIUS_SM,
                font=T.font(T.SIZE_SM), border_width=1,
                command=lambda n=name: self.editor._apply_platform_preset(n),
            )
            btn.grid(row=i // 3, column=i % 3, sticky="ew", padx=3, pady=3)
            self.platform_buttons[name] = btn
        plat.grid_columnconfigure((0, 1, 2), weight=1, uniform="plat")

        C.section_label(how, "Format").pack(fill="x", padx=18, pady=(14, 6))
        self.format_seg = C.segmented(how, FORMAT_SEGMENTS, command=self._format_picked,
                                      height=32)
        self.format_seg.pack(fill="x", padx=18)
        self.format_hint = C.hint(how, "", wrap=420)
        self.format_hint.pack(anchor="w", padx=18, pady=(4, 0))

        C.section_label(how, "Quality").pack(fill="x", padx=18, pady=(14, 6))
        self.quality_seg = C.segmented(how, list(PRESETS.keys()), height=32,
                                       command=self.editor._on_quality_change)
        self.quality_seg.pack(fill="x", padx=18)
        self.quality_hint = C.hint(how, "", wrap=420)
        self.quality_hint.pack(anchor="w", padx=18, pady=(4, 0))

        C.section_label(how, "Save to").pack(fill="x", padx=18, pady=(14, 6))
        folder = ctk.CTkFrame(how, fg_color="transparent")
        folder.pack(fill="x", padx=18)
        C.entry(folder, textvariable=opts.output_folder_var, width=200,
                mono=True).pack(side="left", fill="x", expand=True)
        button(folder, "Change", variant="secondary", width=70, height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._pick_folder).pack(side="left", padx=(6, 0))
        button(folder, "Open", variant="ghost", width=54, height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._open_folder).pack(side="left", padx=(4, 0))

        C.section_label(how, "File names").pack(fill="x", padx=18, pady=(14, 6))
        naming = ctk.CTkFrame(how, fg_color="transparent")
        naming.pack(fill="x", padx=18)
        C.option_menu(naming, [label for label, _fn in NAMING_STYLES.values()],
                      variable=opts.naming_var, width=220).pack(side="left")
        self.naming_example = ctk.CTkLabel(naming, text="", font=T.font(T.SIZE_SM, mono=True),
                                           text_color=T.TEXT_DIM, anchor="w")
        self.naming_example.pack(side="left", fill="x", expand=True, padx=(10, 0))

        self._more_open = False
        self.more_btn = button(how, "▸  More options", variant="ghost", height=30,
                               anchor="w", font=T.font(T.SIZE_SM, "bold"),
                               command=self._toggle_more)
        self.more_btn.pack(fill="x", padx=12, pady=(12, 0))
        self.more = ctk.CTkFrame(how, fg_color="transparent")
        self._more_row(self.more, "Graphics card encoding",
                       C.segmented(self.more, HW_CHOICES, variable=opts.hw_var))
        self._more_row(self.more, "GIF dither", C.option_menu(
            self.more, [label for label, _k in GIF_DITHER_CHOICES],
            variable=opts.gif_dither_var, width=170))
        self._more_row(self.more, "GIF palette", C.segmented(
            self.more, [label for label, _k in GIF_STATS_CHOICES],
            variable=opts.gif_stats_var))
        self._more_row(self.more, "GIF loop", C.option_menu(
            self.more, [label for label, _k in GIF_LOOP_CHOICES],
            variable=opts.gif_loop_var, width=110))

        ctk.CTkFrame(how, height=14, fg_color="transparent").pack()

        # -- Go: summary + the button, under "What" so it's always in view.
        go = _card(left, "You'll get")
        go.pack(fill="x", pady=(16, 0))
        self.summary_label = ctk.CTkLabel(go, text="", font=T.font(T.SIZE_LG),
                                          text_color=T.TEXT, justify="left", anchor="w")
        self.summary_label.pack(fill="x", padx=18)
        self.export_btn = button(go, "Export", variant="primary", height=44,
                                 font=T.font(T.SIZE_LG, "bold"),
                                 command=self.editor._export)
        self.export_btn.pack(fill="x", padx=18, pady=(14, 18))
        return page

    def _more_row(self, parent, label, widget):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(6, 0))
        ctk.CTkLabel(row, text=label, font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED,
                     width=150, anchor="w").pack(side="left")
        widget.pack(in_=row, side="left", fill="x", expand=True)

    def _toggle_more(self):
        self._more_open = not self._more_open
        if self._more_open:
            self.more.pack(fill="x", after=self.more_btn, pady=(0, 4))
            self.more_btn.configure(text="▾  More options")
        else:
            self.more.pack_forget()
            self.more_btn.configure(text="▸  More options")

    # ------------------------------------------------------------------
    def _format_picked(self, value):
        opts = self.editor.options
        if value == "MP3":
            opts.audio_only_var.set(True)
            self.editor._mark_platform_custom()
        else:
            opts.audio_only_var.set(False)
            self.editor._on_format_change(value)
        self.refresh()

    def _pick_folder(self):
        var = self.editor.options.output_folder_var
        folder = filedialog.askdirectory(
            title="Choose where exports go",
            initialdir=var.get() or str(Path.home() / "Downloads"),
        )
        if folder:
            var.set(folder)

    def _open_folder(self):
        folder = self.editor.options.get_output_folder()
        if folder and Path(folder).exists():
            if os.name == "nt":
                os.startfile(folder)  # noqa: S606 — user-chosen folder
            else:
                subprocess.Popen(["xdg-open", folder])

    def _remove_range(self, index):
        self.editor.remove_range(index)
        self.refresh()

    def _move_range(self, index, delta):
        self.editor.move_range(index, delta)
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        if self.current != "project" or not self.winfo_exists():
            return
        ed = self.editor
        opts = ed.options
        has_video = bool(ed.video_path)

        if has_video:
            start, end = ed.timeline.get_values()
            self.selection_label.configure(
                text=f"Selection   {seconds_to_hms(start)} → {seconds_to_hms(end)}"
                     f"   ({end - start:.1f} s)")
        else:
            self.selection_label.configure(text="No video yet. Open one in Import.")

        for child in self.ranges_box.winfo_children():
            child.destroy()
        ranges = ed.range_queue.get_ranges()
        for i, (s, e) in enumerate(ranges):
            row = ctk.CTkFrame(self.ranges_box, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=f"Range {i + 1}   {seconds_to_hms(s)} → "
                                   f"{seconds_to_hms(e)}   ({e - s:.1f} s)",
                         font=T.font(T.SIZE_MD), text_color=T.TEXT,
                         anchor="w").pack(side="left", fill="x", expand=True)
            button(row, "Remove", variant="ghost", width=64, height=26,
                   font=T.font(T.SIZE_SM),
                   command=lambda k=i: self._remove_range(k)).pack(side="right")
            if len(ranges) > 1:
                # Order matters when the parts are joined into one video.
                for glyph, delta, edge in (("▼", 1, len(ranges) - 1), ("▲", -1, 0)):
                    button(row, glyph, variant="ghost", width=28, height=26,
                           font=T.font(T.SIZE_SM),
                           state="disabled" if i == edge else "normal",
                           command=lambda k=i, d=delta: self._move_range(k, d),
                           ).pack(side="right")
        if not ranges:
            C.hint(self.ranges_box, "Save more ranges in Edit (Q) to export "
                                    "several parts at once.", wrap=320).pack(anchor="w")

        current = ed.platform_var.get()
        for name, btn in self.platform_buttons.items():
            on = name == current
            btn.configure(
                fg_color=T.ACCENT_SOFT if on else T.BG_SURFACE,
                hover_color=T.ACCENT_SOFT if on else T.BG_HOVER,
                text_color=T.ACCENT_SOFT_TEXT if on else T.TEXT,
                border_color=T.ACCENT if on else T.BORDER,
            )

        audio_only = bool(opts.audio_only_var.get())
        fmt = "MP3" if audio_only else ed.format_var.get()
        self.format_seg.set(fmt)
        self.format_hint.configure(text={
            "MP4": "Video with sound. Plays everywhere.",
            "GIF": "Loops without sound. Best kept short.",
            "MP3": "Just the audio.",
        }.get(fmt, ""))
        quality = ed.quality_var.get()
        self.quality_seg.set(quality)
        self.quality_hint.configure(text=QUALITY_DETAIL.get(quality, ""))
        self.transition_dur_menu.set(f"{float(opts.transition_duration_var.get()):g}s")
        ext = {"MP4": "mp4", "GIF": "gif", "MP3": "mp3"}.get(fmt, "mp4")
        example = opts.naming_example(getattr(ed, "source_title", None) if has_video
                                      else None, ext)
        self.naming_example.configure(text=f"e.g.  {example}" if example else "")

        count = len(ranges) + (1 if has_video else 0)
        joined = bool(opts.concat_var.get()) and count > 1 and fmt == "MP4"
        files = "1 file" if joined or count == 1 else f"{count} files"
        lines = [f"{fmt} · {quality} · {files}"]
        if ed.size_estimate_text:
            lines[0] += f" · {ed.size_estimate_text}"
        color = opts.color_summary()
        if color:
            lines.append(color)
        self.summary_label.configure(text="\n".join(lines) if has_video
                                     else "Open a video to export.")
        self.export_btn.configure(
            state="normal" if has_video else "disabled",
            text=f"Export {files}" if has_video else "Export",
        )
