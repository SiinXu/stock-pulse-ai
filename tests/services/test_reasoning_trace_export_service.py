# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for reasoning-trace export (Issue #135 / T03)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from src.services.reasoning_trace_export_service import (
    SCHEMA_VERSION,
    ReasoningTraceExportDisabled,
    ReasoningTraceExportService,
    ReasoningTraceNotFound,
    build_reasoning_trace_package,
    is_reasoning_trace_export_enabled,
)


FAKE_API_KEY = "sk-test-secret-key-DO-NOT-LEAK-1234567890"
FAKE_TOKEN = "Bearer ghp_exampleTokenValueABCDEF1234567890"
FAKE_PATH = "/Users/alice/.config/stock-pulse/secrets.env"
FAKE_URL = "https://user:p4ssw0rd@api.example.com/v1/chat"


def _source_payload() -> Dict[str, Any]:
    return {
        "diagnostics": {
            "trace_id": "trace-abc",
            "query_id": "q-1",
            "stock_code": "600519",
            "agent_events": [
                {
                    "event_type": "agent.tool_start",
                    "name": "get_quote",
                    "status": "ok",
                    "sequence": 1,
                    "timestamp": "2026-08-09T00:00:00Z",
                    "attrs": {
                        "agent": "research",
                        "tool": "get_quote",
                        "api_key": FAKE_API_KEY,
                        "authorization": FAKE_TOKEN,
                    },
                },
                {
                    "event_type": "agent.decision",
                    "name": "research",
                    "sequence": 2,
                    "attrs": {
                        "agent": "research",
                        "signal": "buy",
                        "summary": f"used key {FAKE_API_KEY} from {FAKE_PATH}",
                    },
                },
                {
                    "event_type": "agent.decision",
                    "name": "risk",
                    "sequence": 3,
                    "attrs": {"agent": "risk", "signal": "hold"},
                },
            ],
            "provider_runs": [
                {
                    "provider": "yfinance",
                    "data_type": "daily",
                    "operation": "fetch",
                    "status": "success",
                    "base_url": FAKE_URL,
                }
            ],
            "llm_runs": [
                {
                    "provider": "openai",
                    "model": "gpt-test",
                    "call_type": "analysis",
                    "status": "success",
                    "api_key": FAKE_API_KEY,
                }
            ],
            "pipeline_stage_runs": [
                {"stage": "fetch", "status": "success", "duration_ms": 12}
            ],
        },
        "raw_result": {
            "code": "600519",
            "name": "Kweichow Moutai",
            "model_used": "gpt-test",
            "decision_type": "buy",
            "operation_advice": "accumulate on dips",
            "analysis_summary": "bullish with risk check",
            "sentiment_score": 72,
            "dashboard": {
                "core_conclusion": {
                    "decision_type": "buy",
                    "operation_advice": "accumulate on dips",
                    "confidence_level": "中",
                    "analysis_summary": "bullish with risk check",
                },
                "strategy_synthesis": {
                    "final_signal": "buy",
                    "consensus_level": "partial",
                    "conflict_severity": "low",
                    "conflict_count": 1,
                    "supporting_skills": ["momentum"],
                    "opposing_skills": ["mean_reversion"],
                },
                "committee_deliberation": {
                    "status": "completed",
                    "personas": [{"persona_id": "value", "signal": "buy"}],
                },
            },
        },
        "context_snapshot": {
            "analysis_context_pack_overview": {
                "data_quality": {"status": "ok", "warnings": []},
            }
        },
    }


def test_export_schema_contract() -> None:
    src = _source_payload()
    result = build_reasoning_trace_package(
        run_id="q-1",
        stock_code="600519",
        market="CN",
        diagnostics=src["diagnostics"],
        raw_result=src["raw_result"],
        context_snapshot=src["context_snapshot"],
        config=SimpleNamespace(
            agent_observability_enabled=True,
            agent_observability_deep_payload=False,
            agent_multi_strategy_deliberation=False,
            agent_risk_override=True,
            generation_backend="litellm",
            report_type="simple",
            report_language="zh",
        ),
    )
    package = result.package
    assert package["schema_version"] == SCHEMA_VERSION
    assert package["run"]["run_id"] == "q-1"
    assert package["run"]["stock_code"] == "600519"
    assert package["run"]["config_fingerprint"]
    assert isinstance(package["agents"], list)
    assert len(package["agents"]) >= 1
    assert "synthesis" in package
    assert package["synthesis"]["final_conclusion"]["final_signal"] == "buy"
    assert package["data_sources"]["data_quality_status"]["status"] == "ok"
    assert "recorded" in package["coverage"]
    assert "not_recorded" in package["coverage"]
    assert result.markdown.startswith("# Reasoning Trace")


def test_redaction_strips_secrets_from_export() -> None:
    """Mandatory acceptance: injected secrets must never appear in the export."""
    src = _source_payload()
    result = build_reasoning_trace_package(
        run_id="q-secret",
        diagnostics=src["diagnostics"],
        raw_result=src["raw_result"],
        context_snapshot=src["context_snapshot"],
    )
    blob = json.dumps(result.package, ensure_ascii=False) + "\n" + result.markdown
    assert FAKE_API_KEY not in blob
    assert FAKE_TOKEN not in blob
    assert "p4ssw0rd" not in blob
    # Local home path segments should be redacted by shared sanitizer.
    assert FAKE_PATH not in blob
    assert "sk-test-secret-key" not in blob


def test_export_disabled_by_default() -> None:
    assert is_reasoning_trace_export_enabled(SimpleNamespace()) is False
    assert (
        is_reasoning_trace_export_enabled(
            SimpleNamespace(reasoning_trace_export_enabled=False)
        )
        is False
    )
    service = ReasoningTraceExportService(
        history_service=SimpleNamespace(),
        config=SimpleNamespace(reasoning_trace_export_enabled=False),
    )
    with pytest.raises(ReasoningTraceExportDisabled):
        service.ensure_enabled()


def test_export_enabled_flag() -> None:
    assert (
        is_reasoning_trace_export_enabled(
            SimpleNamespace(reasoning_trace_export_enabled=True)
        )
        is True
    )


def test_size_budget_sets_explicit_truncation_marker() -> None:
    events = []
    for i in range(80):
        events.append(
            {
                "event_type": "agent.phase_end",
                "name": f"phase-{i}",
                "sequence": i,
                "attrs": {
                    "agent": f"agent-{i % 5}",
                    "summary": ("x" * 2000),
                },
            }
        )
    result = build_reasoning_trace_package(
        run_id="q-big",
        diagnostics={"agent_events": events, "provider_runs": [], "llm_runs": []},
        raw_result={
            "code": "AAPL",
            "decision_type": "hold",
            "dashboard": {
                "committee_deliberation": {
                    "notes": ["y" * 3000 for _ in range(20)],
                    "personas": [{"persona_id": f"p{i}", "text": "z" * 2000} for i in range(30)],
                },
                "strategy_synthesis": {
                    "final_signal": "hold",
                    "detail": "w" * 8000,
                },
            },
        },
        max_chars=8_000,
    )
    assert result.package.get("truncated") is True
    assert result.package.get("truncation", {}).get("marker") == "truncated"
    assert result.package["truncation"]["reason"] == "export_size_budget_exceeded"


def test_service_export_for_record_uses_history() -> None:
    src = _source_payload()
    record = SimpleNamespace(
        query_id="q-1",
        code="600519",
        name="Kweichow Moutai",
        model_used="gpt-test",
        created_at=None,
        context_snapshot=json.dumps(
            {
                "diagnostics": src["diagnostics"],
                "analysis_context_pack_overview": src["context_snapshot"][
                    "analysis_context_pack_overview"
                ],
            }
        ),
        raw_result=json.dumps(src["raw_result"]),
    )
    history = SimpleNamespace(
        _resolve_record=lambda record_id: record,
        _parse_diagnostic_json_field=lambda value, field: (
            json.loads(value) if isinstance(value, str) and value.strip() else value
        ),
    )
    service = ReasoningTraceExportService(
        history_service=history,
        config=SimpleNamespace(
            reasoning_trace_export_enabled=True,
            reasoning_trace_export_max_chars=500_000,
        ),
    )
    result = service.export_for_record("1")
    assert result.package["schema_version"] == SCHEMA_VERSION
    assert result.package["run"]["stock_code"] == "600519"
    blob = json.dumps(result.package, ensure_ascii=False)
    assert FAKE_API_KEY not in blob


def test_service_not_found() -> None:
    history = SimpleNamespace(
        _resolve_record=lambda record_id: None,
        _parse_diagnostic_json_field=lambda value, field: value,
    )
    service = ReasoningTraceExportService(
        history_service=history,
        config=SimpleNamespace(reasoning_trace_export_enabled=True),
    )
    with pytest.raises(ReasoningTraceNotFound):
        service.export_for_record("missing")
