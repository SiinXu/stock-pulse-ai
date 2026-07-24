# Report Template Plugin Example

This directory is a minimal loadable external plugin. Copy the directory under
the parent configured by `PLUGINS_DIR`; StockPulse discovers the manifest,
loads `plugin.py:Plugin`, and registers the Markdown-only template.

The example is intentionally small and replaces the complete Markdown report
when explicitly loaded. A production renderer should preserve the report
fields and language behavior its notification consumers require. Return `None`
or an empty string to let the next plugin candidate, Jinja renderer, or
hard-coded renderer handle the request.

Use `REPORT_TEMPLATES_DIR` when only Jinja files need to change. Use a trusted
plugin only when report generation needs reviewed Python logic. External
plugins run with the same OS privileges as StockPulse and are not sandboxed.
