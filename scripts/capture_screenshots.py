#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Capture screenshots of VideoKidnapper states for the README + stores.

Launches the app in various configurations, snapshots the window, and
writes the PNGs under ``assets/screenshots/``. Each shot runs in its own
process with a throwaway settings file, so real settings, autosave and
recent projects are never touched.

Local/dev use only. Set VK_DEMO_VIDEO to point at a clip; otherwise this
synthesizes a colourful Mandelbrot render (reads as real content, not
test bars) into the build dir on first run.

    python scripts/capture_screenshots.py              # every shot
    python scripts/capture_screenshots.py --shot NAME  # just one
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHOTS_DIR = ROOT / "assets" / "screenshots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

DEMO_VIDEO = Path(os.environ.get(
    "VK_DEMO_VIDEO", str(ROOT / "build" / "demo-clip.mp4")))
WINDOW = "1440x900+40+40"
_DISPLAY_FOLDER = (r"C:\Users\you\Videos\Clips" if os.name == "nt"
                   else "/home/you/Videos/Clips")


def ensure_demo():
    """Synthesize a good-looking demo clip if one isn't supplied."""
    if DEMO_VIDEO.exists():
        return True
    from videokidnapper.utils.ffmpeg_check import find_ffmpeg
    ff = find_ffmpeg()
    if not ff:
        print("No ffmpeg found and no VK_DEMO_VIDEO set.")
        return False
    DEMO_VIDEO.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(ff), "-y", "-v", "error",
        "-f", "lavfi", "-i", "mandelbrot=size=1280x720:rate=24",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=8",
        "-t", "8", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(DEMO_VIDEO),
    ], check=True)
    return True


def _window_bounds(window):
    """On-screen bounds of just this window, in physical pixels.

    DWM's extended frame bounds are exact on multi-monitor and scaled
    setups where winfo_root* can be off; other platforms fall back to Tk.
    """
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = int(window.wm_frame(), 16)
            rect = wintypes.RECT()
            ctypes.windll.dwmapi.DwmGetWindowAttribute(
                hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
    x, y = window.winfo_rootx(), window.winfo_rooty()
    return x, y, x + window.winfo_width(), y + window.winfo_height()


def grab(window, out_name):
    from PIL import ImageGrab
    window.update_idletasks()
    try:
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()
    except Exception:
        pass
    window.update()
    time.sleep(0.5)
    window.update()
    ImageGrab.grab(bbox=_window_bounds(window), all_screens=True).save(
        SHOTS_DIR / out_name, "PNG")


def pump(app, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.update()
        time.sleep(0.03)


def wait_for_editor_assets(app, editor, timeout=12.0):
    """Pump Tk until the timeline's filmstrip and waveform finish loading."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.update()
        if not editor.timeline._loading:
            break
        time.sleep(0.1)
    pump(app, 0.3)


def new_app():
    from videokidnapper.app import App
    app = App()
    app.geometry(WINDOW)
    app.update()
    return app


def load_demo(app):
    editor = app.trim_tab
    editor._load_path(str(DEMO_VIDEO))
    wait_for_editor_assets(app, editor)
    return editor


def add_caption(editor, text, start=None):
    if start is not None:
        editor._seek(start)
    layer = editor.add_text_layer()
    page = editor.inspector.pages["text"]
    page.textbox.delete("1.0", "end")
    page.textbox.insert("1.0", text)
    page._text_changed()
    return layer


# ---------------------------------------------------------------------------
# Shots
# ---------------------------------------------------------------------------

def shot_studio_empty():
    """First thing you see: the Import workspace."""
    app = new_app()
    app.show_workspace("import")
    grab(app, "studio_empty.png")
    app.destroy()


def shot_studio_loaded():
    """Edit with saved ranges, a caption and the full timeline."""
    app = new_app()
    editor = load_demo(app)
    editor._apply_selection(1.2, 4.5)
    editor._queue_range()
    editor._apply_selection(4.6, 6.8)
    editor._queue_range()
    editor._apply_selection(1.2, 4.5)
    add_caption(editor, "POV: you found the\nperfect clip", start=2.0)
    editor.inspector.show("clip")
    editor._seek(2.6)
    pump(app, 0.6)
    grab(app, "studio_loaded.png")
    app.destroy()


def shot_text_tools():
    """A multiline caption selected, with the Text inspector open."""
    app = new_app()
    editor = load_demo(app)
    add_caption(editor, "First line\nSecond line\nThird line", start=1.0)
    editor._seek(2.0)
    pump(app, 0.6)
    grab(app, "studio_text.png")
    app.destroy()


def shot_studio_link():
    """Import from a link: platform chips live, batch list open."""
    app = new_app()
    app.show_workspace("import")
    bar = app.trim_tab.download_bar
    bar.receive_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    if hasattr(bar.batch, "_toggle"):
        bar.batch._toggle()
    bar.batch.url_text.insert(
        "1.0",
        "https://youtu.be/dQw4w9WgXcQ\n"
        "https://www.instagram.com/reel/C1abcd/\n"
        "https://bsky.app/profile/alice.bsky.social/post/x\n"
        "https://x.com/user/status/12345",
    )
    pump(app, 0.3)
    grab(app, "studio_link.png")
    app.destroy()


def shot_studio_export():
    """The Export workspace for a clip with two saved ranges."""
    app = new_app()
    editor = load_demo(app)
    editor._apply_selection(1.0, 3.5)
    editor._queue_range()
    editor._apply_selection(4.0, 7.0)
    editor._apply_platform_preset("TikTok")
    app.show_workspace("export")
    pump(app, 0.4)
    grab(app, "studio_export.png")
    app.destroy()


def shot_onboarding():
    """The first-run welcome, over the Import workspace."""
    from videokidnapper.utils import settings
    settings.set("onboarding_complete", False)
    # is_first_run() keys off the settings file not existing yet.
    settings._SETTINGS_PATH.unlink(missing_ok=True)
    app = new_app()
    pump(app, 0.8)
    dialog = app._onboarding_dialog
    dialog.update()
    grab(dialog, "onboarding.png")
    dialog._finish()
    app.destroy()


def shot_history():
    from videokidnapper.utils import settings
    from datetime import datetime, timedelta
    now = datetime.now()
    stamp = lambda d: (now - d).strftime("%Y-%m-%d %H:%M")  # noqa: E731
    settings.set("history", [
        {"path": str(DEMO_VIDEO), "format": "MP4", "preset": "High",
         "timestamp": stamp(timedelta(minutes=12)), "size_bytes": 4_850_000, "mode": "trim"},
        {"path": str(DEMO_VIDEO.with_name("Reaction take 2.gif")),
         "format": "GIF", "preset": "Medium", "timestamp": stamp(timedelta(hours=3)),
         "size_bytes": 1_240_000, "mode": "trim"},
        {"path": str(DEMO_VIDEO.with_name("Interview_20261005.mp4")),
         "format": "MP4", "preset": "Ultra", "timestamp": stamp(timedelta(days=1, hours=2)),
         "size_bytes": 18_900_000, "mode": "trim"},
    ])
    app = new_app()
    app.show_workspace("export")
    app.export_workspace.show("history")
    pump(app, 1.5)
    grab(app, "history.png")
    app.destroy()


def shot_debug():
    app = new_app()
    app.debug_tab.add_log("VideoKidnapper started", "INFO")
    app.debug_tab.add_log("FFmpeg found and verified", "INFO")
    app.show_workspace("log")
    pump(app, 0.3)
    grab(app, "debug.png")
    app.destroy()


def shot_setup_dialog():
    from videokidnapper.ui.setup_dialog import SetupDialog
    app = new_app()
    dlg = SetupDialog(app, on_relaunch=app._restart_app)
    dlg.geometry("+160+120")
    pump(app, 0.4)
    grab(dlg, "setup.png")
    dlg.destroy()
    app.destroy()


def shot_project_dialog():
    """Project save, open, and recent-file hub."""
    from videokidnapper.utils import settings
    app = new_app()
    editor = load_demo(app)
    editor._apply_selection(1.0, 4.0)
    editor._flush_pending_snapshot()
    editor.save_project(target=settings._SETTINGS_PATH.with_name("Summer cut.vidkid"))
    editor._apply_selection(1.5, 3.8)
    editor._request_snapshot(immediate=True)
    editor.open_project_hub()
    dialog = next(
        child for child in app.winfo_children()
        if child.winfo_class() == "Toplevel"
    )
    pump(app, 0.4)
    grab(dialog, "projects.png")
    dialog.destroy()
    app.destroy()


def shot_update_dialog():
    """Update prompt as a Windows Setup install sees it (GitHub release).

    Running from source would otherwise show the source-checkout route.
    """
    from videokidnapper.ui import update_dialog
    from videokidnapper.utils.github_update import build_update_plan
    update_dialog.build_update_plan = (
        lambda release_url=None: build_update_plan("setup", release_url))
    UpdateDialog = update_dialog.UpdateDialog
    app = new_app()
    dialog = UpdateDialog(
        app, "1.9.0", "v1.9.1",
        "https://github.com/AES256Afro/VideoKidnapper/releases/latest",
    )
    dialog.deiconify()
    dialog.wait_visibility()
    dialog.attributes("-topmost", True)
    pump(app, 0.5)
    dialog._center()
    pump(app, 0.3)
    grab(app, "updates.png")
    dialog.destroy()
    app.destroy()


def _shots():
    return {
        "studio_empty": shot_studio_empty,
        "studio_loaded": shot_studio_loaded,
        "studio_text": shot_text_tools,
        "studio_link": shot_studio_link,
        "studio_export": shot_studio_export,
        "onboarding": shot_onboarding,
        "history": shot_history,
        "debug": shot_debug,
        "setup": shot_setup_dialog,
        "projects": shot_project_dialog,
        "updates": shot_update_dialog,
    }


def _capture_one(name):
    from videokidnapper.utils import settings
    fn = _shots().get(name)
    if fn is None:
        print(f"Unknown screenshot: {name}")
        return 2
    with tempfile.TemporaryDirectory(prefix=f"vk-{name}-settings-") as temp:
        settings._SETTINGS_PATH = Path(temp) / "settings.json"
        # Theme is read once when ui.theme is imported, which happens
        # inside fn(); write it before that so the capture matches.
        settings.update({
            "onboarding_complete": True,
            "auto_update_check": False,
            "theme": os.environ.get("VK_SCREENSHOT_THEME")
                     or os.environ.get("VK_THEME", "light"),
            # Shown in the Export shot, so a generic path rather than the
            # temp dir (which carries the capturing user's name). No shot
            # exports anything, so it never has to exist.
            "output_folder": _DISPLAY_FOLDER,
        })
        fn()
    return 0


def main():
    if not ensure_demo():
        return 1
    if len(sys.argv) == 3 and sys.argv[1] == "--shot":
        return _capture_one(sys.argv[2])

    failures = []
    for name in _shots():
        print(f"{name}:", flush=True)
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--shot", name],
            cwd=ROOT,
        )
        if result.returncode:
            failures.append(name)
    if failures:
        print(f"Failed: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
