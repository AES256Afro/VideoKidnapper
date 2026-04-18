# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Plugin discovery + version-gating tests.

These tests exercise the discovery layer only — they don't boot the Tk
event loop. Entry points are injected via the ``entry_points`` argument
to :func:`discover_plugins`, so we never have to actually install a
dummy pip package to test the loader.
"""
from types import SimpleNamespace

from videokidnapper.plugins import (
    ENTRY_POINT_GROUP, Plugin, discover_plugins,
)
from videokidnapper.plugins.discovery import _tuple_version, _version_mismatch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class GoodPlugin(Plugin):
    name = "GoodPlugin"
    version = "0.1.0"

    def __init__(self):
        self.ready_called_with = None

    def on_app_ready(self, app):
        self.ready_called_with = app


class BoomInInit(Plugin):
    name = "BoomInInit"

    def __init__(self):
        raise RuntimeError("nope")


class BoomOnLoad:
    """Not a real entry target — its ``load()`` raises."""


class PinnedOld(Plugin):
    name = "PinnedOld"
    max_app_version = "1.0.0"


class PinnedFuture(Plugin):
    name = "PinnedFuture"
    min_app_version = "99.0.0"


def _ep(name, target, load_exc=None):
    """Tiny EntryPoint stand-in for discover_plugins(entry_points=[...])."""
    def load():
        if load_exc is not None:
            raise load_exc
        return target
    return SimpleNamespace(
        name=name, load=load,
        dist=SimpleNamespace(name="test-pkg", version="0.0.1"),
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_entry_point_group_constant():
    assert ENTRY_POINT_GROUP == "videokidnapper.plugins"


def test_empty_discovery_returns_empty_list():
    assert discover_plugins(entry_points=[]) == []


def test_successful_plugin_is_instantiated():
    results = discover_plugins(entry_points=[_ep("good", GoodPlugin)])
    assert len(results) == 1
    entry = results[0]
    assert entry.error is None
    assert isinstance(entry.plugin, GoodPlugin)
    assert entry.name == "good"
    assert entry.dist_name == "test-pkg"
    assert entry.dist_version == "0.0.1"


def test_load_exception_is_captured_not_raised():
    results = discover_plugins(entry_points=[
        _ep("broken", None, load_exc=ImportError("boom")),
    ])
    assert len(results) == 1
    assert results[0].plugin is None
    assert "load error" in results[0].error


def test_init_exception_is_captured_not_raised():
    results = discover_plugins(entry_points=[_ep("boom", BoomInInit)])
    assert len(results) == 1
    assert results[0].plugin is None
    assert "init error" in results[0].error


def test_one_bad_plugin_does_not_stop_siblings():
    results = discover_plugins(entry_points=[
        _ep("boom", BoomInInit),
        _ep("good", GoodPlugin),
    ])
    assert len(results) == 2
    names = [r.name for r in results]
    assert names == ["boom", "good"]
    assert results[0].plugin is None
    assert isinstance(results[1].plugin, GoodPlugin)


def test_non_class_entry_point_is_used_directly():
    # Some authors register an instance rather than a class. That's fine.
    instance = GoodPlugin()
    results = discover_plugins(entry_points=[_ep("instance", instance)])
    assert results[0].plugin is instance


# ---------------------------------------------------------------------------
# Version gating
# ---------------------------------------------------------------------------

def test_app_version_below_min_is_skipped():
    results = discover_plugins(
        app_version="1.0.0",
        entry_points=[_ep("future", PinnedFuture)],
    )
    assert results[0].plugin is None
    assert "requires VideoKidnapper >=" in results[0].error


def test_app_version_at_or_above_max_is_skipped():
    results = discover_plugins(
        app_version="1.1.0",
        entry_points=[_ep("old", PinnedOld)],
    )
    assert results[0].plugin is None
    assert "requires VideoKidnapper <" in results[0].error


def test_plugin_with_no_bounds_always_passes_version_check():
    results = discover_plugins(
        app_version="99.99.99",
        entry_points=[_ep("good", GoodPlugin)],
    )
    assert results[0].plugin is not None


def test_missing_app_version_disables_gating():
    # When the caller doesn't pass an app_version, pinned plugins
    # still load (they'll just fail later if the API is missing).
    results = discover_plugins(entry_points=[_ep("old", PinnedOld)])
    assert results[0].plugin is not None


def test_tuple_version_handles_prerelease_and_build_tags():
    assert _tuple_version("1.2.3") == (1, 2, 3)
    assert _tuple_version("1.2.3-rc1") == (1, 2, 3)
    assert _tuple_version("1.2.3+gab1234") == (1, 2, 3)


def test_version_mismatch_returns_none_without_bounds():
    class P(Plugin):
        pass
    assert _version_mismatch(P(), "1.0.0") is None


def test_version_mismatch_on_bad_version_string_is_tolerant():
    class P(Plugin):
        min_app_version = "not-a-version"
    # Bad bound → treated as unenforceable; plugin loads.
    assert _version_mismatch(P(), "1.0.0") is None
