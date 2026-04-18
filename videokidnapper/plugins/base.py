# SPDX-FileCopyrightText: 2026 Christopher Courtney <https://github.com/AES256Afro>
# SPDX-License-Identifier: Apache-2.0
"""Base class for VideoKidnapper plugins.

Subclass :class:`Plugin`, fill in ``name`` / ``version``, and override
whichever lifecycle hooks you need. Every hook has a no-op default so a
minimal plugin can be just a class with a name — useful for "info-only"
plugins that just want to show up in the plugins list.

Hook signatures
---------------

``on_app_ready(app)``
    Called once after the main window is fully built (tabs, header,
    status bar). The ``app`` argument is the live ``videokidnapper.App``
    instance — use ``app.register_tab(name, factory)``,
    ``app.tabview``, ``app.status_bar``, etc. to wire your UI in.

``on_shutdown(app)``
    Called when the app is about to close. Flush state, close sockets,
    stop background threads. Default: no-op. (NOT implemented yet — the
    hook is declared so plugins can adopt it now and we wire it into
    ``App.destroy`` later without breaking plugin authors.)

Version compatibility
---------------------

A plugin can declare the VideoKidnapper version range it supports via
``min_app_version`` / ``max_app_version``. The loader skips plugins
whose range excludes the running app version and reports the skip in
the Debug tab, rather than letting the plugin crash later on a missing
attribute.
"""


class Plugin:
    """Base class for VideoKidnapper plugins.

    Attributes that subclasses should override:

    - ``name``            — human-readable display name
    - ``version``         — plugin-specific version string
    - ``min_app_version`` — optional lower bound on VideoKidnapper
                            version (``None`` = no lower bound)
    - ``max_app_version`` — optional upper bound, exclusive
    """

    name: str = "Unnamed plugin"
    version: str = "0.0.0"
    min_app_version: "str | None" = None
    max_app_version: "str | None" = None

    # ------------------------------------------------------------------
    # Lifecycle hooks — override the ones you need.
    # ------------------------------------------------------------------
    def on_app_ready(self, app):
        """Called after the app window is fully built.

        This is the main integration point. The ``app`` argument is
        the live ``videokidnapper.App`` instance.
        """

    def on_shutdown(self, app):
        """Called when the app is about to close."""

    # ------------------------------------------------------------------
    # Convenience: lets ``str(plugin)`` produce a useful line for the
    # Debug tab / plugins list without every subclass having to define
    # ``__repr__``.
    # ------------------------------------------------------------------
    def __repr__(self):
        return f"<{type(self).__name__} name={self.name!r} version={self.version!r}>"
