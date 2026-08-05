# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Guards the wheel against silently dropping a subpackage.

The 1.8.0 wheel shipped without ``videokidnapper.core.ffmpeg`` and
``videokidnapper.plugins`` because ``pyproject.toml`` carried a
hand-maintained ``packages = [...]`` list that nobody updated when those
subpackages were split out. ``pip install videokidnapper`` installed
cleanly and then raised ``ModuleNotFoundError`` the moment anything
touched the ffmpeg backend.

pyproject now uses ``[tool.setuptools.packages.find]``, which cannot go
stale. These tests are the tripwire in case someone reverts to an
explicit list — they compare what setuptools would ship against what
actually exists on disk, and assert every package is importable.
"""

import fnmatch
import importlib
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG_ROOT = ROOT / "videokidnapper"


def _packages_on_disk():
    """Every directory under videokidnapper/ that is a real package."""
    found = {"videokidnapper"}
    for init in PKG_ROOT.rglob("__init__.py"):
        rel = init.parent.relative_to(ROOT)
        if "__pycache__" in rel.parts:
            continue
        found.add(".".join(rel.parts))
    return found


def _load_pyproject():
    try:
        import tomllib  # 3.11+
    except ModuleNotFoundError:  # pragma: no cover - 3.9/3.10
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            return None
    with open(ROOT / "pyproject.toml", "rb") as fh:
        return tomllib.load(fh)


def _packages_setuptools_would_ship():
    """Resolve the shipped package set from the *actual* pyproject config.

    Deliberately reads the config rather than assuming auto-discovery —
    otherwise a revert to a hand-maintained ``packages = [...]`` list
    would sail past this test, which is the exact failure being guarded.

    ``find_packages`` is reimplemented here rather than imported:
    setuptools is no longer present in a fresh Python 3.12 environment,
    and CI installs only ``requirements.txt`` plus pytest. The matching
    rules (fnmatch against the dotted name, exclude beating include) are
    setuptools' own.
    """
    cfg = _load_pyproject()
    if cfg is None:  # no TOML parser available (3.9/3.10 without tomli)
        return {p for p in _packages_on_disk()
                if fnmatch.fnmatch(p, "videokidnapper*")}

    setuptools_cfg = cfg.get("tool", {}).get("setuptools", {})
    explicit = setuptools_cfg.get("packages")
    if isinstance(explicit, list):
        # Hand-maintained list — ship exactly what it names.
        return set(explicit)

    find_cfg = explicit.get("find", {}) if isinstance(explicit, dict) else {}
    include = find_cfg.get("include") or ["*"]
    exclude = find_cfg.get("exclude") or []

    return {
        pkg
        for pkg in _packages_on_disk()
        if any(fnmatch.fnmatch(pkg, pat) for pat in include)
        and not any(fnmatch.fnmatch(pkg, pat) for pat in exclude)
    }


def test_every_subpackage_is_shipped():
    """No package on disk may be missing from the distribution."""
    on_disk = _packages_on_disk()
    shipped = _packages_setuptools_would_ship()
    missing = on_disk - shipped
    assert not missing, (
        "these packages exist but would NOT be installed by pip: "
        f"{sorted(missing)} — a user's `pip install` would raise "
        "ModuleNotFoundError. Check [tool.setuptools.packages.find] "
        "in pyproject.toml."
    )


def test_known_subpackages_present():
    """Explicit floor: the two that 1.8.0 dropped."""
    shipped = _packages_setuptools_would_ship()
    for pkg in ("videokidnapper.core.ffmpeg", "videokidnapper.plugins"):
        assert pkg in shipped, f"{pkg} would not be shipped"


def test_every_shipped_package_imports():
    """A shipped package that cannot be imported is just as broken.

    Skips the UI tree: those modules import tkinter at load time, which
    is unavailable on the headless CI runner (same reason ci.yml scopes
    its collection).
    """
    failures = []
    for pkg in sorted(_packages_setuptools_would_ship()):
        if pkg.startswith("videokidnapper.ui"):
            continue
        try:
            importlib.import_module(pkg)
        except Exception as exc:  # pragma: no cover - failure path
            failures.append(f"{pkg}: {type(exc).__name__}: {exc}")
    assert not failures, "packages failed to import:\n" + "\n".join(failures)


def test_ffmpeg_backend_facade_resolves():
    """The compat facade re-exports from core.ffmpeg — the exact import
    that blew up on the 1.8.0 wheel."""
    sys.modules.pop("videokidnapper.core.ffmpeg_backend", None)
    mod = importlib.import_module("videokidnapper.core.ffmpeg_backend")
    for symbol in mod.__all__:
        assert hasattr(mod, symbol), f"facade is missing {symbol}"
