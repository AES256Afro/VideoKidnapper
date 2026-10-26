# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
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


@pytest.mark.parametrize("typed, seconds", [
    ("1:30", 90.0), ("90", 90.0), ("90.5", 90.5), ("1:30,25", 90.25),
    ("0:01:30.250", 90.25), ("  7 ", 7.0), ("1:02:03", 3723.0),
])
def test_short_typed_times_are_understood(typed, seconds):
    """"1:30" in a time box used to be refused and put back silently."""
    assert hms_to_seconds(typed) == pytest.approx(seconds)


@pytest.mark.parametrize("typed", ["", "abc", "1::2", "1:2:3:4", "-5", "1:30x"])
def test_anything_else_is_still_refused(typed):
    with pytest.raises(ValueError):
        hms_to_seconds(typed)
