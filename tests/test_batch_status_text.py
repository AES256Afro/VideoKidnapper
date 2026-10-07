# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Plain-English status labels on Batch queue rows."""

from videokidnapper.ui.batch_export_tab import status_text
from videokidnapper.utils.batch import (
    STATUS_CANCELLED, STATUS_DONE, STATUS_FAILED, STATUS_PROCESSING,
    STATUS_QUEUED, BatchJob,
)


def _job(tmp_path, status, **extra):
    job = BatchJob(index=0, input_path=str(tmp_path / "in.mp4"),
                   output_path=str(tmp_path / "out.mp4"))
    job.status = status
    for key, value in extra.items():
        setattr(job, key, value)
    return job


def test_waiting_and_stopped(tmp_path):
    assert status_text(_job(tmp_path, STATUS_QUEUED)) == "Waiting"
    assert status_text(_job(tmp_path, STATUS_CANCELLED)) == "Stopped"


def test_processing_shows_percent(tmp_path):
    assert status_text(_job(tmp_path, STATUS_PROCESSING, progress=0.48)) == "Exporting · 48%"


def test_done_shows_size_when_file_exists(tmp_path):
    (tmp_path / "out.mp4").write_bytes(b"x" * 2048)
    assert status_text(_job(tmp_path, STATUS_DONE)).startswith("Done · ")
    (tmp_path / "out.mp4").unlink()
    assert status_text(_job(tmp_path, STATUS_DONE)) == "Done"


def test_failed_includes_reason(tmp_path):
    assert status_text(_job(tmp_path, STATUS_FAILED, error="source moved")) == "Failed · source moved"
    assert status_text(_job(tmp_path, STATUS_FAILED, error=None)) == "Failed"
