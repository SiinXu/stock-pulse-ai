# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract tests for default-off multimodal Agent Tools."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.agent.tools.multimodal_tools import (
    PARSE_PDF_TOOL_NAME,
    READ_CHART_TOOL_NAME,
    build_multimodal_tools,
)
from src.agent.tools.registry import ToolRegistry, validate_tool_capability_contract
from src.services.chart_reading_service import ChartReadingService
from src.services.pdf_parsing_service import PdfParsingService

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "multimodal"


def test_build_multimodal_tools_default_off() -> None:
    tools = build_multimodal_tools(
        SimpleNamespace(multimodal_agent_tools_enabled=False, multimodal_file_root=None)
    )
    assert tools is None


def test_build_multimodal_tools_requires_file_root() -> None:
    tools = build_multimodal_tools(
        SimpleNamespace(multimodal_agent_tools_enabled=True, multimodal_file_root="")
    )
    assert tools is None


def test_build_multimodal_tools_registers_when_enabled(tmp_path: Path) -> None:
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes((FIXTURES / "sample_financial_report.pdf").read_bytes())
    chart_path = tmp_path / "chart.png"
    chart_path.write_bytes((FIXTURES / "sample_chart.png").read_bytes())

    mock_chart = {
        "chart_type": "line",
        "symbol_hints": ["AAPL"],
        "timeframe_hint": "1D",
        "trend": "sideways",
        "key_levels": [],
        "observations": ["flat range"],
        "confidence": "medium",
    }

    def pdf_factory() -> PdfParsingService:
        return PdfParsingService(file_root=str(tmp_path))

    def chart_factory() -> ChartReadingService:
        return ChartReadingService(
            file_root=str(tmp_path),
            vision_caller=lambda _b, _m: json.dumps(mock_chart),
        )

    tools = build_multimodal_tools(
        SimpleNamespace(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root=str(tmp_path),
        ),
        pdf_service_factory=pdf_factory,
        chart_service_factory=chart_factory,
    )
    assert tools is not None
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {PARSE_PDF_TOOL_NAME, READ_CHART_TOOL_NAME}

    registry = ToolRegistry()
    for tool in tools:
        assert validate_tool_capability_contract(tool) is None
        registry.register(tool)

    pdf_tool = next(t for t in tools if t.name == PARSE_PDF_TOOL_NAME)
    chart_tool = next(t for t in tools if t.name == READ_CHART_TOOL_NAME)

    pdf_payload = pdf_tool.handler(file_path="report.pdf")
    assert pdf_payload["schema_version"] == "pdf-parse-v1"
    assert pdf_payload["status"] in {"available", "degraded"}
    assert "600519" in pdf_payload["text"]

    chart_payload = chart_tool.handler(file_path="chart.png")
    assert chart_payload["schema_version"] == "chart-reading-v1"
    assert chart_payload["status"] == "available"
    assert chart_payload["symbol_hints"] == ["AAPL"]
