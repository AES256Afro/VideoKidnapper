# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Preview approximation of the export's ``eq=`` color grade.

The export runs ffmpeg's ``eq`` filter on the video (see
``core/ffmpeg/filters._build_eq_filter``). The editor preview is a PIL
image, so this module mirrors the same math closely enough that what
you see before exporting is what you get:

- brightness / contrast / gamma: ffmpeg's per-value lookup table,
  ``v = contrast * (v - 0.5) + 0.5 + brightness`` then ``v ** (1/gamma)``.
  ffmpeg applies it to luma; here it's applied per RGB channel, which is
  visually very close for preview purposes.
- saturation: a blend toward the grayscale image, like scaling chroma.

Neutral values return the image untouched so the common case costs
nothing.
"""

from PIL import ImageEnhance

_NEUTRAL = (0.0, 1.0, 1.0, 1.0)


def is_neutral(brightness, contrast, saturation, gamma, tol=0.001):
    return (
        abs(brightness - _NEUTRAL[0]) < tol
        and abs(contrast - _NEUTRAL[1]) < tol
        and abs(saturation - _NEUTRAL[2]) < tol
        and abs(gamma - _NEUTRAL[3]) < tol
    )


def clamp_grade(brightness, contrast, saturation, gamma):
    """Same clamps ``_build_eq_filter`` applies before building the filter."""
    return (
        max(-1.0, min(1.0, float(brightness))),
        max(0.1, min(3.0, float(contrast))),
        max(0.0, min(3.0, float(saturation))),
        max(0.1, min(3.0, float(gamma))),
    )


def build_lut(brightness, contrast, gamma):
    """256-entry table for one 8-bit channel."""
    lut = []
    inv_gamma = 1.0 / gamma
    for i in range(256):
        v = contrast * (i / 255.0 - 0.5) + 0.5 + brightness
        if v <= 0.0:
            out = 0
        else:
            out = round(255.0 * min(1.0, v) ** inv_gamma)
        lut.append(max(0, min(255, out)))
    return lut


def apply_grade(image, brightness=0.0, contrast=1.0, saturation=1.0, gamma=1.0):
    """Return ``image`` (RGB) with the grade applied; neutral is a no-op."""
    if is_neutral(brightness, contrast, saturation, gamma):
        return image
    brightness, contrast, saturation, gamma = clamp_grade(
        brightness, contrast, saturation, gamma)
    if image.mode != "RGB":
        image = image.convert("RGB")
    if not (abs(brightness) < 0.001 and abs(contrast - 1) < 0.001
            and abs(gamma - 1) < 0.001):
        image = image.point(build_lut(brightness, contrast, gamma) * 3)
    if abs(saturation - 1.0) >= 0.001:
        image = ImageEnhance.Color(image).enhance(saturation)
    return image
