# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic trajectory evaluation for the owned offline benchmark.

The benchmark invocation is the opt-in consumer. This service has no runtime
environment gate and never mutates the agent runner. It consumes the runner's
already-redacted tool-call log plus benchmark-owned expected-tool annotations.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from itertools import islice
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from pydantic import ValidationError

from src.schemas.agent_trajectory import (
    FAILURE_CLASS_ERROR,
    FAILURE_CLASS_GUARDED,
    FAILURE_CLASS_NONE,
    FAILURE_CLASS_TIMEOUT,
    INPUT_SCHEMA_VERSION,
    MAX_REPORTED_REJECTED_CALLS,
    PATH_ORCHESTRATOR,
    PATH_SINGLE,
    RUBRIC_VERSION,
    TRAJECTORY_EVAL_ENGINE_VERSION,
    TrajectoryEvalResult,
    TrajectoryEvaluationProvenance,
    TrajectoryMetrics,
    TrajectoryRubric,
    TrajectoryRunInput,
    TrajectoryRunProvenance,
    TrajectoryStep,
    TrajectoryToolCallInput,
)


MAX_RUNS = 64
MAX_SOURCE_CALLS_PER_RUN = 2_000
MAX_EVALUATED_CALLS = 2_000
MAX_OUTPUT_STEPS = 1_000
MAX_RESULT_CHARS = 500_000
MAX_ARGUMENT_DEPTH = 4
MAX_ARGUMENT_KEYS = 32
MAX_ARGUMENT_ITEMS = 64
MAX_ARGUMENT_STRING_CHARS = 512
MAX_ARGUMENT_JSON_CHARS = 4_096


def evaluate_agent_trajectory(
    runs: Sequence[TrajectoryRunInput | Mapping[str, Any] | Any],
    *,
    rubric: TrajectoryRubric | Mapping[str, Any],
    path_label: str = PATH_SINGLE,
    as_of: Optional[str] = None,
) -> TrajectoryEvalResult:
    """Evaluate bounded run inputs and return a joinable strict result.

    Invalid runs/calls are counted rather than coerced. Valid calls within a
    partially malformed run remain evaluable. Raw argument bodies are used only
    to compute a bounded SHA-256 fingerprint and are not returned.
    """
    label = _validate_path_label(path_label)
    rubric_model = (
        rubric if isinstance(rubric, TrajectoryRubric) else TrajectoryRubric.model_validate(rubric)
    )
    normalized_as_of = _validate_optional_timestamp(as_of)

    accepted_runs: List[TrajectoryRunInput] = []
    run_provenance: List[TrajectoryRunProvenance] = []
    rejected_run_count = 0
    rejected_call_count = 0
    source_truncated = len(runs) > MAX_RUNS
    remaining_capacity = MAX_EVALUATED_CALLS

    for raw_run in list(runs)[:MAX_RUNS]:
        parsed = _parse_run(raw_run, remaining_capacity=remaining_capacity)
        if parsed is None:
            rejected_run_count += 1
            continue
        run_model, rejected, clipped = parsed
        rejected_call_count += rejected
        source_truncated = source_truncated or clipped or run_model.source_truncated
        accepted_runs.append(run_model)
        remaining_capacity -= len(run_model.tool_calls)
        run_provenance.append(
            TrajectoryRunProvenance(
                run_id=run_model.run_id,
                execution_id=run_model.execution_id,
                task_id=run_model.task_id,
                agent_id=run_model.agent_id,
                stock_code=run_model.stock_code,
                market=run_model.market,
                started_at=run_model.started_at,
                completed=run_model.completed,
                source_truncated=run_model.source_truncated or clipped,
                accepted_call_count=len(run_model.tool_calls),
                rejected_call_count=rejected,
            )
        )
        if remaining_capacity <= 0:
            source_truncated = True
            break

    result = _compute_result(
        accepted_runs,
        rubric=rubric_model,
        path_label=label,
        as_of=normalized_as_of,
        run_provenance=run_provenance,
        rejected_run_count=rejected_run_count,
        rejected_call_count=rejected_call_count,
        source_truncated=source_truncated,
    )
    return _enforce_result_budget(result)


def compute_trajectory_metrics(
    runs: Sequence[TrajectoryRunInput | Mapping[str, Any] | Any],
    *,
    rubric: TrajectoryRubric | Mapping[str, Any],
    path_label: str = PATH_SINGLE,
    as_of: Optional[str] = None,
) -> TrajectoryEvalResult:
    """Compatibility name for the pure benchmark calculation."""
    return evaluate_agent_trajectory(
        runs,
        rubric=rubric,
        path_label=path_label,
        as_of=as_of,
    )


def strict_json_dumps(result: TrajectoryEvalResult) -> str:
    """Serialize without JavaScript-only NaN/Infinity extensions."""
    return json.dumps(
        result.to_dict(),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def duration_to_ms(duration_seconds: Any) -> Optional[int]:
    """Convert a finite 0..3600-second duration to milliseconds."""
    if duration_seconds is None or isinstance(duration_seconds, bool):
        return None
    try:
        value = float(duration_seconds)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(value) or value < 0.0 or value > 3_600.0:
        return None
    return int(value * 1_000.0)


def normalize_tool_arguments(arguments: Any) -> str:
    """Return a bounded canonical JSON representation or raise ``ValueError``."""
    normalized = _canonicalize(arguments, depth=0)
    serialized = json.dumps(
        normalized,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(serialized) > MAX_ARGUMENT_JSON_CHARS:
        raise ValueError("tool arguments exceed canonical size limit")
    return serialized


def classify_failure(entry: TrajectoryToolCallInput | Mapping[str, Any]) -> str:
    """Classify a strictly Boolean tool outcome."""
    success = entry.success if isinstance(entry, TrajectoryToolCallInput) else entry.get("success")
    if success is True:
        return FAILURE_CLASS_NONE
    timeout = entry.timeout if isinstance(entry, TrajectoryToolCallInput) else entry.get("timeout")
    guarded = entry.guarded if isinstance(entry, TrajectoryToolCallInput) else entry.get("guarded")
    if timeout is True:
        return FAILURE_CLASS_TIMEOUT
    if guarded is True:
        return FAILURE_CLASS_GUARDED
    return FAILURE_CLASS_ERROR


def _parse_run(
    raw_run: TrajectoryRunInput | Mapping[str, Any] | Any,
    *,
    remaining_capacity: int,
) -> Optional[Tuple[TrajectoryRunInput, int, bool]]:
    if isinstance(raw_run, TrajectoryRunInput):
        calls_raw: Sequence[Any] = raw_run.tool_calls
        metadata = raw_run.model_dump(exclude={"tool_calls"})
    elif isinstance(raw_run, Mapping):
        calls_value = raw_run.get("tool_calls")
        if not isinstance(calls_value, list):
            return None
        calls_raw = calls_value
        allowed = set(TrajectoryRunInput.model_fields) - {"tool_calls"}
        if any(key not in allowed and key != "tool_calls" for key in raw_run):
            return None
        metadata = {key: raw_run[key] for key in allowed if key in raw_run}
    else:
        return None

    valid_calls: List[TrajectoryToolCallInput] = []
    rejected = 0
    source_limit = min(MAX_SOURCE_CALLS_PER_RUN, max(0, remaining_capacity))
    clipped = len(calls_raw) > source_limit
    # Slice lazily: an oversized source must never be fully materialized here.
    for raw_call in islice(calls_raw, source_limit):
        try:
            call = (
                raw_call
                if isinstance(raw_call, TrajectoryToolCallInput)
                else TrajectoryToolCallInput.model_validate(raw_call)
            )
            normalize_tool_arguments(call.arguments)
        except (ValidationError, TypeError, ValueError, OverflowError):
            rejected += 1
            continue
        valid_calls.append(call)
    rejected += max(0, len(calls_raw) - source_limit)

    try:
        run = TrajectoryRunInput.model_validate({**metadata, "tool_calls": valid_calls})
    except ValidationError:
        return None
    return run, rejected, clipped


_PreparedCall = Tuple[TrajectoryToolCallInput, str, str, Tuple[str, str], Optional[int]]


def _prepare_run_calls(run: TrajectoryRunInput) -> List[_PreparedCall]:
    """Resolve owner, argument fingerprint, causal scope and position per call."""
    prepared: List[_PreparedCall] = []
    for call in run.tool_calls:
        agent_id = call.agent_id or run.agent_id
        argument_json = normalize_tool_arguments(call.arguments)
        argument_fingerprint = hashlib.sha256(argument_json.encode("utf-8")).hexdigest()
        scope_key = (agent_id, f"{call.tool}\0{argument_fingerprint}")
        position = call.dispatch_index if call.dispatch_index is not None else call.step
        prepared.append((call, agent_id, argument_fingerprint, scope_key, position))
    return prepared


def _build_causal_frontier(
    prepared: Sequence[_PreparedCall],
) -> Dict[Tuple[str, str], Tuple[Optional[int], Optional[int]]]:
    """Aggregate the earliest observed and earliest successful position per scope.

    The aggregate depends only on the multiset of ``(position, success)`` pairs,
    never on list order, so parallel same-position completions are interchangeable.
    Calls without a position carry no causal precedence and are excluded.
    """
    frontier: Dict[Tuple[str, str], Tuple[Optional[int], Optional[int]]] = {}
    for call, _agent_id, _fingerprint, scope_key, position in prepared:
        if position is None:
            continue
        earliest_any, earliest_success = frontier.get(scope_key, (None, None))
        if earliest_any is None or position < earliest_any:
            earliest_any = position
        if call.success and (earliest_success is None or position < earliest_success):
            earliest_success = position
        frontier[scope_key] = (earliest_any, earliest_success)
    return frontier


def _classify_causality(
    frontier: Mapping[Tuple[str, str], Tuple[Optional[int], Optional[int]]],
    scope_key: Tuple[str, str],
    position: Optional[int],
) -> Tuple[bool, bool]:
    """Classify one call as redundant, retry, or neither.

    An identical call that already succeeded at a strictly earlier position makes
    this call redundant. Otherwise a strictly earlier identical attempt that never
    succeeded makes it a retry. Same-position calls are parallel and are neither.
    """
    if position is None:
        return False, False
    earliest_any, earliest_success = frontier.get(scope_key, (None, None))
    if earliest_success is not None and earliest_success < position:
        return True, False
    if earliest_any is not None and earliest_any < position:
        return False, True
    return False, False


def _compute_result(
    runs: Sequence[TrajectoryRunInput],
    *,
    rubric: TrajectoryRubric,
    path_label: str,
    as_of: Optional[str],
    run_provenance: List[TrajectoryRunProvenance],
    rejected_run_count: int,
    rejected_call_count: int,
    source_truncated: bool,
) -> TrajectoryEvalResult:
    steps: List[TrajectoryStep] = []
    success_count = 0
    redundant_count = 0
    retry_count = 0
    productive_count = 0
    cache_count = 0
    total_duration_ms = 0
    missing_duration_count = 0
    selected_tools: List[str] = []

    for run in runs:
        # Fingerprints never cross run or agent ownership boundaries.
        prepared = _prepare_run_calls(run)
        # Causality is derived from a position-based frontier aggregated over
        # the whole run before any call is classified, so the completion order
        # of same-position (parallel) results cannot change any classification.
        frontier = _build_causal_frontier(prepared)
        for local_index, (call, agent_id, argument_fingerprint, scope_key, position) in enumerate(
            prepared
        ):
            is_redundant, is_retry = _classify_causality(frontier, scope_key, position)
            if is_redundant:
                redundant_count += 1
            elif is_retry:
                retry_count += 1

            duration_ms = duration_to_ms(call.duration)
            if duration_ms is None:
                missing_duration_count += 1
            else:
                total_duration_ms += duration_ms
            if call.success:
                success_count += 1
            if call.cached:
                cache_count += 1
            if call.success and not is_redundant:
                productive_count += 1
            selected_tools.append(call.tool)

            steps.append(
                TrajectoryStep(
                    index=len(steps),
                    run_id=run.run_id,
                    execution_id=run.execution_id,
                    task_id=run.task_id,
                    agent_id=agent_id,
                    call_id=call.call_id or f"{run.run_id}:{agent_id}:{local_index}",
                    step=call.step,
                    dispatch_index=call.dispatch_index,
                    tool=call.tool,
                    argument_fingerprint=argument_fingerprint,
                    success=call.success,
                    duration_ms=duration_ms,
                    cached=call.cached,
                    failure_class=classify_failure(call),
                    is_redundant=is_redundant,
                    is_retry=is_retry,
                    dispatched_at=call.dispatched_at,
                    started_at=call.started_at,
                    ended_at=call.ended_at,
                )
            )

    sample_size = len(steps)
    precision, recall, f1 = _selection_metrics(selected_tools, rubric)
    completed = [run.completed for run in runs if run.completed is not None]
    completion_rate = (
        sum(1 for value in completed if value) / float(len(completed))
        if completed
        else None
    )
    metrics = TrajectoryMetrics(
        tool_selection_precision=precision,
        tool_selection_recall=recall,
        tool_selection_f1=f1,
        tool_call_success_rate=_rate(success_count, sample_size),
        productive_step_rate=_rate(productive_count, sample_size),
        redundancy_rate=_rate(redundant_count, sample_size),
        retry_rate=_rate(retry_count, sample_size),
        cache_hit_rate=_rate(cache_count, sample_size),
        task_completion_rate=completion_rate,
        redundant_call_count=redundant_count,
        retry_count=retry_count,
        successful_call_count=success_count,
        productive_step_count=productive_count,
        total_duration_ms=total_duration_ms,
        missing_duration_count=missing_duration_count,
        sample_size=sample_size,
    )

    rubric_json = json.dumps(
        rubric.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    rubric_fingerprint = hashlib.sha256(rubric_json.encode("utf-8")).hexdigest()
    reported_rejected_call_count = min(rejected_call_count, MAX_REPORTED_REJECTED_CALLS)
    rejected_call_count_saturated = rejected_call_count > MAX_REPORTED_REJECTED_CALLS

    # The identity payload covers the complete normalized result, so any input
    # difference that moves a metric, a step field (duration, cache, causality,
    # position, timestamps, failure class) or the rejection/truncation evidence
    # also moves ``evaluation_id``. Output-side truncation is a deterministic
    # function of this payload and therefore needs no separate contribution.
    identity_payload = {
        "as_of": as_of,
        "engine": TRAJECTORY_EVAL_ENGINE_VERSION,
        "input_schema_version": INPUT_SCHEMA_VERSION,
        "metrics": metrics.model_dump(mode="json"),
        "path": path_label,
        "rejected_call_count": reported_rejected_call_count,
        "rejected_call_count_saturated": rejected_call_count_saturated,
        "rejected_run_count": rejected_run_count,
        "rubric": rubric_fingerprint,
        "rubric_version": RUBRIC_VERSION,
        "runs": [item.model_dump(mode="json") for item in run_provenance],
        "source_truncated": source_truncated,
        "steps": [step.model_dump(mode="json") for step in steps],
    }
    evaluation_id = hashlib.sha256(
        json.dumps(
            identity_payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    provenance = TrajectoryEvaluationProvenance(
        evaluation_id=evaluation_id,
        input_schema_version=INPUT_SCHEMA_VERSION,
        engine_version=TRAJECTORY_EVAL_ENGINE_VERSION,
        rubric_version=RUBRIC_VERSION,
        rubric_fingerprint=rubric_fingerprint,
        path_label=path_label,
        as_of=as_of,
        run_count=len(runs),
        rejected_run_count=rejected_run_count,
        rejected_call_count=reported_rejected_call_count,
        rejected_call_count_saturated=rejected_call_count_saturated,
        source_truncated=source_truncated,
        output_truncated=False,
        output_dropped_step_count=0,
    )
    return TrajectoryEvalResult(
        provenance=provenance,
        metrics=metrics,
        runs=run_provenance,
        steps=steps[:MAX_OUTPUT_STEPS],
    )


def _enforce_result_budget(result: TrajectoryEvalResult) -> TrajectoryEvalResult:
    steps = list(result.steps)
    initial_dropped = max(0, result.metrics.sample_size - len(steps))
    while steps:
        candidate = _with_output_truncation(result, steps, initial_dropped + len(result.steps) - len(steps))
        if len(strict_json_dumps(candidate)) <= MAX_RESULT_CHARS:
            return candidate
        steps = steps[: max(0, len(steps) // 2)]
    candidate = _with_output_truncation(result, [], result.metrics.sample_size)
    if len(strict_json_dumps(candidate)) > MAX_RESULT_CHARS:
        raise ValueError("trajectory evaluation metadata exceeds result size limit")
    return candidate


def _with_output_truncation(
    result: TrajectoryEvalResult,
    steps: List[TrajectoryStep],
    dropped: int,
) -> TrajectoryEvalResult:
    provenance = result.provenance.model_copy(
        update={
            "output_truncated": dropped > 0,
            "output_dropped_step_count": dropped,
        }
    )
    return result.model_copy(update={"provenance": provenance, "steps": steps})


def _selection_metrics(
    selected_tools: Sequence[str],
    rubric: TrajectoryRubric,
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    required = set(rubric.required_tools)
    if not required:
        return None, None, None
    correct_call_count = sum(1 for tool in selected_tools if tool in required)
    precision = _rate(correct_call_count, len(selected_tools))
    recall = len(required & set(selected_tools)) / float(len(required))
    if precision is None or precision + recall == 0.0:
        f1 = 0.0
    else:
        f1 = 2.0 * precision * recall / (precision + recall)
    return precision, recall, f1


def _rate(numerator: int, denominator: int) -> Optional[float]:
    return numerator / float(denominator) if denominator else None


def _validate_path_label(value: str) -> str:
    if value not in {PATH_SINGLE, PATH_ORCHESTRATOR}:
        raise ValueError("path_label must be 'single' or 'orchestrator'")
    return value


def _validate_optional_timestamp(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValueError("as_of must be a bounded ISO-8601 string")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("as_of must be an ISO-8601 timestamp") from exc
    return value


def _canonicalize(value: Any, *, depth: int) -> Any:
    if depth > MAX_ARGUMENT_DEPTH:
        raise ValueError("tool arguments exceed depth limit")
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("tool arguments contain a non-finite number")
        return value
    if isinstance(value, str):
        if len(value) > MAX_ARGUMENT_STRING_CHARS:
            raise ValueError("tool argument string exceeds length limit")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_ARGUMENT_KEYS:
            raise ValueError("tool arguments exceed mapping key limit")
        normalized: Dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            if not isinstance(key, str) or not key or len(key) > 120:
                raise ValueError("tool argument keys must be bounded strings")
            normalized[key] = _canonicalize(item, depth=depth + 1)
        return normalized
    if isinstance(value, list):
        if len(value) > MAX_ARGUMENT_ITEMS:
            raise ValueError("tool arguments exceed list item limit")
        return [_canonicalize(item, depth=depth + 1) for item in value]
    raise ValueError("tool arguments must contain JSON values only")


__all__ = [
    "MAX_EVALUATED_CALLS",
    "MAX_RESULT_CHARS",
    "PATH_ORCHESTRATOR",
    "PATH_SINGLE",
    "classify_failure",
    "compute_trajectory_metrics",
    "duration_to_ms",
    "evaluate_agent_trajectory",
    "normalize_tool_arguments",
    "strict_json_dumps",
]
