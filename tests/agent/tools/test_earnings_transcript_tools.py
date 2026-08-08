# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Tests for default-off earnings transcript Agent tool registration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.agent.tools.earnings_transcript_tools import (
    PARSE_EARNINGS_TRANSCRIPT_TOOL_NAME,
    build_earnings_transcript_tools,
)
from src.services.earnings_transcript_service import TRANSCRIPT_SCHEMA_VERSION


def test_build_transcript_tools_default_off() -> None:
    tools = build_earnings_transcript_tools(
        SimpleNamespace(multimodal_agent_tools_enabled=False, multimodal_file_root=None)
    )
    assert tools is None


def test_build_transcript_tools_requires_file_root() -> None:
    tools = build_earnings_transcript_tools(
        SimpleNamespace(multimodal_agent_tools_enabled=True, multimodal_file_root="")
    )
    assert tools is None


def test_build_transcript_tools_registers_when_enabled(tmp_path: Path) -> None:
    tools = build_earnings_transcript_tools(
        SimpleNamespace(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root=str(tmp_path),
        )
    )
    assert tools is not None
    assert len(tools) == 1
    assert tools[0].name == PARSE_EARNINGS_TRANSCRIPT_TOOL_NAME
    assert tools[0].name != "parse_financial_pdf"
    assert tools[0].name != "read_price_chart"
    assert tools[0].name != "extract_image_text"
    assert "ocr" not in tools[0].name.lower()


def test_handler_parses_inline_text(tmp_path: Path) -> None:
    tools = build_earnings_transcript_tools(
        SimpleNamespace(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root=str(tmp_path),
        )
    )
    assert tools is not None
    handler = tools[0].handler
    text = (
        "Prepared Remarks\n"
        "CEO: Revenue was $50 million. Gross margin was 40%.\n"
        "Question-and-Answer Session\n"
        "Operator: First question from Pat Kim with Lake Research.\n"
        "Q - Pat Kim, Lake Research:\n"
        "How sustainable is growth?\n"
        "A - CEO:\n"
        "We expect growth near 10% under current guidance.\n"
    )
    result = handler(text=text)
    assert result["schema_version"] == TRANSCRIPT_SCHEMA_VERSION
    assert result["status"] in {"available", "degraded"}
    assert result["metrics"]
    for metric in result["metrics"]:
        start = metric["start_char"]
        end = metric["end_char"]
        assert text[start:end] == metric["value_text"] or metric["value_text"] in text


def test_handler_requires_input(tmp_path: Path) -> None:
    tools = build_earnings_transcript_tools(
        SimpleNamespace(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root=str(tmp_path),
        )
    )
    assert tools is not None
    result = tools[0].handler()
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "missing_input"


def test_handler_parses_path(tmp_path: Path) -> None:
    sample = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "multimodal"
        / "sample_earnings_transcript.txt"
    )
    target = tmp_path / "call.txt"
    target.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    tools = build_earnings_transcript_tools(
        SimpleNamespace(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root=str(tmp_path),
        )
    )
    assert tools is not None
    result = tools[0].handler(file_path="call.txt")
    assert result["status"] in {"available", "degraded"}
    assert result["qa_items"]


def test_handler_accepts_empty_path_with_text(tmp_path: Path) -> None:
    """Optional file_path default must not fail tool-parameter pattern validation."""
    tools = build_earnings_transcript_tools(
        SimpleNamespace(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root=str(tmp_path),
        )
    )
    assert tools is not None
    # Simulate schema-level pattern check used by ToolParameter.
    pattern = None
    for param in tools[0].parameters:
        if param.name == "file_path":
            pattern = param.pattern
            break
    assert pattern is not None
    import re
    assert re.match(pattern, "") is not None
    result = tools[0].handler(file_path="", text="Revenue was $10 million.")
    assert result["status"] in {"available", "degraded"}
    assert result["metrics"]
