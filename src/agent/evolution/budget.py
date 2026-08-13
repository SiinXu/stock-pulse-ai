# -*- coding: utf-8 -*-
"""Hard LLM call budget for multi-level reflection paths.

Semantics intentionally mirror ``src/agent/critic.py`` budget-skip recording:
when the remaining budget cannot fund another LLM call, the path records an
explicit ``budget_skipped`` validation status and does **not** silently pretend
the optional work completed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


BUDGET_SKIPPED = "budget_skipped"
DEFAULT_STEP_CRITIQUE_LLM_BUDGET = 0
DEFAULT_REFLECTION_LLM_BUDGET = 1
DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET = 8
DEFAULT_META_REVIEW_LLM_BUDGET = 0
MAX_REFLECTION_LLM_CALL_BUDGET = 64
MAX_BUDGET_SKIP_REASONS = 32


@dataclass
class LlmCallBudget:
    """Process-local counter for optional reflection LLM calls."""

    total: int = DEFAULT_REFLECTION_LLM_BUDGET
    consumed: int = 0
    skips: int = 0
    skip_reasons: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if type(self.total) is not int:
            raise TypeError("llm budget total must be an integer")
        if not 0 <= self.total <= MAX_REFLECTION_LLM_CALL_BUDGET:
            raise ValueError(
                f"llm budget total must be between 0 and {MAX_REFLECTION_LLM_CALL_BUDGET}"
            )
        if type(self.consumed) is not int:
            raise TypeError("llm budget consumed must be an integer")
        if self.consumed < 0:
            raise ValueError("llm budget consumed must be >= 0")
        if self.consumed > self.total:
            raise ValueError("llm budget consumed must not exceed total")
        if type(self.skips) is not int or self.skips < 0:
            raise ValueError("llm budget skips must be a non-negative integer")
        if not isinstance(self.skip_reasons, list):
            raise TypeError("llm budget skip_reasons must be a list")
        if any(not isinstance(reason, str) for reason in self.skip_reasons):
            raise TypeError("every llm budget skip reason must be a string")
        self.skip_reasons = [
            reason.strip()[:160]
            for reason in self.skip_reasons[-MAX_BUDGET_SKIP_REASONS:]
            if reason.strip()
        ]

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.consumed)

    def try_consume(self, *, reason: str = "llm_call") -> bool:
        """Consume one call when available; otherwise record an explicit skip."""
        if self.remaining < 1:
            self.record_skip(reason=f"budget_exhausted:{reason}")
            return False
        self.consumed += 1
        return True

    def record_skip(self, *, reason: str) -> Dict[str, Any]:
        """Record that optional LLM work was skipped; never silent."""
        if not isinstance(reason, str):
            raise TypeError("budget skip reason must be a string")
        self.skips += 1
        safe_reason = reason.strip()[:160] or "budget_exhausted"
        self.skip_reasons.append(safe_reason)
        if len(self.skip_reasons) > MAX_BUDGET_SKIP_REASONS:
            self.skip_reasons = self.skip_reasons[-MAX_BUDGET_SKIP_REASONS:]
        return self.snapshot(validation_status=BUDGET_SKIPPED, skip_reason=safe_reason)

    def snapshot(
        self,
        *,
        validation_status: str = "valid",
        skip_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bounded budget fields for traces and ReflectionResult."""
        return {
            "llm_budget_total": self.total,
            "llm_budget_consumed": self.consumed,
            "llm_budget_remaining": self.remaining,
            "llm_budget_skips": self.skips,
            "validation_status": validation_status,
            "skip_reason": skip_reason,
            "skip_reasons": list(self.skip_reasons),
        }


def budget_from_config(
    config: Any,
    *,
    attr: str = "agent_reflection_llm_budget",
    default: int = DEFAULT_REFLECTION_LLM_BUDGET,
) -> LlmCallBudget:
    """Build a budget from a named config attribute with a safe default."""
    raw = getattr(config, attr, None) if config is not None else None
    total = raw if type(raw) is int else default
    if type(total) is not int:
        raise TypeError("default llm budget must be an integer")
    return LlmCallBudget(total=total)


__all__ = [
    "BUDGET_SKIPPED",
    "DEFAULT_META_REVIEW_LLM_BUDGET",
    "DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET",
    "DEFAULT_REFLECTION_LLM_BUDGET",
    "DEFAULT_STEP_CRITIQUE_LLM_BUDGET",
    "LlmCallBudget",
    "MAX_REFLECTION_LLM_CALL_BUDGET",
    "budget_from_config",
]
