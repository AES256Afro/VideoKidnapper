import sys
from unittest.mock import patch

from videokidnapper.utils import prereq_check


def test_check_python_package_detects_installed():
    # pathlib is always available
    result = prereq_check.check_python_package("pathlib")
    assert result["installed"] is True


def test_check_python_package_detects_missing():
    result = prereq_check.check_python_package("__definitely_not_a_real_module__")
    assert result["installed"] is False
    assert result["version"] is None


def test_pip_name_mapping():
    assert prereq_check._pip_name_for("PIL") == "Pillow"
    assert prereq_check._pip_name_for("yt_dlp") == "yt-dlp"
    # Passes through unchanged for packages where import==pip name.
    assert prereq_check._pip_name_for("customtkinter") == "customtkinter"


def test_build_install_commands_windows():
    with patch.object(sys, "platform", "win32"):
        cmds = prereq_check.build_install_commands(
            missing_ffmpeg=True,
            missing_pip=["yt-dlp"],
        )
        assert any("winget" in c for c in cmds)
        assert any("yt-dlp" in c for c in cmds)


def test_build_install_commands_darwin():
    with patch.object(sys, "platform", "darwin"):
        cmds = prereq_check.build_install_commands(
            missing_ffmpeg=True,
            missing_pip=["Pillow"],
        )
        assert any("brew install ffmpeg" in c for c in cmds)
        assert any("Pillow" in c for c in cmds)


def test_build_install_commands_linux():
    with patch.object(sys, "platform", "linux"):
        cmds = prereq_check.build_install_commands(
            missing_ffmpeg=True,
            missing_pip=["mss"],
        )
        assert any("apt-get install" in c for c in cmds)
        assert any("mss" in c for c in cmds)


def test_build_install_commands_nothing_missing():
    cmds = prereq_check.build_install_commands(
        missing_ffmpeg=False, missing_pip=[],
    )
    assert cmds == []


def test_check_all_shape():
    result = prereq_check.check_all()
    assert "FFmpeg" in result
    # Every expected key should carry the uniform fields.
    for info in result.values():
        assert "installed" in info
        assert "optional" in info
        assert "description" in info


def test_install_ffmpeg_portable_non_windows_returns_guidance():
    with patch.object(sys, "platform", "linux"):
        ok, msg = prereq_check.install_ffmpeg_portable("/tmp")
        assert ok is False
        # The message should point the user at the right package manager.
        assert "brew" in msg or "package manager" in msg


def test_default_ffmpeg_install_dir_is_project_relative():
    path = prereq_check.default_ffmpeg_install_dir()
    # Should be inside the project under assets/ffmpeg/bin.
    assert path.name == "bin"
    assert path.parent.name == "ffmpeg"
    assert path.parent.parent.name == "assets"


def test_has_any_missing_when_everything_present(monkeypatch):
    fake = {
        "FFmpeg":       {"installed": True, "optional": False},
        "Pillow":       {"installed": True, "optional": False},
        "tkinterdnd2":  {"installed": False, "optional": True},
    }
    monkeypatch.setattr(prereq_check, "check_all", lambda: fake)
    # required_only → optional misses don't count
    assert prereq_check.has_any_missing(required_only=True) is False
    # When counting optional, the tkinterdnd2 gap counts.
    assert prereq_check.has_any_missing(required_only=False) is True
