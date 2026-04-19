# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Backwards-compat facade for the split-out ``ffmpeg`` subpackage.

The real implementation lives under :mod:`videokidnapper.core.ffmpeg`
in focused submodules — see that package's ``__init__.py`` for the
module map. This file exists so existing callers that do:

    from videokidnapper.core.ffmpeg_backend import trim_to_video, ...
    from videokidnapper.core import ffmpeg_backend

keep working without an import update. Every public symbol the split
exposes is re-exported here; every private symbol that tests import
directly (``_assemble_video_filters``, ``_build_eq_filter``, etc.) is
also re-exported so the existing test suite runs unchanged.

When adding new ffmpeg-adjacent functionality, put it in the right
submodule under ``ffmpeg/`` and add the public symbol to that
submodule's ``__all__`` AND the top of the ``ffmpeg/__init__.py``
re-export list. This file shouldn't need changes unless you're
bridging a legacy private import a test was leaning on.
"""

# --- Public API (re-export from the new subpackage) ------------------------

from videokidnapper.core.ffmpeg import (
    CONCAT_TRANSITIONS,
    IMAGE_OVERLAY_POSITIONS,
    ProbeError,
    concat_clips,
    concat_clips_with_transition,
    detect_hardware_encoders,
    extract_frame,
    extract_waveform,
    frames_to_gif,
    frames_to_video,
    get_video_info,
    pick_video_encoder,
    trim_to_gif,
    trim_to_video,
)

# --- Legacy private symbols that tests / callers import directly -----------
#
# Everything below is technically internal, but external modules have
# established imports on these names. Re-export so the split is
# transparent. New internal-only helpers should NOT be added here.

from videokidnapper.core.ffmpeg._internals import (  # noqa: F401
    _encoder_quality_args,
    _get_ffmpeg,
    _get_ffprobe,
    _log_ffmpeg_failure,
    _parse_progress,
    _probe_encoder,
    _run_kwargs,
)
from videokidnapper.core.ffmpeg.concat import (  # noqa: F401
    _build_xfade_filter_complex,
    _probe_clip_duration,
    _xfade_transition_name,
)
from videokidnapper.core.ffmpeg.filters import (  # noqa: F401
    _assemble_video_filters,
    _build_aspect_crop,
    _build_audio_speed,
    _build_crop_filter,
    _build_drawtext_filter,
    _build_eq_filter,
    _build_image_overlay_chain,
    _build_rotate_filter,
    _build_scale_filter,
    _build_speed_filter,
    _build_text_filters,
    _fade_alpha_expr,
    _overlay_position_expr,
)


__all__ = [
    # Public
    "CONCAT_TRANSITIONS",
    "IMAGE_OVERLAY_POSITIONS",
    "ProbeError",
    "concat_clips",
    "concat_clips_with_transition",
    "detect_hardware_encoders",
    "extract_frame",
    "extract_waveform",
    "frames_to_gif",
    "frames_to_video",
    "get_video_info",
    "pick_video_encoder",
    "trim_to_gif",
    "trim_to_video",
]
