# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
import pytest

from videokidnapper.utils.undo import UndoStack


def test_fresh_stack_has_nothing_to_undo_or_redo():
    s = UndoStack()
    assert not s.can_undo()
    assert not s.can_redo()
    assert s.undo() is None
    assert s.redo() is None


def test_record_moves_present_to_undo():
    s = UndoStack()
    s.reset({"v": 0})
    assert s.record({"v": 1})
    assert s.can_undo()
    assert not s.can_redo()
    assert s.present() == {"v": 1}


def test_undo_returns_previous_state_and_enables_redo():
    s = UndoStack()
    s.reset({"v": 0})
    s.record({"v": 1})
    s.record({"v": 2})
    assert s.undo() == {"v": 1}
    assert s.present() == {"v": 1}
    assert s.can_redo()
    assert s.undo() == {"v": 0}
    assert not s.can_undo()


def test_redo_reapplies_undone_state():
    s = UndoStack()
    s.reset({"v": 0})
    s.record({"v": 1})
    s.undo()
    assert s.redo() == {"v": 1}
    assert s.present() == {"v": 1}
    assert not s.can_redo()


def test_record_after_undo_clears_redo_branch():
    s = UndoStack()
    s.reset({"v": 0})
    s.record({"v": 1})
    s.record({"v": 2})
    s.undo()             # present = {"v": 1}, redo has {"v": 2}
    assert s.can_redo()
    s.record({"v": 9})   # branching off kills the redo history
    assert not s.can_redo()
    assert s.present() == {"v": 9}


def test_identical_snapshots_are_ignored():
    s = UndoStack()
    s.reset({"v": 0})
    assert not s.record({"v": 0})
    assert not s.can_undo()


def test_cap_drops_oldest_entries():
    s = UndoStack(cap=3)
    s.reset({"v": 0})
    for i in range(1, 10):
        s.record({"v": i})
    # Cap only limits the undo stack; oldest entries fall off the bottom.
    assert s.depth() == (3, 0)
    # The oldest snapshots we can still reach are the last 3 pushed.
    assert s.undo() == {"v": 8}
    assert s.undo() == {"v": 7}
    assert s.undo() == {"v": 6}
    assert not s.can_undo()


def test_reset_clears_history():
    s = UndoStack()
    s.reset({"v": 0})
    s.record({"v": 1})
    s.record({"v": 2})
    s.reset({"v": 99})
    assert s.present() == {"v": 99}
    assert s.depth() == (0, 0)


def test_cap_must_be_positive():
    with pytest.raises(ValueError):
        UndoStack(cap=0)
