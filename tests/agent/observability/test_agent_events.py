# -*- coding: utf-8 -*-
"""Deterministic tests for agent observability L0 events."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.agent.observability import (
    AgentEventType,
    emit_decision,
    emit_model_end,
    emit_model_start,
    emit_phase_end,
    emit_phase_start,
    emit_tool_end,
    emit_tool_start,
    reset_span_state_for_tests,
    sanitize_agent_event_payload,
)
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)
from src.services.run_flow import build_history_run_flow_snapshot


@pytest.fixture(autouse=True)
def _reset_spans():
    reset_span_state_for_tests()
    yield
    reset_span_state_for_tests()


def test_fixture_run_emits_expected_event_sequence(monkeypatch):
    monkeypatch.setattr(
        "src.agent.observability.events.is_agent_observability_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "src.agent.observability.events.is_deep_payload_enabled",
        lambda: False,
    )
    flow_events: List[Dict[str, Any]] = []
    token = activate_run_diagnostic_context(
        trace_id="trace-fixture-1",
        task_id="task-1",
        stock_code="600519",
        event_sink=flow_events.append,
    )
    try:
        emit_phase_start("agent_loop")
        emit_model_start("demo-model", step=1)
        emit_model_end("demo-model", success=True, duration_ms=12, step=1)
        start = emit_tool_start("get_realtime_quote", step=1)
        assert start is not None
        emit_tool_end(
            "get_realtime_quote",
            success=True,
            duration_ms=5,
            step=1,
            span_id=start.span_id,
            payload={"arguments": {"stock_code": "600519"}, "api_key": "sk-secret"},
        )
        emit_decision("final_answer", status="success", step=1)
        emit_phase_end("agent_loop", status="success", duration_ms=40)

        snapshot = current_diagnostic_snapshot()
        assert snapshot is not None
        events = snapshot["agent_events"]
        types = [event["event_type"] for event in events]
        assert types == [
            AgentEventType.PHASE_START.value,
            AgentEventType.MODEL_START.value,
            AgentEventType.MODEL_END.value,
            AgentEventType.TOOL_START.value,
            AgentEventType.TOOL_END.value,
            AgentEventType.DECISION.value,
            AgentEventType.PHASE_END.value,
        ]
        assert all(event.get("trace_id") == "trace-fixture-1" for event in events)
        assert all(event.get("span_id") for event in events)
        # Lightweight mode drops deep tool bodies.
        tool_end = next(event for event in events if event["event_type"] == AgentEventType.TOOL_END.value)
        assert "payload" not in tool_end
        # Mirrored into run-flow sink.
        assert any(str(item.get("type", "")).startswith("agent_") for item in flow_events)
        replay_events = [item for item in flow_events if str(item.get("type", "")).startswith("agent_")]
        assert [item["metadata"]["sequence"] for item in replay_events] == list(range(1, 8))
        assert all(item["metadata"]["schema_version"] == 1 for item in replay_events)
        assert replay_events[-1]["metadata"]["capture"] == {
            "original_count": 7,
            "returned_count": 7,
            "dropped_count": 0,
            "truncated": False,
        }
        assert all(item["metadata"]["detail_integrity"] == "valid" for item in replay_events)
    finally:
        reset_run_diagnostic_context(token)


def test_sanitization_blocks_prompt_and_keys():
    sanitized = sanitize_agent_event_payload(
        {
            "prompt": "system secret instructions",
            "api_key": "sk-live-abcdef",
            "authorization": "Bearer token-value",
            "stock_code": "AAPL",
            "arguments": {"password": "hunter2", "query": "price"},
        },
        deep=True,
    )
    assert sanitized["prompt"] == "<redacted>"
    assert sanitized["api_key"] == "<redacted>"
    assert sanitized["authorization"] == "<redacted>"
    assert sanitized["stock_code"] == "AAPL"
    assert sanitized["arguments"]["password"] == "<redacted>"
    assert sanitized["arguments"]["query"] == "price"


def test_deep_payload_flag_controls_tool_body(monkeypatch):
    monkeypatch.setattr(
        "src.agent.observability.events.is_agent_observability_enabled",
        lambda: True,
    )
    token = activate_run_diagnostic_context(trace_id="trace-deep")
    try:
        monkeypatch.setattr(
            "src.agent.observability.events.is_deep_payload_enabled",
            lambda: True,
        )
        start = emit_tool_start(
            "search",
            payload={"arguments": {"q": "600519", "api_key": "sk-xyz"}},
        )
        emit_tool_end(
            "search",
            success=True,
            span_id=start.span_id if start else None,
            payload={"result_preview": "ok", "token": "abc"},
        )
        deep_events = current_diagnostic_snapshot()["agent_events"]
        deep_start = deep_events[0]
        assert deep_start.get("payload", {}).get("arguments", {}).get("q") == "600519"
        assert deep_start["payload"]["arguments"]["api_key"] == "<redacted>"

        # Clear and re-emit with deep off.
        reset_run_diagnostic_context(token)
        token = activate_run_diagnostic_context(trace_id="trace-lite")
        monkeypatch.setattr(
            "src.agent.observability.events.is_deep_payload_enabled",
            lambda: False,
        )
        emit_tool_start(
            "search",
            payload={"arguments": {"q": "600519", "api_key": "sk-xyz"}},
        )
        lite = current_diagnostic_snapshot()["agent_events"][0]
        assert "payload" not in lite
    finally:
        reset_run_diagnostic_context(token)


def test_history_run_flow_includes_agent_tool_sequence():
    class _Record:
        query_id = "q-1"
        code = "600519"
        name = "Kweichow Moutai"
        report_type = "detailed"
        created_at = "2026-08-06T10:00:00"
        id = 42

    context_snapshot = {
        "diagnostics": {
            "trace_id": "trace-hist",
            "task_id": "task-hist",
            "stock_code": "600519",
            "provider_runs": [],
            "llm_runs": [
                {
                    "trace_id": "trace-hist",
                    "model": "demo",
                    "call_type": "analysis",
                    "success": True,
                    "duration_ms": 10,
                    "created_at": "2026-08-06T10:00:01",
                }
            ],
            "agent_events": [
                {
                    "schema_version": 1,
                    "event_type": "agent.phase_start",
                    "trace_id": "trace-hist",
                    "span_id": "phase1",
                    "sequence": 1,
                    "timestamp": "2026-08-06T10:00:02",
                    "name": "agent_loop",
                    "status": "running",
                },
                {
                    "schema_version": 1,
                    "event_type": "agent.tool_start",
                    "trace_id": "trace-hist",
                    "span_id": "tool1",
                    "parent_span_id": "phase1",
                    "sequence": 2,
                    "timestamp": "2026-08-06T10:00:03",
                    "name": "get_realtime_quote",
                    "status": "running",
                    "step": 1,
                    "attrs": {"stock_code": "600519", "api_key": "secret"},
                },
                {
                    "schema_version": 1,
                    "event_type": "agent.tool_end",
                    "trace_id": "trace-hist",
                    "span_id": "tool1",
                    "parent_span_id": "phase1",
                    "sequence": 3,
                    "timestamp": "2026-08-06T10:00:04",
                    "name": "get_realtime_quote",
                    "status": "success",
                    "duration_ms": 8,
                    "step": 1,
                },
                {
                    "schema_version": 1,
                    "event_type": "agent.phase_end",
                    "trace_id": "trace-hist",
                    "span_id": "phase1",
                    "sequence": 4,
                    "timestamp": "2026-08-06T10:00:05",
                    "name": "agent_loop",
                    "status": "success",
                    "duration_ms": 30,
                },
            ],
            "agent_events_capture": {
                "original_count": 4,
                "returned_count": 4,
                "dropped_count": 0,
                "truncated": False,
            },
            "history_runs": [],
            "notification_runs": [],
        }
    }
    snapshot = build_history_run_flow_snapshot(
        _Record(),
        context_snapshot=context_snapshot,
        raw_result={"model_used": "demo", "success": True},
    )
    event_types = [event.type for event in snapshot.events]
    assert any(t.startswith("agent_") for t in event_types)
    tool_nodes = [node for node in snapshot.nodes if node.id.startswith("agent_tool_")]
    assert tool_nodes
    assert any(node.duration_ms == 8 for node in tool_nodes)
    phase_nodes = [node for node in snapshot.nodes if node.id.startswith("agent_phase_")]
    assert phase_nodes
    tool_sequence = (phase_nodes[0].metadata or {}).get("tool_sequence") or []
    assert tool_sequence
    assert tool_sequence[0]["label"] == "get_realtime_quote"
    replay_events = [event for event in snapshot.events if event.type.startswith("agent_")]
    assert [event.metadata["sequence"] for event in replay_events] == [1, 2, 3, 4]
    assert all(event.metadata["schema_version"] == 1 for event in replay_events)
    assert all(event.metadata["detail_integrity"] == "valid" for event in replay_events)
    assert replay_events[0].metadata["capture"] == {
        "original_count": 4,
        "returned_count": 4,
        "dropped_count": 0,
        "truncated": False,
    }
    assert replay_events[1].metadata["attrs"] == {
        "stock_code": "600519",
        "api_key": "<redacted>",
    }


def test_agent_replay_projection_rejects_non_finite_detail():
    class _Record:
        query_id = "q-non-finite"
        code = "600519"
        name = "Kweichow Moutai"
        report_type = "detailed"
        created_at = "2026-08-06T10:00:00"
        id = 43

    snapshot = build_history_run_flow_snapshot(
        _Record(),
        context_snapshot={
            "diagnostics": {
                "trace_id": "trace-non-finite",
                "agent_events": [{
                    "schema_version": 1,
                    "event_type": "agent.decision",
                    "trace_id": "trace-non-finite",
                    "span_id": "decision-1",
                    "sequence": 1,
                    "timestamp": "2026-08-06T10:00:01",
                    "name": "final_answer",
                    "status": "success",
                    "attrs": {"confidence": float("inf"), "signal": "hold"},
                }],
                "agent_events_capture": {
                    "original_count": 1,
                    "returned_count": 1,
                    "dropped_count": 0,
                    "truncated": False,
                },
            }
        },
        raw_result={"success": True},
    )

    replay_event = next(event for event in snapshot.events if event.type.startswith("agent_"))
    assert replay_event.metadata["attrs"] == {"signal": "hold"}
    assert replay_event.metadata["detail_integrity"] == "invalid_non_finite"
