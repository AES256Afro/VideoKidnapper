# VideoKidnapper v1.0.0

First public release. Paste this body into the GitHub Release form for `v1.0.0` (edit as you like).

---

🎬 **Trim videos, download clips from the open web, and export polished GIFs or MP4s — from any supported platform.**

![Trim Video with ranges queued](https://raw.githubusercontent.com/AES256Afro/VideoKidnapper/main/assets/screenshots/trim_loaded.png)

## Highlights

- **Multi-platform downloads** — YouTube, Instagram, Bluesky, Twitter/X, Reddit, Facebook
- **Share-to-platform** — one click copies the exported file and opens the compose page (captions prefilled on X / Reddit / Facebook)
- **Pixel-accurate preview** — what you see in the preview canvas is what ffmpeg writes to disk
- **Multi-range trimming** — queue N clips, export separately or concat into one
- **SRT / VTT import** — auto-creates time-synced text layers
- **Crop by click-drag** + aspect presets (1:1, 9:16, 16:9, 4:5, 3:4)
- **Hardware encoding** — auto-probes NVENC / QSV / VideoToolbox / AMF, falls back to libx264 when the probe fails
- **Screen recording**, **live waveform**, **history tab**, **light / dark themes**
- **CLI mode** — `python main.py --url … --start 10 --end 25 --format GIF`
- **Setup dialog** auto-installs missing prerequisites (FFmpeg + pip packages) or opens an elevated terminal with the right commands

## Install

```bash
git clone https://github.com/AES256Afro/VideoKidnapper.git
cd VideoKidnapper
git checkout v1.0.0
pip install -r requirements.txt
python main.py
```

If FFmpeg isn't installed, the first launch opens the **⚙ Setup** dialog with an **Install Selected** button that downloads a portable build into `assets/ffmpeg/bin/`.

## What's in this release

See [CHANGELOG.md](https://github.com/AES256Afro/VideoKidnapper/blob/main/CHANGELOG.md#100--2026-04-18) for the full list — features, hardening, fixes, and tests.

## Platform terms of use

Downloading from services like YouTube, Instagram, X, Reddit, Bluesky, and Facebook may violate their terms of service. You are responsible for complying with each platform's ToS, your local laws, and applicable copyright. See the [Disclaimer section](https://github.com/AES256Afro/VideoKidnapper#disclaimer--terms-of-use) for details.

## Thanks

Built on top of a stack of excellent open source projects — [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), [Pillow](https://github.com/python-pillow/Pillow), [yt-dlp](https://github.com/yt-dlp/yt-dlp), [mss](https://github.com/BoboTiG/python-mss), [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2), and [FFmpeg](https://ffmpeg.org/). See [NOTICE.md](https://github.com/AES256Afro/VideoKidnapper/blob/main/NOTICE.md).
