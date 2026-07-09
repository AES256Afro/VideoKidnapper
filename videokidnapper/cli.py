# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Command-line / GUI entry point.

This module lives inside the package so ``pip install videokidnapper``
can register a console script (``videokidnapper = ...cli:main``) that
users invoke as a plain shell command. The repo-root ``main.py`` stays
around as a thin shim so ``python main.py --url ...`` still works after
a ``git clone``.
"""

import argparse
import sys
from pathlib import Path

# Legacy Windows consoles decode stdout as cp1252, which can't encode
# characters like "→" in progress lines — print() then raises
# UnicodeEncodeError and kills the CLI job (found via the MSIX
# container's attached-pipe console). Degrade to replacement chars
# instead of crashing; harmless everywhere else.
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(errors="replace")
        except Exception:
            pass


def _cli_main(args):
    """Run a single trim/download-and-trim operation without the GUI."""
    from videokidnapper.core.downloader import download_video
    from videokidnapper.core.ffmpeg_backend import (
        get_video_info, trim_to_gif, trim_to_video,
    )
    from videokidnapper.utils.file_naming import generate_export_path

    if not args.url and not args.file:
        print("error: --url or --file is required", file=sys.stderr)
        return 2

    src_path = args.file
    if args.url:
        print(f"Downloading {args.url}...", flush=True)
        result = download_video(args.url)
        if result.get("error"):
            print(f"Download failed: {result['error']}", file=sys.stderr)
            return 1
        src_path = result["path"]

    if not src_path or not Path(src_path).exists():
        print(f"error: file not found: {src_path}", file=sys.stderr)
        return 1

    info = get_video_info(src_path)
    start = args.start if args.start is not None else 0.0
    end = args.end if args.end is not None else info["duration"]

    out = args.out
    if not out:
        ext = "gif" if args.format.upper() == "GIF" else "mp4"
        out = str(generate_export_path("cli", ext))

    options = {
        "speed":         args.speed,
        "rotate":        args.rotate,
        "mute":          args.mute,
        "audio_only":    args.audio_only,
        "aspect_preset": args.aspect,
        "hw_encoder":    args.hw,
        "text_fade":     0.0,
    }

    print(f"Encoding {start}–{end}s → {out} ...", flush=True)

    def progress(p, *a):
        pct = int(p * 100)
        print(f"  {pct:3d}%", end="\r", flush=True)

    if args.format.upper() == "GIF":
        result = trim_to_gif(src_path, start, end, args.quality, out,
                             progress_callback=progress, options=options)
    else:
        result = trim_to_video(src_path, start, end, args.quality, out,
                               progress_callback=progress, options=options)
    print()
    if not result:
        print("error: encoding failed", file=sys.stderr)
        return 1
    print(f"Wrote {result}")
    return 0


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog="videokidnapper",
        description=(
            "Trim a local file or download+trim a URL. "
            "With no flags, launches the GUI."
        ),
    )
    p.add_argument("--cli", action="store_true", help="Force CLI mode")
    p.add_argument("--url", help="URL to download (YouTube/IG/Bsky/X/Reddit/FB)")
    p.add_argument("--file", help="Local video file to trim")
    p.add_argument("--start", type=float, help="Start time in seconds")
    p.add_argument("--end",   type=float, help="End time in seconds")
    p.add_argument("--out",   help="Output path (auto-generated if omitted)")
    p.add_argument("--format", default="MP4", choices=["MP4", "GIF", "mp4", "gif"])
    p.add_argument("--quality", default="Medium",
                   choices=["Low", "Medium", "High", "Ultra"])
    p.add_argument("--speed",  type=float, default=1.0)
    p.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270])
    p.add_argument("--mute",   action="store_true")
    p.add_argument("--audio-only", dest="audio_only", action="store_true")
    p.add_argument("--aspect", default="Source",
                   choices=["Source", "1:1", "9:16", "16:9", "4:5", "3:4"])
    p.add_argument("--hw", default="auto", choices=["auto", "off"],
                   help="Hardware encoder preference")
    p.add_argument("--version", action="version",
                   version=_version_string())
    p.add_argument("--selftest", action="store_true",
                   help="Report bundled-capability status (ffmpeg, "
                        "auto-track) and exit; used by packaging CI.")
    return p.parse_args(argv)


def _version_string():
    from videokidnapper import __version__
    return f"videokidnapper {__version__}"


def _selftest():
    """Print bundled-capability status; exit non-zero if a REQUIRED one is
    missing. Auto-track is optional, so its absence is reported but does
    not fail — except in a frozen build, where it SHOULD have been
    bundled, so a frozen build without it is a packaging regression."""
    frozen = getattr(sys, "frozen", False)

    from videokidnapper.utils.ffmpeg_check import check_ffmpeg
    ffmpeg_ok = bool(check_ffmpeg()[0])
    print(f"ffmpeg: {'ok' if ffmpeg_ok else 'MISSING'}")

    from videokidnapper.core.tracker import tracking_available
    track_ok, hint = tracking_available()
    print(f"auto-track: {'ok' if track_ok else 'unavailable'}"
          + ("" if track_ok else f" ({hint})"))
    print(f"frozen: {frozen}")

    failed = False
    if frozen and not track_ok:
        print("FAIL: auto-track should be bundled in a packaged build")
        failed = True
    return 1 if failed else 0


def main():
    """Entry point for both ``python main.py`` and ``videokidnapper`` script.

    Any CLI argument (including ``--help`` / ``-h`` / ``--version``)
    routes through argparse; a bare launch opens the GUI.
    """
    argv = sys.argv[1:]
    if argv:
        args = _parse_args(argv)
        if getattr(args, "selftest", False):
            sys.exit(_selftest())
        sys.exit(_cli_main(args))

    from videokidnapper.app import App
    App().mainloop()


if __name__ == "__main__":
    main()
