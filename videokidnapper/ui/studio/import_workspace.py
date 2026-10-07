# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Studio Import workspace: every way to bring a clip in, on one page.

Paste a link (the existing :class:`DownloadBar`, including its batch
list and browser-cookie picker), open a file, record the screen, or
reopen a recent project. Whatever loads lands in Edit.
"""

from pathlib import Path

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.source_bar import DownloadBar
from videokidnapper.ui.studio import controls as C
from videokidnapper.ui.theme import button
from videokidnapper.utils import settings


def _card(parent, **kwargs):
    return ctk.CTkFrame(parent, fg_color=T.BG_SURFACE, corner_radius=T.RADIUS_LG,
                        border_width=1, border_color=T.BORDER, **kwargs)


class ImportWorkspace(ctk.CTkScrollableFrame):
    def __init__(self, master, app, editor, **kwargs):
        super().__init__(master, fg_color=T.BG_BASE, corner_radius=0,
                         scrollbar_button_color=T.BG_HOVER,
                         scrollbar_button_hover_color=T.BG_ACTIVE, **kwargs)
        self.app = app
        self.editor = editor

        page = ctk.CTkFrame(self, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=40, pady=(32, 24))
        page.grid_columnconfigure(0, weight=3)
        page.grid_columnconfigure(1, weight=2, minsize=320)

        intro = ctk.CTkFrame(page, fg_color="transparent")
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        ctk.CTkLabel(intro, text="Start with a video", font=T.font(26, "bold"),
                     text_color=T.TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            intro,
            text="Bring a clip in from the web, a file, or your screen. Trimming, "
                 "captions and crops happen in Edit. Export makes the MP4, GIF or MP3.",
            font=T.font(T.SIZE_LG), text_color=T.TEXT_MUTED, anchor="w",
            justify="left", wraplength=760,
        ).pack(anchor="w", pady=(4, 0))

        left = ctk.CTkFrame(page, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 20))

        link = _card(left)
        link.pack(fill="x")
        ctk.CTkLabel(link, text="Paste a link", font=T.font(T.SIZE_XL, "bold"),
                     text_color=T.TEXT).pack(anchor="w", padx=20, pady=(18, 8))
        self.download_bar = DownloadBar(
            link, on_video_ready=editor._on_downloaded_video,
            notify=editor._notify,
        )
        self.download_bar.pack(fill="x", padx=20, pady=(0, 18))
        editor.download_bar = self.download_bar

        row = ctk.CTkFrame(left, fg_color="transparent")
        row.pack(fill="x", pady=(18, 0))
        row.grid_columnconfigure((0, 1), weight=1, uniform="cards")

        file_card = _card(row)
        file_card.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        ctk.CTkLabel(file_card, text="Open a file", font=T.font(T.SIZE_XL, "bold"),
                     text_color=T.TEXT).pack(anchor="w", padx=20, pady=(18, 4))
        C.hint(file_card, "A video or GIF from this computer. You can also drop a "
                          "file on the Edit preview.", wrap=300).pack(anchor="w", padx=20)
        button(file_card, "Browse files…   Ctrl+O", variant="primary", height=34,
               command=editor._open_file).pack(anchor="w", padx=20, pady=(14, 18))

        rec_card = _card(row)
        rec_card.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        ctk.CTkLabel(rec_card, text="Record your screen", font=T.font(T.SIZE_XL, "bold"),
                     text_color=T.TEXT).pack(anchor="w", padx=20, pady=(18, 4))
        C.hint(rec_card, "Captures the main monitor at 15 fps, for up to two "
                         "minutes. The window hides while it records.",
               wrap=300).pack(anchor="w", padx=20)
        button(rec_card, "Set up recording…", variant="secondary", height=34,
               command=editor._record_screen).pack(anchor="w", padx=20, pady=(14, 18))

        right = _card(page)
        right.grid(row=1, column=1, sticky="new")
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 8))
        ctk.CTkLabel(head, text="Recent projects", font=T.font(T.SIZE_XL, "bold"),
                     text_color=T.TEXT).pack(side="left")
        button(head, "Open project…", variant="secondary", height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=editor.choose_and_open_project).pack(side="right")
        self.recent_list = ctk.CTkFrame(right, fg_color="transparent")
        self.recent_list.pack(fill="x", padx=12, pady=(0, 16))
        self.refresh()

    def refresh(self):
        for child in self.recent_list.winfo_children():
            child.destroy()
        projects = settings.get_recent_projects()[:6]
        if not projects:
            C.hint(self.recent_list, "Projects you save (Ctrl+S) show up here.",
                   wrap=300).pack(anchor="w", padx=8, pady=(0, 4))
            return
        for path in projects:
            p = Path(path)
            row = ctk.CTkFrame(self.recent_list, fg_color="transparent",
                               corner_radius=T.RADIUS_MD)
            row.pack(fill="x", pady=1)
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, padx=8, pady=6)
            ctk.CTkLabel(text, text=p.stem, font=T.font(T.SIZE_MD, "bold"),
                         text_color=T.TEXT, anchor="w").pack(fill="x")
            ctk.CTkLabel(text, text=str(p.parent), font=T.font(T.SIZE_SM),
                         text_color=T.TEXT_MUTED, anchor="w").pack(fill="x")
            button(row, "Open", variant="ghost", width=56, height=28,
                   text_color=T.ACCENT, font=T.font(T.SIZE_SM, "bold"),
                   command=lambda q=str(p): self.editor.open_project(q)).pack(
                side="right", padx=(0, 6))
