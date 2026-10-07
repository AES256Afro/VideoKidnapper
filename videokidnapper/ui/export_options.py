# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Compatibility names for the old Export Options panel.

The collapsible panel is gone: Studio spreads its controls across the
Edit inspector and the Export workspace, all bound to
:class:`~videokidnapper.ui.editor_options.EditorOptions`. The choice
lists and helpers it used to define are re-exported here so existing
imports keep working.
"""

from videokidnapper.ui.editor_options import (  # noqa: F401 — re-exported
    ASPECT_CHOICES, ASPECT_FILL_CHOICES, ASPECT_FILL_KEY_TO_LABEL,
    ASPECT_FILL_LABEL_TO_KEY, FADE_CHOICES, GIF_DITHER_CHOICES,
    GIF_DITHER_KEY_TO_LABEL, GIF_DITHER_LABEL_TO_KEY, GIF_LOOP_CHOICES,
    GIF_LOOP_KEY_TO_LABEL, GIF_LOOP_LABEL_TO_KEY, GIF_STATS_CHOICES,
    GIF_STATS_KEY_TO_LABEL, GIF_STATS_LABEL_TO_KEY, HW_CHOICES,
    ROTATE_CHOICES, SPEED_CHOICES, TRANSITION_CHOICES,
    TRANSITION_KEY_TO_LABEL, TRANSITION_LABEL_TO_KEY, EditorOptions,
    _color_grade_summary, _fade_to_seconds, _rotate_to_int,
    _seconds_to_fade_label, _speed_to_float,
)
