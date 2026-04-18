# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Whisper-based auto-captions.

Runs `faster-whisper <https://github.com/guillaumekln/faster-whisper>`_
over the video's audio track and produces a list of ``{start, end, text}``
dicts in the same shape the existing SRT importer consumes. That means
auto-captions immediately feed into the Text Layers panel with no
separate UI path for "captioned video vs user-typed overlays" — they're
just layers.

Why faster-whisper and not openai-whisper:
  * ~4× faster CPU inference via CTranslate2
  * No torch / CUDA requirement for CPU mode — CI friendly
  * Same model sizes / quality as the upstream "openai-whisper" package
  * Permissive license (MIT)

The dependency is **optional**. ``is_available()`` probes for the
import; the UI button checks that flag and, when it returns False,
shows a toast with install instructions rather than crashing.

Scope note: this module does not ship models. faster-whisper
downloads the first time it's asked to load a model size (tiny: ~40MB,
base: ~75MB, small: ~250MB). Subsequent loads hit the on-disk cache in
``~/.cache/huggingface``. Model management is a faster-whisper
responsibility — we just ask for a size and get back a ready model.
"""

import subprocess
import tempfile
from pathlib import Path

from videokidnapper.utils.ffmpeg_check import find_ffmpeg


# Supported model sizes in size/quality order. "tiny" is enough for
# most clip-length work; "small" nudges accuracy noticeably at ~3× cost.
MODEL_SIZES = ("tiny", "base", "small", "medium", "large")


def is_available():
    """Return True when faster-whisper is importable.

    Kept separate from actual import so the caller (UI) can disable
    the Auto-captions button cleanly on startup without paying the
    cost of loading a WhisperModel.
    """
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return True


def extract_audio_segment(video_path, start=None, end=None, ffmpeg=None):
    """Extract mono 16 kHz WAV audio for the given time window.

    Whisper expects 16 kHz mono s16 PCM. ffmpeg's ``-ar 16000 -ac 1``
    lines up exactly; no extra resampling in Python. The extracted
    file is a temporary path the caller is responsible for deleting.
    """
    ffmpeg = ffmpeg or str(find_ffmpeg() or "ffmpeg")
    wav_path = Path(tempfile.mktemp(suffix=".wav"))
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", str(max(0.0, float(start)))]
    cmd += ["-i", str(video_path)]
    if end is not None and start is not None:
        cmd += ["-t", str(max(0.01, float(end) - float(start)))]
    elif end is not None:
        cmd += ["-t", str(max(0.01, float(end)))]
    cmd += [
        "-vn",                  # drop video
        "-ac", "1",             # mono
        "-ar", "16000",         # 16 kHz
        "-acodec", "pcm_s16le", # signed 16-bit little-endian
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0 or not wav_path.exists():
        raise RuntimeError(
            "ffmpeg failed to extract audio for transcription: "
            + (result.stderr.decode("utf-8", errors="replace")[-200:] or "(no stderr)")
        )
    return wav_path


def segments_to_entries(segments, time_offset=0.0):
    """Normalize faster-whisper segments into SRT-compatible dicts.

    Split into its own function so tests can feed in synthetic
    "segments" without actually running a Whisper model. The shape
    faster-whisper produces is ``[Segment(start, end, text), ...]`` —
    we read attributes with ``getattr`` so dict-like stand-ins (easy
    to build in tests) also work.
    """
    entries = []
    for seg in segments:
        start = float(getattr(seg, "start", 0.0))
        end = float(getattr(seg, "end", start))
        text = (getattr(seg, "text", "") or "").strip()
        if not text:
            continue
        if end <= start:
            end = start + 0.5  # keep a visible display window
        entries.append({
            "start": time_offset + start,
            "end":   time_offset + end,
            "text":  text,
        })
    return entries


def transcribe(
    video_path,
    model_size="base",
    language=None,
    start=None,
    end=None,
    progress_callback=None,
    cancel_event=None,
):
    """Transcribe the audio of ``video_path`` into SRT-shaped dicts.

    ``model_size`` must be one of :data:`MODEL_SIZES`. ``language`` is
    an ISO code like ``"en"`` or ``None`` for auto-detect. ``start`` /
    ``end`` (seconds) restrict the transcription to a window — useful
    for captioning just the current trim range. Returned timestamps
    are in the *video* timeline, not relative to the window.

    ``progress_callback(fraction)`` is called after each segment with
    a rough [0, 1] fraction. ``cancel_event`` (a ``threading.Event``)
    lets the UI stop the transcription early.

    Raises:
      * ``RuntimeError`` if faster-whisper isn't installed.
      * ``ValueError`` for an unknown model_size.
      * ``RuntimeError`` if ffmpeg audio extraction fails.
    """
    if model_size not in MODEL_SIZES:
        raise ValueError(
            f"unknown model_size {model_size!r}; pick one of {MODEL_SIZES}",
        )
    if not is_available():
        raise RuntimeError(
            "faster-whisper is not installed. "
            "Run:  pip install faster-whisper",
        )

    from faster_whisper import WhisperModel

    wav = extract_audio_segment(video_path, start=start, end=end)
    time_offset = float(start) if start else 0.0
    try:
        # CPU inference with int8 quantization — roughly 2× faster than
        # float16 and fits in RAM on machines without a dedicated GPU.
        # Users with CUDA can still pick a larger model; we just pick
        # a conservative default that works on everything.
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(wav), language=language)
        # faster-whisper returns an iterator — consume it so we can
        # report progress and honour cancellation per-segment.
        entries = []
        total = getattr(info, "duration", 0) or 1.0
        for seg in segments:
            if cancel_event is not None and cancel_event.is_set():
                break
            s_entries = segments_to_entries([seg], time_offset=time_offset)
            entries.extend(s_entries)
            if progress_callback:
                try:
                    progress_callback(min(1.0, float(seg.end) / total))
                except Exception:
                    pass
        if progress_callback:
            progress_callback(1.0)
        return entries
    finally:
        try:
            wav.unlink(missing_ok=True)
        except OSError:
            pass
