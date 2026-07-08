#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Capture screenshots of VideoKidnapper states for the README + stores.

Launches the app in various configurations, snapshots the window via
``PIL.ImageGrab``, and writes the PNGs under ``assets/screenshots/``.

Local/dev use only. Set VK_DEMO_VIDEO to point at a clip; otherwise this
synthesizes a colourful Mandelbrot render (reads as real content, not
test bars) into the scratch dir on first run.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHOTS_DIR = ROOT / "assets" / "screenshots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

DEMO_VIDEO = Path(os.environ.get(
    "VK_DEMO_VIDEO", str(ROOT / "build" / "demo-clip.mp4")))

STUDIO = "  ⬇  Kidnap & Trim  "
HISTORY = "  ⌛  History  "
DEBUG = "  ⚙  Debug  "


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
        "-f", "lavfi", "-i", "sine=frequency=220:duration=6",
        "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(DEMO_VIDEO),
    ], check=True)
    return True


def grab(window, out_name):
    from PIL import ImageGrab
    window.update()
    window.update_idletasks()
    try:
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()
    except Exception:
        pass
    window.update()
    time.sleep(0.5)
    x, y = window.winfo_rootx(), window.winfo_rooty()
    w, h = window.winfo_width(), window.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(SHOTS_DIR / out_name, "PNG")


def shot_studio_empty():
    from videokidnapper.app import App
    app = App()
    app.geometry("1280x860")
    app.update()
    grab(app, "studio_empty.png")
    app.destroy()


def shot_studio_loaded():
    from videokidnapper.app import App
    app = App()
    app.geometry("1280x900")
    app.tabview.set(STUDIO)
    app.update()

    trim = app.trim_tab
    trim._load_path(str(DEMO_VIDEO))
    app.update()
    trim.range_slider.set_values(1.2, 4.5)
    trim._on_slider_change(1.2, 4.5)
    trim._queue_range()
    trim.range_slider.set_values(4.6, 5.8)
    trim._on_slider_change(4.6, 5.8)
    trim._queue_range()

    if hasattr(trim.export_options, "_toggle"):
        trim.export_options._toggle()
    trim.text_layers._add_layer()
    if trim.text_layers.layers:
        layer = trim.text_layers.layers[0]
        if hasattr(layer, "text_box"):
            layer.text_box.insert("1.0", "POV: you found the\nperfect clip")
    trim.player.refresh_overlay()
    app.update()
    grab(app, "studio_loaded.png")
    app.destroy()


def shot_studio_link():
    """The 'from a link' path — batch queue open, platform chips live."""
    from videokidnapper.app import App
    app = App()
    app.geometry("1280x900")
    app.tabview.set(STUDIO)
    app.update()
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
    app.update()
    grab(app, "studio_link.png")
    app.destroy()


def shot_history():
    from videokidnapper.app import App
    from videokidnapper.utils import settings
    settings.set("history", [
        {"path": str(DEMO_VIDEO.with_name("VidKid_trim_20260707_221530.mp4")),
         "format": "MP4", "preset": "High", "timestamp": "2026-07-07 22:15",
         "size_bytes": 4_850_000, "mode": "trim"},
        {"path": str(DEMO_VIDEO.with_name("VidKid_url_20260707_203901.gif")),
         "format": "GIF", "preset": "Medium", "timestamp": "2026-07-07 20:39",
         "size_bytes": 1_240_000, "mode": "url"},
        {"path": str(DEMO_VIDEO.with_name("VidKid_trim_20260706_140112.mp4")),
         "format": "MP4", "preset": "Ultra", "timestamp": "2026-07-06 14:01",
         "size_bytes": 18_900_000, "mode": "trim"},
    ])
    app = App()
    app.geometry("1280x720")
    app.tabview.set(HISTORY)
    app.update()
    grab(app, "history.png")
    app.destroy()
    settings.set("history", [])


def shot_setup_dialog():
    from videokidnapper.app import App
    from videokidnapper.ui.setup_dialog import SetupDialog
    app = App()
    app.geometry("1280x720")
    app.update()
    dlg = SetupDialog(app, on_relaunch=app._restart_app)
    dlg.geometry("+120+120")
    dlg.update()
    time.sleep(0.3)
    grab(dlg, "setup.png")
    dlg.destroy()
    app.destroy()


def main():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    if not ensure_demo():
        return 1
    shots = [
        ("studio_empty",  shot_studio_empty),
        ("studio_loaded", shot_studio_loaded),
        ("studio_link",   shot_studio_link),
        ("history",       shot_history),
        ("setup",         shot_setup_dialog),
    ]
    for name, fn in shots:
        print(f"{name}:")
        try:
            fn()
        except Exception as e:
            print(f"  FAILED — {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
