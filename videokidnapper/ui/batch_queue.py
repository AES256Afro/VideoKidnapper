# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Batch URL queue: paste many URLs, download sequentially, then choose one
to open in the trim workflow."""

import threading

import customtkinter as ctk

from videokidnapper.core.downloader import detect_platform, download_video
from videokidnapper.ui import theme as T
from videokidnapper.ui.theme import button


class BatchPanel(ctk.CTkFrame):
    _CHEVRON_OPEN   = "▾"
    _CHEVRON_CLOSED = "▸"

    def __init__(self, master, get_cookies=None, on_video_selected=None, **kwargs):
        super().__init__(
            master,
            fg_color=T.BG_SURFACE,
            border_width=1,
            border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
            **kwargs,
        )
        self._get_cookies = get_cookies
        self._on_video_selected = on_video_selected
        self._rows = []       # [(url, status_label, path)]
        self._expanded = False
        self._running = False
        self._cancel = threading.Event()

        self._build_ui()

    def _build_ui(self):
        self.toggle_btn = ctk.CTkButton(
            self,
            text=f"  {self._CHEVRON_CLOSED}   Batch Download",
            font=T.font(T.SIZE_LG, "bold"),
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT, corner_radius=T.RADIUS_MD,
            height=40, anchor="w",
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", padx=4, pady=4)

        self.body = ctk.CTkFrame(self, fg_color="transparent")

        self.url_text = ctk.CTkTextbox(
            self.body, height=110,
            font=T.font(T.SIZE_MD, mono=True),
            fg_color=T.BG_RAISED,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_SM,
            border_width=1, border_color=T.BORDER_STRONG,
        )
        self.url_text.pack(fill="x", padx=12, pady=(4, 6))
        self.url_text.insert("1.0", "")

        btn_row = ctk.CTkFrame(self.body, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))

        self.start_btn = button(
            btn_row, "  ⬇  Download All", variant="primary",
            width=170, height=32, command=self._start,
        )
        self.start_btn.pack(side="left")

        self.cancel_btn = button(
            btn_row, "Stop", variant="danger",
            width=80, height=32, command=self._stop, state="disabled",
        )
        self.cancel_btn.pack(side="left", padx=(6, 0))

        self.clear_btn = button(
            btn_row, "Clear", variant="ghost",
            width=80, height=32, command=self._clear,
        )
        self.clear_btn.pack(side="left", padx=(6, 0))

        self.status_frame = ctk.CTkScrollableFrame(
            self.body, height=160, fg_color="transparent",
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        self.status_frame.pack(fill="x", padx=12, pady=(0, 10))

    # ------------------------------------------------------------------
    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.body.pack(fill="x")
        else:
            self.body.pack_forget()
        chev = self._CHEVRON_OPEN if self._expanded else self._CHEVRON_CLOSED
        self.toggle_btn.configure(text=f"  {chev}   Batch Download")

    def _clear(self):
        if self._running:
            return
        self.url_text.delete("1.0", "end")
        for row in self._rows:
            row["frame"].destroy()
        self._rows.clear()

    def _stop(self):
        if self._running:
            self._cancel.set()

    # ------------------------------------------------------------------
    def _start(self):
        if self._running:
            return
        raw = self.url_text.get("1.0", "end").strip()
        urls = [u.strip() for u in raw.splitlines() if u.strip()]
        if not urls:
            return

        for row in self._rows:
            row["frame"].destroy()
        self._rows.clear()

        for url in urls:
            self._rows.append(self._make_row(url))

        self._running = True
        self._cancel.clear()
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")

        threading.Thread(target=self._worker, daemon=True).start()

    def _make_row(self, url):
        frame = ctk.CTkFrame(
            self.status_frame, fg_color=T.BG_RAISED,
            corner_radius=T.RADIUS_SM,
        )
        frame.pack(fill="x", pady=3)

        dot = ctk.CTkLabel(
            frame, text="●", font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT_DIM, width=20,
        )
        dot.pack(side="left", padx=(8, 6))

        plat = detect_platform(url) or "?"
        short = url if len(url) < 80 else url[:77] + "..."
        info = ctk.CTkLabel(
            frame, text=f"[{plat}] {short}",
            font=T.font(T.SIZE_SM, mono=True),
            text_color=T.TEXT_MUTED, anchor="w",
        )
        info.pack(side="left", fill="x", expand=True)

        status = ctk.CTkLabel(
            frame, text="Queued",
            font=T.font(T.SIZE_SM),
            text_color=T.TEXT_DIM, width=90,
        )
        status.pack(side="left", padx=4)

        open_btn = button(
            frame, "Use", variant="secondary",
            width=60, height=26,
        )
        open_btn.configure(state="disabled")
        open_btn.pack(side="right", padx=6, pady=4)

        return {
            "url": url, "frame": frame, "dot": dot,
            "status": status, "open_btn": open_btn, "path": None,
        }

    def _worker(self):
        cookies = self._get_cookies() if self._get_cookies else None

        for row in self._rows:
            if self._cancel.is_set():
                self.after(0, self._set_row, row, "Cancelled", T.TEXT_DIM)
                continue

            self.after(0, self._set_row, row, "Downloading...", T.ACCENT)
            result = download_video(row["url"], cookies=cookies, cancel_event=self._cancel)
            if self._cancel.is_set():
                self.after(0, self._set_row, row, "Cancelled", T.TEXT_DIM)
                continue
            if result.get("error"):
                msg = result["error"][:40]
                self.after(0, self._set_row, row, f"✕ {msg}", T.DANGER)
            else:
                row["path"] = result.get("path")
                self.after(0, self._set_row_done, row)

        self._running = False
        self.after(0, self._finish)

    def _set_row(self, row, text, color):
        row["status"].configure(text=text, text_color=color)
        row["dot"].configure(text_color=color)

    def _set_row_done(self, row):
        row["status"].configure(text="✓ Done", text_color=T.SUCCESS)
        row["dot"].configure(text_color=T.SUCCESS)
        if self._on_video_selected:
            row["open_btn"].configure(
                state="normal",
                command=lambda p=row["path"]: self._on_video_selected(p),
            )

    def _finish(self):
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
