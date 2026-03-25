import sys
import io
import threading
from datetime import datetime

import customtkinter as ctk


class LogCapture:
    """Captures stdout/stderr and forwards to a callback while preserving original output."""

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
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = app
        self._logs = []
        self._lock = threading.Lock()

        self._build_ui()
        self._install_log_capture()

    def _build_ui(self):
        # Header with controls
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(
            header, text="Debug Log",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left")

        self.clear_btn = ctk.CTkButton(
            header, text="Clear", width=80, height=30,
            fg_color="#444", hover_color="#555",
            command=self._clear_logs,
        )
        self.clear_btn.pack(side="right", padx=(5, 0))

        self.autoscroll_var = ctk.BooleanVar(value=True)
        self.autoscroll_cb = ctk.CTkCheckBox(
            header, text="Auto-scroll", variable=self.autoscroll_var,
            font=ctk.CTkFont(size=12),
        )
        self.autoscroll_cb.pack(side="right", padx=10)

        # Log display
        self.log_text = ctk.CTkTextbox(
            self, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#1a1a2e", text_color="#cccccc",
            corner_radius=8, wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        self.log_text.configure(state="disabled")

        # Add startup message
        self.add_log("VideoKidnapper Debug Log started", "INFO")

    def _install_log_capture(self):
        sys.stdout = LogCapture(sys.__stdout__, self.add_log, "INFO")
        sys.stderr = LogCapture(sys.__stderr__, self.add_log, "ERROR")

    def add_log(self, message, tag="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with self._lock:
            entry = f"[{timestamp}] [{tag}] {message}"
            self._logs.append(entry)

        if self.winfo_exists():
            self.after(0, self._append_to_display, entry, tag)

    def _append_to_display(self, entry, tag):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", entry + "\n")
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
