# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""First-run welcome that gets users to a useful action quickly."""

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button
from videokidnapper.utils import settings


class OnboardingDialog(ctk.CTkToplevel):
    def __init__(self, master, editor, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = editor
        self.title("Welcome to VideoKidnapper")
        self.geometry("640x430")
        self.resizable(False, False)
        self.configure(fg_color=T.BG_BASE)
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self._finish)

        card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card, text="Make your first clip",
            font=T.font(T.SIZE_HERO, "bold"), text_color=T.TEXT,
        ).pack(anchor="w", padx=24, pady=(22, 4))
        ctk.CTkLabel(
            card,
            text="The three steps across the top of the window are the whole app: "
                 "bring a clip in, edit it, export it.",
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
            justify="left", wraplength=560,
        ).pack(anchor="w", padx=24)

        steps = ctk.CTkFrame(card, fg_color="transparent")
        steps.pack(fill="x", padx=24, pady=(22, 18))
        for number, title, detail in (
            ("1", "Import", "Open a file, record your screen, or paste a link."),
            ("2", "Edit", "Pick the part on the timeline; add captions and images."),
            ("3", "Export", "Choose where it's going and make an MP4, GIF or MP3."),
        ):
            row = ctk.CTkFrame(steps, fg_color=T.BG_RAISED, corner_radius=T.RADIUS_MD)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row, text=number, width=34,
                font=T.font(T.SIZE_LG, "bold"), text_color=T.TEXT_ON_ACCENT,
                fg_color=T.ACCENT, corner_radius=14,
            ).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(
                row, text=title, width=120, anchor="w",
                font=T.font(T.SIZE_MD, "bold"), text_color=T.TEXT,
            ).pack(side="left", padx=(4, 8))
            ctk.CTkLabel(
                row, text=detail, anchor="w",
                font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED,
            ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            card,
            text="Private by design: editing stays on this computer. No account, "
                 "upload, or watermark.",
            font=T.font(T.SIZE_SM, "bold"), text_color=T.SUCCESS,
        ).pack(anchor="w", padx=24, pady=(0, 14))

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=24, pady=(0, 22))
        button(
            actions, "Open a video", variant="primary", width=150,
            command=self._open_video,
        ).pack(side="left")
        button(
            actions, "Use a web link", variant="secondary", width=170,
            command=self._open_web,
        ).pack(side="left", padx=(8, 0))
        button(
            actions, "Explore first", variant="ghost", width=120,
            command=self._finish,
        ).pack(side="right")

        self.after(50, self._center)

    def _center(self):
        self.update_idletasks()
        owner = self.master.winfo_toplevel()
        x = owner.winfo_rootx() + max(0, (owner.winfo_width() - self.winfo_width()) // 2)
        y = owner.winfo_rooty() + max(0, (owner.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")
        self.lift()
        self.focus_force()

    def _remember(self):
        settings.set("onboarding_complete", True)

    def _open_video(self):
        self._remember()
        self.destroy()
        self.editor.keyboard_open()

    def _open_web(self):
        self._remember()
        self.destroy()
        self.editor._show_workspace("import")
        if self.editor.download_bar is not None:
            self.editor.download_bar.url_entry.focus_set()

    def _finish(self):
        self._remember()
        self.destroy()
