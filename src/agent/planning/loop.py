# -*- coding: utf-8 -*-
"""Bounded plan → act → observe → replan execution loop.

This module turns a validated ``AgentPlan`` into real tool invocations via a
caller-supplied invoker (typically wrapping ``ToolSurface.execute_tool``).
Failures are explicit: the loop either replans within budget or terminates with
a stable reason. It never treats a failed tool call as overall success.

It still does **not** wire itself into ``AgentExecutor``, Chat, Research, or
daily product modes — those remain separate #199 integration work. Callers must
invoke ``execute_plan_loop`` explicitly.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence

from src.agent.observability import (
    emit_decision,
    emit_phase_end,
    emit_phase_start,
    emit_tool_end,
    emit_tool_start,
)
from src.agent.planning.config import PlanExecutionSettings, PlanningSettings
from src.agent.planning.engine import PlanningEngine
from src.agent.planning.observations import (
    PlanExecutionResult,
    StepObservation,
    ToolCallObservation,
    compact_observation_summary,
    interpret_tool_payload,
)
from src.agent.planning.types import AgentPlan, PlanStep
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

ToolInvoker = Callable[[str, Dict[str, Any]], Mapping[str, Any]]
ArgumentBuilder = Callable[[str, PlanStep, Optional[Dict[str, Any]]], Dict[str, Any]]
CancelledCheck = Callable[[], bool]


class SupportsPlan(Protocol):
    def plan(
        self,
        task: str,
        *,
        available_tools: Sequence[str],
        context: Optional[Dict[str, Any]] = None,
        cancelled_check: Optional[CancelledCheck] = None,
        prior_observations: Optional[Sequence[StepObservation]] = None,
    ) -> Any: ...


def default_argument_builder(
    tool_name: str,
    step: PlanStep,
    context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build minimal tool arguments from execution context.

    Most stock-analysis tools accept ``stock_code``. Unknown context keys are
    ignored so the loop never invents parameters.
    """
    del tool_name, step  # reserved for caller-supplied builders
    args: Dict[str, Any] = {}
    if not isinstance(context, dict):
        return args
    stock = context.get("stock_code")
    if isinstance(stock, str) and stock.strip():
        args["stock_code"] = stock.strip()
    market = context.get("market")
    if isinstance(market, str) and market.strip():
        args["market"] = market.strip()
    return args


def execute_plan_loop(
    *,
    plan: AgentPlan,
    tool_invoker: ToolInvoker,
    available_tools: Sequence[str],
    task: str = "",
    context: Optional[Dict[str, Any]] = None,
    settings: Optional[PlanExecutionSettings] = None,
    planning_settings: Optional[PlanningSettings] = None,
    planner: Optional[SupportsPlan] = None,
    argument_builder: Optional[ArgumentBuilder] = None,
    cancelled_check: Optional[CancelledCheck] = None,
) -> PlanExecutionResult:
    """Execute ``plan`` under hard tool-call / replan / wall-clock bounds.

    Args:
        plan: Validated proposal to execute.
        tool_invoker: Callable ``(tool_name, arguments) -> mapping`` whose
            result must include an exact boolean ``ok`` field (ToolSurface shape
            is accepted). Missing or non-bool ``ok`` is treated as failure.
        available_tools: Authorization set for any observation-driven replan.
        task: Original task text used when replanning.
        context: Optional execution context (for argument defaults / replan).
        settings: Explicit loop bounds; defaults to ``PlanExecutionSettings()``.
        planning_settings: Settings for observation-driven replan attempts.
        planner: Optional planner; defaults to ``PlanningEngine`` when replan
            is permitted.
        argument_builder: Optional ``(tool, step, context) -> args`` override.
        cancelled_check: Cooperative cancellation predicate.

    Returns:
        ``PlanExecutionResult`` with success only when every step succeeded.
    """
    resolved = settings or PlanExecutionSettings()
    build_args = argument_builder or default_argument_builder
    started = time.perf_counter()
    deadline = time.monotonic() + float(resolved.timeout_seconds)

    if not callable(tool_invoker):
        return _terminal(
            success=False,
            status="invalid_invoker",
            reason="invalid_invoker",
            error_code="invalid_invoker",
            plan=plan,
            started=started,
        )

    tools = [name.strip() for name in available_tools if isinstance(name, str) and name.strip()]
    current_plan = plan
    initial_plan_id = plan.plan_id
    plans_trace: List[Dict[str, Any]] = [
        {"plan_id": plan.plan_id, "step_count": plan.step_count, "role": "initial"}
    ]
    observations: List[StepObservation] = []
    tool_call_count = 0
    observation_replans = 0
    planning_tokens = 0

    emit_phase_start(
        "plan_execution",
        attrs={
            "plan_id": initial_plan_id,
            "step_count": plan.step_count,
            "max_total_tool_calls": resolved.max_total_tool_calls,
        },
    )

    try:
        step_index = 0
        while step_index < len(current_plan.steps):
            if cancelled_check is not None and cancelled_check():
                return _finish(
                    success=False,
                    status="cancelled",
                    reason="cancelled",
                    error_code="cancelled",
                    plan=current_plan,
                    initial_plan_id=initial_plan_id,
                    observations=observations,
                    tool_call_count=tool_call_count,
                    observation_replans=observation_replans,
                    planning_tokens=planning_tokens,
                    plans_trace=plans_trace,
                    started=started,
                    cancelled=True,
                    phase_status="cancelled",
                )
            if time.monotonic() >= deadline:
                return _finish(
                    success=False,
                    status="timed_out",
                    reason="execution_timeout",
                    error_code="execution_timeout",
                    plan=current_plan,
                    initial_plan_id=initial_plan_id,
                    observations=observations,
                    tool_call_count=tool_call_count,
                    observation_replans=observation_replans,
                    planning_tokens=planning_tokens,
                    plans_trace=plans_trace,
                    started=started,
                    timed_out=True,
                    phase_status="timed_out",
                )

            step = current_plan.steps[step_index]
            emit_phase_start(
                "plan_step",
                step=step.id,
                attrs={
                    "goal_chars": len(step.goal),
                    "expected_tools": list(step.expected_tools),
                },
            )
            step_obs, tool_call_count, budget_hit = _execute_step(
                step=step,
                tool_invoker=tool_invoker,
                build_args=build_args,
                context=context,
                tool_call_count=tool_call_count,
                max_total_tool_calls=resolved.max_total_tool_calls,
                max_summary_chars=resolved.max_result_summary_chars,
                deadline=deadline,
                cancelled_check=cancelled_check,
            )
            observations.append(step_obs)
            emit_phase_end(
                "plan_step",
                status=step_obs.status,
                step=step.id,
                attrs={"failure_reason": step_obs.failure_reason or ""},
            )

            if budget_hit == "cancelled":
                return _finish(
                    success=False,
                    status="cancelled",
                    reason="cancelled",
                    error_code="cancelled",
                    plan=current_plan,
                    initial_plan_id=initial_plan_id,
                    observations=observations,
                    tool_call_count=tool_call_count,
                    observation_replans=observation_replans,
                    planning_tokens=planning_tokens,
                    plans_trace=plans_trace,
                    started=started,
                    cancelled=True,
                    phase_status="cancelled",
                )
            if budget_hit == "timed_out":
                return _finish(
                    success=False,
                    status="timed_out",
                    reason="execution_timeout",
                    error_code="execution_timeout",
                    plan=current_plan,
                    initial_plan_id=initial_plan_id,
                    observations=observations,
                    tool_call_count=tool_call_count,
                    observation_replans=observation_replans,
                    planning_tokens=planning_tokens,
                    plans_trace=plans_trace,
                    started=started,
                    timed_out=True,
                    phase_status="timed_out",
                )
            if budget_hit == "max_tool_calls_exceeded":
                return _finish(
                    success=False,
                    status="budget_exhausted",
                    reason="max_tool_calls_exceeded",
                    error_code="max_tool_calls_exceeded",
                    plan=current_plan,
                    initial_plan_id=initial_plan_id,
                    observations=observations,
                    tool_call_count=tool_call_count,
                    observation_replans=observation_replans,
                    planning_tokens=planning_tokens,
                    plans_trace=plans_trace,
                    started=started,
                    phase_status="failed",
                )

            if step_obs.status == "succeeded":
                step_index += 1
                continue

            # Step failed: replan or terminate. Never claim overall success.
            if (
                resolved.on_step_failure == "terminate"
                or observation_replans >= resolved.max_observation_replans
            ):
                reason = (
                    "step_failed"
                    if resolved.on_step_failure == "terminate"
                    or resolved.max_observation_replans == 0
                    else "max_observation_replans_exceeded"
                )
                status = (
                    "failed"
                    if reason == "step_failed"
                    else "max_observation_replans_exceeded"
                )
                return _finish(
                    success=False,
                    status=status,
                    reason=reason,
                    error_code=step_obs.failure_reason or "step_failed",
                    plan=current_plan,
                    initial_plan_id=initial_plan_id,
                    observations=observations,
                    tool_call_count=tool_call_count,
                    observation_replans=observation_replans,
                    planning_tokens=planning_tokens,
                    plans_trace=plans_trace,
                    started=started,
                    phase_status="failed",
                )

            replan_outcome = _replan(
                task=task or current_plan.goal,
                available_tools=tools,
                context=context,
                observations=observations,
                planning_settings=planning_settings,
                planner=planner,
                cancelled_check=cancelled_check,
            )
            observation_replans += 1
            planning_tokens += int(getattr(replan_outcome, "planning_tokens", 0) or 0)

            if (
                not getattr(replan_outcome, "applied", False)
                or getattr(replan_outcome, "plan", None) is None
            ):
                return _finish(
                    success=False,
                    status="replan_failed",
                    reason=getattr(replan_outcome, "fallback_reason", None)
                    or "replan_failed",
                    error_code=getattr(replan_outcome, "error_code", None)
                    or "replan_failed",
                    plan=current_plan,
                    initial_plan_id=initial_plan_id,
                    observations=observations,
                    tool_call_count=tool_call_count,
                    observation_replans=observation_replans,
                    planning_tokens=planning_tokens,
                    plans_trace=plans_trace,
                    started=started,
                    phase_status="failed",
                )

            new_plan: AgentPlan = replan_outcome.plan
            plans_trace.append(
                {
                    "plan_id": new_plan.plan_id,
                    "step_count": new_plan.step_count,
                    "role": "replan",
                    "after_failed_step": step.id,
                    "replan_index": observation_replans,
                }
            )
            emit_decision(
                "plan_replan",
                attrs={
                    "previous_plan_id": current_plan.plan_id,
                    "new_plan_id": new_plan.plan_id,
                    "observation_replans": observation_replans,
                    "failed_step_id": step.id,
                },
            )
            # Replace the active plan and restart from the first step of the
            # new proposal. Prior observations remain in the audit trail.
            current_plan = new_plan
            step_index = 0

        return _finish(
            success=True,
            status="succeeded",
            reason=None,
            error_code=None,
            plan=current_plan,
            initial_plan_id=initial_plan_id,
            observations=observations,
            tool_call_count=tool_call_count,
            observation_replans=observation_replans,
            planning_tokens=planning_tokens,
            plans_trace=plans_trace,
            started=started,
            phase_status="success",
        )
    except Exception as exc:  # broad-exception: fallback_recorded - loop must never raise into callers as fake success
        log_safe_exception(
            logger,
            "Plan execution loop failed unexpectedly",
            exc,
            error_code="plan_execution_loop_failed",
            level=logging.ERROR,
        )
        return _finish(
            success=False,
            status="failed",
            reason="loop_error",
            error_code="loop_error",
            plan=current_plan,
            initial_plan_id=initial_plan_id,
            observations=observations,
            tool_call_count=tool_call_count,
            observation_replans=observation_replans,
            planning_tokens=planning_tokens,
            plans_trace=plans_trace,
            started=started,
            phase_status="failed",
        )


def _execute_step(
    *,
    step: PlanStep,
    tool_invoker: ToolInvoker,
    build_args: ArgumentBuilder,
    context: Optional[Dict[str, Any]],
    tool_call_count: int,
    max_total_tool_calls: int,
    max_summary_chars: int,
    deadline: float,
    cancelled_check: Optional[CancelledCheck],
) -> tuple[StepObservation, int, Optional[str]]:
    """Run one step's expected tools; return observation, new count, optional fence."""
    calls: List[ToolCallObservation] = []

    if not step.expected_tools:
        return (
            StepObservation(
                step_id=step.id,
                status="succeeded",
                goal=step.goal,
                tool_calls=(),
            ),
            tool_call_count,
            None,
        )

    for tool_name in step.expected_tools:
        if cancelled_check is not None and cancelled_check():
            calls.append(
                ToolCallObservation(
                    tool_name=tool_name,
                    ok=False,
                    error_code="cancelled",
                    summary="cancelled",
                    step_id=step.id,
                )
            )
            return (
                StepObservation(
                    step_id=step.id,
                    status="cancelled",
                    goal=step.goal,
                    tool_calls=tuple(calls),
                    failure_reason="cancelled",
                ),
                tool_call_count,
                "cancelled",
            )
        if time.monotonic() >= deadline:
            calls.append(
                ToolCallObservation(
                    tool_name=tool_name,
                    ok=False,
                    error_code="execution_timeout",
                    summary="execution timeout",
                    step_id=step.id,
                )
            )
            return (
                StepObservation(
                    step_id=step.id,
                    status="timed_out",
                    goal=step.goal,
                    tool_calls=tuple(calls),
                    failure_reason="execution_timeout",
                ),
                tool_call_count,
                "timed_out",
            )
        if tool_call_count >= max_total_tool_calls:
            calls.append(
                ToolCallObservation(
                    tool_name=tool_name,
                    ok=False,
                    error_code="max_tool_calls_exceeded",
                    summary="tool call budget exhausted",
                    step_id=step.id,
                )
            )
            return (
                StepObservation(
                    step_id=step.id,
                    status="budget_exhausted",
                    goal=step.goal,
                    tool_calls=tuple(calls),
                    failure_reason="max_tool_calls_exceeded",
                ),
                tool_call_count,
                "max_tool_calls_exceeded",
            )

        tool_call_count += 1
        args = build_args(tool_name, step, context)
        if not isinstance(args, dict):
            args = {}
        emit_tool_start(
            tool_name,
            step=step.id,
            attrs={
                "plan_step_id": step.id,
                "argument_keys": sorted(str(k) for k in args.keys())[:16],
            },
        )
        call_started = time.perf_counter()
        try:
            raw = tool_invoker(tool_name, args)
        except Exception as exc:  # broad-exception: fallback_recorded - tool failures become observations
            log_safe_exception(
                logger,
                "Plan-loop tool invoker raised",
                exc,
                error_code="plan_loop_tool_invoker_failed",
                level=logging.WARNING,
                context={"tool_name": tool_name, "step_id": step.id},
            )
            duration_ms = max(0, int((time.perf_counter() - call_started) * 1000))
            emit_tool_end(
                tool_name,
                success=False,
                duration_ms=duration_ms,
                step=step.id,
                attrs={"error_code": "invoker_exception"},
            )
            calls.append(
                ToolCallObservation(
                    tool_name=tool_name,
                    ok=False,
                    error_code="invoker_exception",
                    summary="invoker raised",
                    duration_ms=duration_ms,
                    step_id=step.id,
                )
            )
            return (
                StepObservation(
                    step_id=step.id,
                    status="failed",
                    goal=step.goal,
                    tool_calls=tuple(calls),
                    failure_reason="invoker_exception",
                ),
                tool_call_count,
                None,
            )

        ok, error_code, summary = interpret_tool_payload(raw)
        if len(summary) > max_summary_chars:
            summary = summary[:max_summary_chars]
        duration_ms = max(0, int((time.perf_counter() - call_started) * 1000))
        emit_tool_end(
            tool_name,
            success=ok,
            duration_ms=duration_ms,
            step=step.id,
            attrs={"error_code": error_code or "", "summary_chars": len(summary)},
        )
        calls.append(
            ToolCallObservation(
                tool_name=tool_name,
                ok=ok,
                error_code=error_code,
                summary=summary,
                duration_ms=duration_ms,
                step_id=step.id,
            )
        )
        if not ok:
            return (
                StepObservation(
                    step_id=step.id,
                    status="failed",
                    goal=step.goal,
                    tool_calls=tuple(calls),
                    failure_reason=error_code or "tool_failed",
                ),
                tool_call_count,
                None,
            )

    return (
        StepObservation(
            step_id=step.id,
            status="succeeded",
            goal=step.goal,
            tool_calls=tuple(calls),
        ),
        tool_call_count,
        None,
    )


def _replan(
    *,
    task: str,
    available_tools: Sequence[str],
    context: Optional[Dict[str, Any]],
    observations: Sequence[StepObservation],
    planning_settings: Optional[PlanningSettings],
    planner: Optional[SupportsPlan],
    cancelled_check: Optional[CancelledCheck],
) -> Any:
    """Produce a replacement plan from prior observations."""
    settings = planning_settings or PlanningSettings(
        enabled=True,
        strategy="template",
        max_plan_steps=8,
        max_replans=0,
    )
    if not settings.enabled:
        from src.agent.planning.types import PlanningOutcome

        return PlanningOutcome(
            enabled=False,
            applied=False,
            strategy="none",
            fallback_reason="planning_disabled",
            error_code="planning_disabled",
        )

    engine: SupportsPlan = planner or PlanningEngine(settings)
    replan_context: Dict[str, Any] = dict(context or {})
    replan_context["prior_observations_summary"] = compact_observation_summary(
        observations
    )
    non_retriable = {
        call.tool_name
        for obs in observations
        for call in obs.tool_calls
        if not call.ok
        and call.error_code not in {None, "timeout", "retriable", "provider_error"}
    }
    remaining_tools = [name for name in available_tools if name not in non_retriable]
    tools_for_replan = (
        remaining_tools
        if remaining_tools or not available_tools
        else list(available_tools)
    )

    return engine.plan(
        task,
        available_tools=tools_for_replan,
        context=replan_context,
        cancelled_check=cancelled_check,
        prior_observations=observations,
    )


def _terminal(
    *,
    success: bool,
    status: str,
    reason: Optional[str],
    error_code: Optional[str],
    plan: Optional[AgentPlan],
    started: float,
) -> PlanExecutionResult:
    return PlanExecutionResult(
        success=success,
        status=status,
        plan=plan,
        initial_plan_id=plan.plan_id if plan is not None else None,
        final_plan_id=plan.plan_id if plan is not None else None,
        reason=reason,
        error_code=error_code,
        duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )


def _finish(
    *,
    success: bool,
    status: str,
    reason: Optional[str],
    error_code: Optional[str],
    plan: Optional[AgentPlan],
    initial_plan_id: Optional[str],
    observations: List[StepObservation],
    tool_call_count: int,
    observation_replans: int,
    planning_tokens: int,
    plans_trace: List[Dict[str, Any]],
    started: float,
    cancelled: bool = False,
    timed_out: bool = False,
    phase_status: str = "success",
) -> PlanExecutionResult:
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    result = PlanExecutionResult(
        success=success,
        status=status,
        plan=plan,
        initial_plan_id=initial_plan_id,
        final_plan_id=plan.plan_id if plan is not None else initial_plan_id,
        step_observations=list(observations),
        tool_call_count=tool_call_count,
        observation_replans=observation_replans,
        planning_tokens=planning_tokens,
        reason=reason,
        error_code=error_code,
        cancelled=cancelled,
        timed_out=timed_out,
        duration_ms=duration_ms,
        plans=list(plans_trace),
    )
    emit_phase_end(
        "plan_execution",
        status=phase_status,
        duration_ms=duration_ms,
        attrs={
            "success": success,
            "status": status,
            "tool_call_count": tool_call_count,
            "observation_replans": observation_replans,
            "reason": reason or "",
        },
    )
    emit_decision(
        "plan_execution_terminal",
        attrs={
            "success": success,
            "status": status,
            "plan_id": plan.plan_id if plan is not None else "",
            "tool_call_count": tool_call_count,
            "observation_replans": observation_replans,
        },
    )
    return result
