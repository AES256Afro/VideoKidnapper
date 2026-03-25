# SnapIt

A modern desktop tool for creating GIFs and video clips with text overlays from local video files or YouTube URLs.

## Features

- **Video Trimming** - Load any video file, set start/end points with a dual-handle slider, and export as GIF or MP4
- **YouTube Downloads** - Paste a YouTube URL, download the video, trim and export clips
- **Text Overlay Layers** - Add multiple text layers with per-layer timing, fonts, colors, and positions
- **Text Style Presets** - Subtitle (with background box), Title (large centered), Watermark (small corner), Custom
- **Quality Presets** - Choose from Low, Medium, High, or Ultra quality presets
- **Modern Dark UI** - Clean, dark-themed interface built with CustomTkinter
- **Debug Log** - Built-in debug tab for troubleshooting
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
3. Expand **Text Layers** to add text overlays with per-layer timing
4. Select quality preset and export format (GIF or MP4)
5. Click **Export** - file saves to your Downloads folder

### URL Download Mode
1. Paste a YouTube URL and click **Download**
2. Once downloaded, set start/end points on the timeline
3. Add text layers if desired
4. Select quality preset and export format
5. Click **Export** - file saves to your Downloads folder

### Text Layers
- Click **+ Text Layers** to expand the panel
- Click **+ Add Text Layer** to add a layer
- Choose a style preset: **Subtitle**, **Title**, **Watermark**, or **Custom**
- Set font, size, color, and position per layer
- Use the per-layer timing slider to control when each layer appears

## Export Naming

Files are saved as: `SnapIt_{mode}_{YYYYMMDD}_{HHMMSS}.{ext}`

Example: `SnapIt_trim_20260324_143022.gif`

## Tech Stack

- **CustomTkinter** - Modern dark-themed GUI framework
- **Pillow** - Image processing and display
- **yt-dlp** - YouTube video downloading
- **FFmpeg** - Video/GIF encoding with drawtext overlays

## License

MIT
