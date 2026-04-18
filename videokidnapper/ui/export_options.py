# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Shared export options panel.

Reads defaults from settings on construction and writes back on any change
so the next launch remembers everything. The ``on_change`` callback lets
parent tabs re-run the size estimator.
"""

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button
from videokidnapper.utils import settings


SPEED_CHOICES = ["0.25x", "0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x", "3x", "4x"]
ROTATE_CHOICES = ["0°", "90°", "180°", "270°"]
ASPECT_CHOICES = ["Source", "1:1", "9:16", "16:9", "4:5", "3:4"]
FADE_CHOICES = ["Off", "0.25s", "0.5s", "1s"]
HW_CHOICES = ["auto", "off"]


def _speed_to_float(label):
    try:
        return float(label.rstrip("x"))
    except ValueError:
        return 1.0


def _rotate_to_int(label):
    try:
        return int(label.rstrip("°"))
    except ValueError:
        return 0


def _fade_to_seconds(label):
    if label == "Off":
        return 0.0
    try:
        return float(label.rstrip("s"))
    except ValueError:
        return 0.0


def _seconds_to_fade_label(value):
    if value <= 0:
        return "Off"
    for label in FADE_CHOICES[1:]:
        if abs(_fade_to_seconds(label) - value) < 0.01:
            return label
    return "Off"


class ExportOptionsPanel(ctk.CTkFrame):
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
        self._on_change = on_change
        self._expanded = False

        self.output_folder_var = ctk.StringVar(value=settings.get("output_folder"))
        self.speed_var  = ctk.StringVar(value=f"{settings.get('speed', 1.0)}x")
        self.rotate_var = ctk.StringVar(value=f"{settings.get('rotate', 0)}°")
        self.mute_var   = ctk.BooleanVar(value=settings.get("mute_audio", False))
        self.audio_only_var = ctk.BooleanVar(value=settings.get("audio_only", False))
        self.aspect_var = ctk.StringVar(value=settings.get("aspect_preset", "Source"))
        self.concat_var = ctk.BooleanVar(value=settings.get("concat_ranges", False))
        self.fade_var   = ctk.StringVar(value=_seconds_to_fade_label(settings.get("text_fade", 0.0)))
        self.hw_var     = ctk.StringVar(value=settings.get("hw_encoder", "auto"))

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        self.toggle_btn = ctk.CTkButton(
            self,
            text=f"  {self._CHEVRON_CLOSED}   Export Options",
            font=T.font(T.SIZE_LG, "bold"),
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_MD,
            height=40, anchor="w",
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", padx=4, pady=4)

        self.body = ctk.CTkFrame(self, fg_color="transparent")

        # --- Row: Output folder -------------------------------------------
        row1 = ctk.CTkFrame(self.body, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(6, 4))

        ctk.CTkLabel(
            row1, text="Output folder",
            font=T.font(T.SIZE_MD, "bold"),
            text_color=T.TEXT_MUTED, width=120, anchor="w",
        ).pack(side="left")

        self.output_entry = ctk.CTkEntry(
            row1, textvariable=self.output_folder_var,
            font=T.font(T.SIZE_MD, mono=True),
            height=T.INPUT_HEIGHT,
            fg_color=T.BG_RAISED,
            border_color=T.BORDER_STRONG,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
        )
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        button(row1, "Browse", variant="secondary", width=90, height=32,
               command=self._pick_folder).pack(side="left", padx=(0, 4))
        button(row1, "Open", variant="ghost", width=70, height=32,
               command=self._open_folder).pack(side="left")

        # --- Row: Speed, rotate, aspect, fade -----------------------------
        row2 = ctk.CTkFrame(self.body, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(4, 4))

        self._menu_label(row2, "Speed")
        self._menu(row2, self.speed_var, SPEED_CHOICES, width=90).pack(side="left", padx=(0, 14))

        self._menu_label(row2, "Rotate")
        self._menu(row2, self.rotate_var, ROTATE_CHOICES, width=80).pack(side="left", padx=(0, 14))

        self._menu_label(row2, "Aspect")
        self._menu(row2, self.aspect_var, ASPECT_CHOICES, width=90).pack(side="left", padx=(0, 14))

        self._menu_label(row2, "Text fade")
        self._menu(row2, self.fade_var, FADE_CHOICES, width=90).pack(side="left")

        # --- Row: Mute, audio-only, concat, HW encoder --------------------
        row3 = ctk.CTkFrame(self.body, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(4, 10))

        ctk.CTkCheckBox(
            row3, text="Mute audio", variable=self.mute_var,
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.BORDER_STRONG,
            command=self._save,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkCheckBox(
            row3, text="Audio only (MP3)", variable=self.audio_only_var,
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.BORDER_STRONG,
            command=self._save,
        ).pack(side="left", padx=(0, 14))

        ctk.CTkCheckBox(
            row3, text="Concat queued ranges", variable=self.concat_var,
            font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.BORDER_STRONG,
            command=self._save,
        ).pack(side="left", padx=(0, 14))

        self._menu_label(row3, "HW encoder")
        self._menu(row3, self.hw_var, HW_CHOICES, width=90).pack(side="left")

    def _menu_label(self, parent, text):
        ctk.CTkLabel(
            parent, text=text,
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED,
        ).pack(side="left", padx=(0, 4))

    def _menu(self, parent, variable, values, width=100):
        return ctk.CTkOptionMenu(
            parent, variable=variable, values=values, width=width,
            fg_color=T.BG_RAISED, button_color=T.BG_HOVER,
            button_hover_color=T.BG_ACTIVE, text_color=T.TEXT,
            dropdown_fg_color=T.BG_RAISED, dropdown_text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
            command=lambda _: self._save(),
        )

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()
        chev = self._CHEVRON_OPEN if self._expanded else self._CHEVRON_CLOSED
        self.toggle_btn.configure(text=f"  {chev}   Export Options")

    # ------------------------------------------------------------------
    def _pick_folder(self):
        current = self.output_folder_var.get() or str(Path.home() / "Downloads")
        folder = filedialog.askdirectory(
            title="Choose output folder", initialdir=current,
        )
        if folder:
            self.output_folder_var.set(folder)
            self._save()

    def _open_folder(self):
        folder = self.output_folder_var.get()
        if folder and Path(folder).exists():
            import os
            import subprocess
            if os.name == "nt":
                os.startfile(folder)  # noqa: S606 — user-chosen folder
            else:
                subprocess.Popen(["xdg-open", folder])

    def _save(self, *_):
        settings.update({
            "output_folder":  self.output_folder_var.get(),
            "speed":          _speed_to_float(self.speed_var.get()),
            "rotate":         _rotate_to_int(self.rotate_var.get()),
            "mute_audio":     bool(self.mute_var.get()),
            "audio_only":     bool(self.audio_only_var.get()),
            "aspect_preset":  self.aspect_var.get(),
            "concat_ranges":  bool(self.concat_var.get()),
            "text_fade":      _fade_to_seconds(self.fade_var.get()),
            "hw_encoder":     self.hw_var.get(),
        })
        if self._on_change:
            self._on_change()

    def get_options(self):
        return {
            "speed":         _speed_to_float(self.speed_var.get()),
            "rotate":        _rotate_to_int(self.rotate_var.get()),
            "mute":          bool(self.mute_var.get()),
            "audio_only":    bool(self.audio_only_var.get()),
            "aspect_preset": self.aspect_var.get(),
            "concat":        bool(self.concat_var.get()),
            "text_fade":     _fade_to_seconds(self.fade_var.get()),
            "hw_encoder":    self.hw_var.get(),
            "crop":          settings.get("crop"),
        }

    def get_output_folder(self):
        return self.output_folder_var.get()
