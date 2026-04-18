# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""VideoKidnapper plugin system.

Plugins extend the app via the standard Python ``entry_points`` mechanism.
A plugin is a regular pip-installable package whose ``pyproject.toml``
declares one or more entries under the ``videokidnapper.plugins`` group,
each pointing at a class that derives from :class:`Plugin`:

.. code-block:: toml

    [project.entry-points."videokidnapper.plugins"]
    my_plugin = "my_pkg.plugin:MyPlugin"

At startup VideoKidnapper discovers every such entry, instantiates the
class, and calls ``on_app_ready(app)``. From that hook a plugin can
register tabs, add export options, register filters, or anything else
the ``App`` object exposes. See ``docs/PLUGINS.md`` for the full API.

Because the plugin mechanism relies on Python's packaging infrastructure
rather than a bespoke file-scan, plugins are:

- carried by their own license (Apache-2.0 applies to VideoKidnapper
  itself, not to third-party plugin packages),
- installed / uninstalled with ``pip install`` / ``pip uninstall``,
- visible via ``pip show`` and ``importlib.metadata`` like any other
  Python package.

A failure in one plugin never kills the app: ``discover_plugins``
catches load-time exceptions and logs them, and the hook dispatcher in
``app.py`` wraps each lifecycle call in its own try/except.
"""

from videokidnapper.plugins.base import Plugin
from videokidnapper.plugins.discovery import (
    ENTRY_POINT_GROUP, DiscoveredPlugin, discover_plugins,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "DiscoveredPlugin",
    "Plugin",
    "discover_plugins",
]
