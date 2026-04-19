# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Image / logo overlay track.

Mirrors the pattern of :class:`TextLayersPanel` but each row carries
a PNG / JPG path instead of a text string. The collapsible container,
+ add button, scrollable body, and notify-on-change signalling are
deliberately similar so the panels read as "same shape, different
payload" rather than two bespoke widgets.

Per-layer controls:
  - File picker (path)
  - Position anchor (7 presets — matches text anchors)
  - Scale (5% to 100% of the image's own width)
  - Opacity (0 to 100%)
  - Timing range slider (start / end within video duration)
  - Remove button

Live preview is deliberately out of scope for this first ship — the
export bakes the overlays in, so users see them when they encode.
Follow-up can add PIL-based compositing to VideoPlayer if desired.
"""

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from videokidnapper.ui import theme as T
from videokidnapper.ui.widgets import RangeSlider


POSITION_ANCHORS = [
    "Top Left", "Top Center", "Top Right",
    "Center",
    "Bottom Left", "Bottom Center", "Bottom Right",
]

_DISPLAY_TO_KEY = {
    "Top Left":      "top_left",
    "Top Center":    "top_center",
    "Top Right":     "top_right",
    "Center":        "center",
    "Bottom Left":   "bottom_left",
    "Bottom Center": "bottom_center",
    "Bottom Right":  "bottom_right",
}
_KEY_TO_DISPLAY = {v: k for k, v in _DISPLAY_TO_KEY.items()}


SUPPORTED_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


class ImageLayerWidget(ctk.CTkFrame):
    """A single image-overlay row with every knob the user needs."""

    def __init__(self, master, layer_index, video_duration,
                 on_remove=None, **kwargs):
        super().__init__(
            master,
            corner_radius=T.RADIUS_MD,
            border_width=1,
            border_color=T.BORDER,
            fg_color=T.BG_RAISED,
            **kwargs,
        )
        self.layer_index = layer_index
        self.video_duration = max(0.1, float(video_duration))
        self.on_remove = on_remove

        self.path_var     = ctk.StringVar(value="")
        self.position_var = ctk.StringVar(value="Top Right")
        self.scale_var    = ctk.DoubleVar(value=0.25)
        self.opacity_var  = ctk.DoubleVar(value=1.0)
        # Explicit drag position in source-video pixel coords. ``-1``
        # is the sentinel for "unset" — when either axis is -1 the
        # renderer + backend fall back to the anchor dropdown. Dragging
        # the overlay on the preview sets both; picking a new anchor
        # from the dropdown clears both back to -1.
        self.x_var = ctk.IntVar(value=-1)
        self.y_var = ctk.IntVar(value=-1)

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        # Row 1: header + remove
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            row1, text=f"Image {self.layer_index + 1}",
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT,
        ).pack(side="left")

        ctk.CTkButton(
            row1, text="✕", width=28, height=28,
            fg_color=T.DANGER, hover_color=T.DANGER_HOVER,
            font=T.font(T.SIZE_MD, "bold"),
            corner_radius=T.RADIUS_SM,
            command=self._on_remove,
        ).pack(side="right")

        # Row 2: path picker
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=2)

        self.path_entry = ctk.CTkEntry(
            row2, textvariable=self.path_var,
            placeholder_text="PNG / JPG path…",
            font=ctk.CTkFont(size=12), height=28,
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            row2, text="Browse", width=70, height=28,
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT,
            font=T.font(T.SIZE_SM, "bold"),
            corner_radius=T.RADIUS_SM,
            command=self._pick_file,
        ).pack(side="left")

        # Row 3: position + scale + opacity
        row3 = ctk.CTkFrame(self, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(row3, text="Position:",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        # Picking an anchor wipes any drag-applied x/y so the dropdown
        # is always truthful about where the overlay sits.
        ctk.CTkOptionMenu(
            row3, variable=self.position_var,
            values=POSITION_ANCHORS, width=130,
            command=lambda _v: self._clear_drag_position(),
        ).pack(side="left", padx=(2, 10))

        ctk.CTkLabel(row3, text="Scale:",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self.scale_label = ctk.CTkLabel(
            row3, text=f"{int(self.scale_var.get() * 100)}%",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=T.TEXT_DIM, width=42,
        )
        ctk.CTkSlider(
            row3, from_=0.05, to=1.0, variable=self.scale_var,
            width=110, command=self._on_scale_change,
        ).pack(side="left", padx=(2, 0))
        self.scale_label.pack(side="left", padx=(4, 10))

        ctk.CTkLabel(row3, text="Opacity:",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self.opacity_label = ctk.CTkLabel(
            row3, text=f"{int(self.opacity_var.get() * 100)}%",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=T.TEXT_DIM, width=42,
        )
        ctk.CTkSlider(
            row3, from_=0.0, to=1.0, variable=self.opacity_var,
            width=110, command=self._on_opacity_change,
        ).pack(side="left", padx=(2, 0))
        self.opacity_label.pack(side="left", padx=(4, 0))

        # Row 4: timing slider
        row4 = ctk.CTkFrame(self, fg_color="transparent")
        row4.pack(fill="x", padx=10, pady=(2, 8))

        ctk.CTkLabel(row4, text="Visible:",
                     font=ctk.CTkFont(size=11)).pack(side="left")
        self.time_slider = RangeSlider(
            row4, from_=0, to=self.video_duration,
            command=self._on_time_change,
        )
        self.time_slider.pack(side="left", fill="x", expand=True, padx=(5, 5))

        from videokidnapper.utils.time_format import seconds_to_hms
        self.time_label = ctk.CTkLabel(
            row4,
            text=f"0s - {seconds_to_hms(self.video_duration)}",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="gray",
        )
        self.time_label.pack(side="right")

    # ------------------------------------------------------------------
    def _pick_file(self):
        exts = " ".join(f"*{e}" for e in SUPPORTED_IMAGE_EXTS)
        path = filedialog.askopenfilename(
            title="Pick an overlay image",
            filetypes=[("Images", exts), ("All files", "*.*")],
        )
        if path:
            self.path_var.set(path)

    def _on_remove(self):
        if self.on_remove:
            self.on_remove(self)

    def _on_scale_change(self, _val):
        self.scale_label.configure(text=f"{int(self.scale_var.get() * 100)}%")

    def _on_opacity_change(self, _val):
        self.opacity_label.configure(text=f"{int(self.opacity_var.get() * 100)}%")

    def _on_time_change(self, start, end):
        from videokidnapper.utils.time_format import seconds_to_hms
        self.time_label.configure(
            text=f"{seconds_to_hms(start)} - {seconds_to_hms(end)}",
        )

    # ------------------------------------------------------------------
    def update_duration(self, duration):
        self.video_duration = max(0.1, float(duration))
        self.time_slider.set_range(0, self.video_duration)

    def set_position(self, source_x, source_y):
        """Apply a drag-positioned (x, y) in source-video pixel coords.

        Called by the VideoPlayer drag handler each time the user
        moves the overlay. Setting the vars triggers the panel's
        ``trace_add`` wiring, so the preview refreshes live.
        """
        self.x_var.set(max(0, int(source_x)))
        self.y_var.set(max(0, int(source_y)))

    def _clear_drag_position(self):
        """Reset drag override so the overlay snaps back to the anchor."""
        self.x_var.set(-1)
        self.y_var.set(-1)

    def get_layer_data(self):
        """Return the dict ffmpeg_backend.trim_to_video consumes.

        ``x`` and ``y`` are only included when the user has dragged the
        overlay (sentinels cleared). Both the preview renderer and the
        backend filter read them as the override when present and fall
        back to ``position`` (anchor) otherwise.
        """
        start, end = self.time_slider.get_values()
        data = {
            "path":     self.path_var.get(),
            "position": _DISPLAY_TO_KEY.get(self.position_var.get(), "top_right"),
            "scale":    float(self.scale_var.get()),
            "opacity":  float(self.opacity_var.get()),
            "start":    float(start),
            "end":      float(end),
        }
        x, y = int(self.x_var.get()), int(self.y_var.get())
        if x >= 0 and y >= 0:
            data["x"] = x
            data["y"] = y
        return data


class ImageLayersPanel(ctk.CTkFrame):
    """Collapsible panel mirroring :class:`TextLayersPanel` for images."""

    _CHEVRON_OPEN   = "▾"
    _CHEVRON_CLOSED = "▸"

    def __init__(self, master, on_change=None, on_notify=None, **kwargs):
        super().__init__(
            master,
            fg_color=T.BG_SURFACE,
            border_width=1,
            border_color=T.BORDER,
            corner_radius=T.RADIUS_LG,
            **kwargs,
        )
        self.layers = []
        self.video_duration = 0.0
        self._expanded = False
        self._on_change = on_change
        # Optional ``(message, level)`` sink so clipboard-paste failures
        # surface to the user via the main status toast instead of the
        # console. Parent tab sets this after construction.
        self._on_notify = on_notify

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        self.toggle_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.toggle_frame.pack(fill="x")

        self.toggle_btn = ctk.CTkButton(
            self.toggle_frame,
            text=f"  {self._CHEVRON_CLOSED}   Image Overlays  ·  0",
            font=T.font(T.SIZE_LG, "bold"),
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_MD,
            height=40, anchor="w",
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", padx=4, pady=4)

        self.content = ctk.CTkFrame(self, fg_color="transparent")

        from videokidnapper.ui.theme import button as _btn
        btn_row = ctk.CTkFrame(self.content, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(6, 6))

        self.add_btn = _btn(
            btn_row, "  +  Add Image Overlay",
            variant="secondary", width=200, height=30,
            font=T.font(T.SIZE_MD, "bold"),
        )
        self.add_btn.configure(command=self._add_layer)
        self.add_btn.pack(side="left")

        # Paste-from-clipboard button — discoverable second entry-point
        # alongside the Ctrl+V shortcut. Useful when the user has just
        # copied an image and isn't sure the keybind is wired up.
        self.paste_btn = _btn(
            btn_row, "  📋  Paste from clipboard",
            variant="ghost", width=190, height=30,
            font=T.font(T.SIZE_MD),
        )
        self.paste_btn.configure(command=self._on_paste_clicked)
        self.paste_btn.pack(side="left", padx=(6, 0))

        self.layers_container = ctk.CTkScrollableFrame(
            self.content,
            fg_color="transparent",
            height=200,
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        self.layers_container.pack(fill="x", padx=12, pady=(0, 10))

    # ------------------------------------------------------------------
    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.content.pack(fill="x", after=self.toggle_frame)
        else:
            self.content.pack_forget()
        self._update_header()

    def _add_layer(self):
        layer = ImageLayerWidget(
            self.layers_container,
            layer_index=len(self.layers),
            video_duration=self.video_duration,
            on_remove=self._remove_layer,
        )
        layer.pack(fill="x", pady=(0, 5))
        self.layers.append(layer)
        self._wire_layer_change(layer)
        self._update_header()
        self._notify_change()

        if not self._expanded:
            self._toggle()
        return layer

    def set_layer_position(self, index, source_x, source_y):
        """Apply a drag-positioned (x, y) to ``layers[index]``.

        Called by :class:`VideoPlayer` each time the user drags an
        image overlay on the preview canvas. Out-of-range indices are
        silently ignored (the provider list can race with a remove).
        """
        if not (0 <= index < len(self.layers)):
            return
        self.layers[index].set_position(source_x, source_y)

    def add_layer_from_path(self, path):
        """Add a new image layer pre-populated with ``path``.

        Public hook used by both the clipboard-paste handler and any
        future drag-drop route. Returns the newly-created widget, or
        ``None`` if ``path`` is falsy (so callers can chain without a
        null check).
        """
        if not path:
            return None
        layer = self._add_layer()
        layer.path_var.set(str(path))
        return layer

    # ------------------------------------------------------------------
    # Clipboard paste — driven by the Paste button and Ctrl+V from
    # TrimTab. Silent-success through to add_layer_from_path; toasts on
    # the failure path so the user knows why nothing happened.
    def _on_paste_clicked(self):
        from videokidnapper.utils.clipboard_image import grab_clipboard_image
        path = grab_clipboard_image()
        if path is None:
            self._notify("No image in clipboard — copy one first.", "warn")
            return
        self.add_layer_from_path(path)
        self._notify("Added image overlay from clipboard.", "success")

    def _notify(self, message, level="info"):
        if self._on_notify:
            self._on_notify(message, level)

    def _wire_layer_change(self, layer):
        """Fire :meth:`_notify_change` whenever the user edits any knob.

        Without this, the live preview only refreshed on add / remove —
        slider drags, path picks, and anchor changes would all silently
        bypass ``on_change``. Traces on the Tk vars catch every mutation.
        """
        def fire(*_):
            self._notify_change()
        layer.path_var.trace_add("write", fire)
        layer.position_var.trace_add("write", fire)
        layer.scale_var.trace_add("write", fire)
        layer.opacity_var.trace_add("write", fire)
        # Drag-override coords: the drag handler writes both x and y
        # per motion event, so we fire on either to keep the preview
        # repaint in lockstep with the drag.
        layer.x_var.trace_add("write", fire)
        layer.y_var.trace_add("write", fire)

        # Timing slider doesn't use a Tk var; it calls the command
        # passed at construction. Wrap the existing callback to also
        # fire our on_change.
        original_time_cb = layer._on_time_change
        def time_cb(start, end):
            original_time_cb(start, end)
            self._notify_change()
        layer._on_time_change = time_cb
        layer.time_slider.command = time_cb

    def _remove_layer(self, layer_widget):
        if layer_widget in self.layers:
            self.layers.remove(layer_widget)
            layer_widget.destroy()
            for i, layer in enumerate(self.layers):
                layer.layer_index = i
            self._update_header()
            self._notify_change()

    def _update_header(self):
        chev = self._CHEVRON_OPEN if self._expanded else self._CHEVRON_CLOSED
        self.toggle_btn.configure(
            text=f"  {chev}   Image Overlays  ·  {len(self.layers)}",
        )

    def _notify_change(self):
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass

    # ------------------------------------------------------------------
    def set_duration(self, duration):
        self.video_duration = float(duration)
        for layer in self.layers:
            layer.update_duration(duration)

    def clear_layers(self):
        for layer in self.layers:
            layer.destroy()
        self.layers.clear()
        self._update_header()

    def get_all_layers(self, include_empty=False):
        """Return only layers with a non-empty ``path`` by default."""
        result = []
        for layer in self.layers:
            data = layer.get_layer_data()
            if include_empty or Path(data["path"]).is_file():
                result.append(data)
        return result
