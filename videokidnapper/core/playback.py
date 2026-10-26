# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
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

import logging
import os
import shutil
import subprocess
import threading
import time


_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# PortAudio keeps its open streams in one global list with no lock of its
# own. Every Play makes a new player, so the audio thread of the session
# just paused can still be closing its stream while the next one opens
# its own; both calls drop the GIL and really do run at once. Opening and
# closing streams therefore go through this lock, in every player.
_SOUND_LOCK = threading.Lock()
# Audio threads still running, from any player, so the app can wait for
# all of them before the sound library shuts down at exit.
_AUDIO_THREADS = set()
_AUDIO_THREADS_LOCK = threading.Lock()


def wait_for_sound(timeout=1.0):
    """Wait up to ``timeout`` seconds for every playback's sound to close."""
    deadline = time.monotonic() + timeout
    with _AUDIO_THREADS_LOCK:
        threads = list(_AUDIO_THREADS)
    for thread in threads:
        if thread is threading.current_thread():
            continue
        thread.join(max(0.0, deadline - time.monotonic()))


def _app_ffmpeg():
    """The ffmpeg the rest of the app uses (it may not be on PATH)."""
    try:
        from videokidnapper.utils.ffmpeg_check import find_ffmpeg
        found = find_ffmpeg()
    except Exception:
        found = None
    return str(found) if found else (shutil.which("ffmpeg") or "ffmpeg")


def _decode_pictures_with(ffmpeg_path):
    """Have imageio_ffmpeg decode the picture with the same ffmpeg.

    It otherwise uses its own bundled copy, a different version from the
    one the sound, the colour filter and the export are built for.
    """
    if (ffmpeg_path and os.path.isfile(ffmpeg_path)
            and not os.environ.get("IMAGEIO_FFMPEG_EXE")):
        os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg_path


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
        # Set by finish(): where the audio left off, and when.
        self._finished_at = None
        self._finished_time = 0.0
        self._lock = threading.Lock()

    def reset(self, base_time):
        with self._lock:
            self._base_time = float(base_time)
            self._samples = 0
            self._wall_start = time.monotonic()
            self._finished_at = None

    def mark(self, sample_count):
        """Record ``sample_count`` more samples written to the audio device."""
        with self._lock:
            self._samples += int(sample_count)

    def finish(self):
        """The audio is done; keep time moving on the wall clock from here.

        The sample count stops growing when the audio ends. If the
        picture runs longer than the sound, or there is no sound at all,
        the video thread would otherwise wait forever for a frame time
        the clock never reaches.
        """
        with self._lock:
            if self._finished_at is None:
                self._finished_time = self._time_locked()
                self._finished_at = time.monotonic()

    def time_now(self):
        """Return the current playback timestamp in clip-space seconds."""
        with self._lock:
            if self._finished_at is not None:
                return self._finished_time + (time.monotonic() - self._finished_at)
            return self._time_locked()

    def _time_locked(self):
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
    # A frame further behind the clock than this many frame lengths, and
    # than MAX_LATE_S (sleep is that coarse on Windows), is skipped. The
    # sound leading the picture by ~45 ms is about where people notice.
    MAX_LATE_FRAMES = 1.5
    MAX_LATE_S = 0.05

    def __init__(
        self,
        video_path,
        render_callback,
        on_finished=None,
        ffmpeg_path=None,
        frame_size=None,
    ):
        """Create a player. Call :meth:`play` to start, :meth:`stop` to end.

        Parameters
        ----------
        video_path : str
            Path to the source video.
        render_callback : callable
            ``cb(pil_image, timestamp_seconds)`` — called from the video
            thread. It must not call into Tk (not even ``after``); hand
            the frame over and let the Tk thread pick it up.
        on_finished : callable, optional
            ``cb(reason)`` where ``reason`` is ``"end"`` once both the
            sound and the picture have run out, or ``"stopped"`` on user
            stop. Fired once per ``play()``, from a worker thread on a
            natural end, so the same rule applies.
        ffmpeg_path : str, optional
            Path to ffmpeg binary. Defaults to the one the app found,
            which may be a bundled copy that isn't on PATH; playback
            used to look on PATH only and played without sound then.
        frame_size : (int, int), optional
            Have ffmpeg shrink the picture to this size, about the size
            it is shown at. Full-size 4K frames could not be piped over
            fast enough to keep up with the sound.
        """
        self.video_path = video_path
        self.render_callback = render_callback
        self.on_finished = on_finished
        self.ffmpeg_path = ffmpeg_path or _app_ffmpeg()
        self.frame_size = frame_size
        _decode_pictures_with(self.ffmpeg_path)

        self._clock = AudioClock(sample_rate=self.SAMPLE_RATE)
        self._stop_event = threading.Event()
        self._audio_thread = None
        self._video_thread = None
        self._audio_proc = None
        self._running = False
        self._finished_fired = False
        # Workers of the current session still playing ("audio" and
        # "video"). The clip has ended when both have run out.
        self._pending = set()
        self._lock = threading.Lock()
        # Held while a frame is handed to render_callback; see stop().
        self._render_lock = threading.Lock()

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
        # Each session gets its own stop event and clock. A worker from
        # the previous session may still be closing its stream; it must
        # not see a cleared event and carry on, or tick the new clock.
        stop_event = threading.Event()
        clock = AudioClock(sample_rate=self.SAMPLE_RATE)
        clock.reset(base_time=float(start))
        with self._lock:
            self._stop_event = stop_event
            self._clock = clock
            self._finished_fired = False
            self._pending = {"audio", "video"}
        self._running = True

        self._audio_thread = threading.Thread(
            target=self._audio_worker,
            args=(start, end, stop_event, clock),
            name="AudioVideoPlayer-audio",
            daemon=True,
        )
        with _AUDIO_THREADS_LOCK:
            _AUDIO_THREADS.add(self._audio_thread)
        self._video_thread = threading.Thread(
            target=self._video_worker,
            args=(start, end, stop_event, clock),
            name="AudioVideoPlayer-video",
            daemon=True,
        )
        self._audio_thread.start()
        self._video_thread.start()

    def stop(self, wait=0.0):
        """Signal both threads to exit.

        Safe to call repeatedly. This only signals: the audio thread owns
        its sound stream and closes it itself. Stopping or closing the
        stream from this thread as well raced the worker's own cleanup
        inside PortAudio, and pausing playback crashed the app.

        ``wait`` is how long to wait for the threads to finish, for a
        caller about to exit the process: the sound library's own
        shutdown must not run while a stream is still closing. By
        default nothing blocks, which keeps the Tk event loop responsive.
        """
        was_running = self._running
        self._stop_event.set()
        self._running = False
        # Killing the decoder ends the audio thread's pipe read at once.
        proc = self._audio_proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        # Only fire "stopped" if something was actually playing. play()
        # calls stop() to tear down any prior session; on a fresh player
        # (nothing running) that must not spuriously notify the UI.
        if was_running:
            # Let a frame being handed over right now finish; none starts
            # after this (see _video_worker).
            with self._render_lock:
                pass
            self._fire_finished("stopped")
        if wait:
            for thread in (self._audio_thread, self._video_thread):
                if thread is not None and thread is not threading.current_thread():
                    thread.join(wait)

    # ------------------------------------------------------------------
    def _fire_finished(self, reason):
        """Dispatch on_finished exactly once per play() cycle."""
        with self._lock:
            if self._finished_fired:
                return
            self._finished_fired = True
        cb = self.on_finished
        if cb:
            try:
                cb(reason)
            except Exception:
                pass

    def _worker_done(self, name, stop_event):
        """A worker ran out of input. The clip ends when both have."""
        with self._lock:
            # A stop, or a worker from a session that has since been
            # replaced, is not the end of the clip.
            if stop_event.is_set() or stop_event is not self._stop_event:
                return
            self._pending.discard(name)
            finished = not self._pending
        if finished:
            self._running = False
            self._fire_finished("end")

    # ------------------------------------------------------------------
    def _audio_worker(self, start, end, stop_event, clock):
        """Pipe PCM from ffmpeg into the sound device, ticking the clock.

        Returns early, silently, when the deps or the sound device are
        missing or the file has no audio track. The video thread then
        plays on the wall clock and decides when the clip is over. This
        thread used to end the clip itself, which stopped silent videos
        (screen recordings, GIFs) a quarter of a second in.
        """
        proc = None
        stream = None
        try:
            try:
                import numpy as np
                import sounddevice as sd
            except Exception:
                return

            cmd = [
                self.ffmpeg_path, "-hide_banner", "-nostdin",
                "-loglevel", "error",
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
                # ffmpeg is a console program. Started from the windowed
                # app without CREATE_NO_WINDOW, Windows gave it a console
                # window of its own, which popped up over the editor on
                # every Play. imageio_ffmpeg already hides the video
                # decoder's; this is the sound's.
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, bufsize=0,
                    creationflags=_NO_WINDOW,
                )
            except Exception:
                return
            self._audio_proc = proc
            if stop_event.is_set():
                return  # stopped before stop() could see the process

            bytes_per_sample = 2 * self.CHANNELS
            chunk_bytes = self.CHUNK_SAMPLES * bytes_per_sample

            while not stop_event.is_set():
                raw = proc.stdout.read(chunk_bytes)
                if not raw:
                    break
                # If the last read was short, respect that many samples.
                samples_this_chunk = len(raw) // bytes_per_sample
                if samples_this_chunk == 0:
                    break
                if stream is None:
                    # Opened on the first audio, so a file without an
                    # audio track never takes the sound device.
                    opened = None
                    try:
                        with _SOUND_LOCK:
                            if stop_event.is_set():
                                break
                            opened = sd.OutputStream(
                                samplerate=self.SAMPLE_RATE,
                                channels=self.CHANNELS,
                                dtype="int16",
                            )
                            opened.start()
                        stream = opened
                    except Exception:
                        # Audio device not available (headless CI, no
                        # speakers). Silent fallback — the video thread
                        # still plays via the wall clock. A stream that
                        # opened but wouldn't start is still closed.
                        if opened is not None:
                            with _SOUND_LOCK:
                                try:
                                    opened.close()
                                except Exception:
                                    pass
                        return
                arr = np.frombuffer(
                    raw[: samples_this_chunk * bytes_per_sample],
                    dtype=np.int16,
                ).reshape(-1, self.CHANNELS)
                try:
                    stream.write(arr)
                except Exception:
                    break
                clock.mark(samples_this_chunk)
        except Exception:
            pass
        finally:
            # This thread is the only one that touches the stream. A stop
            # drops what is still queued, so the sound cuts at once; a
            # natural end lets the last of it play out.
            if stream is not None:
                with _SOUND_LOCK:
                    try:
                        if stop_event.is_set():
                            stream.abort()
                        else:
                            stream.stop()
                        stream.close()
                    except Exception:
                        pass
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                if self._audio_proc is proc:
                    self._audio_proc = None
            clock.finish()
            self._worker_done("audio", stop_event)
            with _AUDIO_THREADS_LOCK:
                _AUDIO_THREADS.discard(threading.current_thread())

    def _video_worker(self, start, end, stop_event, clock):
        """Pull decoded frames, wait for audio clock, hand off to Tk."""
        reader = None
        try:
            try:
                import imageio_ffmpeg
                from PIL import Image
            except Exception:
                return

            input_params = ["-ss", str(max(0.0, float(start)))]
            output_params = []
            if end is not None:
                output_params += ["-t", str(max(0.01, float(end) - float(start)))]
            # Same colour chain as the export and the still preview, so HDR
            # footage plays back with the colours it will export with.
            try:
                from videokidnapper.core.ffmpeg.probe import preview_color_filter
                vf = preview_color_filter(self.video_path)
            except Exception:
                vf = None
            filters = [vf] if vf else []
            if self.frame_size:
                w, h = self.frame_size
                filters.append(f"scale={int(w)}:{int(h)}:flags=bilinear")
                # imageio warns on every play that the frames it reads are
                # not the source's size, which is the point here.
                logging.getLogger("imageio_ffmpeg").setLevel(logging.ERROR)
            if filters:
                output_params += ["-vf", ",".join(filters)]

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
                return

            late_after = max(self.MAX_LATE_FRAMES / src_fps, self.MAX_LATE_S)
            skipped = 0
            for i, raw in enumerate(reader):
                if stop_event.is_set():
                    break
                frame_t = float(start) + i / src_fps

                # Wait for the audio clock to catch up. Poll with a
                # small sleep so we don't hot-spin the CPU.
                while not stop_event.is_set():
                    now = clock.time_now()
                    lag = frame_t - now
                    if lag <= self.VIDEO_LOOKAHEAD_S:
                        break
                    time.sleep(min(0.030, max(0.001, lag / 2)))

                if stop_event.is_set():
                    break

                # Already behind the sound by more than a frame (a slow
                # machine, a busy window): skip it rather than show every
                # frame later and later, drifting off the sound. Every
                # fourth is still shown so the picture never freezes.
                if (clock.time_now() - frame_t > late_after and skipped < 3):
                    skipped += 1
                    continue
                skipped = 0

                try:
                    img = Image.frombytes("RGB", (w, h), bytes(raw))
                except Exception:
                    continue
                with self._render_lock:
                    # Checked again under the lock stop() takes before it
                    # reports "stopped", so no frame lands after that and
                    # replaces the paused picture.
                    if stop_event.is_set():
                        break
                    try:
                        self.render_callback(img, frame_t)
                    except Exception:
                        # A single bad frame shouldn't end playback.
                        pass
        except Exception:
            pass
        finally:
            if reader is not None:
                try:
                    reader.close()
                except Exception:
                    pass
            self._worker_done("video", stop_event)
