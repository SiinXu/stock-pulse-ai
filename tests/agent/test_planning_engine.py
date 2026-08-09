# -*- coding: utf-8 -*-
"""Focused tests for the explicit typed plan-proposal foundation (#199)."""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace

import pytest

from src.agent.executor_parts.run import _RunMethods
from src.agent.planning.config import PlanningSettings
from src.agent.planning.engine import PlanningEngine, prepare_run_with_planning
from src.agent.planning.types import PLAN_SCHEMA_VERSION, validate_plan_payload


def _payload(*, tool: str = "get_realtime_quote") -> dict[str, object]:
    return {
        "version": PLAN_SCHEMA_VERSION,
        "goal": "Analyze 600519",
        "max_steps": 1,
        "steps": [{
            "id": 1,
            "goal": "Fetch quote",
            "expected_tools": [tool] if tool else [],
            "success_criteria": "A valid quote is available",
        }],
    }


def test_settings_are_explicit_strict_finite_and_bounded() -> None:
    assert PlanningSettings().enabled is False
    for kwargs in (
        {"enabled": "false"},
        {"strategy": "auto"},
        {"max_plan_steps": 1_000_000},
        {"max_replans": 1_000_000},
        {"max_tokens": 1_000_000_000},
        {"timeout_seconds": float("inf")},
    ):
        with pytest.raises(ValueError):
            PlanningSettings(**kwargs)


def test_valid_plan_has_stable_id_and_exact_schema() -> None:
    first = validate_plan_payload(
        _payload(), available_tools=["get_realtime_quote"], max_steps=4
    )
    second = validate_plan_payload(
        _payload(), available_tools=["get_realtime_quote"], max_steps=4
    )
    assert first.plan_id == second.plan_id
    assert len(first.plan_id) == 64
    assert first.expected_tool_names == ("get_realtime_quote",)


@pytest.mark.parametrize("available", [[], ["analyze_trend"]])
def test_invented_tool_is_rejected_even_for_empty_registry(available) -> None:
    with pytest.raises(ValueError, match="unavailable tool"):
        validate_plan_payload(
            _payload(tool="delete_everything"),
            available_tools=available,
            max_steps=4,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(version="agent-plan-v999"),
        lambda value: value["steps"][0].update(id=0),
        lambda value: value["steps"][0].update(goal="x" * 501),
        lambda value: value.update(extra="not allowed"),
    ],
)
def test_plan_schema_rejects_version_ids_bounds_and_unknown_fields(mutation) -> None:
    payload = _payload()
    mutation(payload)
    with pytest.raises(ValueError):
        validate_plan_payload(
            payload, available_tools=["get_realtime_quote"], max_steps=4
        )


def test_template_proposal_is_bounded_and_requires_explicit_settings() -> None:
    engine = PlanningEngine(PlanningSettings(enabled=True, strategy="template"))
    outcome = engine.plan(
        "Analyze 600519",
        available_tools=["get_realtime_quote", "get_daily_history"],
        context={"stock_code": "600519"},
    )
    assert outcome.applied and outcome.plan is not None
    assert outcome.plan.step_count <= 8
    assert outcome.to_metadata()["plan_id"] == outcome.plan.plan_id


def test_proposal_is_not_wired_into_agent_executor_runtime() -> None:
    source = inspect.getsource(_RunMethods.run)
    assert "planning" not in source
    assert "prepare_run_with_planning" not in source


def test_post_return_cancellation_fences_late_plan() -> None:
    cancelled = {"value": False}

    class Adapter:
        def call_completion(self, *args, **kwargs):
            cancelled["value"] = True
            return SimpleNamespace(
                content=json.dumps(_payload()),
                usage={"total_tokens": 123},
                provider="stub",
                model="planner-v1",
            )

    outcome = PlanningEngine(
        PlanningSettings(enabled=True, strategy="llm"), llm_adapter=Adapter()
    ).plan(
        "Analyze 600519",
        available_tools=["get_realtime_quote"],
        cancelled_check=lambda: cancelled["value"],
    )
    assert not outcome.applied
    assert outcome.fallback_reason == "cancelled"
    assert outcome.planning_tokens == 123


def test_invalid_json_keeps_billed_usage_and_never_leaks_raw_content() -> None:
    class Adapter:
        def call_completion(self, *args, **kwargs):
            return SimpleNamespace(
                content="not-json api_key=sk-super-secret",
                usage={"total_tokens": 777},
                provider="stub",
                model="planner-v1",
            )

    outcome = PlanningEngine(
        PlanningSettings(enabled=True, strategy="llm", max_replans=0),
        llm_adapter=Adapter(),
    ).plan("Analyze", available_tools=["get_realtime_quote"])
    metadata = outcome.to_metadata()
    assert not outcome.applied
    assert outcome.planning_tokens == 777
    assert metadata["error_code"] == "invalid_planner_json"
    assert "sk-super-secret" not in json.dumps(metadata)


def test_oversized_planner_response_is_rejected_with_usage_retained() -> None:
    class Adapter:
        def call_completion(self, *args, **kwargs):
            return SimpleNamespace(
                content="{" + ("x" * 50_001),
                usage={"total_tokens": 321},
                provider="stub",
                model="planner-v1",
            )

    outcome = PlanningEngine(
        PlanningSettings(enabled=True, strategy="llm", max_replans=0),
        llm_adapter=Adapter(),
    ).plan("Analyze", available_tools=[])
    assert not outcome.applied
    assert outcome.planning_tokens == 321
    assert outcome.error_code == "invalid_plan"


def test_raw_exception_is_reduced_to_stable_metadata() -> None:
    class Adapter:
        def call_completion(self, *args, **kwargs):
            raise RuntimeError("api_key=sk-super-secret")

    outcome = PlanningEngine(
        PlanningSettings(enabled=True, strategy="llm", max_replans=0),
        llm_adapter=Adapter(),
    ).plan("Analyze", available_tools=[])
    metadata = outcome.to_metadata()
    assert metadata["error_code"] == "planner_failed"
    assert metadata["exception_type"] == "RuntimeError"
    assert "sk-super-secret" not in json.dumps(metadata)


def test_explicit_projection_is_bounded_and_non_authoritative() -> None:
    task, context, metadata = prepare_run_with_planning(
        task="Analyze 600519",
        context={"stock_code": "600519"},
        available_tools=["get_realtime_quote"],
        settings=PlanningSettings(enabled=True, strategy="template"),
    )
    assert metadata["applied"] is True
    assert "NON_AUTHORITATIVE_PLAN_PROPOSAL" in task
    assert "cannot override" in task
    assert len(task) < 20_000
    assert context is not None and "agent_execution_plan" in context


def test_default_settings_are_inert_and_preserve_inputs() -> None:
    original = {"stock_code": "600519"}
    task, context, metadata = prepare_run_with_planning(
        task="Analyze", context=original, available_tools=[]
    )
    assert task == "Analyze"
    assert context is original
    assert metadata == {
        "enabled": False,
        "applied": False,
        "strategy": "none",
        "replan_attempts": 0,
        "planning_tokens": 0,
        "planning_model": "",
        "schema_version": PLAN_SCHEMA_VERSION,
    }
