#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Record the animated tour at the top of the README and the website.

Walks the Studio layout through the app's core loop: paste a link in
Import, mark a range on the Edit timeline, type a caption, reframe for
9:16 with a blurred fill, and land on the Export page. Each step holds for
a fixed number of frames, and every frame is grabbed straight from the
window, so the GIF's timing is exact no matter how fast the machine is.

Runs with a throwaway settings file like capture_screenshots.py, so real
settings, autosave and recent projects are never touched.

Local use only (Windows renders the real fonts). Set VK_DEMO_VIDEO to a
clip; otherwise capture_screenshots.py's Mandelbrot demo is synthesized.

    python scripts/record_demo.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from capture_screenshots import (  # noqa: E402
    DEMO_VIDEO, _DISPLAY_FOLDER, _window_bounds, ensure_demo,
    wait_for_editor_assets,
)

OUTPUT = ROOT / "assets" / "screenshots" / "demo.gif"
WINDOW = "1280x800+40+40"
FPS = 10
GIF_WIDTH = 960


class Recorder:
    """Grab one frame per tick; steps decide how many ticks they hold."""

    def __init__(self, app, frame_dir):
        self.app = app
        self.frame_dir = frame_dir
        self.count = 0
        self.bbox = None

    def frame(self):
        from PIL import ImageGrab
        self.app.update()
        if self.bbox is None:
            self.bbox = _window_bounds(self.app)
        ImageGrab.grab(bbox=self.bbox, all_screens=True).save(
            self.frame_dir / f"frame_{self.count:04d}.png")
        self.count += 1

    def hold(self, frames):
        for _ in range(frames):
            self.frame()

    def animate(self, frames, fn):
        """Call ``fn(progress)`` with progress 0→1, one frame each."""
        for i in range(1, frames + 1):
            fn(i / frames)
            self.frame()


def tour(app, rec):
    editor = app.trim_tab

    # 1. Import: a link goes in and the platform chip lights up.
    app.show_workspace("import")
    rec.hold(8)
    bar = editor.download_bar
    url = "https://youtu.be/dQw4w9WgXcQ"
    bar.url_entry.focus_set()

    def type_url(p):
        bar.url_entry.delete(0, "end")
        bar.url_entry.insert(0, url[:max(1, round(len(url) * p))])
        bar._on_url_typed()
    rec.animate(8, type_url)
    rec.hold(8)

    # 2. The clip lands in Edit.
    editor._load_path(str(DEMO_VIDEO))
    wait_for_editor_assets(app, editor)
    editor.inspector.show("clip")
    rec.hold(8)

    # 3. Sweep the playhead and mark a range (I at 1.2 s, O at 4.5 s),
    #    save it with Q, then mark a second part to export alongside it.
    rec.animate(8, lambda p: editor._seek(1.2 * p))
    editor.keyboard_mark_in()
    rec.hold(3)
    rec.animate(12, lambda p: editor._seek(1.2 + 3.3 * p))
    editor.keyboard_mark_out()
    rec.hold(4)
    editor.keyboard_save_range()
    rec.hold(5)
    rec.animate(3, lambda p: editor._seek(4.5 + 0.3 * p))
    editor.keyboard_mark_in()
    rec.animate(6, lambda p: editor._seek(4.8 + 1.0 * p))
    editor.keyboard_mark_out()
    rec.hold(4)

    # 4. A caption, typed into the Text inspector.
    editor._seek(2.0)
    editor.add_text_layer()
    page = editor.inspector.pages["text"]
    caption = "POV: you found the\nperfect clip"

    def type_caption(p):
        page.textbox.delete("1.0", "end")
        page.textbox.insert("1.0", caption[:max(1, round(len(caption) * p))])
        page._text_changed()
    rec.animate(14, type_caption)
    rec.animate(6, lambda p: editor._seek(2.0 + 0.8 * p))
    rec.hold(6)

    # 5. A touch of color: the preview shows exactly what exports.
    editor.inspector.show("color")
    rec.hold(3)
    rec.animate(8, lambda p: editor.options.saturation_var.set(round(1.0 + 0.35 * p, 3)))
    rec.hold(6)

    # 6. Reframe for Shorts: 9:16 with a blurred fill.
    editor.inspector.show("clip")
    rec.hold(4)
    editor.options.set_aspect("9:16")
    rec.hold(6)
    editor.options.aspect_fill_var.set("Blur fill")
    rec.hold(12)

    # 7. Export: every setting on one page, a summary, one button.
    app.show_workspace("export")
    rec.hold(10)
    editor._apply_platform_preset("TikTok")
    rec.hold(18)


def encode_gif(frame_dir, output, ffmpeg):
    """PNG sequence → palette-optimised looping GIF."""
    scale = f"scale={GIF_WIDTH}:-2:flags=lanczos"
    palette = frame_dir / "palette.png"
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS), "-i", str(frame_dir / "frame_%04d.png"),
        "-vf", f"{scale},palettegen=max_colors=128:stats_mode=diff",
        str(palette),
    ], check=True)
    subprocess.run([
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-framerate", str(FPS), "-i", str(frame_dir / "frame_%04d.png"),
        "-i", str(palette),
        "-lavfi", f"{scale} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
        "-loop", "0", str(output),
    ], check=True)


def main():
    if not ensure_demo():
        return 1
    from videokidnapper.utils import settings
    from videokidnapper.utils.ffmpeg_check import find_ffmpeg

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("FFmpeg not found. Open Setup inside the app first.")
        return 1

    frame_dir = Path(tempfile.mkdtemp(prefix="vkdemo_"))
    with tempfile.TemporaryDirectory(prefix="vk-demo-settings-") as temp:
        settings._SETTINGS_PATH = Path(temp) / "settings.json"
        settings.update({
            "onboarding_complete": True,
            "auto_update_check": False,
            "theme": os.environ.get("VK_SCREENSHOT_THEME", "light"),
            "output_folder": _DISPLAY_FOLDER,
        })
        from videokidnapper.app import App
        try:
            app = App()
            app.geometry(WINDOW)
            app.update()
            try:
                app.attributes("-topmost", True)
                app.lift()
                app.focus_force()
            except Exception:
                pass
            time.sleep(0.3)
            rec = Recorder(app, frame_dir)
            tour(app, rec)
            app.destroy()
            print(f"Captured {rec.count} frames ({rec.count / FPS:.1f} s), encoding GIF...")
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            encode_gif(frame_dir, OUTPUT, str(ffmpeg))
            print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size / 1e6:.1f} MB)")
        finally:
            shutil.rmtree(frame_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
