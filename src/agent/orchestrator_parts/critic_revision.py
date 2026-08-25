# -*- coding: utf-8 -*-
"""Bounded Critic revision and convergence-recheck execution."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from src.agent import critic as _critic
from src.agent.protocols import (
    AgentContext,
    AgentRunStats,
    StageFailureReason,
    StageResult,
    StageStatus,
)
from src.agent.public_contract import AGENT_EXECUTION_FAILURE_MESSAGE
from src.agent.soul import (
    propagate_agent_soul_composition as _propagate_agent_soul_composition,
)
from src.agent.skills.router import skill_instructions_for_run as _skill_instructions_for_run
from src.agent.stream_events import stream_event
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger("src.agent.orchestrator")


class _CriticRevisionRunner:
    """Execute optional Critic work while preserving the Decision reserve."""

    def __init__(
        self,
        orchestrator: Any,
        ctx: AgentContext,
        *,
        stats: AgentRunStats,
        all_tool_calls: List[Dict[str, Any]],
        models_used: List[str],
        started_at: float,
        timeout_seconds: Optional[float],
        decision_budget_reserve_seconds: float,
        optional_stage_margin_seconds: float,
        progress_callback: Optional[Callable],
        cancelled_check: Optional[Callable[[], bool]],
    ) -> None:
        self.orchestrator = orchestrator
        self.ctx = ctx
        self.stats = stats
        self.all_tool_calls = all_tool_calls
        self.models_used = models_used
        self.started_at = started_at
        self.timeout_seconds = timeout_seconds
        self.decision_budget_reserve_seconds = decision_budget_reserve_seconds
        self.optional_stage_margin_seconds = optional_stage_margin_seconds
        self.progress_callback = progress_callback
        self.cancelled_check = cancelled_check

    def remaining_optional_budget_s(self) -> Optional[float]:
        if not self.timeout_seconds:
            return None
        return max(
            0.0,
            self.timeout_seconds - (time.time() - self.started_at),
        )

    def _timeout_budget_s(self) -> Optional[float]:
        remaining_s = self.remaining_optional_budget_s()
        if remaining_s is None:
            return None
        return max(
            0.0,
            remaining_s
            - self.decision_budget_reserve_seconds
            - self.optional_stage_margin_seconds,
        )

    def _record_optional_stage(self, stage_result: StageResult) -> None:
        self.stats.record_stage(stage_result)
        self.all_tool_calls.extend(
            tc for tc in (stage_result.meta.get("tool_calls_log") or [])
        )
        self.models_used.extend(stage_result.meta.get("models_used", []))

    def run_revision(
        self,
        source: Any,
        target: str,
        started_trace: Dict[str, Any],
    ) -> tuple[StageResult, Dict[str, Any]]:
        stage_name = str(source.agent_name or "")
        if self.progress_callback:
            self.progress_callback(stream_event(
                "critic_retry_start",
                stage=stage_name,
                retry_target=target,
                **_critic.trace_event_fields(started_trace),
            ))

        before = _critic.snapshot_target_evidence(self.ctx, target)
        started_elapsed_s = time.time() - self.started_at
        try:
            revision_result, revision_ctx = (
                self.orchestrator._execute_isolated_stage(
                    source,
                    _critic.build_retry_seed(self.ctx, target),
                    stage_name=stage_name,
                    progress_callback=self.progress_callback,
                    timeout_seconds=(
                        self.orchestrator._resolve_stage_timeout_seconds(
                            stage_name,
                            self._timeout_budget_s(),
                        )
                    ),
                    cancelled_check=self.cancelled_check,
                )
            )
            _propagate_agent_soul_composition(revision_ctx, self.ctx)
            if not isinstance(revision_result, StageResult):
                raise TypeError("Critic revision stage returned an invalid result")
            if (
                revision_result.status == StageStatus.COMPLETED
                and not _critic.retry_produced_evidence(
                    revision_ctx,
                    target,
                    strategy_engine=self.orchestrator.strategy_engine,
                )
            ):
                revision_result.status = StageStatus.FAILED
                revision_result.error = AGENT_EXECUTION_FAILURE_MESSAGE
                revision_result.failure_reason = StageFailureReason.STAGE_FAILURE
            if revision_result.status == StageStatus.COMPLETED:
                self.orchestrator._commit_stage_context(self.ctx, revision_ctx)
        except TimeoutError as exc:
            log_safe_exception(
                logger,
                "[Orchestrator] Critic revision timed out",
                exc,
                error_code="agent_critic_retry_timeout",
                level=logging.WARNING,
                context={"stage": stage_name},
            )
            revision_result = StageResult(
                stage_name=stage_name,
                status=StageStatus.FAILED,
                error=AGENT_EXECUTION_FAILURE_MESSAGE,
                failure_reason=StageFailureReason.TIMEOUT,
                meta={"runtime_guard_event": "critic_retry_exception_captured"},
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Optional bounded revision becomes a fail-soft diagnostic.
            log_safe_exception(
                logger,
                "[Orchestrator] Critic revision failed",
                exc,
                error_code="agent_critic_retry_failed",
                level=logging.WARNING,
                context={"stage": stage_name},
            )
            revision_result = StageResult(
                stage_name=stage_name,
                status=StageStatus.FAILED,
                error=AGENT_EXECUTION_FAILURE_MESSAGE,
                failure_reason=StageFailureReason.STAGE_FAILURE,
                meta={"runtime_guard_event": "critic_retry_exception_captured"},
            )

        elapsed_now_s = time.time() - self.started_at
        if revision_result.meta.get("runtime_guard_event") in {
            "critic_retry_exception_captured",
            "stage_timeout",
        }:
            revision_result.duration_s = round(
                max(0.0, elapsed_now_s - started_elapsed_s),
                2,
            )
        completed = revision_result.status == StageStatus.COMPLETED
        _critic.finish_retry(self.ctx, completed=completed)
        trace = _critic.append_revision_round(
            self.ctx,
            target=target,
            before=before,
            after=_critic.snapshot_target_evidence(self.ctx, target),
            status="completed" if completed else "failed",
        )
        revision_result.meta["critic_retry"] = _critic.trace_event_fields(trace)
        self._record_optional_stage(revision_result)
        if self.progress_callback:
            self.progress_callback(stream_event(
                "critic_retry_done",
                stage=stage_name,
                status=revision_result.status.value,
                duration=revision_result.duration_s,
                retry_target=target,
                **_critic.trace_event_fields(trace),
            ))
        if revision_result.status == StageStatus.FAILED:
            self.orchestrator._record_degraded_stage(
                self.ctx,
                stage_name,
                revision_result,
            )
        return revision_result, trace

    def run_recheck(self) -> tuple[StageResult, Optional[str], Dict[str, Any]]:
        recheck_agent = self.orchestrator._prepare_agent(
            _critic.BoundedCriticAgent(
                tool_registry=(
                    self.orchestrator._tool_registry_for_context(self.ctx)
                ),
                llm_adapter=self.orchestrator.llm_adapter,
                skill_instructions=_skill_instructions_for_run(
                    self.orchestrator,
                    self.ctx,
                ),
                technical_skill_policy=(
                    self.orchestrator.technical_skill_policy
                ),
            )
        )
        recheck_agent.max_steps = _critic.CRITIC_MAX_STEPS
        if self.progress_callback:
            self.progress_callback(stream_event(
                "stage_start",
                stage=_critic.CRITIC_STAGE_NAME,
                message="Rechecking Critic convergence...",
            ))
        try:
            recheck_result, recheck_ctx = (
                self.orchestrator._execute_isolated_stage(
                    recheck_agent,
                    self.ctx,
                    stage_name=_critic.CRITIC_STAGE_NAME,
                    progress_callback=self.progress_callback,
                    timeout_seconds=(
                        self.orchestrator._resolve_stage_timeout_seconds(
                            _critic.CRITIC_STAGE_NAME,
                            self._timeout_budget_s(),
                        )
                    ),
                    cancelled_check=self.cancelled_check,
                )
            )
            _propagate_agent_soul_composition(recheck_ctx, self.ctx)
            if not isinstance(recheck_result, StageResult):
                raise TypeError("Critic recheck returned an invalid result")
            if recheck_result.status == StageStatus.COMPLETED:
                self.orchestrator._commit_stage_context(self.ctx, recheck_ctx)
                trace = _critic.get_critic_trace(self.ctx) or {}
                verdict = str(trace.get("verdict") or "")
            else:
                verdict = None
                trace = _critic.mark_convergence_unavailable(
                    self.ctx,
                    "Critic convergence recheck did not complete; the "
                    "revision remains unverified.",
                )
        except Exception as exc:  # broad-exception: fallback_recorded - Optional convergence recheck fails soft with an explicit limitation.
            log_safe_exception(
                logger,
                "[Orchestrator] Critic recheck failed",
                exc,
                error_code="agent_critic_recheck_failed",
                level=logging.WARNING,
            )
            recheck_result = StageResult(
                stage_name=_critic.CRITIC_STAGE_NAME,
                status=StageStatus.FAILED,
                error=AGENT_EXECUTION_FAILURE_MESSAGE,
                failure_reason=StageFailureReason.STAGE_FAILURE,
            )
            verdict = None
            trace = _critic.mark_convergence_unavailable(
                self.ctx,
                "Critic convergence recheck failed; the revision remains "
                "unverified.",
            )

        if (
            recheck_result.status == StageStatus.COMPLETED
            and verdict in {"pass", "fail_soft"}
        ):
            trace = _critic.finalize_convergence(
                self.ctx,
                recheck_verdict=verdict,
            )
        recheck_result.meta["critic"] = _critic.trace_event_fields(trace)
        self._record_optional_stage(recheck_result)
        if self.progress_callback:
            self.progress_callback(stream_event(
                "stage_done",
                stage=_critic.CRITIC_STAGE_NAME,
                status=recheck_result.status.value,
                duration=recheck_result.duration_s,
            ))
            if verdict == "retry":
                self.progress_callback(stream_event(
                    "critic_verdict",
                    stage=_critic.CRITIC_STAGE_NAME,
                    **_critic.trace_event_fields(trace),
                ))
        if recheck_result.status == StageStatus.FAILED:
            self.orchestrator._record_degraded_stage(
                self.ctx,
                _critic.CRITIC_STAGE_NAME,
                recheck_result,
            )
        return recheck_result, verdict, trace
