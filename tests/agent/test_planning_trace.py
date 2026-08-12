# -*- coding: utf-8 -*-
"""Structured planning-loop trace events (#1078 / #1125 taxonomy alignment)."""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.agent.observability import AgentEventType
from src.agent.planning import (
    PlanExecutionSettings,
    execute_plan_loop,
    reconstruct_planning_run,
    validate_plan_payload,
    validate_planning_trace_event,
)
from src.agent.planning.trace import (
    PLANNING_TRACE_KINDS,
    PlanningTraceRecorder,
)
from src.agent.planning.types import PLAN_SCHEMA_VERSION
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)


def _plan(tools_per_step: List[List[str]]):
    steps = []
    for index, tools in enumerate(tools_per_step, start=1):
        steps.append(
            {
                "id": index,
                "goal": f"Step {index}",
                "expected_tools": list(tools),
                "success_criteria": f"Step {index} done",
            }
        )
    all_tools = sorted({name for group in tools_per_step for name in group})
    payload = {
        "version": PLAN_SCHEMA_VERSION,
        "goal": "Trace reconstruction fixture",
        "max_steps": max(1, len(steps)),
        "steps": steps,
    }
    return validate_plan_payload(
        payload, available_tools=all_tools, max_steps=max(1, len(steps))
    ), all_tools


def test_planning_trace_event_schema_shape() -> None:
    recorder = PlanningTraceRecorder(run_id="run-fixture", enabled=True)
    recorder.emit_plan(plan_id="p1", step_count=2, role="initial")
    recorder.emit_action(
        tool_name="get_realtime_quote",
        step=1,
        argument_keys=["stock_code", "api_key"],
        plan_id="p1",
        budget=recorder.budget_attrs(tool_call_count=1, max_total_tool_calls=8),
    )
    recorder.emit_observation(
        step=1,
        status="failed",
        error_type="tool_failed",
        plan_id="p1",
    )
    recorder.emit_replan(
        reason="tool_failed",
        previous_plan_id="p1",
        new_plan_id="p2",
        failed_step=1,
        observation_replans=1,
    )
    recorder.emit_terminate(
        reason="completed",
        status="succeeded",
        success=True,
        plan_id="p2",
    )

    assert len(recorder.events) == 5
    kinds = {event["kind"] for event in recorder.events}
    assert kinds == PLANNING_TRACE_KINDS

    for event in recorder.events:
        errors = validate_planning_trace_event(event)
        assert errors == [], errors
        assert event["run_id"] == "run-fixture"
        assert event["event_type"].startswith("agent.")
        assert event["attrs"]["run_id"] == "run-fixture"
        if event["kind"] == "action":
            assert event["attrs"]["arg_names"] == ["stock_code"]
            assert "api_key" not in event["attrs"]["arg_names"]

    terminate = recorder.events[-1]
    assert terminate["kind"] == "terminate"
    assert terminate["reason"] == "completed"
    assert terminate["event_type"] == AgentEventType.TERMINATE.value


def test_failed_run_reconstructable_from_trace_events() -> None:
    plan, tools = _plan([["get_realtime_quote"], ["analyze_trend"]])

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name == "get_realtime_quote":
            return {"ok": True, "summary": "quote-ok"}
        return {
            "ok": False,
            "error_code": "provider_error",
            "summary": "provider down",
            "api_key": "sk-should-not-appear",
        }

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        context={"stock_code": "600519"},
        settings=PlanExecutionSettings(
            max_observation_replans=0,
            on_step_failure="terminate",
        ),
        task="Analyze 600519",
    )

    assert result.success is False
    assert result.reason == "step_failed"
    assert result.trace_events, "trace events required for reconstruction"
    assert result.planning_run_id

    for event in result.trace_events:
        assert validate_planning_trace_event(event) == []
        dumped = str(event)
        assert "sk-should-not-appear" not in dumped

    story = reconstruct_planning_run(result.trace_events)
    assert story["run_id"] == result.planning_run_id
    assert story["plans"], "at least the initial plan event"
    assert story["actions"], "tool actions should be present"
    assert story["observations"], "step observations should be present"
    assert story["terminate"] is not None
    assert story["terminate"]["reason"]
    assert story["terminate"]["success"] is False
    assert story["budget"].get("tool_call_count", 0) >= 1

    kinds = [event["kind"] for event in result.trace_events]
    assert kinds[0] == "plan"
    assert kinds[-1] == "terminate"
    assert "action" in kinds
    assert "observation" in kinds


def test_terminate_reason_always_present_on_success_and_failure() -> None:
    plan_ok, tools_ok = _plan([["get_realtime_quote"], []])

    def ok_invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "summary": "ok"}

    success = execute_plan_loop(
        plan=plan_ok,
        tool_invoker=ok_invoker,
        available_tools=tools_ok,
        context={"stock_code": "AAPL"},
        settings=PlanExecutionSettings(max_observation_replans=0, on_step_failure="terminate"),
    )
    assert success.success is True
    term = next(e for e in success.trace_events if e["kind"] == "terminate")
    assert term["reason"]
    assert success.reason == "completed"

    plan_bad, tools_bad = _plan([["get_realtime_quote"]])

    def bad_invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": False, "error_code": "tool_failed", "summary": "nope"}

    failure = execute_plan_loop(
        plan=plan_bad,
        tool_invoker=bad_invoker,
        available_tools=tools_bad,
        settings=PlanExecutionSettings(max_observation_replans=0, on_step_failure="terminate"),
    )
    assert failure.success is False
    term_f = next(e for e in failure.trace_events if e["kind"] == "terminate")
    assert term_f["reason"] == "step_failed"


def test_replan_emits_replan_reason_and_budget() -> None:
    plan, tools = _plan([["get_realtime_quote"], ["analyze_trend"]])
    calls: List[str] = []

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        calls.append(name)
        if name == "analyze_trend" and calls.count("analyze_trend") == 1:
            return {"ok": False, "error_code": "tool_failed", "summary": "fail-once"}
        return {"ok": True, "summary": f"{name}-ok"}

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools + ["get_daily_history", "search_stock_news"],
        context={"stock_code": "600519"},
        task="Analyze 600519",
        settings=PlanExecutionSettings(
            max_observation_replans=1,
            on_step_failure="replan",
            max_total_tool_calls=16,
        ),
    )
    replan_events = [e for e in result.trace_events if e["kind"] == "replan"]
    assert replan_events, "expected observation-driven replan event"
    assert replan_events[0]["reason"]
    assert "budget" in replan_events[0]["attrs"]
    assert replan_events[0]["attrs"]["budget"]["observation_replans"] >= 1

    story = reconstruct_planning_run(result.trace_events)
    assert story["replans"]
    assert story["replans"][0]["reason"]


def test_trace_disabled_produces_no_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.agent.planning.trace.is_planning_trace_enabled",
        lambda: False,
    )
    plan, tools = _plan([["get_realtime_quote"]])

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "summary": "ok"}

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        settings=PlanExecutionSettings(max_observation_replans=0, on_step_failure="terminate"),
    )
    assert result.success is True
    assert result.trace_events == []


def test_trace_events_dual_write_to_diagnostic_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.agent.observability.events.is_agent_observability_enabled",
        lambda: True,
    )
    token = activate_run_diagnostic_context(trace_id="trace-plan-1078")
    try:
        plan, tools = _plan([["get_realtime_quote"]])

        def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            return {"ok": True, "summary": "ok"}

        result = execute_plan_loop(
            plan=plan,
            tool_invoker=invoker,
            available_tools=tools,
            context={"stock_code": "600519"},
            settings=PlanExecutionSettings(
                max_observation_replans=0, on_step_failure="terminate"
            ),
        )
        assert result.trace_events
        snapshot = current_diagnostic_snapshot()
        assert snapshot is not None
        agent_events = snapshot["agent_events"]
        planning_types = {
            AgentEventType.PLAN.value,
            AgentEventType.ACTION.value,
            AgentEventType.OBSERVATION.value,
            AgentEventType.TERMINATE.value,
        }
        seen = {event["event_type"] for event in agent_events}
        assert planning_types.issubset(seen)
        for event in agent_events:
            if event["event_type"] in planning_types:
                assert event.get("attrs", {}).get("run_id") == result.planning_run_id
    finally:
        reset_run_diagnostic_context(token)


def test_metadata_includes_trace_events() -> None:
    plan, tools = _plan([[]])
    result = execute_plan_loop(
        plan=plan,
        tool_invoker=lambda n, a: {"ok": True},
        available_tools=tools,
        settings=PlanExecutionSettings(max_observation_replans=0),
    )
    meta = result.to_metadata()
    assert meta.get("planning_run_id") == result.planning_run_id
    assert meta.get("trace_events")
    assert meta["trace_events"][-1]["kind"] == "terminate"
