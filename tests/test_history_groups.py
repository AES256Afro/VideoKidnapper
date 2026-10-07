# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Day grouping and time labels in the History list."""

from datetime import date

from videokidnapper.ui.history_tab import day_group, short_time

TODAY = date(2026, 10, 6)


def test_day_groups():
    assert day_group("2026-10-06 18:53", TODAY) == "Today"
    assert day_group("2026-10-05 09:01", TODAY) == "Yesterday"
    assert day_group("2026-09-28 14:00", TODAY) == "Earlier"


def test_unparseable_stamp_goes_to_earlier():
    assert day_group("", TODAY) == "Earlier"
    assert day_group(None, TODAY) == "Earlier"
    assert day_group("last tuesday", TODAY) == "Earlier"


def test_short_time_drops_the_date_for_recent_groups():
    assert short_time("2026-10-06 18:53", "Today") == "18:53"
    assert short_time("2026-10-05 09:01", "Yesterday") == "09:01"
    assert short_time("2026-09-28 14:00", "Earlier") == "2026-09-28 14:00"
    assert short_time(None, "Today") == ""
