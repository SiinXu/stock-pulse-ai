# -*- coding: utf-8 -*-
"""Production wiring: plan → act → observe → replan on the Agent RUN path.

Default-off. When ``Config.agent_planning_enabled`` is true, ``AgentExecutor.run``
invokes this module so the planning loop participates in the real analysis
orchestration path. Tools dispatch through ``BoundToolSession`` (same authority
as the native runner). Failures terminate with explicit reasons; nothing here
claims success after a failed plan step or exhausted budget.

Config is constructor/parameter injected (or resolved via the composition root).
This module does not call bare ``get_config()``.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.planning.config import (
    MAX_EXECUTION_TIMEOUT_SECONDS,
    MAX_OBSERVATION_REPLANS,
    MAX_PLAN_STEPS,
    MAX_PLANNER_TIMEOUT_SECONDS,
    MAX_PLANNER_TOKENS,
    MAX_REPLANS,
    MAX_TOTAL_TOOL_CALLS,
    FAILURE_POLICIES,
    PlanExecutionSettings,
    PlanningSettings,
)
from src.agent.planning.engine import PlanningEngine
from src.agent.planning.loop import execute_plan_loop
from src.agent.planning.observations import compact_observation_summary
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.stock_scope import resolve_stock_scope
from src.services.security_audit_service import get_security_audit_service
from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)

CancelledCheck = Callable[[], bool]
ReflectionComplete = Callable[[str, str], str]
REFLECTION_MAX_TOKENS = 800


def _resolve_config(config: Any = None) -> Any:
    """Prefer injected Config; fall back to composition-root access."""
    if config is not None:
        return config
    from src.application_services import get_application_services

    return get_application_services().config


def is_agent_planning_enabled(config: Any = None) -> bool:
    """Return whether the production planning path is opted in."""
    cfg = _resolve_config(config)
    return bool(getattr(cfg, "agent_planning_enabled", False))


def resolve_planning_settings(
    config: Any = None,
) -> Tuple[PlanningSettings, PlanExecutionSettings]:
    """Build finite planning/execution settings from shared Config.

    Values are taken from Config (already env-parsed with finite clamps).
    ``PlanningSettings`` / ``PlanExecutionSettings`` re-validate and reject
    non-finite or out-of-range numbers.
    """
    cfg = _resolve_config(config)
    strategy = str(getattr(cfg, "agent_planning_strategy", "template") or "template").strip().lower()
    if strategy not in {"template", "llm"}:
        strategy = "template"
    on_failure = str(
        getattr(cfg, "agent_planning_on_step_failure", "replan") or "replan"
    ).strip().lower()
    if on_failure not in FAILURE_POLICIES:
        on_failure = "replan"

    planning = PlanningSettings(
        enabled=True,
        strategy=strategy,
        max_plan_steps=int(getattr(cfg, "agent_planning_max_plan_steps", 8) or 8),
        max_replans=int(getattr(cfg, "agent_planning_max_replans", 1) or 0),
        max_tokens=int(getattr(cfg, "agent_planning_max_tokens", 1500) or 1500),
        timeout_seconds=float(
            getattr(cfg, "agent_planning_proposal_timeout_seconds", 30.0) or 30.0
        ),
    )
    execution = PlanExecutionSettings(
        max_total_tool_calls=int(
            getattr(cfg, "agent_planning_max_total_tool_calls", 16) or 16
        ),
        max_observation_replans=int(
            getattr(cfg, "agent_planning_max_observation_replans", 1) or 0
        ),
        timeout_seconds=float(
            getattr(cfg, "agent_planning_exec_timeout_seconds", 60.0) or 60.0
        ),
        on_step_failure=on_failure,
    )
    return planning, execution


def try_run_with_planning(
    executor: Any,
    *,
    task: str,
    context: Optional[Dict[str, Any]] = None,
    cancelled_check: Optional[CancelledCheck] = None,
    config: Any = None,
) -> Optional[Any]:
    """Run the production planning path or return ``None`` when disabled.

    When enabled, always returns an ``AgentResult`` (success or explicit failure).
    When disabled, returns ``None`` so the caller continues the classic ReAct path.
    """
    cfg = _resolve_config(config)
    if not is_agent_planning_enabled(cfg):
        return None
    return run_with_planning(
        executor,
        task=task,
        context=context,
        cancelled_check=cancelled_check,
        config=cfg,
    )


def run_with_planning(
    executor: Any,
    *,
    task: str,
    context: Optional[Dict[str, Any]] = None,
    cancelled_check: Optional[CancelledCheck] = None,
    config: Any = None,
) -> Any:
    """Plan, execute tools under BoundToolSession, then synthesize the dashboard.

    Returns an ``AgentResult``. Planning/execution failures set ``success=False``
    with an explicit error; they never fail-open as a successful analysis.
    """
    # Local import keeps the optional product path off the module import graph
    # for pure library consumers of ``src.agent.planning``.
    from src.agent.executor import AgentResult

    cfg = _resolve_config(config)
    started = time.perf_counter()
    scope_resolution = resolve_stock_scope(task, context)
    effective_context = dict(scope_resolution.effective_context or {})
    # Bind the resolved product Config so multi-level reflection (Issue #1094)
    # can read enable flags on the real AgentExecutor planning path. Without
    # this, step critique stays library-only even when AGENT_STEP_CRITIQUE_* is on.
    effective_context["config"] = cfg
    available_tools = list(executor.tool_registry.list_names())

    try:
        planning_settings, execution_settings = resolve_planning_settings(cfg)
    except ValueError as exc:
        log_safe_exception(
            logger,
            "Invalid agent planning configuration",
            exc,
            error_code="agent_planning_invalid_config",
            level=logging.ERROR,
        )
        return AgentResult(
            success=False,
            error=f"Planning configuration invalid: {exc}",
            planning_metadata={
                "enabled": True,
                "applied": False,
                "fallback_reason": "invalid_config",
                "error_code": "invalid_config",
            },
        )

    llm_for_planner = (
        executor.llm_adapter if planning_settings.strategy == "llm" else None
    )
    engine = PlanningEngine(planning_settings, llm_adapter=llm_for_planner)
    proposal = engine.plan(
        task,
        available_tools=available_tools,
        context=effective_context,
        cancelled_check=cancelled_check,
    )
    proposal_meta = proposal.to_metadata()
    if not proposal.applied or proposal.plan is None:
        reason = proposal.fallback_reason or proposal.error_code or "planning_failed"
        return AgentResult(
            success=False,
            error=f"Planning failed: {reason}",
            cancelled=reason == "cancelled",
            total_tokens=int(proposal.planning_tokens or 0),
            planning_metadata={
                **proposal_meta,
                "product_path": "agent_executor_run",
                "phase": "proposal",
            },
        )

    session: Optional[BoundToolSession] = None
    try:
        session = _open_plan_tool_session(
            executor,
            available_tools=available_tools,
            stock_scope=scope_resolution.stock_scope,
            cancelled_check=cancelled_check,
            deadline_seconds=execution_settings.timeout_seconds,
        )

        def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            assert session is not None
            return session.execute(name, arguments)

        exec_result = execute_plan_loop(
            plan=proposal.plan,
            tool_invoker=invoker,
            available_tools=available_tools,
            task=task,
            context=effective_context,
            settings=execution_settings,
            planning_settings=planning_settings,
            planner=engine,
            cancelled_check=cancelled_check,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - never fake success
        log_safe_exception(
            logger,
            "Production planning path failed unexpectedly",
            exc,
            error_code="agent_planning_product_path_failed",
            level=logging.ERROR,
        )
        return AgentResult(
            success=False,
            error="Plan execution failed unexpectedly",
            planning_metadata={
                **proposal_meta,
                "product_path": "agent_executor_run",
                "phase": "execution",
                "success": False,
                "status": "failed",
                "reason": "loop_error",
                "error_code": "loop_error",
            },
        )
    finally:
        if session is not None:
            try:
                session.close()
            except Exception as close_exc:  # broad-exception: fallback_recorded - session close best-effort
                log_safe_exception(
                    logger,
                    "Plan tool session close failed",
                    close_exc,
                    error_code="agent_planning_session_close_failed",
                    level=logging.WARNING,
                )

    exec_meta = exec_result.to_metadata()
    planning_metadata: Dict[str, Any] = {
        **proposal_meta,
        **exec_meta,
        "product_path": "agent_executor_run",
        "phase": "execution",
        "proposal_applied": True,
    }
    # Harvest multi-level reflection artifacts written onto context during replan.
    _merge_reflection_context(planning_metadata, effective_context)
    plan_tool_log = _tool_calls_log_from_execution(exec_result)

    if not exec_result.success:
        reason = exec_result.reason or exec_result.status or "plan_execution_failed"
        _maybe_attach_end_of_run_reflection(
            planning_metadata,
            executor=executor,
            config=cfg,
            context=effective_context,
            success=False,
            tool_calls_log=plan_tool_log,
        )
        result = AgentResult(
            success=False,
            error=f"Plan execution terminated: {reason}",
            tool_calls_log=plan_tool_log,
            total_steps=len(exec_result.step_observations),
            total_tokens=int(exec_result.planning_tokens or 0)
            + int(proposal.planning_tokens or 0),
            cancelled=bool(exec_result.cancelled),
            timed_out=bool(exec_result.timed_out),
            planning_metadata=planning_metadata,
        )
        _apply_live_mode_budget_snapshot(
            result,
            executor=executor,
            context=effective_context,
            planning_metadata=planning_metadata,
        )
        return result

    # Successful plan: inject observation evidence and run LLM synthesis.
    evidence = compact_observation_summary(exec_result.step_observations)
    synthesis_context = dict(effective_context)
    # Keep full trace_events on AgentResult.planning_metadata; omit the dense list
    # from synthesis context (not prompt keys today, avoids accidental growth).
    synthesis_context["planning_execution_metadata"] = {
        key: value
        for key, value in planning_metadata.items()
        if key != "trace_events"
    }
    if evidence:
        synthesis_context["plan_execution_evidence"] = evidence

    system_prompt, user_message, tool_decls = executor.build_run_messages(
        task,
        synthesis_context,
    )
    if evidence:
        user_message = (
            f"{user_message}\n\n"
            "[Plan execution evidence — already gathered under planning budgets; "
            "prefer these results and call tools only for remaining gaps]\n"
            f"{evidence}"
        )
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    result = executor._run_loop(
        messages,
        tool_decls,
        parse_dashboard=True,
        stock_scope=scope_resolution.stock_scope,
        cancelled_check=cancelled_check,
    )
    # Prepend plan-loop tool audit trail so diagnostics see real tool work.
    result.tool_calls_log = list(plan_tool_log) + list(result.tool_calls_log or [])
    result.total_tokens = int(result.total_tokens or 0) + int(
        exec_result.planning_tokens or 0
    ) + int(proposal.planning_tokens or 0)
    result.planning_metadata = {
        **planning_metadata,
        "synthesis_success": bool(result.success),
        "product_duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
    }
    _maybe_attach_end_of_run_reflection(
        result.planning_metadata,
        executor=executor,
        config=cfg,
        context=effective_context,
        success=bool(result.success),
        tool_calls_log=result.tool_calls_log,
    )
    _apply_live_mode_budget_snapshot(
        result,
        executor=executor,
        context=effective_context,
        planning_metadata=result.planning_metadata,
    )
    return result


def _merge_reflection_context(
    planning_metadata: Dict[str, Any],
    context: Optional[Dict[str, Any]],
) -> None:
    """Copy step-critique / replan taxonomy fields from loop context into metadata."""
    if not isinstance(context, dict):
        return
    kinds = context.get("replan_reason_kinds")
    if isinstance(kinds, list) and kinds:
        planning_metadata["replan_reason_kinds"] = [
            str(item) for item in kinds if str(item).strip()
        ][:8]
    step_payload = context.get("step_critique_result")
    if isinstance(step_payload, dict):
        planning_metadata["step_critique_result"] = step_payload


def _maybe_attach_end_of_run_reflection(
    planning_metadata: Dict[str, Any],
    *,
    executor: Any,
    config: Any,
    context: Optional[Dict[str, Any]],
    success: bool,
    tool_calls_log: Optional[Sequence[Dict[str, Any]]] = None,
) -> None:
    """Attach one bounded trajectory reflection to planning metadata.

    Default-off via ``agent_reflection_enabled``. Fail-soft: a reflection
    provider/validation failure is explicit in metadata but never changes the
    already-computed Agent result. When the executor or planning context holds
    a ``mode_budget_account``, that same object is copied onto the reflection
    ctx so the optional LLM call charges the run account. Episode persistence
    remains owned by #1210's single end-of-run finalizer so this hook cannot
    create duplicate episodes.
    """
    if getattr(config, "agent_reflection_enabled", False) is not True:
        return
    try:
        from src.agent.evolution.budget import budget_from_config
        from src.agent.evolution.multilevel import run_trajectory_layer
        from src.agent.evolution.reflection import REFLECTION_META_KEY
        from src.agent.evolution.step_critique import STEP_CRITIQUE_META_KEY
    except Exception as exc:  # broad-exception: fallback_recorded - reflection is optional
        log_safe_exception(
            logger,
            "End-of-run reflection imports failed",
            exc,
            error_code="agent_reflection_import_failed",
            level=logging.INFO,
        )
        planning_metadata["reflection_result"] = _reflection_error_payload(
            "Trajectory reflection could not be loaded."
        )
        return

    class _Ctx:
        meta: Dict[str, Any]
        opinions: List[Any]
        risk_flags: List[Any]
        stock_code: Optional[str]

    ctx = _Ctx()
    ctx.opinions = []
    ctx.risk_flags = []
    ctx.stock_code = None
    run_id = None
    episode_id = None
    if isinstance(context, dict):
        run_id = context.get("run_id") or context.get("analysis_history_id")
        episode_id = context.get("episode_id")
        ctx.stock_code = context.get("stock_code")
        # Seed immediate-layer payload if the plan loop already wrote it.
        step_payload = context.get(STEP_CRITIQUE_META_KEY) or planning_metadata.get(
            STEP_CRITIQUE_META_KEY
        )
        ctx.meta = {
            "run_id": run_id,
            "episode_id": episode_id,
            "run_success": success,
            "planning_outcome": {
                "status": planning_metadata.get("status"),
                "reason": planning_metadata.get("reason"),
                "observation_replans": planning_metadata.get(
                    "observation_replans", 0
                ),
            },
            "degraded_stages": list(context.get("degraded_stages") or []),
        }
        if isinstance(step_payload, dict):
            ctx.meta[STEP_CRITIQUE_META_KEY] = step_payload
            if step_payload.get("replan_reasons"):
                ctx.meta["replan_reason_kinds"] = list(step_payload["replan_reasons"])
    else:
        ctx.meta = {
            "run_id": run_id,
            "episode_id": episode_id,
            "run_success": success,
        }

    ctx.meta["trajectory_summary"] = _reflection_trajectory_summary(
        tool_calls_log
    )
    _attach_mode_budget_account(ctx, executor=executor, context=context)

    try:
        multi = run_trajectory_layer(
            ctx,
            config=config,
            seed_from_immediate=True,
            budget=budget_from_config(
                config,
                attr="agent_reflection_llm_budget",
                default=1,
            ),
            llm_complete=_reflection_llm_complete(executor, config),
        )
    except Exception as exc:  # broad-exception: fallback_recorded - optional end reflection
        log_safe_exception(
            logger,
            "End-of-run trajectory reflection failed",
            exc,
            error_code="agent_reflection_trajectory_failed",
            level=logging.INFO,
        )
        planning_metadata["reflection_result"] = _reflection_error_payload(
            "Trajectory reflection was unavailable."
        )
        return

    if multi.trajectory is not None:
        planning_metadata[REFLECTION_META_KEY] = multi.trajectory
    if multi.episode_lessons:
        planning_metadata["episode_lessons"] = list(multi.episode_lessons)
    if multi.replan_reason_kinds:
        planning_metadata.setdefault(
            "replan_reason_kinds", list(multi.replan_reason_kinds)
        )


def _resolve_mode_budget_account(
    executor: Any,
    context: Optional[Dict[str, Any]],
) -> Any:
    """Return the live run account from executor or planning context."""
    if isinstance(context, dict):
        account = context.get("mode_budget_account")
        if account is None:
            nested = context.get("meta")
            if isinstance(nested, dict):
                account = nested.get("mode_budget_account")
        if account is not None:
            return account
    if executor is None:
        return None
    account = getattr(executor, "mode_budget_account", None)
    if account is not None:
        return account
    return getattr(executor, "_mode_budget_account", None)


def _apply_live_mode_budget_snapshot(
    result: Any,
    *,
    executor: Any,
    context: Optional[Dict[str, Any]] = None,
    planning_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Copy the post-reflection account snapshot onto the returned AgentResult.

    ``_run_loop`` freezes ``budget_snapshot`` before optional reflection
    charges the same account. Diagnostics must show the final used turns.
    """
    account = _resolve_mode_budget_account(executor, context)
    snapshot_fn = getattr(account, "snapshot", None)
    if not callable(snapshot_fn):
        return
    try:
        payload = snapshot_fn()
    except Exception as exc:  # broad-exception: fallback_recorded - snapshot is diagnostic
        log_safe_exception(
            logger,
            "Could not snapshot mode budget after reflection",
            exc,
            error_code="agent_reflection_mode_budget_snapshot_failed",
            level=logging.INFO,
        )
        return
    if not isinstance(payload, dict):
        return
    if result is not None:
        result.budget_snapshot = payload
    if isinstance(planning_metadata, dict):
        planning_metadata["mode_budget"] = payload


def _attach_mode_budget_account(
    ctx: Any,
    *,
    executor: Any,
    context: Optional[Dict[str, Any]],
) -> None:
    """Copy the live run account onto the reflection ctx when one exists."""
    account = _resolve_mode_budget_account(executor, context)
    if account is None:
        return
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return
    meta["mode_budget_account"] = account
    snapshot = getattr(account, "snapshot", None)
    if callable(snapshot):
        try:
            meta["mode_budget"] = snapshot()
        except Exception as exc:  # broad-exception: fallback_recorded - snapshot is diagnostic
            log_safe_exception(
                logger,
                "End-of-run reflection could not snapshot mode budget",
                exc,
                error_code="agent_reflection_mode_budget_snapshot_failed",
                level=logging.INFO,
            )


def _reflection_error_payload(reason: str) -> Dict[str, Any]:
    """Expose optional reflection failure without changing the run outcome."""
    return {
        "lessons": [],
        "revised": False,
        "terminate_reason": "error",
        "status": "error",
        "episode_id": None,
        "prediction_id": None,
        "run_id": None,
        "strategy_note": None,
        "llm_budget_total": 0,
        "llm_budget_consumed": 0,
        "llm_budget_remaining": 0,
        "validation_status": "error",
        "skip_reason": reason,
    }


def _reflection_trajectory_summary(
    tool_calls_log: Optional[Sequence[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Build bounded, redacted evidence for the trajectory critic."""
    summary: List[Dict[str, Any]] = []
    for row in list(tool_calls_log or [])[:64]:
        if not isinstance(row, dict):
            continue
        tool = row.get("tool") or row.get("tool_name")
        if not isinstance(tool, str) or not tool.strip():
            continue
        raw_success = row.get("ok", row.get("success"))
        if type(raw_success) is not bool:
            continue
        summary.append(
            {
                "tool": sanitize_diagnostic_text(tool, max_length=128),
                "success": raw_success,
                "error_code": sanitize_diagnostic_text(
                    row.get("error_code"), max_length=64
                )
                or None,
                "summary": sanitize_diagnostic_text(
                    row.get("summary"), max_length=300
                ),
            }
        )
    return summary


def _reflection_llm_complete(
    executor: Any,
    config: Any,
) -> ReflectionComplete:
    """Adapt the real executor provider to the strict reflection callback."""

    def _complete(system_prompt: str, user_prompt: str) -> str:
        adapter = getattr(executor, "llm_adapter", None)
        call = getattr(adapter, "call_completion", None)
        if not callable(call):
            raise RuntimeError("reflection provider is unavailable")
        timeout = float(
            getattr(config, "agent_planning_proposal_timeout_seconds", 30.0)
            or 30.0
        )
        timeout = max(0.1, min(timeout, 30.0))
        response = call(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=None,
            temperature=0.0,
            max_tokens=REFLECTION_MAX_TOKENS,
            timeout=timeout,
        )
        if str(getattr(response, "provider", "") or "").lower() == "error":
            raise RuntimeError("reflection provider returned an error")
        content = getattr(response, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("reflection provider returned no text")
        return content

    return _complete


def _open_plan_tool_session(
    executor: Any,
    *,
    available_tools: Sequence[str],
    stock_scope: Any,
    cancelled_check: Optional[CancelledCheck],
    deadline_seconds: float,
) -> BoundToolSession:
    """Open a BoundToolSession matching the native runner's security contract."""
    deadline_monotonic = time.monotonic() + float(deadline_seconds)
    return BoundToolSession(
        executor.tool_registry,
        execution_id=str(uuid.uuid4()),
        allowed_tools=list(available_tools),
        derive_granted_permissions=True,
        stock_scope=stock_scope,
        call_timeout_seconds=(
            float(executor.timeout_seconds)
            if getattr(executor, "timeout_seconds", None) is not None
            and float(executor.timeout_seconds) > 0
            else None
        ),
        deadline_monotonic=deadline_monotonic,
        cancelled_check=cancelled_check,
        backend="plan-loop",
        principal="plan-execution-runtime",
        stage="plan_execution",
        audit_context={"source": "agent_planning_product"},
        security_audit=get_security_audit_service(),
    )


def _tool_calls_log_from_execution(exec_result: Any) -> List[Dict[str, Any]]:
    """Flatten step observations into the AgentResult tool_calls_log shape."""
    rows: List[Dict[str, Any]] = []
    for obs in getattr(exec_result, "step_observations", None) or []:
        for call in getattr(obs, "tool_calls", None) or ():
            rows.append(
                {
                    "tool": getattr(call, "tool_name", "unknown"),
                    "ok": bool(getattr(call, "ok", False)),
                    "error_code": getattr(call, "error_code", None),
                    "summary": getattr(call, "summary", "") or "",
                    "duration_ms": getattr(call, "duration_ms", None),
                    "step_id": getattr(obs, "step_id", None),
                    "source": "plan_loop",
                }
            )
    return rows


# Re-export absolute maxima for config loading without circular imports.
PLANNING_CONFIG_BOUNDS = {
    "max_plan_steps": (1, MAX_PLAN_STEPS),
    "max_replans": (0, MAX_REPLANS),
    "max_tokens": (1, MAX_PLANNER_TOKENS),
    "proposal_timeout_seconds": (0.1, MAX_PLANNER_TIMEOUT_SECONDS),
    "max_total_tool_calls": (1, MAX_TOTAL_TOOL_CALLS),
    "max_observation_replans": (0, MAX_OBSERVATION_REPLANS),
    "exec_timeout_seconds": (0.1, MAX_EXECUTION_TIMEOUT_SECONDS),
}
