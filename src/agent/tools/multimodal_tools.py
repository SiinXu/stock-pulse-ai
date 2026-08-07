# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Default-off Agent tools for PDF parsing and chart reading (issue #253 phase 1)."""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence

from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy
from src.services.chart_reading_service import (
    CHART_DISCLAIMER,
    CHART_SCHEMA_VERSION,
    ChartReadingService,
)
from src.services.pdf_parsing_service import (
    MAX_PDF_PAGES,
    PDF_DISCLAIMER,
    PDF_SCHEMA_VERSION,
    PdfParsingService,
)

logger = logging.getLogger(__name__)

PARSE_PDF_TOOL_NAME = "parse_financial_pdf"
READ_CHART_TOOL_NAME = "read_price_chart"

# Relative path under MULTIMODAL_FILE_ROOT (or absolute path contained in root).
_RELATIVE_PATH_PATTERN = r"^(?!.*\.\.)(?!.*://)[A-Za-z0-9_./\- ()\[\]]{1,512}$"

_PDF_TOOL_POLICY = ToolPolicy.declared(
    read_only=True,
    side_effects=["fs_read"],
    permissions=["multimodal:read"],
    scope_dimensions=[],
)

_CHART_TOOL_POLICY = ToolPolicy.declared(
    read_only=True,
    side_effects=["fs_read", "network_read"],
    permissions=["multimodal:read"],
    scope_dimensions=[],
)


class _ParsePdfHandler:
    def __init__(self, service: PdfParsingService) -> None:
        self._service = service

    def __call__(self, file_path: str, max_pages: int = MAX_PDF_PAGES) -> dict[str, Any]:
        try:
            pages = int(max_pages)
        except (TypeError, ValueError):
            pages = MAX_PDF_PAGES
        pages = max(1, min(pages, MAX_PDF_PAGES))
        result = self._service.parse_path(file_path, max_pages=pages)
        # Ensure schema markers always present for the tool surface.
        result.setdefault("schema_version", PDF_SCHEMA_VERSION)
        result.setdefault("disclaimer", PDF_DISCLAIMER)
        return result


class _ReadChartHandler:
    def __init__(self, service: ChartReadingService) -> None:
        self._service = service

    def __call__(self, file_path: str) -> dict[str, Any]:
        result = self._service.read_path(file_path)
        result.setdefault("schema_version", CHART_SCHEMA_VERSION)
        result.setdefault("disclaimer", CHART_DISCLAIMER)
        return result


def _file_root_from_config(config: Any) -> Optional[str]:
    root = getattr(config, "multimodal_file_root", None)
    if root is None:
        return None
    text = str(root).strip()
    return text or None


def build_multimodal_tools(
    config: Any,
    *,
    pdf_service_factory: Optional[Callable[[], PdfParsingService]] = None,
    chart_service_factory: Optional[Callable[[], ChartReadingService]] = None,
) -> Optional[List[ToolDefinition]]:
    """Return PDF + chart tools only when the default-off flag is enabled.

    When ``multimodal_agent_tools_enabled`` is false (the default), returns
    ``None`` so nothing is registered in the process catalog.
    """
    enabled = getattr(config, "multimodal_agent_tools_enabled", False) is True
    if not enabled:
        logger.debug(
            "Multimodal Agent Tools were not registered reason=disabled "
            "guidance=Set MULTIMODAL_AGENT_TOOLS_ENABLED=true, configure "
            "MULTIMODAL_FILE_ROOT, and restart to opt in"
        )
        return None

    file_root = _file_root_from_config(config)
    if not file_root:
        logger.warning(
            "Multimodal Agent Tools were not registered reason=file_root_missing "
            "guidance=Set MULTIMODAL_FILE_ROOT to a local directory that will hold "
            "user-provided PDF/chart files, then restart"
        )
        return None

    try:
        pdf_service = (
            pdf_service_factory()
            if pdf_service_factory is not None
            else PdfParsingService(file_root=file_root)
        )
        chart_service = (
            chart_service_factory()
            if chart_service_factory is not None
            else ChartReadingService(file_root=file_root)
        )
    except Exception:  # broad-exception: fallback_recorded - optional tools stay absent.
        logger.warning(
            "Multimodal Agent Tools were not registered reason=service_init_failed "
            "guidance=Check MULTIMODAL_FILE_ROOT and vision configuration, then restart"
        )
        return None

    pdf_tool = ToolDefinition(
        name=PARSE_PDF_TOOL_NAME,
        description=(
            "Parse a local financial PDF under MULTIMODAL_FILE_ROOT into "
            "structured text and best-effort table rows for analysis context. "
            "Local text extraction only in phase 1; never executes PDF content."
        ),
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description=(
                    "Relative path under MULTIMODAL_FILE_ROOT, or an absolute path "
                    "contained in that root. Paths with '..', URLs, or home "
                    "expansion are rejected."
                ),
                pattern=_RELATIVE_PATH_PATTERN,
            ),
            ToolParameter(
                name="max_pages",
                type="integer",
                description=f"Maximum pages to parse (1-{MAX_PDF_PAGES}).",
                required=False,
                default=MAX_PDF_PAGES,
                minimum=1,
                maximum=MAX_PDF_PAGES,
            ),
        ],
        handler=_ParsePdfHandler(pdf_service),
        category="analysis",
        policy=_PDF_TOOL_POLICY,
        enforce_contract=True,
    )

    chart_tool = ToolDefinition(
        name=READ_CHART_TOOL_NAME,
        description=(
            "Read a local market chart image (PNG/JPEG/WebP/GIF) under "
            "MULTIMODAL_FILE_ROOT into a structured visual observation via the "
            "configured vision model. Degrades honestly when vision is unavailable."
        ),
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description=(
                    "Relative path under MULTIMODAL_FILE_ROOT, or an absolute path "
                    "contained in that root. Paths with '..', URLs, or home "
                    "expansion are rejected."
                ),
                pattern=_RELATIVE_PATH_PATTERN,
            ),
        ],
        handler=_ReadChartHandler(chart_service),
        category="analysis",
        policy=_CHART_TOOL_POLICY,
        enforce_contract=True,
    )
    return [pdf_tool, chart_tool]


def register_multimodal_tools(
    registry: Any,
    config: Any,
    **kwargs: Any,
) -> Sequence[str]:
    """Register multimodal tools on a ToolRegistry when enabled. Returns names."""
    tools = build_multimodal_tools(config, **kwargs)
    if not tools:
        return []
    names: list[str] = []
    for tool in tools:
        registry.register(tool)
        names.append(tool.name)
    return names
