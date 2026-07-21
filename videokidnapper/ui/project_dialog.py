# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Project actions and crash-recovery prompts."""

from pathlib import Path

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button
from videokidnapper.utils import project_files, settings


class ProjectDialog(ctk.CTkToplevel):
    def __init__(self, master, editor, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = editor
        self.title("VideoKidnapper Projects")
        self.geometry("600x440")
        self.configure(fg_color=T.BG_BASE)
        self.transient(master)
        self.grab_set()

        card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(
            card, text="Projects",
            font=T.font(T.SIZE_XL, "bold"), text_color=T.TEXT,
        ).pack(anchor="w", padx=18, pady=(16, 2))
        current = (
            Path(editor.current_project_path).name
            if editor.current_project_path else "Untitled project"
        )
        state = "Unsaved changes" if editor._project_dirty else "All changes saved"
        ctk.CTkLabel(
            card, text=f"{current}  ·  {state}",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED,
        ).pack(anchor="w", padx=18)

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(16, 12))
        button(
            actions, "Open project", variant="primary", width=140,
            command=self._open,
        ).pack(side="left")
        button(
            actions, "Save", variant="secondary", width=100,
            command=lambda: self._save(False),
        ).pack(side="left", padx=(8, 0))
        button(
            actions, "Save as", variant="secondary", width=110,
            command=lambda: self._save(True),
        ).pack(side="left", padx=(8, 0))
        button(
            actions, "Close", variant="ghost", width=90,
            command=self.destroy,
        ).pack(side="right")

        ctk.CTkLabel(
            card, text="RECENT PROJECTS",
            font=T.font(T.SIZE_XS, "bold"), text_color=T.TEXT_DIM,
        ).pack(anchor="w", padx=18, pady=(4, 6))
        recent = settings.get_recent_projects()
        if not recent:
            ctk.CTkLabel(
                card, text="Saved projects will appear here.",
                font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
            ).pack(anchor="w", padx=18, pady=12)
        else:
            recent_frame = ctk.CTkScrollableFrame(
                card, fg_color="transparent", height=220,
                scrollbar_button_color=T.BG_HOVER,
                scrollbar_button_hover_color=T.BG_ACTIVE,
            )
            recent_frame.pack(fill="both", expand=True, padx=14, pady=(0, 14))
            for path in recent:
                project_path = Path(path)
                row = ctk.CTkFrame(
                    recent_frame, fg_color=T.BG_RAISED,
                    corner_radius=T.RADIUS_MD,
                )
                row.pack(fill="x", pady=3)
                ctk.CTkLabel(
                    row, text=project_path.name, anchor="w",
                    font=T.font(T.SIZE_MD, "bold"), text_color=T.TEXT,
                ).pack(side="left", fill="x", expand=True, padx=12, pady=10)
                button(
                    row, "Open", variant="ghost", width=70, height=28,
                    command=lambda value=path: self._open_recent(value),
                ).pack(side="right", padx=8)

        self.after(50, self._center)

    def _center(self):
        self.update_idletasks()
        owner = self.master.winfo_toplevel()
        x = owner.winfo_rootx() + max(0, (owner.winfo_width() - self.winfo_width()) // 2)
        y = owner.winfo_rooty() + max(0, (owner.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")

    def _open(self):
        if self.editor.choose_and_open_project():
            self.destroy()

    def _open_recent(self, path):
        if self.editor.open_project(path):
            self.destroy()

    def _save(self, save_as):
        if self.editor.save_project(save_as=save_as):
            self.destroy()


class RecoveryDialog(ctk.CTkToplevel):
    def __init__(self, master, editor, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = editor
        self.title("Recover VideoKidnapper Project")
        self.geometry("500x250")
        self.resizable(False, False)
        self.configure(fg_color=T.BG_BASE)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._discard)

        card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(
            card, text="Recover unsaved work?",
            font=T.font(T.SIZE_XL, "bold"), text_color=T.TEXT,
        ).pack(anchor="w", padx=20, pady=(20, 6))
        ctk.CTkLabel(
            card,
            text="VideoKidnapper found an autosave from a session that did not "
                 "close normally. Recover it, or discard it and start clean.",
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
            justify="left", wraplength=430,
        ).pack(anchor="w", padx=20)
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(22, 18))
        button(
            actions, "Recover project", variant="primary", width=160,
            command=self._recover,
        ).pack(side="left")
        button(
            actions, "Discard autosave", variant="ghost", width=150,
            command=self._discard,
        ).pack(side="right")
        self.after(50, self._center)

    def _center(self):
        self.update_idletasks()
        owner = self.master.winfo_toplevel()
        x = owner.winfo_rootx() + max(0, (owner.winfo_width() - self.winfo_width()) // 2)
        y = owner.winfo_rooty() + max(0, (owner.winfo_height() - self.winfo_height()) // 2)
        self.geometry(f"+{x}+{y}")

    def _recover(self):
        if self.editor.open_project(project_files.autosave_path(), recovery=True):
            self.destroy()

    def _discard(self):
        self.editor.discard_recovery()
        self.destroy()
