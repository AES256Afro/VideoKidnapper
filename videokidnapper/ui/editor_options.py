# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Export and clip settings as a shared model, separate from any widget.

The Studio layout spreads these controls across three places: speed,
rotate, frame and mute in the Edit inspector's Clip tab, the color grade
in its Color tab, and format, folder, GIF and join options in the Export
workspace. They all bind to one :class:`EditorOptions`, which persists
every change to settings and fans it out to listeners (size estimate,
dirty flag, color badge).

The Batch files page reads the same model, so speed, rotate, frame shape
and color have exactly one home.
"""

from videokidnapper.utils import settings
from videokidnapper.utils.file_naming import (
    LABEL_TO_STYLE, NAMING_STYLES, build_base_name, current_style,
)

import customtkinter as ctk


SPEED_CHOICES = ["0.25x", "0.5x", "0.75x", "1x", "1.25x", "1.5x", "2x", "3x", "4x"]
ROTATE_CHOICES = ["0°", "90°", "180°", "270°"]
ASPECT_CHOICES = ["Source", "1:1", "9:16", "16:9", "4:5", "3:4"]
FADE_CHOICES = ["Off", "0.25s", "0.5s", "1s"]
HW_CHOICES = ["auto", "off"]

# Concat transitions: UI label ↔ ffmpeg_backend transition key.
# "cut" preserves the fast lossless concat-demuxer path; every other
# value forces a re-encode via filter_complex xfade.
TRANSITION_CHOICES = [
    ("Cut",               "cut"),
    ("Crossfade",         "crossfade"),
    ("Fade to black",     "fadeblack"),
    ("Fade to white",     "fadewhite"),
]
TRANSITION_LABEL_TO_KEY = dict(TRANSITION_CHOICES)
TRANSITION_KEY_TO_LABEL = {k: label for label, k in TRANSITION_CHOICES}

# GIF palette options: UI label ↔ settings/backend key. Keys are consumed
# by core/ffmpeg/filters._build_paletteuse_filter / _build_palettegen_filter.
GIF_DITHER_CHOICES = [
    ("Bayer (small files)",   "bayer"),
    ("Floyd-Steinberg",       "floyd_steinberg"),
    ("Sierra",                "sierra2_4a"),
    ("None (flat colors)",    "none"),
]
GIF_DITHER_LABEL_TO_KEY = dict(GIF_DITHER_CHOICES)
GIF_DITHER_KEY_TO_LABEL = {k: label for label, k in GIF_DITHER_CHOICES}

GIF_STATS_CHOICES = [
    ("Full frame", "full"),
    ("Motion",     "diff"),
]
GIF_STATS_LABEL_TO_KEY = dict(GIF_STATS_CHOICES)
GIF_STATS_KEY_TO_LABEL = {k: label for label, k in GIF_STATS_CHOICES}

# Loop: label ↔ the value the GIF muxer's -loop flag takes
# (0 = forever, -1 = play once, N>0 = N extra loops).
GIF_LOOP_CHOICES = [
    ("Forever", 0),
    ("Once",    -1),
    ("2×",      2),
    ("3×",      3),
    ("5×",      5),
]
GIF_LOOP_LABEL_TO_KEY = dict(GIF_LOOP_CHOICES)
GIF_LOOP_KEY_TO_LABEL = {k: label for label, k in GIF_LOOP_CHOICES}

# How aspect presets reshape the frame. "crop" center-crops (historical
# behavior); "blur" fits the frame over a blurred copy of itself.
ASPECT_FILL_CHOICES = [
    ("Crop",      "crop"),
    ("Blur fill", "blur"),
]
ASPECT_FILL_LABEL_TO_KEY = dict(ASPECT_FILL_CHOICES)
ASPECT_FILL_KEY_TO_LABEL = {k: label for label, k in ASPECT_FILL_CHOICES}

COLOR_DEFAULTS = (
    ("color_brightness", "Brightness", 0.0),
    ("color_contrast",   "Contrast",   1.0),
    ("color_saturation", "Saturation", 1.0),
    ("color_gamma",      "Gamma",      1.0),
)


def _speed_to_float(label):
    try:
        return float(label.rstrip("x"))
    except ValueError:
        return 1.0


def _speed_label(value):
    """Closest ``SPEED_CHOICES`` label for a stored float (1.0 → "1x")."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 1.0
    return min(SPEED_CHOICES, key=lambda label: abs(_speed_to_float(label) - value))


def _rotate_to_int(label):
    try:
        return int(label.rstrip("°"))
    except ValueError:
        return 0


def _fade_to_seconds(label):
    if label == "Off":
        return 0.0
    try:
        return float(label.rstrip("s"))
    except ValueError:
        return 0.0


def _seconds_to_fade_label(value):
    if value <= 0:
        return "Off"
    for label in FADE_CHOICES[1:]:
        if abs(_fade_to_seconds(label) - value) < 0.01:
            return label
    return "Off"


def _color_grade_summary(brightness, contrast, saturation, gamma):
    """Short readout of the non-neutral color sliders, or "" when neutral.

    Shown wherever the grade could otherwise go unnoticed. The in-app
    preview doesn't apply the grade, so a forgotten slider (e.g.
    Saturation 0.20) would otherwise silently fade every export with
    nothing on screen to explain it. Uses the same 0.001 neutral
    tolerance as ``_build_eq_filter`` so the summary shows exactly when
    the export gets an ``eq=`` pass.
    """
    parts = []
    for label, value, default in (
        ("Brightness", brightness, 0.0),
        ("Contrast",   contrast,   1.0),
        ("Saturation", saturation, 1.0),
        ("Gamma",      gamma,      1.0),
    ):
        if abs(value - default) >= 0.001:
            shown = f"{value:+.2f}" if default == 0.0 else f"{value:.2f}"
            parts.append(f"{label} {shown}")
    if not parts:
        return ""
    return "Color grade on: " + ", ".join(parts)


class EditorOptions:
    """Tk variables for every export/clip option, plus persistence.

    ``autosave=True`` (the Studio editor) traces every variable: a change
    notifies listeners at once and writes settings after a short debounce,
    so slider drags don't rewrite the settings file on every pixel.
    ``autosave=False`` (the legacy panel) leaves saving to the caller.
    """

    _SAVE_DEBOUNCE_MS = 250

    def __init__(self, master, autosave=True):
        self._master = master
        self._listeners = []
        self._suspend = False
        self._save_after_id = None

        self.output_folder_var = ctk.StringVar(value=settings.get("output_folder"))
        self.naming_var = ctk.StringVar(value=NAMING_STYLES[current_style()][0])
        self.speed_var  = ctk.StringVar(value=_speed_label(settings.get("speed", 1.0)))
        self.rotate_var = ctk.StringVar(value=f"{settings.get('rotate', 0)}°")
        self.mute_var   = ctk.BooleanVar(value=settings.get("mute_audio", False))
        self.audio_only_var = ctk.BooleanVar(value=settings.get("audio_only", False))
        self.aspect_var = ctk.StringVar(value=settings.get("aspect_preset", "Source"))
        self.concat_var = ctk.BooleanVar(value=settings.get("concat_ranges", False))
        self.fade_var   = ctk.StringVar(value=_seconds_to_fade_label(settings.get("text_fade", 0.0)))
        self.hw_var     = ctk.StringVar(value=settings.get("hw_encoder", "auto"))
        # Color grade — persisted as floats, rendered as sliders.
        self.brightness_var = ctk.DoubleVar(value=float(settings.get("color_brightness", 0.0)))
        self.contrast_var   = ctk.DoubleVar(value=float(settings.get("color_contrast", 1.0)))
        self.saturation_var = ctk.DoubleVar(value=float(settings.get("color_saturation", 1.0)))
        self.gamma_var      = ctk.DoubleVar(value=float(settings.get("color_gamma", 1.0)))
        # Concat transition between queued ranges (ignored unless concat=on).
        self.transition_var = ctk.StringVar(
            value=TRANSITION_KEY_TO_LABEL.get(settings.get("concat_transition", "cut"), "Cut"),
        )
        self.transition_duration_var = ctk.DoubleVar(
            value=float(settings.get("concat_transition_duration", 0.5)),
        )
        # GIF palette options — persisted as backend keys, shown as labels.
        self.gif_dither_var = ctk.StringVar(
            value=GIF_DITHER_KEY_TO_LABEL.get(
                settings.get("gif_dither", "bayer"), GIF_DITHER_CHOICES[0][0]),
        )
        self.gif_stats_var = ctk.StringVar(
            value=GIF_STATS_KEY_TO_LABEL.get(
                settings.get("gif_stats_mode", "full"), GIF_STATS_CHOICES[0][0]),
        )
        self.gif_loop_var = ctk.StringVar(
            value=GIF_LOOP_KEY_TO_LABEL.get(
                settings.get("gif_loop", 0), GIF_LOOP_CHOICES[0][0]),
        )
        self.aspect_fill_var = ctk.StringVar(
            value=ASPECT_FILL_KEY_TO_LABEL.get(
                settings.get("aspect_fill_mode", "crop"), ASPECT_FILL_CHOICES[0][0]),
        )

        if autosave:
            for var in self.all_vars():
                var.trace_add("write", self._on_var_write)

    # ------------------------------------------------------------------
    def all_vars(self):
        return (
            self.output_folder_var, self.naming_var, self.speed_var, self.rotate_var,
            self.mute_var, self.audio_only_var, self.aspect_var,
            self.concat_var, self.fade_var, self.hw_var,
            self.brightness_var, self.contrast_var, self.saturation_var,
            self.gamma_var, self.transition_var, self.transition_duration_var,
            self.gif_dither_var, self.gif_stats_var, self.gif_loop_var,
            self.aspect_fill_var,
        )

    def color_vars(self):
        """``(settings key, label, neutral value, var)`` per color slider."""
        vars_ = (self.brightness_var, self.contrast_var,
                 self.saturation_var, self.gamma_var)
        return [(key, label, default, var)
                for (key, label, default), var in zip(COLOR_DEFAULTS, vars_)]

    def add_listener(self, callback):
        self._listeners.append(callback)

    def _notify(self):
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                pass

    def _on_var_write(self, *_):
        if self._suspend:
            return
        self._notify()
        if self._save_after_id is not None:
            try:
                self._master.after_cancel(self._save_after_id)
            except Exception:
                pass
        try:
            self._save_after_id = self._master.after(
                self._SAVE_DEBOUNCE_MS, self._flush_save,
            )
        except Exception:
            self.save()

    def _flush_save(self):
        self._save_after_id = None
        self.save()

    # ------------------------------------------------------------------
    def to_settings(self):
        return {
            "output_folder":    self.output_folder_var.get(),
            "naming_style":     self.naming_style(),
            "speed":            _speed_to_float(self.speed_var.get()),
            "rotate":           _rotate_to_int(self.rotate_var.get()),
            "mute_audio":       bool(self.mute_var.get()),
            "audio_only":       bool(self.audio_only_var.get()),
            "aspect_preset":    self.aspect_var.get(),
            "concat_ranges":    bool(self.concat_var.get()),
            "text_fade":        _fade_to_seconds(self.fade_var.get()),
            "hw_encoder":       self.hw_var.get(),
            "color_brightness": round(float(self.brightness_var.get()), 3),
            "color_contrast":   round(float(self.contrast_var.get()),   3),
            "color_saturation": round(float(self.saturation_var.get()), 3),
            "color_gamma":      round(float(self.gamma_var.get()),      3),
            "concat_transition":
                TRANSITION_LABEL_TO_KEY.get(self.transition_var.get(), "cut"),
            "concat_transition_duration":
                round(float(self.transition_duration_var.get()), 2),
            "gif_dither":
                GIF_DITHER_LABEL_TO_KEY.get(self.gif_dither_var.get(), "bayer"),
            "gif_stats_mode":
                GIF_STATS_LABEL_TO_KEY.get(self.gif_stats_var.get(), "full"),
            "gif_loop":
                GIF_LOOP_LABEL_TO_KEY.get(self.gif_loop_var.get(), 0),
            "aspect_fill_mode":
                ASPECT_FILL_LABEL_TO_KEY.get(self.aspect_fill_var.get(), "crop"),
        }

    def save(self):
        settings.update(self.to_settings())

    def get_options(self):
        return {
            "speed":         _speed_to_float(self.speed_var.get()),
            "rotate":        _rotate_to_int(self.rotate_var.get()),
            "mute":          bool(self.mute_var.get()),
            "audio_only":    bool(self.audio_only_var.get()),
            "aspect_preset": self.aspect_var.get(),
            "concat":        bool(self.concat_var.get()),
            "text_fade":     _fade_to_seconds(self.fade_var.get()),
            "hw_encoder":    self.hw_var.get(),
            "crop":          settings.get("crop"),
            # Color grade — consumed by ffmpeg_backend._build_eq_filter.
            "color_brightness": float(self.brightness_var.get()),
            "color_contrast":   float(self.contrast_var.get()),
            "color_saturation": float(self.saturation_var.get()),
            "color_gamma":      float(self.gamma_var.get()),
            # Concat transition — used by the export path to pick between
            # concat_clips and concat_clips_with_transition.
            "concat_transition":
                TRANSITION_LABEL_TO_KEY.get(self.transition_var.get(), "cut"),
            "concat_transition_duration": float(self.transition_duration_var.get()),
            # GIF palette options — consumed by trim_to_gif / frames_to_gif.
            "gif_dither":
                GIF_DITHER_LABEL_TO_KEY.get(self.gif_dither_var.get(), "bayer"),
            "gif_stats_mode":
                GIF_STATS_LABEL_TO_KEY.get(self.gif_stats_var.get(), "full"),
            "gif_loop":
                GIF_LOOP_LABEL_TO_KEY.get(self.gif_loop_var.get(), 0),
            # Aspect fill mode — picks crop vs blur-fill in
            # _assemble_video_filters when an aspect preset is active.
            "aspect_fill_mode":
                ASPECT_FILL_LABEL_TO_KEY.get(self.aspect_fill_var.get(), "crop"),
        }

    def apply_options(self, data):
        """Restore project-specific values; notifies and saves once."""
        data = data or {}
        self._suspend = True
        try:
            if data.get("output_folder"):
                self.output_folder_var.set(str(data["output_folder"]))
            self.speed_var.set(_speed_label(data.get("speed", 1.0)))
            rotate = int(data.get("rotate", 0)) % 360
            self.rotate_var.set(f"{rotate}°" if f"{rotate}°" in ROTATE_CHOICES else "0°")
            self.mute_var.set(bool(data.get("mute", False)))
            self.audio_only_var.set(bool(data.get("audio_only", False)))
            aspect = str(data.get("aspect_preset", "Source"))
            self.aspect_var.set(aspect if aspect in ASPECT_CHOICES else "Source")
            self.concat_var.set(bool(data.get("concat", False)))
            self.fade_var.set(_seconds_to_fade_label(float(data.get("text_fade", 0.0))))
            self.hw_var.set(str(data.get("hw_encoder", "auto")))
            for key, _label, default, var in self.color_vars():
                var.set(float(data.get(key, default)))
            transition = str(data.get("concat_transition", "cut"))
            self.transition_var.set(TRANSITION_KEY_TO_LABEL.get(transition, "Cut"))
            self.transition_duration_var.set(
                float(data.get("concat_transition_duration", 0.5)))
            self.gif_dither_var.set(GIF_DITHER_KEY_TO_LABEL.get(
                data.get("gif_dither", "bayer"), GIF_DITHER_CHOICES[0][0],
            ))
            self.gif_stats_var.set(GIF_STATS_KEY_TO_LABEL.get(
                data.get("gif_stats_mode", "full"), GIF_STATS_CHOICES[0][0],
            ))
            self.gif_loop_var.set(GIF_LOOP_KEY_TO_LABEL.get(
                data.get("gif_loop", 0), GIF_LOOP_CHOICES[0][0],
            ))
            self.aspect_fill_var.set(ASPECT_FILL_KEY_TO_LABEL.get(
                data.get("aspect_fill_mode", "crop"), ASPECT_FILL_CHOICES[0][0],
            ))
        finally:
            self._suspend = False
        self.save()
        self._notify()

    def reset_color(self):
        self._suspend = True
        try:
            for _key, _label, default, var in self.color_vars():
                var.set(default)
        finally:
            self._suspend = False
        self.save()
        self._notify()

    def color_summary(self):
        return _color_grade_summary(
            float(self.brightness_var.get()),
            float(self.contrast_var.get()),
            float(self.saturation_var.get()),
            float(self.gamma_var.get()),
        )

    def get_output_folder(self):
        return self.output_folder_var.get()

    def naming_style(self):
        """Settings key of the chosen file-name style."""
        return LABEL_TO_STYLE.get(self.naming_var.get(), "title")

    def naming_example(self, title=None, ext="mp4"):
        """What the next export will be called, as shown beside the picker.

        A style name alone does not say much; an example does. Without a
        video loaded the sample title is one that needs cleaning up, so the
        example also shows that titles are sanitized.
        """
        try:
            stem = build_base_name("trim", title or "Cat Video: Take 2",
                                   style=self.naming_style())
        except Exception:
            return ""
        return f"{stem}.{ext}"

    def set_aspect(self, value):
        if value in ASPECT_CHOICES:
            self.aspect_var.set(value)
