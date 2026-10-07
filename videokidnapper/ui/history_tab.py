# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Recent exports, shown in the Export workspace's History tab.

Entries come from the history list in settings (newest first), grouped
under Today / Yesterday / Earlier. Video and GIF exports get a small
thumbnail, decoded on a worker thread so a long list never blocks the
UI; files that were moved or deleted are shown greyed out.
"""

import os
import subprocess
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.studio import controls as C
from videokidnapper.ui.theme import button
from videokidnapper.utils import settings
from videokidnapper.utils.size_estimator import human_bytes

_THUMB_SIZE = (96, 54)
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".gif", ".m4v", ".avi"}


def day_group(timestamp, today=None):
    """``"Today"``, ``"Yesterday"`` or ``"Earlier"`` for a history stamp.

    Stamps are written as ``YYYY-MM-DD HH:MM``; anything unparseable
    lands in Earlier rather than breaking the list.
    """
    today = today or date.today()
    try:
        day = datetime.strptime(str(timestamp)[:10], "%Y-%m-%d").date()
    except ValueError:
        return "Earlier"
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return "Earlier"


def short_time(timestamp, group):
    """Show just the time for Today/Yesterday, the full stamp otherwise."""
    text = str(timestamp or "")
    if group in ("Today", "Yesterday") and len(text) >= 16:
        return text[11:16]
    return text


class HistoryTab(ctk.CTkFrame):
    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color=T.BG_BASE, corner_radius=0, **kwargs)
        self.app = app
        self._thumb_gen = 0
        self._thumb_labels = {}      # path → CTkLabel awaiting a thumbnail
        self._thumb_images = []      # keep CTkImages alive
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        page = ctk.CTkFrame(self, fg_color="transparent")
        page.pack(fill="both", expand=True, padx=28, pady=22)

        head = ctk.CTkFrame(page, fg_color="transparent")
        head.pack(fill="x", pady=(0, 14))
        title = ctk.CTkFrame(head, fg_color="transparent")
        title.pack(side="left")
        ctk.CTkLabel(title, text="Recent exports", font=T.font(T.SIZE_XL, "bold"),
                     text_color=T.TEXT).pack(anchor="w")
        C.hint(title, "Your last 25 exports from Edit and Batch.", wrap=500).pack(anchor="w")
        button(head, "Clear history", variant="ghost", width=110, height=32,
               text_color=T.DANGER, font=T.font(T.SIZE_SM, "bold"),
               command=self._clear).pack(side="right")
        button(head, "Open exports folder", variant="secondary", width=150, height=32,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._open_exports_folder).pack(side="right", padx=(0, 8))

        card = ctk.CTkFrame(page, fg_color=T.BG_SURFACE, corner_radius=T.RADIUS_LG,
                            border_width=1, border_color=T.BORDER)
        card.pack(fill="both", expand=True)
        self.list_container = ctk.CTkScrollableFrame(
            card, fg_color="transparent",
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        self.list_container.pack(fill="both", expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    def refresh(self):
        for child in self.list_container.winfo_children():
            child.destroy()
        self._thumb_labels = {}
        self._thumb_images = []

        entries = settings.get_history()
        if not entries:
            empty = ctk.CTkFrame(self.list_container, fg_color="transparent")
            empty.pack(fill="both", expand=True, pady=80)
            ctk.CTkLabel(empty, text="Nothing exported yet", font=T.font(T.SIZE_XL, "bold"),
                         text_color=T.TEXT).pack()
            C.hint(empty, "Exports from Edit and Batch show up here, newest first.",
                   wrap=420).pack(pady=(4, 12))
            button(empty, "Go to Edit", variant="secondary", width=110, height=32,
                   command=lambda: self._show("edit")).pack()
            return

        current = None
        for entry in entries:
            group = day_group(entry.get("timestamp"))
            if group != current:
                C.section_label(self.list_container, group).pack(
                    fill="x", padx=16, pady=(10 if current is None else 18, 4))
                current = group
            self._render_entry(entry, group)
        self._load_thumbnails()

    def _render_entry(self, entry, group):
        path = entry.get("path", "")
        exists = bool(path) and Path(path).exists()

        row = ctk.CTkFrame(self.list_container, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=8)

        fmt = str(entry.get("format", "") or "").upper()
        thumb = ctk.CTkLabel(
            row, text=fmt or "?", width=_THUMB_SIZE[0], height=_THUMB_SIZE[1],
            fg_color=T.MONITOR_BG, corner_radius=4,
            font=T.font(T.SIZE_SM, "bold"), text_color=T.TEXT_MUTED,
        )
        thumb.pack(side="left", padx=(8, 14), pady=8)
        if exists and Path(path).suffix.lower() in _VIDEO_EXTS:
            self._thumb_labels[path] = thumb

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        name = os.path.basename(path) if path else "Unknown"
        ctk.CTkLabel(info, text=name, font=T.font(T.SIZE_MD, "bold"),
                     text_color=T.TEXT if exists else T.TEXT_DIM, anchor="w").pack(fill="x")
        meta = [fmt, entry.get("preset", ""), short_time(entry.get("timestamp"), group)]
        size = entry.get("size_bytes")
        if size:
            meta.append(human_bytes(size))
        if not exists:
            meta.append("moved or deleted")
        ctk.CTkLabel(info, text="  ·  ".join(p for p in meta if p),
                     font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED,
                     anchor="w").pack(fill="x")

        btns = ctk.CTkFrame(row, fg_color="transparent")
        btns.pack(side="right", padx=(8, 10))
        state = "normal" if exists else "disabled"
        button(btns, "Play", variant="secondary", width=64, height=30,
               font=T.font(T.SIZE_SM, "bold"), state=state,
               command=lambda p=path: self._open(p)).pack(side="left", padx=3)
        button(btns, "Show in folder", variant="ghost", width=110, height=30,
               font=T.font(T.SIZE_SM, "bold"), state=state,
               command=lambda p=path: self._reveal(p)).pack(side="left", padx=3)

        C.divider(self.list_container).pack(fill="x", padx=16)

    # ------------------------------------------------------------------
    def _load_thumbnails(self):
        """Decode one frame per export on a worker; apply on the main thread."""
        self._thumb_gen += 1
        gen = self._thumb_gen
        paths = list(self._thumb_labels)
        if not paths:
            return
        results = {}
        done = {"flag": False}

        def worker():
            from videokidnapper.core.ffmpeg_backend import extract_frame
            for path in paths:
                if gen != self._thumb_gen:
                    return
                try:
                    frame = extract_frame(path, 0.5)
                    if frame is not None:
                        frame = frame.convert("RGB")
                        frame.thumbnail(_THUMB_SIZE)
                        results[path] = frame
                except Exception:
                    continue
            done["flag"] = True

        def poll():
            if gen != self._thumb_gen or not self.winfo_exists():
                return
            for path in list(results):
                frame = results.pop(path)
                label = self._thumb_labels.get(path)
                if label is not None and label.winfo_exists():
                    image = ctk.CTkImage(light_image=frame, dark_image=frame,
                                         size=frame.size)
                    self._thumb_images.append(image)
                    label.configure(image=image, text="")
            if not done["flag"] or results:
                self.after(150, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, poll)

    def _show(self, key):
        show = getattr(self.app, "show_workspace", None)
        if callable(show):
            show(key)

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

    def _open_exports_folder(self):
        folder = settings.get("output_folder") or str(Path.home() / "Downloads")
        if not Path(folder).exists():
            return
        if os.name == "nt":
            os.startfile(folder)  # noqa: S606 — user-chosen folder
        else:
            subprocess.Popen(["xdg-open", folder])

    def _clear(self):
        settings.clear_history()
        self.refresh()
