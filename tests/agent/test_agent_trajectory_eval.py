# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract and counterexample tests for trajectory evaluation (Issue #269)."""

from __future__ import annotations

import json
import math

import pytest

from src.schemas.agent_trajectory import (
    FAILURE_CLASS_GUARDED,
    PATH_ORCHESTRATOR,
)
from src.services.agent_trajectory_eval_service import (
    MAX_RESULT_CHARS,
    classify_failure,
    duration_to_ms,
    evaluate_agent_trajectory,
    normalize_tool_arguments,
    strict_json_dumps,
)


def _call(
    *,
    tool: str = "get_realtime_quote",
    success: bool = True,
    step: int | None = 1,
    arguments: object = None,
    agent_id: str | None = None,
    duration: float | None = 0.1,
    cached: bool = False,
    **extra: object,
) -> dict:
    row = {
        "tool": tool,
        "arguments": {"stock_code": "600519"} if arguments is None else arguments,
        "success": success,
        "step": step,
        "duration": duration,
        "cached": cached,
        "result_length": 10,
    }
    if agent_id is not None:
        row["agent_id"] = agent_id
    row.update(extra)
    return row


def _run(calls: list[object], **extra: object) -> dict:
    payload = {
        "run_id": "run-1",
        "execution_id": "execution-1",
        "task_id": "task-1",
        "agent_id": "agent-1",
        "stock_code": "600519",
        "market": "A",
        "completed": True,
        "tool_calls": calls,
    }
    payload.update(extra)
    return payload


def _evaluate(calls: list[object], **kwargs: object):
    return evaluate_agent_trajectory(
        [_run(calls)],
        rubric={"required_tools": ["get_realtime_quote"], "forbidden_tools": []},
        **kwargs,
    )


def test_wrong_but_successful_tool_does_not_score_selection_quality() -> None:
    result = _evaluate([_call(tool="wrong_tool", success=True)])

    assert result.metrics.tool_call_success_rate == 1.0
    assert result.metrics.tool_selection_precision == 0.0
    assert result.metrics.tool_selection_recall == 0.0
    assert result.metrics.tool_selection_f1 == 0.0


def test_repeated_total_failure_cannot_receive_perfect_productive_rate() -> None:
    calls = [_call(success=False, step=index) for index in (1, 2, 3)]
    result = evaluate_agent_trajectory(
        [_run(calls, completed=False)],
        rubric={"required_tools": ["get_realtime_quote"], "forbidden_tools": []},
    )

    assert result.metrics.retry_count == 2
    assert result.metrics.retry_rate == pytest.approx(2 / 3)
    assert result.metrics.tool_call_success_rate == 0.0
    assert result.metrics.productive_step_rate == 0.0
    assert result.metrics.task_completion_rate == 0.0


def test_same_step_parallel_calls_are_not_causally_redundant() -> None:
    result = _evaluate([_call(step=4), _call(step=4)])

    assert result.metrics.redundant_call_count == 0
    assert [step.is_redundant for step in result.steps] == [False, False]


def test_independent_agents_never_share_redundancy_state() -> None:
    result = evaluate_agent_trajectory(
        [
            _run(
                [
                    _call(step=1, agent_id="fundamental"),
                    _call(step=2, agent_id="technical"),
                ]
            )
        ],
        rubric={"required_tools": ["get_realtime_quote"], "forbidden_tools": []},
        path_label=PATH_ORCHESTRATOR,
    )

    assert result.metrics.redundant_call_count == 0
    assert {step.agent_id for step in result.steps} == {"fundamental", "technical"}


def test_independent_runs_keep_identity_and_never_share_fingerprint_state() -> None:
    result = evaluate_agent_trajectory(
        [
            _run([_call(step=1)], run_id="run-1"),
            _run([_call(step=2)], run_id="run-2", execution_id="execution-2"),
        ],
        rubric={"required_tools": ["get_realtime_quote"], "forbidden_tools": []},
    )

    assert result.metrics.redundant_call_count == 0
    assert [step.run_id for step in result.steps] == ["run-1", "run-2"]
    assert [run.run_id for run in result.runs] == ["run-1", "run-2"]


def test_later_same_scope_call_after_success_is_redundant() -> None:
    result = _evaluate([_call(step=1), _call(step=2)])

    assert result.metrics.redundant_call_count == 1
    assert result.steps[1].is_redundant is True
    assert result.metrics.productive_step_rate == 0.5


def test_string_boolean_is_rejected_instead_of_coerced() -> None:
    result = _evaluate([_call(success="false")])  # type: ignore[arg-type]

    assert result.metrics.sample_size == 0
    assert result.provenance.rejected_call_count == 1
    assert result.runs[0].rejected_call_count == 1


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 10**1000])
def test_non_finite_or_unbounded_duration_is_rejected(value: object) -> None:
    result = _evaluate([_call(duration=value)])  # type: ignore[arg-type]

    assert result.metrics.sample_size == 0
    assert result.provenance.rejected_call_count == 1
    assert duration_to_ms(value) is None


def test_non_json_argument_is_rejected_and_output_is_strict_json() -> None:
    result = _evaluate([_call(arguments={"codes": {"600519"}})])

    assert result.metrics.sample_size == 0
    assert result.provenance.rejected_call_count == 1
    serialized = strict_json_dumps(result)
    assert json.loads(serialized) == result.to_dict()
    assert "NaN" not in serialized and "Infinity" not in serialized


def test_argument_bodies_are_replaced_by_stable_fingerprints() -> None:
    first = _evaluate([_call(arguments={"b": 2, "a": [1, "x"]})])
    second = _evaluate([_call(arguments={"a": [1, "x"], "b": 2})])

    assert normalize_tool_arguments({"b": 2, "a": [1, "x"]}) == '{"a":[1,"x"],"b":2}'
    assert first.steps[0].argument_fingerprint == second.steps[0].argument_fingerprint
    assert "arguments" not in first.steps[0].model_dump()


def test_invalid_path_label_is_rejected() -> None:
    with pytest.raises(ValueError, match="path_label"):
        _evaluate([_call()], path_label="multi")


def test_provenance_is_joinable_and_deterministic() -> None:
    first = _evaluate([_call(call_id="call-1")], as_of="2026-08-09T00:00:00Z")
    second = _evaluate([_call(call_id="call-1")], as_of="2026-08-09T00:00:00Z")

    assert first.provenance.evaluation_id == second.provenance.evaluation_id
    assert first.steps[0].run_id == "run-1"
    assert first.steps[0].execution_id == "execution-1"
    assert first.steps[0].task_id == "task-1"
    assert first.steps[0].call_id == "call-1"


def test_empty_expected_tool_annotations_keep_selection_metrics_unavailable() -> None:
    result = evaluate_agent_trajectory(
        [_run([_call()])],
        rubric={"required_tools": [], "forbidden_tools": []},
    )

    assert result.metrics.tool_selection_precision is None
    assert result.metrics.tool_selection_recall is None
    assert result.metrics.tool_selection_f1 is None
    assert result.metrics.tool_call_success_rate == 1.0


def test_result_step_detail_and_serialized_size_are_bounded() -> None:
    calls = [
        _call(step=index, arguments={"stock_code": "600519", "index": index})
        for index in range(1_050)
    ]
    result = _evaluate(calls)
    serialized = strict_json_dumps(result)

    assert result.metrics.sample_size == 1_050
    assert len(result.steps) <= 1_000
    assert result.provenance.output_truncated is True
    assert result.provenance.output_dropped_step_count >= 50
    assert len(serialized) <= MAX_RESULT_CHARS


def test_malformed_run_is_counted_without_crashing_valid_run() -> None:
    result = evaluate_agent_trajectory(
        ["bad-run", _run([_call()])],
        rubric={"required_tools": ["get_realtime_quote"], "forbidden_tools": []},
    )

    assert result.provenance.rejected_run_count == 1
    assert result.provenance.run_count == 1
    assert result.metrics.sample_size == 1


def test_failure_class_uses_exact_boolean_fields() -> None:
    assert classify_failure({"success": False, "guarded": True}) == FAILURE_CLASS_GUARDED
