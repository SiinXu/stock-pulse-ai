# -*- coding: utf-8 -*-
"""Budgeted post-mortem reflection on resolved forecasts (Issue #1103).

Consumes already-scored prediction outcomes (A5 contract surface) and produces
typed ``ReflectionLesson[]`` linked to an episode. Does not invent claims from
prose, does not mutate Soul / ToolSurface, and never fabricates hits when data
is unavailable.

Upstream A1–A5 own persistence and actuals scoring. This module accepts a
minimal resolved-forecast input so it can land before those packages exist.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.agent.evolution.budget import (
    BUDGET_SKIPPED,
    DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET,
    LlmCallBudget,
)
from src.agent.evolution.guards import (
    assert_soul_unchanged,
    assert_tool_surface_unchanged,
    snapshot_soul_identity,
    snapshot_tool_surface_denials,
)
from src.agent.evolution.lessons import (
    EpisodeLessonBundle,
    ReflectionLesson,
    ReflectionResult,
    lessons_from_kinds,
    parse_lessons_payload,
)
from src.agent.public_contract import sanitize_agent_diagnostic
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

ClaimScore = Literal["hit", "partial", "miss", "data_unavailable"]
CostMode = Literal["normal", "tight"]

DEFAULT_POSTMORTEM_LLM_CALLS_PER_ITEM = 1
_JSON_FENCE_PATTERN = re.compile(
    r"\A```(?:json)?\s*(?P<body>.*?)\s*```\Z",
    re.DOTALL | re.IGNORECASE,
)
_MAX_EVIDENCE_REFS = 12
_MAX_CLAIMS = 16

LlmCompleteFn = Callable[[str, str], str]


class ResolvedClaimOutcome(BaseModel):
    """One scored claim from the horizon resolver / ClaimScorer (A5)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    claim_id: str = Field(min_length=1, max_length=128)
    claim_type: str = Field(default="custom", max_length=64)
    score: ClaimScore
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    predicted: Dict[str, Any] = Field(default_factory=dict)
    actual: Dict[str, Any] = Field(default_factory=dict)
    signals: List[str] = Field(default_factory=list, max_length=16)

    @field_validator("signals")
    @classmethod
    def _normalize_signals(cls, values: List[str]) -> List[str]:
        out: List[str] = []
        for item in values:
            if not isinstance(item, str):
                raise TypeError("signals must be strings")
            text = item.strip().lower()
            if text:
                out.append(text)
        return out


class ResolvedForecastInput(BaseModel):
    """Minimal post-resolution context for one prediction episode."""

    model_config = ConfigDict(extra="forbid", strict=True)

    episode_id: str = Field(min_length=1, max_length=128)
    prediction_id: str = Field(min_length=1, max_length=128)
    run_id: Optional[str] = Field(default=None, max_length=128)
    symbol: Optional[str] = Field(default=None, max_length=32)
    market: Optional[str] = Field(default=None, max_length=16)
    claims: List[ResolvedClaimOutcome] = Field(default_factory=list, max_length=_MAX_CLAIMS)
    evidence_refs: List[str] = Field(default_factory=list, max_length=_MAX_EVIDENCE_REFS)
    flags: List[str] = Field(default_factory=list, max_length=16)

    @field_validator("flags", "evidence_refs")
    @classmethod
    def _normalize_string_list(cls, values: List[str]) -> List[str]:
        out: List[str] = []
        for item in values:
            if not isinstance(item, str):
                raise TypeError("list items must be strings")
            text = item.strip()
            if text:
                out.append(text)
        return out


class PostMortemBatchResult(BaseModel):
    """Aggregate outcome for one resolution-batch post-mortem pass."""

    model_config = ConfigDict(extra="forbid", strict=True)

    results: List[ReflectionResult] = Field(default_factory=list)
    bundles: List[EpisodeLessonBundle] = Field(default_factory=list)
    llm_budget_total: int = 0
    llm_budget_consumed: int = 0
    llm_budget_remaining: int = 0
    budget_skips: int = 0

    def to_public_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="python")


def is_postmortem_enabled(config: Any) -> bool:
    return getattr(config, "agent_postmortem_enabled", False) is True


def _overall_score(item: ResolvedForecastInput) -> ClaimScore:
    if not item.claims:
        return "data_unavailable"
    scores = [claim.score for claim in item.claims]
    if any(score == "data_unavailable" for score in scores):
        if all(score == "data_unavailable" for score in scores):
            return "data_unavailable"
    if all(score == "hit" for score in scores):
        return "hit"
    if any(score == "miss" for score in scores):
        return "miss"
    if any(score == "partial" for score in scores):
        return "partial"
    if any(score == "data_unavailable" for score in scores):
        return "data_unavailable"
    return "hit"


def infer_lesson_kinds(item: ResolvedForecastInput) -> List[str]:
    """Deterministic kind inference from scored claims and structured flags."""
    overall = _overall_score(item)
    if overall in {"hit", "data_unavailable"}:
        return []

    kinds: List[str] = []
    flag_set = {flag.strip().lower() for flag in item.flags}
    for claim in item.claims:
        if claim.score not in {"miss", "partial"}:
            continue
        signals = set(claim.signals) | flag_set
        if "evidence_gap" in signals or "missing_evidence" in signals:
            kinds.append("evidence_gap")
        if "regime_shift" in signals or "regime_change" in signals:
            kinds.append("regime_shift")
        if "horizon_mismatch" in signals or "wrong_horizon" in signals:
            kinds.append("horizon_mismatch")
        if "tool_failure" in signals or "tool_error" in signals:
            kinds.append("tool_failure")
        if "risk_omission" in signals:
            kinds.append("risk_omission")
        if "format_violation" in signals:
            kinds.append("format_violation")
        if "overclaim" in signals:
            kinds.append("overclaim")
        if (
            "overconfidence" in signals
            or (claim.confidence is not None and claim.confidence >= 0.8 and claim.score == "miss")
        ):
            kinds.append("overconfidence")
        if claim.score == "partial" and "horizon_mismatch" not in kinds:
            if "regime_shift" in signals:
                kinds.append("regime_shift")
            else:
                kinds.append("horizon_mismatch")

    ordered: List[str] = []
    for kind in kinds:
        if kind not in ordered:
            ordered.append(kind)
    if not ordered and overall in {"miss", "partial"}:
        ordered.append("other")
    return ordered


def _default_remedies() -> Dict[str, str]:
    return {
        "evidence_gap": "Require material evidence coverage before high-confidence claims.",
        "overconfidence": "Lower confidence when confirmatory volume or multi-source checks are missing.",
        "overclaim": "Keep prose claims out of the verifiable claim pipeline.",
        "tool_failure": "Treat tool errors as missing evidence; do not substitute invented actuals.",
        "risk_omission": "Surface downside and invalidation conditions alongside opportunity language.",
        "format_violation": "Emit only schema-valid structured claims; skip non-parseable prose.",
        "regime_shift": "Re-check regime filters when macro or volatility regime flags flip.",
        "horizon_mismatch": "Align claim horizon with the resolve_after calendar used for scoring.",
        "other": "Review episode evidence snapshot before promoting the route or skill.",
    }


def build_deterministic_lessons(item: ResolvedForecastInput) -> List[ReflectionLesson]:
    """Build typed lessons from fixture-friendly score signals."""
    kinds = infer_lesson_kinds(item)
    claim_ref = item.claims[0].claim_id if item.claims else item.prediction_id
    severity = "high" if _overall_score(item) == "miss" else "medium"
    return lessons_from_kinds(
        kinds,
        claim_ref=claim_ref,
        severity=severity,  # type: ignore[arg-type]
        remedies=_default_remedies(),
        source_step="postmortem",
    )


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


def parse_postmortem_output(raw_text: str) -> ReflectionResult:
    """Parse one post-mortem LLM response into typed lessons."""
    parsed = _parse_strict_json_object(raw_text)
    if parsed is None:
        return ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="error",
            status="error",
            validation_status="invalid",
            skip_reason="Post-mortem output was not a JSON object.",
        )
    try:
        lessons = parse_lessons_payload(parsed.get("lessons", []))
        strategy_note = parsed.get("strategy_note")
        if strategy_note is not None and not isinstance(strategy_note, str):
            raise ValueError("strategy_note must be a string")
        return ReflectionResult(
            lessons=lessons,
            revised=False,
            terminate_reason="ok",
            status="completed",
            strategy_note=strategy_note,
            validation_status="valid",
        )
    except (ValidationError, TypeError, ValueError) as exc:
        log_safe_exception(
            logger,
            "Post-mortem output validation failed",
            exc,
            error_code="agent_postmortem_output_invalid",
            level=logging.INFO,
        )
        return ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="error",
            status="error",
            validation_status="invalid",
            skip_reason="Post-mortem output did not satisfy the lesson contract.",
        )


def _postmortem_system_prompt() -> str:
    return """\
You are a budgeted post-mortem reviewer for resolved stock research forecasts.
Produce typed next-time lessons only. You may NOT rewrite Agent Soul, grant
tools, invent market actuals, or promise returns.
Return only one JSON object:
{
  "lessons": [
    {
      "kind": "evidence_gap|overclaim|overconfidence|tool_failure|risk_omission|format_violation|regime_shift|horizon_mismatch|other",
      "severity": "low|medium|high",
      "claim_ref": "claim id",
      "remedy": "bounded adapter/skill hint",
      "source_step": "postmortem"
    }
  ],
  "strategy_note": "optional human note, not a Soul edit"
}
If evidence is insufficient, emit fewer lessons rather than free-form diary text.
"""


def _postmortem_user_payload(item: ResolvedForecastInput) -> str:
    payload = {
        "episode_id": item.episode_id,
        "prediction_id": item.prediction_id,
        "run_id": item.run_id,
        "symbol": item.symbol,
        "market": item.market,
        "claims": [claim.model_dump(mode="python") for claim in item.claims],
        "evidence_refs": list(item.evidence_refs),
        "flags": list(item.flags),
        "overall_score": _overall_score(item),
    }
    return (
        "Review this resolved forecast and emit typed lessons for misses/partials:\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


def reflect_resolved_forecast(
    item: ResolvedForecastInput,
    *,
    config: Any = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    budget: Optional[LlmCallBudget] = None,
    cost_mode: CostMode = "normal",
    allow_deterministic_lessons: bool = True,
    tool_surface: Any = None,
    denied_tools: Optional[Sequence[str]] = None,
    denial_codes: Optional[Sequence[str]] = None,
) -> ReflectionResult:
    """Produce lessons for one resolved prediction under a hard LLM budget."""
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(
        tool_surface,
        denied_tools=denied_tools,
        denial_codes=denial_codes,
    )

    call_budget = budget or LlmCallBudget(total=DEFAULT_POSTMORTEM_LLM_CALLS_PER_ITEM)

    if config is not None and not is_postmortem_enabled(config):
        result = ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="disabled",
            status="disabled",
            episode_id=item.episode_id,
            prediction_id=item.prediction_id,
            run_id=item.run_id,
            llm_budget_total=call_budget.total,
            llm_budget_consumed=call_budget.consumed,
            llm_budget_remaining=call_budget.remaining,
            validation_status="disabled",
            skip_reason="Post-mortem is disabled by configuration.",
        )
        assert_soul_unchanged(soul_before)
        assert_tool_surface_unchanged(
            tools_before,
            tool_surface,
            denied_tools=denied_tools,
            denial_codes=denial_codes,
        )
        return result

    overall = _overall_score(item)
    if overall == "data_unavailable":
        result = ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="ok",
            status="data_unavailable",
            episode_id=item.episode_id,
            prediction_id=item.prediction_id,
            run_id=item.run_id,
            llm_budget_total=call_budget.total,
            llm_budget_consumed=call_budget.consumed,
            llm_budget_remaining=call_budget.remaining,
            validation_status="data_unavailable",
            skip_reason=(
                "Actuals unavailable; post-mortem skipped without fabricating a hit."
            ),
        )
        assert_soul_unchanged(soul_before)
        assert_tool_surface_unchanged(
            tools_before,
            tool_surface,
            denied_tools=denied_tools,
            denial_codes=denial_codes,
        )
        return result

    if overall == "hit" and (
        cost_mode == "tight"
        or getattr(config, "agent_postmortem_skip_clean_hits", True) is True
    ):
        result = ReflectionResult(
            lessons=[],
            revised=False,
            terminate_reason="skipped_hit",
            status="skipped_hit",
            episode_id=item.episode_id,
            prediction_id=item.prediction_id,
            run_id=item.run_id,
            llm_budget_total=call_budget.total,
            llm_budget_consumed=call_budget.consumed,
            llm_budget_remaining=call_budget.remaining,
            validation_status="skipped_hit",
            skip_reason="Clean hit skipped under cost policy; no LLM post-mortem.",
        )
        assert_soul_unchanged(soul_before)
        assert_tool_surface_unchanged(
            tools_before,
            tool_surface,
            denied_tools=denied_tools,
            denial_codes=denial_codes,
        )
        return result

    lessons: List[ReflectionLesson] = []
    strategy_note: Optional[str] = None
    terminate_reason = "ok"
    status = "completed"
    validation_status = "valid"
    skip_reason: Optional[str] = None

    if allow_deterministic_lessons:
        lessons = build_deterministic_lessons(item)

    if llm_complete is not None and overall in {"miss", "partial"}:
        if not call_budget.try_consume(reason=f"postmortem:{item.prediction_id}"):
            terminate_reason = "budget"
            status = "budget_skipped"
            validation_status = BUDGET_SKIPPED
            skip_reason = (
                "Post-mortem LLM call skipped: batch LLM budget exhausted."
            )
        else:
            try:
                raw = llm_complete(
                    _postmortem_system_prompt(),
                    _postmortem_user_payload(item),
                )
                parsed = parse_postmortem_output(raw)
                if parsed.validation_status == "valid" and parsed.lessons:
                    lessons = list(parsed.lessons)
                    strategy_note = parsed.strategy_note
                elif parsed.validation_status == "valid":
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
                    "Post-mortem LLM call failed",
                    exc,
                    error_code="agent_postmortem_llm_failed",
                    level=logging.WARNING,
                )
                terminate_reason = "error"
                status = "error"
                validation_status = "error"
                skip_reason = sanitize_agent_diagnostic(
                    f"Post-mortem LLM failed: {type(exc).__name__}"
                )
                lessons = []

    result = ReflectionResult(
        lessons=lessons,
        revised=False,
        terminate_reason=terminate_reason,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        episode_id=item.episode_id,
        prediction_id=item.prediction_id,
        run_id=item.run_id,
        strategy_note=strategy_note,
        llm_budget_total=call_budget.total,
        llm_budget_consumed=call_budget.consumed,
        llm_budget_remaining=call_budget.remaining,
        validation_status=validation_status,
        skip_reason=skip_reason,
    )

    assert_soul_unchanged(soul_before)
    assert_tool_surface_unchanged(
        tools_before,
        tool_surface,
        denied_tools=denied_tools,
        denial_codes=denial_codes,
    )
    return result


def run_postmortem_batch(
    items: Sequence[ResolvedForecastInput],
    *,
    config: Any = None,
    llm_complete: Optional[LlmCompleteFn] = None,
    budget: Optional[LlmCallBudget] = None,
    cost_mode: CostMode = "normal",
    allow_deterministic_lessons: bool = True,
    tool_surface: Any = None,
    denied_tools: Optional[Sequence[str]] = None,
    denial_codes: Optional[Sequence[str]] = None,
) -> PostMortemBatchResult:
    """Run post-mortem over a resolution batch under one shared LLM budget."""
    call_budget = budget or LlmCallBudget(total=DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET)
    results: List[ReflectionResult] = []
    bundles: List[EpisodeLessonBundle] = []

    for item in items:
        result = reflect_resolved_forecast(
            item,
            config=config,
            llm_complete=llm_complete,
            budget=call_budget,
            cost_mode=cost_mode,
            allow_deterministic_lessons=allow_deterministic_lessons,
            tool_surface=tool_surface,
            denied_tools=denied_tools,
            denial_codes=denial_codes,
        )
        results.append(result)
        if result.lessons:
            bundles.append(
                EpisodeLessonBundle(
                    episode_id=item.episode_id,
                    prediction_id=item.prediction_id,
                    run_id=item.run_id,
                    result=result,
                )
            )

    return PostMortemBatchResult(
        results=results,
        bundles=bundles,
        llm_budget_total=call_budget.total,
        llm_budget_consumed=call_budget.consumed,
        llm_budget_remaining=call_budget.remaining,
        budget_skips=call_budget.skips,
    )


__all__ = [
    "ClaimScore",
    "CostMode",
    "DEFAULT_POSTMORTEM_LLM_CALLS_PER_ITEM",
    "PostMortemBatchResult",
    "ResolvedClaimOutcome",
    "ResolvedForecastInput",
    "build_deterministic_lessons",
    "infer_lesson_kinds",
    "is_postmortem_enabled",
    "parse_postmortem_output",
    "reflect_resolved_forecast",
    "run_postmortem_batch",
]
