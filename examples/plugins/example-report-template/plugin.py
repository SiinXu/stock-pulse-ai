# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic Markdown report-template plugin for authoring and tests.

Imports only frozen author-facing names from ``src.plugins`` for the
``report_template`` extension point (ADR-007 surface freeze).
"""

from __future__ import annotations

from src.plugins import (
    Plugin as BasePlugin,
    PluginContext,
    ReportRenderRequest,
)


class MarkdownSummaryTemplate:
    """Render a complete Markdown report or decline with ``None``."""

    template_id = "example-markdown-summary"
    platforms = frozenset({"markdown"})

    def render(self, request: ReportRenderRequest) -> str | None:
        if not request.results:
            return None
        lines = [f"# Plugin report for {request.report_date}", ""]
        lines.extend(
            f"- {result.name} ({result.code}): {result.operation_advice}"
            for result in request.results
        )
        return "\n".join(lines)


class Plugin(BasePlugin):
    """Register the Markdown summary template for each enable transition."""

    def onload(self, context: PluginContext) -> None:
        template = MarkdownSummaryTemplate()
        context.register(
            "report_template",
            template.template_id,
            template,
            contract_version="1",
            priority=200,
        )

    def onunload(self) -> None:
        """Release plugin-owned resources; registration cleanup is manager-owned."""
