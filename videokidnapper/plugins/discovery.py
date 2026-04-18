# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Entry-point-based plugin discovery.

Uses ``importlib.metadata.entry_points`` to find every third-party
package that declares an entry under the ``videokidnapper.plugins``
group. Each entry point's object is loaded; if it's a class, an
instance is created, otherwise it's used as-is. Load failures are
captured — a single broken plugin should never take the app down.

Version compatibility is checked here rather than at the call site so
the same rule applies whether a plugin is loaded at startup, enumerated
in a "plugins" dialog, or instantiated by tests.
"""

import importlib.metadata as md
import logging
from collections import namedtuple


ENTRY_POINT_GROUP = "videokidnapper.plugins"

logger = logging.getLogger(__name__)


# DiscoveredPlugin bundles the plugin instance with the entry-point
# metadata we want to keep around for introspection (plugins list,
# error reporting, etc.).
#
# ``error`` is ``None`` on a successful load; otherwise it's a short
# human-readable reason the plugin was skipped (load exception,
# version-range mismatch, ...). The instance is ``None`` in that case.
DiscoveredPlugin = namedtuple(
    "DiscoveredPlugin",
    "name dist_name dist_version plugin error",
)


def discover_plugins(
    app_version=None,
    group=ENTRY_POINT_GROUP,
    entry_points=None,
):
    """Return every discovered plugin, successful or not.

    Parameters
    ----------
    app_version : str, optional
        VideoKidnapper's running version. When provided, plugins with
        ``min_app_version`` / ``max_app_version`` outside this version
        are reported as skipped (with an ``error`` string) instead of
        being loaded.
    group : str
        Entry-point group to query. Defaults to ``videokidnapper.plugins``.
    entry_points : iterable, optional
        Injected for tests — skip importlib.metadata and use this list
        of objects that look like EntryPoints. In production, leave this
        ``None`` and discovery uses the real entry-point table.
    """
    eps = _list_entry_points(group) if entry_points is None else list(entry_points)
    results = []
    for ep in eps:
        results.append(_load_one(ep, app_version))
    return results


def _list_entry_points(group):
    """Cross-version accessor for entry points in a specific group.

    Python 3.10 added ``entry_points(group=...)``; 3.9 returns a
    dict-like keyed by group. The try/except covers both.
    """
    try:
        eps = md.entry_points()
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("entry_points() failed: %s", exc)
        return []
    # 3.10+: EntryPoints.select(group=...)
    if hasattr(eps, "select"):
        try:
            return list(eps.select(group=group))
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("entry_points.select() failed: %s", exc)
            return []
    # 3.9: dict-like; missing group returns []
    try:
        return list(eps.get(group, []))  # type: ignore[union-attr]
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("entry_points dict access failed: %s", exc)
        return []


def _load_one(ep, app_version):
    name = getattr(ep, "name", "<unknown>")
    dist_name, dist_version = _distribution_info(ep)

    try:
        obj = ep.load()
    except Exception as exc:
        logger.warning("Plugin %r failed to load: %s", name, exc)
        return DiscoveredPlugin(
            name=name,
            dist_name=dist_name,
            dist_version=dist_version,
            plugin=None,
            error=f"load error: {exc}",
        )

    try:
        instance = obj() if isinstance(obj, type) else obj
    except Exception as exc:
        logger.warning("Plugin %r failed to instantiate: %s", name, exc)
        return DiscoveredPlugin(
            name=name,
            dist_name=dist_name,
            dist_version=dist_version,
            plugin=None,
            error=f"init error: {exc}",
        )

    incompatible = _version_mismatch(instance, app_version)
    if incompatible:
        return DiscoveredPlugin(
            name=name,
            dist_name=dist_name,
            dist_version=dist_version,
            plugin=None,
            error=incompatible,
        )

    return DiscoveredPlugin(
        name=name,
        dist_name=dist_name,
        dist_version=dist_version,
        plugin=instance,
        error=None,
    )


def _distribution_info(ep):
    """Best-effort lookup of the pip package that provided this entry point."""
    dist = getattr(ep, "dist", None)
    if dist is None:
        return None, None
    return (
        getattr(dist, "name", None) or getattr(dist, "metadata", {}).get("Name"),
        getattr(dist, "version", None),
    )


def _version_mismatch(plugin, app_version):
    """Return a reason string if the plugin's range excludes ``app_version``.

    Returns ``None`` when the plugin is compatible (or when app_version
    was not provided / either bound is unset). Uses simple tuple-of-ints
    comparison, which handles the ``MAJOR.MINOR.PATCH`` scheme the
    project uses. Pre-release suffixes (``1.2.0-rc1``) are truncated at
    the first ``-`` so a plugin pinned to ``>=1.2.0`` accepts them.
    """
    if not app_version:
        return None
    lo = getattr(plugin, "min_app_version", None)
    hi = getattr(plugin, "max_app_version", None)
    if not lo and not hi:
        return None
    try:
        av = _tuple_version(app_version)
    except ValueError:
        return None
    if lo:
        try:
            if av < _tuple_version(lo):
                return f"requires VideoKidnapper >= {lo}"
        except ValueError:
            pass
    if hi:
        try:
            if av >= _tuple_version(hi):
                return f"requires VideoKidnapper < {hi}"
        except ValueError:
            pass
    return None


def _tuple_version(s):
    head = s.split("-", 1)[0].split("+", 1)[0]
    parts = head.split(".")
    return tuple(int(p) for p in parts)
