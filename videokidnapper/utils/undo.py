# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Generic bounded undo/redo stack for editor-style state.

The stack stores full snapshots rather than command deltas — editor state
(text layers, crop rect, trim range, queued ranges) is small enough that
snapshot-and-restore is cheaper to implement, easier to reason about, and
avoids the bookkeeping a command-pattern implementation would require for
every mutation path.

Snapshots are compared with ``==`` to suppress no-op records; callers can
use any snapshot type that supports structural equality (dicts, tuples,
named tuples, frozen dataclasses).

The stack is ``threading``-safe only to the extent that all mutations
happen on the Tk main thread — Tkinter itself is not thread-safe, so
there's no reason to pay for a lock here.
"""


class UndoStack:
    """A bounded undo/redo stack keyed to a single "present" snapshot.

    Usage:
        stack = UndoStack(cap=50)
        stack.reset(initial_state)
        stack.record(state_after_edit)   # moves the old state to undo
        stack.undo()   # returns the previous state, or None if empty
        stack.redo()   # re-applies a state popped by undo(), or None

    ``record`` clears the redo stack, matching the "linear history"
    behavior users expect from editors. An explicit ``reset`` clears
    both stacks and installs a new baseline (used on video load).
    """

    def __init__(self, cap=50):
        if cap < 1:
            raise ValueError("cap must be >= 1")
        self._cap = cap
        self._present = None
        self._undo = []
        self._redo = []

    # ------------------------------------------------------------------
    def reset(self, snapshot):
        """Install ``snapshot`` as the present state, clearing history."""
        self._present = snapshot
        self._undo.clear()
        self._redo.clear()

    def record(self, snapshot):
        """Record a new present state.

        No-ops (``snapshot == present``) are ignored so debounced callers
        don't inflate the history with identical entries. Returns True
        when the stack actually changed.
        """
        if self._present is not None and snapshot == self._present:
            return False
        if self._present is not None:
            self._undo.append(self._present)
            if len(self._undo) > self._cap:
                # Drop the oldest entry. The cap matters: long editing
                # sessions can otherwise hold thousands of dict copies.
                self._undo.pop(0)
        self._present = snapshot
        self._redo.clear()
        return True

    # ------------------------------------------------------------------
    def can_undo(self):
        return bool(self._undo)

    def can_redo(self):
        return bool(self._redo)

    def present(self):
        return self._present

    def undo(self):
        """Pop the most-recent snapshot off the undo stack and return it.

        The state it displaces (the current ``present``) moves onto the
        redo stack so a subsequent ``redo()`` re-applies it. Returns
        ``None`` when there's nothing to undo.
        """
        if not self._undo:
            return None
        self._redo.append(self._present)
        self._present = self._undo.pop()
        return self._present

    def redo(self):
        """Symmetric counterpart to ``undo()``."""
        if not self._redo:
            return None
        self._undo.append(self._present)
        self._present = self._redo.pop()
        return self._present

    # ------------------------------------------------------------------
    def depth(self):
        """Return ``(undo_count, redo_count)`` — useful for UI state."""
        return len(self._undo), len(self._redo)

    def clear(self):
        """Drop both stacks and the present snapshot."""
        self._present = None
        self._undo.clear()
        self._redo.clear()
