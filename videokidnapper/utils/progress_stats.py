# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Turn a stream of progress fractions into a time estimate.

The export dialog had a percentage bar and nothing else, which answers
"how far" but not "how long". At 40% there was no way to tell whether
the next step was ten seconds or four minutes, so a slow export looked
exactly like a stuck one.

This is deliberately fed from the *outer* progress fraction rather than
from ffmpeg's own output. That fraction is already unified upstream: the
GIF path folds its two passes into one 0→1 range
(``progress_callback(0.3 + p * 0.7)``), and a multi-clip export folds
every clip into one. Estimating here means the two-pass and multi-clip
cases work without either knowing about the estimator.

The cost of that choice is that the fraction is not linear in *work* —
the palette pass is 30% of the bar but not 30% of the time — so the
estimate drifts at a pass boundary and re-converges. The rolling window
below is what makes that recovery quick.
"""

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, Tuple


#: Only the last few seconds inform the estimate, so it tracks the
#: current encoding rate rather than an average dragged down by a slow
#: start.
WINDOW_SECONDS = 8.0

#: Below this the estimate is noise: a couple of samples over a fraction
#: of a second can imply anything. Showing nothing is better than
#: showing a number that swings by minutes.
MIN_ELAPSED_SECONDS = 2.0
MIN_SAMPLES = 3

#: Past this the job is finishing; a countdown that keeps re-appearing
#: at 99% reads as broken.
SUPPRESS_ABOVE_FRACTION = 0.995


@dataclass(frozen=True)
class ProgressStats:
    """What is known about an in-flight export right now."""

    fraction: float
    #: Estimated seconds remaining, or None while unknowable.
    eta_seconds: Optional[float] = None
    #: Progress per wall-second — 0.05 means the whole job every 20s.
    rate: Optional[float] = None

    @property
    def eta_text(self) -> str:
        """Human phrasing, or "" when there is nothing worth saying."""
        return format_eta(self.eta_seconds)


def format_eta(seconds: Optional[float]) -> str:
    """Phrase a duration the way someone waiting would say it.

    Deliberately vague at the top end: "about 1h 5m left" claims less
    precision than "1:05:12 remaining", and an estimate that precise
    would be lying.
    """
    if seconds is None or seconds < 0:
        return ""
    if seconds < 5:
        return "a few seconds left"
    if seconds < 60:
        return f"about {int(round(seconds / 5.0)) * 5}s left"
    if seconds < 3600:
        minutes, secs = divmod(int(seconds), 60)
        if minutes < 5 and secs >= 10:
            return f"about {minutes}m {secs // 10 * 10}s left"
        return f"about {minutes + (1 if secs >= 30 else 0)}m left"
    hours, rem = divmod(int(seconds), 3600)
    return f"about {hours}h {rem // 60}m left"


class EtaEstimator:
    """Rolling-window estimate of the time left in a 0→1 job.

    Feed it every progress update; it reports an estimate once there is
    enough signal to justify one.
    """

    def __init__(self, window_seconds: float = WINDOW_SECONDS) -> None:
        self._window = window_seconds
        self._samples: Deque[Tuple[float, float]] = deque()  # (when, fraction)
        self._started: Optional[float] = None

    def update(self, fraction: float, now: Optional[float] = None) -> ProgressStats:
        """Record a progress reading and return what is known."""
        if now is None:
            now = time.monotonic()
        fraction = max(0.0, min(1.0, float(fraction)))
        if self._started is None:
            self._started = now

        # A restarted or rewound job (a new clip in a batch reusing the
        # dialog) invalidates the window — otherwise the backwards jump
        # produces a negative rate and a nonsense estimate.
        if self._samples and fraction < self._samples[-1][1]:
            self._samples.clear()

        self._samples.append((now, fraction))
        cutoff = now - self._window
        while len(self._samples) > MIN_SAMPLES and self._samples[0][0] < cutoff:
            self._samples.popleft()

        return ProgressStats(
            fraction=fraction,
            eta_seconds=self._estimate(fraction, now),
            rate=self._rate(),
        )

    def _rate(self) -> Optional[float]:
        """Fraction of the job completed per wall-second."""
        if len(self._samples) < MIN_SAMPLES:
            return None
        (t0, f0), (t1, f1) = self._samples[0], self._samples[-1]
        elapsed = t1 - t0
        if elapsed <= 0:
            return None
        rate = (f1 - f0) / elapsed
        return rate if rate > 0 else None

    def _estimate(self, fraction: float, now: float) -> Optional[float]:
        if fraction >= SUPPRESS_ABOVE_FRACTION:
            return None
        if self._started is None or (now - self._started) < MIN_ELAPSED_SECONDS:
            return None
        rate = self._rate()
        if not rate:
            return None
        return (1.0 - fraction) / rate

    def reset(self) -> None:
        self._samples.clear()
        self._started = None
