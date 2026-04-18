from videokidnapper.utils.size_estimator import (
    estimate_bytes, estimate_gif_bytes, estimate_mp3_bytes, estimate_mp4_bytes,
    human_bytes,
)


def test_zero_duration():
    assert estimate_bytes(0, "Medium", "GIF", 1920, 1080) == 0


def test_gif_scales_with_colors():
    low  = estimate_gif_bytes(5, "Low", 1920, 1080)
    high = estimate_gif_bytes(5, "High", 1920, 1080)
    assert high > low


def test_mp4_scales_with_crf_quality():
    low  = estimate_mp4_bytes(5, "Low", 1920, 1080)   # crf=28
    ultra = estimate_mp4_bytes(5, "Ultra", 1920, 1080)  # crf=15
    assert ultra > low


def test_mp3_independent_of_resolution():
    a = estimate_mp3_bytes(60)
    b = estimate_mp3_bytes(60)
    assert a == b
    assert a > 0


def test_audio_only_uses_mp3_estimate():
    est = estimate_bytes(30, "Medium", "MP4", 1920, 1080, audio_only=True)
    assert est == estimate_mp3_bytes(30)


def test_human_bytes_units():
    assert human_bytes(512).endswith("B")
    assert "KB" in human_bytes(2048)
    assert "MB" in human_bytes(5 * 1024 * 1024)


def test_small_input_no_upscale():
    # Low preset caps width at 480 — a 320-wide input should not grow.
    est = estimate_gif_bytes(5, "Low", 320, 240)
    assert est > 0
