# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
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


# ---------------------------------------------------------------------------
# ffmpeg_check binary resolution (frozen-app bundled lookup)
# ---------------------------------------------------------------------------

def test_find_ffmpeg_frozen_checks_next_to_executable(tmp_path, monkeypatch):
    """A frozen app must find ffmpeg bundled next to its own exe.

    PATH inside the MSIX container is unreliable (the activation broker
    does not rebuild it from the registry), so the packaged app ships
    ffmpeg at <exe dir>/assets/ffmpeg/bin and the resolver must look
    there without any PATH help.
    """
    import os
    from videokidnapper.utils import ffmpeg_check

    exe_name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    bundled = tmp_path / "assets" / "ffmpeg" / "bin" / exe_name
    bundled.parent.mkdir(parents=True)
    bundled.write_bytes(b"stub")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "VideoKidnapper.exe"))
    with patch.object(ffmpeg_check.shutil, "which", return_value=None):
        found = ffmpeg_check.find_ffmpeg()
    assert found == bundled


def test_find_ffmpeg_none_when_absent(tmp_path, monkeypatch):
    from videokidnapper.utils import ffmpeg_check

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "VideoKidnapper.exe"))
    with patch.object(ffmpeg_check.shutil, "which", return_value=None):
        # No bundled copy in tmp_path and (crucially) no PATH hit: the
        # repo-relative fallback may exist on dev machines, so only
        # assert the *type* contract — Path or None, never a crash.
        found = ffmpeg_check.find_ffmpeg()
    assert found is None or found.exists()


def test_find_ffmpeg_prefers_path(monkeypatch):
    from pathlib import Path
    from videokidnapper.utils import ffmpeg_check

    with patch.object(ffmpeg_check.shutil, "which", return_value="/usr/bin/ffmpeg"):
        assert ffmpeg_check.find_ffmpeg() == Path("/usr/bin/ffmpeg")


def test_describe_install_plan():
    from videokidnapper.utils.prereq_check import describe_install_plan
    text = describe_install_plan(["ffmpeg", "yt_dlp", "tkinterdnd2"])
    assert "FFmpeg (portable download" in text
    assert "yt-dlp (pip)" in text
    assert "tkinterdnd2 (pip)" in text


def test_describe_install_plan_empty():
    from videokidnapper.utils.prereq_check import describe_install_plan
    assert describe_install_plan([]) == ""


def test_pip_install_streaming_refuses_frozen(monkeypatch):
    import sys
    from videokidnapper.utils import prereq_check
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    ok, msg = prereq_check.pip_install_streaming("anything")
    assert not ok
    assert "bundled" in msg


def test_default_ffmpeg_install_dir_frozen_is_exe_relative(monkeypatch, tmp_path):
    import sys
    from videokidnapper.utils import prereq_check
    exe = tmp_path / "VideoKidnapper.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    dest = prereq_check.default_ffmpeg_install_dir()
    assert dest == tmp_path / "assets" / "ffmpeg" / "bin"


def test_missing_required_excludes_optional(monkeypatch):
    from videokidnapper.utils import prereq_check
    # Everything present → nothing missing.
    monkeypatch.setattr(prereq_check, "check_ffmpeg",
                        lambda: {"installed": True})
    monkeypatch.setattr(prereq_check, "check_python_package",
                        lambda name: {"installed": True})
    assert prereq_check.missing_required() == []


def test_missing_required_reports_ffmpeg_and_pkgs(monkeypatch):
    from videokidnapper.utils import prereq_check
    monkeypatch.setattr(prereq_check, "check_ffmpeg",
                        lambda: {"installed": False})

    def fake_pkg(name):
        return {"installed": name != "yt_dlp"}
    monkeypatch.setattr(prereq_check, "check_python_package", fake_pkg)
    missing = prereq_check.missing_required()
    assert missing[0] == "ffmpeg"         # ffmpeg first
    assert "yt_dlp" in missing
    assert "tkinterdnd2" not in missing   # optional never gates startup


def test_install_needs_restart_frozen_never(monkeypatch):
    import sys
    from videokidnapper.utils import prereq_check
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert prereq_check.install_needs_restart(["ffmpeg", "yt_dlp"]) is False


def test_install_needs_restart_source_needs_it_for_pkgs(monkeypatch):
    import sys
    from videokidnapper.utils import prereq_check
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert prereq_check.install_needs_restart(["ffmpeg"]) is False
    assert prereq_check.install_needs_restart(["ffmpeg", "yt_dlp"]) is True


def test_install_missing_orchestrates(monkeypatch):
    from videokidnapper.utils import prereq_check
    calls = []
    monkeypatch.setattr(prereq_check, "install_ffmpeg_portable",
                        lambda dest, progress_cb=None: (True, "ok"))
    monkeypatch.setattr(prereq_check, "pip_install_streaming",
                        lambda pkg, line_cb=None: (
                            calls.append(pkg), (True, "ok"))[1])
    installed, failures = prereq_check.install_missing(["ffmpeg", "yt_dlp"])
    assert installed == ["ffmpeg", "yt_dlp"]
    assert failures == []
    assert calls == ["yt-dlp"]


def test_install_missing_collects_failures(monkeypatch):
    from videokidnapper.utils import prereq_check
    monkeypatch.setattr(prereq_check, "install_ffmpeg_portable",
                        lambda dest, progress_cb=None: (False, "network error"))
    installed, failures = prereq_check.install_missing(["ffmpeg"])
    assert installed == []
    assert failures and failures[0][0] == "ffmpeg"
