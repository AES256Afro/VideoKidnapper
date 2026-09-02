# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""A corrupt project must not crash the editor — on either side.

`.vidkid` files are portable by design and `project_files.load_document`
validates their structure without inspecting layer contents, so every
number in a layer is untrusted. 1.8.2 hardened the ffmpeg filter
builders against that but left the preview canvas calling bare `int()`
and `float()` on the *same* dicts. The result was a project that
exported perfectly and crashed the preview:

    ValueError: invalid literal for int() with base 10: 'abc'

Both sides now share `utils.coerce`. These tests check the shared
helpers, and — the part that actually guards against the regression —
that the export and the preview agree about the same hostile layer.
"""

import pytest

from videokidnapper.utils.coerce import coerce_float, coerce_int


BAD_VALUES = ["abc", "", None, [], {}, "12abc", "  "]


@pytest.mark.parametrize("value", BAD_VALUES)
def test_coerce_int_falls_back(value):
    assert coerce_int(value, 24) == 24


@pytest.mark.parametrize("value", BAD_VALUES)
def test_coerce_float_falls_back(value):
    assert coerce_float(value, 0.25) == 0.25


def test_good_values_pass_through():
    assert coerce_int("42") == 42
    assert coerce_int(42.9) == 42
    assert coerce_float("0.5") == 0.5
    assert coerce_float(3) == 3.0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_rejected(value):
    """These convert without error but poison the arithmetic downstream —
    an infinite coordinate is not something ffmpeg or Pillow handles."""
    assert coerce_float(value, 1.0) == 1.0


# --------------------------------------------------------------------------
# The regression that motivated the shared module
# --------------------------------------------------------------------------

HOSTILE_TEXT_LAYERS = [
    {"text": "hi", "fontsize": "abc", "start": 0, "end": 9},
    {"text": "hi", "box": 1, "boxborderw": "?", "start": 0, "end": 9},
    {"text": "hi", "borderw": None, "start": 0, "end": 9},
    {"text": "hi", "shadowx": "n", "shadowy": "m", "start": 0, "end": 9},
    {"text": "hi", "fontsize": float("nan"), "start": 0, "end": 9},
    {"text": "hi", "start": "soon", "end": "later"},
]


@pytest.mark.parametrize("layer", HOSTILE_TEXT_LAYERS)
def test_export_survives_corrupt_text_layer(layer):
    from videokidnapper.core.ffmpeg.filters import _build_drawtext_filter

    spec = _build_drawtext_filter(layer)
    assert spec and spec.startswith("drawtext=")


@pytest.mark.parametrize("layer", HOSTILE_TEXT_LAYERS)
def test_preview_survives_the_same_corrupt_layer(layer):
    """The half that was missing. Skips without a display, like the rest
    of the UI tests."""
    ctk = pytest.importorskip("customtkinter")
    Image = pytest.importorskip("PIL.Image")

    from videokidnapper.ui.video_player import VideoPlayer

    try:
        root = ctk.CTk()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}")
    root.withdraw()
    try:
        player = VideoPlayer(root)
        player.set_text_layers_provider(lambda: [layer])
        frame = Image.new("RGB", (160, 120), (10, 20, 60))
        player._apply_text_overlay(frame, 1.0)   # must not raise
    finally:
        root.destroy()


def test_preview_survives_corrupt_image_overlay():
    ctk = pytest.importorskip("customtkinter")
    Image = pytest.importorskip("PIL.Image")

    from videokidnapper.ui.video_player import VideoPlayer

    try:
        root = ctk.CTk()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}")
    root.withdraw()
    try:
        player = VideoPlayer(root)
        player.set_image_layers_provider(lambda: [{
            "path": "/nonexistent.png", "scale": "big",
            "opacity": "x", "start": 0, "end": 9,
        }])
        player._apply_image_overlay(Image.new("RGB", (160, 120)), 1.0)
    finally:
        root.destroy()


def test_no_bare_numeric_casts_on_layer_data_in_the_preview():
    """Tripwire. The preview and the export read the same dicts; a bare
    int()/float() on one side is how they drifted apart last time."""
    import pathlib
    import re

    source = pathlib.Path("videokidnapper/ui/video_player.py").read_text()
    # Word boundary matters: coerce_int(layer.get(...) contains
    # "int(layer.get(" as a substring and is exactly what we want.
    offenders = re.findall(r'(?<![A-Za-z_])(?:int|float)\(\s*layer\.get\(', source)
    assert not offenders, (
        f"{len(offenders)} bare numeric cast(s) on layer data in "
        "video_player.py — use utils.coerce so the preview cannot crash "
        "on a project the export handles fine"
    )
