# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

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


def test_parse_sha256_accepts_publisher_format():
    digest = "a" * 64
    assert prereq_check._parse_sha256(f"{digest}  ffmpeg.zip\n") == digest


def test_parse_sha256_rejects_missing_digest():
    with pytest.raises(ValueError, match="SHA-256"):
        prereq_check._parse_sha256("not a checksum")


def test_extract_ffmpeg_binaries_rejects_incomplete_archive(tmp_path):
    import zipfile
    archive = tmp_path / "ffmpeg.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("build/bin/readme.txt", "no executables")
    with pytest.raises(ValueError, match="missing"):
        prereq_check._extract_ffmpeg_binaries(archive, tmp_path / "stage")


def test_extract_ffmpeg_binaries_creates_staging_directory(tmp_path):
    import zipfile
    archive = tmp_path / "ffmpeg.zip"
    executable = b"MZ" + (b"\0" * (1024 * 1024))
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("build/bin/ffmpeg.exe", executable)
        zf.writestr("build/bin/ffprobe.exe", executable)
    staging = tmp_path / "new" / "stage"
    result = prereq_check._extract_ffmpeg_binaries(archive, staging)
    assert set(result) == {"ffmpeg.exe", "ffprobe.exe"}
    assert all(path.exists() for path in result.values())


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


def test_staged_binary_install_replaces_both(tmp_path):
    from videokidnapper.utils import prereq_check
    dest = tmp_path / "dest"
    stage = tmp_path / "stage"
    dest.mkdir()
    stage.mkdir()
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        (dest / name).write_bytes(b"old")
        (stage / name).write_bytes(b"new")
    prereq_check._install_staged_binaries(
        {name: stage / name for name in ("ffmpeg.exe", "ffprobe.exe")}, dest,
    )
    assert (dest / "ffmpeg.exe").read_bytes() == b"new"
    assert (dest / "ffprobe.exe").read_bytes() == b"new"
    assert not list(dest.glob("*.previous"))


def test_staged_binary_install_rolls_back_on_failure(tmp_path, monkeypatch):
    from videokidnapper.utils import prereq_check
    dest = tmp_path / "dest"
    stage = tmp_path / "stage"
    dest.mkdir()
    stage.mkdir()
    names = ("ffmpeg.exe", "ffprobe.exe")
    for name in names:
        (dest / name).write_bytes(f"old-{name}".encode())
        (stage / name).write_bytes(f"new-{name}".encode())
    real_replace = prereq_check.os.replace

    def fail_second_new(source, target):
        if Path(source) == stage / "ffprobe.exe":
            raise OSError("simulated replacement failure")
        return real_replace(source, target)

    monkeypatch.setattr(prereq_check.os, "replace", fail_second_new)
    with pytest.raises(OSError, match="simulated"):
        prereq_check._install_staged_binaries(
            {name: stage / name for name in names}, dest,
        )
    assert (dest / "ffmpeg.exe").read_bytes() == b"old-ffmpeg.exe"
    assert (dest / "ffprobe.exe").read_bytes() == b"old-ffprobe.exe"


# ---------------------------------------------------------------------------
# macOS automatic install
# ---------------------------------------------------------------------------

MACHO = b"\xcf\xfa\xed\xfe"


def _fake_download(payloads):
    """Stand-in for _download_with_sha256: writes canned bytes per URL."""
    import hashlib

    def download(url, target, progress_cb=None):
        data = payloads[url.rsplit("/", 1)[1]]
        Path(target).write_bytes(data)
        if progress_cb:
            progress_cb(0.5, "Downloading FFmpeg... 50%")
        return hashlib.sha256(data).hexdigest()
    return download


def _mac(monkeypatch, arch="arm64"):
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(prereq_check, "_mac_arch", lambda: arch)


def test_mac_install_verifies_pinned_digests_and_installs(tmp_path, monkeypatch):
    import hashlib
    _mac(monkeypatch)
    payloads = {"ffmpeg-darwin-arm64": MACHO + b"f" * (2 << 20),
                "ffprobe-darwin-arm64": MACHO + b"p" * (2 << 20)}
    monkeypatch.setattr(prereq_check, "_FFMPEG_MAC_SHA256", {
        ("arm64", "ffmpeg"): hashlib.sha256(payloads["ffmpeg-darwin-arm64"]).hexdigest(),
        ("arm64", "ffprobe"): hashlib.sha256(payloads["ffprobe-darwin-arm64"]).hexdigest(),
    })
    monkeypatch.setattr(prereq_check, "_download_with_sha256", _fake_download(payloads))
    notes = []
    ok, msg = prereq_check.install_ffmpeg_portable(
        tmp_path / "bin", progress_cb=lambda p, n: notes.append((p, n)))
    assert ok, msg
    for name in ("ffmpeg", "ffprobe"):
        installed = tmp_path / "bin" / name
        assert installed.read_bytes() == payloads[f"{name}-darwin-arm64"]
        assert os.access(installed, os.X_OK)
    assert notes[-1][0] == 1.0
    assert not list((tmp_path / "bin").glob(".videokidnapper-ffmpeg-*"))


def test_mac_install_refuses_a_tampered_download(tmp_path, monkeypatch):
    _mac(monkeypatch)
    payloads = {"ffmpeg-darwin-arm64": MACHO + b"f" * (2 << 20),
                "ffprobe-darwin-arm64": MACHO + b"p" * (2 << 20)}
    monkeypatch.setattr(prereq_check, "_FFMPEG_MAC_SHA256", {
        ("arm64", "ffmpeg"): "0" * 64, ("arm64", "ffprobe"): "0" * 64})
    monkeypatch.setattr(prereq_check, "_download_with_sha256", _fake_download(payloads))
    ok, msg = prereq_check.install_ffmpeg_portable(tmp_path / "bin")
    assert ok is False and "SHA-256" in msg
    assert not (tmp_path / "bin" / "ffmpeg").exists()


def test_mac_install_refuses_a_non_executable(tmp_path, monkeypatch):
    import hashlib
    _mac(monkeypatch, "x64")
    html = b"<html>rate limited</html>" + b" " * (2 << 20)
    payloads = {"ffmpeg-darwin-x64": html, "ffprobe-darwin-x64": html}
    monkeypatch.setattr(prereq_check, "_FFMPEG_MAC_SHA256", {
        ("x64", "ffmpeg"): hashlib.sha256(html).hexdigest(),
        ("x64", "ffprobe"): hashlib.sha256(html).hexdigest()})
    monkeypatch.setattr(prereq_check, "_download_with_sha256", _fake_download(payloads))
    ok, msg = prereq_check.install_ffmpeg_portable(tmp_path / "bin")
    assert ok is False and "not a Mac executable" in msg


def test_mac_install_keeps_the_old_binaries_on_failure(tmp_path, monkeypatch):
    _mac(monkeypatch)
    dest = tmp_path / "bin"
    dest.mkdir()
    (dest / "ffmpeg").write_bytes(b"old")
    monkeypatch.setattr(prereq_check, "_download_with_sha256",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no network")))
    ok, msg = prereq_check.install_ffmpeg_portable(dest)
    assert ok is False and "no network" in msg
    assert (dest / "ffmpeg").read_bytes() == b"old"


def test_pinned_mac_digests_cover_both_architectures():
    for arch in ("arm64", "x64"):
        for name in ("ffmpeg", "ffprobe"):
            digest = prereq_check._FFMPEG_MAC_SHA256[(arch, name)]
            assert len(digest) == 64 and int(digest, 16)


def test_auto_install_is_offered_only_where_it_works(monkeypatch):
    for platform, expected in (("win32", True), ("darwin", True), ("linux", False)):
        monkeypatch.setattr(sys, "platform", platform)
        assert prereq_check.can_auto_install_ffmpeg() is expected
    monkeypatch.setattr(sys, "platform", "darwin")
    assert "GitHub" in prereq_check.ffmpeg_download_source()
    monkeypatch.setattr(sys, "platform", "win32")
    assert "gyan" in prereq_check.ffmpeg_download_source()
