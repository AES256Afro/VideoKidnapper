# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Download and install a GitHub release without leaving the app.

Windows Setup and winget installs, and the portable .exe, update the way
Notepad++ and Notion do: the new build downloads with a progress bar, the
app closes, the update installs, and the app opens again.

* **Setup / winget**: the release's ``VideoKidnapper-Setup-<version>.exe``
  runs with ``/SILENT`` (a progress window, no questions), in the same
  scope as the existing install, and with ``/RELAUNCH=1`` so the installer
  opens the new version when it finishes (see the [Run] section of
  packaging/inno-setup/videokidnapper.iss).
* **Portable**: the release's ``VideoKidnapper.exe`` replaces the running
  file. Windows lets a running executable be renamed, so the old one is
  moved aside to ``*.old`` and removed on the next start.

Every download is checked against the SHA-256 digest GitHub publishes for
the release asset, and its size. A release without a digest is not
installed automatically; the caller falls back to opening the release.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from videokidnapper.utils.github_update import (  # noqa: F401 — re-exported
    GITHUB_REPO, SELF_UPDATE_CHANNELS, can_self_update as supported,
)

_API_TIMEOUT_S = 8
_DOWNLOAD_TIMEOUT_S = 30
_CHUNK = 256 * 1024
_USER_AGENT = "VideoKidnapper-updater"


class UpdateError(Exception):
    """A download or install step failed; the message is user-facing."""


class UpdateCancelled(UpdateError):
    """The user stopped the download."""


@dataclass(frozen=True)
class Asset:
    name: str
    size: int
    url: str
    sha256: str  # lower-case hex; "" when GitHub gave no digest


@dataclass(frozen=True)
class Release:
    tag: str
    url: str
    assets: tuple = field(default_factory=tuple)

    @property
    def version(self):
        return self.tag[1:] if self.tag[:1] in ("v", "V") else self.tag


def _sha256_of(digest):
    if isinstance(digest, str) and digest.lower().startswith("sha256:"):
        value = digest.split(":", 1)[1].strip().lower()
        if len(value) == 64 and all(c in "0123456789abcdef" for c in value):
            return value
    return ""


def parse_release(data):
    """A :class:`Release` from the GitHub releases API JSON."""
    assets = []
    for item in data.get("assets") or ():
        try:
            assets.append(Asset(
                name=str(item["name"]),
                size=int(item["size"]),
                url=str(item["browser_download_url"]),
                sha256=_sha256_of(item.get("digest")),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return Release(str(data.get("tag_name") or ""), str(data.get("html_url") or ""),
                   tuple(assets))


def fetch_release(repo=GITHUB_REPO, opener=urllib.request.urlopen):
    """The latest release, or None on any network or parse failure."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT},
    )
    try:
        with opener(req, timeout=_API_TIMEOUT_S) as resp:
            release = parse_release(json.load(resp))
    except Exception:
        return None
    return release if release.tag else None


def pick_asset(release, channel):
    """The file this channel installs from, or None if it can't self-update.

    Setup and winget installs run the Setup installer; the portable build
    swaps in the plain .exe. An asset without a SHA-256 digest is never
    returned, so nothing unverified gets installed.
    """
    if channel in ("setup", "winget"):
        wanted = f"VideoKidnapper-Setup-{release.version}.exe"
    elif channel == "portable":
        wanted = "VideoKidnapper.exe"
    else:
        return None
    for asset in release.assets:
        if asset.name == wanted and asset.sha256 and asset.size > 0:
            return asset
    return None


def download_dir():
    return Path(tempfile.gettempdir()) / "VideoKidnapper-update"


def download(asset, dest_dir=None, progress=None, cancel=None,
             opener=urllib.request.urlopen):
    """Download ``asset`` and verify it; returns the final path.

    ``progress(done_bytes, total_bytes)`` is called from this (worker)
    thread. ``cancel`` is a ``threading.Event``; setting it stops the
    download and raises :class:`UpdateCancelled`. Partial and failed
    downloads are deleted.
    """
    dest_dir = Path(dest_dir) if dest_dir else download_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / asset.name
    part = final.with_name(final.name + ".part")
    req = urllib.request.Request(asset.url, headers={"User-Agent": _USER_AGENT})
    digest = hashlib.sha256()
    done = 0
    try:
        with opener(req, timeout=_DOWNLOAD_TIMEOUT_S) as resp, open(part, "wb") as out:
            while True:
                if cancel is not None and cancel.is_set():
                    raise UpdateCancelled("Download cancelled.")
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if done > asset.size:
                    raise UpdateError("The download was larger than the release says.")
                if progress is not None:
                    progress(done, asset.size)
        if done != asset.size:
            raise UpdateError("The download was incomplete. Check your connection and try again.")
        if digest.hexdigest() != asset.sha256:
            raise UpdateError("The download didn't match the release checksum, so it wasn't installed.")
        if final.exists():
            final.unlink()
        part.replace(final)
        return final
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except Exception as exc:
        part.unlink(missing_ok=True)
        raise UpdateError(f"Couldn't download the update: {exc}") from exc


def installer_args(installer, scope):
    """Command line for a silent, in-place upgrade that reopens the app.

    ``scope`` is "user" or "machine", matching the existing install so the
    upgrade lands on top of it instead of beside it. A machine-wide
    upgrade shows the Windows admin prompt, as the first install did.
    """
    return [
        str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCANCEL",
        "/SP-", "/CLOSEAPPLICATIONS",
        "/ALLUSERS" if scope == "machine" else "/CURRENTUSER",
        "/RELAUNCH=1",
    ]


def _spawn_detached(args):
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, close_fds=True, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def start_setup_install(installer, scope, spawn=_spawn_detached):
    """Launch the installer; the caller must exit right after."""
    spawn(installer_args(installer, scope))


def swap_portable(new_exe, current_exe):
    """Put ``new_exe`` where ``current_exe`` is; returns the old file's path.

    The running exe is renamed (Windows allows that), the new one moved
    into its place. On failure the original is restored and
    :class:`UpdateError` raised.
    """
    current = Path(current_exe)
    old = current.with_name(current.name + ".old")
    try:
        if old.exists():
            old.unlink()
        current.replace(old)
    except OSError as exc:
        raise UpdateError(
            f"Can't replace {current.name} in {current.parent} ({exc.strerror or exc}). "
            "Move the app to a folder you can write to, or download the update yourself."
        ) from exc
    try:
        shutil.move(str(new_exe), str(current))
    except OSError as exc:
        try:
            old.replace(current)
        except OSError:
            pass
        raise UpdateError(f"Couldn't put the new version in place: {exc}") from exc
    return old


def start_portable(current_exe, spawn=_spawn_detached):
    """Open the freshly swapped-in portable build."""
    spawn([str(current_exe)])


def cleanup_after_update(current_exe=None):
    """Best-effort removal of leftovers from a previous update.

    Called at startup: the portable build's ``*.old`` file (once the old
    process has exited it can be deleted) and downloaded installers.
    """
    if current_exe is None and getattr(sys, "frozen", False):
        current_exe = sys.executable
    if current_exe:
        old = Path(current_exe).with_name(Path(current_exe).name + ".old")
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass
    shutil.rmtree(download_dir(), ignore_errors=True)
