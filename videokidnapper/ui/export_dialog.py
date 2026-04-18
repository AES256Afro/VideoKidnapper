import os
import subprocess
import threading

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.share_panel import SharePanel
from videokidnapper.ui.theme import button


class ExportDialog(ctk.CTkToplevel):
    """Modal progress dialog for export operations."""

    _W = 460
    _H = 260
    _H_EXPANDED = 400  # taller once the share panel is shown

    def __init__(self, master, title="Exporting...", **kwargs):
        super().__init__(master, **kwargs)
        self.title(title)
        self.geometry(f"{self._W}x{self._H}")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()
        self.configure(fg_color=T.BG_BASE)

        self.cancel_event = threading.Event()
        self._result = None

        # Center on parent
        self.update_idletasks()
        pw = master.winfo_toplevel()
        x = pw.winfo_x() + (pw.winfo_width() - self._W) // 2
        y = pw.winfo_y() + (pw.winfo_height() - self._H) // 2
        self.geometry(f"+{x}+{y}")

        # Card
        card = ctk.CTkFrame(
            self, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        # Title + icon
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(18, 6))

        self.icon_label = ctk.CTkLabel(
            top, text="⟳",
            font=T.font(T.SIZE_HERO, "bold"),
            text_color=T.ACCENT,
        )
        self.icon_label.pack(side="left", padx=(0, 12))

        self.status_label = ctk.CTkLabel(
            top, text="Preparing export...",
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT, anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        # Progress bar
        self.progress = ctk.CTkProgressBar(
            card, height=10,
            progress_color=T.ACCENT,
            fg_color=T.BG_RAISED,
            corner_radius=5,
        )
        self.progress.pack(fill="x", padx=18, pady=(6, 4))
        self.progress.set(0)

        self.percent_label = ctk.CTkLabel(
            card, text="0%",
            font=T.font(T.SIZE_SM, mono=True),
            text_color=T.TEXT_DIM, anchor="e",
        )
        self.percent_label.pack(fill="x", padx=18, pady=(0, 12))

        # Share panel slot (populated on success)
        self._card = card
        self.share_panel = None

        # Buttons
        self.btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        self.btn_frame.pack(fill="x", side="bottom", padx=18, pady=(0, 18))

        self.cancel_btn = button(
            self.btn_frame, "Cancel", variant="danger",
            width=120, command=self._on_cancel,
        )
        self.cancel_btn.pack(side="right", padx=(6, 0))

        self.open_btn = button(
            self.btn_frame, "Open in Explorer", variant="primary",
            width=160, command=self._open_folder, state="disabled",
        )
        self.open_btn.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def update_progress(self, value, status_text=None):
        if self.winfo_exists():
            self.progress.set(value)
            self.percent_label.configure(text=f"{int(value * 100)}%")
            if status_text:
                self.status_label.configure(text=status_text)

    def export_complete(self, output_path):
        self._result = output_path
        if not self.winfo_exists():
            return
        self.progress.set(1.0)
        self.percent_label.configure(text="100%")
        fname = os.path.basename(output_path) if output_path else "Unknown"
        self.status_label.configure(text=f"Saved: {fname}", text_color=T.SUCCESS)
        self.icon_label.configure(text="✓", text_color=T.SUCCESS)
        self.cancel_btn.configure(text="Close", fg_color=T.BG_RAISED,
                                  hover_color=T.BG_HOVER, text_color=T.TEXT)
        self.open_btn.configure(state="normal")

        # Reveal the share panel above the buttons and resize the window.
        if output_path and self.share_panel is None:
            divider = ctk.CTkFrame(self._card, height=1, fg_color=T.BORDER,
                                   corner_radius=0)
            divider.pack(fill="x", side="bottom", padx=18, pady=(4, 8),
                         before=self.btn_frame)
            self.share_panel = SharePanel(self._card, file_path=output_path)
            self.share_panel.pack(fill="x", side="bottom",
                                  padx=18, pady=(0, 4), before=divider)
            self.geometry(f"{self._W}x{self._H_EXPANDED}")

    def export_failed(self, error_msg="Export failed"):
        if self.winfo_exists():
            self.status_label.configure(text=error_msg, text_color=T.DANGER)
            self.icon_label.configure(text="⚠", text_color=T.DANGER)
            self.cancel_btn.configure(text="Close", fg_color=T.BG_RAISED,
                                      hover_color=T.BG_HOVER, text_color=T.TEXT)

    def _on_cancel(self):
        self.cancel_event.set()
        self.grab_release()
        self.destroy()

    def _open_folder(self):
        if self._result:
            folder = os.path.dirname(self._result)
            if os.name == "nt":
                subprocess.Popen(["explorer", "/select,", str(self._result)])
            else:
                subprocess.Popen(["xdg-open", folder])
