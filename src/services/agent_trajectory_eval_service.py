# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only Agent trajectory evaluation over runner ``tool_calls_log`` (Issue #269).

Consumes fields already written by the agent runner:

- ``step`` (int, loop step index; may repeat for parallel tools)
- ``tool`` (str)
- ``arguments`` (dict, already redacted by the runner)
- ``success`` (bool)
- ``duration`` (float seconds; converted to ms here)
- ``cached`` (bool)
- optional ``timeout`` (bool)
- optional ``guarded`` (bool)

Does **not** modify runner / executor / orchestrator. Default-off gate:
``AGENT_TRAJECTORY_EVAL_ENABLED`` (env) or ``config.agent_trajectory_eval_enabled``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from src.schemas.agent_trajectory import (
    FAILURE_CLASS_ERROR,
    FAILURE_CLASS_GUARDED,
    FAILURE_CLASS_NONE,
    FAILURE_CLASS_TIMEOUT,
    PATH_LABELS,
    PATH_ORCHESTRATOR,
    PATH_SINGLE,
    TRAJECTORY_EVAL_ENGINE_VERSION,
    TrajectoryEvalResult,
    TrajectoryMetrics,
    TrajectoryStep,
)


logger = logging.getLogger(__name__)

ToolCallsLog = Sequence[Mapping[str, Any]]
PathLabel = str


def is_agent_trajectory_eval_enabled(config: Any = None) -> bool:
    """Return whether trajectory evaluation is enabled (default off).

    Resolution order:

    1. Explicit ``config.agent_trajectory_eval_enabled`` when the attribute exists
    2. Environment variable ``AGENT_TRAJECTORY_EVAL_ENABLED``
    3. Default ``False``

    Config model registration is intentionally not required for this offline
    consumer so the gate works without touching shared config ownership files.
    """
    if config is not None and hasattr(config, "agent_trajectory_eval_enabled"):
        return bool(getattr(config, "agent_trajectory_eval_enabled"))
    return _parse_env_bool(os.getenv("AGENT_TRAJECTORY_EVAL_ENABLED"), False)


def evaluate_agent_trajectory(
    tool_calls_log: Optional[ToolCallsLog] = None,
    *,
    runs: Optional[Sequence[ToolCallsLog]] = None,
    path_label: PathLabel = PATH_SINGLE,
    config: Any = None,
    force: bool = False,
) -> TrajectoryEvalResult:
    """Evaluate one or more ``tool_calls_log`` sequences under the default-off gate.

    Parameters
    ----------
    tool_calls_log:
        Single-run log. Ignored when ``runs`` is provided.
    runs:
        Multiple runs (single-agent or orchestrator-aggregated logs). All runs
        share the same metric functions for comparable baselines.
    path_label:
        ``single`` or ``orchestrator`` — labeling only; does not change formulas.
    config:
        Optional config object exposing ``agent_trajectory_eval_enabled``.
    force:
        When True, compute metrics even if the gate is off (used by pure tests
        and offline tooling). Runtime product callers should leave this False.
    """
    label = _normalize_path_label(path_label)
    if not force and not is_agent_trajectory_eval_enabled(config):
        return _neutral_result(path_label=label, enabled=False)

    run_logs = _collect_runs(tool_calls_log=tool_calls_log, runs=runs)
    return compute_trajectory_metrics(run_logs, path_label=label)


def compute_trajectory_metrics(
    runs: Sequence[ToolCallsLog],
    *,
    path_label: PathLabel = PATH_SINGLE,
) -> TrajectoryEvalResult:
    """Pure metric computation shared by single-agent and orchestrator paths.

    Empty input returns a neutral result with ``sample_size=0`` and nullable
    rate metrics set to ``None`` (never fabricated).
    """
    label = _normalize_path_label(path_label)
    if not runs:
        return TrajectoryEvalResult(
            metrics=_empty_metrics(path_label=label, enabled=True, neutral=True),
            steps=[],
            run_count=0,
        )

    all_steps: List[TrajectoryStep] = []
    total_success = 0
    total_redundant = 0
    total_retry = 0
    total_duration_ms = 0
    global_index = 0

    for run_log in runs:
        run_steps, success_n, redundant_n, retry_n, duration_ms = _evaluate_single_run(
            run_log,
            start_index=global_index,
        )
        all_steps.extend(run_steps)
        total_success += success_n
        total_redundant += redundant_n
        total_retry += retry_n
        total_duration_ms += duration_ms
        global_index += len(run_steps)

    sample_size = len(all_steps)
    run_count = len(runs)
    if sample_size == 0:
        return TrajectoryEvalResult(
            metrics=_empty_metrics(path_label=label, enabled=True, neutral=True),
            steps=[],
            run_count=run_count,
        )

    accuracy = total_success / float(sample_size)
    efficiency = (sample_size - total_redundant) / float(sample_size)

    metrics = TrajectoryMetrics(
        tool_selection_accuracy=accuracy,
        redundant_call_count=total_redundant,
        retry_count=total_retry,
        step_efficiency=efficiency,
        total_duration_ms=total_duration_ms,
        sample_size=sample_size,
        path_label=label,
        engine_version=TRAJECTORY_EVAL_ENGINE_VERSION,
        enabled=True,
        neutral=False,
    )
    return TrajectoryEvalResult(
        metrics=metrics,
        steps=all_steps,
        run_count=run_count,
    )


def normalize_tool_arguments(arguments: Any) -> str:
    """Return a stable fingerprint for argument equality (redundancy / retry).

    Deterministic rules:

    - Non-mapping arguments become a JSON scalar / list via ``default=str``
    - Mapping keys are sorted recursively
    - Output is compact JSON (no whitespace)
    """
    return json.dumps(
        _canonicalize(arguments if arguments is not None else {}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def classify_failure(entry: Mapping[str, Any]) -> str:
    """Classify failure using only runner log fields."""
    if bool(entry.get("success")):
        return FAILURE_CLASS_NONE
    if entry.get("timeout") is True:
        return FAILURE_CLASS_TIMEOUT
    if entry.get("guarded") is True:
        return FAILURE_CLASS_GUARDED
    return FAILURE_CLASS_ERROR


def duration_to_ms(duration_seconds: Any) -> Optional[int]:
    """Convert runner ``duration`` (seconds) to non-negative milliseconds."""
    if duration_seconds is None:
        return None
    try:
        return max(0, int(float(duration_seconds) * 1000.0))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _evaluate_single_run(
    tool_calls_log: Optional[ToolCallsLog],
    *,
    start_index: int = 0,
) -> Tuple[List[TrajectoryStep], int, int, int, int]:
    """Evaluate one run. Returns steps, success_n, redundant_n, retry_n, duration_ms."""
    steps: List[TrajectoryStep] = []
    if not tool_calls_log:
        return steps, 0, 0, 0, 0

    # fingerprint -> last outcome was success (True) or failure (False)
    prior_outcome: Dict[str, bool] = {}
    success_n = 0
    redundant_n = 0
    retry_n = 0
    duration_sum = 0
    emitted = 0

    for raw in tool_calls_log:
        if not isinstance(raw, Mapping):
            continue
        tool = _tool_name(raw.get("tool"))
        args_key = normalize_tool_arguments(raw.get("arguments"))
        fingerprint = f"{tool}\0{args_key}"
        success = bool(raw.get("success"))
        cached = bool(raw.get("cached"))
        duration_ms = duration_to_ms(raw.get("duration"))
        failure_class = classify_failure(raw)

        is_redundant = False
        is_retry = False
        if fingerprint in prior_outcome:
            if prior_outcome[fingerprint] is True:
                # Same tool + same normalized args after a prior success → redundant
                # (includes cache hits re-issued with identical args).
                is_redundant = True
                redundant_n += 1
            else:
                # Same tool + same normalized args after a prior failure → retry
                is_retry = True
                retry_n += 1

        # Update last outcome for this fingerprint (latest attempt wins for chain).
        prior_outcome[fingerprint] = success

        if success:
            success_n += 1
        if duration_ms is not None:
            duration_sum += duration_ms

        step_value = raw.get("step")
        step_int: Optional[int]
        try:
            step_int = int(step_value) if step_value is not None else None
        except (TypeError, ValueError):
            step_int = None

        arguments = raw.get("arguments")
        args_dict: Optional[Dict[str, Any]]
        if isinstance(arguments, dict):
            args_dict = dict(arguments)
        else:
            args_dict = None

        steps.append(
            TrajectoryStep(
                index=start_index + emitted,
                step=step_int,
                tool=tool,
                success=success,
                duration_ms=duration_ms,
                cached=cached,
                failure_class=failure_class,
                is_redundant=is_redundant,
                is_retry=is_retry,
                arguments=args_dict,
            )
        )
        emitted += 1

    return steps, success_n, redundant_n, retry_n, duration_sum


def _collect_runs(
    *,
    tool_calls_log: Optional[ToolCallsLog],
    runs: Optional[Sequence[ToolCallsLog]],
) -> List[ToolCallsLog]:
    if runs is not None:
        return [run if run is not None else [] for run in runs]
    if tool_calls_log is not None:
        return [tool_calls_log]
    return []


def _neutral_result(*, path_label: str, enabled: bool) -> TrajectoryEvalResult:
    logger.debug(
        "agent_trajectory_eval neutral result path_label=%s enabled=%s",
        path_label,
        enabled,
    )
    return TrajectoryEvalResult(
        metrics=_empty_metrics(path_label=path_label, enabled=enabled, neutral=True),
        steps=[],
        run_count=0,
    )


def _empty_metrics(
    *,
    path_label: str,
    enabled: bool,
    neutral: bool,
) -> TrajectoryMetrics:
    return TrajectoryMetrics(
        tool_selection_accuracy=None,
        redundant_call_count=0,
        retry_count=0,
        step_efficiency=None,
        total_duration_ms=0,
        sample_size=0,
        path_label=path_label,
        engine_version=TRAJECTORY_EVAL_ENGINE_VERSION,
        enabled=enabled,
        neutral=neutral,
    )


def _normalize_path_label(path_label: Optional[str]) -> str:
    if path_label in PATH_LABELS:
        return str(path_label)
    if path_label in (None, ""):
        return PATH_SINGLE
    lowered = str(path_label).strip().lower()
    if lowered in PATH_LABELS:
        return lowered
    if lowered in {"multi", "multi_agent", "multi-agent", "orch"}:
        return PATH_ORCHESTRATOR
    return PATH_SINGLE


def _tool_name(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(k): _canonicalize(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _parse_env_bool(value: Optional[str], default: bool = False) -> bool:
    """Local bool parse to avoid hard dependency on config loading in unit tests."""
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    if normalized in {"0", "false", "no", "off", "n"}:
        return False
    if normalized in {"1", "true", "yes", "on", "y"}:
        return True
    return default


__all__ = [
    "PATH_ORCHESTRATOR",
    "PATH_SINGLE",
    "TRAJECTORY_EVAL_ENGINE_VERSION",
    "classify_failure",
    "compute_trajectory_metrics",
    "duration_to_ms",
    "evaluate_agent_trajectory",
    "is_agent_trajectory_eval_enabled",
    "normalize_tool_arguments",
]
