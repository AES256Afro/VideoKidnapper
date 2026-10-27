# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The update offer lives in the banner and carries through to the install.

Runs on the banner's widget-free queue with a stand-in app, so nothing is
drawn and nothing is downloaded or installed.
"""

import threading
from types import SimpleNamespace

import pytest

from videokidnapper.ui import update_prompt as up
from videokidnapper.ui.studio.banner import PromptQueue
from videokidnapper.utils import self_update
from videokidnapper.utils.github_update import build_update_plan

URL = "https://example.test/releases/v1.9.2"


class _App:
    """Runs ``after`` callbacks synchronously, in order, on demand."""

    def __init__(self):
        self.banner = PromptQueue()
        self.timers = []
        self.clipboard = ""
        self.installs = []

    def after(self, _ms, fn, *args):
        self.timers.append((fn, args))

    def run_timers(self, limit=500):
        for _ in range(limit):
            if not self.timers:
                return
            fn, args = self.timers.pop(0)
            fn(*args)
        raise AssertionError("timers never settled")

    def clipboard_clear(self):
        self.clipboard = ""

    def clipboard_append(self, text):
        self.clipboard += text

    def install_downloaded_update(self, path, channel, on_cancel=None, on_error=None):
        self.installs.append((path, channel, on_cancel, on_error))


def _prompt(app, channel="setup"):
    return up.UpdatePrompt(app, "1.9.1", "v1.9.2", URL,
                           plan=build_update_plan(channel, URL, platform_name="win32",
                                                  frozen=True))


def _labels(prompt):
    return [b.label for b in prompt.buttons]


@pytest.fixture
def release(monkeypatch, tmp_path):
    """A release whose download finishes at once, into tmp_path."""
    asset = self_update.Asset("VideoKidnapper-Setup-1.9.2.exe", 10, "https://x", "0" * 64)
    monkeypatch.setattr(self_update, "fetch_release", lambda: self_update.Release(
        "v1.9.2", URL, [asset]))
    monkeypatch.setattr(self_update, "pick_asset", lambda release, channel: asset)
    gate = threading.Event()
    gate.set()

    def download(asset, progress=None, cancel=None, **_kw):
        progress(5, 10)
        gate.wait(5)
        if cancel is not None and cancel.is_set():
            raise self_update.UpdateCancelled()
        progress(10, 10)
        path = tmp_path / asset.name
        path.write_bytes(b"x" * 10)
        return path

    monkeypatch.setattr(self_update, "download", download)
    return SimpleNamespace(gate=gate, path=tmp_path / asset.name)


def _wait_for_worker(app):
    # The worker thread sets "finished"; poll timers until the prompt moves on.
    import time
    end = time.monotonic() + 5
    while time.monotonic() < end:
        if app.timers:
            fn, args = app.timers.pop(0)
            fn(*args)
        else:
            time.sleep(0.01)
        if app.installs or (app.banner.current and "Downloading" not in app.banner.current.message):
            return
    raise AssertionError("the download never finished")


def test_windows_install_offers_restart_to_update():
    app = _App()
    _prompt(app).show()
    shown = app.banner.current
    assert shown.message == "VideoKidnapper v1.9.2 is available"
    assert _labels(shown) == ["Restart to update", "What's new", "Later"]
    assert shown.dismissable


def test_restart_to_update_downloads_with_progress_then_installs(release):
    app = _App()
    offer = _prompt(app)
    offer.show()
    app.banner.current.press("Restart to update")
    assert app.banner.current.message.startswith("Downloading")
    assert app.banner.current.progress == 0.0
    assert _labels(app.banner.current) == ["Cancel"]
    _wait_for_worker(app)
    (path, channel, on_cancel, on_error), = app.installs
    assert path == release.path and channel == "setup"
    # It stepped aside so the save question can be asked in the banner.
    assert app.banner.current is None


def test_keeping_the_app_open_leaves_the_download_ready(release):
    app = _App()
    offer = _prompt(app)
    offer.show()
    app.banner.current.press("Restart to update")
    _wait_for_worker(app)
    _path, _channel, on_cancel, _on_error = app.installs[0]
    on_cancel()   # the user chose Cancel at "Save your project before updating?"
    assert app.banner.current.message == "VideoKidnapper v1.9.2 is downloaded"
    # Asking again later reuses the download instead of fetching it again.
    app.banner.current.press("Later")
    offer.show()
    app.banner.current.press("Restart to update")
    assert len(app.installs) == 2 and app.installs[1][0] == release.path


def test_an_installer_that_will_not_start_is_reported(release):
    app = _App()
    offer = _prompt(app)
    offer.show()
    app.banner.current.press("Restart to update")
    _wait_for_worker(app)
    app.installs[0][3]("Access is denied")
    assert app.banner.current.message == "The update couldn't start"
    assert app.banner.current.detail == "Access is denied"
    assert app.banner.current.tone == "warn"


def test_cancel_stops_the_download(release):
    app = _App()
    offer = _prompt(app)
    offer.show()
    release.gate.clear()
    app.banner.current.press("Restart to update")
    app.banner.current.press("Cancel")
    release.gate.set()
    _wait_for_worker(app)
    assert app.installs == []
    assert app.banner.current.message == "Download cancelled"
    assert "Try again" in _labels(app.banner.current)


def test_offline_shows_why_and_offers_a_retry(monkeypatch):
    monkeypatch.setattr(self_update, "fetch_release", lambda: None)
    app = _App()
    _prompt(app).show()
    app.banner.current.press("Restart to update")
    _wait_for_worker(app)
    assert app.banner.current.message == "The update didn't download"
    assert "Couldn't reach GitHub" in app.banner.current.detail


def test_store_and_release_routes_stay_in_the_banner():
    app = _App()
    _prompt(app, "store").show()
    assert _labels(app.banner.current) == ["Open the Store", "Later"]
    app = _App()
    plan = build_update_plan("setup", URL, platform_name="win32", frozen=False)
    offer = up.UpdatePrompt(app, "1.9.1", "v1.9.2", URL, plan=plan)
    offer.show()
    assert _labels(app.banner.current) == ["Download", "Copy link", "Later"]
    app.banner.current.press("Copy link")
    assert app.clipboard == URL
    assert app.banner.current.detail == "Release link copied."


def test_no_update_window_is_left():
    import importlib.util
    assert importlib.util.find_spec("videokidnapper.ui.update_dialog") is None


def _app_class():
    from videokidnapper import app as app_module
    return next(obj for obj in vars(app_module).values()
                if isinstance(obj, type) and hasattr(obj, "install_downloaded_update"))


def test_install_goes_through_the_safe_close(monkeypatch, tmp_path):
    """Unsaved work and a running export are asked about first."""
    App = _app_class()
    asked = []
    app = SimpleNamespace(
        close_then=lambda callback, verb, on_cancel: asked.append((callback, verb, on_cancel)),
    )
    App.install_downloaded_update(app, tmp_path / "Setup.exe", "setup", on_cancel="later")
    (callback, verb, on_cancel), = asked
    assert verb == "update" and on_cancel == "later"


def test_installer_that_cannot_start_keeps_the_app_open(monkeypatch, tmp_path):
    App = _app_class()
    destroyed, errors = [], []
    app = SimpleNamespace(
        close_then=lambda callback, verb, on_cancel: callback(),
        destroy=lambda: destroyed.append(True),
    )

    def refuse(path, scope):
        raise OSError("Access is denied")

    monkeypatch.setattr(self_update, "start_setup_install", refuse)
    monkeypatch.setattr("videokidnapper.utils.github_update.installer_scope", lambda: "user")
    App.install_downloaded_update(app, tmp_path / "Setup.exe", "setup",
                                  on_error=errors.append)
    assert errors == ["Couldn't start the update: Access is denied"]
    assert destroyed == []
