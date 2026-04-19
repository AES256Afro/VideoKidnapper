# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Split-out ffmpeg subpackage.

The previous :mod:`videokidnapper.core.ffmpeg_backend` was a 1200-line
wall of mixed concerns — binary resolution, filter construction, encode
driving, concat logic, waveform extraction. Each piece moved into a
focused submodule here; ``ffmpeg_backend.py`` stays as a thin re-export
facade so external callers (``trim_tab.py``, ``url_tab.py``, CLI,
tests) don't have to update their imports.

Module map:

- :mod:`_internals` — binary resolution, HW encoder detection, progress
  parsing, failure logging. Cross-module private helpers.
- :mod:`probe` — read-only queries: ``ProbeError``, ``get_video_info``,
  ``extract_frame``, ``extract_waveform``.
- :mod:`filters` — filter-string builders: crop, rotate, speed, eq,
  drawtext, image overlay chain, aspect crop, and the full
  ``_assemble_video_filters`` orchestrator.
- :mod:`encode` — user-facing encode entry points: ``trim_to_video``,
  ``trim_to_gif``, ``frames_to_video``, ``frames_to_gif``.
- :mod:`concat` — ``concat_clips`` (lossless) +
  ``concat_clips_with_transition`` (xfade re-encode).
"""

# Public API — re-exported from ffmpeg_backend.py so existing callers
# keep working. Add new public symbols here when new features land.

from videokidnapper.core.ffmpeg._internals import (
    detect_hardware_encoders,
    pick_video_encoder,
)
from videokidnapper.core.ffmpeg.concat import (
    CONCAT_TRANSITIONS,
    concat_clips,
    concat_clips_with_transition,
)
from videokidnapper.core.ffmpeg.encode import (
    frames_to_gif,
    frames_to_video,
    trim_to_gif,
    trim_to_video,
)
from videokidnapper.core.ffmpeg.filters import (
    IMAGE_OVERLAY_POSITIONS,
)
from videokidnapper.core.ffmpeg.probe import (
    ProbeError,
    extract_frame,
    extract_waveform,
    get_video_info,
)


__all__ = [
    # probe
    "ProbeError",
    "extract_frame",
    "extract_waveform",
    "get_video_info",
    # encoders
    "detect_hardware_encoders",
    "pick_video_encoder",
    # encode
    "frames_to_gif",
    "frames_to_video",
    "trim_to_gif",
    "trim_to_video",
    # concat
    "CONCAT_TRANSITIONS",
    "concat_clips",
    "concat_clips_with_transition",
    # filters — image overlay constants
    "IMAGE_OVERLAY_POSITIONS",
]
