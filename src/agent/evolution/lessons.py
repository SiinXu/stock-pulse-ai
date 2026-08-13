# -*- coding: utf-8 -*-
"""Shared typed lesson taxonomy for run-local reflection and forecast post-mortems.

This module is the single source of truth for ReflectionLesson / ReflectionResult
shapes used by Issues #1089 (run-local reflection) and #1103 (resolved-forecast
post-mortem). Free-form prose is never accepted as a lesson kind.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.agent.public_contract import sanitize_agent_diagnostic

# Union of #1089 run-local kinds and #1103 post-mortem kinds.
LESSON_KINDS = frozenset(
    {
        "evidence_gap",
        "overclaim",
        "overconfidence",
        "tool_failure",
        "risk_omission",
        "format_violation",
        "regime_shift",
        "horizon_mismatch",
        "other",
    }
)

LessonKind = Literal[
    "evidence_gap",
    "overclaim",
    "overconfidence",
    "tool_failure",
    "risk_omission",
    "format_violation",
    "regime_shift",
    "horizon_mismatch",
    "other",
]
LessonSeverity = Literal["low", "medium", "high"]
TerminateReason = Literal["ok", "budget", "critic_reject", "error", "disabled", "skipped_hit"]
PostMortemStatus = Literal[
    "completed",
    "budget_skipped",
    "skipped_hit",
    "disabled",
    "data_unavailable",
    "error",
]

_MAX_LESSONS = 8
_MAX_REMEDY_CHARS = 300
_MAX_STRATEGY_NOTE_CHARS = 500
_MAX_REF_CHARS = 128
_MAX_SOURCE_STEP_CHARS = 64


class ReflectionLesson(BaseModel):
    """One typed lesson. Remedy is a bounded hint, not a Soul rewrite."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: LessonKind
    severity: LessonSeverity = "medium"
    claim_ref: Optional[str] = Field(default=None, max_length=_MAX_REF_CHARS)
    remedy: Optional[str] = Field(default=None, max_length=_MAX_REMEDY_CHARS)
    source_step: Optional[str] = Field(default=None, max_length=_MAX_SOURCE_STEP_CHARS)

    @field_validator("remedy", "claim_ref", "source_step", mode="before")
    @classmethod
    def _sanitize_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("text fields must be strings")
        cleaned = sanitize_agent_diagnostic(value.strip())
        return cleaned or None


class ReflectionResult(BaseModel):
    """Bounded reflection outcome for one run or one resolved prediction."""

    model_config = ConfigDict(extra="forbid", strict=True)

    lessons: List[ReflectionLesson] = Field(default_factory=list, max_length=_MAX_LESSONS)
    revised: bool = False
    terminate_reason: TerminateReason = "ok"
    status: PostMortemStatus = "completed"
    episode_id: Optional[str] = Field(default=None, max_length=_MAX_REF_CHARS)
    prediction_id: Optional[str] = Field(default=None, max_length=_MAX_REF_CHARS)
    run_id: Optional[str] = Field(default=None, max_length=_MAX_REF_CHARS)
    strategy_note: Optional[str] = Field(default=None, max_length=_MAX_STRATEGY_NOTE_CHARS)
    # Explicit budget accounting (aligned with critic fail-soft / budget_skipped).
    llm_budget_total: int = Field(default=0, ge=0)
    llm_budget_consumed: int = Field(default=0, ge=0)
    llm_budget_remaining: int = Field(default=0, ge=0)
    validation_status: str = "valid"
    skip_reason: Optional[str] = Field(default=None, max_length=_MAX_REMEDY_CHARS)

    @field_validator("strategy_note", "skip_reason", mode="before")
    @classmethod
    def _sanitize_optional_notes(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("text fields must be strings")
        cleaned = sanitize_agent_diagnostic(value.strip())
        return cleaned or None

    def to_public_dict(self) -> Dict[str, Any]:
        """Serialize for run metadata / episode storage."""
        return self.model_dump(mode="python")


class EpisodeLessonBundle(BaseModel):
    """Traceable link from an episode to the lessons produced for it."""

    model_config = ConfigDict(extra="forbid", strict=True)

    episode_id: str = Field(min_length=1, max_length=_MAX_REF_CHARS)
    prediction_id: Optional[str] = Field(default=None, max_length=_MAX_REF_CHARS)
    run_id: Optional[str] = Field(default=None, max_length=_MAX_REF_CHARS)
    result: ReflectionResult


def parse_lessons_payload(raw: Any) -> List[ReflectionLesson]:
    """Parse a list of lesson objects; reject free-form prose substitutes."""
    if not isinstance(raw, list):
        raise ValueError("lessons must be a list")
    if len(raw) > _MAX_LESSONS:
        raise ValueError(f"lessons exceeds {_MAX_LESSONS} items")
    lessons: List[ReflectionLesson] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each lesson must be an object")
        lessons.append(ReflectionLesson.model_validate(item))
    return lessons


def lessons_from_kinds(
    kinds: Sequence[str],
    *,
    claim_ref: Optional[str] = None,
    severity: LessonSeverity = "medium",
    remedies: Optional[Dict[str, str]] = None,
    source_step: Optional[str] = None,
) -> List[ReflectionLesson]:
    """Build typed lessons from known kinds only (no free-text kind invention)."""
    remedies = remedies or {}
    out: List[ReflectionLesson] = []
    for kind in kinds:
        if kind not in LESSON_KINDS:
            continue
        out.append(
            ReflectionLesson(
                kind=kind,  # type: ignore[arg-type]
                severity=severity,
                claim_ref=claim_ref,
                remedy=remedies.get(kind),
                source_step=source_step,
            )
        )
        if len(out) >= _MAX_LESSONS:
            break
    return out


__all__ = [
    "LESSON_KINDS",
    "EpisodeLessonBundle",
    "LessonKind",
    "LessonSeverity",
    "PostMortemStatus",
    "ReflectionLesson",
    "ReflectionResult",
    "TerminateReason",
    "lessons_from_kinds",
    "parse_lessons_payload",
]
