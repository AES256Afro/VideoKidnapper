import os
import tempfile
import threading
import time

import mss
from PIL import Image


class Recorder:
    def __init__(self):
        self.recording = False
        self.frame_dir = None
        self.frame_count = 0
        self.start_time = 0
        self.elapsed = 0
        self._thread = None
        self._stop_event = threading.Event()
        self.region = None
        self.capture_fps = 30

    def start(self, region, fps=30):
        self.region = region
        self.capture_fps = fps
        self.frame_dir = tempfile.mkdtemp(prefix="snapit_")
        self.frame_count = 0
        self.start_time = time.time()
        self.elapsed = 0
        self._stop_event.clear()
        self.recording = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self.recording = False
        if self._thread:
            self._thread.join(timeout=5)
        self.elapsed = time.time() - self.start_time
        return self.frame_dir, self.frame_count, self.elapsed

    def _capture_loop(self):
        x, y, w, h = self.region
        monitor = {"left": x, "top": y, "width": w, "height": h}
        interval = 1.0 / self.capture_fps

        with mss.mss() as sct:
            while not self._stop_event.is_set():
                frame_start = time.time()
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                frame_path = os.path.join(self.frame_dir, f"frame_{self.frame_count:06d}.png")
                img.save(frame_path, "PNG")
                self.frame_count += 1
                self.elapsed = time.time() - self.start_time

                sleep_time = interval - (time.time() - frame_start)
                if sleep_time > 0:
                    self._stop_event.wait(sleep_time)

    def get_actual_fps(self):
        if self.elapsed > 0:
            return self.frame_count / self.elapsed
        return self.capture_fps

    def cleanup(self):
        if self.frame_dir and os.path.exists(self.frame_dir):
            import shutil
            shutil.rmtree(self.frame_dir, ignore_errors=True)
            self.frame_dir = None
