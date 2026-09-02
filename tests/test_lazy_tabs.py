# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Batch and History are built on first view, not at startup.

Constructing every tab up front cost 968 ms of window build, measured
in situ on this tree — 365 ms of it Batch and 93 ms History, two tabs
most sessions never open. Deferring them halved the build.

The deferral is easy to undo by accident: any code that reaches for
``app.batch_export_tab`` or ``app.history_tab`` during startup builds
the thing it was meant to skip. These tests pin both the deferral and
the escape hatch (``_tab_if_built``) that lets callers poke an
already-open tab without paying for one that is not.

Tk is needed for a real window, so the whole module skips when a
display is unavailable — the same reason the rest of ``ui/`` is
untested on CI.
"""

import pytest


ctk = pytest.importorskip("customtkinter", reason="needs customtkinter")


def _app_class():
    from videokidnapper import app as app_module

    return next(
        obj for obj in vars(app_module).values()
        if isinstance(obj, type) and hasattr(obj, "_bind_accel")
    )


@pytest.fixture
def app():
    from videokidnapper import app as app_module

    try:
        instance = _app_class()()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no usable display: {type(exc).__name__}: {exc}")
    instance.update_idletasks()

    # App.__init__ shows the prerequisite-setup landing and returns
    # early when ffmpeg is absent, so the tabs are never built. That is
    # correct behaviour, not a failure — but nothing here is meaningful
    # without the real UI, and without this guard the tests fail with a
    # confusing AttributeError from Tk's attribute fallthrough.
    if not hasattr(instance, "_built_tabs"):
        instance.destroy()
        pytest.skip("ffmpeg missing — app showed the setup landing, not the tabs")

    yield instance, app_module
    try:
        instance.destroy()
    except Exception:
        pass


def test_startup_defers_batch_and_history(app):
    """The deferral itself, plus the two tabs that must stay eager."""
    instance, module = app

    assert instance._built_tabs == {}, (
        "something reached for a deferred tab during startup — that "
        "rebuilds the cost this deferral removed"
    )
    # Studio is what the user sees first.
    assert instance.trim_tab.winfo_exists()
    # Debug receives log lines from the global exception handler and the
    # ffmpeg failure logger, which can fire before it is ever opened.
    assert instance.debug_tab.winfo_exists()

    # The non-forcing accessor exists so an export can refresh History
    # only when History is actually open. It must not build one.
    assert instance._tab_if_built(module.TAB_HISTORY) is None
    assert instance._built_tabs == {}, "_tab_if_built built something"

    # Eager tabs have no factory, and an unknown name is not an error —
    # _on_tab_changed fires for every tab, not just deferred ones.
    assert instance._ensure_tab(module.TAB_STUDIO) is None
    assert instance._ensure_tab("nonexistent") is None


def test_tabs_build_on_first_view_and_are_cached(app):
    instance, module = app

    for name in (module.TAB_BATCH, module.TAB_HISTORY):
        assert name not in instance._built_tabs
        instance.tabview.set(name)
        instance._on_tab_changed()
        instance.update_idletasks()
        assert name in instance._built_tabs, f"selecting {name!r} did not build it"
        assert instance._built_tabs[name].winfo_exists()

    # Built once, then reused — and the property returns that instance.
    first = instance.batch_export_tab
    assert first is instance.batch_export_tab, "the tab was rebuilt"
    assert first is instance._built_tabs[module.TAB_BATCH]
    assert instance.history_tab is instance._built_tabs[module.TAB_HISTORY]


def test_a_failing_factory_does_not_wedge_tab_switching(app, monkeypatch):
    instance, module = app

    def boom():
        raise RuntimeError("simulated failure")

    monkeypatch.setitem(instance._lazy_tabs, module.TAB_BATCH, boom)
    instance.tabview.set(module.TAB_BATCH)
    instance._on_tab_changed()  # must not raise
    assert module.TAB_BATCH not in instance._built_tabs
