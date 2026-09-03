# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Reordering and layout of the queued-range chips.

With "Concat ranges" on, **the queue order is the output order**. Before
these controls the only way to resequence was to delete rows and re-find
every in- and out-point.

The wrapping matters as much as the reordering: chips packed into a
single row ran off the edge of the window at three ranges, so a queue
you cannot see is a queue you cannot reorder.

Tk is needed for a real widget, so the module skips without a display —
the same reason the rest of ``ui/`` is untested on CI.
"""

import pytest


ctk = pytest.importorskip("customtkinter", reason="needs customtkinter")


@pytest.fixture(scope="module")
def root():
    """One Tk root for the module.

    Creating and destroying a root per test crashes the interpreter —
    Tk does not expect to be torn down and rebuilt repeatedly in one
    process. Each test gets a fresh widget on a shared root instead.
    """
    try:
        instance = ctk.CTk()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}: {exc}")
    instance.geometry("1000x700")
    yield instance
    try:
        instance.destroy()
    except Exception:
        pass


@pytest.fixture
def queue(root):
    from videokidnapper.ui.multi_range import RangeQueue

    # Each test resizes freely, so restore the width other tests assume.
    root.geometry("1000x700")
    root.update_idletasks()
    changes = []
    widget = RangeQueue(root, on_change=lambda: changes.append(1))
    widget.pack(fill="x")
    root.update_idletasks()
    yield widget, changes, root
    widget.destroy()


def _add(widget, count):
    for i in range(count):
        widget.add_range(i * 10, i * 10 + 7)


def _order(widget):
    return [round(s) for s, _e in widget.get_ranges()]


# ------------------------------------------------------------ reordering

def test_move_later_and_earlier(queue):
    widget, _changes, _root = queue
    _add(widget, 3)
    assert _order(widget) == [0, 10, 20]

    assert widget.move_range(0, 1) is True
    assert _order(widget) == [10, 0, 20]

    assert widget.move_range(2, -1) is True
    assert _order(widget) == [10, 20, 0]


def test_moves_off_either_end_are_no_ops(queue):
    widget, changes, _root = queue
    _add(widget, 3)
    before = _order(widget)

    assert widget.move_range(0, -1) is False
    assert widget.move_range(2, 1) is False
    assert _order(widget) == before
    assert changes == [], "a no-op must not report a change"


def test_a_stale_index_does_not_raise(queue):
    """Chips are rebuilt on every change, so a click can arrive with an
    index that no longer exists."""
    widget, _changes, _root = queue
    _add(widget, 2)
    assert widget.move_range(99, 1) is False
    assert widget.move_range(-3, 1) is False
    assert len(widget.get_ranges()) == 2


def test_reorder_reports_a_change(queue):
    """The parent takes an undo snapshot and re-evaluates the export
    button from this callback — a reorder needs both as much as a
    removal does."""
    widget, changes, _root = queue
    _add(widget, 3)
    changes.clear()
    widget.move_range(0, 1)
    assert len(changes) == 1


def test_removal_still_reports_a_change(queue):
    widget, changes, _root = queue
    _add(widget, 2)
    changes.clear()
    widget._remove(0)
    assert len(changes) == 1
    assert len(widget.get_ranges()) == 1


# ---------------------------------------------------------------- chips

def test_chip_shows_duration(queue):
    """Timecodes alone make every chip look alike; duration is what you
    reason about when sequencing."""
    widget, _changes, root = queue
    widget.add_range(0, 7)
    root.update_idletasks()
    labels = [
        w.cget("text")
        for chip in widget._chip_frames
        for w in chip.winfo_children()
        if isinstance(w, ctk.CTkLabel)
    ]
    assert labels and "7.0s" in labels[0]
    assert "0:00" in labels[0] and "0:07" in labels[0]


def test_end_chips_disable_the_move_they_cannot_do(queue):
    widget, _changes, root = queue
    _add(widget, 3)
    root.update_idletasks()

    def states(chip):
        return [w.cget("state") for w in chip.winfo_children()
                if isinstance(w, ctk.CTkButton)]

    first, middle, last = (states(c) for c in widget._chip_frames)
    assert first[0] == "disabled", "first chip cannot move earlier"
    assert last[1] == "disabled", "last chip cannot move later"
    assert "disabled" not in middle[:2], "a middle chip can move either way"


# -------------------------------------------------------------- wrapping

def test_chips_wrap_instead_of_running_off_the_edge(queue):
    """The regression this guards: eight chips in one row is ~1900px of
    content in a ~980px window."""
    widget, _changes, root = queue
    _add(widget, 8)
    root.update_idletasks()
    widget._on_chips_resize()
    root.update_idletasks()

    widest = max(c.winfo_reqwidth() for c in widget._chip_frames)
    available = widget.chips_frame.winfo_width()
    assert widget._chip_columns * widest <= available, "a row still overflows"
    rows = max(int(c.grid_info()["row"]) for c in widget._chip_frames) + 1
    assert rows > 1, "eight chips should not fit on one row"


def test_narrowing_the_window_uses_fewer_columns(queue):
    widget, _changes, root = queue
    _add(widget, 8)
    root.update_idletasks()
    widget._on_chips_resize()
    wide = widget._chip_columns

    root.geometry("620x700")
    root.update_idletasks()
    widget._on_chips_resize()
    assert widget._chip_columns < wide


def test_reflow_is_stable_when_nothing_changes(queue):
    """Re-gridding fires <Configure>, so reacting to every event would
    loop. A resize that does not change the column count must be inert."""
    widget, _changes, root = queue
    _add(widget, 5)
    root.update_idletasks()
    widget._on_chips_resize()
    columns = widget._chip_columns
    for _ in range(3):
        widget._on_chips_resize()
    assert widget._chip_columns == columns


def test_clearing_resets_the_layout_state(queue):
    widget, _changes, root = queue
    _add(widget, 4)
    root.update_idletasks()
    widget.clear()
    assert widget.get_ranges() == []
    assert widget._chip_columns == 0
