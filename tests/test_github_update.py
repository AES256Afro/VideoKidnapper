# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
from videokidnapper.utils import github_update
from videokidnapper.utils.github_update import (
    build_update_plan, detect_install_channel, is_newer,
)


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


def test_appimage_environment_wins():
    assert detect_install_channel(
        platform_name="linux", frozen=True,
        env={"APPIMAGE": "/tmp/VideoKidnapper.AppImage"},
    ) == "appimage"


def test_store_package_detected(monkeypatch, tmp_path):
    monkeypatch.setattr(github_update, "_has_windows_package_identity", lambda: True)
    assert detect_install_channel(
        platform_name="win32", frozen=True, env={}, module_path=tmp_path,
    ) == "store"


def test_windows_portable_detected(monkeypatch, tmp_path):
    monkeypatch.setattr(github_update, "_has_windows_package_identity", lambda: False)
    monkeypatch.setattr(github_update, "_windows_installer_channel", lambda: None)
    assert detect_install_channel(
        platform_name="win32", frozen=True, env={}, module_path=tmp_path,
    ) == "portable"


def test_source_checkout_detected(tmp_path):
    (tmp_path / ".git").mkdir()
    module = tmp_path / "videokidnapper" / "utils" / "github_update.py"
    module.parent.mkdir(parents=True)
    assert detect_install_channel(
        platform_name="linux", frozen=False, env={}, module_path=module,
    ) == "source"


def test_update_plans_use_native_routes():
    winget = build_update_plan("winget", "https://example.test/release")
    store = build_update_plan("store", "https://example.test/release")
    portable = build_update_plan("portable", "https://example.test/release")
    assert winget.command[:4] == (
        "winget", "upgrade", "--id", "AES256Afro.VideoKidnapper",
    )
    assert store.action == "store"
    assert portable.action == "release"
    assert portable.copy_text == "https://example.test/release"
