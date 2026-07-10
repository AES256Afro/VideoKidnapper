# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""DownloadBar — the "get a video from a link" strip.

Extracted from the old URL tab so the app needs only ONE editor: the
Kidnap & Trim tab embeds this bar above the player, and a finished
download flows into the same trim/caption/export pipeline a local file
uses. Contains the URL entry + platform detection, cookies selection,
yt-dlp self-update, download progress, and the batch queue.
"""
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.config import SUPPORTED_PLATFORMS
from videokidnapper.core.downloader import (
    OFFLINE_MESSAGE, cleanup_temp, detect_platform, download_video,
    resolve_cookies,
)
from videokidnapper.ui import theme as T
from videokidnapper.ui.batch_queue import BatchPanel
from videokidnapper.ui.theme import button
from videokidnapper.ui.widgets import PlatformChip
from videokidnapper.utils import settings

COOKIE_FILE_CHOICE = "Cookies file…"
BROWSER_CHOICES = ["(no cookies)", "chrome", "firefox", "edge", "brave", "opera",
                   COOKIE_FILE_CHOICE]


def _cookie_file_label(path):
    name = Path(path).name
    if len(name) > 18:
        name = name[:15] + "..."
    return f"file: {name}"


class DownloadBar(ctk.CTkFrame):
    """URL → downloaded file, reported via ``on_video_ready(path, platform, title)``."""

    def __init__(self, master, on_video_ready, notify=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._on_video_ready = on_video_ready
        self._notify_cb = notify
        self._download_cancel = threading.Event()
        self._platform_chips = {}
        self._build_ui()

    def _notify(self, message, level="info"):
        if self._notify_cb:
            self._notify_cb(message, level)

    # ------------------------------------------------------------------
    def _build_ui(self):
        # Passive platform indicators — light up when the URL matches.
        chip_row = ctk.CTkFrame(self, fg_color="transparent")
        chip_row.pack(fill="x")
        ctk.CTkLabel(
            chip_row, text="Kidnap from",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(side="left", padx=(0, 8))
        for platform in SUPPORTED_PLATFORMS.keys():
            chip = PlatformChip(chip_row, platform)
            chip.pack(side="left", padx=3)
            self._platform_chips[platform] = chip
        ctk.CTkLabel(
            chip_row, text="…and most sites yt-dlp knows",
            font=T.font(T.SIZE_XS), text_color=T.TEXT_DIM,
        ).pack(side="left", padx=(8, 0))

        input_row = ctk.CTkFrame(self, fg_color="transparent")
        input_row.pack(fill="x", pady=(8, 0))

        self.url_entry = ctk.CTkEntry(
            input_row,
            placeholder_text="Paste a video or GIF link  (Ctrl+V anywhere, Enter to download)",
            font=T.font(T.SIZE_MD),
            height=T.INPUT_HEIGHT,
            fg_color=T.BG_RAISED,
            border_color=T.BORDER_STRONG,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.url_entry.bind("<Return>", lambda e: self._download())
        self.url_entry.bind("<KeyRelease>", self._on_url_typed)

        button(
            input_row, "Paste", variant="secondary",
            width=80, height=32, command=self._paste_from_clipboard,
        ).pack(side="left", padx=(0, 6))

        self.download_btn = button(
            input_row, "  ⬇  Download", variant="primary",
            width=140, height=34, command=self._download,
        )
        self.download_btn.pack(side="left")

        cookie_row = ctk.CTkFrame(self, fg_color="transparent")
        cookie_row.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(
            cookie_row, text="Cookies from",
            font=T.font(T.SIZE_SM), text_color=T.TEXT_DIM,
        ).pack(side="left", padx=(0, 4))
        self.cookies_var = ctk.StringVar(value=self._cookie_label_from_settings())
        ctk.CTkOptionMenu(
            cookie_row, variable=self.cookies_var, values=BROWSER_CHOICES, width=130,
            fg_color=T.BG_RAISED, button_color=T.BG_HOVER,
            button_hover_color=T.BG_ACTIVE, text_color=T.TEXT,
            dropdown_fg_color=T.BG_RAISED, dropdown_text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
            command=self._on_cookies_change,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            cookie_row,
            text="(needed for some Instagram / private X videos)",
            font=T.font(T.SIZE_XS), text_color=T.TEXT_DIM,
        ).pack(side="left")

        self.update_ytdlp_btn = button(
            cookie_row, "⟳ Update yt-dlp", variant="ghost",
            width=120, height=26, command=self._update_ytdlp,
        )
        self.update_ytdlp_btn.pack(side="right")

        self.status_label = ctk.CTkLabel(
            self, text="", font=T.font(T.SIZE_SM),
            text_color=T.TEXT_DIM, anchor="w",
        )
        self.status_label.pack(fill="x", pady=(4, 0))

        self.download_progress = ctk.CTkProgressBar(
            self, height=6,
            progress_color=T.ACCENT, fg_color=T.BG_RAISED, corner_radius=3,
        )
        self.download_progress.pack(fill="x", pady=(2, 0))
        self.download_progress.set(0)

        # Batch queue (collapsible) — many links, download sequentially,
        # "Use" loads any finished row into the editor below.
        self.batch = BatchPanel(
            self,
            get_cookies=self._get_cookies,
            on_video_selected=lambda p: self._on_video_ready(p, None, None),
        )
        self.batch.pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------------
    # Cookies
    # ------------------------------------------------------------------
    def _cookie_label_from_settings(self):
        cookie_file = settings.get("cookies_file") or ""
        if cookie_file:
            return _cookie_file_label(cookie_file)
        return settings.get("cookies_browser") or "(no cookies)"

    def _on_cookies_change(self, value):
        if value == COOKIE_FILE_CHOICE:
            path = filedialog.askopenfilename(
                title="Choose a cookies.txt export",
                filetypes=[("Cookies file", "*.txt"), ("All files", "*.*")],
            )
            if path:
                settings.update({"cookies_file": path, "cookies_browser": ""})
                self.cookies_var.set(_cookie_file_label(path))
                self._notify(f"Using cookies file: {Path(path).name}", "info")
            else:
                self.cookies_var.set(self._cookie_label_from_settings())
        elif value == "(no cookies)":
            settings.update({"cookies_browser": "", "cookies_file": ""})
        else:
            settings.update({"cookies_browser": value, "cookies_file": ""})

    def _get_cookies(self):
        return resolve_cookies(
            settings.get("cookies_browser") or "",
            settings.get("cookies_file") or "",
        )

    # ------------------------------------------------------------------
    # URL entry
    # ------------------------------------------------------------------
    def receive_url(self, url):
        """Fill the entry (app-level Ctrl+V router or any other source)."""
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)
        self.url_entry.focus_set()
        self._on_url_typed(None)
        self._notify("Link pasted — press Enter or click Download", "info")

    def _paste_from_clipboard(self):
        try:
            data = self.clipboard_get()
        except Exception:
            data = ""
        if data:
            self.receive_url(data.strip())

    def _on_url_typed(self, _event=None):
        url = self.url_entry.get().strip()
        platform = detect_platform(url)
        for name, chip in self._platform_chips.items():
            chip.set_active(name == platform)
        if url and not platform:
            self.status_label.configure(
                text="Unrecognized site — yt-dlp will still try",
                text_color=T.TEXT_DIM)
        else:
            self.status_label.configure(text="")

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------
    def _download(self):
        url = self.url_entry.get().strip()
        if not url:
            self.status_label.configure(text="Paste a link first", text_color=T.DANGER)
            self._notify("No URL provided", "warn")
            return

        platform = detect_platform(url)
        self._download_cancel.clear()
        self.download_btn.configure(state="disabled", text="  Downloading...")
        self.url_entry.configure(state="disabled")
        label = f"Fetching {platform} video..." if platform else "Fetching video..."
        self.status_label.configure(text=label, text_color=T.TEXT_MUTED)
        self.download_progress.set(0)
        self._notify(label, "info")

        cookies = self._get_cookies()

        def run_download():
            def progress_cb(value, text=""):
                if self.winfo_exists():
                    self.after(0, self._update_download_progress, value, text)

            result = download_video(
                url,
                progress_callback=progress_cb,
                cancel_event=self._download_cancel,
                cookies=cookies,
            )
            if self.winfo_exists():
                self.after(0, self._on_download_complete, result)

        threading.Thread(target=run_download, daemon=True).start()

    def _update_download_progress(self, value, text):
        self.download_progress.set(value)
        if text:
            self.status_label.configure(text=text, text_color=T.TEXT_MUTED)

    def _on_download_complete(self, result):
        self.download_btn.configure(state="normal", text="  ⬇  Download")
        self.url_entry.configure(state="normal")

        if result.get("error"):
            if result["error"] == "cancelled":
                self.status_label.configure(text="Download cancelled", text_color=T.TEXT_DIM)
                self._notify("Download cancelled", "warn")
            elif result["error"] == OFFLINE_MESSAGE:
                # Being offline is an expected state, not a failure — present
                # it calmly (no red "Error:" prefix) so the app reads as
                # working-as-intended without a connection.
                self.status_label.configure(text=OFFLINE_MESSAGE, text_color=T.WARN)
                self._notify("You're offline — connect to download", "warn")
            else:
                error_text = f"Error: {result['error'][:160]}"
                from videokidnapper.utils import ytdlp_update
                if ytdlp_update.looks_like_extractor_failure(result["error"]):
                    error_text += "  — yt-dlp may be outdated; try ⟳ Update yt-dlp"
                self.status_label.configure(text=error_text, text_color=T.DANGER)
                self._notify(f"Download failed: {result['error'][:60]}", "error")
            self.download_progress.set(0)
            return

        path = result.get("path")
        if not path:
            self.status_label.configure(text="Error: No file downloaded", text_color=T.DANGER)
            self._notify("No file downloaded", "error")
            return

        self.download_progress.set(1.0)
        self.status_label.configure(text="", text_color=T.TEXT_DIM)
        self._on_video_ready(path, result.get("platform"), result.get("title"))

    # ------------------------------------------------------------------
    def _update_ytdlp(self):
        from videokidnapper.utils import ytdlp_update

        self.update_ytdlp_btn.configure(state="disabled", text="Updating...")
        self.status_label.configure(text="Updating yt-dlp...", text_color=T.TEXT_MUTED)

        def worker():
            ok, msg = ytdlp_update.update_via_pip()
            if self.winfo_exists():
                self.after(0, self._on_ytdlp_updated, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_ytdlp_updated(self, ok, msg):
        self.update_ytdlp_btn.configure(state="normal", text="⟳ Update yt-dlp")
        self.status_label.configure(
            text=msg[:100], text_color=T.TEXT_MUTED if ok else T.DANGER)
        self._notify(msg[:100], "info" if ok else "error")

    # ------------------------------------------------------------------
    def destroy(self):
        self._download_cancel.set()
        cleanup_temp()
        super().destroy()
