#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Capture screenshots of VideoKidnapper states for the README.

Launches the app in various configurations, snapshots the window via
``PIL.ImageGrab``, and writes the PNGs under ``assets/screenshots/``.

Intended for local use only — not packaged with the app.
"""

import os
import sys
import time
from pathlib import Path

# Ensure we can import the package even when run from scripts/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SHOTS_DIR = ROOT / "assets" / "screenshots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)

DEMO_VIDEO = Path(os.environ.get("VK_DEMO_VIDEO", "/tmp/vkshots/demo.mp4"))


def grab(window, out_name):
    """Snap the window's rectangle and save.

    Forces the target window above anything else on screen so ImageGrab
    (which reads screen pixels) doesn't capture whatever game or terminal
    happens to be behind it.
    """
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
    time.sleep(0.5)  # give the compositor time to bring it forward

    x = window.winfo_rootx()
    y = window.winfo_rooty()
    w = window.winfo_width()
    h = window.winfo_height()
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    out = SHOTS_DIR / out_name
    img.save(out, "PNG")
    print(f"  wrote {out} ({img.size[0]}x{img.size[1]})")


def shot_trim_empty():
    from videokidnapper.app import App
    app = App()
    app.geometry("1100x820")
    app.tabview.set("  ✂  Trim Video  ")
    app.update()
    grab(app, "trim_empty.png")
    app.destroy()


def shot_trim_loaded():
    """Trim tab with video, range queued, text layer added, options open."""
    from videokidnapper.app import App
    app = App()
    app.geometry("1100x1100")
    app.tabview.set("  ✂  Trim Video  ")
    app.update()

    trim = app.trim_tab
    trim._load_path(str(DEMO_VIDEO))
    app.update()

    # Mid-clip preview
    trim.range_slider.set_values(1.2, 4.5)
    trim._on_slider_change(1.2, 4.5)
    app.update()
    time.sleep(0.3)

    # Queue that range
    trim._queue_range()
    # Queue a second
    trim.range_slider.set_values(4.6, 5.8)
    trim._on_slider_change(4.6, 5.8)
    trim._queue_range()
    app.update()

    # Expand export options so the screenshot shows the new knobs.
    if hasattr(trim.export_options, "_toggle"):
        trim.export_options._toggle()
        app.update()

    # Add a text layer so the collapsible opens with content.
    trim.text_layers._add_layer()
    if trim.text_layers.layers:
        layer = trim.text_layers.layers[0]
        layer.text_var.set("Hello VideoKidnapper")
    trim.player.refresh_overlay()
    app.update()

    grab(app, "trim_loaded.png")
    app.destroy()


def shot_url_tab():
    from videokidnapper.app import App
    app = App()
    app.geometry("1100x820")
    app.tabview.set("  ↓  URL Download  ")
    app.update()

    url = app.url_tab
    url.url_entry.delete(0, "end")
    url.url_entry.insert(0, "https://youtu.be/dQw4w9WgXcQ")
    url._on_url_typed()
    app.update()

    grab(app, "url_download.png")
    app.destroy()


def shot_url_batch():
    from videokidnapper.app import App
    app = App()
    app.geometry("1100x820")
    app.tabview.set("  ↓  URL Download  ")
    app.update()

    url = app.url_tab
    if hasattr(url.batch, "_toggle"):
        url.batch._toggle()
    url.batch.url_text.insert(
        "1.0",
        "https://youtu.be/dQw4w9WgXcQ\n"
        "https://www.instagram.com/reel/C1abcd/\n"
        "https://bsky.app/profile/alice.bsky.social/post/x\n"
        "https://www.reddit.com/r/videos/comments/abc/title/\n"
        "https://x.com/user/status/12345\n"
        "https://www.facebook.com/watch?v=999",
    )
    app.update()
    grab(app, "url_batch.png")
    app.destroy()


def shot_history_tab():
    from videokidnapper.app import App
    from videokidnapper.utils import settings
    # Seed history with a few realistic entries just for the screenshot.
    settings.set("history", [
        {"path": str(DEMO_VIDEO.with_name("VidKid_trim_20260417_221530.mp4")),
         "format": "MP4", "preset": "High", "timestamp": "2026-04-17 22:15",
         "size_bytes": 4_850_000, "mode": "trim"},
        {"path": str(DEMO_VIDEO.with_name("VidKid_url_20260417_203901.gif")),
         "format": "GIF", "preset": "Medium", "timestamp": "2026-04-17 20:39",
         "size_bytes": 1_240_000, "mode": "url"},
        {"path": str(DEMO_VIDEO.with_name("VidKid_trim_20260416_140112.mp4")),
         "format": "MP4", "preset": "Ultra", "timestamp": "2026-04-16 14:01",
         "size_bytes": 18_900_000, "mode": "trim"},
    ])
    app = App()
    app.geometry("1100x680")
    app.tabview.set("  ⌛  History  ")
    app.update()
    grab(app, "history.png")
    app.destroy()
    settings.set("history", [])  # restore


def shot_debug_tab():
    from videokidnapper.app import App
    app = App()
    app.geometry("1100x680")
    app.tabview.set("  ⚙  Debug  ")
    app.update()

    # Emit some multi-level log entries.
    app.debug_tab.add_log("URL detected: YouTube", "INFO")
    app.debug_tab.add_log("Downloading best video+audio...", "INFO")
    app.debug_tab.add_log("Instagram cookies needed for this reel", "WARN")
    app.debug_tab.add_log("ffmpeg failed (rc=1): invalid filter chain", "ERROR")
    app.debug_tab.add_log("Exported to VidKid_trim_20260417_221530.mp4", "INFO")
    app.update()
    grab(app, "debug.png")
    app.destroy()


def shot_setup_dialog():
    from videokidnapper.app import App
    from videokidnapper.ui.setup_dialog import SetupDialog
    app = App()
    app.geometry("1100x640")
    app.update()
    dlg = SetupDialog(app)
    dlg.geometry("+120+120")
    dlg.update()
    time.sleep(0.3)
    grab(dlg, "setup.png")
    dlg.destroy()
    app.destroy()


def main():
    if not DEMO_VIDEO.exists():
        print(f"Demo video not found at {DEMO_VIDEO}. Generate one with:")
        print('  ffmpeg -y -f lavfi -i "testsrc=duration=6:size=1280x720:rate=24" \\')
        print('         -f lavfi -i "sine=frequency=440:duration=6" \\')
        print('         -c:v libx264 -c:a aac -pix_fmt yuv420p /tmp/vkshots/demo.mp4')
        return 1

    shots = [
        ("trim_empty",   shot_trim_empty),
        ("trim_loaded",  shot_trim_loaded),
        ("url_download", shot_url_tab),
        ("url_batch",    shot_url_batch),
        ("history",      shot_history_tab),
        ("debug",        shot_debug_tab),
        ("setup",        shot_setup_dialog),
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
