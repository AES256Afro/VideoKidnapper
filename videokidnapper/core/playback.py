# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Real-time in-app video + audio playback.

Replaces the previous "scrub at 8 fps with no sound" preview loop with
a pair of threads driven by an audio-mastered clock:

- **Audio thread** pipes PCM from an ``ffmpeg -f s16le`` subprocess
  into a ``sounddevice.OutputStream``. Every write bumps a sample
  counter; ``current_time()`` derives wall-ish time from that.
- **Video thread** pulls decoded RGB frames from ``imageio_ffmpeg.read_frames``
  (persistent ffmpeg subprocess, one spawn per play) and waits until
  the audio clock catches up to each frame's timestamp before handing
  it to the Tk render callback.

Audio as the master is the standard video-player choice: human ears
pick up audio glitches long before they notice a dropped video frame,
and audio hardware latency is stable so ``samples_played / sample_rate``
is a steady clock. When the source has no audio track (silent clip,
mute toggle planned for later), the video thread falls back to a
``time.monotonic()`` clock instead.

This module is **optional**: it imports ``imageio_ffmpeg``,
``sounddevice``, and ``numpy`` only when a player is actually
constructed, and :func:`is_available` returns ``False`` when any of
those deps are missing. Callers (``VideoPlayer``) check that flag and
fall back to the scrub-based preview path so the core app still runs
with just the base install.

Scope: this is for *preview* only. It intentionally doesn't attempt
frame-exact seek, does not loop, and is discarded + re-created on each
``play()`` call. Export still goes through ffmpeg_backend.py.
"""

import shutil
import subprocess
import threading
import time


# ---------------------------------------------------------------------------
# Availability probe
# ---------------------------------------------------------------------------

def is_available():
    """Return True when all three optional deps import cleanly.

    Called by the UI layer to decide whether to wire the real player
    or fall back to the scrub loop. We import inside the function so
    ``import videokidnapper.core.playback`` itself never fails — the
    module has to be importable even on a base install for the caller
    to ask this question.
    """
    try:
        import imageio_ffmpeg  # noqa: F401
        import numpy           # noqa: F401
        import sounddevice     # noqa: F401
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Clock
# ---------------------------------------------------------------------------

class AudioClock:
    """Derives current playback time from samples written to the audio device.

    Kept in its own tiny class so the sync logic is unit-testable
    without actually opening sounddevice: tests drive ``mark()`` with
    synthesized sample counts and assert ``time_now()`` agrees.

    ``base_time`` is the clip-space timestamp at which playback began;
    ``samples`` is the cumulative sample count the audio thread has
    handed to the device (monotonically increasing). When the clip has
    no audio, callers construct with ``sample_rate=None`` and the
    wall-clock fallback below is used.
    """

    def __init__(self, base_time=0.0, sample_rate=44100):
        self._base_time = float(base_time)
        self._sample_rate = sample_rate
        self._samples = 0
        self._wall_start = None
        self._lock = threading.Lock()

    def reset(self, base_time):
        with self._lock:
            self._base_time = float(base_time)
            self._samples = 0
            self._wall_start = time.monotonic()

    def mark(self, sample_count):
        """Record ``sample_count`` more samples written to the audio device."""
        with self._lock:
            self._samples += int(sample_count)

    def time_now(self):
        """Return the current playback timestamp in clip-space seconds."""
        with self._lock:
            if self._sample_rate and self._samples > 0:
                return self._base_time + self._samples / self._sample_rate
            # No audio data yet — fall back to wall clock so video still
            # plays at real-time (used for silent clips and the first
            # few ms before the audio thread has written anything).
            if self._wall_start is None:
                return self._base_time
            return self._base_time + (time.monotonic() - self._wall_start)


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

class AudioVideoPlayer:
    """Threaded audio + video player using imageio_ffmpeg + sounddevice."""

    # Defaults tuned for preview: stereo 44.1 kHz is universally
    # supported by consumer audio hardware, and 1024-sample chunks give
    # us ~23 ms of latency without starving the device.
    SAMPLE_RATE = 44100
    CHANNELS = 2
    CHUNK_SAMPLES = 1024
    # How far ahead of the audio clock we'll render a video frame.
    # Small negative means "render slightly early"; tweaks jitter.
    VIDEO_LOOKAHEAD_S = 0.02

    def __init__(
        self,
        video_path,
        render_callback,
        on_finished=None,
        ffmpeg_path=None,
    ):
        """Create a player. Call :meth:`play` to start, :meth:`stop` to end.

        Parameters
        ----------
        video_path : str
            Path to the source video.
        render_callback : callable
            ``cb(pil_image, timestamp_seconds)`` — called from the video
            thread. The UI side must marshal back to the Tk main
            thread via ``widget.after(0, ...)``.
        on_finished : callable, optional
            ``cb(reason)`` where ``reason`` is ``"end"`` on natural end
            or ``"stopped"`` on user stop. Fired once per ``play()``.
        ffmpeg_path : str, optional
            Path to ffmpeg binary. Defaults to the system ``ffmpeg`` —
            callers that already resolved a portable copy should pass
            it here.
        """
        self.video_path = video_path
        self.render_callback = render_callback
        self.on_finished = on_finished
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"

        self._clock = AudioClock(sample_rate=self.SAMPLE_RATE)
        self._stop_event = threading.Event()
        self._audio_thread = None
        self._video_thread = None
        self._audio_proc = None
        self._audio_stream = None
        self._running = False
        self._finished_fired = False

    # ------------------------------------------------------------------
    def is_running(self):
        return self._running

    def current_time(self):
        """Audio-mastered current clip time in seconds (thread-safe)."""
        return self._clock.time_now()

    # ------------------------------------------------------------------
    def play(self, start=0.0, end=None):
        """Start playback from ``start`` (seconds). Non-blocking.

        If a previous play is still running, it's stopped first.
        """
        self.stop()
        self._stop_event.clear()
        self._finished_fired = False
        self._clock.reset(base_time=float(start))
        self._running = True

        self._audio_thread = threading.Thread(
            target=self._audio_worker,
            args=(start, end),
            name="AudioVideoPlayer-audio",
            daemon=True,
        )
        self._video_thread = threading.Thread(
            target=self._video_worker,
            args=(start, end),
            name="AudioVideoPlayer-video",
            daemon=True,
        )
        self._audio_thread.start()
        self._video_thread.start()

    def stop(self):
        """Signal both threads to exit and release audio resources.

        Safe to call repeatedly. Does not block on thread join to keep
        the Tk event loop responsive; the daemon threads die on their
        own once they see the stop event.
        """
        self._stop_event.set()
        self._running = False
        # Tear down audio first — the OS stream holds real hardware.
        stream = self._audio_stream
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            self._audio_stream = None
        proc = self._audio_proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            self._audio_proc = None
        self._fire_finished("stopped")

    # ------------------------------------------------------------------
    def _fire_finished(self, reason):
        """Dispatch on_finished exactly once per play() cycle."""
        if self._finished_fired:
            return
        self._finished_fired = True
        cb = self.on_finished
        if cb:
            try:
                cb(reason)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _audio_worker(self, start, end):
        """Pipe PCM from ffmpeg into the sound device, ticking the clock."""
        try:
            import numpy as np
            import sounddevice as sd
        except Exception:
            # Deps gone at runtime — bail; video thread will use wall clock.
            return

        cmd = [
            self.ffmpeg_path, "-hide_banner", "-loglevel", "error",
            "-ss", str(max(0.0, float(start))),
            "-i", self.video_path,
        ]
        if end is not None:
            cmd += ["-t", str(max(0.01, float(end) - float(start)))]
        cmd += [
            "-vn",
            "-f", "s16le",
            "-ac", str(self.CHANNELS),
            "-ar", str(self.SAMPLE_RATE),
            "pipe:",
        ]
        try:
            self._audio_proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except Exception:
            return

        try:
            self._audio_stream = sd.OutputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="int16",
            )
            self._audio_stream.start()
        except Exception:
            # Audio device not available (headless CI, no speakers).
            # Silent fallback — video thread will still play via wall clock.
            self._audio_stream = None
            try:
                self._audio_proc.terminate()
            except Exception:
                pass
            return

        bytes_per_sample = 2 * self.CHANNELS
        chunk_bytes = self.CHUNK_SAMPLES * bytes_per_sample

        try:
            while not self._stop_event.is_set():
                raw = self._audio_proc.stdout.read(chunk_bytes)
                if not raw:
                    break
                # If the last read was short, respect that many samples.
                samples_this_chunk = len(raw) // bytes_per_sample
                if samples_this_chunk == 0:
                    break
                arr = np.frombuffer(
                    raw[: samples_this_chunk * bytes_per_sample],
                    dtype=np.int16,
                ).reshape(-1, self.CHANNELS)
                try:
                    self._audio_stream.write(arr)
                except Exception:
                    break
                self._clock.mark(samples_this_chunk)
        finally:
            # Audio EOF means natural end of clip — fire finished so
            # the UI can update the play-button label.
            if not self._stop_event.is_set():
                self._fire_finished("end")

    def _video_worker(self, start, end):
        """Pull decoded frames, wait for audio clock, hand off to Tk."""
        try:
            import imageio_ffmpeg
            from PIL import Image
        except Exception:
            return

        input_params = ["-ss", str(max(0.0, float(start)))]
        output_params = []
        if end is not None:
            output_params += ["-t", str(max(0.01, float(end) - float(start)))]

        try:
            reader = imageio_ffmpeg.read_frames(
                self.video_path,
                input_params=input_params,
                output_params=output_params,
                pix_fmt="rgb24",
            )
            meta = next(reader)
        except Exception:
            return

        w, h = meta.get("size", (0, 0))
        src_fps = meta.get("fps") or 30.0
        if w <= 0 or h <= 0:
            try:
                reader.close()
            except Exception:
                pass
            return

        try:
            for i, raw in enumerate(reader):
                if self._stop_event.is_set():
                    break
                frame_t = float(start) + i / src_fps

                # Wait for the audio clock to catch up. Poll with a
                # small sleep so we don't hot-spin the CPU.
                while not self._stop_event.is_set():
                    now = self._clock.time_now()
                    lag = frame_t - now
                    if lag <= self.VIDEO_LOOKAHEAD_S:
                        break
                    time.sleep(min(0.030, max(0.001, lag / 2)))

                if self._stop_event.is_set():
                    break

                try:
                    img = Image.frombytes("RGB", (w, h), bytes(raw))
                except Exception:
                    continue
                try:
                    self.render_callback(img, frame_t)
                except Exception:
                    # A single bad frame shouldn't end playback.
                    pass
        finally:
            try:
                reader.close()
            except Exception:
                pass
