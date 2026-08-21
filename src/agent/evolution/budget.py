# -*- coding: utf-8 -*-
"""Hard LLM call budget for multi-level reflection paths.

Semantics intentionally mirror ``src/agent/critic.py`` budget-skip recording:
when the remaining budget cannot fund another LLM call, the path records an
explicit ``budget_skipped`` validation status and does **not** silently pretend
the optional work completed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


BUDGET_SKIPPED = "budget_skipped"
DEFAULT_STEP_CRITIQUE_LLM_BUDGET = 0
DEFAULT_REFLECTION_LLM_BUDGET = 1
DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET = 8
DEFAULT_META_REVIEW_LLM_BUDGET = 0
DECISION_LLM_TURN_RESERVE = 1
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


def _mode_budget_account_from_ctx(ctx: Any) -> Any:
    meta = getattr(ctx, "meta", None) if ctx is not None else None
    if not isinstance(meta, dict):
        return None
    return meta.get("mode_budget_account")


def _refresh_mode_budget_snapshot(ctx: Any, account: Any) -> None:
    snapshot = getattr(account, "snapshot", None)
    if not callable(snapshot):
        return
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return
    try:
        meta["mode_budget"] = snapshot()
    except Exception as exc:  # broad-exception: fallback_recorded - snapshot refresh is diagnostic only
        log_safe_exception(
            logger,
            "Mode-budget snapshot refresh failed",
            exc,
            error_code="agent_reflection_mode_budget_snapshot_failed",
            level=logging.INFO,
        )


def mode_budget_turn_block_reason(
    ctx: Any,
    *,
    required_llm_turns: int = 1,
    reserve_llm_turns: int = 0,
) -> Optional[str]:
    """Return a run-account reason that forbids another LLM call.

    Does not increment counters. ``None`` means there is no run account, the
    account is disabled, or the requested turns plus reserve still fit.
    In-loop optional work must pass ``reserve_llm_turns`` so required
    downstream stages (Decision) keep a turn. End-of-run reflection keeps the
    default reserve of 0.
    """
    account = _mode_budget_account_from_ctx(ctx)
    if account is None:
        return None
    check = getattr(account, "check", None)
    snapshot = getattr(account, "snapshot", None)
    try:
        breach = check() if callable(check) else getattr(account, "breach", None)
        if breach is not None:
            return str(getattr(breach, "reason", None) or "budget_turns")
        if not callable(snapshot):
            return None
        payload = snapshot()
    except Exception as exc:  # broad-exception: fallback_recorded - unreadable run account must skip optional LLM
        log_safe_exception(
            logger,
            "Mode-budget account probe failed",
            exc,
            error_code="agent_reflection_mode_budget_probe_failed",
            level=logging.INFO,
        )
        return "budget_turns"
    if not isinstance(payload, dict):
        return "budget_turns"
    limits = payload.get("limits")
    used = payload.get("used")
    if not isinstance(limits, dict) or not isinstance(used, dict):
        return "budget_turns"
    if limits.get("enabled") is False:
        return None
    try:
        max_turns = max(0, int(limits.get("max_llm_turns") or 0))
        used_turns = max(0, int(used.get("llm_turns") or 0))
        required = max(1, int(required_llm_turns))
        reserve = max(0, int(reserve_llm_turns))
    except (TypeError, ValueError):
        return "budget_turns"
    if max_turns > 0 and used_turns + required + reserve > max_turns:
        return "budget_turns"
    return None


def record_mode_budget_llm_turn(ctx: Any) -> Optional[str]:
    """Record one LLM turn on the run account after nested ``try_consume``.

    Returns a breach reason when the call must be skipped. Missing accounts
    are a no-op so nested ``LlmCallBudget`` remains the only cap.
    """
    account = _mode_budget_account_from_ctx(ctx)
    if account is None:
        return None
    record = getattr(account, "record_llm_turn", None)
    if not callable(record):
        return "budget_turns"
    try:
        breach = record()
    except Exception as exc:  # broad-exception: fallback_recorded - failed accounting must skip the optional LLM
        log_safe_exception(
            logger,
            "Mode-budget record_llm_turn failed",
            exc,
            error_code="agent_reflection_mode_budget_record_failed",
            level=logging.INFO,
        )
        return "budget_turns"
    _refresh_mode_budget_snapshot(ctx, account)
    if breach is not None:
        return str(getattr(breach, "reason", None) or "budget_turns")
    return None


def try_consume_with_run_account(
    call_budget: LlmCallBudget,
    ctx: Any,
    *,
    reason: str,
    required_llm_turns: int = 1,
    reserve_llm_turns: int = 0,
) -> bool:
    """Consume one nested slot and one run-account turn when both allow it.

    Callers must record ``budget_skipped`` when this returns False. The nested
    ``LlmCallBudget`` is unchanged in meaning; the run account is charged only
    for calls that do not already go through ``run_agent_loop``. In-loop
    optional work must pass ``reserve_llm_turns`` so later required stages
    keep capacity.
    """
    block = mode_budget_turn_block_reason(
        ctx,
        required_llm_turns=required_llm_turns,
        reserve_llm_turns=reserve_llm_turns,
    )
    if block is not None:
        call_budget.record_skip(reason=f"budget_exhausted:{reason}")
        return False
    if not call_budget.try_consume(reason=reason):
        return False
    recorded = record_mode_budget_llm_turn(ctx)
    if recorded is not None:
        return False
    return True


__all__ = [
    "BUDGET_SKIPPED",
    "DECISION_LLM_TURN_RESERVE",
    "DEFAULT_META_REVIEW_LLM_BUDGET",
    "DEFAULT_POSTMORTEM_BATCH_LLM_BUDGET",
    "DEFAULT_REFLECTION_LLM_BUDGET",
    "DEFAULT_STEP_CRITIQUE_LLM_BUDGET",
    "LlmCallBudget",
    "MAX_REFLECTION_LLM_CALL_BUDGET",
    "budget_from_config",
    "mode_budget_turn_block_reason",
    "record_mode_budget_llm_turn",
    "try_consume_with_run_account",
]
