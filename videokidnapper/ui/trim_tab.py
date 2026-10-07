# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The Studio Edit workspace.

Layout, with no page scrolling:

    ┌ Media ───┬ Preview ──────────────────────┬ Inspector ─────┐
    │ add/open │ canvas tools                  │ Clip Text      │
    │ record   │ video                         │ Image Color    │
    │ this clip│ timecode · transport · in/out │                │
    ├──────────┴───────────────────────────────┴────────────────┤
    │ Timeline: ruler, ranges, text, image, video, audio lanes   │
    └────────────────────────────────────────────────────────────┘

The class keeps its historical name and public API (``app.trim_tab``,
``open_project``, ``receive_url``, keyboard handlers, ...) so dialogs,
plugins and the CLI-adjacent code that call into it keep working.

Captions and image overlays still live in ``TextLayersPanel`` /
``ImageLayersPanel`` rows, which act as the data model; they're never
shown. The Inspector edits one selected row at a time and the timeline
draws them all as clips.
"""

import os
import subprocess
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from videokidnapper.config import PRESETS, SUPPORTED_VIDEO_EXTENSIONS, EXPORT_FORMATS
from videokidnapper.core.ffmpeg_backend import (
    concat_clips_with_transition, frames_to_video,
    get_video_info, trim_to_gif, trim_to_video,
)
from videokidnapper.core.preview import clear_cache
from videokidnapper.core.screen_capture import record_screen
from videokidnapper.ui import theme as T
from videokidnapper.ui.editor_options import EditorOptions
from videokidnapper.ui.export_dialog import ExportDialog
from videokidnapper.ui.image_layers import SUPPORTED_IMAGE_EXTS, ImageLayersPanel
from videokidnapper.ui.platform_presets import PLATFORM_CHOICES, get_preset
from videokidnapper.ui.studio import controls as C
from videokidnapper.ui.studio.icons import glyph, icon_button, icon_font
from videokidnapper.ui.studio.inspector import Inspector
from videokidnapper.ui.studio.timeline import MAX_ZOOM, TimelineView
from videokidnapper.ui.text_layers import TextLayersPanel
from videokidnapper.ui.theme import button
from videokidnapper.ui.video_player import VideoPlayer
from videokidnapper.utils import project_files, settings
from videokidnapper.utils.file_naming import generate_export_path
from videokidnapper.utils.size_estimator import estimate_bytes, human_bytes
from videokidnapper.utils.srt_parser import parse_srt_file, srt_to_text_layers
from videokidnapper.utils.time_format import seconds_to_hms, hms_to_seconds
from videokidnapper.utils.undo import UndoStack

MEDIA_W = 250
MEDIA_RAIL_W = 44
INSPECTOR_W = 340
_FRAME_COALESCE_MS = 15
_PREVIEW_REFRESH_MS = 40
_PLAY_POLL_MS = 80


def short_duration(seconds):
    """Compact clip length for labels: ``0:42``, ``12:05``, ``1:02:03``."""
    total = int(round(max(0.0, float(seconds or 0))))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


class RangeStore:
    """Saved ranges: what the old ``RangeQueue`` held, minus its widget."""

    MIN_LENGTH = 0.05

    def __init__(self, on_change=None):
        self._ranges = []
        self._on_change = on_change

    def _changed(self):
        if self._on_change:
            self._on_change()

    def add_range(self, start, end):
        if end - start < self.MIN_LENGTH:
            return False
        self._ranges.append((float(start), float(end)))
        self._changed()
        return True

    def remove(self, index):
        if 0 <= index < len(self._ranges):
            del self._ranges[index]
            self._changed()

    def move(self, index, delta):
        """Move one range earlier (-1) or later (+1); True if it moved.

        Joined exports follow this order. An out-of-range move is a no-op
        so a stale index from a redrawn list cannot raise.
        """
        target = index + delta
        if not (0 <= index < len(self._ranges) and 0 <= target < len(self._ranges)):
            return False
        self._ranges[index], self._ranges[target] = (
            self._ranges[target], self._ranges[index])
        self._changed()
        return True

    def clear(self):
        if self._ranges:
            self._ranges.clear()
            self._changed()

    def set_ranges(self, ranges):
        self._ranges = [(float(s), float(e)) for s, e in ranges]
        self._changed()

    def get_ranges(self):
        return list(self._ranges)


class TrimTab(ctk.CTkFrame):
    """Studio Edit workspace (historical name kept for compatibility)."""

    def __init__(self, master, app, **kwargs):
        super().__init__(master, fg_color=T.BORDER, corner_radius=0, **kwargs)
        self.app = app
        self.video_path = None
        # The name exports derive from. For a download this is the real
        # title yt-dlp reported; for a local file it is the filename.
        # Kept separately because the downloaded file's stem is
        # truncated to 80 chars by the output template.
        self.source_title = None
        self.video_info = None
        self._toast = None

        # Undo/redo machinery. ``_restoring`` guards the widget callbacks
        # that would otherwise record a new snapshot while we're applying
        # one; ``_snapshot_after_id`` debounces rapid-fire edits (typing,
        # slider scrub) into a single history entry per settled state.
        self._undo_stack = UndoStack(cap=50)
        self._restoring = False
        self._snapshot_after_id = None
        self._snapshot_debounce_ms = 350
        self._autosave_after_id = None
        self._autosave_debounce_ms = 1500
        self.current_project_path = None
        self._project_dirty = False

        self.playhead = 0.0
        self.selected_text_index = None
        self.selected_image_index = None
        self.size_estimate_text = ""
        self.download_bar = None          # set by the Import workspace
        self._state_listeners = []
        self._frame_after_id = None
        self._pending_frame_t = None
        self._preview_after_id = None
        self._crop_on = False
        self._media_thumb = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Wiring for other workspaces
    # ------------------------------------------------------------------
    def set_toast(self, toast):
        self._toast = toast

    def _notify(self, message, level="info"):
        if self._toast:
            self._toast.show(message, level)

    def add_state_listener(self, callback):
        """``callback()`` runs whenever export-relevant state changes."""
        self._state_listeners.append(callback)

    def _emit_state(self):
        for callback in list(self._state_listeners):
            try:
                callback()
            except Exception:
                pass

    def _show_workspace(self, key):
        show = getattr(self.app, "show_workspace", None)
        if callable(show):
            show(key)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_ui(self):
        self._build_models()

        self.grid_columnconfigure(0, minsize=MEDIA_W, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, minsize=INSPECTOR_W, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self.media_panel = self._build_media_panel()
        self.media_rail = self._build_media_rail()
        self._set_media_collapsed(bool(settings.get("media_panel_collapsed", False)),
                                  persist=False)
        self._build_preview().grid(row=0, column=1, sticky="nsew")
        self.inspector = Inspector(self, self, width=INSPECTOR_W)
        self.inspector.pack_propagate(False)
        self.inspector.grid(row=0, column=2, sticky="nsew", padx=(1, 0))
        self._build_timeline().grid(row=1, column=0, columnspan=3, sticky="ew", pady=(1, 0))

        self._update_project_status()
        self._update_timecode()

    def _build_models(self):
        self.options = EditorOptions(self)
        # Historical name: export, projects and presets call through it.
        self.export_options = self.options
        self.options.add_listener(self._on_export_options_changed)

        self.platform_var = ctk.StringVar(value=settings.get("platform_preset", "Custom"))
        self.quality_var = ctk.StringVar(value=settings.get("quality", "Medium"))
        self.format_var = ctk.StringVar(value=settings.get("format", "GIF"))

        # Never packed: the caption and overlay rows are the data model.
        self._model_host = ctk.CTkFrame(self)
        self.text_layers = TextLayersPanel(
            self._model_host, on_change=self._on_text_layers_changed)
        # Auto-track lives on each caption but is driven from here.
        self.text_layers.set_autotrack_handler(self._auto_track)
        self.image_layers = ImageLayersPanel(
            self._model_host,
            on_change=self._on_image_layers_changed,
            on_notify=self._notify,
        )
        self.range_queue = RangeStore(on_change=self._on_ranges_changed)

    def _build_media_panel(self):
        panel = ctk.CTkFrame(self, fg_color=T.BG_SURFACE, corner_radius=0, width=MEDIA_W)
        panel.pack_propagate(False)
        header, right = C.panel_header(panel, "Media")
        header.pack(fill="x")
        icon_button(right, "back", size=28, icon_size=11,
                    command=lambda: self._set_media_collapsed(True)).pack()
        C.divider(panel).pack(fill="x")

        add = ctk.CTkFrame(panel, fg_color="transparent")
        add.pack(fill="x", padx=14, pady=(12, 12))
        C.section_label(add, "Add a video").pack(fill="x", pady=(0, 6))
        link_row = ctk.CTkFrame(add, fg_color="transparent")
        link_row.pack(fill="x")
        self.media_link_entry = C.entry(link_row, width=150, placeholder_text="Paste a link")
        self.media_link_entry.pack(side="left", fill="x", expand=True)
        self.media_link_entry.bind("<Return>", lambda _e: self._media_get_link())
        button(link_row, "Get", variant="secondary", width=48, height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._media_get_link).pack(side="left", padx=(6, 0))
        btns = ctk.CTkFrame(add, fg_color="transparent")
        btns.pack(fill="x", pady=(8, 0))
        btns.grid_columnconfigure((0, 1), weight=1)
        button(btns, "Open file", variant="secondary", height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._open_file).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        button(btns, "Record", variant="secondary", height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self._record_screen).grid(row=0, column=1, sticky="ew", padx=(3, 0))
        C.hint(add, "Or drop a file on the preview.", wrap=210).pack(anchor="w", pady=(8, 0))

        C.divider(panel).pack(fill="x")
        clip = ctk.CTkFrame(panel, fg_color="transparent")
        clip.pack(fill="x", padx=14, pady=(12, 0))
        C.section_label(clip, "In this project").pack(fill="x", pady=(0, 8))
        card = ctk.CTkFrame(clip, fg_color=T.ACCENT_SOFT, corner_radius=T.RADIUS_MD)
        self.media_card = card
        self.media_thumb = ctk.CTkLabel(card, text="", width=64, height=36,
                                        fg_color=T.MONITOR_BG, corner_radius=4)
        self.media_thumb.pack(side="left", padx=(8, 10), pady=8)
        text_col = ctk.CTkFrame(card, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True, pady=8)
        self.file_label = ctk.CTkLabel(text_col, text="", font=T.font(T.SIZE_MD, "bold"),
                                       text_color=T.TEXT, anchor="w")
        self.file_label.pack(fill="x")
        self.file_meta = ctk.CTkLabel(text_col, text="", font=T.font(T.SIZE_SM),
                                      text_color=T.TEXT_MUTED, anchor="w")
        self.file_meta.pack(fill="x")
        self.media_empty = C.hint(clip, "Nothing here yet. Open a file, paste a "
                                        "link, or record your screen.", wrap=210)
        self.media_empty.pack(anchor="w")

        spacer = ctk.CTkFrame(panel, fg_color="transparent")
        spacer.pack(fill="both", expand=True)
        button(panel, "Download several links…", variant="ghost", height=30,
               text_color=T.ACCENT, font=T.font(T.SIZE_SM, "bold"),
               command=lambda: self._show_workspace("import")).pack(
            fill="x", padx=8, pady=(0, 10))
        return panel

    def _build_media_rail(self):
        """Collapsed Media panel: a thin strip that keeps the quick actions."""
        rail = ctk.CTkFrame(self, fg_color=T.BG_SURFACE, corner_radius=0, width=MEDIA_RAIL_W)
        rail.pack_propagate(False)
        icon_button(rail, "forward", size=32, icon_size=11,
                    command=lambda: self._set_media_collapsed(False)).pack(pady=(6, 10))
        C.divider(rail).pack(fill="x", padx=8, pady=(0, 8))
        for name, cmd in (("folder", self._open_file),
                          ("link", lambda: self._show_workspace("import")),
                          ("screen", self._record_screen)):
            icon_button(rail, name, size=32, icon_size=14, command=cmd).pack(pady=2)
        return rail

    def _set_media_collapsed(self, collapsed, persist=True):
        """Swap the Media panel for its rail (or back) and keep the choice."""
        self._media_collapsed = bool(collapsed)
        show, hide = ((self.media_rail, self.media_panel) if collapsed
                      else (self.media_panel, self.media_rail))
        hide.grid_forget()
        show.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
        self.grid_columnconfigure(0, minsize=MEDIA_RAIL_W if collapsed else MEDIA_W)
        if persist:
            settings.set("media_panel_collapsed", self._media_collapsed)

    def _build_preview(self):
        pv = ctk.CTkFrame(self, fg_color=T.BG_SURFACE, corner_radius=0)

        head = ctk.CTkFrame(pv, fg_color=T.BG_SURFACE, corner_radius=0, height=40)
        head.pack(fill="x")
        head.pack_propagate(False)
        ctk.CTkLabel(head, text="Preview", font=T.font(T.SIZE_MD, "bold"),
                     text_color=T.TEXT).pack(side="left", padx=(14, 8))
        self.preview_name = ctk.CTkLabel(head, text="", font=T.font(T.SIZE_SM),
                                         text_color=T.TEXT_MUTED)
        self.preview_name.pack(side="left")
        tools = ctk.CTkFrame(head, fg_color=T.BG_RAISED, corner_radius=T.RADIUS_SM)
        tools.pack(side="right", padx=(0, 10))
        icon_button(tools, "open_new", command=self._play_in_system, size=28,
                    icon_size=12).pack(side="right", padx=2, pady=2)
        icon_button(tools, "image", command=self.add_image_layer, size=28,
                    icon_size=13).pack(side="right", padx=2, pady=2)
        icon_button(tools, "text", command=self.add_text_layer, size=28,
                    icon_size=13).pack(side="right", padx=2, pady=2)
        self.crop_btn = icon_button(tools, "crop", command=self._toggle_crop_mode,
                                    size=28, icon_size=13)
        self.crop_btn.pack(side="right", padx=2, pady=2)
        C.divider(pv).pack(fill="x")

        self.player = VideoPlayer(
            pv,
            on_empty_click=self._open_file,
            on_file_dropped=self._on_file_dropped,
            fg_color=T.MONITOR_BG, border_width=0, corner_radius=0,
            canvas_bg=T.MONITOR_BG, inset=14,
        )
        self.player.pack(fill="both", expand=True)
        self.player.set_text_layers_provider(self._current_text_layers)
        # Image overlays share the same provider pattern as text layers —
        # the player composites them in source-resolution space so the
        # preview matches the exported output.
        self.player.set_image_layers_provider(self._current_image_layers)
        self.player.set_color_provider(self._color_values)
        # The preview renders the export's frame (aspect preset, crop,
        # blur fill, rotation), so it needs the live export options.
        self.player.set_export_options_provider(self.options.get_options)
        # Dragging in the preview moves a caption (or records a motion
        # keyframe) and drags image overlays to an exact spot.
        self.player.set_text_position_callback(self._on_text_dragged)
        self.player.set_image_position_callback(self._on_image_dragged)

        C.divider(pv).pack(fill="x")
        transport = ctk.CTkFrame(pv, fg_color=T.BG_SURFACE, corner_radius=0, height=58)
        transport.pack(fill="x")
        transport.pack_propagate(False)
        self.timecode_label = ctk.CTkLabel(
            transport, text="", font=T.font(T.SIZE_LG, "bold", mono=True),
            text_color=T.TEXT,
        )
        self.timecode_label.pack(side="left", padx=(14, 0))

        marks = ctk.CTkFrame(transport, fg_color="transparent")
        marks.pack(side="right", padx=(0, 12))
        button(marks, "Mark in  I", variant="secondary", width=86, height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self.keyboard_mark_in).pack(side="left", padx=(0, 6))
        button(marks, "Mark out  O", variant="secondary", width=92, height=30,
               font=T.font(T.SIZE_SM, "bold"),
               command=self.keyboard_mark_out).pack(side="left")

        play = ctk.CTkFrame(transport, fg_color="transparent")
        play.place(relx=0.5, rely=0.5, anchor="center")
        icon_button(play, "to_start", command=self._go_to_in, size=32).pack(side="left", padx=2)
        icon_button(play, "back", command=lambda: self.keyboard_nudge(-1.0),
                    size=32).pack(side="left", padx=2)
        self.play_btn = ctk.CTkButton(
            play, text=glyph("play"), width=42, height=42, corner_radius=21,
            font=icon_font(16), fg_color=T.TEXT, hover_color=T.TEXT_MUTED,
            text_color=T.BG_SURFACE, command=self._toggle_play,
        )
        self.play_btn.pack(side="left", padx=6)
        icon_button(play, "forward", command=lambda: self.keyboard_nudge(1.0),
                    size=32).pack(side="left", padx=2)
        icon_button(play, "to_end", command=self._go_to_out, size=32).pack(side="left", padx=2)
        return pv

    def _build_timeline(self):
        tl = ctk.CTkFrame(self, fg_color=T.BG_SURFACE, corner_radius=0)
        bar = ctk.CTkFrame(tl, fg_color=T.BG_SURFACE, corner_radius=0, height=42)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, text="Timeline", font=T.font(T.SIZE_MD, "bold"),
                     text_color=T.TEXT).pack(side="left", padx=(14, 12))
        small = dict(variant="secondary", height=28, font=T.font(T.SIZE_SM, "bold"))
        button(bar, "+ Text", width=64, command=self.add_text_layer, **small).pack(
            side="left", padx=(0, 6))
        button(bar, "+ Image", width=70, command=self.add_image_layer, **small).pack(
            side="left", padx=(0, 6))
        self.captions_btn = button(bar, "Captions ▾", width=90,
                                   command=self._open_captions_menu, **small)
        self.captions_btn.pack(side="left", padx=(0, 6))
        C.divider(bar, horizontal=False).pack(side="left", fill="y", pady=10, padx=6)
        button(bar, "+ Save range  Q", width=118, command=self._queue_range,
               **small).pack(side="left")

        zoom = ctk.CTkFrame(bar, fg_color="transparent")
        zoom.pack(side="right", padx=(0, 14))
        ctk.CTkLabel(zoom, text="Zoom", font=T.font(T.SIZE_SM),
                     text_color=T.TEXT_MUTED).pack(side="left", padx=(0, 8))
        self.zoom_slider = C.slider(zoom, 1.0, MAX_ZOOM, width=120,
                                    command=lambda v: self.timeline.set_zoom(v))
        self.zoom_slider.set(1.0)
        self.zoom_slider.pack(side="left")
        C.divider(tl).pack(fill="x")

        self.timeline = TimelineView(
            tl,
            on_seek=self._seek,
            on_selection_change=self._on_timeline_selection,
            on_clip_select=self.select_layer,
            on_clip_change=self.set_layer_time,
            on_range_click=self._load_range,
            on_zoom_change=lambda z: self.zoom_slider.set(z),
        )
        self.timeline.pack(fill="x")

        self._captions_menu = tk.Menu(
            self, tearoff=0, bg=T.BG_SURFACE, fg=T.TEXT,
            activebackground=T.ACCENT_SOFT, activeforeground=T.TEXT,
            font=(T.FONT_FAMILY, 10), bd=1, relief="solid",
        )
        self._captions_menu.add_command(label="Import SRT or VTT…", command=self._import_srt)
        self._captions_menu.add_command(label="Captions from speech…", command=self._auto_caption)
        return tl

    def _open_captions_menu(self):
        btn = self.captions_btn
        try:
            self._captions_menu.tk_popup(btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height())
        finally:
            self._captions_menu.grab_release()

    # ------------------------------------------------------------------
    # Compatibility shims for callers of the old scrolling layout
    # ------------------------------------------------------------------
    def _jump_to_feature(self, name):
        """Old TOOLS-dock names → where that feature lives now."""
        if name == "Source":
            self._show_workspace("import")
        elif name in ("Ranges", "Export"):
            self._show_workspace("export")
        else:
            self._show_workspace("edit")
            tab = {"Text": "text", "Overlays": "image", "Options": "clip"}.get(name)
            if tab:
                self.inspector.show(tab)

    def _toggle_download_bar(self):
        self._show_workspace("import")

    def _set_download_bar_expanded(self, expanded):
        if expanded:
            self._show_workspace("import")

    # ------------------------------------------------------------------
    # Providers and change handlers
    # ------------------------------------------------------------------
    def _current_image_layers(self):
        # Only layers whose path is a real file — the ffmpeg export path
        # applies the same filter, so the preview matches.
        return self.image_layers.get_all_layers()

    def _current_text_layers(self):
        # include_empty keeps the list index aligned with panel.layers so
        # the VideoPlayer's hit-test can call back with the right widget index.
        return self.text_layers.get_all_layers(include_empty=True)

    def _color_values(self):
        o = self.options
        return (float(o.brightness_var.get()), float(o.contrast_var.get()),
                float(o.saturation_var.get()), float(o.gamma_var.get()))

    def _schedule_preview_refresh(self):
        """Coalesce bursts of edits (slider drags, typing) into one repaint."""
        if self._preview_after_id is not None:
            return

        def run():
            self._preview_after_id = None
            if self.video_path and not self.player._playing:
                self.player.refresh_overlay()

        self._preview_after_id = self.after(_PREVIEW_REFRESH_MS, run)

    def _on_text_layers_changed(self):
        self._schedule_preview_refresh()
        self._sync_timeline_clips()
        self._clamp_selection_indices()
        page = getattr(self, "inspector", None)
        if page is not None:
            page.pages["text"].refresh_details()
        self._request_snapshot(immediate=False)

    def _on_image_layers_changed(self):
        # Drop the image cache so newly-picked files aren't shadowed by a
        # previous failure, and re-render the current frame.
        self.player._image_cache.clear()
        self._schedule_preview_refresh()
        self._sync_timeline_clips()
        self._clamp_selection_indices()
        page = getattr(self, "inspector", None)
        if page is not None:
            page.pages["image"].refresh_details()
        # Debounce: typing into a text entry fires on every keystroke —
        # we only want one undo entry per "pause".
        self._request_snapshot(immediate=False)

    def _on_export_options_changed(self):
        self._update_size_estimate()
        self._mark_project_dirty()
        # Color, rotate and the like can change what the preview shows.
        if hasattr(self, "player"):
            self._schedule_preview_refresh()

    def _on_ranges_changed(self):
        if hasattr(self, "timeline"):
            self.timeline.set_ranges(self.range_queue.get_ranges())
        self._update_size_estimate()

    def _sync_timeline_clips(self):
        if not hasattr(self, "timeline"):
            return
        text = []
        for data in self.text_layers.get_all_layers(include_empty=True):
            first_line = (data.get("text") or "").strip().splitlines()
            text.append({"start": data["start"], "end": data["end"],
                         "label": first_line[0] if first_line else "(empty caption)"})
        images = []
        for data in self.image_layers.get_all_layers(include_empty=True):
            path = data.get("path") or ""
            images.append({"start": data["start"], "end": data["end"],
                           "label": os.path.basename(path) if path else "(no file)"})
        self.timeline.set_clips(text=text, images=images)

    def _clamp_selection_indices(self):
        n_text = len(self.text_layers.layers)
        if self.selected_text_index is not None and self.selected_text_index >= n_text:
            self.selected_text_index = n_text - 1 if n_text else None
        n_img = len(self.image_layers.layers)
        if self.selected_image_index is not None and self.selected_image_index >= n_img:
            self.selected_image_index = n_img - 1 if n_img else None

    # ------------------------------------------------------------------
    # Captions and overlays: selection, add, delete, retime
    # ------------------------------------------------------------------
    def select_layer(self, kind, index):
        layers = (self.text_layers if kind == "text" else self.image_layers).layers
        if not (0 <= index < len(layers)):
            return
        if kind == "text":
            self.selected_text_index = index
        else:
            self.selected_image_index = index
        self.timeline.set_selected(kind, index)
        self.inspector.pages[kind].refresh()
        self.inspector.show(kind)
        # Jump into the clip so the preview actually shows it.
        start, end = layers[index].time_slider.get_values()
        if not (start <= self.playhead <= end):
            self._seek(start)

    def add_text_layer(self):
        if not self.video_path:
            self._notify("Open a video first", "warn")
            return None
        duration = self.video_info["duration"]
        start = min(self.playhead, max(0.0, duration - 0.5))
        end = min(duration, start + 3.0)
        layer = self.text_layers._add_layer(preset_data={
            "text": "Your text", "start": start, "end": end,
        })
        layer._on_style_change(layer.style_var.get())
        index = len(self.text_layers.layers) - 1
        self.select_layer("text", index)
        page = self.inspector.pages["text"]
        page.textbox.focus_set()
        page.textbox.tag_add("sel", "1.0", "end-1c")
        return layer

    def duplicate_text_layer(self, index):
        layers = self.text_layers.layers
        if 0 <= index < len(layers):
            self.text_layers._add_layer(preset_data=layers[index].get_layer_data())
            self.select_layer("text", len(layers) - 1)

    def add_image_layer(self):
        if not self.video_path:
            self._notify("Open a video first", "warn")
            return None
        exts = " ".join(f"*{e}" for e in SUPPORTED_IMAGE_EXTS)
        path = filedialog.askopenfilename(
            title="Pick an overlay image",
            filetypes=[("Images", exts), ("All files", "*.*")],
        )
        if not path:
            return None
        layer = self.image_layers.add_layer_from_path(path)
        self.select_layer("image", len(self.image_layers.layers) - 1)
        return layer

    def paste_image_layer(self):
        if not self.video_path:
            self._notify("Open a video first", "warn")
            return
        before = len(self.image_layers.layers)
        self.image_layers._on_paste_clicked()
        if len(self.image_layers.layers) > before:
            self.select_layer("image", len(self.image_layers.layers) - 1)

    def delete_layer(self, kind, index):
        panel = self.text_layers if kind == "text" else self.image_layers
        if not (0 <= index < len(panel.layers)):
            return
        panel._remove_layer(panel.layers[index])
        remaining = len(panel.layers)
        new_index = min(index, remaining - 1) if remaining else None
        if kind == "text":
            self.selected_text_index = new_index
        else:
            self.selected_image_index = new_index
        self.timeline.set_selected(kind if new_index is not None else None,
                                   new_index if new_index is not None else 0)
        self.inspector.pages[kind].refresh()
        self._request_snapshot(immediate=True)

    def set_layer_time(self, kind, index, start, end, final=True):
        """Retime a caption/overlay from the timeline or the inspector."""
        panel = self.text_layers if kind == "text" else self.image_layers
        if not (0 <= index < len(panel.layers)) or not self.video_info:
            return
        duration = self.video_info["duration"]
        start = max(0.0, min(float(start), duration - 0.1))
        end = max(start + 0.1, min(float(end), duration))
        layer = panel.layers[index]
        layer.time_slider.set_values(start, end)
        if final:
            # The panel wraps _on_time_change to notify; that refreshes the
            # preview, timeline and inspector and records an undo step.
            layer._on_time_change(start, end)
            self._request_snapshot(immediate=True)
        else:
            self._schedule_preview_refresh()
            self.inspector.pages[kind].refresh_details()

    def _on_text_dragged(self, index, source_x, source_y):
        """Preview drag: motion-armed layers record a keyframe at the
        playhead; everything else keeps the classic move-the-layer."""
        t = self.player.current_time
        if self.text_layers.maybe_record_keyframe(index, t, source_x, source_y):
            self._notify(
                f"Keyframe at {t:.2f}s — scrub and drag again to extend the path",
                "success",
            )
        else:
            self.text_layers.set_layer_position(index, source_x, source_y)
        if self.selected_text_index != index:
            self.select_layer("text", index)

    def _on_image_dragged(self, index, source_x, source_y):
        self.image_layers.set_layer_position(index, source_x, source_y)
        if self.selected_image_index != index:
            self.select_layer("image", index)

    # ------------------------------------------------------------------
    # Playhead, selection and transport
    # ------------------------------------------------------------------
    def _update_timecode(self):
        duration = (self.video_info or {}).get("duration", 0.0)
        self.timecode_label.configure(
            text=f"{seconds_to_hms(self.playhead)}   /   {seconds_to_hms(duration)}"
            if self.video_path else "--:--:--.---",
        )

    def _request_frame(self, t):
        """Show the frame at ``t``, coalescing bursts from scrubbing."""
        self._pending_frame_t = t
        if self._frame_after_id is not None:
            return

        def run():
            self._frame_after_id = None
            if self._pending_frame_t is not None and self.video_path:
                self.player.show_frame(self._pending_frame_t)

        self._frame_after_id = self.after(_FRAME_COALESCE_MS, run)

    def _seek(self, t):
        if not self.video_path:
            return
        if self.player._playing:
            self._stop_playback()
        duration = self.video_info["duration"]
        self.playhead = max(0.0, min(float(t), duration))
        self.timeline.set_playhead(self.playhead)
        self._request_frame(self.playhead)
        self._update_timecode()

    def _apply_selection(self, start, end, from_timeline=False):
        """Single place that pushes a new in/out everywhere it's shown."""
        self.start_entry.set_value(seconds_to_hms(start))
        self.end_entry.set_value(seconds_to_hms(end))
        self._update_duration_label(start, end)
        if not from_timeline:
            self.timeline.set_selection(start, end)
        self._update_size_estimate()

    def _on_timeline_selection(self, start, end):
        """An in/out edge was dragged; the timeline moved the playhead to it."""
        self._apply_selection(start, end, from_timeline=True)
        self.playhead = self.timeline.playhead
        self._request_frame(self.playhead)
        self._update_timecode()
        self._request_snapshot(immediate=False)

    def _load_range(self, index):
        ranges = self.range_queue.get_ranges()
        if 0 <= index < len(ranges):
            start, end = ranges[index]
            self._apply_selection(start, end)
            self._seek(start)
            self._notify(f"Range {index + 1} loaded into the selection", "info")

    def _go_to_in(self):
        self._seek(self.timeline.get_values()[0])

    def _go_to_out(self):
        self._seek(self.timeline.get_values()[1])

    # ------------------------------------------------------------------
    # Platform preset wiring: selecting a platform snaps three fields;
    # editing any of those fields afterward reverts the label to Custom
    # so the picker never claims a preset the user has deviated from.
    def _apply_platform_preset(self, name):
        self.platform_var.set(name)
        settings.set("platform_preset", name)
        preset = get_preset(name)
        if preset is None:
            self._emit_state()
            return
        self.quality_var.set(preset["quality"])
        settings.set("quality", preset["quality"])
        self.format_var.set(preset["format"])
        settings.set("format", preset["format"])
        self.export_options.set_aspect(preset["aspect"])
        self._update_export_enabled()
        self._update_size_estimate()
        self._mark_project_dirty()
        self._notify(f"Applied preset: {name}", "info")

    def _on_quality_change(self, value):
        self.quality_var.set(value)
        settings.set("quality", value)
        self._mark_platform_custom()
        self._update_size_estimate()
        self._mark_project_dirty()

    def _on_format_change(self, value):
        self.format_var.set(value)
        settings.set("format", value)
        self._mark_platform_custom()
        self._update_export_enabled()
        self._update_size_estimate()
        self._mark_project_dirty()

    def _mark_platform_custom(self):
        if self.platform_var.get() != "Custom":
            self.platform_var.set("Custom")
            settings.set("platform_preset", "Custom")

    # ------------------------------------------------------------------
    # Loading media
    # ------------------------------------------------------------------
    def _open_file(self):
        exts = " ".join(f"*{e}" for e in SUPPORTED_VIDEO_EXTENSIONS)
        path = filedialog.askopenfilename(
            title="Open Video File",
            filetypes=[("Video files", exts), ("All files", "*.*")],
        )
        if path:
            self._load_path(path)

    def _on_file_dropped(self, path):
        if not path:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_VIDEO_EXTENSIONS:
            self._notify(f"Unsupported file type: {ext}", "warn")
            return
        self._load_path(path)

    def _media_get_link(self):
        url = self.media_link_entry.get().strip()
        if not url:
            self._show_workspace("import")
            return
        if self.download_bar is None:
            self._notify("The downloader isn't ready yet", "warn")
            return
        self.download_bar.receive_url(url)
        self.download_bar._download()
        self.media_link_entry.delete(0, "end")

    def _auto_track(self, index):
        """Auto-track: follow the video patch under the caption from the
        playhead to the end of the selection, then install the tracked
        path as this layer's keyframes."""
        from videokidnapper.core import tracker as trk

        if not self.video_path:
            self._notify("Load a video first", "warn")
            return
        ok, hint = trk.tracking_available()
        if not ok:
            self._notify(hint, "warn")
            return
        bbox = self.player.get_text_source_bbox(index)
        if not bbox:
            self._notify(
                "Drag the caption onto the thing you want to track first",
                "warn")
            return
        x1, y1, x2, y2 = bbox
        region = (x1, y1, max(8, x2 - x1), max(8, y2 - y1))
        start_t = self.player.current_time
        _, end_t = self.timeline.get_values()
        if end_t - start_t < 0.2:
            self._notify("Nothing after the playhead to track into", "warn")
            return

        self._notify("Tracking… the caption will follow when it's done", "info")
        state = {"frac": 0.0, "done": False, "result": None, "error": None}

        def worker():
            try:
                state["result"] = trk.track_region(
                    self.video_path, region, start_t, end_t,
                    progress_cb=lambda f: state.__setitem__("frac", f),
                )
            except Exception as e:      # noqa: BLE001 - surfaced to the user
                state["error"] = str(e)
            state["done"] = True

        def poll():
            if not self.winfo_exists():
                return
            if not state["done"]:
                self._notify(f"Tracking… {int(state['frac']*100)}%", "info")
                self.after(250, poll)
                return
            if state["error"]:
                self._notify(f"Tracking failed: {state['error'][:120]}", "error")
                return
            kfs = state["result"] or []
            if len(kfs) < 2:
                self._notify(
                    "Tracker lost the target immediately — try a more "
                    "distinct spot", "warn")
                return
            # The tracker works in source pixels; captions live in the
            # export's layout frame. Map each tracked box back (it is
            # the caption's own box, so its top-left is the caption's).
            bw, bh = region[2], region[3]
            mapped = []
            for kf in kfs:
                lx1, ly1, _lx2, _ly2 = self.player.source_rect_to_layout(
                    kf["x"], kf["y"], kf["x"] + bw, kf["y"] + bh)
                mapped.append(dict(kf, x=int(round(lx1)), y=int(round(ly1))))
            kfs = mapped
            self.text_layers.set_layer_keyframes(index, kfs)
            self.player.refresh_overlay()
            self._notify(
                f"Tracked {kfs[-1]['t'] - kfs[0]['t']:.1f}s → "
                f"{len(kfs)} keyframes. Scrub to check; drag to fix any spot.",
                "success")

        threading.Thread(target=worker, daemon=True).start()
        self.after(250, poll)

    def _on_downloaded_video(self, path, platform=None, title=None):
        """A download (single or batch) lands in the editor."""
        if not self._load_path(path):
            return
        # After _load_path, which seeds the title from the filename —
        # the reported title is better, being untruncated.
        if title:
            self.source_title = title
        if platform:
            self._notify(f"Kidnapped from {platform} — trim away", "success")

    def receive_url(self, url):
        """App-level Ctrl+V router hands pasted links to the downloader."""
        self._show_workspace("import")
        if self.download_bar is not None:
            self.download_bar.receive_url(url)

    def _set_media_card(self, path):
        if not path:
            self.media_card.pack_forget()
            self.media_empty.pack(anchor="w")
            return
        self.media_empty.pack_forget()
        self.media_card.pack(fill="x")
        info = self.video_info or {}
        fps = info.get("fps")
        parts = [f"{info.get('width', 0)}×{info.get('height', 0)}",
                 short_duration(info.get("duration", 0))]
        if fps:
            parts.append(f"{round(float(fps), 2):g} fps")
        name = os.path.basename(path)
        self.file_label.configure(text=name if len(name) <= 24 else name[:21] + "…")
        self.file_meta.configure(text=" · ".join(parts))
        try:
            from videokidnapper.core.preview import get_frame_at
            frame = get_frame_at(path, min(1.0, info.get("duration", 0) / 2))
            if frame is not None:
                frame = frame.copy()
                frame.thumbnail((64, 36))
                self._media_thumb = ctk.CTkImage(light_image=frame, dark_image=frame,
                                                 size=frame.size)
                self.media_thumb.configure(image=self._media_thumb)
        except Exception:
            pass

    def _load_path(self, path, preserve_project=False):
        if not preserve_project and not self._prepare_to_replace_project():
            return False
        try:
            new_video_info = get_video_info(path)
        except Exception as e:
            self._notify(f"Could not read video: {e}", "error")
            return False
        # _restoring suppresses undo/redo recording during the flurry of
        # callbacks that fires as we reset every widget below. The stack
        # is re-baselined at the end.
        self._restoring = True
        try:
            self.video_path = path
            self.video_info = new_video_info
            self.source_title = Path(path).stem
            # A crop rectangle from a previous video's source pixels doesn't
            # transfer — clear it so the export doesn't choke on out-of-bounds
            # coordinates.
            settings.set("crop", None)
            self.player.set_crop(None)
            self._set_crop_ui(False)
            dur = self.video_info["duration"]
            name = os.path.basename(path)

            clear_cache()
            self.playhead = 0.0
            self.selected_text_index = None
            self.selected_image_index = None
            self.timeline.load(path, dur)
            self.zoom_slider.set(1.0)
            self.start_entry.set_value(seconds_to_hms(0))
            self.end_entry.set_value(seconds_to_hms(dur))
            self._update_duration_label(0, dur)
            self.text_layers.clear_layers()
            self.text_layers.set_duration(dur)
            self.image_layers.clear_layers()
            self.image_layers.set_duration(dur)
            self.range_queue.clear()
            self._sync_timeline_clips()
            self.inspector.pages["text"].refresh()
            self.inspector.pages["image"].refresh()

            self.player.load_video(path, dur)
            self.preview_name.configure(text=name)
            self._set_media_card(path)
            self._update_timecode()
            self._update_export_enabled()
            if not preserve_project:
                self.current_project_path = None
                self._project_dirty = False
                project_files.delete_autosave()
                self._update_project_status()
            self._notify(f"Loaded {name}", "success")
        finally:
            self._restoring = False
        # Baseline undo history against the freshly-loaded state.
        self._undo_stack.reset(self._snapshot())
        self._show_workspace("edit")
        return True

    def _on_start_entry(self, value):
        try:
            start_sec = hms_to_seconds(value)
        except ValueError:
            return
        _, end_val = self.timeline.get_values()
        start_sec = max(0.0, min(start_sec, end_val - 0.05))
        self._apply_selection(start_sec, end_val)
        self._seek(start_sec)
        self._request_snapshot(immediate=True)

    def _on_end_entry(self, value):
        try:
            end_sec = hms_to_seconds(value)
        except ValueError:
            return
        start_val, _ = self.timeline.get_values()
        duration = (self.video_info or {}).get("duration", end_sec)
        end_sec = min(duration, max(end_sec, start_val + 0.05))
        self._apply_selection(start_val, end_sec)
        self._seek(end_sec)
        self._request_snapshot(immediate=True)

    def _update_duration_label(self, start, end):
        dur = max(0, end - start)
        self.duration_label.configure(text=f"Length  {seconds_to_hms(dur)}")

    def _update_export_enabled(self):
        self._update_size_estimate()

    def _update_size_estimate(self):
        if not self.video_path or not self.video_info or not hasattr(self, "timeline"):
            self.size_estimate_text = ""
            self._emit_state()
            return
        ranges = self._gather_ranges()
        duration = sum(max(0.0, e - s) for s, e in ranges)
        fmt = self.format_var.get()
        opts = self.export_options.get_options()
        est = estimate_bytes(
            duration, self.quality_var.get(),
            "MP3" if opts.get("audio_only") else fmt,
            self.video_info.get("width", 0),
            self.video_info.get("height", 0),
            audio_only=opts.get("audio_only"),
        )
        self.size_estimate_text = f"about {human_bytes(est)}"
        self._emit_state()

    # ------------------------------------------------------------------
    def _queue_range(self):
        if not self.video_path:
            return
        start, end = self.timeline.get_values()
        if self.range_queue.add_range(start, end):
            count = len(self.range_queue.get_ranges())
            self._notify(
                f"Saved range {count}: {seconds_to_hms(start)} → {seconds_to_hms(end)}",
                "success")
            self._request_snapshot(immediate=True)

    def remove_range(self, index):
        self.range_queue.remove(index)
        self._request_snapshot(immediate=True)

    def move_range(self, index, delta):
        if self.range_queue.move(index, delta):
            self._request_snapshot(immediate=True)

    # ------------------------------------------------------------------
    def _play_in_system(self):
        if not self.video_path:
            return
        if os.name == "nt":
            os.startfile(self.video_path)  # noqa: S606
        elif os.uname().sysname == "Darwin":
            subprocess.Popen(["open", self.video_path])
        else:
            subprocess.Popen(["xdg-open", self.video_path])

    def _set_crop_ui(self, on):
        self._crop_on = bool(on)
        self.crop_btn.configure(
            fg_color=T.ACCENT_SOFT if on else "transparent",
            text_color=T.ACCENT if on else T.TEXT_MUTED,
        )
        page = getattr(self, "inspector", None)
        if page is not None:
            page.pages["clip"].crop_btn.configure(
                text="Done cropping" if on else "Crop by hand…",
            )

    def _toggle_crop_mode(self):
        if not self.video_path:
            self._notify("Open a video first", "warn")
            return
        is_on = not self._crop_on
        self.player.enable_crop_mode(is_on, on_change=self._on_crop_changed)
        self._set_crop_ui(is_on)
        if is_on:
            self._notify("Drag a box on the preview to crop. Click Crop again when done.", "info")
        else:
            crop = self.player.get_crop()
            self._notify("Crop kept" if crop else "No crop set", "info")

    def clear_crop(self):
        settings.set("crop", None)
        self.player.set_crop(None)
        if self._crop_on:
            self.player.enable_crop_mode(False, on_change=self._on_crop_changed)
            self._set_crop_ui(False)
        self._update_size_estimate()
        self._request_snapshot(immediate=True)
        self._notify("Crop cleared", "info")

    def _on_crop_changed(self, rect):
        settings.set("crop", rect)
        self._update_size_estimate()
        self._request_snapshot(immediate=True)

    # ------------------------------------------------------------------
    def _auto_caption(self):
        """Run Whisper over the selection and import the result as captions."""
        if not self.video_path:
            self._notify("Load a video first", "warn")
            return
        # Late-import so the app still runs when faster-whisper isn't installed.
        from videokidnapper.core import whisper_captions

        if not whisper_captions.is_available():
            self._notify(
                "Auto-captions needs faster-whisper. "
                "Install with:  pip install faster-whisper",
                "error",
            )
            return

        # Small dialog: pick model size. Larger = slower + more accurate.
        dialog = ctk.CTkToplevel(self)
        dialog.title("Captions from speech")
        dialog.geometry("380x220")
        dialog.resizable(False, False)
        dialog.configure(fg_color=T.BG_BASE)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        card = ctk.CTkFrame(
            dialog, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            card, text="Write captions from the speech",
            font=T.font(T.SIZE_LG, "bold"), text_color=T.TEXT,
        ).pack(pady=(16, 8))

        model_var = ctk.StringVar(value="base")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(pady=4)
        ctk.CTkLabel(
            row, text="Accuracy model", font=T.font(T.SIZE_MD),
            text_color=T.TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))
        C.option_menu(row, list(whisper_captions.MODEL_SIZES),
                      variable=model_var, width=110).pack(side="left")

        ctk.CTkLabel(
            card,
            text=(
                "Transcribes the selection only.\n"
                "The first run downloads the model (~75 MB for base)."
            ),
            font=T.font(T.SIZE_SM), text_color=T.TEXT_MUTED,
            justify="center",
        ).pack(pady=(8, 4))

        def start():
            model_size = model_var.get()
            dialog.destroy()
            self._run_whisper_in_background(model_size)

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=10)
        button(btns, "Start", variant="primary", width=120,
               command=start).pack(side="left", padx=4)
        button(btns, "Cancel", variant="secondary", width=120,
               command=dialog.destroy).pack(side="left", padx=4)

    def _run_whisper_in_background(self, model_size):
        """Worker thread: transcribe then marshal the result back to Tk."""
        from videokidnapper.core import whisper_captions

        start, end = self.timeline.get_values()
        self._notify(f"Transcribing with Whisper ({model_size})…", "info")
        self.captions_btn.configure(state="disabled")

        def worker():
            try:
                entries = whisper_captions.transcribe(
                    self.video_path,
                    model_size=model_size,
                    start=start, end=end,
                )
            except Exception as exc:
                self.after(0, self._on_captions_failed, str(exc))
                return
            self.after(0, self._on_captions_done, entries)

        threading.Thread(target=worker, daemon=True).start()

    def _on_captions_done(self, entries):
        self.captions_btn.configure(state="normal")
        if not entries:
            self._notify("Whisper produced no text (silent clip?)", "warn")
            return
        self.text_layers.import_srt_layers(srt_to_text_layers(entries))
        self.select_layer("text", 0)
        self._notify(f"Imported {len(entries)} caption line(s)", "success")

    def _on_captions_failed(self, error):
        self.captions_btn.configure(state="normal")
        self._notify(f"Auto-captions failed: {error}", "error")

    def _import_srt(self):
        if not self.video_path:
            self._notify("Open a video first", "warn")
            return
        path = filedialog.askopenfilename(
            title="Import SRT subtitles",
            filetypes=[("SRT / VTT", "*.srt *.vtt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            entries = parse_srt_file(path)
            if not entries:
                self._notify("No subtitle entries found", "warn")
                return
            self.text_layers.import_srt_layers(srt_to_text_layers(entries))
            self.select_layer("text", 0)
            self._notify(f"Imported {len(entries)} subtitle line(s)", "success")
        except Exception as e:
            self._notify(f"SRT import failed: {e}", "error")

    # ------------------------------------------------------------------
    def _record_screen(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Record your screen")
        dialog.geometry("360x200")
        dialog.resizable(False, False)
        dialog.configure(fg_color=T.BG_BASE)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        card = ctk.CTkFrame(
            dialog, fg_color=T.BG_SURFACE,
            border_width=1, border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(
            card, text="Record the main monitor",
            font=T.font(T.SIZE_LG, "bold"), text_color=T.TEXT,
        ).pack(pady=(18, 8))

        dur_var = ctk.StringVar(value="10")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(pady=4)
        ctk.CTkLabel(row, text="Seconds (1–120)",
                     font=T.font(T.SIZE_MD), text_color=T.TEXT_MUTED).pack(side="left")
        C.entry(row, textvariable=dur_var, width=70, mono=True).pack(side="left", padx=8)

        def start():
            try:
                seconds = max(1, min(120, int(dur_var.get())))
            except ValueError:
                seconds = 10
            dialog.destroy()
            self._run_screen_recording(seconds)

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(pady=14)
        button(btns, "Start recording", variant="primary", width=130,
               command=start).pack(side="left", padx=4)
        button(btns, "Cancel", variant="secondary", width=100,
               command=dialog.destroy).pack(side="left", padx=4)

    def _run_screen_recording(self, duration_seconds):
        self._notify(f"Recording {duration_seconds}s — window will minimize...", "info")
        self.winfo_toplevel().iconify()
        time.sleep(0.4)  # let the window minimize before capture begins

        def worker():
            try:
                frame_dir, fps, count = record_screen(
                    duration_seconds, fps=15,
                    progress_callback=None,
                )
            except Exception as e:
                self.after(0, self._on_record_failed, str(e))
                return
            if count < 2:
                self.after(0, self._on_record_failed, "No frames captured")
                return
            # A screen recording has no source video, so the title
            # styles fall back to "clip" — which is the honest answer.
            output = generate_export_path(
                "record", "mp4",
                base_dir=self.export_options.get_output_folder(),
                source_name="screen recording",
            )
            preset = self.quality_var.get()
            result = frames_to_video(str(frame_dir), fps, preset, str(output))
            self.after(0, self._on_record_done, str(result) if result else None)

        threading.Thread(target=worker, daemon=True).start()

    def _on_record_done(self, path):
        self.winfo_toplevel().deiconify()
        if not path:
            self._notify("Recording failed during encoding", "error")
            return
        self._notify(f"Recorded {os.path.basename(path)}", "success")
        self._load_path(path)

    def _on_record_failed(self, error):
        self.winfo_toplevel().deiconify()
        self._notify(f"Recording failed: {error}", "error")

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------
    def _toggle_play(self):
        if not self.video_path:
            return
        if self.player._playing:
            self._stop_playback()
            return
        start, end = self.timeline.get_values()
        # Play from the playhead when it's inside the selection, otherwise
        # from the in point.
        begin = self.playhead if start <= self.playhead < end - 0.05 else start
        self.player.play(start=begin, end=end)
        self.play_btn.configure(text=glyph("pause"))
        self.after(_PLAY_POLL_MS, self._poll_play_state)

    def _stop_playback(self):
        self.player.stop()
        self.play_btn.configure(text=glyph("play"))
        self.playhead = float(self.player.current_time)
        self.timeline.set_playhead(self.playhead)
        self._update_timecode()

    def _poll_play_state(self):
        if not self.winfo_exists():
            return
        self.playhead = float(self.player.current_time)
        self.timeline.set_playhead(self.playhead)
        self._update_timecode()
        if not self.player._playing:
            self.play_btn.configure(text=glyph("play"))
            return
        self.after(_PLAY_POLL_MS, self._poll_play_state)

    # ------------------------------------------------------------------
    # Keyboard shortcuts bound by App
    # ------------------------------------------------------------------
    def keyboard_play_pause(self):
        self._toggle_play()

    def keyboard_nudge(self, delta_seconds):
        """J / L: step the playhead (the old build moved the in point)."""
        if not self.video_path:
            return
        self._seek(self.playhead + delta_seconds)

    def keyboard_mark_in(self):
        if not self.video_path:
            return
        _, end = self.timeline.get_values()
        start = self.playhead
        if end <= start + 0.05:
            end = self.video_info["duration"]
        self._apply_selection(start, end)
        self._request_snapshot(immediate=True)

    def keyboard_mark_out(self):
        if not self.video_path:
            return
        start, _ = self.timeline.get_values()
        end = self.playhead
        if end <= start + 0.05:
            start = 0.0
        self._apply_selection(start, end)
        self._request_snapshot(immediate=True)

    def keyboard_save_range(self):
        self._queue_range()

    def keyboard_export(self):
        if self.video_path:
            self._export()

    def keyboard_open(self):
        self._open_file()

    def keyboard_save_project(self):
        self.save_project()

    def keyboard_save_project_as(self):
        self.save_project(save_as=True)

    def keyboard_open_project(self):
        self.choose_and_open_project()

    def keyboard_paste_url(self):
        """Ctrl+V with an image on the clipboard adds an image overlay."""
        self.paste_image_layer()

    def keyboard_undo(self):
        """Restore the last recorded snapshot (Ctrl+Z)."""
        # Flush any pending debounced edit so the user undoes the most
        # recent "settled" state, not whatever was there 350ms ago.
        self._flush_pending_snapshot()
        snap = self._undo_stack.undo()
        if snap is None:
            self._notify("Nothing to undo", "info")
            return
        self._apply_snapshot(snap)
        self._notify("Undo", "info")

    def keyboard_redo(self):
        """Re-apply a snapshot previously popped by undo (Ctrl+Y / Ctrl+Shift+Z)."""
        self._flush_pending_snapshot()
        snap = self._undo_stack.redo()
        if snap is None:
            self._notify("Nothing to redo", "info")
            return
        self._apply_snapshot(snap)
        self._notify("Redo", "info")

    # ------------------------------------------------------------------
    # Undo/redo snapshot plumbing
    # ------------------------------------------------------------------
    def _snapshot(self):
        """Capture the slice of editor state that undo/redo should restore.

        Export preferences (quality, format, output folder, fade, etc.)
        are intentionally excluded — they're settings, not edits, and
        users don't expect Ctrl+Z to toggle them.
        """
        crop = self.player.get_crop() if hasattr(self, "player") else None
        return {
            "range":  tuple(self.timeline.get_values()),
            "queued": list(self.range_queue.get_ranges()),
            "crop":   dict(crop) if crop else None,
            "layers": [
                dict(layer)
                for layer in self.text_layers.get_all_layers(include_empty=True)
            ],
            "images": [
                dict(layer)
                for layer in self.image_layers.get_all_layers(include_empty=True)
            ],
        }

    def _request_snapshot(self, immediate=False):
        """Schedule (or immediately commit) a new undo-history entry."""
        if self._restoring or not self.video_path:
            return
        if self._snapshot_after_id is not None:
            try:
                self.after_cancel(self._snapshot_after_id)
            except Exception:
                pass
            self._snapshot_after_id = None
        if immediate:
            self._commit_snapshot()
        else:
            self._snapshot_after_id = self.after(
                self._snapshot_debounce_ms, self._commit_snapshot,
            )

    def _commit_snapshot(self):
        self._snapshot_after_id = None
        if self._restoring or not self.video_path:
            return
        self._undo_stack.record(self._snapshot())
        self._mark_project_dirty()

    def _flush_pending_snapshot(self):
        if self._snapshot_after_id is None:
            return
        try:
            self.after_cancel(self._snapshot_after_id)
        except Exception:
            pass
        self._snapshot_after_id = None
        self._commit_snapshot()

    def _apply_snapshot(self, snap):
        """Restore editor state from ``snap`` without re-recording."""
        if not snap:
            return
        self._restoring = True
        try:
            start, end = snap.get(
                "range", (0.0, float((self.video_info or {}).get("duration", 0.0))),
            )
            self._apply_selection(start, end)
            self.range_queue.set_ranges(snap.get("queued", []))

            # Crop rect.
            self.player.set_crop(snap.get("crop"))
            settings.set("crop", snap.get("crop"))

            # Captions and overlays — rebuild the model rows from dicts.
            self.text_layers.clear_layers()
            for data in snap.get("layers", []):
                self.text_layers._add_layer(preset_data=data)

            self.image_layers.clear_layers()
            for data in snap.get("images", []):
                self.image_layers._add_layer(preset_data=data)

            self._clamp_selection_indices()
            self._sync_timeline_clips()
            for kind in ("text", "image"):
                self.inspector.pages[kind].layer = None
                self.inspector.pages[kind].refresh()

            # Show the frame at the playhead and refresh the overlay.
            self.player.show_frame(self.playhead)
            self._update_export_enabled()
        finally:
            self._restoring = False

    # ------------------------------------------------------------------
    # Project files, autosave, and recovery
    # ------------------------------------------------------------------
    def _project_export_state(self):
        options = dict(self.export_options.get_options())
        options["output_folder"] = self.export_options.get_output_folder()
        return {
            "platform": self.platform_var.get(),
            "quality": self.quality_var.get(),
            "format": self.format_var.get(),
            "options": options,
        }

    def _project_document(self, project_path=None):
        return project_files.build_document(
            self.video_path,
            self._snapshot(),
            self._project_export_state(),
            project_path=project_path,
        )

    def _mark_project_dirty(self):
        if self._restoring or not self.video_path:
            return
        self._project_dirty = True
        self._update_project_status()
        if self._autosave_after_id is not None:
            try:
                self.after_cancel(self._autosave_after_id)
            except Exception:
                pass
        self._autosave_after_id = self.after(
            self._autosave_debounce_ms, self._write_autosave,
        )

    def _write_autosave(self):
        self._autosave_after_id = None
        if not self.video_path or not self._project_dirty:
            return
        try:
            document = self._project_document(self.current_project_path)
            project_files.save_document(project_files.autosave_path(), document)
        except Exception as exc:
            self._notify(f"Autosave failed: {exc}", "warn")

    def _update_project_status(self):
        setter = getattr(self.app, "set_project_status", None)
        if not callable(setter):
            return
        name = (
            Path(self.current_project_path).stem
            if self.current_project_path else "Untitled"
        )
        setter(name, self._project_dirty)

    def open_project_hub(self):
        from videokidnapper.ui.project_dialog import ProjectDialog
        ProjectDialog(self.app, self)

    def save_project(self, save_as=False, target=None):
        if not self.video_path:
            self._notify("Load a video before saving a project", "warn")
            return False
        path = target or (None if save_as else self.current_project_path)
        if not path:
            path = filedialog.asksaveasfilename(
                title="Save VideoKidnapper Project",
                defaultextension=project_files.PROJECT_EXTENSION,
                filetypes=[
                    ("VideoKidnapper projects", "*.vidkid"),
                    ("All files", "*.*"),
                ],
            )
        if not path:
            return False
        try:
            document = self._project_document(path)
            saved = project_files.save_document(path, document)
        except Exception as exc:
            self._notify(f"Could not save project: {exc}", "error")
            return False
        self.current_project_path = str(saved)
        self._project_dirty = False
        settings.add_recent_project(saved)
        project_files.delete_autosave()
        self._update_project_status()
        self._notify(f"Saved project: {saved.name}", "success")
        return True

    def choose_and_open_project(self):
        path = filedialog.askopenfilename(
            title="Open VideoKidnapper Project",
            filetypes=[
                ("VideoKidnapper projects", "*.vidkid"),
                ("All files", "*.*"),
            ],
        )
        return self.open_project(path) if path else False

    def open_project(self, path, recovery=False):
        try:
            document = project_files.load_document(path)
        except project_files.ProjectFileError as exc:
            self._notify(str(exc), "error")
            return False

        source = Path(document["resolved_source"])
        if not source.is_file():
            replacement = filedialog.askopenfilename(
                title="Locate the project's source video",
                filetypes=[("Video files", "*.*")],
            )
            if not replacement:
                self._notify("Project source video was not found", "warn")
                return False
            source = Path(replacement)

        if not recovery and not self._prepare_to_replace_project():
            return False
        if not self._load_path(str(source), preserve_project=True):
            return False
        self._apply_snapshot(document.get("editor") or {})
        self._restoring = True
        try:
            export = document.get("export") or {}
            platform = str(export.get("platform", "Custom"))
            self.platform_var.set(
                platform if platform in PLATFORM_CHOICES else "Custom",
            )
            quality = str(export.get("quality", "Medium"))
            self.quality_var.set(quality if quality in PRESETS else "Medium")
            fmt = str(export.get("format", "GIF"))
            self.format_var.set(fmt if fmt in EXPORT_FORMATS else "GIF")
            self.export_options.apply_options(export.get("options") or {})
        finally:
            self._restoring = False

        linked = document.get("linked_project_path") or ""
        self.current_project_path = (
            str(Path(linked).expanduser().resolve())
            if recovery and linked else str(Path(path).expanduser().resolve())
        )
        self._project_dirty = bool(recovery)
        if not recovery:
            settings.add_recent_project(self.current_project_path)
            project_files.delete_autosave()
        self._undo_stack.reset(self._snapshot())
        self._update_project_status()
        self.player.refresh_overlay()
        self._emit_state()
        self._notify(
            "Recovered autosaved project" if recovery else
            f"Opened project: {Path(path).name}",
            "success",
        )
        return True

    def discard_recovery(self):
        project_files.delete_autosave()

    def _prepare_to_replace_project(self):
        if not self._project_dirty:
            return True
        choice = messagebox.askyesnocancel(
            "Save current project?",
            "Save the current project before opening something else?",
            parent=self.app,
        )
        if choice is None:
            return False
        if choice and not self.save_project():
            return False
        return True

    def request_close(self):
        self._flush_pending_snapshot()
        if self._autosave_after_id is not None:
            try:
                self.after_cancel(self._autosave_after_id)
            except Exception:
                pass
            self._autosave_after_id = None
        if self._project_dirty:
            self._write_autosave()
        if not self._project_dirty:
            project_files.delete_autosave()
            return True
        choice = messagebox.askyesnocancel(
            "Save project?",
            "Save your VideoKidnapper project before closing?",
            parent=self.app,
        )
        if choice is None:
            return False
        if choice and not self.save_project():
            return False
        project_files.delete_autosave()
        return True

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def _gather_ranges(self):
        """Saved ranges + current selection = ranges to export."""
        ranges = list(self.range_queue.get_ranges())
        start, end = self.timeline.get_values()
        ranges.append((start, end))
        return ranges

    def _export(self):
        if not self.video_path:
            return

        preset = self.quality_var.get()
        fmt = self.format_var.get()
        options = self.export_options.get_options()
        ext = "mp3" if options.get("audio_only") else ("gif" if fmt == "GIF" else "mp4")

        output_dir = Path(self.export_options.get_output_folder())
        output_dir.mkdir(parents=True, exist_ok=True)

        layers = self.text_layers.get_all_layers()
        image_layers = self.image_layers.get_all_layers()
        ranges = self._gather_ranges()
        concat = options.get("concat") and len(ranges) > 1 and fmt != "GIF" \
                 and not options.get("audio_only")

        title_suffix = " (joined)" if concat else ""
        dialog = ExportDialog(
            self,
            title=f"Exporting {len(ranges)} clip{'s' if len(ranges) != 1 else ''}{title_suffix}...",
        )
        self._notify(f"Exporting {len(ranges)} clip(s) [{preset}]{title_suffix}...", "info")

        def run_export():
            produced = []
            for i, (start, end) in enumerate(ranges, 1):
                if dialog.cancel_event.is_set():
                    break
                output_path = str(generate_export_path(
                    "trim", ext, base_dir=output_dir,
                    source_name=self.source_title,
                ))

                def progress_cb(p, i=i):
                    if dialog.winfo_exists():
                        prog = ((i - 1) + p) / len(ranges)
                        dialog.after(0, dialog.update_progress, prog,
                                     f"Clip {i}/{len(ranges)} — encoding {fmt}...")
                try:
                    if options.get("audio_only"):
                        result = trim_to_video(
                            self.video_path, start, end, preset, output_path,
                            text_layers=layers, options=options,
                            progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                        )
                    elif fmt == "GIF":
                        # GIF + image overlays encodes an intermediate MP4
                        # first (see ffmpeg_backend.trim_to_gif) — slower
                        # but keeps the filter-graph plumbing simple.
                        result = trim_to_gif(
                            self.video_path, start, end, preset, output_path,
                            text_layers=layers, image_layers=image_layers,
                            options=options,
                            progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                        )
                    else:
                        result = trim_to_video(
                            self.video_path, start, end, preset, output_path,
                            text_layers=layers, image_layers=image_layers,
                            options=options,
                            progress_callback=progress_cb, cancel_event=dialog.cancel_event,
                        )
                    if result:
                        produced.append(str(result))
                    else:
                        if dialog.winfo_exists():
                            dialog.after(0, dialog.export_failed,
                                         f"Clip {i} failed — aborting")
                        return
                except Exception as e:
                    if dialog.winfo_exists():
                        dialog.after(0, dialog.export_failed, f"Error: {e}")
                        self._notify(f"Export error: {e}", "error")
                    return

            final_path = None
            if concat and len(produced) > 1:
                combined = str(generate_export_path(
                    "trim_concat", ext, base_dir=output_dir,
                    source_name=self.source_title,
                ))
                # Pick transition from the export options. "cut" stays on
                # the fast lossless concat demuxer path; anything else
                # re-encodes via filter_complex xfade + acrossfade.
                transition = options.get("concat_transition", "cut")
                trans_dur = options.get("concat_transition_duration", 0.5)
                merged = concat_clips_with_transition(
                    produced, combined,
                    transition=transition, duration=trans_dur,
                )
                if merged:
                    final_path = str(merged)
                    for p in produced:
                        try:
                            Path(p).unlink()
                        except OSError:
                            pass
            if not final_path:
                final_path = produced[-1] if produced else None

            if final_path and dialog.winfo_exists():
                settings.set("last_export", final_path)
                self._record_history(final_path, fmt, preset, options)
                dialog.after(0, dialog.export_complete, final_path)
                self._notify(f"Exported {len(ranges)} clip(s)", "success")
            elif dialog.winfo_exists():
                dialog.after(0, dialog.export_failed, "Cancelled")
                self._notify("Export cancelled", "warn")

        threading.Thread(target=run_export, daemon=True).start()

    def _record_history(self, path, fmt, preset, options):
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = 0
        settings.add_history_entry({
            "path":      path,
            "format":    "MP3" if options.get("audio_only") else fmt,
            "preset":    preset,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "size_bytes": size,
            "mode":      "trim",
        })
        # Deliberately the non-forcing accessor: History is built on
        # first view, and it loads its data at construction. Reaching
        # through `self.app.history_tab` here would build it after every
        # export just to refresh something nobody is looking at.
        from videokidnapper.app import TAB_HISTORY

        history = getattr(self.app, "_tab_if_built", lambda _n: None)(TAB_HISTORY)
        if history is not None and history.winfo_exists():
            history.after(0, history.refresh)
