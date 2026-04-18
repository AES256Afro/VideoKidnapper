# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import os
import tkinter.font as tkfont

import customtkinter as ctk

from videokidnapper.config import TEXT_STYLES, POSITION_MAP, TEXT_COLORS
from videokidnapper.ui import theme as T
from videokidnapper.ui.widgets import RangeSlider


def _get_system_fonts():
    try:
        families = sorted(set(tkfont.families()))
        preferred = ["Arial", "Segoe UI", "Helvetica", "Verdana", "Times New Roman",
                      "Courier New", "Georgia", "Impact", "Comic Sans MS", "Trebuchet MS"]
        top = [f for f in preferred if f in families]
        rest = [f for f in families if f not in top and not f.startswith("@")]
        return top + rest
    except Exception:
        return ["Arial", "Segoe UI", "Helvetica", "Verdana", "Times New Roman"]


def _find_font_path(font_name):
    fonts_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    name_lower = font_name.lower().replace(" ", "")
    common = {
        "arial": "arial.ttf", "arialblack": "ariblk.ttf",
        "segoeui": "segoeui.ttf", "helvetica": "arial.ttf",
        "verdana": "verdana.ttf", "timesnewroman": "times.ttf",
        "couriernew": "cour.ttf", "georgia": "georgia.ttf",
        "impact": "impact.ttf", "comicsansms": "comic.ttf",
        "trebuchetms": "trebuc.ttf", "tahoma": "tahoma.ttf",
        "calibri": "calibri.ttf", "cambria": "cambria.ttc",
        "consolas": "consola.ttf", "lucidaconsole": "lucon.ttf",
    }
    if name_lower in common:
        path = os.path.join(fonts_dir, common[name_lower])
        if os.path.exists(path):
            return path
    # Try direct match
    for ext in (".ttf", ".otf", ".ttc"):
        path = os.path.join(fonts_dir, font_name.replace(" ", "") + ext)
        if os.path.exists(path):
            return path
        path = os.path.join(fonts_dir, font_name.replace(" ", "").lower() + ext)
        if os.path.exists(path):
            return path
    # Fallback to arial
    return os.path.join(fonts_dir, "arial.ttf")


class TextLayerWidget(ctk.CTkFrame):
    """A single text layer with all its controls."""

    def __init__(self, master, layer_index, video_duration,
                 on_remove=None, on_duplicate=None, on_move=None, **kwargs):
        super().__init__(
            master,
            corner_radius=T.RADIUS_MD,
            border_width=1,
            border_color=T.BORDER,
            fg_color=T.BG_RAISED,
            **kwargs,
        )
        self.layer_index = layer_index
        self.video_duration = video_duration
        self.on_remove = on_remove
        self.on_duplicate = on_duplicate
        self.on_move = on_move
        self._fonts = None
        self._custom_color = None  # hex string if user picked a custom color
        # When the user drags the layer on the preview we store the source-
        # pixel coords here. Selecting a preset from the dropdown clears it.
        self._custom_position = None  # {"x": int, "y": int} or None

        self._build_ui()

    def _build_ui(self):
        # Row 1: Header + style preset + remove button
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            row1, text=f"Layer {self.layer_index + 1}",
            font=T.font(T.SIZE_LG, "bold"),
            text_color=T.TEXT,
        ).pack(side="left")

        self.remove_btn = ctk.CTkButton(
            row1, text="✕", width=28, height=28,
            fg_color=T.DANGER, hover_color=T.DANGER_HOVER,
            font=T.font(T.SIZE_MD, "bold"),
            corner_radius=T.RADIUS_SM,
            command=self._on_remove,
        )
        self.remove_btn.pack(side="right")

        self.dup_btn = ctk.CTkButton(
            row1, text="⧉", width=28, height=28,
            fg_color=T.BG_RAISED, hover_color=T.BG_HOVER,
            text_color=T.TEXT,
            font=T.font(T.SIZE_MD, "bold"),
            corner_radius=T.RADIUS_SM,
            command=self._on_duplicate,
        )
        self.dup_btn.pack(side="right", padx=(0, 4))

        self.down_btn = ctk.CTkButton(
            row1, text="▼", width=24, height=28,
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_MUTED,
            font=T.font(T.SIZE_SM),
            corner_radius=T.RADIUS_SM,
            command=lambda: self._on_move(1),
        )
        self.down_btn.pack(side="right")

        self.up_btn = ctk.CTkButton(
            row1, text="▲", width=24, height=28,
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_MUTED,
            font=T.font(T.SIZE_SM),
            corner_radius=T.RADIUS_SM,
            command=lambda: self._on_move(-1),
        )
        self.up_btn.pack(side="right")

        ctk.CTkLabel(row1, text="Style:", font=ctk.CTkFont(size=12)).pack(side="right", padx=(0, 5))
        self.style_var = ctk.StringVar(value="Subtitle")
        self.style_menu = ctk.CTkOptionMenu(
            row1, variable=self.style_var,
            values=list(TEXT_STYLES.keys()), width=110,
            command=self._on_style_change,
        )
        self.style_menu.pack(side="right", padx=(0, 8))

        # Row 2: Text input
        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=2)

        self.text_var = ctk.StringVar(value="")
        self.text_entry = ctk.CTkEntry(
            row2, textvariable=self.text_var,
            placeholder_text="Enter text...",
            font=ctk.CTkFont(size=13), height=32,
        )
        self.text_entry.pack(fill="x")

        # Row 3: Font, size, color, position
        row3 = ctk.CTkFrame(self, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=2)

        ctk.CTkLabel(row3, text="Font:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.font_var = ctk.StringVar(value="Arial")
        self.font_menu = ctk.CTkOptionMenu(
            row3, variable=self.font_var,
            values=self._get_fonts()[:30],  # Limit dropdown length
            width=130,
        )
        self.font_menu.pack(side="left", padx=(2, 8))

        ctk.CTkLabel(row3, text="Size:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.size_var = ctk.StringVar(value="24")
        self.size_entry = ctk.CTkEntry(
            row3, textvariable=self.size_var, width=50, height=28,
            font=ctk.CTkFont(size=12), justify="center",
        )
        self.size_entry.pack(side="left", padx=(2, 8))

        ctk.CTkLabel(row3, text="Color:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.color_var = ctk.StringVar(value="White")
        self.color_menu = ctk.CTkOptionMenu(
            row3, variable=self.color_var,
            values=list(TEXT_COLORS.keys()) + ["Custom…"], width=110,
            command=self._on_color_choice,
        )
        self.color_menu.pack(side="left", padx=(2, 8))

        ctk.CTkLabel(row3, text="Position:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.position_var = ctk.StringVar(value="Bottom Center")
        # Custom is selected automatically when the user drags the text on
        # the preview; picking any preset clears the custom override.
        self.position_menu = ctk.CTkOptionMenu(
            row3, variable=self.position_var,
            values=list(POSITION_MAP.keys()) + ["Custom (drag)"], width=150,
            command=self._on_position_choice,
        )
        self.position_menu.pack(side="left", padx=(2, 0))

        # Row 4: Background toggle
        row4 = ctk.CTkFrame(self, fg_color="transparent")
        row4.pack(fill="x", padx=10, pady=2)

        self.box_var = ctk.BooleanVar(value=True)
        self.box_cb = ctk.CTkCheckBox(
            row4, text="Background box (subtitle style)",
            variable=self.box_var,
            font=ctk.CTkFont(size=11),
        )
        self.box_cb.pack(side="left")

        # Row 5: Timing slider
        row5 = ctk.CTkFrame(self, fg_color="transparent")
        row5.pack(fill="x", padx=10, pady=(2, 8))

        ctk.CTkLabel(row5, text="Visible:", font=ctk.CTkFont(size=11)).pack(side="left")

        self.time_slider = RangeSlider(
            row5, from_=0, to=max(self.video_duration, 0.1),
            command=self._on_time_change,
        )
        self.time_slider.pack(side="left", fill="x", expand=True, padx=(5, 5))

        from videokidnapper.utils.time_format import seconds_to_hms
        self.time_label = ctk.CTkLabel(
            row5,
            text=f"0s - {seconds_to_hms(self.video_duration)}",
            font=ctk.CTkFont(family="Consolas", size=11), text_color="gray",
        )
        self.time_label.pack(side="right")

        # Apply default style
        self._on_style_change("Subtitle")

    def _get_fonts(self):
        if self._fonts is None:
            self._fonts = _get_system_fonts()
        return self._fonts

    def _on_style_change(self, style_name):
        style = TEXT_STYLES.get(style_name, {})
        if not style:
            return

        pos = style.get("position", "bottom_center")
        pos_display = {
            "bottom_center": "Bottom Center",
            "top_center": "Top Center",
            "center": "Center",
            "top_left": "Top Left",
            "top_right": "Top Right",
            "bottom_left": "Bottom Left",
            "bottom_right": "Bottom Right",
        }.get(pos, "Bottom Center")

        self.position_var.set(pos_display)
        self.size_var.set(str(style.get("fontsize", 24)))
        self.box_var.set(style.get("box", False))

        # Map fontcolor to color name
        fc = style.get("fontcolor", "white")
        if fc == "white" or fc == "white@0.5":
            self.color_var.set("White")
        elif fc == "black":
            self.color_var.set("Black")

    def _on_time_change(self, start, end):
        from videokidnapper.utils.time_format import seconds_to_hms
        self.time_label.configure(text=f"{seconds_to_hms(start)} - {seconds_to_hms(end)}")

    def _on_color_choice(self, value):
        if value == "Custom…":
            self.pick_custom_color()
            # Revert dropdown label; custom color is applied via get_layer_data.
            if self._custom_color:
                self.color_var.set(f"Custom {self._custom_color}")
            else:
                self.color_var.set("White")

    def _on_position_choice(self, value):
        # Picking any preset clears the drag-custom override. Selecting
        # "Custom (drag)" directly is a hint to drag — leave state alone.
        if value != "Custom (drag)":
            self._custom_position = None

    def set_custom_position(self, source_x, source_y):
        """Called from the VideoPlayer drag handler to persist a position."""
        self._custom_position = {"x": int(source_x), "y": int(source_y)}
        if self.position_var.get() != "Custom (drag)":
            self.position_var.set("Custom (drag)")

    def has_custom_position(self):
        return self._custom_position is not None

    def _on_remove(self):
        if self.on_remove:
            self.on_remove(self)

    def _on_duplicate(self):
        if self.on_duplicate:
            self.on_duplicate(self)

    def _on_move(self, delta):
        if self.on_move:
            self.on_move(self, delta)

    def pick_custom_color(self):
        from videokidnapper.ui.color_picker import ask_color
        current = self._custom_color or "#FFFFFF"
        new = ask_color(self, initial=current, title="Pick text color")
        if new:
            self._custom_color = new

    def update_duration(self, duration):
        self.video_duration = duration
        self.time_slider.set_range(0, max(duration, 0.1))

    def get_layer_data(self):
        start, end = self.time_slider.get_values()
        color_name = self.color_var.get()
        if color_name.startswith("Custom ") and self._custom_color:
            fontcolor = self._custom_color
        else:
            fontcolor = TEXT_COLORS.get(color_name, "white")

        # Custom-drag overrides every preset. We emit the position as the
        # raw "<x>:<y>" pair ffmpeg accepts as numeric coordinates; the
        # preview resolver recognises this form too.
        if self._custom_position:
            cx, cy = self._custom_position["x"], self._custom_position["y"]
            pos_expr = f"{cx}:{cy}"
        else:
            pos_name = self.position_var.get()
            pos_expr = POSITION_MAP.get(pos_name, "(w-tw)/2:h-th-20")

        try:
            fontsize = int(self.size_var.get())
        except ValueError:
            fontsize = 24

        return {
            "text": self.text_var.get(),
            "font": self.font_var.get(),
            "fontsize": fontsize,
            "fontcolor": fontcolor,
            "position": pos_expr,
            "box": self.box_var.get(),
            "start": start,
            "end": end,
        }

    def load_from_dict(self, data):
        """Populate this widget from a layer dict (used for duplicate/import)."""
        self.text_var.set(data.get("text", ""))
        self.font_var.set(data.get("font", "Arial"))
        self.size_var.set(str(data.get("fontsize", 24)))
        self.box_var.set(bool(data.get("box", True)))
        # Position: match a preset name, fall back to numeric custom, else default.
        pos_expr = data.get("position", "(w-tw)/2:h-th-20")
        friendly = next(
            (k for k, v in POSITION_MAP.items() if v == pos_expr),
            None,
        )
        if friendly:
            self._custom_position = None
            self.position_var.set(friendly)
        else:
            # Try numeric "<x>:<y>" form.
            try:
                parts = pos_expr.split(":", 1)
                cx, cy = int(float(parts[0])), int(float(parts[1]))
                self._custom_position = {"x": cx, "y": cy}
                self.position_var.set("Custom (drag)")
            except (ValueError, IndexError):
                self._custom_position = None
                self.position_var.set("Bottom Center")
        # Color: accept named or custom hex.
        color = data.get("fontcolor", "white")
        if isinstance(color, str) and color.startswith("#"):
            self._custom_color = color
            self.color_var.set(f"Custom {color}")
        else:
            matched = next(
                (k for k, v in TEXT_COLORS.items() if v == color),
                "White",
            )
            self.color_var.set(matched)
        start = float(data.get("start", 0))
        end = float(data.get("end", self.video_duration))
        self.time_slider.set_values(start, end)


class TextLayersPanel(ctk.CTkFrame):
    """Collapsible panel containing multiple text layers."""

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
        self.layers = []
        self.video_duration = 0
        self._expanded = False
        self._on_change = on_change

        self._build_ui()

    def _notify_change(self):
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass

    def _build_ui(self):
        # Toggle header
        self.toggle_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.toggle_frame.pack(fill="x")

        self.toggle_btn = ctk.CTkButton(
            self.toggle_frame,
            text=f"  {self._CHEVRON_CLOSED}   Text Layers  ·  0",
            font=T.font(T.SIZE_LG, "bold"),
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT,
            corner_radius=T.RADIUS_MD,
            height=40, anchor="w",
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", padx=4, pady=4)

        # Content area (hidden by default)
        self.content = ctk.CTkFrame(self, fg_color="transparent")

        from videokidnapper.ui.theme import button as _btn
        self.add_btn = _btn(
            self.content, "  +  Add Text Layer",
            variant="secondary", width=180, height=30,
            font=T.font(T.SIZE_MD, "bold"),
        )
        self.add_btn.configure(command=self._add_layer)
        self.add_btn.pack(anchor="w", padx=12, pady=(6, 6))

        # Scrollable container for layers
        self.layers_container = ctk.CTkScrollableFrame(
            self.content,
            fg_color="transparent",
            height=220,
            scrollbar_button_color=T.BG_HOVER,
            scrollbar_button_hover_color=T.BG_ACTIVE,
        )
        self.layers_container.pack(fill="x", padx=12, pady=(0, 10))

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.content.pack(fill="x", after=self.toggle_frame)
        else:
            self.content.pack_forget()
        self._update_header()

    def _add_layer(self, preset_data=None):
        layer = TextLayerWidget(
            self.layers_container,
            layer_index=len(self.layers),
            video_duration=self.video_duration,
            on_remove=self._remove_layer,
            on_duplicate=self._duplicate_layer,
            on_move=self._move_layer,
        )
        layer.pack(fill="x", pady=(0, 5))
        self.layers.append(layer)
        self._wire_layer_change(layer)
        if preset_data:
            layer.load_from_dict(preset_data)
        self._update_header()
        self._notify_change()

        # Auto-expand when first layer is added
        if not self._expanded:
            self._toggle()
        return layer

    def _duplicate_layer(self, layer_widget):
        data = layer_widget.get_layer_data()
        self._add_layer(preset_data=data)

    def _move_layer(self, layer_widget, delta):
        if layer_widget not in self.layers:
            return
        idx = self.layers.index(layer_widget)
        new_idx = max(0, min(len(self.layers) - 1, idx + delta))
        if new_idx == idx:
            return
        self.layers.pop(idx)
        self.layers.insert(new_idx, layer_widget)
        # Re-pack to match new order.
        for lyr in self.layers:
            lyr.pack_forget()
        for i, lyr in enumerate(self.layers):
            lyr.layer_index = i
            lyr.pack(fill="x", pady=(0, 5))
        self._notify_change()

    def import_srt_layers(self, layer_dicts):
        """Bulk-add parsed SRT entries; each becomes its own layer widget."""
        for data in layer_dicts:
            self._add_layer(preset_data=data)

    def _wire_layer_change(self, layer):
        """Call `_notify_change` whenever the user edits any field of a layer."""
        def fire(*_):
            self._notify_change()
        layer.text_var.trace_add("write", fire)
        layer.font_var.trace_add("write", fire)
        layer.size_var.trace_add("write", fire)
        layer.color_var.trace_add("write", fire)
        layer.position_var.trace_add("write", fire)
        layer.style_var.trace_add("write", fire)
        layer.box_var.trace_add("write", fire)
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
            # Re-index remaining layers
            for i, layer in enumerate(self.layers):
                layer.layer_index = i
            self._update_header()
            self._notify_change()

    def _update_header(self):
        chev = self._CHEVRON_OPEN if self._expanded else self._CHEVRON_CLOSED
        self.toggle_btn.configure(
            text=f"  {chev}   Text Layers  ·  {len(self.layers)}",
        )

    def set_duration(self, duration):
        self.video_duration = duration
        for layer in self.layers:
            layer.update_duration(duration)

    def get_all_layers(self, include_empty=False):
        result = []
        for layer in self.layers:
            data = layer.get_layer_data()
            if include_empty or data["text"].strip():
                result.append(data)
        return result

    def set_layer_position(self, index, source_x, source_y):
        """Drag callback entry point — forwarded from VideoPlayer."""
        if 0 <= index < len(self.layers):
            self.layers[index].set_custom_position(source_x, source_y)
            self._notify_change()

    def clear_layers(self):
        for layer in self.layers:
            layer.destroy()
        self.layers.clear()
        self._update_header()
