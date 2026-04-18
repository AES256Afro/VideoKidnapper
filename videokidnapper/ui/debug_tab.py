# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import sys
import threading
from datetime import datetime

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button


class LogCapture:
    """Forwards writes to the original stream and a callback."""

    def __init__(self, original, callback, tag="INFO"):
        self.original = original
        self.callback = callback
        self.tag = tag

    def write(self, text):
        if self.original:
            self.original.write(text)
        if text.strip():
            self.callback(text.strip(), self.tag)

    def flush(self):
        if self.original:
            self.original.flush()


class DebugTab(ctk.CTkFrame):
    _LEVEL_COLORS = {
        "INFO":    T.ACCENT_GLOW,
        "WARN":    T.WARN,
        "WARNING": T.WARN,
        "ERROR":   T.DANGER,
        "DEBUG":   T.TEXT_DIM,
    }

    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._logs = []
        self._lock = threading.Lock()

        self._build_ui()
        self._install_log_capture()

    def _build_ui(self):
        # Header card
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
            title_col, text="Debug Console",
            font=T.font(T.SIZE_XL, "bold"),
            text_color=T.TEXT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_col, text="Captures stdout + stderr with level coloring",
            font=T.font(T.SIZE_SM),
            text_color=T.TEXT_DIM,
        ).pack(anchor="w")

        self.clear_btn = button(
            inner, "Clear", variant="secondary",
            width=80, height=30, command=self._clear_logs,
        )
        self.clear_btn.pack(side="right", padx=(5, 0))

        self.autoscroll_var = ctk.BooleanVar(value=True)
        self.autoscroll_cb = ctk.CTkCheckBox(
            inner, text="Auto-scroll",
            variable=self.autoscroll_var,
            font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED,
            fg_color=T.ACCENT, hover_color=T.ACCENT_HOVER,
            border_color=T.BORDER_STRONG,
        )
        self.autoscroll_cb.pack(side="right", padx=10)

        # Log body
        body = ctk.CTkFrame(
            self, fg_color=T.BG_BASE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        body.pack(fill="both", expand=True, padx=12, pady=(6, 12))

        self.log_text = ctk.CTkTextbox(
            body,
            font=T.font(T.SIZE_MD, mono=True),
            fg_color=T.BG_BASE,
            text_color=T.TEXT_MUTED,
            corner_radius=T.RADIUS_MD,
            wrap="word",
            border_width=0,
        )
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

        # Register color tags on the underlying Tk Text widget
        tk_text = self.log_text._textbox
        for level, color in self._LEVEL_COLORS.items():
            tk_text.tag_configure(f"level_{level}", foreground=color)
        tk_text.tag_configure("timestamp", foreground=T.TEXT_DIM)

        self.log_text.configure(state="disabled")

        self.add_log("VideoKidnapper debug console ready", "INFO")

    def _install_log_capture(self):
        sys.stdout = LogCapture(sys.__stdout__, self.add_log, "INFO")
        sys.stderr = LogCapture(sys.__stderr__, self.add_log, "ERROR")

    def add_log(self, message, tag="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with self._lock:
            entry = (timestamp, tag, message)
            self._logs.append(entry)

        if self.winfo_exists():
            self.after(0, self._append_to_display, timestamp, tag, message)

    def _append_to_display(self, timestamp, tag, message):
        tk_text = self.log_text._textbox
        self.log_text.configure(state="normal")
        tk_text.insert("end", f"[{timestamp}] ", ("timestamp",))
        level_tag = f"level_{tag}" if tag in self._LEVEL_COLORS else "level_INFO"
        tk_text.insert("end", f"[{tag:5s}] ", (level_tag,))
        tk_text.insert("end", f"{message}\n")
        self.log_text.configure(state="disabled")

        if self.autoscroll_var.get():
            self.log_text.see("end")

    def _clear_logs(self):
        with self._lock:
            self._logs.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.add_log("Log cleared", "INFO")

    def destroy(self):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        super().destroy()
