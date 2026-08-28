# -*- coding: utf-8 -*-
"""Facade for the three reflection layers (Issue #1094).

1. Immediate step critique (in-loop)
2. Trajectory / end-of-run reflection
3. Cross-run meta-review (offline, sample-thresholded)

Each layer has explicit trigger conditions and LLM budgets. Outputs are typed
lessons that project into episode storage. Soul / ToolSurface are never mutated.

``attach_end_of_run_reflection`` is the single production attach point shared by
the opt-in planning product path, the classic Native ``AgentExecutor`` run and
the Native Multi ``AgentOrchestrator`` dashboard run (Issue #1089). It writes
only run-local metadata; persistence for evolution stays with Issue #1090.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.agent.evolution.budget import LlmCallBudget, budget_from_config
from src.agent.evolution.episode_lessons import (
    EpisodeLessonSink,
    merge_episode_lessons,
    record_reflection_lessons,
    reflection_result_to_episode_lessons,
)
from src.agent.evolution.meta_review import MetaReviewReport, run_meta_review
from src.agent.evolution.reflection import REFLECTION_META_KEY, run_reflection_loop
from src.agent.evolution.step_critique import (
    STEP_CRITIQUE_META_KEY,
    critique_step_observations,
)
from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)

LlmCompleteFn = Callable[[str, str], str]
EventSink = Callable[[str, Dict[str, Any]], None]

REFLECTION_MAX_TOKENS = 800
MAX_TRAJECTORY_ROWS = 64
MAX_CRITIC_TRACE_ROWS = 8
MAX_OPINION_ROWS = 12
MAX_RISK_FLAG_ROWS = 10
MAX_DEGRADED_STAGE_ROWS = 16
MAX_REPLAN_REASON_ROWS = 8
MAX_REFLECTION_TIMEOUT_SECONDS = 30.0
# Only bounded start/end attrs reach observability; lesson text never does.
_REFLECT_EVENT_ATTRS: Dict[str, Sequence[str]] = {
    "reflect_start": ("llm_budget_total",),
    "reflect_end": (
        "terminate_reason",
        "status",
        "lesson_count",
        "llm_budget_consumed",
        "llm_budget_remaining",
    ),
}


@dataclass
class MultiLevelReflectionResult:
    """Combined view of the three reflection layers for one orchestration pass."""

    immediate: Optional[Dict[str, Any]] = None
    trajectory: Optional[Dict[str, Any]] = None
    meta: Optional[Dict[str, Any]] = None
    episode_lessons: List[Dict[str, Any]] = field(default_factory=list)
    replan_reason_kinds: List[str] = field(default_factory=list)

    def to_public_dict(self) -> Dict[str, Any]:
        return {
            "immediate": self.immediate,
            "trajectory": self.trajectory,
            "meta": self.meta,
            "episode_lessons": list(self.episode_lessons),
            "replan_reason_kinds": list(self.replan_reason_kinds),
            "mutates_soul": False,
            "mutates_tool_surface": False,
        }


def run_immediate_layer(
    observations: Sequence[Any],
    *,
    config: Any = None,
    ctx: Any = None,
    budget: Optional[LlmCallBudget] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    sink: Optional[EpisodeLessonSink] = None,
    force: bool = False,
) -> MultiLevelReflectionResult:
    """Layer 1: step critique after tool failure / contradiction.

    Optional LLM enrichment charges ``ctx.meta["mode_budget_account"]`` when
    present. Production planning does not inject ``llm_complete``.
    """
    result = critique_step_observations(
        observations,
        config=config,
        ctx=ctx,
        budget=budget,
        llm_complete=llm_complete,
        force=force,
    )
    lessons = record_reflection_lessons(
        sink,
        result,
        layer="immediate",
        run_id=result.run_id,
        episode_id=result.episode_id,
        meta={"layer": "immediate"},
    )
    meta = getattr(ctx, "meta", None) if ctx is not None else None
    replan_reasons: List[str] = []
    if isinstance(meta, dict):
        replan_reasons = list(meta.get("replan_reason_kinds") or [])
        payload = meta.get(STEP_CRITIQUE_META_KEY)
    else:
        payload = result.to_public_dict()
        payload["layer"] = "immediate"
    return MultiLevelReflectionResult(
        immediate=payload if isinstance(payload, dict) else result.to_public_dict(),
        episode_lessons=lessons,
        replan_reason_kinds=replan_reasons,
    )


def run_trajectory_layer(
    ctx: Any,
    *,
    config: Any = None,
    budget: Optional[LlmCallBudget] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    sink: Optional[EpisodeLessonSink] = None,
    seed_from_immediate: bool = True,
    event_sink: Optional[EventSink] = None,
) -> MultiLevelReflectionResult:
    """Layer 2: end-of-run reflection producing full ReflectionResult.

    LLM calls go through ``llm_complete`` (not ``run_agent_loop``). When
    ``ctx.meta["mode_budget_account"]`` is present they charge that shared
    run account once; a run-account skip uses ``budget_skipped``. ``event_sink``
    receives the bounded ``reflect_*`` trace names for observability only.
    """
    seed = None
    meta = getattr(ctx, "meta", None) if ctx is not None else None
    if seed_from_immediate and isinstance(meta, dict):
        step_payload = meta.get(STEP_CRITIQUE_META_KEY)
        if isinstance(step_payload, dict) and step_payload.get("lessons"):
            from src.agent.evolution.lessons import parse_lessons_payload

            seed = parse_lessons_payload(step_payload.get("lessons") or [])

    result = run_reflection_loop(
        ctx,
        config=config,
        llm_complete=llm_complete,
        budget=budget,
        seed_lessons=seed,
        event_sink=event_sink,
    )
    if isinstance(meta, dict) and isinstance(meta.get(REFLECTION_META_KEY), dict):
        meta[REFLECTION_META_KEY]["layer"] = "trajectory"

    record_reflection_lessons(
        sink,
        result,
        layer="trajectory",
        run_id=result.run_id,
        episode_id=result.episode_id,
        meta={"layer": "trajectory"},
    )
    payload = (
        meta.get(REFLECTION_META_KEY)
        if isinstance(meta, dict)
        else result.to_public_dict()
    )
    if isinstance(payload, dict):
        payload = dict(payload)
        payload.setdefault("layer", "trajectory")

    immediate_lessons: List[Dict[str, Any]] = []
    if isinstance(meta, dict):
        step_payload = meta.get(STEP_CRITIQUE_META_KEY)
        if isinstance(step_payload, dict):
            immediate_lessons = list(step_payload.get("lessons") or [])

    return MultiLevelReflectionResult(
        immediate={"lessons": immediate_lessons} if immediate_lessons else None,
        trajectory=payload if isinstance(payload, dict) else result.to_public_dict(),
        episode_lessons=merge_episode_lessons(
            immediate_lessons,
            reflection_result_to_episode_lessons(result),
        ),
        replan_reason_kinds=list((meta or {}).get("replan_reason_kinds") or [])
        if isinstance(meta, dict)
        else [],
    )


def run_cross_run_layer(
    episodes: Sequence[Dict[str, Any]],
    *,
    config: Any = None,
    min_episodes: Optional[int] = None,
    budget: Optional[LlmCallBudget] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    force: bool = False,
) -> MultiLevelReflectionResult:
    """Layer 3: offline meta-review with sample threshold."""
    report: MetaReviewReport = run_meta_review(
        episodes,
        config=config,
        min_episodes=min_episodes,
        budget=budget,
        llm_complete=llm_complete,
        force=force,
    )
    return MultiLevelReflectionResult(meta=report.to_dict())


class _ReflectionRunCtx:
    """Bounded run-local snapshot handed to the trajectory critic.

    Deliberately not the live ``AgentContext``: reflection reads a projected,
    redacted copy so it can never mutate stage data, Soul, or ToolSurface.
    """

    __slots__ = ("meta", "opinions", "risk_flags", "stock_code")

    def __init__(self) -> None:
        self.meta: Dict[str, Any] = {}
        self.opinions: List[Any] = []
        self.risk_flags: List[Any] = []
        self.stock_code: Optional[str] = None


def resolve_mode_budget_account(executor: Any, context: Optional[Dict[str, Any]]) -> Any:
    """Return the live run account from executor or run context."""
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


def attach_mode_budget_account(
    ctx: Any,
    *,
    executor: Any,
    context: Optional[Dict[str, Any]],
) -> None:
    """Copy the live run account onto the reflection ctx when one exists."""
    account = resolve_mode_budget_account(executor, context)
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


def apply_live_mode_budget_snapshot(
    result: Any,
    *,
    executor: Any,
    context: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Copy the post-reflection account snapshot onto the returned result.

    The run loop freezes ``budget_snapshot`` before optional reflection charges
    the same account. Diagnostics must show the final used turns.
    """
    account = resolve_mode_budget_account(executor, context)
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
    if isinstance(metadata, dict):
        metadata["mode_budget"] = payload


def reflection_error_payload(reason: str) -> Dict[str, Any]:
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


def reflection_trajectory_summary(
    tool_calls_log: Optional[Sequence[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Build bounded, redacted evidence for the trajectory critic."""
    summary: List[Dict[str, Any]] = []
    for row in list(tool_calls_log or [])[:MAX_TRAJECTORY_ROWS]:
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


def bounded_critic_trace(trace: Any) -> Optional[Dict[str, Any]]:
    """Project a Critic trace down to bounded, sanitized reflection evidence."""
    if not isinstance(trace, dict):
        return None
    bounded: Dict[str, Any] = {
        "verdict": sanitize_diagnostic_text(trace.get("verdict"), max_length=32) or None,
        "validation_status": sanitize_diagnostic_text(
            trace.get("validation_status"), max_length=32
        )
        or None,
    }
    for key in ("reasons", "missing_evidence"):
        rows = trace.get(key)
        if not isinstance(rows, list):
            continue
        items = [
            sanitize_diagnostic_text(row, max_length=200)
            for row in rows[:MAX_CRITIC_TRACE_ROWS]
        ]
        items = [item for item in items if item]
        if items:
            bounded[key] = items
    return bounded


def reflection_llm_complete(executor: Any, config: Any) -> LlmCompleteFn:
    """Adapt the real executor provider to the strict reflection callback.

    Tool-free, JSON-only, single completion. It never re-enters the agent tool
    loop, so run-account turns are charged exactly once.
    """

    def _complete(system_prompt: str, user_prompt: str) -> str:
        adapter = getattr(executor, "llm_adapter", None)
        call = getattr(adapter, "call_completion", None)
        if not callable(call):
            raise RuntimeError("reflection provider is unavailable")
        timeout = float(
            getattr(config, "agent_planning_proposal_timeout_seconds", 30.0)
            or 30.0
        )
        timeout = max(0.1, min(timeout, MAX_REFLECTION_TIMEOUT_SECONDS))
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


def build_reflect_event_sink() -> Optional[EventSink]:
    """Return a fail-open sink emitting only bounded ``reflect_*`` attrs.

    Lesson text, remedies and strategy notes never reach observability; only
    the whitelisted counters in ``_REFLECT_EVENT_ATTRS`` are forwarded.
    """
    try:
        from src.agent.observability.events import AgentEventType, emit_agent_event
    except Exception as exc:  # broad-exception: fallback_recorded - observability is optional
        log_safe_exception(
            logger,
            "Reflection observability sink unavailable",
            exc,
            error_code="agent_reflection_event_sink_unavailable",
            level=logging.DEBUG,
        )
        return None

    def _sink(name: str, payload: Dict[str, Any]) -> None:
        allowed = _REFLECT_EVENT_ATTRS.get(name)
        if not allowed:
            return
        attrs = {
            key: payload.get(key) for key in allowed if payload.get(key) is not None
        }
        emit_agent_event(AgentEventType.REFLECT, name=name, attrs=attrs)

    return _sink


def _project_reflection_ctx(
    *,
    context: Optional[Dict[str, Any]],
    run_ctx: Any,
    metadata: Dict[str, Any],
    success: bool,
    tool_calls_log: Optional[Sequence[Dict[str, Any]]],
) -> _ReflectionRunCtx:
    """Build the bounded reflection ctx shared by every Native call site."""
    ctx = _ReflectionRunCtx()
    meta: Dict[str, Any] = {"run_success": bool(success)}
    step_payload: Any = None
    replan_kinds: Any = None

    if isinstance(context, dict):
        meta["run_id"] = context.get("run_id") or context.get("analysis_history_id")
        meta["episode_id"] = context.get("episode_id")
        ctx.stock_code = context.get("stock_code")
        meta["planning_outcome"] = {
            "status": metadata.get("status"),
            "reason": metadata.get("reason"),
            "observation_replans": metadata.get("observation_replans", 0),
        }
        meta["degraded_stages"] = list(context.get("degraded_stages") or [])[
            :MAX_DEGRADED_STAGE_ROWS
        ]
        step_payload = context.get(STEP_CRITIQUE_META_KEY) or metadata.get(
            STEP_CRITIQUE_META_KEY
        )
    else:
        meta["run_id"] = None
        meta["episode_id"] = None

    run_meta = getattr(run_ctx, "meta", None) if run_ctx is not None else None
    if isinstance(run_meta, dict):
        for key in ("response_mode", "prediction_id", "mode_budget_account"):
            value = run_meta.get(key)
            if value is not None:
                meta[key] = value
        for key in ("run_id", "episode_id"):
            if meta.get(key) is None:
                meta[key] = run_meta.get(key)
        if meta.get("run_id") is None:
            meta["run_id"] = run_meta.get("analysis_history_id")
        degraded = run_meta.get("degraded_stages")
        if isinstance(degraded, list) and degraded:
            meta["degraded_stages"] = list(degraded)[:MAX_DEGRADED_STAGE_ROWS]
        trace = bounded_critic_trace(run_meta.get("critic_trace"))
        if trace is not None:
            meta["critic_trace"] = trace
        if step_payload is None:
            step_payload = run_meta.get(STEP_CRITIQUE_META_KEY)
        replan_kinds = run_meta.get("replan_reason_kinds")
    if run_ctx is not None:
        if not ctx.stock_code:
            ctx.stock_code = getattr(run_ctx, "stock_code", None)
        ctx.opinions = list(getattr(run_ctx, "opinions", None) or [])[:MAX_OPINION_ROWS]
        ctx.risk_flags = list(getattr(run_ctx, "risk_flags", None) or [])[
            :MAX_RISK_FLAG_ROWS
        ]

    if isinstance(step_payload, dict):
        meta[STEP_CRITIQUE_META_KEY] = step_payload
        if step_payload.get("replan_reasons") and replan_kinds is None:
            replan_kinds = list(step_payload["replan_reasons"])
    if isinstance(replan_kinds, list) and replan_kinds:
        meta["replan_reason_kinds"] = [str(item) for item in replan_kinds][
            :MAX_REPLAN_REASON_ROWS
        ]

    meta["trajectory_summary"] = reflection_trajectory_summary(tool_calls_log)
    ctx.meta = meta
    return ctx


def attach_end_of_run_reflection(
    metadata: Dict[str, Any],
    *,
    executor: Any,
    config: Any,
    context: Optional[Dict[str, Any]] = None,
    success: bool,
    tool_calls_log: Optional[Sequence[Dict[str, Any]]] = None,
    run_ctx: Any = None,
    event_sink: Optional[EventSink] = None,
) -> None:
    """Attach one bounded trajectory reflection to a run metadata bag.

    Single production attach point for the planning product path, the classic
    Native ``AgentExecutor`` run and the Native Multi ``AgentOrchestrator``
    dashboard run (Issue #1089).

    Default-off via ``agent_reflection_enabled``; Chat stays off because the
    projected ``response_mode`` reaches ``is_reflection_enabled``. Fail-soft: a
    reflection provider/validation failure is explicit in metadata but never
    changes the already-computed Agent result. When the executor or run context
    holds a ``mode_budget_account``, that same object is charged so the optional
    LLM call cannot escape the run budget. Nothing here persists lessons; the
    evolution store stays with Issue #1090.
    """
    if getattr(config, "agent_reflection_enabled", False) is not True:
        return

    ctx = _project_reflection_ctx(
        context=context,
        run_ctx=run_ctx,
        metadata=metadata,
        success=success,
        tool_calls_log=tool_calls_log,
    )
    attach_mode_budget_account(ctx, executor=executor, context=context)

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
            llm_complete=reflection_llm_complete(executor, config),
            event_sink=event_sink if event_sink is not None else build_reflect_event_sink(),
        )
    except Exception as exc:  # broad-exception: fallback_recorded - optional end reflection
        log_safe_exception(
            logger,
            "End-of-run trajectory reflection failed",
            exc,
            error_code="agent_reflection_trajectory_failed",
            level=logging.INFO,
        )
        metadata[REFLECTION_META_KEY] = reflection_error_payload(
            "Trajectory reflection was unavailable."
        )
        return

    if multi.trajectory is not None:
        metadata[REFLECTION_META_KEY] = multi.trajectory
        run_meta = getattr(run_ctx, "meta", None) if run_ctx is not None else None
        if isinstance(run_meta, dict):
            run_meta[REFLECTION_META_KEY] = multi.trajectory
    if multi.episode_lessons:
        metadata["episode_lessons"] = list(multi.episode_lessons)
    if multi.replan_reason_kinds:
        metadata.setdefault("replan_reason_kinds", list(multi.replan_reason_kinds))


__all__ = [
    "MultiLevelReflectionResult",
    "apply_live_mode_budget_snapshot",
    "attach_end_of_run_reflection",
    "attach_mode_budget_account",
    "bounded_critic_trace",
    "build_reflect_event_sink",
    "reflection_error_payload",
    "reflection_llm_complete",
    "reflection_trajectory_summary",
    "resolve_mode_budget_account",
    "run_cross_run_layer",
    "run_immediate_layer",
    "run_trajectory_layer",
]
