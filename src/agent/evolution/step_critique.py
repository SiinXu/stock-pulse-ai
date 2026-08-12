# -*- coding: utf-8 -*-
"""Immediate (in-loop) step critique for multi-level reflection (Issue #1094).

Triggered after tool failure or contradictory observations. Emits typed
``ReflectionLesson`` values and standardized replan reason codes aligned with
the shared lesson taxonomy. Product execution is deterministic; library callers
may inject an explicit budget and LLM callback for bounded enrichment. Never
mutates Agent Soul or ToolSurface denials.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.evolution.budget import (
    BUDGET_SKIPPED,
    DEFAULT_STEP_CRITIQUE_LLM_BUDGET,
    LlmCallBudget,
)
from src.agent.evolution.guards import (
    assert_soul_unchanged,
    assert_tool_surface_unchanged,
    snapshot_soul_identity,
    snapshot_tool_surface_denials,
)
from src.agent.evolution.lessons import (
    LESSON_KINDS,
    ReflectionLesson,
    ReflectionResult,
    lessons_from_kinds,
    parse_lessons_payload,
)
from src.agent.public_contract import sanitize_agent_diagnostic
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

STEP_CRITIQUE_META_KEY = "step_critique_result"
STEP_CRITIQUE_EVENTS = (
    "step_critique_start",
    "step_critique_lesson",
    "step_critique_end",
)

_ERROR_CODE_TO_KIND: Dict[str, str] = {
    "tool_failed": "tool_failure",
    "tool_error": "tool_failure",
    "tool_denied": "tool_failure",
    "permission_denied": "tool_failure",
    "timeout": "tool_failure",
    "timed_out": "tool_failure",
    "provider_error": "tool_failure",
    "invalid_tool_result": "format_violation",
    "invalid_plan": "format_violation",
    "schema_invalid": "format_violation",
    "format_error": "format_violation",
    "missing_evidence": "evidence_gap",
    "no_data": "evidence_gap",
    "data_unavailable": "evidence_gap",
    "empty_result": "evidence_gap",
    "contradiction": "overclaim",
    "conflicting_signal": "overclaim",
    "overconfident": "overconfidence",
    "risk_missing": "risk_omission",
    "horizon_mismatch": "horizon_mismatch",
    "regime_shift": "regime_shift",
}

_CONTRADICTION_HINTS = (
    "contradict",
    "conflict",
    "inconsist",
    "disagree",
    "mismatch",
)

_JSON_FENCE_PATTERN = re.compile(
    r"\A```(?:json)?\s*(?P<body>.*?)\s*```\Z",
    re.DOTALL | re.IGNORECASE,
)

LlmCompleteFn = Callable[[str, str], str]
MAX_STEP_CRITIQUE_OBSERVATIONS = 16
MAX_STEP_CRITIQUE_LESSONS = 8


def _bounded_observations(observations: Sequence[Any]) -> List[Any]:
    if isinstance(observations, (str, bytes)) or not isinstance(
        observations, Sequence
    ):
        raise TypeError("observations must be a sequence")
    if len(observations) > MAX_STEP_CRITIQUE_OBSERVATIONS:
        raise ValueError(
            f"observations exceeds {MAX_STEP_CRITIQUE_OBSERVATIONS} items"
        )
    return list(observations)


def _bounded_source(value: Any) -> str:
    return sanitize_agent_diagnostic(str(value or "step"))[:64] or "step"


def is_step_critique_enabled(config: Any) -> bool:
    """Immediate critique is default-off and config-gated."""
    return getattr(config, "agent_step_critique_enabled", False) is True


def map_replan_reason_kind(
    *,
    failure_reason: Optional[str] = None,
    error_code: Optional[str] = None,
    summary: Optional[str] = None,
) -> str:
    """Map a step failure into a shared ``LessonKind`` replan reason code.

    Free-form prose never becomes a new kind; unknown text falls back to
    ``tool_failure`` for hard failures and ``other`` otherwise.
    """
    for candidate in (error_code, failure_reason):
        code = str(candidate or "").strip().lower()
        if not code:
            continue
        if code in LESSON_KINDS:
            return code
        mapped = _ERROR_CODE_TO_KIND.get(code)
        if mapped is not None:
            return mapped
        for key, kind in _ERROR_CODE_TO_KIND.items():
            if key in code:
                return kind

    text = " ".join(
        str(part or "").lower()
        for part in (failure_reason, error_code, summary)
        if part
    )
    if any(hint in text for hint in _CONTRADICTION_HINTS):
        return "overclaim"
    if "risk" in text and ("omit" in text or "missing" in text or "ignore" in text):
        return "risk_omission"
    if "evidence" in text or "missing data" in text or "no data" in text:
        return "evidence_gap"
    if "format" in text or "schema" in text or "parse" in text:
        return "format_violation"
    if "tool" in text or "timeout" in text or "denied" in text or "fail" in text:
        return "tool_failure"
    return "other"


def should_trigger_step_critique(
    observations: Sequence[Any],
    *,
    force: bool = False,
) -> bool:
    """True when the latest observations indicate tool failure or contradiction."""
    if type(force) is not bool:
        raise TypeError("force must be a boolean")
    bounded = _bounded_observations(observations)
    if force:
        return True
    for obs in bounded:
        status = str(getattr(obs, "status", "") or "").lower()
        if status in {"failed", "timed_out", "budget_exhausted"}:
            return True
        failure_reason = getattr(obs, "failure_reason", None)
        if failure_reason:
            return True
        for call in list(getattr(obs, "tool_calls", None) or ()):
            if getattr(call, "ok", True) is False:
                return True
            summary = str(getattr(call, "summary", "") or "").lower()
            if any(hint in summary for hint in _CONTRADICTION_HINTS):
                return True
        if isinstance(obs, dict):
            mapping_status = str(obs.get("status") or "").lower()
            if mapping_status in {"failed", "timed_out", "budget_exhausted"}:
                return True
            if obs.get("failure_reason"):
                return True
            raw_calls = obs.get("tool_calls") or []
            if not isinstance(raw_calls, (list, tuple)):
                continue
            for call in raw_calls:
                if isinstance(call, dict) and call.get("ok") is False:
                    return True
                if not isinstance(call, dict):
                    continue
                summary = str(call.get("summary") or "").lower()
                if any(hint in summary for hint in _CONTRADICTION_HINTS):
                    return True
    return False


def deterministic_step_lessons(
    observations: Sequence[Any],
    *,
    max_lessons: int = 8,
) -> Tuple[List[ReflectionLesson], List[str]]:
    """Build typed lessons and replan reason codes from observations (no LLM)."""
    bounded = _bounded_observations(observations)
    if type(max_lessons) is not int:
        raise TypeError("max_lessons must be an integer")
    if not 1 <= max_lessons <= MAX_STEP_CRITIQUE_LESSONS:
        raise ValueError(
            f"max_lessons must be between 1 and {MAX_STEP_CRITIQUE_LESSONS}"
        )
    lessons: List[ReflectionLesson] = []
    reason_codes: List[str] = []
    seen_kinds: set = set()

    def _add(kind: str, *, source_step: str, remedy: str, severity: str = "medium") -> None:
        if kind not in LESSON_KINDS or kind in seen_kinds:
            if kind in LESSON_KINDS and kind not in reason_codes:
                reason_codes.append(kind)
            return
        if len(lessons) >= max_lessons:
            return
        seen_kinds.add(kind)
        reason_codes.append(kind)
        lessons.extend(
            lessons_from_kinds(
                [kind],
                severity=severity,  # type: ignore[arg-type]
                remedies={kind: remedy},
                source_step=source_step,
            )
        )

    for obs in bounded:
        if isinstance(obs, dict):
            step_id = obs.get("step_id")
            status = str(obs.get("status") or "").lower()
            failure_reason = obs.get("failure_reason")
            tool_calls = obs.get("tool_calls") or []
            if not isinstance(tool_calls, (list, tuple)):
                tool_calls = []
        else:
            step_id = getattr(obs, "step_id", None)
            status = str(getattr(obs, "status", "") or "").lower()
            failure_reason = getattr(obs, "failure_reason", None)
            tool_calls = list(getattr(obs, "tool_calls", None) or ())

        source = _bounded_source(
            f"step:{step_id}" if step_id is not None else "step"
        )
        if status in {"failed", "timed_out", "budget_exhausted"} or failure_reason:
            kind = map_replan_reason_kind(
                failure_reason=str(failure_reason) if failure_reason else status,
                error_code=str(failure_reason) if failure_reason else status,
            )
            _add(
                kind,
                source_step=source,
                remedy=(
                    f"Replan after {kind}; avoid repeating the failed path "
                    "without an alternative."
                ),
                severity="high" if status in {"failed", "timed_out"} else "medium",
            )

        for call in tool_calls:
            if isinstance(call, dict):
                ok = call.get("ok", True)
                error_code = call.get("error_code")
                summary = call.get("summary")
                tool_name = call.get("tool_name") or "tool"
            else:
                ok = getattr(call, "ok", True)
                error_code = getattr(call, "error_code", None)
                summary = getattr(call, "summary", None)
                tool_name = getattr(call, "tool_name", None) or "tool"
            if ok is True and not (
                summary and any(h in str(summary).lower() for h in _CONTRADICTION_HINTS)
            ):
                continue
            kind = map_replan_reason_kind(
                failure_reason=None if ok is True else "tool_failed",
                error_code=str(error_code) if error_code else None,
                summary=str(summary) if summary else None,
            )
            _add(
                kind,
                source_step=_bounded_source(f"{source}:{tool_name}"),
                remedy=sanitize_agent_diagnostic(
                    f"Tool {tool_name} produced a {kind} signal; replan with "
                    "alternatives and do not invent missing data."
                )[:300],
                severity="high" if ok is False else "medium",
            )

    return lessons, reason_codes


def critique_step_observations(
    observations: Sequence[Any],
    *,
    config: Any = None,
    ctx: Any = None,
    budget: Optional[LlmCallBudget] = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    tool_surface: Any = None,
    denied_tools: Optional[Sequence[str]] = None,
    denial_codes: Optional[Sequence[str]] = None,
    force: bool = False,
    event_sink: Optional[Callable[[str, Dict[str, Any]], None]] = None,
) -> ReflectionResult:
    """Run the immediate step-critique layer and attach results to run meta."""
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(
        tool_surface,
        denied_tools=denied_tools,
        denial_codes=denial_codes,
    )

    def _emit(name: str, payload: Dict[str, Any]) -> None:
        if event_sink is not None:
            event_sink(name, payload)

    if config is not None and not is_step_critique_enabled(config) and not force:
        result = ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="disabled",
            status="disabled",
            validation_status="disabled",
            skip_reason="Step critique is disabled by configuration.",
        )
        _attach(ctx, result, replan_reasons=[])
        assert_soul_unchanged(soul_before)
        assert_tool_surface_unchanged(
            tools_before,
            tool_surface,
            denied_tools=denied_tools,
            denial_codes=denial_codes,
        )
        return result

    if not should_trigger_step_critique(observations, force=force):
        result = ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="skipped_hit",
            status="skipped_hit",
            validation_status="skipped",
            skip_reason="No tool failure or contradictory observation to critique.",
        )
        _attach(ctx, result, replan_reasons=[])
        assert_soul_unchanged(soul_before)
        assert_tool_surface_unchanged(
            tools_before,
            tool_surface,
            denied_tools=denied_tools,
            denial_codes=denial_codes,
        )
        return result

    call_budget = budget
    if call_budget is None:
        call_budget = LlmCallBudget(total=DEFAULT_STEP_CRITIQUE_LLM_BUDGET)

    _emit("step_critique_start", {"llm_budget_total": call_budget.total})

    lessons, reason_codes = deterministic_step_lessons(observations)
    terminate_reason = "ok"
    status = "completed"
    validation_status = "valid"
    skip_reason: Optional[str] = None
    strategy_note: Optional[str] = None

    if llm_complete is not None:
        if not call_budget.try_consume(reason="step_critique"):
            if not lessons:
                terminate_reason = "budget"
                status = "budget_skipped"
                validation_status = BUDGET_SKIPPED
                skip_reason = "Step critique LLM call skipped: budget exhausted."
            else:
                skip_reason = "Step critique LLM enrichment skipped: budget exhausted."
                validation_status = BUDGET_SKIPPED
        else:
            try:
                raw = llm_complete(
                    _step_critique_system_prompt(),
                    _step_critique_user_payload(observations, lessons),
                )
                enriched = _parse_optional_lessons(raw)
                if enriched is None:
                    validation_status = "invalid"
                    skip_reason = "Step critique LLM output was invalid."
                elif enriched:
                    lessons = _merge_lessons(lessons, enriched)
            except Exception as exc:  # broad-exception: fallback_recorded - optional LLM fail-soft
                log_safe_exception(
                    logger,
                    "Step critique LLM call failed",
                    exc,
                    error_code="agent_step_critique_llm_failed",
                    level=logging.WARNING,
                )
                skip_reason = sanitize_agent_diagnostic(
                    f"Step critique LLM failed: {type(exc).__name__}"
                )
                validation_status = "error"

    for lesson in lessons:
        if lesson.kind not in reason_codes:
            reason_codes.append(lesson.kind)
        _emit(
            "step_critique_lesson",
            {
                "kind": lesson.kind,
                "severity": lesson.severity,
                "source_step": lesson.source_step,
            },
        )

    result = ReflectionResult(
        lessons=lessons,
        revised=False,
        terminate_reason=terminate_reason,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        run_id=_meta_str(ctx, "run_id") or _meta_str(ctx, "analysis_history_id"),
        episode_id=_meta_str(ctx, "episode_id"),
        strategy_note=strategy_note,
        llm_budget_total=call_budget.total,
        llm_budget_consumed=call_budget.consumed,
        llm_budget_remaining=call_budget.remaining,
        validation_status=validation_status,
        skip_reason=skip_reason,
    )
    _attach(ctx, result, replan_reasons=reason_codes)
    _emit(
        "step_critique_end",
        {
            "status": result.status,
            "lesson_count": len(result.lessons),
            "replan_reasons": list(reason_codes),
            "llm_budget_consumed": result.llm_budget_consumed,
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


def _attach(ctx: Any, result: ReflectionResult, *, replan_reasons: Sequence[str]) -> None:
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return
    payload = result.to_public_dict()
    payload["layer"] = "immediate"
    payload["replan_reasons"] = [code for code in replan_reasons if code in LESSON_KINDS]
    meta[STEP_CRITIQUE_META_KEY] = payload
    if payload["replan_reasons"]:
        meta["replan_reason_kinds"] = list(payload["replan_reasons"])


def _meta_str(ctx: Any, key: str) -> Optional[str]:
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return None
    value = meta.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _step_critique_system_prompt() -> str:
    return """\
You are a bounded, tool-free step critic for a stock research agent.
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
  ]
}
Use only the listed lesson kinds. Prefer empty lessons over invented claims.
"""


def _step_critique_user_payload(
    observations: Sequence[Any],
    seed: Sequence[ReflectionLesson],
) -> str:
    obs_payload: List[Dict[str, Any]] = []
    for obs in list(observations)[:16]:
        if isinstance(obs, dict):
            obs_payload.append(obs)
        elif hasattr(obs, "to_dict"):
            obs_payload.append(obs.to_dict())
        else:
            obs_payload.append(
                {
                    "step_id": getattr(obs, "step_id", None),
                    "status": getattr(obs, "status", None),
                    "failure_reason": getattr(obs, "failure_reason", None),
                }
            )
    payload = {
        "seed_lessons": [lesson.model_dump(mode="python") for lesson in seed],
        "observations": obs_payload,
    }
    return (
        "Critique failed or contradictory steps; emit typed lessons only:\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def _parse_optional_lessons(raw_text: str) -> Optional[List[ReflectionLesson]]:
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
    if not isinstance(parsed, dict):
        return None
    try:
        return parse_lessons_payload(parsed.get("lessons", []))
    except (TypeError, ValueError):
        return None


def _merge_lessons(
    base: Sequence[ReflectionLesson],
    extra: Sequence[ReflectionLesson],
    *,
    max_lessons: int = 8,
) -> List[ReflectionLesson]:
    out: List[ReflectionLesson] = list(base)
    seen = {lesson.kind for lesson in out}
    for lesson in extra:
        if lesson.kind in seen:
            continue
        out.append(lesson)
        seen.add(lesson.kind)
        if len(out) >= max_lessons:
            break
    return out


__all__ = [
    "STEP_CRITIQUE_EVENTS",
    "STEP_CRITIQUE_META_KEY",
    "critique_step_observations",
    "deterministic_step_lessons",
    "is_step_critique_enabled",
    "map_replan_reason_kind",
    "should_trigger_step_critique",
]
