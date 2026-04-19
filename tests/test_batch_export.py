# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Batch-export pure helpers.

The UI layer owes the planner a deterministic, Tk-free core so a change
in widget code can't silently break job construction. These tests cover
the whole surface of ``videokidnapper/utils/batch.py``.
"""

from pathlib import Path

import pytest

from videokidnapper.utils.batch import (
    PLATFORM_INHERIT,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    BatchJob,
    extend_batch_jobs,
    is_supported_video,
    plan_batch_jobs,
    plan_output_path,
    summarise,
)


# ---------------------------------------------------------------------------
# is_supported_video

@pytest.mark.parametrize("name, expected", [
    ("video.mp4",   True),
    ("clip.MP4",    True),        # case-insensitive
    ("movie.mkv",   True),
    ("photo.jpg",   False),
    ("song.mp3",    False),
    ("no_ext",      False),
    ("archive.zip", False),
])
def test_is_supported_video(name, expected):
    assert is_supported_video(name) is expected


# ---------------------------------------------------------------------------
# plan_output_path

def test_plan_output_path_preserves_stem(tmp_path):
    src = tmp_path / "podcast_ep5.mp4"
    out = plan_output_path(src, tmp_path, "mp4")
    assert out.name == "podcast_ep5_batch.mp4"
    assert out.parent == tmp_path


def test_plan_output_path_normalises_extension(tmp_path):
    # ".mp4" and "mp4" and "MP4" should all behave the same.
    for ext in ("mp4", ".mp4", "MP4", ".MP4"):
        out = plan_output_path(tmp_path / "x.mov", tmp_path, ext)
        assert out.suffix == ".mp4"


def test_plan_output_path_collides_on_disk(tmp_path):
    # Pre-create the natural output name so the planner must pick _1.
    existing = tmp_path / "clip_batch.mp4"
    existing.write_text("")
    out = plan_output_path(tmp_path / "clip.mov", tmp_path, "mp4")
    assert out.name == "clip_batch_1.mp4"


def test_plan_output_path_collides_across_batch(tmp_path):
    taken: set[str] = set()
    a = plan_output_path(tmp_path / "a.mp4", tmp_path, "mp4", taken=taken)
    # Different source, same stem → second call must pick _1.
    b = plan_output_path(
        tmp_path / "subdir" / "a.mp4", tmp_path, "mp4", taken=taken,
    )
    assert a.name == "a_batch.mp4"
    assert b.name == "a_batch_1.mp4"
    assert len(taken) == 2


# ---------------------------------------------------------------------------
# plan_batch_jobs

def test_plan_batch_jobs_builds_queued_jobs(tmp_path):
    inputs = [tmp_path / "a.mp4", tmp_path / "b.mov"]
    jobs = plan_batch_jobs(inputs, tmp_path, "mp4")
    assert len(jobs) == 2
    assert all(j.status == STATUS_QUEUED for j in jobs)
    assert [j.index for j in jobs] == [0, 1]
    assert jobs[0].display_name == "a.mp4"


def test_plan_batch_jobs_skips_unsupported(tmp_path):
    inputs = [tmp_path / "a.mp4", tmp_path / "song.mp3", tmp_path / "b.mkv"]
    jobs = plan_batch_jobs(inputs, tmp_path, "mp4")
    # .mp3 is in the audio-only path, not the batch input filter.
    names = [j.display_name for j in jobs]
    assert names == ["a.mp4", "b.mkv"]


def test_plan_batch_jobs_deduplicates(tmp_path):
    dup = str(tmp_path / "a.mp4")
    jobs = plan_batch_jobs([dup, dup, dup], tmp_path, "mp4")
    assert len(jobs) == 1


def test_plan_batch_jobs_unique_outputs_for_same_stem(tmp_path):
    # Same source filename in two different folders — outputs must not collide.
    a = tmp_path / "src1" / "clip.mp4"
    b = tmp_path / "src2" / "clip.mp4"
    jobs = plan_batch_jobs([a, b], tmp_path, "mp4")
    assert len(jobs) == 2
    assert jobs[0].output_path != jobs[1].output_path


# ---------------------------------------------------------------------------
# BatchJob defaults

def test_batch_job_defaults():
    job = BatchJob(input_path="/tmp/foo.mp4", output_path="/out/foo_batch.mp4")
    assert job.status == STATUS_QUEUED
    assert job.error is None
    assert job.progress == 0.0
    assert job.display_name == "foo.mp4"


def test_batch_job_explicit_display_name_wins():
    job = BatchJob(
        input_path="/tmp/a/very/long/path/clip.mp4",
        output_path="/out/clip_batch.mp4",
        display_name="clip (renamed)",
    )
    assert job.display_name == "clip (renamed)"


# ---------------------------------------------------------------------------
# summarise

def test_summarise_empty():
    assert summarise([]) == "empty"


def test_summarise_mixed():
    jobs = [
        BatchJob("a", "a.mp4", status=STATUS_DONE),
        BatchJob("b", "b.mp4", status=STATUS_DONE),
        BatchJob("c", "c.mp4", status=STATUS_FAILED),
        BatchJob("d", "d.mp4", status=STATUS_QUEUED),
        BatchJob("e", "e.mp4", status=STATUS_PROCESSING),
    ]
    result = summarise(jobs)
    assert "2 done" in result
    assert "1 failed" in result
    assert "1 running" in result
    assert "1 queued" in result


def test_summarise_skips_zero_counts():
    jobs = [BatchJob("a", "a.mp4", status=STATUS_DONE)]
    result = summarise(jobs)
    # Only non-zero buckets appear in the summary.
    assert result == "1 done"


# ---------------------------------------------------------------------------
# Relative-path normalisation

def test_plan_batch_jobs_normalises_pathlike(tmp_path):
    # Pass a Path (not a string) through the planner — should round-trip.
    input_path = tmp_path / "x.mp4"
    jobs = plan_batch_jobs([input_path], tmp_path, "mp4")
    assert len(jobs) == 1
    # str(Path(...)) uses the platform separator; just make sure we
    # can recover the original basename.
    assert Path(jobs[0].input_path).name == "x.mp4"


# ---------------------------------------------------------------------------
# extend_batch_jobs: the re-entrant planner the UI calls on every Add.

def test_extend_preserves_per_row_state(tmp_path):
    # Build a queue, mutate a row's platform_override + status, then
    # add another file. The mutated row must survive unchanged.
    jobs = plan_batch_jobs([tmp_path / "a.mp4"], tmp_path, "mp4")
    jobs[0].platform_override = "Instagram Reel"
    jobs[0].status = STATUS_DONE

    extended = extend_batch_jobs(jobs, [tmp_path / "b.mp4"], tmp_path, "mp4")
    assert len(extended) == 2
    assert extended[0].platform_override == "Instagram Reel"
    assert extended[0].status == STATUS_DONE
    assert extended[1].platform_override == PLATFORM_INHERIT
    assert extended[1].status == STATUS_QUEUED


def test_extend_ignores_duplicate_re_drops(tmp_path):
    jobs = plan_batch_jobs([tmp_path / "a.mp4"], tmp_path, "mp4")
    jobs[0].status = STATUS_FAILED
    jobs[0].error = "bad codec"

    # Drop the same path again — must NOT reset the failure state.
    extended = extend_batch_jobs(jobs, [tmp_path / "a.mp4"], tmp_path, "mp4")
    assert len(extended) == 1
    assert extended[0].status == STATUS_FAILED
    assert extended[0].error == "bad codec"


def test_extend_reindexes_after_extension(tmp_path):
    jobs = plan_batch_jobs([tmp_path / "a.mp4", tmp_path / "b.mp4"], tmp_path, "mp4")
    extended = extend_batch_jobs(
        jobs, [tmp_path / "c.mp4"], tmp_path, "mp4",
    )
    assert [j.index for j in extended] == [0, 1, 2]


def test_extend_does_not_mutate_input(tmp_path):
    # extend_batch_jobs returns a fresh list; callers can trust that
    # holding a reference to the old list remains safe.
    jobs = plan_batch_jobs([tmp_path / "a.mp4"], tmp_path, "mp4")
    original_id = id(jobs)
    extended = extend_batch_jobs(jobs, [tmp_path / "b.mp4"], tmp_path, "mp4")
    assert id(extended) != original_id
    assert len(jobs) == 1  # untouched


# ---------------------------------------------------------------------------
# BatchJob serialisation — persistence round-trip.

def test_to_dict_captures_all_fields():
    job = BatchJob(
        input_path="/src/a.mp4",
        output_path="/out/a_batch.mp4",
        status=STATUS_DONE,
        error=None,
        progress=1.0,
        index=3,
        display_name="a.mp4",
        platform_override="TikTok",
    )
    d = job.to_dict()
    assert d["input_path"] == "/src/a.mp4"
    assert d["output_path"] == "/out/a_batch.mp4"
    assert d["status"] == STATUS_DONE
    assert d["progress"] == 1.0
    assert d["platform_override"] == "TikTok"


def test_from_dict_round_trips():
    original = BatchJob(
        input_path="/src/a.mp4",
        output_path="/out/a_batch.mp4",
        status=STATUS_FAILED,
        error="codec mismatch",
        progress=0.42,
        index=5,
        display_name="a.mp4",
        platform_override="Discord (8 MB)",
    )
    restored = BatchJob.from_dict(original.to_dict())
    assert restored == original


def test_from_dict_normalises_in_flight_status():
    # A crash mid-encode leaves status=processing in the persisted file.
    # On load, processing must become queued so the row re-runs cleanly.
    d = BatchJob(
        input_path="/src/a.mp4", output_path="/out/a.mp4",
        status=STATUS_PROCESSING, progress=0.6,
    ).to_dict()
    restored = BatchJob.from_dict(d)
    assert restored.status == STATUS_QUEUED
    assert restored.progress == 0.0


def test_from_dict_keeps_terminal_statuses():
    # Done / failed / cancelled survive — users shouldn't have to
    # re-queue everything just because the app restarted.
    for status in (STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED):
        d = BatchJob(
            input_path="/a", output_path="/b", status=status,
        ).to_dict()
        assert BatchJob.from_dict(d).status == status


def test_from_dict_drops_unknown_fields():
    # A newer app version may have added fields. Loading in an older
    # build must ignore them rather than crashing.
    d = {
        "input_path":  "/src/a.mp4",
        "output_path": "/out/a_batch.mp4",
        "future_field": {"nested": "value"},
    }
    restored = BatchJob.from_dict(d)
    assert restored.input_path == "/src/a.mp4"
    assert restored.status == STATUS_QUEUED


def test_from_dict_rejects_missing_required():
    with pytest.raises(ValueError):
        BatchJob.from_dict({"status": STATUS_QUEUED})  # no paths


def test_from_dict_normalises_unknown_status():
    d = {
        "input_path":  "/src/a.mp4",
        "output_path": "/out/a_batch.mp4",
        "status": "fizzbuzz",   # garbage — treat as queued
    }
    restored = BatchJob.from_dict(d)
    assert restored.status == STATUS_QUEUED


# ---------------------------------------------------------------------------
# PLATFORM_INHERIT constant — used as the "no override" sentinel in both
# the batch runner and the persisted queue.

def test_platform_inherit_is_default():
    job = BatchJob(input_path="/a", output_path="/b")
    assert job.platform_override == PLATFORM_INHERIT
