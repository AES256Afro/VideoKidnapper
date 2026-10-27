# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import os
import sys
import tkinter.font as tkfont
from contextlib import contextmanager

import customtkinter as ctk

from videokidnapper.config import TEXT_STYLES, POSITION_MAP, TEXT_COLORS
from videokidnapper.ui import theme as T
from videokidnapper.utils import font_index
from videokidnapper.utils.coerce import coerce_float, coerce_int


_PREFERRED_FONTS = ["Arial", "Segoe UI", "Helvetica", "Verdana", "Times New Roman",
                    "Courier New", "Georgia", "Impact", "Comic Sans MS", "Trebuchet MS"]


def _get_system_fonts():
    """Font families for the caption font menu, common ones first.

    Once the font index is built (utils.font_index) these are the
    installed families that really draw; until then, Tk's list.
    """
    try:
        start_font_index()
        families = font_index.families()
        if families is None:
            families = sorted(set(tkfont.families()))
        top = [f for f in _PREFERRED_FONTS if f in families]
        rest = [f for f in families if f not in top and not f.startswith("@")]
        return top + rest
    except Exception:
        return ["Arial", "Segoe UI", "Helvetica", "Verdana", "Times New Roman"]


def start_font_index():
    """Start reading the installed fonts' names, in the background."""
    font_index.start(_font_dirs())


# Style-variant filename suffixes, tried in order against the regular
# face's stem. Windows font files follow loose conventions: arialbd.ttf /
# ariali.ttf / arialbi.ttf, georgiab.ttf / georgiai.ttf / georgiaz.ttf,
# trebucbd.ttf / trebucit.ttf / trebucbi.ttf, calibrib / calibrii /
# calibriz... The candidate lists cover all of those.
_VARIANT_SUFFIXES = {
    (True, False): ("bd", "b"),           # bold
    (False, True): ("i", "it"),           # italic
    (True, True):  ("bi", "z", "bdit"),   # bold italic
}


def _variant_font_path(regular_path, bold, italic):
    """Resolve the bold/italic variant file next to ``regular_path``.

    Returns the variant path when a matching file exists, else the
    regular path — a missing Bold face silently renders regular rather
    than failing the export. Pure path math + ``os.path.exists``, so
    it's unit-testable with a temp fonts dir.
    """
    if not (bold or italic):
        return regular_path
    base, ext = os.path.splitext(regular_path)
    for suffix in _VARIANT_SUFFIXES[(bool(bold), bool(italic))]:
        candidate = base + suffix + ext
        if os.path.exists(candidate):
            return candidate
    # Bold italic with no dedicated file: fall back to plain bold, then
    # plain italic, before giving up — closer to the asked-for look.
    if bold and italic:
        for key in ((True, False), (False, True)):
            for suffix in _VARIANT_SUFFIXES[key]:
                candidate = base + suffix + ext
                if os.path.exists(candidate):
                    return candidate
    return regular_path


# Where each platform keeps its fonts, most specific (user) first.
#
# This used to be Windows-only: a hardcoded C:\\Windows\\Fonts and
# Windows filenames. On macOS and Linux nothing ever matched, so every
# lookup returned a path that did not exist. The preview then fell
# through to PIL's `load_default()` bitmap face and drew EVERY caption
# at ~8 px tall no matter what size was chosen — on a captioning app,
# the font-size control did nothing you could see.
def _font_dirs():
    if sys.platform == "win32":
        dirs = [os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")]
        # Fonts installed "for me only" (the default when you double-click
        # a font file) live here, not in the system folder.
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
        return dirs
    if sys.platform == "darwin":
        return [
            os.path.expanduser("~/Library/Fonts"),
            "/Library/Fonts",
            # Arial, Impact, Georgia and friends live in Supplemental on
            # modern macOS; the base dir holds the system faces.
            "/System/Library/Fonts/Supplemental",
            "/System/Library/Fonts",
        ]
    return [
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
        "/usr/local/share/fonts",
        "/usr/share/fonts",
    ]


# One logical font name to the filenames it goes by, across platforms.
# Windows spellings first to keep that platform's resolution identical,
# then macOS, then the metric-compatible substitutes Linux ships.
_FONT_FILES = {
    "arial":         ("arial.ttf", "Arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"),
    "arialblack":    ("ariblk.ttf", "Arial Black.ttf", "DejaVuSans-Bold.ttf"),
    "segoeui":       ("segoeui.ttf", "SFNSDisplay.ttf", "DejaVuSans.ttf"),
    "helvetica":     ("arial.ttf", "Helvetica.ttc", "Helvetica.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"),
    "verdana":       ("verdana.ttf", "Verdana.ttf", "DejaVuSans.ttf"),
    "timesnewroman": ("times.ttf", "Times New Roman.ttf", "LiberationSerif-Regular.ttf", "DejaVuSerif.ttf"),
    "couriernew":    ("cour.ttf", "Courier New.ttf", "Menlo.ttc", "LiberationMono-Regular.ttf", "DejaVuSansMono.ttf"),
    "georgia":       ("georgia.ttf", "Georgia.ttf", "DejaVuSerif.ttf"),
    "impact":        ("impact.ttf", "Impact.ttf", "DejaVuSans-Bold.ttf"),
    "comicsansms":   ("comic.ttf", "Comic Sans MS.ttf", "DejaVuSans.ttf"),
    "trebuchetms":   ("trebuc.ttf", "Trebuchet MS.ttf", "DejaVuSans.ttf"),
    "tahoma":        ("tahoma.ttf", "Tahoma.ttf", "DejaVuSans.ttf"),
    "calibri":       ("calibri.ttf", "Calibri.ttf", "DejaVuSans.ttf"),
    "cambria":       ("cambria.ttc", "Cambria.ttc", "DejaVuSerif.ttf"),
    # Keep monospace monospace: without a mono option here these fell
    # through to the sans last-resort, which is a visibly wrong answer.
    "consolas":      ("consola.ttf", "Consolas.ttf", "Menlo.ttc", "Courier New.ttf", "LiberationMono-Regular.ttf", "DejaVuSansMono.ttf"),
    "lucidaconsole": ("lucon.ttf", "Lucida Console.ttf", "Menlo.ttc", "Courier New.ttf", "DejaVuSansMono.ttf"),
}

#: Anything present here beats returning a path that does not exist.
_LAST_RESORT = (
    "arial.ttf", "Arial.ttf", "Helvetica.ttc",
    "LiberationSans-Regular.ttf", "DejaVuSans.ttf",
)


def _first_existing(filenames, dirs):
    """First of ``filenames`` that exists in any of ``dirs``.

    Linux nests fonts (``/usr/share/fonts/truetype/dejavu/…``), so each
    directory is walked when a direct hit fails. The walk is bounded to
    the listed roots and stops at the first match.
    """
    for directory in dirs:
        for name in filenames:
            candidate = os.path.join(directory, name)
            if os.path.exists(candidate):
                return candidate
    wanted = {n.lower() for n in filenames}
    for directory in dirs:
        if not os.path.isdir(directory):
            continue
        for root, _subdirs, files in os.walk(directory):
            for filename in files:
                if filename.lower() in wanted:
                    return os.path.join(root, filename)
    return None


def _find_font_path(font_name, bold=False, italic=False, fonts_dir=None):
    """Resolve a font name to a file on disk.

    ``fonts_dir`` overrides the platform search path — the tests use it
    to exercise resolution against a temp directory.
    """
    if fonts_dir is None:
        # The installed font that really has this family name, when the
        # index knows it; the guesses below cover the rest.
        indexed = font_index.lookup(font_name, bold=bold, italic=italic)
        if indexed:
            return indexed
    dirs = [fonts_dir] if fonts_dir is not None else _font_dirs()
    name_lower = font_name.lower().replace(" ", "")

    candidates = list(_FONT_FILES.get(name_lower, ()))
    # Direct match on the name as typed, in the usual extensions.
    bare = font_name.replace(" ", "")
    for ext in (".ttf", ".otf", ".ttc"):
        candidates += [bare + ext, bare.lower() + ext, font_name + ext]

    found = _first_existing(candidates, dirs)
    if found:
        return _variant_font_path(found, bold, italic)

    # Nothing matched by name — take any usable face over a path that
    # does not exist, which is what made the preview render a bitmap
    # stand-in at a fixed size.
    fallback = _first_existing(_LAST_RESORT, dirs)
    if fallback:
        return _variant_font_path(fallback, bold, italic)

    # Truly nothing (a locked-down box, or a temp dir in a test): keep
    # the historical return shape so callers behave as they always have.
    return _variant_font_path(os.path.join(dirs[0], "arial.ttf"), bold, italic)


class _TimeRange:
    """A caption's visible window, in seconds of the source video.

    Holds what the hidden ``RangeSlider`` of each caption row used to:
    the same ``from_``/``to`` bounds, the same clamping in
    :meth:`set_values`, and a ``command`` the panel wraps, so the
    timeline, the Inspector and undo use it unchanged.
    """

    def __init__(self, from_=0, to=100, command=None):
        self.from_ = from_
        self.to = to
        self.command = command
        self._start_val = from_
        self._end_val = to

    def set_range(self, from_, to):
        self.from_ = from_
        self.to = to
        self._start_val = from_
        self._end_val = to

    def set_values(self, start, end):
        self._start_val = max(self.from_, min(start, self.to))
        self._end_val = max(self.from_, min(end, self.to))

    def get_values(self):
        return self._start_val, self._end_val


class TextLayer:
    """One caption: its settings held in Tk variables, with no widgets.

    The Studio Inspector edits the selected caption by binding its own
    controls to these variables; the preview, timeline and export read
    :meth:`get_layer_data`. Each caption used to build a full row of
    controls that was never shown, about thirty widgets with four
    drop-down menus. A 300-line subtitle file took minutes to import
    that way, and then failed when Windows ran out of menus. Tk
    variables cost microseconds.
    """

    def __init__(self, master, layer_index, video_duration,
                 on_remove=None, on_duplicate=None, on_move=None):
        # ``master`` owns the Tk variables (and parents any dialog).
        self.master = master
        self.layer_index = layer_index
        self.video_duration = video_duration
        self.on_remove = on_remove
        self.on_duplicate = on_duplicate
        self.on_move = on_move
        self._fonts = None
        self._custom_color = None  # "#RRGGBB" when the colour isn't a preset
        # When the user drags the layer on the preview we store the source-
        # pixel coords here. Selecting a preset from the dropdown clears it.
        self._custom_position = None  # {"x": int, "y": int} or None

        self._build_vars()

    def _build_vars(self):
        def string(value):
            return ctk.StringVar(self.master, value=value)

        def flag(value):
            return ctk.BooleanVar(self.master, value=value)

        self.style_var = string("Subtitle")
        # The caption text. Embedded newlines flow through to drawtext
        # (and the PIL preview) as real line breaks.
        self.text_var = string("")
        self.font_var = string("Arial")
        self.size_var = string("24")
        # Bold / italic resolve to font-variant files at export and
        # preview time (arialbd.ttf, ariali.ttf, ...).
        self.bold_var = flag(False)
        self.italic_var = flag(False)
        self.color_var = string("White")
        # "Custom (drag)" is selected automatically when the user drags
        # the text on the preview; picking any preset clears the override.
        self.position_var = string("Bottom Center")
        self.box_var = flag(True)
        self.outline_var = flag(False)
        self.shadow_var = flag(False)
        # Outline / shadow widths and offsets default to the social-caption
        # standard (2px). load_from_dict preserves imported values in the
        # private fields so a round-trip doesn't normalise them away.
        self._borderw = 2
        self._shadow_offset = (2, 2)
        self.time_slider = _TimeRange(
            0, max(self.video_duration, 0.1), command=self._on_time_change)
        # Motion path (meme-style tracked caption). While armed, dragging
        # the text on the preview records a keyframe at the current
        # playhead time instead of moving the whole layer; the caption
        # then follows the interpolated path in preview AND export.
        self._keyframes = []
        self.motion_var = flag(False)

    def destroy(self):
        """The panel dropped this caption: stop calling back into it."""
        self._change_cb = None
        self._autotrack_cb = None
        self.time_slider.command = None

    def _request_autotrack(self):
        cb = getattr(self, "_autotrack_cb", None)
        if callable(cb):
            cb(self.layer_index)

    def set_keyframes(self, keyframes):
        """Replace the whole motion path (auto-tracking result)."""
        from videokidnapper.utils.keyframes import normalize_keyframes
        self._keyframes = normalize_keyframes(keyframes)
        if self._keyframes:
            self.motion_var.set(True)
        self._fire_change()

    # ------------------------------------------------------------------
    # Motion path (keyframed position)
    # ------------------------------------------------------------------
    def _on_motion_toggled(self):
        self._fire_change()

    def _clear_keyframes(self):
        self._keyframes = []
        self._fire_change()

    def add_keyframe(self, t, x, y):
        """Record (or replace, if within 10 ms) a keyframe at time ``t``."""
        from videokidnapper.utils.keyframes import normalize_keyframes
        self._keyframes.append(
            {"t": float(t), "x": float(x), "y": float(y)})
        self._keyframes = normalize_keyframes(self._keyframes)
        self._fire_change()

    def is_motion_armed(self):
        return bool(self.motion_var.get())

    def _fire_change(self):
        # The panel wires _notify_change onto layers after construction;
        # guard for the brief window before that happens.
        cb = getattr(self, "_change_cb", None)
        if callable(cb):
            cb()

    def _get_fonts(self):
        if self._fonts is None:
            self._fonts = _get_system_fonts()
        return self._fonts

    def _set_text(self, value):
        value = value or ""
        if value != self.text_var.get():
            self.text_var.set(value)

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
        self.outline_var.set(int(style.get("borderw", 0) or 0) > 0)
        if int(style.get("borderw", 0) or 0) > 0:
            self._borderw = int(style["borderw"])
        self.shadow_var.set(
            bool(style.get("shadowx") or style.get("shadowy")))

        # Map fontcolor to color name
        fc = style.get("fontcolor", "white")
        if fc == "white" or fc == "white@0.5":
            self.color_var.set("White")
        elif fc == "black":
            self.color_var.set("Black")

    def _on_time_change(self, start, end):
        """Hook for a new visible window; the panel wraps it to notify."""

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

    def color_value(self):
        """The colour as the layer data stores it: a preset's value
        (``white``, ``#FF0000``...) or a custom ``#RRGGBB``."""
        color_name = self.color_var.get()
        if color_name.startswith("Custom ") and self._custom_color:
            return self._custom_color
        return TEXT_COLORS.get(color_name, "white")

    def set_color(self, value):
        """Use the colour picked in the Inspector's palette.

        A preset's colour selects that preset, so it's stored exactly as
        if it had been picked by name; any other colour is kept as a
        custom ``#RRGGBB``. Returns False, changing nothing, when
        ``value`` isn't a colour.
        """
        from videokidnapper.ui.studio.color_palette import normalize_hex, preset_name

        hex_value = normalize_hex(value)
        if hex_value is None:
            return False
        name = preset_name(hex_value)
        if name is None:
            self._custom_color = hex_value
            name = f"Custom {hex_value}"
        # Setting the same value would still fire the change trace and
        # record an undo step for nothing.
        if self.color_var.get() != name:
            self.color_var.set(name)
        return True

    def update_duration(self, duration):
        self.video_duration = duration
        self.time_slider.set_range(0, max(duration, 0.1))

    def get_layer_data(self):
        start, end = self.time_slider.get_values()
        fontcolor = self.color_value()

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

        sx, sy = self._shadow_offset
        return {
            "text": self.text_var.get(),
            "font": self.font_var.get(),
            "fontsize": fontsize,
            "fontcolor": fontcolor,
            "position": pos_expr,
            "box": self.box_var.get(),
            "bold": bool(self.bold_var.get()),
            "italic": bool(self.italic_var.get()),
            "borderw": self._borderw if self.outline_var.get() else 0,
            "bordercolor": "black",
            "shadowx": sx if self.shadow_var.get() else 0,
            "shadowy": sy if self.shadow_var.get() else 0,
            "shadowcolor": "black@0.7",
            "start": start,
            "end": end,
            # Motion path: present only when the user recorded one, so
            # untouched layers keep byte-identical filter strings.
            **({"keyframes": [dict(kf) for kf in self._keyframes]}
               if self._keyframes else {}),
        }

    def load_from_dict(self, data):
        """Populate this caption from a layer dict (duplicate, import, undo).

        Project files are shared, so every value may be the wrong type or
        missing; odd values fall back to the defaults (see utils.coerce)
        rather than failing the whole project.
        """
        text = data.get("text", "")
        self._set_text(text if isinstance(text, str) else
                       "" if text is None else str(text))
        font = data.get("font")
        self.font_var.set(font if isinstance(font, str) and font else "Arial")
        fontsize = coerce_int(data.get("fontsize", 24), 24)
        self.size_var.set(str(fontsize if fontsize > 0 else 24))
        self.box_var.set(bool(data.get("box", True)))
        self.bold_var.set(bool(data.get("bold", False)))
        self.italic_var.set(bool(data.get("italic", False)))
        # Outline / shadow: a positive imported width / offset is preserved
        # in the private fields so duplicate and undo round-trips don't
        # normalise it back to the 2px default.
        borderw = coerce_int(data.get("borderw", 0) or 0, 0)
        self.outline_var.set(borderw > 0)
        if borderw > 0:
            self._borderw = borderw
        sx = coerce_int(data.get("shadowx", 0) or 0, 0)
        sy = coerce_int(data.get("shadowy", 0) or 0, 0)
        self.shadow_var.set(bool(sx or sy))
        if sx or sy:
            self._shadow_offset = (sx, sy)
        # Position: match a preset name, fall back to numeric custom, else default.
        pos_expr = data.get("position", "(w-tw)/2:h-th-20")
        if not isinstance(pos_expr, str):
            pos_expr = "(w-tw)/2:h-th-20"
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
        start = coerce_float(data.get("start", 0), 0.0)
        end = coerce_float(data.get("end", self.video_duration), self.video_duration)
        self.time_slider.set_values(start, end)
        # Motion path round-trips through undo snapshots / duplication.
        from videokidnapper.utils.keyframes import normalize_keyframes
        self._keyframes = normalize_keyframes(data.get("keyframes") or [])


# The old name, for anything that still imports it.
TextLayerWidget = TextLayer


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
        # batch_changes() nesting depth, and whether a change arrived
        # while it was held.
        self._batch_depth = 0
        self._batch_changed = False

        self._build_ui()

    def _notify_change(self):
        if self._batch_depth:
            self._batch_changed = True
            return
        if self._on_change:
            try:
                self._on_change()
            except Exception:
                pass

    @contextmanager
    def batch_changes(self):
        """Hold change notifications; send one at the end if anything changed.

        Loading a caption sets a dozen variables, each of which notifies,
        and every notification redraws the timeline from every caption.
        Without this, importing N subtitle lines did that about 12 * N
        times over a growing list.
        """
        self._batch_depth += 1
        try:
            yield
        finally:
            self._batch_depth -= 1
            if not self._batch_depth and self._batch_changed:
                self._batch_changed = False
                self._notify_change()

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

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.content.pack(fill="x", after=self.toggle_frame)
        else:
            self.content.pack_forget()
        self._update_header()

    def _add_layer(self, preset_data=None):
        with self.batch_changes():
            layer = TextLayer(
                self,
                layer_index=len(self.layers),
                video_duration=self.video_duration,
                on_remove=self._remove_layer,
                on_duplicate=self._duplicate_layer,
                on_move=self._move_layer,
            )
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
        for i, lyr in enumerate(self.layers):
            lyr.layer_index = i
        self._notify_change()

    def import_srt_layers(self, layer_dicts):
        """Bulk-add parsed SRT entries as captions, with one notification.

        Returns the number added.
        """
        added = 0
        with self.batch_changes():
            for data in layer_dicts:
                self._add_layer(preset_data=data)
                added += 1
        return added

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
        layer.bold_var.trace_add("write", fire)
        layer.italic_var.trace_add("write", fire)
        layer.outline_var.trace_add("write", fire)
        layer.shadow_var.trace_add("write", fire)
        original_time_cb = layer._on_time_change
        def time_cb(start, end):
            original_time_cb(start, end)
            self._notify_change()
        layer._on_time_change = time_cb
        layer.time_slider.command = time_cb
        # Motion-path edits (arm/record/clear) refresh the preview too.
        layer._change_cb = self._notify_change
        layer._autotrack_cb = getattr(self, "_autotrack_handler", None)

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

    def set_autotrack_handler(self, cb):
        """The studio tab owns tracking (player + video + threads); it
        registers here and every layer's ⚡ button forwards to it."""
        self._autotrack_handler = cb
        for layer in self.layers:
            layer._autotrack_cb = cb

    def set_layer_keyframes(self, index, keyframes):
        if 0 <= index < len(self.layers):
            self.layers[index].set_keyframes(keyframes)
            self._notify_change()

    def maybe_record_keyframe(self, index, t, source_x, source_y):
        """If the dragged layer is motion-armed, record a keyframe at
        time ``t`` and return True; otherwise return False so the caller
        falls back to a static position move."""
        if 0 <= index < len(self.layers) and self.layers[index].is_motion_armed():
            self.layers[index].add_keyframe(t, source_x, source_y)
            return True
        return False

    def clear_layers(self):
        for layer in self.layers:
            layer.destroy()
        self.layers.clear()
        self._update_header()
