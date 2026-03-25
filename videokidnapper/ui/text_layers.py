import os
import tkinter.font as tkfont

import customtkinter as ctk

from videokidnapper.config import TEXT_STYLES, POSITION_MAP, TEXT_COLORS
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

    def __init__(self, master, layer_index, video_duration, on_remove=None, **kwargs):
        super().__init__(master, corner_radius=8, border_width=1, border_color="#444", **kwargs)
        self.layer_index = layer_index
        self.video_duration = video_duration
        self.on_remove = on_remove
        self._fonts = None

        self._build_ui()

    def _build_ui(self):
        # Row 1: Header + style preset + remove button
        row1 = ctk.CTkFrame(self, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 4))

        ctk.CTkLabel(
            row1, text=f"Layer {self.layer_index + 1}",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        self.remove_btn = ctk.CTkButton(
            row1, text="X", width=28, height=28,
            fg_color="#e84a1a", hover_color="#c43e15",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_remove,
        )
        self.remove_btn.pack(side="right")

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
            values=list(TEXT_COLORS.keys()), width=90,
        )
        self.color_menu.pack(side="left", padx=(2, 8))

        ctk.CTkLabel(row3, text="Position:", font=ctk.CTkFont(size=11)).pack(side="left")
        self.position_var = ctk.StringVar(value="Bottom Center")
        self.position_menu = ctk.CTkOptionMenu(
            row3, variable=self.position_var,
            values=list(POSITION_MAP.keys()), width=130,
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

    def _on_remove(self):
        if self.on_remove:
            self.on_remove(self)

    def update_duration(self, duration):
        self.video_duration = duration
        self.time_slider.set_range(0, max(duration, 0.1))

    def get_layer_data(self):
        start, end = self.time_slider.get_values()
        color_name = self.color_var.get()
        fontcolor = TEXT_COLORS.get(color_name, "white")
        position = self.position_var.get()
        pos_expr = POSITION_MAP.get(position, "(w-tw)/2:h-th-20")

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


class TextLayersPanel(ctk.CTkFrame):
    """Collapsible panel containing multiple text layers."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.layers = []
        self.video_duration = 0
        self._expanded = False

        self._build_ui()

    def _build_ui(self):
        # Toggle header
        self.toggle_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.toggle_frame.pack(fill="x")

        self.toggle_btn = ctk.CTkButton(
            self.toggle_frame,
            text="+ Text Layers (0)",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#333", hover_color="#444",
            height=32, anchor="w",
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x")

        # Content area (hidden by default)
        self.content = ctk.CTkFrame(self, fg_color="transparent")

        # Add layer button
        self.add_btn = ctk.CTkButton(
            self.content, text="+ Add Text Layer", width=160, height=30,
            font=ctk.CTkFont(size=12),
            fg_color="#1a73e8", hover_color="#1557b0",
            command=self._add_layer,
        )
        self.add_btn.pack(anchor="w", pady=(5, 5))

        # Scrollable container for layers
        self.layers_container = ctk.CTkScrollableFrame(
            self.content, fg_color="transparent",
            height=200,
        )
        self.layers_container.pack(fill="x", pady=(0, 5))

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.content.pack(fill="x", after=self.toggle_frame)
            prefix = "- "
        else:
            self.content.pack_forget()
            prefix = "+ "
        self.toggle_btn.configure(text=f"{prefix}Text Layers ({len(self.layers)})")

    def _add_layer(self):
        layer = TextLayerWidget(
            self.layers_container,
            layer_index=len(self.layers),
            video_duration=self.video_duration,
            on_remove=self._remove_layer,
        )
        layer.pack(fill="x", pady=(0, 5))
        self.layers.append(layer)
        self._update_header()

        # Auto-expand when first layer is added
        if not self._expanded:
            self._toggle()

    def _remove_layer(self, layer_widget):
        if layer_widget in self.layers:
            self.layers.remove(layer_widget)
            layer_widget.destroy()
            # Re-index remaining layers
            for i, layer in enumerate(self.layers):
                layer.layer_index = i
            self._update_header()

    def _update_header(self):
        prefix = "- " if self._expanded else "+ "
        self.toggle_btn.configure(text=f"{prefix}Text Layers ({len(self.layers)})")

    def set_duration(self, duration):
        self.video_duration = duration
        for layer in self.layers:
            layer.update_duration(duration)

    def get_all_layers(self):
        result = []
        for layer in self.layers:
            data = layer.get_layer_data()
            if data["text"].strip():
                result.append(data)
        return result

    def clear_layers(self):
        for layer in self.layers:
            layer.destroy()
        self.layers.clear()
        self._update_header()
