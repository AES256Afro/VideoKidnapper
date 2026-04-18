#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Record an animated demo GIF of the app for the README banner.

Drives the app through a short tour — loads the demo video, scrubs, queues
ranges, toggles crop, flips to the URL tab, shows the platform chips — while
``mss`` captures the window at ~10fps. The frame sequence is then encoded
into a ~5-second GIF with ffmpeg.

Intended for local use. Not imported at runtime.

Usage:
    # 1. Create a demo clip if you don't have one already:
    ffmpeg -y -f lavfi -i "testsrc=duration=6:size=1280x720:rate=24" \\
           -f lavfi -i "sine=frequency=440:duration=6" \\
           -c:v libx264 -c:a aac -pix_fmt yuv420p /tmp/vkshots/demo.mp4

    # 2. Run the recorder:
    VK_DEMO_VIDEO=/tmp/vkshots/demo.mp4 python scripts/record_demo.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT = ROOT / "assets" / "screenshots" / "demo.gif"
DEMO_VIDEO = Path(os.environ.get(
    "VK_DEMO_VIDEO", Path(tempfile.gettempdir()) / "vkshots" / "demo.mp4",
))

FPS = 10
DURATION_S = 8
FRAME_COUNT = FPS * DURATION_S


def capture_window_frames(app, out_dir):
    """Capture `FRAME_COUNT` frames of the app window into `out_dir`."""
    import mss
    import mss.tools

    with mss.mss() as sct:
        interval = 1.0 / FPS
        start = time.time()
        for i in range(FRAME_COUNT):
            bbox = {
                "left":   app.winfo_rootx(),
                "top":    app.winfo_rooty(),
                "width":  app.winfo_width(),
                "height": app.winfo_height(),
            }
            shot = sct.grab(bbox)
            mss.tools.to_png(
                shot.rgb, shot.size,
                output=str(out_dir / f"frame_{i:04d}.png"),
            )
            # Sleep to hit the target frame pace.
            target = start + (i + 1) * interval
            remaining = target - time.time()
            if remaining > 0:
                time.sleep(remaining)


def drive_app(app):
    """Script the app through a short tour in lockstep with capture."""
    time.sleep(0.4)  # let the first frames capture the empty Trim tab

    trim = app.trim_tab
    trim._load_path(str(DEMO_VIDEO))
    time.sleep(0.6)

    # Scrub to the middle
    trim.range_slider.set_values(2.0, 4.5)
    trim._on_slider_change(2.0, 4.5)
    time.sleep(0.6)

    # Queue the range
    trim._queue_range()
    time.sleep(0.5)

    # Add a text layer with sample text
    trim.text_layers._add_layer()
    if trim.text_layers.layers:
        trim.text_layers.layers[0].text_var.set("Demo clip")
        trim.player.refresh_overlay()
    time.sleep(0.8)

    # Flip to URL Download tab
    app.tabview.set("  ↓  URL Download  ")
    time.sleep(0.6)
    url = app.url_tab
    url.url_entry.delete(0, "end")
    url.url_entry.insert(0, "https://youtu.be/dQw4w9WgXcQ")
    url._on_url_typed()
    time.sleep(0.8)

    # History tab
    app.tabview.set("  ⌛  History  ")
    time.sleep(0.6)


def encode_gif(frame_dir, output, ffmpeg):
    """Convert the PNG sequence to a palette-optimised GIF."""
    palette = frame_dir / "palette.png"

    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%04d.png"),
        "-vf", "scale=900:-2:flags=lanczos,palettegen=max_colors=128",
        str(palette),
    ], check=True)

    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS),
        "-i", str(frame_dir / "frame_%04d.png"),
        "-i", str(palette),
        "-lavfi",
        "scale=900:-2:flags=lanczos [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
        "-loop", "0",
        str(output),
    ], check=True)


def main():
    if not DEMO_VIDEO.exists():
        print(f"Demo video not found at {DEMO_VIDEO}.")
        print("Create one with:")
        print('  ffmpeg -y -f lavfi -i "testsrc=duration=6:size=1280x720:rate=24" \\')
        print('         -f lavfi -i "sine=frequency=440:duration=6" \\')
        print('         -c:v libx264 -c:a aac -pix_fmt yuv420p /tmp/vkshots/demo.mp4')
        return 1

    from videokidnapper.app import App
    from videokidnapper.utils.ffmpeg_check import find_ffmpeg

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("FFmpeg not found — open the Setup dialog inside the app first.")
        return 1
    ffmpeg = str(ffmpeg)

    frame_dir = Path(tempfile.mkdtemp(prefix="vkdemo_"))
    try:
        app = App()
        app.geometry("1100x780")
        app.update()
        try:
            app.attributes("-topmost", True)
            app.lift()
            app.focus_force()
        except Exception:
            pass
        app.update()
        time.sleep(0.3)

        # Drive + capture in parallel — the driver issues Tk changes on the
        # main thread while capture runs in a worker with its own mss loop.
        def worker():
            capture_window_frames(app, frame_dir)
            app.after(0, app.destroy)

        capture_thread = threading.Thread(target=worker, daemon=True)
        capture_thread.start()

        # The drive script runs on the main thread using a dispatch loop so
        # Tk stays responsive while capture threads run.
        driver = threading.Thread(target=lambda: drive_app(app), daemon=True)
        driver.start()

        app.mainloop()
        capture_thread.join(timeout=2)

        print(f"→ Captured {FRAME_COUNT} frames, encoding GIF...")
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        encode_gif(frame_dir, OUTPUT, ffmpeg)
        print(f"✓ Wrote {OUTPUT}")
    finally:
        shutil.rmtree(frame_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
