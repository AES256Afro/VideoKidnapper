# SPDX-FileCopyrightText: 2026 AES256Afro <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""The crash log tells the next run that the last one died, and why."""

import faulthandler
import sys
import threading

import pytest

from videokidnapper.utils import crash_log


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / "crash.log"
    monkeypatch.setattr(crash_log, "LOG_PATH", path)
    was_enabled = faulthandler.is_enabled()
    yield path
    crash_log.finish()
    if was_enabled:
        faulthandler.enable(file=sys.__stderr__ or sys.stdout, all_threads=True)


def test_a_first_run_reports_nothing(log):
    assert crash_log.start("1.0") == ""
    assert crash_log.previous_crash() == ""
    assert log.read_text(encoding="utf-8").startswith(crash_log.START)


def test_a_clean_exit_reports_nothing_next_time(log):
    crash_log.start("1.0")
    crash_log.finish()
    assert crash_log.start("1.0") == ""


def test_a_run_that_never_exited_is_reported_with_its_log(log):
    crash_log.start("1.0")
    crash_log.write("pressed play")
    # The process dies here: no finish().
    crash_log._file.close()
    crash_log._file = None

    previous = crash_log.start("1.1")
    assert previous.startswith(crash_log.START)
    assert "v1.0" in previous and "pressed play" in previous
    assert crash_log.previous_crash() == previous
    # Reported once: this run is the one being logged now.
    crash_log.finish()
    assert crash_log.start("1.1") == ""


def test_uncaught_errors_are_written_with_their_traceback(log):
    crash_log.start("1.0")
    try:
        raise ValueError("boom")
    except ValueError:
        crash_log.record_exception(*sys.exc_info(), where="a test")
    crash_log.finish()
    text = log.read_text(encoding="utf-8")
    assert "Uncaught exception in a test" in text
    assert "ValueError: boom" in text and "Traceback" in text


def test_worker_thread_errors_are_logged(log, monkeypatch):
    monkeypatch.setattr(threading, "excepthook", lambda args: None)
    crash_log.start("1.0")
    crash_log.install_thread_hook()

    def fail():
        raise RuntimeError("worker failed")

    t = threading.Thread(target=fail, name="decoder")
    t.start()
    t.join()
    crash_log.finish()
    text = log.read_text(encoding="utf-8")
    assert "in decoder" in text and "RuntimeError: worker failed" in text


def test_the_file_keeps_only_recent_runs(log, monkeypatch):
    monkeypatch.setattr(crash_log, "MAX_BYTES", 4000)
    for i in range(40):
        crash_log.start(f"1.{i}")
        crash_log.write("x" * 200)
        crash_log.finish()
    text = log.read_text(encoding="utf-8")
    assert len(text.encode("utf-8")) <= 4000
    assert text.startswith(crash_log.START)
    assert "v1.39" in text and "v1.0 " not in text


def test_last_run_crashed_reads_only_the_last_run():
    ok = f"{crash_log.START} a\n{crash_log.CLEAN_EXIT} b\n"
    died = f"{crash_log.START} c\nstack\n"
    assert not crash_log.last_run_crashed("")
    assert not crash_log.last_run_crashed(ok)
    assert crash_log.last_run_crashed(ok + died)
    assert not crash_log.last_run_crashed(died + ok)
