from videokidnapper.core.ffmpeg_backend import (
    _build_audio_speed, _build_crop_filter, _build_rotate_filter,
    _build_speed_filter,
)


def test_rotate_90():
    assert _build_rotate_filter(90) == "transpose=1"


def test_rotate_180():
    assert _build_rotate_filter(180) == "transpose=1,transpose=1"


def test_rotate_270():
    assert _build_rotate_filter(270) == "transpose=2"


def test_rotate_zero_returns_none():
    assert _build_rotate_filter(0) is None
    assert _build_rotate_filter(None) is None


def test_speed_identity_returns_none():
    assert _build_speed_filter(1.0) is None
    assert _build_speed_filter(None) is None


def test_speed_2x():
    f = _build_speed_filter(2.0)
    assert f.startswith("setpts=0.5000")


def test_audio_speed_chains_beyond_range():
    # 4x requires atempo=2.0 * atempo=2.0
    f = _build_audio_speed(4.0)
    assert f.count("atempo=") >= 2


def test_crop_returns_none_when_missing():
    info = {"width": 1920, "height": 1080}
    assert _build_crop_filter(None, info) is None


def test_crop_clamps_tiny():
    info = {"width": 100, "height": 100}
    # w=0 is invalid; builder should clamp to at least 2
    out = _build_crop_filter({"x": 0, "y": 0, "w": 0, "h": 0}, info)
    assert out.startswith("crop=2:2:")
