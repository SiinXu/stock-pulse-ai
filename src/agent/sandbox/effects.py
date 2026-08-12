# -*- coding: utf-8 -*-
"""External-effect fence for sandbox runs.

Any production side effect (decision signals, notifications, real orders)
attempted while a sandbox is active is recorded as blocked and refused.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


_BLOCKED_EFFECTS: ContextVar[Optional[List["BlockedExternalEffect"]]] = ContextVar(
    "agent_sandbox_blocked_effects",
    default=None,
)


class SandboxExternalEffectBlocked(RuntimeError):
    """Raised when a production write is attempted under an active sandbox."""

    def __init__(
        self,
        *,
        effect: str,
        sandbox_run_id: str,
        message: Optional[str] = None,
    ) -> None:
        self.effect = effect
        self.sandbox_run_id = sandbox_run_id
        super().__init__(
            message
            or (
                f"Sandbox refuses production external effect {effect!r} "
                f"(run_id={sandbox_run_id})"
            )
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": "sandbox_external_effect_blocked",
            "effect": self.effect,
            "sandbox_run_id": self.sandbox_run_id,
            "message": str(self),
            "simulation": True,
        }


@dataclass(frozen=True)
class BlockedExternalEffect:
    effect: str
    sandbox_run_id: str
    detail: str
    recorded_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "effect": self.effect,
            "sandbox_run_id": self.sandbox_run_id,
            "detail": self.detail,
            "recorded_at": self.recorded_at,
            "blocked": True,
            "simulation": True,
        }


def record_blocked_external_effect(
    *,
    effect: str,
    sandbox_run_id: str,
    detail: str = "",
) -> BlockedExternalEffect:
    """Append one blocked-effect receipt when a fence is active."""
    entry = BlockedExternalEffect(
        effect=str(effect),
        sandbox_run_id=str(sandbox_run_id),
        detail=str(detail or ""),
        recorded_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    bucket = _BLOCKED_EFFECTS.get()
    if bucket is not None:
        bucket.append(entry)
    return entry


def get_blocked_external_effects() -> List[BlockedExternalEffect]:
    bucket = _BLOCKED_EFFECTS.get()
    if not bucket:
        return []
    return list(bucket)


@dataclass
class ExternalEffectFence:
    """Records blocked production effects for the active sandbox run."""

    sandbox_run_id: str
    _effects: List[BlockedExternalEffect] = field(default_factory=list)

    def activate(self) -> Token:
        self._effects = []
        return _BLOCKED_EFFECTS.set(self._effects)

    def deactivate(self, token: Token) -> None:
        _BLOCKED_EFFECTS.reset(token)

    @property
    def blocked(self) -> List[BlockedExternalEffect]:
        return list(self._effects)

    def as_dicts(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self._effects]


# Canonical effect names used by production write fences.
EFFECT_DECISION_SIGNAL = "decision_signal.write"
EFFECT_DECISION_MEMORY = "decision_memory.write"
EFFECT_ANALYSIS_HISTORY = "analysis_history.write"
EFFECT_NOTIFICATION = "notification.send"
EFFECT_REAL_ORDER = "order.place"
EFFECT_PRODUCTION_PORTFOLIO = "portfolio.production_write"
