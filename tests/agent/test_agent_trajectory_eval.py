# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contract and counterexample tests for trajectory evaluation (Issue #269)."""

from __future__ import annotations

import json
import math

import pytest

from src.schemas.agent_trajectory import (
    FAILURE_CLASS_GUARDED,
    MAX_REPORTED_REJECTED_CALLS,
    PATH_ORCHESTRATOR,
)
from src.services.agent_trajectory_eval_service import (
    MAX_EVALUATED_CALLS,
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


def test_parallel_completion_order_cannot_flip_a_later_dependent_classification() -> None:
    """Counterexample: two same-step parallel results plus one later call.

    Ordering the parallel pair as success/failure or failure/success must not
    move the later call between ``retry`` and ``redundant``.
    """
    success_first = _evaluate(
        [
            _call(step=1, success=True),
            _call(step=1, success=False),
            _call(step=2, success=True),
        ]
    )
    failure_first = _evaluate(
        [
            _call(step=1, success=False),
            _call(step=1, success=True),
            _call(step=2, success=True),
        ]
    )

    assert [step.is_redundant for step in success_first.steps][:2] == [False, False]
    assert [step.is_retry for step in success_first.steps][:2] == [False, False]
    assert success_first.steps[2].is_redundant is True
    assert success_first.steps[2].is_retry is False

    assert failure_first.steps[2].is_redundant is True
    assert failure_first.steps[2].is_retry is False

    # Causal aggregates are identical. ``evaluation_id`` still differs because
    # the emitted step sequence itself differs, which is a real result difference.
    assert (
        success_first.metrics.redundant_call_count
        == failure_first.metrics.redundant_call_count
        == 1
    )
    assert success_first.metrics.retry_count == failure_first.metrics.retry_count == 0
    assert (
        success_first.metrics.redundancy_rate == failure_first.metrics.redundancy_rate
    )
    assert success_first.metrics.retry_rate == failure_first.metrics.retry_rate


def test_parallel_failures_keep_a_later_call_a_retry_in_any_order() -> None:
    """No same-step success means the later identical call stays a retry."""
    forward = _evaluate(
        [
            _call(step=1, success=False, call_id="a"),
            _call(step=1, success=False, call_id="b"),
            _call(step=2, success=False, call_id="c"),
        ]
    )

    assert forward.steps[2].is_retry is True
    assert forward.steps[2].is_redundant is False
    assert forward.metrics.retry_count == 1
    assert forward.metrics.redundant_call_count == 0


def test_evaluation_id_changes_when_duration_cache_or_result_identity_changes() -> None:
    """Counterexample: identity must cover the material normalized result."""
    base = _evaluate([_call(duration=0.1, cached=False)])
    slower = _evaluate([_call(duration=0.2, cached=False)])
    cached = _evaluate([_call(duration=0.1, cached=True)])
    failed = _evaluate([_call(duration=0.1, cached=False, success=False)])

    assert base.metrics.total_duration_ms != slower.metrics.total_duration_ms
    assert base.metrics.cache_hit_rate != cached.metrics.cache_hit_rate

    identifiers = {
        base.provenance.evaluation_id,
        slower.provenance.evaluation_id,
        cached.provenance.evaluation_id,
        failed.provenance.evaluation_id,
    }
    assert len(identifiers) == 4

    for left, right in (
        (base, slower),
        (base, cached),
        (base, failed),
    ):
        assert strict_json_dumps(left) != strict_json_dumps(right)
        assert left.provenance.evaluation_id != right.provenance.evaluation_id

    # Identical inputs still collapse to one deterministic identity.
    assert base.provenance.evaluation_id == _evaluate(
        [_call(duration=0.1, cached=False)]
    ).provenance.evaluation_id


def test_oversized_source_returns_saturated_evidence_instead_of_raising() -> None:
    """Counterexample: 130,001 valid calls must not raise on output validation."""
    call = _call(step=1)
    result = _evaluate([call] * 130_001)

    assert result.provenance.source_truncated is True
    assert result.provenance.rejected_call_count == MAX_REPORTED_REJECTED_CALLS
    assert result.provenance.rejected_call_count_saturated is True
    # Per-run provenance keeps the exact, unsaturated rejection count.
    assert result.runs[0].rejected_call_count == 130_001 - MAX_EVALUATED_CALLS
    assert result.runs[0].source_truncated is True
    assert result.metrics.sample_size == MAX_EVALUATED_CALLS
    assert len(strict_json_dumps(result)) <= MAX_RESULT_CHARS


def test_rejected_call_count_is_not_saturated_below_the_reported_cap() -> None:
    result = _evaluate([_call(step=1)] * 2_050)

    assert result.provenance.rejected_call_count == 50
    assert result.provenance.rejected_call_count_saturated is False
    assert result.provenance.source_truncated is True


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
