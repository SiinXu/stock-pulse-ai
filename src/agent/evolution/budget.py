# -*- coding: utf-8 -*-
"""Hard LLM call budget for reflection / post-mortem paths.

Semantics intentionally mirror ``src/agent/critic.py`` budget-skip recording:
when the remaining budget cannot fund another LLM call, the path records an
explicit ``budget_skipped`` validation status and does **not** silently pretend
the optional work completed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


BUDGET_SKIPPED = "budget_skipped"
DEFAULT_REFLECTION_LLM_BUDGET = 1
DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET = 8


@dataclass
class LlmCallBudget:
    """Process-local counter for optional reflection LLM calls."""

    total: int = DEFAULT_REFLECTION_LLM_BUDGET
    consumed: int = 0
    skips: int = 0
    skip_reasons: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.total < 0:
            raise ValueError("llm budget total must be >= 0")
        if self.consumed < 0:
            raise ValueError("llm budget consumed must be >= 0")
        self.consumed = min(self.consumed, self.total)

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
        self.skips += 1
        safe_reason = (reason or "budget_exhausted").strip() or "budget_exhausted"
        self.skip_reasons.append(safe_reason)
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


def budget_from_config(config: Any, *, default: int = DEFAULT_REFLECTION_LLM_BUDGET) -> LlmCallBudget:
    """Build a budget from config attributes with safe defaults."""
    raw = getattr(config, "agent_reflection_llm_budget", None)
    if raw is None:
        raw = getattr(config, "agent_postmortem_llm_budget", None)
    try:
        total = int(raw) if raw is not None else int(default)
    except (TypeError, ValueError):
        total = int(default)
    return LlmCallBudget(total=max(0, total))


__all__ = [
    "BUDGET_SKIPPED",
    "DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET",
    "DEFAULT_REFLECTION_LLM_BUDGET",
    "LlmCallBudget",
    "budget_from_config",
]
