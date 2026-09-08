# -*- coding: utf-8 -*-
"""Opt-in Technical ∥ Intel wave helpers for Native Multi (issue #1290 slice 1)."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import CancelledError, ThreadPoolExecutor, as_completed
from math import ceil
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from src.agent.protocols import (
    AgentContext,
    AgentRunStats,
    StageFailureReason,
    StageResult,
    StageStatus,
    normalize_stage_failure_reason,
)
from src.agent.public_contract import AGENT_EXECUTION_FAILURE_MESSAGE
from src.agent.runtime.guards import StageFailurePolicy, log_runtime_guard_event
from src.agent.runtime_facts import DegradationBoundary, build_agent_runtime_facts
from src.agent.soul import propagate_agent_soul_composition
from src.agent.stream_events import stream_event
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger("src.agent.orchestrator")

WAVE_PAIR = ("technical", "intel")
WAVE_MODES = frozenset({"standard", "full", "specialist"})
WAVE_MAX_WORKERS = 2
WAVE_CHECKPOINT_STAGE = "technical_intel"
HARD_BUDGET_REASONS = frozenset({
    StageFailureReason.BUDGET_TURNS,
    StageFailureReason.BUDGET_TOOLS,
    StageFailureReason.BUDGET_COST,
    StageFailureReason.BUDGET_TOKENS,
})


def skill_batch_timeout_slice(agent_count, *, timeout_seconds):
    """Split remaining wall-clock budget across a bounded skill-batch pool."""
    if timeout_seconds is None:
        return None
    try:
        remaining = float(timeout_seconds)
    except (TypeError, ValueError):
        return None
    if remaining <= 0:
        return 0.0
    count = max(1, int(agent_count or 1))
    worker_count = min(3, count)
    return remaining / max(1, ceil(count / worker_count))


def expand_wave_restored_stages(restored: Optional[Sequence[str]]) -> Set[str]:
    """Treat a completed technical_intel checkpoint as both member stages."""
    expanded = set(restored or ())
    if WAVE_CHECKPOINT_STAGE in expanded:
        expanded.update(WAVE_PAIR)
    return expanded


def _stamp_stage(
    progress_callback: Optional[Callable[[Dict[str, Any]], None]],
    stage_name: str,
) -> Optional[Callable[[Dict[str, Any]], None]]:
    """Ensure in-wave thinking/tool events carry the owning stage name."""
    if progress_callback is None:
        return None

    def _wrapped(event: Dict[str, Any]) -> None:
        payload = dict(event) if isinstance(event, dict) else {"type": str(event)}
        if payload.get("stage") is None:
            payload["stage"] = stage_name
        progress_callback(payload)

    return _wrapped


def _wave_eligible(
    orchestrator: Any,
    agents: Sequence[Any],
    index: int,
    restored_agent_stages: Optional[Sequence[str]],
) -> bool:
    config = getattr(orchestrator, "config", None)
    if not bool(getattr(config, "agent_stage_parallel_enabled", False)):
        return False
    if getattr(orchestrator, "mode", "") not in WAVE_MODES:
        return False
    if index < 0 or index + 1 >= len(agents):
        return False
    left = str(getattr(agents[index], "agent_name", "") or "")
    right = str(getattr(agents[index + 1], "agent_name", "") or "")
    if (left, right) != WAVE_PAIR:
        return False
    restored = set(restored_agent_stages or ())
    if left in restored or right in restored:
        return False
    return True


def _merge_intel_first_wins(
    target: AgentContext,
    intel_ctx: AgentContext,
    *,
    baseline_opinion_count: int,
    baseline_risk_count: int,
) -> None:
    """Apply Intel outputs after Technical, keeping Technical on overlapping keys."""
    sealed_keys = getattr(target.data, "_sealed_keys", frozenset()) or frozenset()
    for key, value in intel_ctx.data.items():
        if key in sealed_keys or key in target.data:
            continue
        target.data[key] = value
    target.opinions.extend(list(intel_ctx.opinions[baseline_opinion_count:]))
    target.risk_flags.extend(list(intel_ctx.risk_flags[baseline_risk_count:]))
    target_meta = target.meta
    intel_meta = intel_ctx.meta
    if isinstance(target_meta, dict) and isinstance(intel_meta, dict):
        for key, value in intel_meta.items():
            if key not in target_meta:
                target_meta[key] = value


def _record_stage_outputs(
    stats: AgentRunStats,
    all_tool_calls: List[Dict[str, Any]],
    models_used: List[str],
    result: StageResult,
) -> None:
    stats.record_stage(result)
    all_tool_calls.extend(tc for tc in (result.meta.get("tool_calls_log") or []))
    models_used.extend(result.meta.get("models_used", []))


def _should_isolate_intel(orchestrator: Any, result: StageResult) -> bool:
    reason = normalize_stage_failure_reason(result.failure_reason)
    if reason in HARD_BUDGET_REASONS:
        return False
    policy = orchestrator.runtime_guard_policy.stage_failure_policy
    return (
        policy == StageFailurePolicy.ISOLATE
        and orchestrator._is_non_critical_stage("intel")
    )


def _fail_fast_result(
    orchestrator: Any,
    *,
    ctx: AgentContext,
    stats: AgentRunStats,
    all_tool_calls: List[Dict[str, Any]],
    error: str,
    failure_reason: Optional[StageFailureReason],
):
    from src.agent.orchestrator import OrchestratorResult

    reason = (
        failure_reason.value
        if failure_reason is not None
        else StageFailureReason.STAGE_FAILURE.value
    )
    return orchestrator._with_budget_snapshot(
        OrchestratorResult(
            success=False,
            error=error,
            stats=stats,
            total_tokens=stats.total_tokens,
            tool_calls_log=all_tool_calls,
            runtime_facts=build_agent_runtime_facts(ctx),
            failure_reason=reason,
        ),
        ctx,
    )


def _run_isolated_member(
    orchestrator: Any,
    agent: Any,
    ctx: AgentContext,
    *,
    stage_name: str,
    progress_callback: Optional[Callable],
    timeout_seconds: Optional[float],
    cancelled_check: Optional[Callable[[], bool]],
) -> tuple[StageResult, Optional[AgentContext]]:
    try:
        result, staged_ctx = orchestrator._execute_isolated_stage(
            agent,
            ctx,
            stage_name=stage_name,
            progress_callback=progress_callback,
            timeout_seconds=timeout_seconds,
            cancelled_check=cancelled_check,
        )
        if not isinstance(result, StageResult):
            raise TypeError("Stage agent returned an invalid result")
        return result, staged_ctx
    except TimeoutError as exc:
        log_safe_exception(
            logger,
            "[Orchestrator] stage execution timed out",
            exc,
            error_code="agent_stage_timeout",
            level=logging.WARNING,
            context={"stage": stage_name},
        )
        log_runtime_guard_event(
            logger,
            "stage_exception_captured",
            scope="stage",
            stage=stage_name,
            exception_type=type(exc).__name__,
            reason=StageFailureReason.TIMEOUT.value,
        )
        return (
            StageResult(
                stage_name=stage_name,
                status=StageStatus.FAILED,
                error=AGENT_EXECUTION_FAILURE_MESSAGE,
                failure_reason=StageFailureReason.TIMEOUT,
                meta={"runtime_guard_event": "stage_exception_captured"},
            ),
            None,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Escaped stage failures become typed results at the isolation boundary.
        log_safe_exception(
            logger,
            "[Orchestrator] stage execution failed",
            exc,
            error_code="agent_stage_exception",
            level=logging.WARNING,
            context={"stage": stage_name},
        )
        log_runtime_guard_event(
            logger,
            "stage_exception_captured",
            scope="stage",
            stage=stage_name,
            exception_type=type(exc).__name__,
            reason=StageFailureReason.STAGE_FAILURE.value,
        )
        return (
            StageResult(
                stage_name=stage_name,
                status=StageStatus.FAILED,
                error=AGENT_EXECUTION_FAILURE_MESSAGE,
                failure_reason=StageFailureReason.STAGE_FAILURE,
                meta={"runtime_guard_event": "stage_exception_captured"},
            ),
            None,
        )


def _save_wave_checkpoint(
    orchestrator: Any,
    ctx: AgentContext,
    *,
    checkpoint_session: Any,
    stage_name: str,
    stage_result: Optional[StageResult] = None,
) -> None:
    if checkpoint_session is None or not getattr(checkpoint_session, "enabled", False):
        return
    from src.services.analysis_stage_checkpoint import (
        agent_stage_name,
        capture_agent_stage_payload,
    )

    try:
        payload_kwargs: Dict[str, Any] = {"stage_name": stage_name}
        if stage_result is not None:
            payload_kwargs["stage_result"] = stage_result
        checkpoint_session.save_stage(
            agent_stage_name(stage_name),
            capture_agent_stage_payload(ctx, **payload_kwargs),
        )
    except Exception as exc:  # broad-exception: fallback_recorded - Checkpoint failure is logged and disables only optional resume state.
        log_safe_exception(
            logger,
            "[Orchestrator] stage checkpoint save failed",
            exc,
            error_code="agent_stage_checkpoint_save_failed",
            level=logging.WARNING,
            context={"stage": stage_name},
        )


def _emit_wave_starts(
    progress_callback: Optional[Callable],
) -> None:
    if progress_callback is None:
        return
    for stage_name in WAVE_PAIR:
        progress_callback(stream_event(
            "stage_start",
            stage=stage_name,
            message=f"Starting {stage_name} analysis...",
        ))


def _emit_wave_dones(
    progress_callback: Optional[Callable],
    results: Dict[str, StageResult],
) -> None:
    if progress_callback is None:
        return
    for stage_name in WAVE_PAIR:
        result = results.get(stage_name)
        if result is None:
            continue
        progress_callback(stream_event(
            "stage_done",
            stage=stage_name,
            status=result.status.value,
            duration=result.duration_s,
        ))


def _mark_stage_entries(
    orchestrator: Any,
    ctx: AgentContext,
    stats: AgentRunStats,
    stage_entry_counts: Dict[str, int],
    stage_name: str,
) -> Optional[Any]:
    observed_entries = stage_entry_counts.get(stage_name, 0) + 1
    stage_entry_limit = orchestrator.runtime_guard_policy.max_stage_entries
    if stage_entry_limit > 0 and observed_entries > stage_entry_limit:
        log_runtime_guard_event(
            logger,
            "stage_loop_detected",
            level=logging.ERROR,
            scope="stage",
            stage=stage_name,
            observed=observed_entries,
            limit=stage_entry_limit,
            action="stop",
        )
        guard_result = StageResult(
            stage_name=stage_name,
            status=StageStatus.FAILED,
            error="Stage re-entry limit exceeded",
            failure_reason=StageFailureReason.LOOP_DETECTED,
            meta={"runtime_guard_event": "stage_loop_detected"},
        )
        stats.record_stage(guard_result)
        orchestrator._record_degraded_event(
            ctx,
            stage=stage_name,
            reason=StageFailureReason.LOOP_DETECTED,
            boundary=DegradationBoundary.BEFORE_STAGE,
        )
        from src.agent.orchestrator import OrchestratorResult
        return orchestrator._with_budget_snapshot(
            OrchestratorResult(
                success=False,
                error=f"Stage '{stage_name}' exceeded the re-entry limit",
                stats=stats,
                total_steps=stats.total_stages,
                total_tokens=stats.total_tokens,
                runtime_facts=build_agent_runtime_facts(ctx),
                failure_reason=StageFailureReason.LOOP_DETECTED.value,
            ),
            ctx,
        )
    stage_entry_counts[stage_name] = observed_entries
    return None


def maybe_run_technical_intel_wave(
    orchestrator: Any,
    agents: Sequence[Any],
    index: int,
    ctx: AgentContext,
    stats: AgentRunStats,
    all_tool_calls: List[Dict[str, Any]],
    models_used: List[str],
    progress_callback: Optional[Callable],
    cancelled_check: Optional[Callable[[], bool]],
    timeout_s: Optional[float],
    elapsed_s: float,
    t0: float,
    restored_agent_stages: Optional[Sequence[str]],
    checkpoint_session: Any,
    parse_dashboard: bool,
    stage_entry_counts: Dict[str, int],
) -> Any:
    """Run Technical ∥ Intel when eligible.

    Returns ``None`` to keep the serial path, an ``int`` next index to
    continue the pipeline, or a terminal ``OrchestratorResult``.
    """
    del parse_dashboard  # wave fail-fast uses the same envelope as serial stages
    if not _wave_eligible(orchestrator, agents, index, restored_agent_stages):
        return None

    for stage_name in WAVE_PAIR:
        loop_result = _mark_stage_entries(
            orchestrator, ctx, stats, stage_entry_counts, stage_name,
        )
        if loop_result is not None:
            return loop_result

    technical_agent = agents[index]
    intel_agent = agents[index + 1]
    baseline_opinion_count = len(ctx.opinions)
    baseline_risk_count = len(ctx.risk_flags)
    cancel_event = threading.Event()

    def _combined_cancelled() -> bool:
        if cancel_event.is_set():
            return True
        return cancelled_check is not None and cancelled_check()

    remaining_timeout_s = None
    if timeout_s:
        remaining_timeout_s = max(0.0, float(timeout_s) - (time.time() - t0))
    technical_timeout = orchestrator._resolve_stage_timeout_seconds(
        "technical", remaining_timeout_s,
    )
    intel_timeout = orchestrator._resolve_stage_timeout_seconds(
        "intel", remaining_timeout_s,
    )

    _emit_wave_starts(progress_callback)
    ctx.meta["stage_parallel"] = {
        "pair": list(WAVE_PAIR),
        "max_workers": WAVE_MAX_WORKERS,
        "merge_order": list(WAVE_PAIR),
    }

    results: Dict[str, StageResult] = {}
    staged: Dict[str, AgentContext] = {}
    pool = ThreadPoolExecutor(max_workers=WAVE_MAX_WORKERS)
    try:
        futures = {
            pool.submit(
                _run_isolated_member,
                orchestrator,
                technical_agent,
                ctx,
                stage_name="technical",
                progress_callback=_stamp_stage(progress_callback, "technical"),
                timeout_seconds=technical_timeout,
                cancelled_check=_combined_cancelled,
            ): "technical",
            pool.submit(
                _run_isolated_member,
                orchestrator,
                intel_agent,
                ctx,
                stage_name="intel",
                progress_callback=_stamp_stage(progress_callback, "intel"),
                timeout_seconds=intel_timeout,
                cancelled_check=_combined_cancelled,
            ): "intel",
        }
        future_by_stage = {stage: future for future, stage in futures.items()}
        for future in as_completed(futures):
            stage_name = futures[future]
            try:
                result, staged_ctx = future.result()
            except CancelledError:
                result = StageResult(
                    stage_name=stage_name,
                    status=StageStatus.FAILED,
                    error=AGENT_EXECUTION_FAILURE_MESSAGE,
                    failure_reason=StageFailureReason.STAGE_FAILURE,
                    meta={"runtime_guard_event": "stage_cancelled"},
                )
                staged_ctx = None
            results[stage_name] = result
            if staged_ctx is not None:
                staged[stage_name] = staged_ctx
            if stage_name == "technical" and result.status != StageStatus.COMPLETED:
                cancel_event.set()
                intel_future = future_by_stage["intel"]
                intel_future.cancel()
        intel_future = future_by_stage["intel"]
        if "intel" not in results:
            try:
                result, staged_ctx = intel_future.result()
                results["intel"] = result
                if staged_ctx is not None:
                    staged["intel"] = staged_ctx
            except CancelledError:
                results["intel"] = StageResult(
                    stage_name="intel",
                    status=StageStatus.FAILED,
                    error=AGENT_EXECUTION_FAILURE_MESSAGE,
                    failure_reason=StageFailureReason.STAGE_FAILURE,
                    meta={"runtime_guard_event": "stage_cancelled"},
                )
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    technical_result = results.get("technical")
    intel_result = results.get("intel")
    if technical_result is None:
        technical_result = StageResult(
            stage_name="technical",
            status=StageStatus.FAILED,
            error=AGENT_EXECUTION_FAILURE_MESSAGE,
            failure_reason=StageFailureReason.STAGE_FAILURE,
        )
        results["technical"] = technical_result
    if intel_result is None:
        intel_result = StageResult(
            stage_name="intel",
            status=StageStatus.FAILED,
            error=AGENT_EXECUTION_FAILURE_MESSAGE,
            failure_reason=StageFailureReason.STAGE_FAILURE,
            meta={"runtime_guard_event": "stage_cancelled"},
        )
        results["intel"] = intel_result

    for stage_name, result in results.items():
        if result.meta.get("runtime_guard_event") in {
            "stage_exception_captured",
            "stage_timeout",
        }:
            result.duration_s = round(max(0.0, time.time() - t0 - elapsed_s), 2)

    technical_ok = technical_result.status == StageStatus.COMPLETED
    intel_ok = intel_result.status == StageStatus.COMPLETED
    commit_intel = technical_ok and intel_ok

    if technical_ok:
        technical_ctx = staged.get("technical")
        if technical_ctx is not None:
            propagate_agent_soul_composition(technical_ctx, ctx)
            orchestrator._commit_stage_context(ctx, technical_ctx)

    if commit_intel:
        intel_ctx = staged.get("intel")
        if intel_ctx is not None:
            propagate_agent_soul_composition(intel_ctx, ctx)
            _merge_intel_first_wins(
                ctx,
                intel_ctx,
                baseline_opinion_count=baseline_opinion_count,
                baseline_risk_count=baseline_risk_count,
            )
        _save_wave_checkpoint(
            orchestrator,
            ctx,
            checkpoint_session=checkpoint_session,
            stage_name=WAVE_CHECKPOINT_STAGE,
            stage_result=technical_result,
        )
    elif technical_ok:
        _save_wave_checkpoint(
            orchestrator,
            ctx,
            checkpoint_session=checkpoint_session,
            stage_name="technical",
            stage_result=technical_result,
        )

    _record_stage_outputs(stats, all_tool_calls, models_used, technical_result)
    _record_stage_outputs(stats, all_tool_calls, models_used, intel_result)
    _emit_wave_dones(progress_callback, results)

    if cancelled_check is not None and cancelled_check():
        return orchestrator._build_cancelled_result(
            stats, all_tool_calls, models_used, time.time() - t0, ctx=ctx,
        )

    if not technical_ok:
        reason = normalize_stage_failure_reason(technical_result.failure_reason)
        log_runtime_guard_event(
            logger,
            "stage_failure_fail_fast",
            level=logging.ERROR,
            scope="stage",
            stage="technical",
            reason=reason.value,
            policy=orchestrator.runtime_guard_policy.stage_failure_policy.value,
            action="stop",
            hard_budget=reason in HARD_BUDGET_REASONS,
        )
        return _fail_fast_result(
            orchestrator,
            ctx=ctx,
            stats=stats,
            all_tool_calls=all_tool_calls,
            error=(
                technical_result.error
                if reason in HARD_BUDGET_REASONS and technical_result.error
                else "Stage 'technical' failed"
            ),
            failure_reason=reason,
        )

    if not intel_ok:
        reason = normalize_stage_failure_reason(intel_result.failure_reason)
        if reason == StageFailureReason.TIMEOUT:
            log_runtime_guard_event(
                logger,
                "stage_timeout",
                scope="stage",
                stage="intel",
                limit_seconds=intel_timeout,
            )
        if not _should_isolate_intel(orchestrator, intel_result):
            log_runtime_guard_event(
                logger,
                "stage_failure_fail_fast",
                level=logging.ERROR,
                scope="stage",
                stage="intel",
                reason=reason.value,
                policy=orchestrator.runtime_guard_policy.stage_failure_policy.value,
                action="stop",
                hard_budget=reason in HARD_BUDGET_REASONS,
            )
            return _fail_fast_result(
                orchestrator,
                ctx=ctx,
                stats=stats,
                all_tool_calls=all_tool_calls,
                error=(
                    intel_result.error
                    if reason in HARD_BUDGET_REASONS and intel_result.error
                    else "Stage 'intel' failed"
                ),
                failure_reason=reason,
            )
        orchestrator._record_degraded_stage(ctx, "intel", intel_result)
        log_runtime_guard_event(
            logger,
            "stage_failure_isolated",
            scope="stage",
            stage="intel",
            reason=reason.value,
            policy=orchestrator.runtime_guard_policy.stage_failure_policy.value,
            action="continue",
        )

    return index + 2
