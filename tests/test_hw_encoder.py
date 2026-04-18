# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from videokidnapper.core import ffmpeg_backend


def test_pick_off_always_libx264(monkeypatch):
    monkeypatch.setattr(ffmpeg_backend, "_hw_encoders_cache", ["h264_nvenc"])
    assert ffmpeg_backend.pick_video_encoder("off") == "libx264"


def test_pick_auto_prefers_hw(monkeypatch):
    monkeypatch.setattr(ffmpeg_backend, "_hw_encoders_cache", ["h264_qsv"])
    assert ffmpeg_backend.pick_video_encoder("auto") == "h264_qsv"


def test_pick_auto_fallback(monkeypatch):
    monkeypatch.setattr(ffmpeg_backend, "_hw_encoders_cache", [])
    assert ffmpeg_backend.pick_video_encoder("auto") == "libx264"


def test_pick_specific_requested_but_absent(monkeypatch):
    monkeypatch.setattr(ffmpeg_backend, "_hw_encoders_cache", [])
    assert ffmpeg_backend.pick_video_encoder("h264_nvenc") == "libx264"


def test_quality_args_for_each_encoder():
    args_x264 = ffmpeg_backend._encoder_quality_args("libx264", 23)
    assert "-crf" in args_x264

    args_nvenc = ffmpeg_backend._encoder_quality_args("h264_nvenc", 23)
    assert "-cq" in args_nvenc

    args_qsv = ffmpeg_backend._encoder_quality_args("h264_qsv", 23)
    assert "-global_quality" in args_qsv

    args_vt = ffmpeg_backend._encoder_quality_args("h264_videotoolbox", 23)
    assert "-q:v" in args_vt


def test_aspect_crop_skips_matching_source():
    info = {"width": 1920, "height": 1080}
    assert ffmpeg_backend._build_aspect_crop("16:9", info, None) is None


def test_aspect_crop_portrait_target():
    info = {"width": 1920, "height": 1080}
    out = ffmpeg_backend._build_aspect_crop("9:16", info, None)
    assert out is not None and out.startswith("crop=")
    # 9:16 from a 1080-high source means target width ~607.
    assert "607" in out or "608" in out


def test_aspect_crop_square():
    info = {"width": 1920, "height": 1080}
    out = ffmpeg_backend._build_aspect_crop("1:1", info, None)
    assert out.startswith("crop=1080:1080:")


def test_aspect_crop_defers_to_explicit():
    info = {"width": 1920, "height": 1080}
    out = ffmpeg_backend._build_aspect_crop(
        "1:1", info, {"x": 0, "y": 0, "w": 100, "h": 100},
    )
    assert out is None


def test_crop_clamps_out_of_bounds_rect():
    """A crop rect larger than the video should clamp, not crash."""
    info = {"width": 1920, "height": 1080}
    out = ffmpeg_backend._build_crop_filter(
        {"x": 0, "y": 0, "w": 5000, "h": 3000}, info,
    )
    # Clamped to the video dimensions.
    assert out == "crop=1920:1080:0:0"


def test_crop_clamps_negative_origin():
    info = {"width": 640, "height": 480}
    out = ffmpeg_backend._build_crop_filter(
        {"x": -50, "y": -20, "w": 100, "h": 100}, info,
    )
    assert out == "crop=100:100:0:0"


def test_crop_clamps_origin_when_rect_overflows_right():
    info = {"width": 640, "height": 480}
    # x=600 + w=100 would go to x=700, but video is 640 wide — x clamps to 540.
    out = ffmpeg_backend._build_crop_filter(
        {"x": 600, "y": 0, "w": 100, "h": 100}, info,
    )
    assert out == "crop=100:100:540:0"


def test_crop_rejects_zero_video_dims():
    out = ffmpeg_backend._build_crop_filter(
        {"x": 0, "y": 0, "w": 10, "h": 10}, {"width": 0, "height": 0},
    )
    assert out is None


def test_detection_drops_probe_failures(monkeypatch):
    """nvenc listed in -encoders but failing probe should NOT appear."""
    monkeypatch.setattr(ffmpeg_backend, "_hw_encoders_cache", None)
    # Pretend ffmpeg -encoders lists both
    class FakeResult:
        stdout = " V..... h264_nvenc\n V..... h264_qsv\n"
        stderr = ""
        returncode = 0
    monkeypatch.setattr(
        ffmpeg_backend.subprocess, "run",
        lambda *a, **kw: FakeResult(),
    )
    # Probe fails for nvenc, succeeds for qsv
    def fake_probe(enc):
        return enc == "h264_qsv"
    monkeypatch.setattr(ffmpeg_backend, "_probe_encoder", fake_probe)

    result = ffmpeg_backend.detect_hardware_encoders()
    assert "h264_nvenc" not in result
    assert "h264_qsv" in result


def test_detection_caches(monkeypatch):
    monkeypatch.setattr(ffmpeg_backend, "_hw_encoders_cache", ["h264_qsv"])
    # Cache should be returned without running anything.
    def boom(*a, **kw):
        raise AssertionError("should not probe when cache is populated")
    monkeypatch.setattr(ffmpeg_backend, "_probe_encoder", boom)
    assert ffmpeg_backend.detect_hardware_encoders() == ["h264_qsv"]


def test_fade_alpha_expr_disabled():
    assert ffmpeg_backend._fade_alpha_expr(0, 10, 0) is None


def test_fade_alpha_expr_returns_expression():
    expr = ffmpeg_backend._fade_alpha_expr(1, 5, 0.5)
    assert expr is not None
    assert "if(" in expr
