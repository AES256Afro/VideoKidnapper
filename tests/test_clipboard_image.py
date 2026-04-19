# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Clipboard-image helper contract.

The helper covers three shapes of clipboard content — bitmap data, a
list of file paths, or nothing — plus the handful of edge cases that
could crash the UI if unguarded (PIL missing, clipboard unreachable,
non-image file paths, disk-write failures). Tests monkeypatch
``PIL.ImageGrab.grabclipboard`` so they don't depend on the host
clipboard state (which is unpredictable in CI).
"""

from pathlib import Path

import pytest

from videokidnapper.utils import clipboard_image


# ---------------------------------------------------------------------------
# Bitmap-data path

class _FakeImage:
    """Stand-in for a PIL Image; records save() calls."""

    def __init__(self, *, raises: bool = False):
        self._raises = raises
        self.saved_to: str | None = None

    def save(self, path, fmt):
        if self._raises:
            raise OSError("simulated write failure")
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal "PNG"
        self.saved_to = str(path)


def _patch_grabclipboard(monkeypatch, return_value):
    from PIL import ImageGrab
    monkeypatch.setattr(ImageGrab, "grabclipboard", lambda: return_value)


def test_bitmap_saves_to_temp_dir(tmp_path, monkeypatch):
    fake = _FakeImage()
    _patch_grabclipboard(monkeypatch, fake)
    result = clipboard_image.grab_clipboard_image(temp_dir=tmp_path)
    assert result is not None
    assert result.exists()
    assert result.suffix == ".png"
    assert result.parent == tmp_path
    assert fake.saved_to == str(result)


def test_bitmap_save_failure_returns_none_and_cleans_up(tmp_path, monkeypatch):
    _patch_grabclipboard(monkeypatch, _FakeImage(raises=True))
    result = clipboard_image.grab_clipboard_image(temp_dir=tmp_path)
    assert result is None
    # The mkstemp file must not be left behind when save() raises.
    leftovers = list(tmp_path.glob("vk_clip_*.png"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# File-path-list path (Explorer / Finder "Copy")

def test_file_list_returns_first_supported(tmp_path, monkeypatch):
    img = tmp_path / "real.png"
    img.write_bytes(b"x")
    txt = tmp_path / "note.txt"
    txt.write_text("hi")
    _patch_grabclipboard(monkeypatch, [str(txt), str(img)])

    result = clipboard_image.grab_clipboard_image(temp_dir=tmp_path)
    assert result == img


def test_file_list_skips_missing_files(tmp_path, monkeypatch):
    img = tmp_path / "missing.png"   # NOT created on disk
    _patch_grabclipboard(monkeypatch, [str(img)])
    result = clipboard_image.grab_clipboard_image(temp_dir=tmp_path)
    assert result is None


def test_file_list_accepts_gif(tmp_path, monkeypatch):
    gif = tmp_path / "anim.gif"
    gif.write_bytes(b"GIF89a")
    _patch_grabclipboard(monkeypatch, [str(gif)])
    result = clipboard_image.grab_clipboard_image(temp_dir=tmp_path)
    assert result == gif


def test_file_list_ignores_non_string_entries(tmp_path, monkeypatch):
    # Some ImageGrab backends can return bytes / other types mixed in;
    # we should skip them rather than raise.
    img = tmp_path / "ok.png"
    img.write_bytes(b"x")
    _patch_grabclipboard(monkeypatch, [b"bytes-entry", None, 42, str(img)])
    result = clipboard_image.grab_clipboard_image(temp_dir=tmp_path)
    assert result == img


def test_file_list_unsupported_extensions(tmp_path, monkeypatch):
    exe = tmp_path / "installer.exe"
    exe.write_bytes(b"MZ")
    _patch_grabclipboard(monkeypatch, [str(exe)])
    result = clipboard_image.grab_clipboard_image(temp_dir=tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# Empty / failure paths

def test_none_clipboard_returns_none(tmp_path, monkeypatch):
    _patch_grabclipboard(monkeypatch, None)
    assert clipboard_image.grab_clipboard_image(temp_dir=tmp_path) is None


def test_grabclipboard_raises_returns_none(tmp_path, monkeypatch):
    # Linux without xclip / wl-paste raises; must not propagate.
    from PIL import ImageGrab
    def _raise():
        raise OSError("xclip not found")
    monkeypatch.setattr(ImageGrab, "grabclipboard", _raise)
    assert clipboard_image.grab_clipboard_image(temp_dir=tmp_path) is None


def test_default_temp_dir_is_app_dir(monkeypatch, tmp_path):
    # When temp_dir is omitted, the helper uses the app's ~/.videokidnapper_temp.
    # We redirect HOME to tmp_path so the test doesn't pollute the real home.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    # PIL must see the redirect too — Path.home() reads USERPROFILE on win.
    fake = _FakeImage()
    _patch_grabclipboard(monkeypatch, fake)
    result = clipboard_image.grab_clipboard_image()
    assert result is not None
    # Parent dir name matches the app's convention.
    assert result.parent.name == ".videokidnapper_temp"


# ---------------------------------------------------------------------------
# Supported-extensions registry

@pytest.mark.parametrize("ext, expected", [
    (".png",  True),
    (".PNG",  False),   # Membership is on lowercased extensions — caller
                         # lowercases before lookup via suffix.lower().
    (".jpg",  True),
    (".jpeg", True),
    (".webp", True),
    (".gif",  True),
    (".bmp",  True),
    (".tiff", False),
    (".mp4",  False),
])
def test_supported_image_exts_membership(ext, expected):
    assert (ext in clipboard_image.SUPPORTED_IMAGE_EXTS) is expected
