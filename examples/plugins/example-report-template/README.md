# Example Report Template

Trusted in-process plugin that registers the deterministic Markdown template
`example-markdown-summary`. It replaces the full Markdown body only when this
plugin is loaded and the renderer selects a matching platform candidate.
Return `None` from `render` to decline and let Jinja or hard-coded fallbacks
continue.

Point `PLUGINS_DIR` at this directory's parent (`examples/plugins`):

```bash
export PLUGINS_DIR="$PWD/examples/plugins"
```

Prefer `REPORT_TEMPLATES_DIR` when only Jinja files need to change. Use a
trusted plugin only when report generation needs reviewed Python logic.

External plugins execute with the same OS privileges as StockPulse and are not
sandboxed. See the
[Plugin Development Guide](../../../docs/plugin-development-guide.md).

A smaller documentation-only copy also lives under
`docs/examples/report-template-plugin/`; this package is the runnable reference
under `examples/plugins/`.
