# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Pure helpers for the Batch Export tab.

All the UI-free logic lives here — job-record construction, output-path
planning, filename collision handling — so it can be exercised without
standing up a Tk root. The tab itself only wires these to widgets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Iterable, Optional

from videokidnapper.config import SUPPORTED_VIDEO_EXTENSIONS


# Status values a BatchJob can take. Strings rather than an Enum so they
# round-trip cleanly through Tk StringVar bindings and telemetry logs.
STATUS_QUEUED     = "queued"
STATUS_PROCESSING = "processing"
STATUS_DONE       = "done"
STATUS_FAILED     = "failed"
STATUS_CANCELLED  = "cancelled"
STATUS_SKIPPED    = "skipped"

_TERMINAL_STATUSES = frozenset({STATUS_DONE, STATUS_FAILED, STATUS_CANCELLED, STATUS_SKIPPED})
_VALID_STATUSES = _TERMINAL_STATUSES | {STATUS_QUEUED, STATUS_PROCESSING}

# Sentinel platform-override value meaning "use the batch-wide Quality /
# aspect settings". Any other value must be a valid key in the platform
# preset registry (validated at run time by the UI, not here, so this
# module stays free of UI-layer imports).
PLATFORM_INHERIT = "Inherit"


@dataclass
class BatchJob:
    """One file in the batch queue.

    ``output_path`` is computed at plan time so every row in the UI can
    show the final destination before the user clicks Start — no "where
    did it go?" surprises.
    """

    input_path: str
    output_path: str
    status: str = STATUS_QUEUED
    error: Optional[str] = None
    # Progress callbacks write the worker's 0..1 progress here so the UI
    # can render a per-row bar without having to pipe it through a Queue.
    progress: float = 0.0
    # Index inside the batch — useful for log messages and deterministic
    # ordering in tests; set automatically by plan_batch_jobs().
    index: int = 0

    # Human-readable filename for the UI. Kept as a field (not a property)
    # so dataclass equality compares what the user actually sees.
    display_name: str = field(default="")

    # Platform-preset override for this row alone. ``PLATFORM_INHERIT``
    # (default) means "use the batch-wide Quality / aspect". Any other
    # value is a key in PLATFORM_PRESETS; the runner looks it up at
    # dispatch time and overrides this row's preset + aspect.
    platform_override: str = PLATFORM_INHERIT

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = Path(self.input_path).name

    # ------------------------------------------------------------------
    # JSON round-trip — ``dataclasses.asdict`` handles the encode; the
    # decode does its own field-by-field filtering so settings written
    # by a newer version of the app can still be loaded by an older one
    # (forward compat, one-way). Unknown fields are dropped.
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BatchJob":
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        # Required fields: bail out with sentinel values rather than
        # raising, so one malformed row in settings doesn't nuke the
        # whole queue on restore.
        if "input_path" not in filtered or "output_path" not in filtered:
            raise ValueError("missing required path fields")
        # Normalise a persisted in-progress status into queued on load —
        # we just crashed / were force-quit mid-encode, so "processing"
        # is a lie. Failed / cancelled stay intact for the UI to show.
        status = filtered.get("status", STATUS_QUEUED)
        if status == STATUS_PROCESSING or status not in _VALID_STATUSES:
            filtered["status"] = STATUS_QUEUED
            filtered["progress"] = 0.0
        return cls(**filtered)


def is_supported_video(path: str | Path) -> bool:
    """True iff ``path`` has an extension the app's backends can open.

    Shared between the drag-drop handler and the file-picker filter so
    both reject the same set of unsupported formats.
    """
    ext = Path(path).suffix.lower()
    return ext in SUPPORTED_VIDEO_EXTENSIONS


def plan_output_path(
    input_path: str | Path,
    output_dir: str | Path,
    extension: str,
    taken: Optional[set[str]] = None,
) -> Path:
    """Compute the destination path for a single batch job.

    Preserves the source stem so ``my_video.mov`` becomes
    ``my_video_batch.mp4``. On collision (another job in the same batch
    already claimed the name, or the file already exists on disk), a
    numeric ``_1`` / ``_2`` suffix is appended until a free slot is
    found. ``taken`` is the set of previously-planned paths in the
    current batch — pass the same set to every call for a consistent
    plan across the whole queue.
    """
    out_dir = Path(output_dir)
    stem = Path(input_path).stem
    ext = extension.lower().lstrip(".")
    candidate = out_dir / f"{stem}_batch.{ext}"
    counter = 1
    taken = taken if taken is not None else set()
    while str(candidate) in taken or candidate.exists():
        candidate = out_dir / f"{stem}_batch_{counter}.{ext}"
        counter += 1
    taken.add(str(candidate))
    return candidate


def plan_batch_jobs(
    input_paths: Iterable[str | Path],
    output_dir: str | Path,
    extension: str,
) -> list[BatchJob]:
    """Build the full ``BatchJob`` list for a given set of inputs.

    Skips unsupported file types and deduplicates repeat paths so a
    double-drop of the same file doesn't silently encode it twice.
    Orders jobs in the input order minus drops so the UI matches what
    the user added.
    """
    return extend_batch_jobs([], input_paths, output_dir, extension)


def extend_batch_jobs(
    existing: list[BatchJob],
    input_paths: Iterable[str | Path],
    output_dir: str | Path,
    extension: str,
) -> list[BatchJob]:
    """Append new inputs to ``existing`` without clobbering per-row state.

    The UI calls this on every Add Files / drop so existing rows keep
    their status, error, progress bar, and ``platform_override``. Inputs
    already present in ``existing`` are ignored (re-dropping the same
    file doesn't duplicate it or reset its state). Unknown file types
    are silently dropped. Index values are recomputed so the returned
    list stays contiguous.
    """
    seen_inputs: set[str] = {job.input_path for job in existing}
    taken_outputs: set[str] = {job.output_path for job in existing}
    # Copy so callers can safely mutate their own list without feedback.
    jobs: list[BatchJob] = list(existing)
    for raw in input_paths:
        path = str(Path(raw))
        if path in seen_inputs:
            continue
        if not is_supported_video(path):
            continue
        seen_inputs.add(path)
        output = plan_output_path(path, output_dir, extension, taken=taken_outputs)
        jobs.append(BatchJob(
            input_path=path,
            output_path=str(output),
        ))
    # Reindex after the extension — keeps UI ordering stable and
    # survives later removals of arbitrary rows.
    for i, job in enumerate(jobs):
        job.index = i
    return jobs


def summarise(jobs: list[BatchJob]) -> str:
    """One-line progress summary for the footer / toasts.

    Shape: ``"2 done · 1 failed · 3 queued"``. Zero-count sections are
    omitted so short batches produce short messages.
    """
    counts = {
        STATUS_DONE:       0,
        STATUS_FAILED:     0,
        STATUS_PROCESSING: 0,
        STATUS_QUEUED:     0,
        STATUS_CANCELLED:  0,
        STATUS_SKIPPED:    0,
    }
    for job in jobs:
        counts[job.status] = counts.get(job.status, 0) + 1
    parts = []
    for label, key in [
        ("done",       STATUS_DONE),
        ("failed",     STATUS_FAILED),
        ("running",    STATUS_PROCESSING),
        ("queued",     STATUS_QUEUED),
        ("cancelled",  STATUS_CANCELLED),
        ("skipped",    STATUS_SKIPPED),
    ]:
        if counts.get(key):
            parts.append(f"{counts[key]} {label}")
    return " · ".join(parts) if parts else "empty"
