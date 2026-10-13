# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""In-place updates: pick the right file, verify it, install it safely."""

import hashlib
import io
import threading
from pathlib import Path

import pytest

from videokidnapper.utils import self_update
from videokidnapper.utils.github_update import build_update_plan


PAYLOAD = b"new VideoKidnapper build " * 4096
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


def _release_json(tag="v1.9.2", setup_digest=f"sha256:{DIGEST}"):
    version = tag.lstrip("v")
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/x/y/releases/tag/{tag}",
        "assets": [
            {"name": f"VideoKidnapper-Setup-{version}.exe", "size": len(PAYLOAD),
             "browser_download_url": "https://example.test/setup.exe", "digest": setup_digest},
            {"name": "VideoKidnapper.exe", "size": len(PAYLOAD),
             "browser_download_url": "https://example.test/portable.exe",
             "digest": f"sha256:{DIGEST}"},
            {"name": "videokidnapper_1.9.2_amd64.deb", "size": 10,
             "browser_download_url": "https://example.test/x.deb", "digest": None},
        ],
    }


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _opener(payload=PAYLOAD):
    def opener(_request, timeout=None):
        return _Response(payload)
    return opener


# -- picking the asset ------------------------------------------------------

def test_parse_release_reads_digests():
    release = self_update.parse_release(_release_json())
    assert release.tag == "v1.9.2" and release.version == "1.9.2"
    by_name = {a.name: a for a in release.assets}
    assert by_name["VideoKidnapper.exe"].sha256 == DIGEST
    assert by_name["videokidnapper_1.9.2_amd64.deb"].sha256 == ""


@pytest.mark.parametrize("channel,expected", [
    ("setup", "VideoKidnapper-Setup-1.9.2.exe"),
    ("winget", "VideoKidnapper-Setup-1.9.2.exe"),
    ("portable", "VideoKidnapper.exe"),
])
def test_pick_asset_per_channel(channel, expected):
    release = self_update.parse_release(_release_json())
    assert self_update.pick_asset(release, channel).name == expected


@pytest.mark.parametrize("channel", ["store", "pip", "deb", "mac-dmg", "source"])
def test_other_channels_never_self_update(channel):
    release = self_update.parse_release(_release_json())
    assert self_update.pick_asset(release, channel) is None


@pytest.mark.parametrize("digest", [None, "", "md5:abc", "sha256:not-hex", "sha256:" + "a" * 63])
def test_asset_without_a_usable_digest_is_not_installed(digest):
    release = self_update.parse_release(_release_json(setup_digest=digest))
    assert self_update.pick_asset(release, "setup") is None


def test_fetch_release_returns_none_on_failure():
    def broken(_request, timeout=None):
        raise OSError("offline")
    assert self_update.fetch_release(opener=broken) is None


def test_fetch_release_parses_the_api_response():
    import json
    body = json.dumps(_release_json()).encode()
    release = self_update.fetch_release(opener=_opener(body))
    assert release.tag == "v1.9.2" and len(release.assets) == 3


# -- downloading ------------------------------------------------------------

def _asset(sha=DIGEST, size=len(PAYLOAD)):
    return self_update.Asset("VideoKidnapper-Setup-1.9.2.exe", size,
                             "https://example.test/setup.exe", sha)


def test_download_verifies_and_reports_progress(tmp_path):
    seen = []
    path = self_update.download(_asset(), tmp_path, progress=lambda d, t: seen.append((d, t)),
                                opener=_opener())
    assert path.read_bytes() == PAYLOAD
    assert seen[-1] == (len(PAYLOAD), len(PAYLOAD))
    assert all(a[0] <= b[0] for a, b in zip(seen, seen[1:])), "progress went backwards"
    assert not list(tmp_path.glob("*.part"))


def test_checksum_mismatch_is_rejected_and_deleted(tmp_path):
    with pytest.raises(self_update.UpdateError, match="checksum"):
        self_update.download(_asset(sha="0" * 64), tmp_path, opener=_opener())
    assert list(tmp_path.iterdir()) == []


def test_short_download_is_rejected(tmp_path):
    with pytest.raises(self_update.UpdateError, match="incomplete"):
        self_update.download(_asset(), tmp_path, opener=_opener(PAYLOAD[:-10]))
    assert list(tmp_path.iterdir()) == []


def test_oversized_download_is_rejected(tmp_path):
    with pytest.raises(self_update.UpdateError, match="larger"):
        self_update.download(_asset(size=100), tmp_path, opener=_opener())
    assert list(tmp_path.iterdir()) == []


def test_cancel_stops_the_download(tmp_path):
    cancel = threading.Event()

    def progress(done, total):
        cancel.set()

    with pytest.raises(self_update.UpdateCancelled):
        self_update.download(_asset(), tmp_path, progress=progress, cancel=cancel,
                             opener=_opener())
    assert list(tmp_path.iterdir()) == []


def test_network_error_becomes_update_error(tmp_path):
    def broken(_request, timeout=None):
        raise OSError("connection reset")
    with pytest.raises(self_update.UpdateError, match="connection reset"):
        self_update.download(_asset(), tmp_path, opener=broken)


# -- installing -------------------------------------------------------------

@pytest.mark.parametrize("scope,flag", [("user", "/CURRENTUSER"), ("machine", "/ALLUSERS")])
def test_installer_runs_silently_in_the_existing_scope_and_relaunches(scope, flag):
    args = self_update.installer_args(Path("C:/t/Setup.exe"), scope)
    assert args[0].endswith("Setup.exe")
    for needed in ("/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                   "/RELAUNCH=1", flag):
        assert needed in args, needed
    assert ("/ALLUSERS" in args) != ("/CURRENTUSER" in args)


def test_start_setup_install_spawns_the_installer():
    spawned = []
    self_update.start_setup_install(Path("Setup.exe"), "user", spawn=spawned.append)
    assert spawned and spawned[0][0] == "Setup.exe" and "/RELAUNCH=1" in spawned[0]


def test_swap_portable_moves_old_aside(tmp_path):
    current = tmp_path / "VideoKidnapper.exe"
    current.write_bytes(b"old build")
    new = tmp_path / "download" / "VideoKidnapper.exe"
    new.parent.mkdir()
    new.write_bytes(b"new build")
    old = self_update.swap_portable(new, current)
    assert current.read_bytes() == b"new build"
    assert old.read_bytes() == b"old build"
    assert not new.exists()


def test_swap_portable_restores_on_failure(tmp_path, monkeypatch):
    current = tmp_path / "VideoKidnapper.exe"
    current.write_bytes(b"old build")
    new = tmp_path / "missing.exe"  # moving it fails

    with pytest.raises(self_update.UpdateError):
        self_update.swap_portable(new, current)
    assert current.read_bytes() == b"old build", "the working build must be put back"


def test_swap_portable_unwritable_folder(tmp_path, monkeypatch):
    current = tmp_path / "VideoKidnapper.exe"
    current.write_bytes(b"old build")

    def deny(self, target):
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(Path, "replace", deny)
    with pytest.raises(self_update.UpdateError, match="folder you can write to"):
        self_update.swap_portable(tmp_path / "new.exe", current)


def test_cleanup_removes_leftovers(tmp_path, monkeypatch):
    exe = tmp_path / "VideoKidnapper.exe"
    exe.write_bytes(b"x")
    (tmp_path / "VideoKidnapper.exe.old").write_bytes(b"old")
    downloads = tmp_path / "dl"
    downloads.mkdir()
    (downloads / "VideoKidnapper-Setup-1.9.2.exe").write_bytes(b"setup")
    monkeypatch.setattr(self_update, "download_dir", lambda: downloads)
    self_update.cleanup_after_update(exe)
    assert exe.exists()
    assert not (tmp_path / "VideoKidnapper.exe.old").exists()
    assert not downloads.exists()


# -- the update plan ----------------------------------------------------------

@pytest.mark.parametrize("channel", ["setup", "winget", "portable"])
def test_windows_builds_get_restart_to_update(channel):
    plan = build_update_plan(channel, "https://example.test/r", platform_name="win32", frozen=True)
    assert plan.action == "install"
    assert plan.button_text == "Restart to update"


@pytest.mark.parametrize("channel", ["setup", "winget", "portable"])
def test_running_from_source_keeps_the_release_route(channel):
    plan = build_update_plan(channel, "https://example.test/r", platform_name="win32", frozen=False)
    assert plan.action == "release"


def test_store_still_updates_through_the_store():
    plan = build_update_plan("store", "https://example.test/r", platform_name="win32", frozen=True)
    assert plan.action == "store"
