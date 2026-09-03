# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Time-remaining estimates for exports.

The export dialog had a percentage and nothing else, which answers "how
far" but not "how long" — so a slow export looked exactly like a stuck
one. These tests pin the two things that make the estimate worth
showing: that it is accurate while the job progresses steadily, and
that it stops claiming to know when the job stops moving.
"""

import pytest

from videokidnapper.utils.progress_stats import (
    EtaEstimator,
    ProgressStats,
    format_eta,
)


# ------------------------------------------------------------- phrasing

@pytest.mark.parametrize("seconds,expected", [
    (2,    "a few seconds left"),
    (7,    "about 5s left"),
    (45,   "about 45s left"),
    (62,   "about 1m left"),
    (150,  "about 2m 30s left"),
    (400,  "about 7m left"),
    (3700, "about 1h 1m left"),
])
def test_format_eta(seconds, expected):
    assert format_eta(seconds) == expected


@pytest.mark.parametrize("bad", [None, -1, -0.5])
def test_format_eta_says_nothing_when_it_knows_nothing(bad):
    """An empty string is the honest output — better than a placeholder
    that looks like an estimate."""
    assert format_eta(bad) == ""


def test_stats_expose_the_phrasing():
    assert ProgressStats(fraction=0.5, eta_seconds=45).eta_text == "about 45s left"
    assert ProgressStats(fraction=0.5).eta_text == ""


# ------------------------------------------------------------- accuracy

def _run(estimator, total_seconds, step=0.5, until=None):
    """Drive a perfectly steady job, returning the last stats seen."""
    stats = None
    t = 0.0
    end = total_seconds if until is None else until
    while t <= end:
        stats = estimator.update(min(t / total_seconds, 1.0), now=t)
        t += step
    return stats


def test_steady_job_estimates_accurately():
    stats = _run(EtaEstimator(), total_seconds=60, until=30.0)
    assert stats.eta_seconds is not None
    # Perfectly steady input, so this should be close to exact.
    assert abs(stats.eta_seconds - 30.0) < 1.0


def test_estimate_shrinks_as_the_job_proceeds():
    seen = [
        _run(EtaEstimator(), total_seconds=40, until=t).eta_seconds
        for t in (5.0, 15.0, 25.0, 35.0)
    ]
    assert all(a > b for a, b in zip(seen, seen[1:])), seen


def test_no_estimate_before_there_is_signal():
    """Two samples over half a second can imply anything; showing a
    number that swings by minutes is worse than showing none."""
    est = EtaEstimator()
    assert est.update(0.0, now=0.0).eta_seconds is None
    assert est.update(0.01, now=0.5).eta_seconds is None


def test_no_estimate_at_the_very_end():
    """A countdown that keeps re-appearing at 99% reads as broken."""
    est = EtaEstimator()
    _run(est, total_seconds=20, until=19.0)
    assert est.update(1.0, now=20.0).eta_seconds is None


# -------------------------------------------------------------- stalling

def test_a_stalled_job_grows_then_gives_up():
    """The important failure mode. A frozen number implies progress
    that has stopped; the estimate should grow, then admit it does not
    know rather than leave a stale value on screen."""
    est = EtaEstimator()
    _run(est, total_seconds=60, until=10.0)
    before = est.update(1 / 6, now=10.0).eta_seconds
    assert before is not None

    grew = est.update(1 / 6, now=16.0).eta_seconds
    assert grew is not None and grew > before

    # Once no forward progress remains anywhere in the window.
    assert est.update(1 / 6, now=40.0).eta_seconds is None


def test_progress_going_backwards_does_not_produce_a_nonsense_estimate():
    """A batch reusing the dialog rewinds the fraction for each clip; a
    backwards jump would otherwise yield a negative rate."""
    est = EtaEstimator()
    _run(est, total_seconds=20, until=15.0)
    stats = est.update(0.0, now=16.0)
    assert stats.eta_seconds is None or stats.eta_seconds >= 0


def test_fraction_is_clamped():
    est = EtaEstimator()
    assert est.update(-5.0, now=0.0).fraction == 0.0
    assert est.update(99.0, now=1.0).fraction == 1.0


def test_reset_forgets_everything():
    est = EtaEstimator()
    _run(est, total_seconds=30, until=20.0)
    est.reset()
    assert est.update(0.5, now=100.0).eta_seconds is None
