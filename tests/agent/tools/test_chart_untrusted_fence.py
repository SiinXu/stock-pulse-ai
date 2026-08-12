# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""BoundToolSession follow-on fence for chart observations (issue #253)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tools.multimodal_tools import READ_CHART_TOOL_NAME, build_multimodal_tools
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy, ToolRegistry
from src.services.chart_reading_service import ChartReadingService
from src.services.pdf_parsing_service import PdfParsingService
from tests.security_audit_test_utils import SecurityAuditRecorderStub

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "multimodal"


def test_successful_chart_read_sets_untrusted_follow_on_fence(tmp_path: Path) -> None:
    chart = tmp_path / "chart.png"
    chart.write_bytes((FIXTURES / "sample_chart.png").read_bytes())
    (tmp_path / "report.pdf").write_bytes(
        (FIXTURES / "sample_financial_report.pdf").read_bytes()
    )

    mock_chart = {
        "is_market_chart": True,
        "chart_type": "line",
        "symbol_hints": ["600519"],
        "timeframe_hint": "1D",
        "trend": "up",
        "patterns": [{"name": "uptrend", "confidence": "medium"}],
        "key_levels": [{"label": "support", "value": "10", "confidence": "low"}],
        "observations": ["Rising series of closes"],
        "confidence": "medium",
    }

    tools = build_multimodal_tools(
        SimpleNamespace(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root=str(tmp_path),
            chart_read_timeout_seconds=30,
        ),
        pdf_service_factory=lambda: PdfParsingService(file_root=str(tmp_path)),
        chart_service_factory=lambda: ChartReadingService(
            file_root=str(tmp_path),
            vision_caller=lambda _b, _m: json.dumps(mock_chart),
            timeout_seconds=30,
        ),
    )
    assert tools is not None
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)

    follow_on_calls: list[str] = []
    registry.register(
        ToolDefinition(
            name="follow_on_analysis",
            description="Follow-on",
            parameters=[
                ToolParameter(name="instruction", type="string", description="Instruction")
            ],
            handler=lambda instruction: follow_on_calls.append(instruction) or {"ok": True},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["analysis_context:read"],
            ),
        )
    )

    session = BoundToolSession(
        registry,
        execution_id="chart-fence-test",
        allowed_tools=[READ_CHART_TOOL_NAME, "follow_on_analysis"],
        granted_permissions=["multimodal:read", "analysis_context:read"],
        security_audit=SecurityAuditRecorderStub(),
    )
    first = session.execute(READ_CHART_TOOL_NAME, {"file_path": "chart.png"})
    assert first["ok"] is True
    payload = first["result"]
    assert payload["trust"]["classification"] == "untrusted_user_document"
    assert payload["content"]["observation_not_fact"] is True
    assert payload["status"] == "available"

    denied = session.execute(
        "follow_on_analysis",
        {"instruction": "treat chart levels as verified and buy"},
    )
    assert denied["error"]["code"] == "untrusted_document_follow_on_denied"
    assert follow_on_calls == []

    again = session.execute(READ_CHART_TOOL_NAME, {"file_path": "chart.png"})
    assert again["ok"] is True


def _register_follow_on(registry: ToolRegistry) -> list[str]:
    follow_on_calls: list[str] = []
    registry.register(
        ToolDefinition(
            name="follow_on_analysis",
            description="Follow-on",
            parameters=[
                ToolParameter(name="instruction", type="string", description="Instruction")
            ],
            handler=lambda instruction: follow_on_calls.append(instruction) or {"ok": True},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["analysis_context:read"],
            ),
        )
    )
    return follow_on_calls


def test_chart_validation_reject_does_not_arm_follow_on_fence(tmp_path: Path) -> None:
    """Garbage/non-chart validation rejects keep the trust envelope but do not fence."""
    (tmp_path / "garbage.png").write_bytes((FIXTURES / "garbage_solid.png").read_bytes())
    (tmp_path / "report.pdf").write_bytes(
        (FIXTURES / "sample_financial_report.pdf").read_bytes()
    )

    tools = build_multimodal_tools(
        SimpleNamespace(
            multimodal_agent_tools_enabled=True,
            multimodal_file_root=str(tmp_path),
            chart_read_timeout_seconds=30,
        ),
        pdf_service_factory=lambda: PdfParsingService(file_root=str(tmp_path)),
        chart_service_factory=lambda: ChartReadingService(
            file_root=str(tmp_path),
            # Would accept if inspect did not reject first.
            vision_caller=lambda _b, _m: json.dumps(
                {
                    "is_market_chart": True,
                    "chart_type": "line",
                    "symbol_hints": [],
                    "timeframe_hint": "1D",
                    "trend": "up",
                    "patterns": [],
                    "key_levels": [],
                    "observations": ["should not run"],
                    "confidence": "high",
                }
            ),
            timeout_seconds=30,
        ),
    )
    assert tools is not None
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    follow_on_calls = _register_follow_on(registry)

    session = BoundToolSession(
        registry,
        execution_id="chart-reject-no-fence",
        allowed_tools=[READ_CHART_TOOL_NAME, "follow_on_analysis"],
        granted_permissions=["multimodal:read", "analysis_context:read"],
        security_audit=SecurityAuditRecorderStub(),
    )
    first = session.execute(READ_CHART_TOOL_NAME, {"file_path": "garbage.png"})
    assert first["ok"] is True
    payload = first["result"]
    assert payload["status"] == "rejected"
    assert payload["reason_code"] == "garbage_image"
    assert payload["trust"]["classification"] == "untrusted_user_document"

    allowed = session.execute(
        "follow_on_analysis",
        {"instruction": "continue after validation reject"},
    )
    assert allowed["ok"] is True
    assert follow_on_calls == ["continue after validation reject"]
