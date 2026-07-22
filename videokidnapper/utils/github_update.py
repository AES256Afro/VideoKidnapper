# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Minimal 'check GitHub releases for a newer version' helper.

Runs on a daemon thread with a short timeout; never blocks UI, never raises
into the caller. Returns `(latest_tag, html_url)` or `None` on any error.
"""

import json
import os
import re
import sys
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path


GITHUB_REPO = "AES256Afro/VideoKidnapper"
_TIMEOUT_S = 4
WINGET_PACKAGE_ID = "AES256Afro.VideoKidnapper"
STORE_PRODUCT_ID = "9N4BMTK8Q7KG"


@dataclass(frozen=True)
class UpdatePlan:
    channel: str
    label: str
    summary: str
    action: str
    button_text: str
    command: tuple[str, ...] = ()
    copy_text: str = ""


def _has_windows_package_identity():
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        length = ctypes.c_uint32(0)
        result = ctypes.windll.kernel32.GetCurrentPackageFullName(
            ctypes.byref(length), None,
        )
        return result == 122 or result == 0
    except Exception:
        return False


def _windows_installer_channel():
    """Return winget or setup when the Inno uninstall record exists."""
    try:
        import winreg
    except ImportError:
        return None
    key_name = (
        "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\"
        "{8C8E1A2F-5D4B-4E6A-9F32-7C1A5B2D6E84}_is1"
    )
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for access in (
            winreg.KEY_READ,
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0),
        ):
            try:
                with winreg.OpenKey(root, key_name, 0, access) as key:
                    try:
                        package_id, _ = winreg.QueryValueEx(
                            key, "WinGetPackageIdentifier",
                        )
                    except OSError:
                        package_id = ""
                    return (
                        "winget" if package_id == WINGET_PACKAGE_ID else "setup"
                    )
            except OSError:
                continue
    return None


def _inside_source_checkout(module_path):
    path = Path(module_path).resolve()
    return any((parent / ".git").exists() for parent in (path, *path.parents))


def detect_install_channel(
    platform_name=None, frozen=None, env=None, module_path=None,
):
    """Identify the install route without changing the user's system."""
    platform_name = platform_name or sys.platform
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    env = os.environ if env is None else env
    module_path = module_path or __file__

    if env.get("APPIMAGE") or env.get("APPDIR"):
        return "appimage"
    if not frozen and _inside_source_checkout(module_path):
        return "source"
    if platform_name == "win32":
        if _has_windows_package_identity():
            return "store"
        installed = _windows_installer_channel()
        if installed:
            return installed
        if frozen:
            return "portable"
    if platform_name == "darwin" and frozen:
        return "mac-dmg"
    if platform_name.startswith("linux") and frozen:
        return "deb"
    return "pip"


def build_update_plan(channel=None, release_url=None):
    channel = channel or detect_install_channel()
    release_url = release_url or f"https://github.com/{GITHUB_REPO}/releases/latest"
    if channel == "store":
        return UpdatePlan(
            channel, "Microsoft Store",
            "The Store installs signed updates and keeps them current automatically.",
            "store", "Open Store updates",
            copy_text=f"ms-windows-store://pdp/?ProductId={STORE_PRODUCT_ID}",
        )
    if channel in ("winget", "setup"):
        return UpdatePlan(
            channel,
            "Windows Package Manager" if channel == "winget" else "Windows installer",
            "Windows Package Manager verifies the installer and handles the upgrade.",
            "run", "Update with winget",
            command=(
                "winget", "upgrade", "--id", WINGET_PACKAGE_ID, "--exact",
                "--accept-source-agreements", "--accept-package-agreements",
            ),
        )
    if channel == "pip":
        return UpdatePlan(
            channel, "Python package",
            "pip will update this Python environment. Restart the app afterward.",
            "run", "Update with pip",
            command=(sys.executable, "-m", "pip", "install", "--upgrade", "videokidnapper"),
        )
    if channel == "deb":
        command = "sudo apt-get update && sudo apt-get install --only-upgrade videokidnapper"
        return UpdatePlan(
            channel, "Linux package",
            "Use the configured APT repository so your package manager can verify the update.",
            "copy", "Copy update command", copy_text=command,
        )
    if channel == "source":
        return UpdatePlan(
            channel, "Source checkout",
            "Review the release, then update the checkout with Git when local changes are safe.",
            "release", "Open verified release", copy_text=release_url,
        )
    labels = {
        "appimage": "Linux AppImage",
        "mac-dmg": "macOS app",
        "portable": "Portable Windows app",
    }
    return UpdatePlan(
        channel, labels.get(channel, "Manual install"),
        "Download the matching release package, then replace or reinstall the app.",
        "release", "Open verified release", copy_text=release_url,
    )


def _normalize(version):
    """Turn 'v1.2.3' or '1.2.3-beta' into a comparable tuple of ints."""
    m = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?", str(version))
    if not m:
        return (0, 0, 0)
    return tuple(int(x) if x else 0 for x in m.groups())


def is_newer(latest, current):
    return _normalize(latest) > _normalize(current)


def fetch_latest(repo=GITHUB_REPO):
    """Synchronous fetch. Returns ``(tag_name, html_url)`` or ``None``."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        req = urllib.request.Request(
            url, headers={"Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            data = json.load(resp)
        tag = data.get("tag_name")
        link = data.get("html_url")
        if tag and link:
            return (tag, link)
    except Exception:
        return None
    return None


def check_async(current_version, on_update_available, repo=GITHUB_REPO):
    """Run ``fetch_latest`` in a thread; call callback only when newer.

    ``on_update_available(latest_tag, html_url)`` runs on the background
    thread — callers must marshal back to the UI thread themselves.
    """

    def worker():
        result = fetch_latest(repo)
        if not result:
            return
        tag, link = result
        if is_newer(tag, current_version):
            try:
                on_update_available(tag, link)
            except Exception:
                pass

    threading.Thread(target=worker, daemon=True).start()
