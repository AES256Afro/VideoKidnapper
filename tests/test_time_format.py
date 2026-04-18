# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import pytest

from videokidnapper.utils.time_format import (
    format_duration, hms_to_seconds, seconds_to_hms,
)


def test_round_trip():
    for s in (0, 1.5, 59.999, 60.0, 3599.123, 3600.0, 12345.678):
        assert abs(hms_to_seconds(seconds_to_hms(s)) - s) < 0.002


def test_clamps_negative():
    assert seconds_to_hms(-5) == "00:00:00.000"


def test_invalid_hms_raises():
    with pytest.raises(ValueError):
        hms_to_seconds("not a time")


def test_format_duration_short():
    assert format_duration(5) == "5.0s"
    assert format_duration(90).startswith("1m")
