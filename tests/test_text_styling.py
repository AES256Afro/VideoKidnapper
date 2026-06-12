# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Tests for text-layer styling: outline, shadow, bold/italic fonts, multiline."""

from videokidnapper.core.ffmpeg.filters import _build_drawtext_filter
from videokidnapper.ui.text_layers import _find_font_path, _variant_font_path


def _layer(**overrides):
    base = {
        "text": "Hello",
        "font": "Arial",
        "fontsize": 24,
        "fontcolor": "white",
        "position": "(w-tw)/2:h-th-20",
        "box": False,
        "start": 0,
        "end": 10,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Outline (borderw / bordercolor)
# ---------------------------------------------------------------------------

def test_no_outline_by_default():
    out = _build_drawtext_filter(_layer())
    assert "borderw" not in out
    assert "bordercolor" not in out


def test_outline_emits_border_params():
    out = _build_drawtext_filter(_layer(borderw=2, bordercolor="black"))
    assert "borderw=2" in out
    assert "bordercolor=black" in out


def test_outline_zero_width_is_omitted():
    out = _build_drawtext_filter(_layer(borderw=0, bordercolor="black"))
    assert "borderw" not in out


def test_outline_negative_width_is_omitted():
    out = _build_drawtext_filter(_layer(borderw=-3))
    assert "borderw" not in out


def test_outline_garbage_width_is_omitted():
    out = _build_drawtext_filter(_layer(borderw="wide"))
    assert "borderw" not in out


def test_outline_missing_color_defaults_to_black():
    out = _build_drawtext_filter(_layer(borderw=2))
    assert "bordercolor=black" in out


# ---------------------------------------------------------------------------
# Shadow (shadowx / shadowy / shadowcolor)
# ---------------------------------------------------------------------------

def test_no_shadow_by_default():
    out = _build_drawtext_filter(_layer())
    assert "shadowx" not in out
    assert "shadowcolor" not in out


def test_shadow_emits_params():
    out = _build_drawtext_filter(
        _layer(shadowx=2, shadowy=2, shadowcolor="black@0.7"))
    assert "shadowx=2" in out
    assert "shadowy=2" in out
    assert "shadowcolor=black@0.7" in out


def test_shadow_single_axis_still_emits():
    out = _build_drawtext_filter(_layer(shadowx=0, shadowy=3))
    assert "shadowx=0" in out
    assert "shadowy=3" in out


def test_shadow_zero_offsets_omitted():
    out = _build_drawtext_filter(_layer(shadowx=0, shadowy=0))
    assert "shadowx" not in out


def test_shadow_missing_color_gets_default():
    out = _build_drawtext_filter(_layer(shadowx=2, shadowy=2))
    assert "shadowcolor=black@0.7" in out


# ---------------------------------------------------------------------------
# Back-compat: a pre-styling layer dict produces the same filter as before
# ---------------------------------------------------------------------------

def test_legacy_layer_dict_filter_is_unchanged():
    out = _build_drawtext_filter(_layer())
    # Exactly the historical option set, in order.
    for token in ("drawtext=text='Hello'", "fontsize=24", "fontcolor=white",
                  "x=(w-tw)/2", "y=h-th-20"):
        assert token in out
    for absent in ("borderw", "bordercolor", "shadowx", "shadowy",
                   "shadowcolor"):
        assert absent not in out


# ---------------------------------------------------------------------------
# Multiline text
# ---------------------------------------------------------------------------

def test_newlines_flow_through_to_drawtext():
    out = _build_drawtext_filter(_layer(text="line one\nline two"))
    assert "line one\nline two" in out


def test_crlf_normalised_to_lf():
    out = _build_drawtext_filter(_layer(text="line one\r\nline two\rthree"))
    assert "\r" not in out
    assert "line one\nline two\nthree" in out


# ---------------------------------------------------------------------------
# Bold / italic font-variant resolution
# ---------------------------------------------------------------------------

def _make_fonts(tmp_path, *names):
    for name in names:
        (tmp_path / name).write_bytes(b"\x00")
    return str(tmp_path)


def test_regular_face_when_no_style(tmp_path):
    fonts = _make_fonts(tmp_path, "arial.ttf", "arialbd.ttf")
    path = _find_font_path("Arial", fonts_dir=fonts)
    assert path.endswith("arial.ttf")


def test_bold_resolves_bd_suffix(tmp_path):
    fonts = _make_fonts(tmp_path, "arial.ttf", "arialbd.ttf")
    path = _find_font_path("Arial", bold=True, fonts_dir=fonts)
    assert path.endswith("arialbd.ttf")


def test_bold_resolves_single_b_suffix(tmp_path):
    # Georgia-style convention: georgiab.ttf.
    fonts = _make_fonts(tmp_path, "georgia.ttf", "georgiab.ttf")
    path = _find_font_path("Georgia", bold=True, fonts_dir=fonts)
    assert path.endswith("georgiab.ttf")


def test_italic_resolves_i_suffix(tmp_path):
    fonts = _make_fonts(tmp_path, "arial.ttf", "ariali.ttf")
    path = _find_font_path("Arial", italic=True, fonts_dir=fonts)
    assert path.endswith("ariali.ttf")


def test_italic_resolves_it_suffix(tmp_path):
    # Trebuchet-style convention: trebucit.ttf.
    fonts = _make_fonts(tmp_path, "trebuc.ttf", "trebucit.ttf")
    path = _find_font_path("Trebuchet MS", italic=True, fonts_dir=fonts)
    assert path.endswith("trebucit.ttf")


def test_bold_italic_resolves_bi_suffix(tmp_path):
    fonts = _make_fonts(tmp_path, "arial.ttf", "arialbi.ttf")
    path = _find_font_path("Arial", bold=True, italic=True, fonts_dir=fonts)
    assert path.endswith("arialbi.ttf")


def test_bold_italic_resolves_z_suffix(tmp_path):
    # Calibri/Georgia convention: calibriz.ttf.
    fonts = _make_fonts(tmp_path, "calibri.ttf", "calibriz.ttf")
    path = _find_font_path("Calibri", bold=True, italic=True, fonts_dir=fonts)
    assert path.endswith("calibriz.ttf")


def test_bold_italic_falls_back_to_bold_then_regular(tmp_path):
    fonts = _make_fonts(tmp_path, "arial.ttf", "arialbd.ttf")
    path = _find_font_path("Arial", bold=True, italic=True, fonts_dir=fonts)
    assert path.endswith("arialbd.ttf")

    sub = tmp_path / "sub"
    sub.mkdir()
    fonts2 = _make_fonts(sub, "impact.ttf")
    path = _find_font_path("Impact", bold=True, italic=True, fonts_dir=fonts2)
    assert path.endswith("impact.ttf")


def test_missing_variant_falls_back_to_regular(tmp_path):
    fonts = _make_fonts(tmp_path, "impact.ttf")
    path = _find_font_path("Impact", bold=True, fonts_dir=fonts)
    assert path.endswith("impact.ttf")


def test_variant_path_passthrough_when_no_style():
    assert _variant_font_path("/x/arial.ttf", False, False) == "/x/arial.ttf"


# ---------------------------------------------------------------------------
# Preview color parsing (alpha suffix)
# ---------------------------------------------------------------------------

def test_parse_color_rgba_alpha_suffix():
    from videokidnapper.ui.video_player import _parse_color_rgba
    assert _parse_color_rgba("black@0.7") == (0, 0, 0, 178)
    assert _parse_color_rgba("white@0.5") == (255, 255, 255, 127)


def test_parse_color_rgba_opaque_without_suffix():
    from videokidnapper.ui.video_player import _parse_color_rgba
    assert _parse_color_rgba("white") == (255, 255, 255, 255)
    assert _parse_color_rgba("#FF0000") == (255, 0, 0, 255)


def test_parse_color_rgba_bad_alpha_falls_back_opaque():
    from videokidnapper.ui.video_player import _parse_color_rgba
    assert _parse_color_rgba("black@oops") == (0, 0, 0, 255)


# ---------------------------------------------------------------------------
# Caption style preset
# ---------------------------------------------------------------------------

def test_caption_style_registered_with_outline():
    from videokidnapper.config import TEXT_STYLES
    caption = TEXT_STYLES["Caption"]
    assert caption["borderw"] > 0
    assert caption["box"] is False
