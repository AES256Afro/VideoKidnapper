# SnapIt

A modern desktop tool for creating GIFs and video clips from screen recordings or existing video files.

## Features

- **Video Trimming** - Load any video file, set start/end points with a dual-handle slider, and export the clip as GIF or MP4
- **Screen Recording** - Select any screen region, record live, and export as GIF or MP4
- **Quality Presets** - Choose from Low, Medium, High, or Ultra quality presets
- **Modern Dark UI** - Clean, dark-themed interface built with CustomTkinter
- **Auto-Export** - All files save to your Downloads folder with timestamped names

## Quality Presets

| Preset | FPS | Max Width | GIF Colors | Video Quality |
|--------|-----|-----------|------------|---------------|
| Low    | 10  | 480px     | 64         | CRF 28        |
| Medium | 15  | 720px     | 128        | CRF 23        |
| High   | 24  | 1080px    | 256        | CRF 18        |
| Ultra  | 30  | Native    | 256        | CRF 15        |

## Requirements

- Python 3.9+
- FFmpeg (must be installed separately)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/AES256Afro/SnapIt.git
   cd SnapIt
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install FFmpeg:**
   - Download from [gyan.dev FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/)
   - Extract the archive
   - Add the `bin/` folder to your system PATH
   - Or place `ffmpeg.exe` and `ffprobe.exe` in `assets/ffmpeg/bin/` within this project

4. **Run SnapIt:**
   ```bash
   python main.py
   ```

## Usage

### Trim Video Mode
1. Click **Open Video File** and select a video
2. Use the dual-handle slider or type timestamps to set start/end points
3. Preview the frame at the start position
4. Select quality preset and export format (GIF or MP4)
5. Click **Export** - file saves to your Downloads folder

### Screen Record Mode
1. Click **Select Region** - the screen dims and you draw a rectangle
2. Click **Record** to start capturing
3. Click **Stop** when done
4. Select quality preset and export format
5. Click **Export** - file saves to your Downloads folder

## Export Naming

Files are saved as: `SnapIt_{mode}_{YYYYMMDD}_{HHMMSS}.{ext}`

Example: `SnapIt_trim_20260324_143022.gif`

## Tech Stack

- **CustomTkinter** - Modern dark-themed GUI framework
- **Pillow** - Image processing and display
- **mss** - Fast cross-platform screen capture
- **FFmpeg** - Video/GIF encoding (two-pass palette for high-quality GIFs)

## License

MIT
