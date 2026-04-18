# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Rough output-size estimates shown next to the Export button.

These are approximations — real compression varies with content. We label
the number as "~" in the UI and err slightly high so users aren't
surprised.
"""

from videokidnapper.config import PRESETS


def _scaled_resolution(preset_name, input_width, input_height):
    """Return (w, h) after preset scaling, preserving aspect ratio."""
    preset = PRESETS[preset_name]
    target_w = preset["width"]
    if target_w is None or input_width <= target_w:
        return input_width, input_height
    scale = target_w / input_width
    return target_w, max(1, int(input_height * scale))


def estimate_gif_bytes(duration_s, preset_name, input_width, input_height):
    preset = PRESETS[preset_name]
    w, h = _scaled_resolution(preset_name, input_width, input_height)
    fps = preset["fps"]
    colors = preset["gif_colors"]
    frames = duration_s * fps
    # Empirical constant: bayer-dithered indexed GIF frames run about 0.22
    # bytes/pixel at 256 colors, scaled linearly down for smaller palettes.
    per_frame = w * h * 0.22 * (colors / 256)
    return int(frames * per_frame)


def estimate_mp4_bytes(duration_s, preset_name, input_width, input_height):
    preset = PRESETS[preset_name]
    w, h = _scaled_resolution(preset_name, input_width, input_height)
    fps = preset["fps"]
    crf = preset["video_crf"]
    # Rough CRF-to-bitrate-per-pixel curve tuned against libx264 defaults.
    # Lower CRF = higher quality = bigger file.
    bits_per_pixel = 0.18 * (2 ** ((23 - crf) / 6))
    bitrate_bps = w * h * fps * bits_per_pixel
    audio_bps = 128_000  # AAC 128k
    return int((bitrate_bps + audio_bps) * duration_s / 8)


def estimate_mp3_bytes(duration_s):
    return int(192_000 * duration_s / 8)


def estimate_bytes(duration_s, preset_name, fmt, input_width, input_height,
                   audio_only=False):
    if duration_s <= 0:
        return 0
    if audio_only:
        return estimate_mp3_bytes(duration_s)
    if fmt.upper() == "GIF":
        return estimate_gif_bytes(duration_s, preset_name, input_width, input_height)
    return estimate_mp4_bytes(duration_s, preset_name, input_width, input_height)


def human_bytes(n):
    units = ["B", "KB", "MB", "GB"]
    size = float(n)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
