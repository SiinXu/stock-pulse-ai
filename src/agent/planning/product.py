# -*- coding: utf-8 -*-
"""Production wiring: plan → act → observe → replan on RUN, Chat, and Research.

Default-off. When ``Config.agent_planning_enabled`` is true, ``AgentExecutor.run``
calls ``try_run_with_planning`` (dashboard synthesis), Chat callers use
``try_gather_with_planning`` (evidence only, ``parse_dashboard=False``), and
Deep Research sub-question gather uses ``try_gather_with_planning`` with
``product_path=agent_research``. Tools dispatch through ``BoundToolSession``.
Failures terminate with explicit reasons; nothing here claims success after a
failed plan step or exhausted budget.

Config is constructor/parameter injected (or resolved via the composition root).
This module does not call bare ``get_config()``.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field, replace
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
from src.agent.evolution.multilevel import (
    apply_live_mode_budget_snapshot as _apply_live_mode_budget_snapshot_shared,
    reflection_error_payload as _reflection_error_payload,
)
from src.agent.planning.engine import PlanningEngine
from src.agent.planning.loop import execute_plan_loop
from src.agent.planning.observations import compact_observation_summary
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.stock_scope import resolve_stock_scope
from src.services.security_audit_service import get_security_audit_service
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

CancelledCheck = Callable[[], bool]
ReflectionComplete = Callable[[str, str], str]

RUN_PRODUCT_PATH = "agent_executor_run"
CHAT_PRODUCT_PATH = "agent_executor_chat"
ORCH_CHAT_PRODUCT_PATH = "agent_orchestrator_chat"
RESEARCH_PRODUCT_PATH = "agent_research"
PLAN_EVIDENCE_HEADER = (
    "[Plan execution evidence — already gathered under planning budgets; "
    "prefer these results and call tools only for remaining gaps]"
)


@dataclass
class PlanningGatherResult:
    """Plan→act→observe gather without dashboard/chat synthesis."""

    success: bool
    product_path: str
    evidence: str = ""
    planning_metadata: Dict[str, Any] = field(default_factory=dict)
    plan_tool_log: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    cancelled: bool = False
    timed_out: bool = False
    total_tokens: int = 0
    total_steps: int = 0
    stock_scope: Any = None
    synthesis_context: Dict[str, Any] = field(default_factory=dict)

    def to_agent_result(self) -> Any:
        from src.agent.executor import AgentResult

        return AgentResult(
            success=self.success,
            error=None if self.success else self.error,
            tool_calls_log=list(self.plan_tool_log),
            total_steps=self.total_steps,
            total_tokens=self.total_tokens,
            cancelled=self.cancelled,
            timed_out=self.timed_out,
            planning_metadata=dict(self.planning_metadata),
        )


def planning_evidence_block(evidence: str) -> str:
    """Prompt block injected into Chat/RUN synthesis after a successful gather."""
    return f"{PLAN_EVIDENCE_HEADER}\n{evidence}"


def _resolve_config(config: Any = None) -> Any:
    """Prefer injected Config; fall back to composition-root access."""
    if config is not None:
        return config
    from src.application_services import get_application_services

    return get_application_services().config


def is_agent_planning_enabled(config: Any = None) -> bool:
    """Return whether the production planning path is opted in."""
    cfg = _resolve_config(config)
    return getattr(cfg, "agent_planning_enabled", False) is True


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


def try_gather_with_planning(
    owner: Any,
    *,
    task: str,
    context: Optional[Dict[str, Any]] = None,
    cancelled_check: Optional[CancelledCheck] = None,
    config: Any = None,
    product_path: str = CHAT_PRODUCT_PATH,
    available_tools: Optional[Sequence[str]] = None,
    max_total_tool_calls: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> Optional[PlanningGatherResult]:
    """Gather plan evidence without dashboard synthesis, or ``None`` when disabled.

    Chat callers must not pass an orchestrator into ``try_run_with_planning``
    (that helper synthesizes via ``build_run_messages`` / ``_run_loop``).
    ``available_tools`` defaults to the owner's full registry so Chat/RUN stay
    identical; Research must pass the filtered research tool names.
    """
    cfg = _resolve_config(config)
    if not is_agent_planning_enabled(cfg):
        return None
    return gather_with_planning(
        owner,
        task=task,
        context=context,
        cancelled_check=cancelled_check,
        config=cfg,
        product_path=product_path,
        available_tools=available_tools,
        max_total_tool_calls=max_total_tool_calls,
        timeout_seconds=timeout_seconds,
    )


def gather_with_planning(
    owner: Any,
    *,
    task: str,
    context: Optional[Dict[str, Any]] = None,
    cancelled_check: Optional[CancelledCheck] = None,
    config: Any = None,
    product_path: str = RUN_PRODUCT_PATH,
    available_tools: Optional[Sequence[str]] = None,
    max_total_tool_calls: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
) -> PlanningGatherResult:
    """Plan and execute tools under BoundToolSession. No LLM dashboard synthesis."""
    cfg = _resolve_config(config)
    scope_resolution = resolve_stock_scope(task, context)
    effective_context = dict(scope_resolution.effective_context or {})
    effective_context["config"] = cfg
    if available_tools is None:
        resolved_tools = list(owner.tool_registry.list_names())
    else:
        resolved_tools = list(available_tools)

    try:
        planning_settings, execution_settings = resolve_planning_settings(cfg)
        execution_settings = _tighten_execution_settings(
            execution_settings,
            max_total_tool_calls=max_total_tool_calls,
            timeout_seconds=timeout_seconds,
        )
    except _PlanningTimeoutTooSmall:
        return PlanningGatherResult(
            success=False,
            product_path=product_path,
            error="Planning execution timeout exhausted",
            timed_out=True,
            planning_metadata={
                "enabled": True,
                "applied": False,
                "fallback_reason": "execution_timeout",
                "error_code": "execution_timeout",
                "product_path": product_path,
            },
            stock_scope=scope_resolution.stock_scope,
            synthesis_context=effective_context,
        )
    except ValueError as exc:
        log_safe_exception(
            logger,
            "Invalid agent planning configuration",
            exc,
            error_code="agent_planning_invalid_config",
            level=logging.ERROR,
        )
        return PlanningGatherResult(
            success=False,
            product_path=product_path,
            error=f"Planning configuration invalid: {exc}",
            planning_metadata={
                "enabled": True,
                "applied": False,
                "fallback_reason": "invalid_config",
                "error_code": "invalid_config",
                "product_path": product_path,
            },
            stock_scope=scope_resolution.stock_scope,
            synthesis_context=effective_context,
        )

    llm_for_planner = (
        owner.llm_adapter if planning_settings.strategy == "llm" else None
    )
    engine = PlanningEngine(planning_settings, llm_adapter=llm_for_planner)
    proposal = engine.plan(
        task,
        available_tools=resolved_tools,
        context=effective_context,
        cancelled_check=cancelled_check,
    )
    proposal_meta = proposal.to_metadata()
    if not proposal.applied or proposal.plan is None:
        reason = proposal.fallback_reason or proposal.error_code or "planning_failed"
        return PlanningGatherResult(
            success=False,
            product_path=product_path,
            error=f"Planning failed: {reason}",
            cancelled=reason == "cancelled",
            total_tokens=int(proposal.planning_tokens or 0),
            planning_metadata={
                **proposal_meta,
                "product_path": product_path,
                "phase": "proposal",
            },
            stock_scope=scope_resolution.stock_scope,
            synthesis_context=effective_context,
        )

    session: Optional[BoundToolSession] = None
    try:
        session = _open_plan_tool_session(
            owner,
            available_tools=resolved_tools,
            stock_scope=scope_resolution.stock_scope,
            cancelled_check=cancelled_check,
            deadline_seconds=execution_settings.timeout_seconds,
            call_timeout_seconds=timeout_seconds,
        )

        def invoker(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            assert session is not None
            return session.execute(name, arguments)

        exec_result = execute_plan_loop(
            plan=proposal.plan,
            tool_invoker=invoker,
            available_tools=resolved_tools,
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
        return PlanningGatherResult(
            success=False,
            product_path=product_path,
            error="Plan execution failed unexpectedly",
            planning_metadata={
                **proposal_meta,
                "product_path": product_path,
                "phase": "execution",
                "success": False,
                "status": "failed",
                "reason": "loop_error",
                "error_code": "loop_error",
            },
            stock_scope=scope_resolution.stock_scope,
            synthesis_context=effective_context,
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
        "product_path": product_path,
        "phase": "execution",
        "proposal_applied": True,
    }
    _merge_reflection_context(planning_metadata, effective_context)
    plan_tool_log = _tool_calls_log_from_execution(exec_result)
    total_tokens = int(exec_result.planning_tokens or 0) + int(
        proposal.planning_tokens or 0
    )
    synthesis_context = dict(effective_context)
    synthesis_context["planning_execution_metadata"] = {
        key: value
        for key, value in planning_metadata.items()
        if key != "trace_events"
    }
    evidence = compact_observation_summary(exec_result.step_observations)
    if evidence:
        synthesis_context["plan_execution_evidence"] = evidence

    if not exec_result.success:
        reason = exec_result.reason or exec_result.status or "plan_execution_failed"
        return PlanningGatherResult(
            success=False,
            product_path=product_path,
            error=f"Plan execution terminated: {reason}",
            planning_metadata=planning_metadata,
            plan_tool_log=plan_tool_log,
            cancelled=bool(exec_result.cancelled),
            timed_out=bool(exec_result.timed_out),
            total_tokens=total_tokens,
            total_steps=len(exec_result.step_observations),
            stock_scope=scope_resolution.stock_scope,
            synthesis_context=synthesis_context,
        )

    return PlanningGatherResult(
        success=True,
        product_path=product_path,
        evidence=evidence,
        planning_metadata=planning_metadata,
        plan_tool_log=plan_tool_log,
        total_tokens=total_tokens,
        total_steps=len(exec_result.step_observations),
        stock_scope=scope_resolution.stock_scope,
        synthesis_context=synthesis_context,
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
    cfg = _resolve_config(config)
    started = time.perf_counter()
    gathered = gather_with_planning(
        executor,
        task=task,
        context=context,
        cancelled_check=cancelled_check,
        config=cfg,
        product_path=RUN_PRODUCT_PATH,
    )
    if not gathered.success:
        _maybe_attach_end_of_run_reflection(
            gathered.planning_metadata,
            executor=executor,
            config=cfg,
            context=gathered.synthesis_context,
            success=False,
            tool_calls_log=gathered.plan_tool_log,
        )
        result = gathered.to_agent_result()
        _apply_live_mode_budget_snapshot(
            result,
            executor=executor,
            context=gathered.synthesis_context,
            planning_metadata=gathered.planning_metadata,
        )
        return result

    system_prompt, user_message, tool_decls = executor.build_run_messages(
        task,
        gathered.synthesis_context,
    )
    if gathered.evidence:
        user_message = (
            f"{user_message}\n\n{planning_evidence_block(gathered.evidence)}"
        )
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    result = executor._run_loop(
        messages,
        tool_decls,
        parse_dashboard=True,
        stock_scope=gathered.stock_scope,
        cancelled_check=cancelled_check,
    )
    result.tool_calls_log = list(gathered.plan_tool_log) + list(
        result.tool_calls_log or []
    )
    result.total_tokens = int(result.total_tokens or 0) + int(gathered.total_tokens or 0)
    result.planning_metadata = {
        **gathered.planning_metadata,
        "synthesis_success": bool(result.success),
        "product_duration_ms": max(0, int((time.perf_counter() - started) * 1000)),
    }
    _maybe_attach_end_of_run_reflection(
        result.planning_metadata,
        executor=executor,
        config=cfg,
        context=gathered.synthesis_context,
        success=bool(result.success),
        tool_calls_log=result.tool_calls_log,
    )
    _apply_live_mode_budget_snapshot(
        result,
        executor=executor,
        context=gathered.synthesis_context,
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
    """Planning-path entry into the shared end-of-run reflection attach point.

    Behaviour is owned by ``src.agent.evolution.multilevel``; the same helper
    now serves the classic Native run and the Native Multi dashboard run
    (Issue #1089), so the planning path cannot drift into a parallel copy.
    """
    if getattr(config, "agent_reflection_enabled", False) is not True:
        return
    try:
        from src.agent.evolution.multilevel import attach_end_of_run_reflection
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

    attach_end_of_run_reflection(
        planning_metadata,
        executor=executor,
        config=config,
        context=context,
        success=success,
        tool_calls_log=tool_calls_log,
    )


def _apply_live_mode_budget_snapshot(
    result: Any,
    *,
    executor: Any,
    context: Optional[Dict[str, Any]] = None,
    planning_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Copy the post-reflection account snapshot onto the returned AgentResult."""
    _apply_live_mode_budget_snapshot_shared(
        result,
        executor=executor,
        context=context,
        metadata=planning_metadata,
    )


def _owner_call_timeout_seconds(owner: Any) -> Optional[float]:
    timeout = getattr(owner, "timeout_seconds", None)
    if timeout is None and hasattr(owner, "_get_timeout_seconds"):
        try:
            timeout = owner._get_timeout_seconds()
        except Exception as exc:  # broad-exception: fallback_recorded - timeout is optional
            log_safe_exception(
                logger,
                "Owner timeout lookup failed",
                exc,
                error_code="agent_planning_owner_timeout_unavailable",
                level=logging.INFO,
            )
            timeout = None
    if timeout is None:
        return None
    try:
        value = float(timeout)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class _PlanningTimeoutTooSmall(ValueError):
    """Remaining wall-clock is below PlanExecutionSettings' 0.1s floor."""


def _tighten_execution_settings(
    execution_settings: PlanExecutionSettings,
    *,
    max_total_tool_calls: Optional[int],
    timeout_seconds: Optional[float],
) -> PlanExecutionSettings:
    """Tighten planning execution caps without expanding Chat/RUN defaults."""
    updates: Dict[str, Any] = {}
    if max_total_tool_calls is not None:
        try:
            remaining = int(max_total_tool_calls)
        except (TypeError, ValueError):
            remaining = execution_settings.max_total_tool_calls
        if remaining >= 1:
            updates["max_total_tool_calls"] = min(
                execution_settings.max_total_tool_calls, remaining
            )
    if timeout_seconds is not None:
        try:
            remaining_timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            remaining_timeout = execution_settings.timeout_seconds
        if remaining_timeout < 0.1:
            raise _PlanningTimeoutTooSmall("timeout_seconds below planning floor")
        updates["timeout_seconds"] = min(
            execution_settings.timeout_seconds, remaining_timeout
        )
    if not updates:
        return execution_settings
    return replace(execution_settings, **updates)


def _open_plan_tool_session(
    executor: Any,
    *,
    available_tools: Sequence[str],
    stock_scope: Any,
    cancelled_check: Optional[CancelledCheck],
    deadline_seconds: float,
    call_timeout_seconds: Optional[float] = None,
) -> BoundToolSession:
    """Open a BoundToolSession matching the native runner's security contract."""
    deadline_monotonic = time.monotonic() + float(deadline_seconds)
    resolved_call_timeout = (
        float(call_timeout_seconds)
        if call_timeout_seconds is not None
        else _owner_call_timeout_seconds(executor)
    )
    return BoundToolSession(
        executor.tool_registry,
        execution_id=str(uuid.uuid4()),
        allowed_tools=list(available_tools),
        derive_granted_permissions=True,
        stock_scope=stock_scope,
        call_timeout_seconds=resolved_call_timeout,
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
