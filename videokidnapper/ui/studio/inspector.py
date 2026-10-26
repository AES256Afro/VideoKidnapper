# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Right-hand Inspector for the Studio Edit workspace.

Four tabs, each editing one thing at a time:

- **Clip** — selection in/out, speed, rotate, frame shape, crop, mute.
- **Text** — the selected caption. Controls re-bind to that caption's
  Tk variables, so all the existing caption logic (style presets,
  colors, drag positions, motion paths) keeps working unchanged. It also
  holds "Captions from speech" (Whisper), which used to be a window.
- **Image** — the selected image overlay, same approach.
- **Color** — the color grade, which the preview now shows live.

The data model is ``editor.text_layers.layers`` (captions: plain
``TextLayer`` objects holding Tk variables, no widgets) and
``editor.image_layers.layers`` (overlay rows that are never packed).
"""

import os

import customtkinter as ctk

from videokidnapper.config import POSITION_MAP, TEXT_STYLES
from videokidnapper.core.whisper_captions import MODEL_SIZES
from videokidnapper.ui import theme as T
from videokidnapper.ui.editor_options import (
    ASPECT_CHOICES, ASPECT_FILL_CHOICES, FADE_CHOICES, ROTATE_CHOICES,
)
from videokidnapper.ui.image_layers import POSITION_ANCHORS
from videokidnapper.ui.studio import controls as C
from videokidnapper.ui.studio.color_palette import ColorPalette
from videokidnapper.ui.studio.icons import icon_button
from videokidnapper.ui.theme import button
from videokidnapper.utils import settings
from videokidnapper.utils.time_format import hms_to_seconds, seconds_to_hms

INSPECTOR_TABS = (("clip", "Clip"), ("text", "Text"), ("image", "Image"), ("color", "Color"))
SPEED_SEGMENTS = ["0.25x", "0.5x", "1x", "1.5x", "2x", "4x"]
_PAD = 14
DEFAULT_WHISPER_MODEL = "base"
# One line under the model menu, so the choice is an informed one.
WHISPER_MODEL_NOTES = {
    "tiny": "Fastest and roughest.",
    "base": "Quick, and fine for clear speech.",
    "small": "More accurate, about three times slower.",
    "medium": "Very accurate, but slow.",
    "large": "Most accurate, and slowest.",
}


def _group(parent, title):
    """A titled block of controls inside an inspector page."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    frame.pack(fill="x", padx=_PAD, pady=(10, 0))
    C.section_label(frame, title).pack(fill="x", pady=(0, 4))
    return frame


class _Pages(dict):
    """The Inspector's pages, each built the first time it is asked for.

    ``pages["text"]`` builds the page if needed. ``pages.get("text")``
    does not, and returns None until something has asked for it, which
    is what callers that only want to update an open page should use.
    ``"text" in pages`` is true for every page there can be.
    """

    def __init__(self, factories, eager=()):
        super().__init__()
        self._factories = dict(factories)
        for key in eager:
            self[key]

    def __missing__(self, key):
        factory = self._factories.get(key)
        if factory is None:
            raise KeyError(key)
        page = self[key] = factory()
        return page

    def __contains__(self, key):
        return key in self._factories

    def built(self, key):
        return dict.__contains__(self, key)


class Inspector(ctk.CTkFrame):
    def __init__(self, master, editor, **kwargs):
        super().__init__(master, fg_color=T.BG_SURFACE, corner_radius=0, **kwargs)
        self.editor = editor
        self.tabs = C.TabStrip(self, INSPECTOR_TABS, command=self.show)
        self.tabs.pack(fill="x")
        C.divider(self).pack(fill="x")
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        # Clip shows first, and Color is small. Text and Image were about
        # a fifth of the startup time and wait for their first use.
        self.pages = _Pages({
            "clip": lambda: ClipPage(body, editor),
            "text": lambda: TextPage(body, editor),
            "image": lambda: ImagePage(body, editor),
            "color": lambda: ColorPage(body, editor),
        }, eager=("clip", "color"))
        self.current = None
        self.show("clip")

    def show(self, key):
        if key not in self.pages:
            return
        if self.current == key:
            return
        if self.current:
            self.pages[self.current].pack_forget()
        self.current = key
        self.tabs.select(key)
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()


# ---------------------------------------------------------------------------
# Clip
# ---------------------------------------------------------------------------

class ClipPage(ctk.CTkScrollableFrame):
    def __init__(self, master, editor):
        super().__init__(master, fg_color="transparent",
                         scrollbar_button_color=T.BG_HOVER,
                         scrollbar_button_hover_color=T.BG_ACTIVE)
        self.editor = editor
        opts = editor.options

        sel = _group(self, "Trim: the part to keep")
        row = ctk.CTkFrame(sel, fg_color="transparent")
        row.pack(fill="x")
        editor.start_entry = C.TimeField(row, "Start", command=editor._on_start_entry,
                                         width=104, inline=True)
        editor.start_entry.pack(side="left", padx=(0, 8))
        editor.end_entry = C.TimeField(row, "End", command=editor._on_end_entry,
                                       width=104, inline=True)
        editor.end_entry.pack(side="left")
        row2 = ctk.CTkFrame(sel, fg_color="transparent")
        row2.pack(fill="x", pady=(8, 0))
        editor.duration_label = ctk.CTkLabel(
            row2, text="Length  —", font=T.font(T.SIZE_SM, mono=True),
            text_color=T.TEXT_MUTED,
        )
        editor.duration_label.pack(side="left")
        button(row2, "+ Save as range", variant="secondary", height=28,
               font=T.font(T.SIZE_SM, "bold"),
               command=editor._queue_range).pack(side="right")

        speed = _group(self, "Speed")
        C.segmented(speed, SPEED_SEGMENTS, variable=opts.speed_var).pack(fill="x")

        rotate = _group(self, "Rotate")
        C.segmented(rotate, ROTATE_CHOICES, variable=opts.rotate_var).pack(fill="x")

        frame = _group(self, "Frame shape")
        C.segmented(frame, ASPECT_CHOICES, variable=opts.aspect_var).pack(fill="x")
        fill_row = ctk.CTkFrame(frame, fg_color="transparent")
        fill_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(fill_row, text="Fill with", font=T.font(T.SIZE_SM),
                     text_color=T.TEXT_MUTED, width=64, anchor="w").pack(side="left")
        C.segmented(fill_row, [label for label, _k in ASPECT_FILL_CHOICES],
                    variable=opts.aspect_fill_var).pack(side="left", fill="x", expand=True)
        crop_row = ctk.CTkFrame(frame, fg_color="transparent")
        crop_row.pack(fill="x", pady=(8, 0))
        self.crop_btn = button(crop_row, "Crop by hand…", variant="secondary",
                               height=28, font=T.font(T.SIZE_SM, "bold"),
                               command=editor._toggle_crop_mode)
        self.crop_btn.pack(side="left")
        button(crop_row, "Clear crop", variant="ghost", height=28,
               font=T.font(T.SIZE_SM), width=80,
               command=editor.clear_crop).pack(side="left", padx=(6, 0))

        audio = _group(self, "Audio and color")
        C.switch(audio, "Mute audio", variable=opts.mute_var).pack(anchor="w")
        color_row = ctk.CTkFrame(audio, fg_color="transparent")
        color_row.pack(fill="x", pady=(10, 0))
        self.color_label = ctk.CTkLabel(
            color_row, text="", font=T.font(T.SIZE_MD), text_color=T.TEXT,
            anchor="w", justify="left", wraplength=220,
        )
        self.color_label.pack(side="left", fill="x", expand=True)
        button(color_row, "Adjust", variant="ghost", width=60, height=28,
               text_color=T.ACCENT, font=T.font(T.SIZE_MD, "bold"),
               command=lambda: editor.inspector.show("color")).pack(side="right")
        opts.add_listener(self._refresh_color)
        self._refresh_color()

    def _refresh_color(self):
        summary = self.editor.options.color_summary()
        self.color_label.configure(
            text=summary.replace("Color grade on: ", "Color: ") if summary
            else "Color: unchanged",
            text_color=T.WARN if summary else T.TEXT,
        )


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

def _motion_hint(layer):
    n = len(getattr(layer, "_keyframes", []) or [])
    if layer.motion_var.get():
        if n:
            return f"{n} point{'s' if n != 1 else ''}. Move the playhead, then drag the caption to add the next."
        return "Move the playhead, then drag the caption in the preview to set a point."
    return f"Path with {n} points." if n else "Off. The caption stays put."


class TextPage(ctk.CTkScrollableFrame):
    def __init__(self, master, editor):
        super().__init__(master, fg_color="transparent",
                         scrollbar_button_color=T.BG_HOVER,
                         scrollbar_button_hover_color=T.BG_ACTIVE)
        self.editor = editor
        self.layer = None
        # Once there are captions the speech box shows only when asked
        # for (the Captions menu) or after a run started from it.
        self._speech_open = False
        self._build_empty()
        self._build_form()
        self.speech = SpeechCaptions(self, editor, on_close=self.hide_speech)
        self.refresh()

    # -- layout -----------------------------------------------------------
    def _build_empty(self):
        self.empty = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.empty, text="No captions yet", font=T.font(T.SIZE_LG, "bold"),
                     text_color=T.TEXT).pack(anchor="w", padx=_PAD, pady=(18, 4))
        C.hint(self.empty, "Add text at the playhead, or bring in captions "
                           "from a subtitle file or from the speech in the clip.").pack(
            anchor="w", padx=_PAD)
        col = ctk.CTkFrame(self.empty, fg_color="transparent")
        col.pack(fill="x", padx=_PAD, pady=(12, 0))
        button(col, "+ Add text", variant="primary", height=32,
               command=self.editor.add_text_layer).pack(fill="x")
        button(col, "Import SRT or VTT…", variant="secondary", height=32,
               command=self.editor._import_srt).pack(fill="x", pady=(6, 0))

    def _build_form(self):
        self.form = ctk.CTkFrame(self, fg_color="transparent")
        head = ctk.CTkFrame(self.form, fg_color="transparent")
        head.pack(fill="x", padx=(_PAD, 8), pady=(10, 0))
        self.title = ctk.CTkLabel(head, text="", font=T.font(T.SIZE_MD, "bold"),
                                  text_color=T.TEXT, anchor="w")
        self.title.pack(side="left")
        for name, cmd, hint in (
                ("delete", self._delete, "Delete this caption  (Delete)"),
                ("copy", self._duplicate, "Duplicate this caption"),
                ("add", self.editor.add_text_layer, "Add a caption at the playhead"),
                ("forward", lambda: self._step(1), "Next caption"),
                ("back", lambda: self._step(-1), "Previous caption")):
            # A gap keeps Delete away from the buttons beside it.
            icon_button(head, name, command=cmd, size=28, icon_size=12, hint=hint).pack(
                side="right", padx=(10, 0) if name == "delete" else 0)

        self.textbox = ctk.CTkTextbox(
            self.form, height=54, wrap="word", font=T.font(T.SIZE_LG),
            fg_color=T.BG_SURFACE, border_color=T.BORDER_STRONG, border_width=1,
            text_color=T.TEXT, corner_radius=T.RADIUS_SM,
            # Ctrl+Z inside the box undoes typing; it had no undo at all.
            undo=True, maxundo=200,
        )
        self.textbox.pack(fill="x", padx=_PAD, pady=(8, 0))
        self.textbox.bind("<KeyRelease>", self._text_changed)
        # Text pasted, cut or undone without a key going up (the right-click
        # menu, say) never reached the caption. The box changes after these
        # bindings run, so read it once it has.
        for virtual in ("<<Paste>>", "<<Cut>>", "<<Undo>>", "<<Redo>>"):
            self.textbox.bind(
                virtual, lambda _e: self.after_idle(self._text_changed), add="+")

        style = _group(self.form, "Style")
        self.style_seg = C.segmented(style, list(TEXT_STYLES.keys()),
                                     command=self._style_changed)
        self.style_seg.pack(fill="x")

        font_row = ctk.CTkFrame(style, fg_color="transparent")
        font_row.pack(fill="x", pady=(8, 0))
        self.font_menu = C.option_menu(font_row, self._font_choices(), width=150)
        self.font_menu.pack(side="left")
        self.size_entry = C.entry(font_row, width=48, justify="center")
        self.size_entry.pack(side="left", padx=(6, 6))
        # "abc" in the size box quietly became 24; say so in red instead.
        self.size_entry.bind("<KeyRelease>", lambda _e: self._check_size(), add="+")
        self.bold_cb = C.checkbox(font_row, "B")
        self.bold_cb.configure(font=T.font(T.SIZE_MD, "bold"), width=40)
        self.bold_cb.pack(side="left")
        self.italic_cb = C.checkbox(font_row, "I")
        self.italic_cb.configure(width=40)
        self.italic_cb.pack(side="left")

        color_row = ctk.CTkFrame(style, fg_color="transparent")
        color_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(color_row, text="Color", font=T.font(T.SIZE_SM),
                     text_color=T.TEXT_MUTED, width=44, anchor="w").pack(
            side="left", anchor="n", pady=(3, 0))
        self.palette = ColorPalette(color_row, command=self._color_changed)
        self.palette.pack(side="left")
        look_row = ctk.CTkFrame(style, fg_color="transparent")
        look_row.pack(fill="x", pady=(8, 0))
        self.outline_cb = C.checkbox(look_row, "Outline")
        self.outline_cb.pack(side="left")
        self.shadow_cb = C.checkbox(look_row, "Shadow")
        self.shadow_cb.pack(side="left", padx=(8, 0))
        self.box_cb = C.checkbox(look_row, "Box")
        self.box_cb.pack(side="left", padx=(8, 0))

        # Laid out a row each, so the whole form fits a 1440x900 window
        # without scrolling (it was 688 px tall in about 515).
        place = _group(self.form, "Position and timing")
        pos_row = ctk.CTkFrame(place, fg_color="transparent")
        pos_row.pack(fill="x")
        self.position_menu = C.option_menu(
            pos_row, list(POSITION_MAP.keys()) + ["Custom (drag)"], width=150,
            command=self._position_changed)
        self.position_menu.pack(side="left")
        C.hint(pos_row, "or drag it in the preview", wrap=150).pack(
            side="left", padx=(10, 0))
        times = ctk.CTkFrame(place, fg_color="transparent")
        times.pack(fill="x", pady=(8, 0))
        self.start_field = C.TimeField(times, "From", command=self._times_changed,
                                       width=106, inline=True)
        self.start_field.pack(side="left", padx=(0, 8))
        self.end_field = C.TimeField(times, "to", command=self._times_changed,
                                     width=106, inline=True)
        self.end_field.pack(side="left")
        fade_row = ctk.CTkFrame(place, fg_color="transparent")
        fade_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(fade_row, text="Fade all", font=T.font(T.SIZE_SM),
                     text_color=T.TEXT_MUTED, width=56, anchor="w").pack(side="left")
        C.segmented(fade_row, FADE_CHOICES,
                    variable=self.editor.options.fade_var).pack(
            side="left", fill="x", expand=True)

        # Motion is one row until it's in use; the how-to and Clear path
        # show once the switch is on or the caption has a path.
        motion = place
        mrow = ctk.CTkFrame(motion, fg_color="transparent")
        mrow.pack(fill="x", pady=(8, 10))
        self.motion_switch = C.switch(mrow, "Motion path",
                                      command=self._motion_toggled)
        self.motion_switch.pack(side="left")
        button(mrow, "Follow an object", variant="secondary", height=28,
               font=T.font(T.SIZE_SM, "bold"),
               command=lambda: self.layer and self.layer._request_autotrack()
               ).pack(side="right")
        self.motion_more = ctk.CTkFrame(motion, fg_color="transparent")
        self._motion_more_shown = False
        self.motion_hint = C.hint(self.motion_more, "")
        self.motion_hint.pack(side="left", fill="x", expand=True)
        button(self.motion_more, "Clear path", variant="ghost", height=28, width=80,
               font=T.font(T.SIZE_SM),
               command=self._clear_path).pack(side="right", padx=(6, 0))

    # -- binding ----------------------------------------------------------
    def refresh(self):
        """Re-bind to the editor's selected caption (or show the empty state)."""
        layers = self.editor.text_layers.layers
        index = self.editor.selected_text_index
        if not layers or index is None or not (0 <= index < len(layers)):
            self.layer = None
            self.form.pack_forget()
            self.empty.pack(fill="both", expand=True)
            self._place_speech()
            return
        self.empty.pack_forget()
        self.form.pack(fill="both", expand=True)
        layer = layers[index]
        if layer is not self.layer:
            self.layer = layer
            self.font_menu.configure(variable=layer.font_var)
            self.size_entry.configure(textvariable=layer.size_var)
            self._check_size()
            self.bold_cb.configure(variable=layer.bold_var)
            self.italic_cb.configure(variable=layer.italic_var)
            self.outline_cb.configure(variable=layer.outline_var)
            self.shadow_cb.configure(variable=layer.shadow_var)
            self.box_cb.configure(variable=layer.box_var)
            self.position_menu.configure(variable=layer.position_var)
            self.motion_switch.configure(variable=layer.motion_var)
            self.style_seg.set(layer.style_var.get())
            self.textbox.delete("1.0", "end")
            self.textbox.insert("1.0", layer.text_var.get())
            # Undo starts afresh for each caption, so it can't bring back
            # the text of the one shown before.
            self.textbox._textbox.edit_reset()
        self._place_speech()
        self.refresh_details()

    def refresh_details(self):
        """Cheap update for count, timing and motion text (no re-binding)."""
        if self.layer is None:
            return
        layers = self.editor.text_layers.layers
        if self.layer not in layers:
            self.refresh()
            return
        index = layers.index(self.layer)
        self.title.configure(text=f"Caption {index + 1} of {len(layers)}")
        start, end = self.layer.time_slider.get_values()
        self.start_field.set_value(seconds_to_hms(start))
        self.end_field.set_value(seconds_to_hms(end))
        self.motion_hint.configure(text=_motion_hint(self.layer))
        in_use = bool(self.layer.motion_var.get() or getattr(self.layer, "_keyframes", None))
        if in_use != self._motion_more_shown:
            self._motion_more_shown = in_use
            if in_use:
                self.motion_more.pack(fill="x", pady=(0, 10))
            else:
                self.motion_more.pack_forget()
        self.palette.set(self.layer.color_value())

    # -- captions from speech ---------------------------------------------
    def show_speech(self):
        """Open "Captions from speech" (the Captions menu sends people here)."""
        self._speech_open = True
        self.refresh()
        try:
            self._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    def hide_speech(self):
        self._speech_open = False
        self.refresh()

    def _place_speech(self):
        """Under the empty state's buttons, or above the caption form."""
        self.speech.pack_forget()
        if self.layer is None:
            self.speech.set_closable(False)
            self.speech.pack(fill="x", padx=_PAD, pady=(18, 0), after=self.empty)
        elif self._speech_open:
            self.speech.set_closable(True)
            self.speech.pack(fill="x", padx=_PAD, pady=(10, 0), before=self.form)

    # -- events -------------------------------------------------------------
    def _text_changed(self, _event=None):
        if self.layer is not None:
            self.layer._set_text(self.textbox.get("1.0", "end-1c"))

    def _style_changed(self, value):
        if self.layer is not None:
            self.layer.style_var.set(value)
            self.layer._on_style_change(value)

    def _color_changed(self, value):
        if self.layer is not None:
            self.layer.set_color(value)

    def _position_changed(self, value):
        if self.layer is not None:
            self.layer._on_position_choice(value)
            self.layer._fire_change()

    def _font_choices(self):
        """Every installed font that draws, once the index has read them.

        The menu used to stop at 30 of Tk's names, most of which drew as
        Arial. Until the index is ready (about a second after start),
        the common fonts, and the full list replaces them when it is.
        """
        from videokidnapper.ui.text_layers import _PREFERRED_FONTS, _get_system_fonts
        from videokidnapper.utils import font_index

        if font_index.families() is not None:
            return _get_system_fonts()
        _get_system_fonts()   # starts the index
        self.after(300, self._refill_fonts)
        return list(_PREFERRED_FONTS)

    def _refill_fonts(self):
        from videokidnapper.utils import font_index

        if font_index.families() is None:
            self.after(300, self._refill_fonts)
        else:
            self.font_menu.configure(values=self._font_choices())

    def _check_size(self):
        try:
            ok = int(self.size_entry.get().strip()) > 0
        except ValueError:
            ok = False
        self.size_entry.configure(border_color=T.BORDER_STRONG if ok else T.DANGER)

    def _times_changed(self, _value=None):
        if self.layer is None:
            return
        try:
            start = hms_to_seconds(self.start_field.get_value())
            end = hms_to_seconds(self.end_field.get_value())
        except ValueError:
            self.refresh_details()
            return
        index = self.editor.text_layers.layers.index(self.layer)
        self.editor.set_layer_time("text", index, start, end, final=True)

    def _motion_toggled(self):
        if self.layer is not None:
            self.layer._on_motion_toggled()
            self.refresh_details()

    def _clear_path(self):
        if self.layer is not None:
            self.layer._clear_keyframes()
            self.refresh_details()

    def _step(self, delta):
        layers = self.editor.text_layers.layers
        if self.layer is None or not layers:
            return
        index = (layers.index(self.layer) + delta) % len(layers)
        self.editor.select_layer("text", index)

    def _duplicate(self):
        if self.layer is not None:
            self.editor.duplicate_text_layer(self.editor.text_layers.layers.index(self.layer))

    def _delete(self):
        if self.layer is not None:
            self.editor.delete_layer("text", self.editor.text_layers.layers.index(self.layer))


def saved_whisper_model():
    """The model size last used, or the default if that setting is off."""
    model = settings.get("whisper_model", DEFAULT_WHISPER_MODEL)
    return model if model in MODEL_SIZES else DEFAULT_WHISPER_MODEL


class SpeechCaptions(ctk.CTkFrame):
    """Write captions from the speech in the selection, with Whisper.

    This used to be a small window that only asked for the model size.
    Now the model menu and the button sit in the Text tab, and the editor
    reports the run back here (see ``TrimTab.generate_captions``), so the
    progress and the outcome show where it was started.
    """

    def __init__(self, master, editor, on_close=None):
        super().__init__(master, fg_color="transparent")
        self.editor = editor
        self.running = False
        self._model = None

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x")
        C.section_label(head, "Captions from speech").pack(side="left")
        self.close_btn = icon_button(head, "close", size=22, icon_size=9,
                                     command=on_close)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        self.model_var = ctk.StringVar(value=saved_whisper_model())
        self.model_menu = C.option_menu(row, list(MODEL_SIZES), variable=self.model_var,
                                        width=92, command=lambda _v: self._show_note())
        self.model_menu.pack(side="left")
        self.go_btn = button(row, "Generate captions", variant="secondary", height=30,
                             font=T.font(T.SIZE_SM, "bold"), command=self._go_clicked)
        self.go_btn.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.bar = ctk.CTkProgressBar(self, height=6, progress_color=T.ACCENT,
                                      fg_color=T.BG_RAISED, corner_radius=3)
        self.status = C.hint(self, "")
        self.status.pack(anchor="w", fill="x", pady=(4, 0))
        self._show_note()

    def set_closable(self, closable):
        if closable:
            self.close_btn.pack(side="right")
        else:
            self.close_btn.pack_forget()

    # -- reports from the editor ----------------------------------------------
    def set_running(self, model):
        self.running = True
        self._model = model
        self.model_menu.configure(state="disabled")
        self.go_btn.configure(text="Stop", state="normal")
        self.bar.set(0)
        self.bar.pack(fill="x", pady=(6, 0), before=self.status)
        self._say(f"Transcribing with {model}… The first use of a model "
                  "downloads it.", T.TEXT_MUTED)

    def set_progress(self, fraction):
        if not self.running:
            return
        fraction = max(0.0, min(1.0, float(fraction)))
        self.bar.set(fraction)
        self._say(f"Transcribing with {self._model}… {int(fraction * 100)}%", T.TEXT_MUTED)

    def set_stopping(self):
        if self.running:
            self.go_btn.configure(text="Stopping…", state="disabled")

    def set_result(self, message, level="info"):
        """Back to ready, saying what happened (or why nothing could)."""
        self.running = False
        self.model_menu.configure(state="normal")
        self.go_btn.configure(text="Generate captions", state="normal")
        self.bar.pack_forget()
        self._say(message, {"success": T.SUCCESS, "warn": T.WARN,
                            "error": T.DANGER}.get(level, T.TEXT_MUTED))

    # -- internals --------------------------------------------------------------
    def _go_clicked(self):
        if self.running:
            self.editor.stop_captions()
        else:
            self.editor.generate_captions(self.model_var.get())

    def _show_note(self):
        if not self.running:
            note = WHISPER_MODEL_NOTES.get(self.model_var.get(), "")
            self._say(f"{note} Transcribes the selection.".strip(), T.TEXT_MUTED)

    def _say(self, text, color):
        self.status.configure(text=text, text_color=color)


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class ImagePage(ctk.CTkScrollableFrame):
    def __init__(self, master, editor):
        super().__init__(master, fg_color="transparent",
                         scrollbar_button_color=T.BG_HOVER,
                         scrollbar_button_hover_color=T.BG_ACTIVE)
        self.editor = editor
        self.layer = None

        self.empty = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(self.empty, text="No images yet", font=T.font(T.SIZE_LG, "bold"),
                     text_color=T.TEXT).pack(anchor="w", padx=_PAD, pady=(18, 4))
        C.hint(self.empty, "Put a logo, sticker or watermark on top of the "
                           "video. PNGs with transparency work best.").pack(
            anchor="w", padx=_PAD)
        col = ctk.CTkFrame(self.empty, fg_color="transparent")
        col.pack(fill="x", padx=_PAD, pady=(12, 0))
        button(col, "+ Add image…", variant="primary", height=32,
               command=editor.add_image_layer).pack(fill="x")
        button(col, "Paste from clipboard", variant="secondary", height=32,
               command=editor.paste_image_layer).pack(fill="x", pady=(6, 0))

        self.form = ctk.CTkFrame(self, fg_color="transparent")
        head = ctk.CTkFrame(self.form, fg_color="transparent")
        head.pack(fill="x", padx=(_PAD, 8), pady=(10, 0))
        self.title = ctk.CTkLabel(head, text="", font=T.font(T.SIZE_MD, "bold"),
                                  text_color=T.TEXT, anchor="w")
        self.title.pack(side="left")
        for name, cmd, hint in (
                ("delete", self._delete, "Delete this image  (Delete)"),
                ("add", editor.add_image_layer, "Add an image or sticker"),
                ("forward", lambda: self._step(1), "Next image"),
                ("back", lambda: self._step(-1), "Previous image")):
            icon_button(head, name, command=cmd, size=28, icon_size=12, hint=hint).pack(
                side="right", padx=(10, 0) if name == "delete" else 0)

        file_group = _group(self.form, "File")
        frow = ctk.CTkFrame(file_group, fg_color="transparent")
        frow.pack(fill="x")
        self.file_label = ctk.CTkLabel(frow, text="", font=T.font(T.SIZE_MD),
                                       text_color=T.TEXT, anchor="w")
        self.file_label.pack(side="left", fill="x", expand=True)
        button(frow, "Change…", variant="secondary", width=80, height=28,
               font=T.font(T.SIZE_SM, "bold"),
               command=lambda: self.layer and self.layer._pick_file()).pack(side="right")

        place = _group(self.form, "Position")
        self.position_menu = C.option_menu(place, POSITION_ANCHORS, width=150,
                                           command=self._position_changed)
        self.position_menu.pack(anchor="w")
        C.hint(place, "Or drag the image in the preview.").pack(anchor="w", pady=(4, 0))

        size = _group(self.form, "Size and opacity")
        for attr, label, lo, hi in (("scale", "Size", 0.05, 1.0),
                                    ("opacity", "Opacity", 0.0, 1.0)):
            row = ctk.CTkFrame(size, fg_color="transparent")
            row.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(row, text=label, font=T.font(T.SIZE_SM),
                         text_color=T.TEXT_MUTED, width=56, anchor="w").pack(side="left")
            sl = C.slider(row, lo, hi, width=170, command=lambda _v: self.refresh_details())
            sl.pack(side="left", padx=(0, 6))
            value = ctk.CTkLabel(row, text="", font=T.font(T.SIZE_SM, mono=True),
                                 text_color=T.TEXT, width=40)
            value.pack(side="left")
            setattr(self, f"{attr}_slider", sl)
            setattr(self, f"{attr}_value", value)

        timing = _group(self.form, "Timing")
        times = ctk.CTkFrame(timing, fg_color="transparent")
        times.pack(fill="x", pady=(0, 12))
        self.start_field = C.TimeField(times, "Shows from", command=self._times_changed)
        self.start_field.pack(side="left", padx=(0, 10))
        self.end_field = C.TimeField(times, "Until", command=self._times_changed)
        self.end_field.pack(side="left")
        self.refresh()

    def refresh(self):
        layers = self.editor.image_layers.layers
        index = self.editor.selected_image_index
        if not layers or index is None or not (0 <= index < len(layers)):
            self.layer = None
            self.form.pack_forget()
            self.empty.pack(fill="both", expand=True)
            return
        self.empty.pack_forget()
        self.form.pack(fill="both", expand=True)
        layer = layers[index]
        if layer is not self.layer:
            self.layer = layer
            self.position_menu.configure(variable=layer.position_var)
            self.scale_slider.configure(variable=layer.scale_var)
            self.opacity_slider.configure(variable=layer.opacity_var)
        self.refresh_details()

    def refresh_details(self):
        if self.layer is None:
            return
        layers = self.editor.image_layers.layers
        if self.layer not in layers:
            self.refresh()
            return
        index = layers.index(self.layer)
        self.title.configure(text=f"Image {index + 1} of {len(layers)}")
        path = self.layer.path_var.get()
        name = os.path.basename(path) if path else "No file chosen"
        # The overlay row's badge says whether the file is an animated
        # sticker; a path alone doesn't, and the preview shows one frame.
        badge = getattr(self.layer, "animated_badge", None)
        animated = badge.cget("text") if badge is not None else ""
        if animated:
            name = f"{name}   ·   {animated.lstrip('● ')}"
        self.file_label.configure(text=name)
        self.scale_value.configure(text=f"{int(self.layer.scale_var.get() * 100)}%")
        self.opacity_value.configure(text=f"{int(self.layer.opacity_var.get() * 100)}%")
        start, end = self.layer.time_slider.get_values()
        self.start_field.set_value(seconds_to_hms(start))
        self.end_field.set_value(seconds_to_hms(end))

    def _position_changed(self, _value):
        if self.layer is not None:
            self.layer._clear_drag_position()

    def _times_changed(self, _value=None):
        if self.layer is None:
            return
        try:
            start = hms_to_seconds(self.start_field.get_value())
            end = hms_to_seconds(self.end_field.get_value())
        except ValueError:
            self.refresh_details()
            return
        index = self.editor.image_layers.layers.index(self.layer)
        self.editor.set_layer_time("image", index, start, end, final=True)

    def _step(self, delta):
        layers = self.editor.image_layers.layers
        if self.layer is None or not layers:
            return
        index = (layers.index(self.layer) + delta) % len(layers)
        self.editor.select_layer("image", index)

    def _delete(self):
        if self.layer is not None:
            self.editor.delete_layer("image", self.editor.image_layers.layers.index(self.layer))


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------

class ColorPage(ctk.CTkFrame):
    _RANGES = {
        "color_brightness": (-0.5, 0.5),
        "color_contrast":   (0.5, 2.0),
        "color_saturation": (0.0, 2.0),
        "color_gamma":      (0.5, 2.0),
    }

    def __init__(self, master, editor):
        super().__init__(master, fg_color="transparent")
        self.editor = editor
        opts = editor.options

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=_PAD, pady=(14, 0))
        ctk.CTkLabel(head, text="Color for this clip", font=T.font(T.SIZE_MD, "bold"),
                     text_color=T.TEXT).pack(side="left")
        button(head, "Reset", variant="secondary", width=64, height=28,
               font=T.font(T.SIZE_SM, "bold"),
               command=opts.reset_color).pack(side="right")

        self._value_labels = []
        for key, label, default, var in opts.color_vars():
            lo, hi = self._RANGES[key]
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=_PAD, pady=(14, 0))
            ctk.CTkLabel(row, text=label, font=T.font(T.SIZE_MD), text_color=T.TEXT,
                         width=80, anchor="w").pack(side="left")
            sl = C.slider(row, lo, hi, variable=var, width=150)
            sl.pack(side="left", padx=(0, 8), fill="x", expand=True)
            # Double-click snaps the slider back to neutral.
            sl.bind("<Double-Button-1>", lambda _e, v=var, d=default: v.set(d))
            value = ctk.CTkLabel(row, text="", font=T.font(T.SIZE_SM, mono=True),
                                 width=44, anchor="e")
            value.pack(side="left")
            self._value_labels.append((value, var, default))

        C.hint(self, "The preview shows these changes, so what you see is "
                     "what you'll export. Double-click a slider to reset it.").pack(
            anchor="w", padx=_PAD, pady=(16, 0))
        opts.add_listener(self.refresh)
        self.refresh()

    def refresh(self):
        for label, var, default in self._value_labels:
            value = float(var.get())
            changed = abs(value - default) >= 0.001
            label.configure(
                text=(f"{value:+.2f}" if default == 0.0 else f"{value:.2f}"),
                text_color=T.WARN if changed else T.TEXT_MUTED,
            )
