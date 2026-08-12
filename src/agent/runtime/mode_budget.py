# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Hard per-mode execution budgets (LLM turns, tool calls, cost, tokens).

Single convergence point for mode-scoped hard budgets. Unifies with existing
wall-clock residual skips (`budget_skip` / `timeout`) via one diagnostic
snapshot and reason vocabulary:

- budget_turns / budget_tools / budget_cost / budget_tokens — hard caps
- budget_skip — residual wall-clock too low for next stage/step (existing)
- timeout — wall-clock hard limit exhausted (existing)

Hard budgets terminate with success=False and an explicit reason.
They never fabricate a completed run.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional

from src.agent.protocols import StageFailureReason
from src.agent.runtime.guards import log_runtime_guard_event

logger = logging.getLogger(__name__)

MODE_BUDGET_META_KEY = "mode_budget"
MODE_BUDGET_ACCOUNT_META_KEY = "mode_budget_account"
BUDGET_MODES = ("quick", "standard", "full", "specialist", "chat")

_DEFAULT_MODE_LIMITS: Dict[str, Dict[str, float]] = {
    "quick": {"max_llm_turns": 6, "max_tool_calls": 16, "max_cost_usd": 0.15, "max_tokens": 0},
    "standard": {"max_llm_turns": 10, "max_tool_calls": 32, "max_cost_usd": 0.50, "max_tokens": 0},
    "full": {"max_llm_turns": 12, "max_tool_calls": 48, "max_cost_usd": 1.00, "max_tokens": 0},
    "specialist": {"max_llm_turns": 12, "max_tool_calls": 64, "max_cost_usd": 1.50, "max_tokens": 0},
    "chat": {"max_llm_turns": 10, "max_tool_calls": 24, "max_cost_usd": 0.35, "max_tokens": 0},
}

_REASON_TO_FAILURE = {
    "budget_turns": StageFailureReason.BUDGET_TURNS,
    "budget_tools": StageFailureReason.BUDGET_TOOLS,
    "budget_cost": StageFailureReason.BUDGET_COST,
    "budget_tokens": StageFailureReason.BUDGET_TOKENS,
    "budget_skip": StageFailureReason.BUDGET_SKIP,
    "timeout": StageFailureReason.TIMEOUT,
}


@dataclass(frozen=True)
class ModeBudgetLimits:
    mode: str = "standard"
    enabled: bool = True
    max_llm_turns: int = 0
    max_tool_calls: int = 0
    max_cost_usd: float = 0.0
    max_tokens: int = 0

    def effective_max_steps(self, configured_max_steps: int) -> int:
        configured = max(1, int(configured_max_steps or 1))
        if not self.enabled or self.max_llm_turns <= 0:
            return configured
        return max(1, min(configured, int(self.max_llm_turns)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "enabled": bool(self.enabled),
            "max_llm_turns": int(self.max_llm_turns),
            "max_tool_calls": int(self.max_tool_calls),
            "max_cost_usd": float(self.max_cost_usd),
            "max_tokens": int(self.max_tokens),
        }


@dataclass(frozen=True)
class BudgetBreach:
    reason: str
    message: str
    used: float
    limit: float
    dimension: str

    @property
    def failure_reason(self) -> StageFailureReason:
        return _REASON_TO_FAILURE.get(self.reason, StageFailureReason.BUDGET_SKIP)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reason": self.reason,
            "message": self.message,
            "used": self.used,
            "limit": self.limit,
            "dimension": self.dimension,
            "failure_reason": self.failure_reason.value,
        }


@dataclass
class ModeBudgetAccount:
    limits: ModeBudgetLimits
    llm_turns: int = 0
    tool_calls: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    wall_clock_skips: int = 0
    breach: Optional[BudgetBreach] = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def __deepcopy__(self, memo):
        """Share the same account across isolated stage context copies.

        Stage isolation deep-copies AgentContext; run-level budgets must remain
        a single shared counter, and RLock is not picklable.
        """
        memo[id(self)] = self
        return self

    def __getstate__(self):
        state = dict(self.__dict__)
        state.pop("_lock", None)
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._lock = threading.RLock()

    def record_llm_turn(
        self, *, tokens: int = 0, cost_usd: float = 0.0, model: str = ""
    ) -> Optional[BudgetBreach]:
        with self._lock:
            if self.breach is not None:
                return self.breach
            self.llm_turns += 1
            if tokens > 0:
                self.tokens += int(tokens)
            if cost_usd > 0 and math.isfinite(cost_usd):
                self.cost_usd = round(self.cost_usd + float(cost_usd), 8)
            return self._evaluate_locked(model=model)

    def record_tool_calls(self, count: int = 1) -> Optional[BudgetBreach]:
        with self._lock:
            if self.breach is not None:
                return self.breach
            if count > 0:
                self.tool_calls += int(count)
            return self._evaluate_locked()

    def reserve_tool_calls(self, count: int = 1) -> Optional[BudgetBreach]:
        with self._lock:
            if self.breach is not None:
                return self.breach
            if not self.limits.enabled or self.limits.max_tool_calls <= 0:
                return None
            projected = self.tool_calls + max(0, int(count))
            if projected > self.limits.max_tool_calls:
                return self._set_breach_locked(
                    reason="budget_tools",
                    dimension="tool_calls",
                    used=float(projected),
                    limit=float(self.limits.max_tool_calls),
                    message=(
                        f"Mode '{self.limits.mode}' tool-call budget exceeded: "
                        f"{projected}/{self.limits.max_tool_calls}"
                    ),
                )
            return None

    def record_wall_clock_skip(self) -> None:
        with self._lock:
            self.wall_clock_skips += 1

    def mark_breach(self, breach: BudgetBreach) -> BudgetBreach:
        with self._lock:
            if self.breach is None:
                self.breach = breach
                self._log_breach(breach)
            return self.breach

    def check(self) -> Optional[BudgetBreach]:
        with self._lock:
            return self._evaluate_locked()

    def remaining_tool_calls(self) -> Optional[int]:
        with self._lock:
            if not self.limits.enabled or self.limits.max_tool_calls <= 0:
                return None
            return max(0, int(self.limits.max_tool_calls) - int(self.tool_calls))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "limits": self.limits.to_dict(),
                "used": {
                    "llm_turns": int(self.llm_turns),
                    "tool_calls": int(self.tool_calls),
                    "tokens": int(self.tokens),
                    "cost_usd": round(float(self.cost_usd), 8),
                    "wall_clock_skips": int(self.wall_clock_skips),
                },
                "breach": self.breach.to_dict() if self.breach is not None else None,
            }

    def _evaluate_locked(self, *, model: str = "") -> Optional[BudgetBreach]:
        if self.breach is not None:
            return self.breach
        if not self.limits.enabled:
            return None
        if self.limits.max_llm_turns > 0 and self.llm_turns > self.limits.max_llm_turns:
            return self._set_breach_locked(
                reason="budget_turns",
                dimension="llm_turns",
                used=float(self.llm_turns),
                limit=float(self.limits.max_llm_turns),
                message=(
                    f"Mode '{self.limits.mode}' LLM turn budget exceeded: "
                    f"{self.llm_turns}/{self.limits.max_llm_turns}"
                ),
            )
        if self.limits.max_tool_calls > 0 and self.tool_calls > self.limits.max_tool_calls:
            return self._set_breach_locked(
                reason="budget_tools",
                dimension="tool_calls",
                used=float(self.tool_calls),
                limit=float(self.limits.max_tool_calls),
                message=(
                    f"Mode '{self.limits.mode}' tool-call budget exceeded: "
                    f"{self.tool_calls}/{self.limits.max_tool_calls}"
                ),
            )
        if self.limits.max_tokens > 0 and self.tokens > self.limits.max_tokens:
            return self._set_breach_locked(
                reason="budget_tokens",
                dimension="tokens",
                used=float(self.tokens),
                limit=float(self.limits.max_tokens),
                message=(
                    f"Mode '{self.limits.mode}' token budget exceeded: "
                    f"{self.tokens}/{self.limits.max_tokens}"
                ),
            )
        if self.limits.max_cost_usd > 0 and self.cost_usd > self.limits.max_cost_usd:
            return self._set_breach_locked(
                reason="budget_cost",
                dimension="cost_usd",
                used=float(self.cost_usd),
                limit=float(self.limits.max_cost_usd),
                message=(
                    f"Mode '{self.limits.mode}' cost budget exceeded: "
                    f"${self.cost_usd:.6f}/${self.limits.max_cost_usd:.6f}"
                    + (f" (model={model})" if model else "")
                ),
            )
        return None

    def _set_breach_locked(
        self, *, reason: str, dimension: str, used: float, limit: float, message: str
    ) -> BudgetBreach:
        breach = BudgetBreach(
            reason=reason, message=message, used=used, limit=limit, dimension=dimension
        )
        self.breach = breach
        self._log_breach(breach)
        return breach

    def _log_breach(self, breach: BudgetBreach) -> None:
        log_runtime_guard_event(
            logger,
            "mode_budget_exceeded",
            scope="mode_budget",
            mode=self.limits.mode,
            reason=breach.reason,
            dimension=breach.dimension,
            used=breach.used,
            limit=breach.limit,
            action="stop",
        )


def normalize_budget_mode(mode: Optional[str], *, chat: bool = False) -> str:
    if chat:
        return "chat"
    raw = str(mode or "standard").strip().lower()
    if raw in {"strategy", "skill"}:
        return "specialist"
    if raw in BUDGET_MODES:
        return raw
    return "standard"


def resolve_mode_budget_limits(
    config: Any = None, *, mode: Optional[str] = None, chat: bool = False
) -> ModeBudgetLimits:
    resolved_mode = normalize_budget_mode(
        mode if mode is not None else getattr(config, "agent_orchestrator_mode", "standard"),
        chat=chat,
    )
    enabled = _read_bool(config, attr_name="agent_mode_budget_enabled", default=True)
    defaults = dict(_DEFAULT_MODE_LIMITS.get(resolved_mode, _DEFAULT_MODE_LIMITS["standard"]))

    max_llm_turns = _read_mode_positive_int(
        config, resolved_mode, attr_suffix="max_llm_turns",
        default=int(defaults["max_llm_turns"]),
    )
    max_tool_calls = _read_mode_positive_int(
        config, resolved_mode, attr_suffix="max_tool_calls",
        default=int(defaults["max_tool_calls"]),
    )
    max_cost_usd = _read_mode_positive_float(
        config, resolved_mode, attr_suffix="max_cost_usd",
        default=float(defaults["max_cost_usd"]),
    )
    max_tokens = _read_mode_positive_int(
        config, resolved_mode, attr_suffix="max_tokens",
        default=int(defaults["max_tokens"]),
    )

    global_turns = _read_nonneg_int(getattr(config, "agent_mode_budget_max_llm_turns", None), default=0)
    global_tools = _read_nonneg_int(getattr(config, "agent_mode_budget_max_tool_calls", None), default=0)
    global_cost = _read_nonneg_float(getattr(config, "agent_mode_budget_max_cost_usd", None), default=0.0)
    global_tokens = _read_nonneg_int(getattr(config, "agent_mode_budget_max_tokens", None), default=0)

    if global_turns > 0:
        max_llm_turns = min(max_llm_turns, global_turns) if max_llm_turns > 0 else global_turns
    if global_tools > 0:
        max_tool_calls = min(max_tool_calls, global_tools) if max_tool_calls > 0 else global_tools
    if global_cost > 0:
        max_cost_usd = min(max_cost_usd, global_cost) if max_cost_usd > 0 else global_cost
    if global_tokens > 0:
        max_tokens = min(max_tokens, global_tokens) if max_tokens > 0 else global_tokens

    return ModeBudgetLimits(
        mode=resolved_mode,
        enabled=enabled,
        max_llm_turns=max_llm_turns,
        max_tool_calls=max_tool_calls,
        max_cost_usd=max_cost_usd,
        max_tokens=max_tokens,
    )


def create_mode_budget_account(
    config: Any = None,
    *,
    mode: Optional[str] = None,
    chat: bool = False,
    limits: Optional[ModeBudgetLimits] = None,
) -> ModeBudgetAccount:
    resolved = limits or resolve_mode_budget_limits(config, mode=mode, chat=chat)
    return ModeBudgetAccount(limits=resolved)


def get_or_create_context_budget_account(
    ctx: Any,
    config: Any = None,
    *,
    mode: Optional[str] = None,
    chat: bool = False,
) -> ModeBudgetAccount:
    meta = getattr(ctx, "meta", None)
    if not isinstance(meta, dict):
        return create_mode_budget_account(config, mode=mode, chat=chat)
    existing = meta.get(MODE_BUDGET_ACCOUNT_META_KEY)
    if isinstance(existing, ModeBudgetAccount):
        return existing
    account = create_mode_budget_account(
        config,
        mode=mode or meta.get("orchestrator_mode") or getattr(config, "agent_orchestrator_mode", None),
        chat=chat or meta.get("response_mode") == "chat",
    )
    meta[MODE_BUDGET_ACCOUNT_META_KEY] = account
    meta[MODE_BUDGET_META_KEY] = account.snapshot()
    return account


def store_budget_snapshot(ctx: Any, account: ModeBudgetAccount) -> Dict[str, Any]:
    snapshot = account.snapshot()
    meta = getattr(ctx, "meta", None)
    if isinstance(meta, dict):
        meta[MODE_BUDGET_META_KEY] = snapshot
        meta[MODE_BUDGET_ACCOUNT_META_KEY] = account
    return snapshot


def estimate_usage_cost_usd(usage: Optional[Mapping[str, Any]], model: str = "") -> float:
    if not usage:
        return 0.0
    for key in ("response_cost", "completion_cost", "cost", "total_cost"):
        raw = usage.get(key)
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if math.isfinite(value) and value >= 0:
            return float(value)
    prompt_tokens = _as_nonneg_int(
        usage.get("prompt_tokens") or usage.get("normalized_prompt_tokens") or usage.get("input_tokens")
    )
    completion_tokens = _as_nonneg_int(
        usage.get("completion_tokens") or usage.get("normalized_completion_tokens") or usage.get("output_tokens")
    )
    if prompt_tokens is None and completion_tokens is None:
        return 0.0
    prompt_tokens = int(prompt_tokens or 0)
    completion_tokens = int(completion_tokens or 0)
    pricing = _lookup_model_pricing(model)
    if not pricing:
        return 0.0
    input_rate = float(pricing.get("input_cost_per_token") or 0.0)
    output_rate = float(pricing.get("output_cost_per_token") or 0.0)
    cost = prompt_tokens * input_rate + completion_tokens * output_rate
    if not math.isfinite(cost) or cost < 0:
        return 0.0
    return float(cost)


def budget_breach_from_max_steps(
    *, max_steps: int, account: Optional[ModeBudgetAccount] = None
) -> BudgetBreach:
    used = float(account.llm_turns if account is not None else max_steps)
    limit = float(
        account.limits.max_llm_turns
        if account is not None and account.limits.max_llm_turns > 0
        else max_steps
    )
    mode = account.limits.mode if account is not None else "standard"
    return BudgetBreach(
        reason="budget_turns",
        message=(
            f"Mode '{mode}' LLM turn budget exceeded: "
            f"hit max steps ({int(max_steps)}; limit {int(limit)}). "
            "Try increasing AGENT_MAX_STEPS or the mode turn budget if analysis tasks are complex."
        ),
        used=used,
        limit=limit,
        dimension="llm_turns",
    )


def _lookup_model_pricing(model: str) -> Optional[Dict[str, Any]]:
    if not model:
        return None
    try:
        import litellm  # type: ignore
        cost_map = getattr(litellm, "model_cost", None)
        if not isinstance(cost_map, dict):
            return None
        wire = str(model).strip()
        if wire in cost_map and isinstance(cost_map[wire], dict):
            return cost_map[wire]
        if "/" in wire:
            bare = wire.split("/", 1)[1]
            if bare in cost_map and isinstance(cost_map[bare], dict):
                return cost_map[bare]
    except Exception:
        return None
    return None


def _read_bool(config: Any, *, attr_name: str, default: bool) -> bool:
    raw = getattr(config, attr_name, None) if config is not None else None
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _read_mode_positive_int(config: Any, mode: str, *, attr_suffix: str, default: int) -> int:
    attr = f"agent_mode_budget_{mode}_{attr_suffix}"
    raw = getattr(config, attr, None) if config is not None else None
    if raw is None or raw == "" or raw == 0 or raw == 0.0:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _read_mode_positive_float(config: Any, mode: str, *, attr_suffix: str, default: float) -> float:
    attr = f"agent_mode_budget_{mode}_{attr_suffix}"
    raw = getattr(config, attr, None) if config is not None else None
    if raw is None or raw == "" or raw == 0 or raw == 0.0:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value) or value <= 0:
        return default
    return value


def _read_nonneg_int(raw: Any, *, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def _read_nonneg_float(raw: Any, *, default: float) -> float:
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value) or value < 0:
        return default
    return value


def _as_nonneg_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


__all__ = [
    "BUDGET_MODES",
    "BudgetBreach",
    "MODE_BUDGET_ACCOUNT_META_KEY",
    "MODE_BUDGET_META_KEY",
    "ModeBudgetAccount",
    "ModeBudgetLimits",
    "budget_breach_from_max_steps",
    "create_mode_budget_account",
    "estimate_usage_cost_usd",
    "get_or_create_context_budget_account",
    "normalize_budget_mode",
    "resolve_mode_budget_limits",
    "store_budget_snapshot",
]
