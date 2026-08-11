# -*- coding: utf-8 -*-
"""Focused tests for the plan→act→observe→replan loop (#199 remaining)."""

from __future__ import annotations

import inspect
import math
from typing import Any, Dict, List

import pytest

from src.agent.executor_parts.run import _RunMethods
from src.agent.planning import (
    PlanExecutionSettings,
    PlanningEngine,
    PlanningSettings,
    execute_plan_loop,
    validate_plan_payload,
)
from src.agent.planning.config import (
    MAX_OBSERVATION_REPLANS,
    MAX_TOTAL_TOOL_CALLS,
)
from src.agent.planning.types import PLAN_SCHEMA_VERSION


def _plan(
    *,
    tools_per_step: List[List[str]],
    available: List[str] | None = None,
):
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
    all_tools = available or sorted({name for group in tools_per_step for name in group})
    payload = {
        "version": PLAN_SCHEMA_VERSION,
        "goal": "Execute research plan",
        "max_steps": max(1, len(steps)),
        "steps": steps,
    }
    return validate_plan_payload(payload, available_tools=all_tools, max_steps=max(1, len(steps))), all_tools


def test_execution_settings_reject_non_finite_and_out_of_range() -> None:
    assert PlanExecutionSettings().max_total_tool_calls == 16
    for kwargs in (
        {"max_total_tool_calls": 0},
        {"max_total_tool_calls": MAX_TOTAL_TOOL_CALLS + 1},
        {"max_observation_replans": -1},
        {"max_observation_replans": MAX_OBSERVATION_REPLANS + 1},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": 0},
        {"on_step_failure": "ignore"},
        {"max_result_summary_chars": 0},
    ):
        with pytest.raises(ValueError):
            PlanExecutionSettings(**kwargs)
    # NaN must not be accepted via math.nan either
    with pytest.raises(ValueError):
        PlanExecutionSettings(timeout_seconds=math.nan)


def test_successful_multi_step_loop_records_observations_and_never_claims_false_success() -> None:
    plan, tools = _plan(tools_per_step=[["get_realtime_quote"], ["analyze_trend"], []])
    calls: List[str] = []

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        calls.append(name)
        assert arguments.get("stock_code") == "600519"
        return {"ok": True, "summary": f"{name}-ok"}

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        context={"stock_code": "600519"},
        settings=PlanExecutionSettings(max_observation_replans=0, on_step_failure="terminate"),
    )
    assert result.success is True
    assert result.status == "succeeded"
    assert result.tool_call_count == 2
    assert calls == ["get_realtime_quote", "analyze_trend"]
    assert len(result.step_observations) == 3
    assert all(obs.status == "succeeded" for obs in result.step_observations)
    meta = result.to_metadata()
    assert meta["success"] is True
    assert meta["tool_call_count"] == 2
    assert meta["initial_plan_id"] == plan.plan_id
    assert meta["observations"][0]["tool_calls"][0]["ok"] is True


def test_tool_failure_terminates_without_fail_open() -> None:
    plan, tools = _plan(tools_per_step=[["get_realtime_quote"], ["analyze_trend"]])

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del arguments
        if name == "get_realtime_quote":
            return {"ok": False, "error": {"code": "provider_error", "message": "down"}}
        return {"ok": True, "summary": "ok"}

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        settings=PlanExecutionSettings(max_observation_replans=0, on_step_failure="terminate"),
    )
    assert result.success is False
    assert result.status == "failed"
    assert result.reason == "step_failed"
    assert result.error_code == "provider_error"
    assert result.tool_call_count == 1
    assert result.step_observations[0].status == "failed"
    # Second step must not run after hard failure under terminate policy.
    assert len(result.step_observations) == 1


def test_missing_ok_field_is_failure_not_success() -> None:
    plan, tools = _plan(tools_per_step=[["get_realtime_quote"]])

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del name, arguments
        return {"result": "looks fine"}  # no explicit ok → must not fail-open

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        settings=PlanExecutionSettings(max_observation_replans=0, on_step_failure="terminate"),
    )
    assert result.success is False
    assert result.error_code == "invalid_tool_result"


def test_tool_call_budget_stops_with_explicit_reason() -> None:
    plan, tools = _plan(
        tools_per_step=[["t1"], ["t2"], ["t3"]],
        available=["t1", "t2", "t3"],
    )

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del arguments
        return {"ok": True, "summary": name}

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        settings=PlanExecutionSettings(
            max_total_tool_calls=2,
            max_observation_replans=0,
            on_step_failure="terminate",
        ),
    )
    assert result.success is False
    assert result.status == "budget_exhausted"
    assert result.reason == "max_tool_calls_exceeded"
    assert result.tool_call_count == 2


def test_observation_replan_avoids_hard_failed_tool_and_can_succeed() -> None:
    """Failed tool is excluded on replan; synthesis-only recovery may succeed."""
    plan, tools = _plan(
        tools_per_step=[["get_realtime_quote"]],
        available=["get_realtime_quote", "get_daily_history"],
    )
    attempts = {"n": 0}

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del arguments
        attempts["n"] += 1
        # First plan calls get_realtime_quote and fails hard.
        if name == "get_realtime_quote":
            return {"ok": False, "error": {"code": "permission_denied", "message": "no"}}
        return {"ok": True, "summary": f"{name}-ok"}

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        task="Analyze 600519",
        context={"stock_code": "600519"},
        settings=PlanExecutionSettings(
            max_observation_replans=1,
            on_step_failure="replan",
            max_total_tool_calls=8,
        ),
        planning_settings=PlanningSettings(
            enabled=True,
            strategy="template",
            max_plan_steps=4,
            max_replans=0,
        ),
    )
    assert result.observation_replans == 1
    assert result.success is True, result.to_metadata()
    assert result.status == "succeeded"
    # Hard-failed tool must not be required after replan for success.
    assert all(
        call.tool_name != "get_realtime_quote" or not call.ok
        for obs in result.step_observations
        for call in obs.tool_calls
        if obs.status == "succeeded"
    )
    meta = result.to_metadata()
    assert meta["observation_replans"] == 1
    assert any(entry.get("role") == "replan" for entry in meta.get("plans", []))


def test_max_observation_replans_exhausted_is_explicit() -> None:
    plan, tools = _plan(tools_per_step=[["always_fail"]], available=["always_fail"])

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del name, arguments
        return {"ok": False, "error": {"code": "handler_error", "message": "boom"}}

    # Custom planner that keeps returning a plan requiring the same failing tool.
    class StickyPlanner:
        def plan(self, task, *, available_tools, context=None, cancelled_check=None, prior_observations=None):
            del task, available_tools, context, cancelled_check, prior_observations
            sticky, _ = _plan(tools_per_step=[["always_fail"]], available=["always_fail"])
            from src.agent.planning.types import PlanningOutcome

            return PlanningOutcome(
                enabled=True,
                applied=True,
                plan=sticky,
                strategy="template",
                requested_strategy="template",
            )

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        settings=PlanExecutionSettings(
            max_observation_replans=1,
            on_step_failure="replan",
            max_total_tool_calls=8,
        ),
        planner=StickyPlanner(),
    )
    assert result.success is False
    assert result.status == "max_observation_replans_exceeded"
    assert result.observation_replans == 1
    assert result.tool_call_count >= 2


def test_cancellation_fence_during_loop() -> None:
    plan, tools = _plan(tools_per_step=[["t1"], ["t2"]], available=["t1", "t2"])
    cancelled = {"value": False}

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del arguments
        if name == "t1":
            cancelled["value"] = True
            return {"ok": True, "summary": "ok"}
        return {"ok": True, "summary": "ok"}

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        settings=PlanExecutionSettings(max_observation_replans=0),
        cancelled_check=lambda: cancelled["value"],
    )
    assert result.success is False
    assert result.cancelled is True
    assert result.status == "cancelled"


def test_invoker_exception_is_step_failure_not_success() -> None:
    plan, tools = _plan(tools_per_step=[["boom"]], available=["boom"])

    def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        del name, arguments
        raise RuntimeError("api_key=sk-secret")

    result = execute_plan_loop(
        plan=plan,
        tool_invoker=invoker,
        available_tools=tools,
        settings=PlanExecutionSettings(max_observation_replans=0, on_step_failure="terminate"),
    )
    assert result.success is False
    assert result.error_code == "invoker_exception"
    assert "sk-secret" not in str(result.to_metadata())


def test_loop_still_not_wired_into_agent_executor_run() -> None:
    source = inspect.getsource(_RunMethods.run)
    assert "execute_plan_loop" not in source
    assert "planning" not in source


def test_planning_engine_accepts_prior_observations_for_template_replan() -> None:
    from src.agent.planning.observations import StepObservation, ToolCallObservation

    engine = PlanningEngine(PlanningSettings(enabled=True, strategy="template", max_plan_steps=4))
    prior = [
        StepObservation(
            step_id=1,
            status="failed",
            goal="quote",
            tool_calls=(
                ToolCallObservation(
                    tool_name="get_realtime_quote",
                    ok=False,
                    error_code="permission_denied",
                    summary="denied",
                ),
            ),
            failure_reason="permission_denied",
        )
    ]
    outcome = engine.plan(
        "Analyze 600519",
        available_tools=["get_realtime_quote", "get_daily_history", "analyze_trend"],
        context={"stock_code": "600519"},
        prior_observations=prior,
    )
    assert outcome.applied and outcome.plan is not None
    # Hard-failed tool must not appear in the replan proposal.
    assert "get_realtime_quote" not in outcome.plan.expected_tool_names
