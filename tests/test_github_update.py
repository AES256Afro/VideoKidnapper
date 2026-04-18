# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from videokidnapper.utils.github_update import is_newer


def test_greater_minor_is_newer():
    assert is_newer("1.1.0", "1.0.0")
    assert is_newer("v1.1.0", "v1.0.0")


def test_same_not_newer():
    assert not is_newer("1.0.0", "1.0.0")


def test_older_not_newer():
    assert not is_newer("0.9.0", "1.0.0")


def test_v_prefix_tolerated():
    assert is_newer("v2.0", "v1.9.9")


def test_garbage_tag_falls_back_to_zero():
    # unparseable tag compared against 1.0.0 -> not newer
    assert not is_newer("garbage", "1.0.0")
