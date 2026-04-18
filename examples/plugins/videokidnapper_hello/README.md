# videokidnapper-hello

The smallest possible VideoKidnapper plugin — adds a tab labeled **✦ Hello** that shows a welcome message.

Use this as the starting point for your own plugin.

## Install

From the VideoKidnapper repo root:

```bash
pip install -e examples/plugins/videokidnapper_hello
```

Launch VideoKidnapper. The new tab appears after the built-in tabs.

## Uninstall

```bash
pip uninstall videokidnapper-hello
```

## What it does

- Declares a `videokidnapper.plugins` entry point pointing at `HelloPlugin`.
- On app startup, `HelloPlugin.on_app_ready(app)` runs.
- Calls `app.register_tab("Hello", factory, glyph="✦")` to add the tab.

See `videokidnapper_hello/__init__.py` for the full 40-line implementation, and `../../../docs/PLUGINS.md` for the plugin API reference.
