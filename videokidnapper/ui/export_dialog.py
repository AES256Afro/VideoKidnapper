import os
import subprocess
import threading

import customtkinter as ctk


class ExportDialog(ctk.CTkToplevel):
    """Modal progress dialog for export operations."""

    def __init__(self, master, title="Exporting...", **kwargs):
        super().__init__(master, **kwargs)
        self.title(title)
        self.geometry("420x200")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.grab_set()

        self.cancel_event = threading.Event()
        self._result = None

        # Center on parent
        self.update_idletasks()
        pw = master.winfo_toplevel()
        x = pw.winfo_x() + (pw.winfo_width() - 420) // 2
        y = pw.winfo_y() + (pw.winfo_height() - 200) // 2
        self.geometry(f"+{x}+{y}")

        # UI
        self.status_label = ctk.CTkLabel(
            self, text="Preparing export...",
            font=ctk.CTkFont(size=14),
        )
        self.status_label.pack(pady=(25, 10))

        self.progress = ctk.CTkProgressBar(self, width=350, height=14)
        self.progress.pack(pady=10)
        self.progress.set(0)

        self.percent_label = ctk.CTkLabel(
            self, text="0%", font=ctk.CTkFont(size=12), text_color="gray",
        )
        self.percent_label.pack(pady=(0, 10))

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=5)

        self.cancel_btn = ctk.CTkButton(
            self.btn_frame, text="Cancel", width=100,
            fg_color="#e84a1a", hover_color="#c43e15",
            command=self._on_cancel,
        )
        self.cancel_btn.pack(side="left", padx=5)

        self.open_btn = ctk.CTkButton(
            self.btn_frame, text="Open Folder", width=120,
            command=self._open_folder, state="disabled",
        )
        self.open_btn.pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def update_progress(self, value, status_text=None):
        if self.winfo_exists():
            self.progress.set(value)
            self.percent_label.configure(text=f"{int(value * 100)}%")
            if status_text:
                self.status_label.configure(text=status_text)

    def export_complete(self, output_path):
        self._result = output_path
        if self.winfo_exists():
            self.progress.set(1.0)
            self.percent_label.configure(text="100%")
            fname = os.path.basename(output_path) if output_path else "Unknown"
            self.status_label.configure(text=f"Saved: {fname}")
            self.cancel_btn.configure(text="Close", fg_color="#333", hover_color="#444")
            self.open_btn.configure(state="normal")

    def export_failed(self, error_msg="Export failed"):
        if self.winfo_exists():
            self.status_label.configure(text=error_msg)
            self.cancel_btn.configure(text="Close", fg_color="#333", hover_color="#444")

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
