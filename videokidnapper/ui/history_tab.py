"""Recent exports tab — shows the history list stored in settings."""

import os
import subprocess
from pathlib import Path

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button
from videokidnapper.utils import settings
from videokidnapper.utils.size_estimator import human_bytes


class HistoryTab(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        header = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        header.pack(fill="x", padx=12, pady=(12, 6))

        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        title_col = ctk.CTkFrame(inner, fg_color="transparent")
        title_col.pack(side="left")

        ctk.CTkLabel(
            title_col, text="Recent Exports",
            font=T.font(T.SIZE_XL, "bold"), text_color=T.TEXT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_col,
            text="Most recent 25 exports across all tabs",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(anchor="w")

        button(inner, "Refresh", variant="secondary",
               width=90, height=30, command=self.refresh).pack(side="right", padx=(4, 0))
        button(inner, "Clear", variant="danger",
               width=90, height=30, command=self._clear).pack(side="right")

        self.list_container = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        self.list_container.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.empty_label = ctk.CTkLabel(
            self.list_container,
            text="No exports yet — finish a trim or URL export to see it here.",
            font=T.font(T.SIZE_MD), text_color=T.TEXT_DIM,
        )

    # ------------------------------------------------------------------
    def refresh(self):
        for child in self.list_container.winfo_children():
            child.destroy()

        entries = settings.get_history()
        if not entries:
            self.empty_label = ctk.CTkLabel(
                self.list_container,
                text="No exports yet — finish a trim or URL export to see it here.",
                font=T.font(T.SIZE_MD), text_color=T.TEXT_DIM,
            )
            self.empty_label.pack(pady=40)
            return

        for entry in entries:
            self._render_entry(entry)

    def _render_entry(self, entry):
        path = entry.get("path", "")
        exists = bool(path) and Path(path).exists()

        row = ctk.CTkFrame(
            self.list_container, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_MD,
        )
        row.pack(fill="x", pady=4)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=14, pady=10)

        name = os.path.basename(path) if path else "Unknown"
        ctk.CTkLabel(
            info, text=name,
            font=T.font(T.SIZE_MD, "bold", mono=True),
            text_color=T.TEXT if exists else T.TEXT_DIM, anchor="w",
        ).pack(anchor="w")

        meta_parts = [
            entry.get("format", ""),
            entry.get("preset", ""),
            entry.get("timestamp", ""),
        ]
        if not exists:
            meta_parts.append("(missing)")
        ctk.CTkLabel(
            info, text="   ·   ".join(p for p in meta_parts if p),
            font=T.font(T.SIZE_SM),
            text_color=T.TEXT_DIM, anchor="w",
        ).pack(anchor="w")

        size = entry.get("size_bytes")
        if size:
            ctk.CTkLabel(
                info, text=human_bytes(size),
                font=T.font(T.SIZE_XS, mono=True),
                text_color=T.TEXT_DIM, anchor="w",
            ).pack(anchor="w")

        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(side="right", padx=10, pady=8)

        button(
            btns, "Open", variant="secondary",
            width=70, height=28,
            command=lambda p=path: self._open(p),
            state="normal" if exists else "disabled",
        ).pack(side="left", padx=3)

        button(
            btns, "Reveal", variant="ghost",
            width=80, height=28,
            command=lambda p=path: self._reveal(p),
            state="normal" if exists else "disabled",
        ).pack(side="left", padx=3)

    def _open(self, path):
        if not path or not Path(path).exists():
            return
        if os.name == "nt":
            os.startfile(path)  # noqa: S606 — user's own file
        else:
            subprocess.Popen(["xdg-open", path])

    def _reveal(self, path):
        if not path:
            return
        if os.name == "nt":
            subprocess.Popen(["explorer", "/select,", str(path)])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])

    def _clear(self):
        settings.clear_history()
        self.refresh()
