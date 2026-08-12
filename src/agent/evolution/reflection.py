# -*- coding: utf-8 -*-
"""Run-local reflection loop contract (Issue #1089).

Produces typed ``ReflectionLesson[]`` after a primary analysis/decision without
mutating Agent Soul or ToolSurface denials. Optional single revision is hard-
capped (default 1). LLM work is optional and budgeted; budget exhaustion is an
explicit ``budget`` terminate reason, never a silent success.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

from pydantic import ValidationError

from src.agent.evolution.budget import (
    BUDGET_SKIPPED,
    DEFAULT_REFLECTION_LLM_BUDGET,
    LlmCallBudget,
)
from src.agent.evolution.guards import (
    assert_soul_unchanged,
    assert_tool_surface_unchanged,
    snapshot_soul_identity,
    snapshot_tool_surface_denials,
)
from src.agent.evolution.lessons import (
    ReflectionLesson,
    ReflectionResult,
    lessons_from_kinds,
    parse_lessons_payload,
)
from src.agent.public_contract import sanitize_agent_diagnostic
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

REFLECTION_META_KEY = "reflection_result"
REFLECTION_EVENTS = (
    "reflect_start",
    "reflect_lesson",
    "reflect_revise",
    "reflect_end",
)
DEFAULT_MAX_REVISE = 1
_JSON_FENCE_PATTERN = re.compile(
    r"\A```(?:json)?\s*(?P<body>.*?)\s*```\Z",
    re.DOTALL | re.IGNORECASE,
)

LlmCompleteFn = Callable[[str, str], str]
ReviseFn = Callable[[Any, Sequence[ReflectionLesson]], bool]


def is_reflection_enabled(config: Any, ctx: Any = None) -> bool:
    """Enable only when explicitly configured; Chat can be excluded by caller."""
    if getattr(config, "agent_reflection_enabled", False) is not True:
        return False
    if ctx is not None and getattr(ctx, "meta", None):
        if ctx.meta.get("response_mode") == "chat" and not getattr(
            config, "agent_reflection_in_chat", False
        ):
            return False
    return True


def _parse_strict_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_text, str):
        return None
    candidate = raw_text.strip()
    if not candidate:
        return None
    fenced = _JSON_FENCE_PATTERN.fullmatch(candidate)
    if fenced is not None:
        candidate = fenced.group("body").strip()
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_reflection_output(raw_text: str) -> ReflectionResult:
    """Parse one reflection LLM response; fail closed to typed empty lessons."""
    parsed = _parse_strict_json_object(raw_text)
    if parsed is None:
        return ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="error",
            status="error",
            validation_status="invalid",
            skip_reason="Reflection output was not a JSON object.",
        )
    try:
        lessons_raw = parsed.get("lessons", [])
        lessons = parse_lessons_payload(lessons_raw)
        strategy_note = parsed.get("strategy_note")
        if strategy_note is not None and not isinstance(strategy_note, str):
            raise ValueError("strategy_note must be a string")
        return ReflectionResult(
            lessons=lessons,
            revised=bool(parsed.get("revised", False)),
            terminate_reason="ok",
            status="completed",
            strategy_note=strategy_note,
            validation_status="valid",
        )
    except (ValidationError, TypeError, ValueError) as exc:
        log_safe_exception(
            logger,
            "Reflection output validation failed",
            exc,
            error_code="agent_reflection_output_invalid",
            level=logging.INFO,
        )
        return ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="error",
            status="error",
            validation_status="invalid",
            skip_reason="Reflection output did not satisfy the lesson contract.",
        )


def _disabled_result() -> ReflectionResult:
    return ReflectionResult(
        lessons=[],
        revised=False,
        terminate_reason="disabled",
        status="disabled",
        validation_status="disabled",
        skip_reason="Reflection is disabled by configuration.",
    )


def _critique_system_prompt() -> str:
    return """\
You are a bounded, tool-free reflection critic for a stock research agent.
You may NOT rewrite Agent Soul rules, grant tools, or promise returns.
Return only one JSON object:
{
  "lessons": [
    {
      "kind": "evidence_gap|overclaim|overconfidence|tool_failure|risk_omission|format_violation|regime_shift|horizon_mismatch|other",
      "severity": "low|medium|high",
      "claim_ref": "optional id",
      "remedy": "bounded next-time hint",
      "source_step": "optional stage"
    }
  ],
  "strategy_note": "optional human note, not a Soul edit",
  "revised": false
}
Use only the listed lesson kinds. Prefer empty lessons over invented claims.
"""


def run_reflection_loop(
    ctx: Any,
    *,
    config: Any = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    revise_fn: Optional[ReviseFn] = None,
    budget: Optional[LlmCallBudget] = None,
    max_revise: int = DEFAULT_MAX_REVISE,
    tool_surface: Any = None,
    denied_tools: Optional[Sequence[str]] = None,
    denial_codes: Optional[Sequence[str]] = None,
    seed_lessons: Optional[Sequence[ReflectionLesson]] = None,
    event_sink: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> ReflectionResult:
    """Execute the bounded reflection contract and attach it to run metadata."""
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(
        tool_surface,
        denied_tools=denied_tools,
        denial_codes=denial_codes,
    )

    def _emit(name: str, payload: Dict[str, Any]) -> None:
        if event_sink is not None:
            event_sink(name, payload)

    if config is not None and not is_reflection_enabled(config, ctx):
        result = _disabled_result()
        _attach_result(ctx, result)
        assert_soul_unchanged(soul_before)
        assert_tool_surface_unchanged(
            tools_before,
            tool_surface,
            denied_tools=denied_tools,
            denial_codes=denial_codes,
        )
        return result

    call_budget = budget or LlmCallBudget(total=DEFAULT_REFLECTION_LLM_BUDGET)
    max_revise = max(0, int(max_revise))
    _emit("reflect_start", {"llm_budget_total": call_budget.total})

    lessons: List[ReflectionLesson] = list(seed_lessons or [])
    terminate_reason = "ok"
    status = "completed"
    validation_status = "valid"
    skip_reason: Optional[str] = None
    strategy_note: Optional[str] = None
    revised = False

    if llm_complete is not None:
        if not call_budget.try_consume(reason="reflect_critique"):
            terminate_reason = "budget"
            status = "budget_skipped"
            validation_status = BUDGET_SKIPPED
            skip_reason = "Reflection LLM call skipped: budget exhausted."
            lessons = []
        else:
            user_payload = _build_reflection_user_payload(ctx)
            try:
                raw = llm_complete(_critique_system_prompt(), user_payload)
                parsed = parse_reflection_output(raw)
                if parsed.validation_status == "valid":
                    lessons = list(parsed.lessons)
                    strategy_note = parsed.strategy_note
                else:
                    terminate_reason = "error"
                    status = "error"
                    validation_status = "invalid"
                    skip_reason = parsed.skip_reason
                    lessons = []
            except Exception as exc:  # broad-exception: fallback_recorded
                log_safe_exception(
                    logger,
                    "Reflection LLM call failed",
                    exc,
                    error_code="agent_reflection_llm_failed",
                    level=logging.WARNING,
                )
                terminate_reason = "error"
                status = "error"
                validation_status = "error"
                skip_reason = sanitize_agent_diagnostic(
                    f"Reflection LLM failed: {type(exc).__name__}"
                )
                lessons = []

    for lesson in lessons:
        _emit(
            "reflect_lesson",
            {
                "kind": lesson.kind,
                "severity": lesson.severity,
                "claim_ref": lesson.claim_ref,
            },
        )

    if (
        terminate_reason == "ok"
        and lessons
        and revise_fn is not None
        and max_revise > 0
    ):
        try:
            did_revise = bool(revise_fn(ctx, lessons))
            if did_revise:
                revised = True
                _emit("reflect_revise", {"revised": True})
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(
                logger,
                "Reflection revise failed",
                exc,
                error_code="agent_reflection_revise_failed",
                level=logging.WARNING,
            )
            terminate_reason = "error"
            status = "error"
            validation_status = "error"
            skip_reason = sanitize_agent_diagnostic(
                f"Reflection revise failed: {type(exc).__name__}"
            )

    result = ReflectionResult(
        lessons=lessons,
        revised=revised,
        terminate_reason=terminate_reason,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        episode_id=_meta_str(ctx, "episode_id"),
        prediction_id=_meta_str(ctx, "prediction_id"),
        run_id=_meta_str(ctx, "run_id") or _meta_str(ctx, "analysis_history_id"),
        strategy_note=strategy_note,
        llm_budget_total=call_budget.total,
        llm_budget_consumed=call_budget.consumed,
        llm_budget_remaining=call_budget.remaining,
        validation_status=validation_status,
        skip_reason=skip_reason,
    )
    _attach_result(ctx, result)
    _emit(
        "reflect_end",
        {
            "terminate_reason": result.terminate_reason,
            "status": result.status,
            "lesson_count": len(result.lessons),
            "llm_budget_consumed": result.llm_budget_consumed,
            "llm_budget_remaining": result.llm_budget_remaining,
        },
    )

    assert_soul_unchanged(soul_before)
    assert_tool_surface_unchanged(
        tools_before,
        tool_surface,
        denied_tools=denied_tools,
        denial_codes=denial_codes,
    )
    return result


def _attach_result(ctx: Any, result: ReflectionResult) -> None:
    meta = getattr(ctx, "meta", None)
    if isinstance(meta, dict):
        meta[REFLECTION_META_KEY] = result.to_public_dict()


def _meta_str(ctx: Any, key: str) -> Optional[str]:
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return None
    value = meta.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_reflection_user_payload(ctx: Any) -> str:
    meta = getattr(ctx, "meta", {}) if ctx is not None else {}
    if not isinstance(meta, dict):
        meta = {}
    opinions = []
    for opinion in list(getattr(ctx, "opinions", None) or []):
        opinions.append(
            {
                "agent_name": getattr(opinion, "agent_name", None),
                "signal": getattr(opinion, "signal", None),
                "confidence": getattr(opinion, "confidence", None),
                "reasoning": getattr(opinion, "reasoning", None),
            }
        )
    payload = {
        "stock_code": getattr(ctx, "stock_code", None),
        "opinions": opinions,
        "risk_flags": list(getattr(ctx, "risk_flags", None) or [])[:10],
        "degraded_stages": meta.get("degraded_stages", []),
        "critic_trace": meta.get("critic_trace"),
    }
    return (
        "Critique this completed run snapshot and emit typed lessons only:\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def seed_lessons_from_critic_trace(trace: Optional[Dict[str, Any]]) -> List[ReflectionLesson]:
    """Map a bounded Critic trace into seed lesson kinds without a second critic voice."""
    if not isinstance(trace, dict):
        return []
    kinds: List[str] = []
    missing = trace.get("missing_evidence") or []
    if missing:
        kinds.append("evidence_gap")
    reasons = " ".join(str(item) for item in (trace.get("reasons") or [])).lower()
    if "overconfiden" in reasons or "overclaim" in reasons:
        kinds.append("overconfidence")
    if "tool" in reasons and ("fail" in reasons or "denied" in reasons):
        kinds.append("tool_failure")
    if "risk" in reasons:
        kinds.append("risk_omission")
    if not kinds and trace.get("verdict") == "fail_soft":
        kinds.append("other")
    return lessons_from_kinds(kinds, source_step="critic", severity="medium")


__all__ = [
    "DEFAULT_MAX_REVISE",
    "REFLECTION_EVENTS",
    "REFLECTION_META_KEY",
    "is_reflection_enabled",
    "parse_reflection_output",
    "run_reflection_loop",
    "seed_lessons_from_critic_trace",
]
