# Writing VideoKidnapper plugins

VideoKidnapper supports third-party plugins via the standard Python `entry_points` mechanism. A plugin is a regular pip-installable package; users install it with `pip install your-plugin` and it appears in VideoKidnapper the next time they launch the app.

This document covers the plugin API, packaging, and the constraints / conventions plugin authors should follow.

See also `examples/plugins/videokidnapper_hello/` — a complete, working, ~40-line plugin you can copy as a starting point.

---

## TL;DR

1. Create a Python package with its own `pyproject.toml`.
2. Declare an entry point under `[project.entry-points."videokidnapper.plugins"]` pointing at a class that subclasses `videokidnapper.plugins.Plugin`.
3. Override `on_app_ready(self, app)` and use the host `App` to wire your UI in.
4. `pip install` your plugin. Launch VideoKidnapper.

---

## The `Plugin` base class

```python
from videokidnapper.plugins import Plugin

class MyPlugin(Plugin):
    name = "My Plugin"         # display name (shown in Debug tab, plugins list)
    version = "1.0.0"          # your plugin's version (not VideoKidnapper's)

    # Optional version bounds — plugins outside the range are skipped,
    # not loaded and allowed to crash later.
    min_app_version = "1.1.0"  # oldest supported VideoKidnapper
    max_app_version = None     # None = no upper bound

    def on_app_ready(self, app):
        """Wire your plugin into the app. See hooks below."""

    def on_shutdown(self, app):
        """Called when the app is closing (hook declared; not yet fired)."""
```

Every method is optional. An info-only plugin is valid — it just shows up in the plugins list without adding any UI.

---

## What you can do from `on_app_ready`

### Add a tab

```python
def on_app_ready(self, app):
    app.register_tab("My Tab", self._build, glyph="✦")

def _build(self, parent):
    import customtkinter as ctk
    frame = ctk.CTkFrame(parent)
    ctk.CTkLabel(frame, text="Hello").pack()
    return frame
```

- `register_tab(display_name, factory, glyph="◆")` returns the widget your `factory` produced, or `None` if the factory raised (the error is logged to the Debug tab).
- Keep `display_name` short — the segmented tab button centers the label.
- `glyph` defaults to a diamond so plugin tabs are visually distinct from built-in tabs (✂ / ↓ / ⌛ / ⚙).

### Read host state / hook into existing UI

`app` is the live `videokidnapper.App` instance. Useful attributes:

| Attribute | Type | Purpose |
|---|---|---|
| `app.trim_tab` | `TrimTab` | The main editing tab |
| `app.url_tab` | `UrlTab` | URL downloader |
| `app.history_tab` | `HistoryTab` | Recent exports list |
| `app.debug_tab` | `DebugTab` | Log sink; `app.debug_tab.add_log(msg, level)` |
| `app.status_bar` | `Toast` | Bottom status strip; `app.status_bar.show(msg, level)` |
| `app.tabview` | `CTkTabview` | Raw tabview (for advanced integrations) |
| `app.ffmpeg_path` / `app.ffprobe_path` | `str` | Verified paths on disk |

Treat everything not in this table as internal — names and shapes can change. Stick to `register_tab` + the documented attributes above and your plugin survives refactors.

### Log to the Debug tab

```python
def on_app_ready(self, app):
    app.debug_tab.add_log("Hello from my plugin", "INFO")  # INFO / WARN / ERROR
```

---

## Packaging

A complete `pyproject.toml` for a plugin:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "videokidnapper-myplugin"
version = "1.0.0"
description = "…"
requires-python = ">=3.9"
dependencies = ["videokidnapper>=1.1.0"]

[project.entry-points."videokidnapper.plugins"]
myplugin = "videokidnapper_myplugin:MyPlugin"

[tool.setuptools]
packages = ["videokidnapper_myplugin"]
```

Naming conventions:

- **Distribution name:** prefix with `videokidnapper-` (e.g. `videokidnapper-whisper`, `videokidnapper-transitions`). Makes plugins findable on PyPI.
- **Import name:** use `videokidnapper_<slug>` so the module path is unambiguous.
- **Entry-point name:** short identifier (shown in the Debug tab on load).

---

## Failure behavior

The loader is defensive so one bad plugin doesn't kill the app:

| Failure | Behavior |
|---|---|
| Entry point fails to import | Logged to Debug; other plugins continue loading |
| Plugin class's `__init__` raises | Logged; plugin skipped |
| `app_version` outside `min_app_version` / `max_app_version` | Plugin skipped; reason logged |
| `on_app_ready` raises | Error goes to Debug tab; other plugins still run |
| Tab factory raises in `register_tab` | Tab is rolled back; error logged |

A plugin that survives all of these shows up in `app.plugins` (a list of `DiscoveredPlugin` namedtuples) and in the Debug tab's startup log.

---

## Licensing

VideoKidnapper itself is Apache-2.0, but **plugins are free to pick any license** — Apache-2.0, MIT, GPL, or fully proprietary / closed-source. The plugin mechanism relies on Python's packaging system, not source-level linking, so there's no copyleft inheritance. This is intentional: it enables a future paid / premium plugin tier without changing the core project's license.

If you publish a plugin under a different license, just include a `LICENSE` file in your plugin's source distribution.

---

## Version compatibility

Declare the VideoKidnapper versions your plugin supports:

```python
class MyPlugin(Plugin):
    min_app_version = "1.1.0"   # first version with register_tab
    max_app_version = "2.0.0"   # exclusive — drop when 2.0 support lands
```

`None` on either bound means "no limit". Skipped plugins appear in `app.plugins` with an `error` string explaining the range mismatch, so users can see why nothing loaded.

---

## Testing your plugin

VideoKidnapper's plugin loader accepts an `entry_points=` argument so you can exercise discovery without installing anything:

```python
from types import SimpleNamespace
from videokidnapper.plugins import discover_plugins
from my_plugin import MyPlugin

def _fake_ep(name, target):
    return SimpleNamespace(name=name, load=lambda: target, dist=None)

def test_plugin_loads():
    results = discover_plugins(entry_points=[_fake_ep("my", MyPlugin)])
    assert results[0].error is None
    assert isinstance(results[0].plugin, MyPlugin)
```

For on_app_ready integration tests, mock the `App` — you rarely need a real Tk root.
