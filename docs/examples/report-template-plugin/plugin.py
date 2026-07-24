"""Minimal trusted report-template plugin example."""

from src.plugins import Plugin as BasePlugin
from src.plugins import ReportRenderRequest


class MarkdownSummaryTemplate:
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
    def onload(self, context) -> None:
        template = MarkdownSummaryTemplate()
        context.register(
            "report_template",
            template.template_id,
            template,
            contract_version="1",
            priority=200,
        )
