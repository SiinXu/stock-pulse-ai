# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Rules-first AgentRouter for per-run depth and chat-path classification.

Library slice for issue #1120. Callers supply already-normalized classification
facts; this module never parses prompts, messages, provider payloads, or tool
results. It does not write config, budgets, Soul, ToolSurface, episodes,
EvolutionEvents, or public API payloads, and it does not call ``prefer_route``.

Mode vocabulary is the orchestrator set ``quick|standard|full|specialist``,
aligned with ``BUDGET_MODES`` minus the Chat budget profile. Invalid explicit
overrides fail closed; they never silently map to ``standard``. Unknown mapping
keys and contradictory classification facts also fail closed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from src.agent.runtime.mode_budget import BUDGET_MODES

# Orchestrator depth modes (BUDGET_MODES without the Chat budget profile).
ROUTER_MODES: Tuple[str, ...] = tuple(mode for mode in BUDGET_MODES if mode != "chat")
CHAT_PATHS: Tuple[str, ...] = ("incremental_tool", "full_repipeline")
ENTRY_KINDS: Tuple[str, ...] = ("run", "chat")
INTENT_CATEGORIES: Tuple[str, ...] = (
    "simple",
    "technical",
    "news",
    "risk",
    "compare",
    "analysis",
    "unknown",
)
QUICK_ELIGIBLE_INTENTS = frozenset({"simple"})
COMPARE_INTENTS = frozenset({"compare"})
RISK_INTENTS = frozenset({"risk"})
NEWS_INTENTS = frozenset({"news"})
# Deprecated orchestrator aliases; canonical output remains specialist.
OVERRIDE_ALIASES = {"strategy": "specialist", "skill": "specialist"}

MISS_RATE_MIN = 0.0
MISS_RATE_MAX = 1.0

REASON_EXPLICIT_OVERRIDE = "explicit_override"
REASON_DEFAULT_STANDARD = "default_standard"
REASON_QUICK_ELIGIBLE = "quick_eligible"
REASON_FLOOR_NEED_RISK = "floor_need_risk"
REASON_FLOOR_COMPARE = "floor_compare"
REASON_FLOOR_MULTI_SYMBOL = "floor_multi_symbol"
REASON_FLOOR_NEED_NEWS = "floor_need_news"
REASON_INVALID_OVERRIDE = "invalid_override"
REASON_INVALID_INTENT = "invalid_intent"
REASON_INVALID_SYMBOL_COUNT = "invalid_symbol_count"
REASON_INVALID_FLAG = "invalid_flag"
REASON_INVALID_ENTRY_KIND = "invalid_entry_kind"
REASON_INVALID_MISS_RATE = "invalid_miss_rate"
REASON_INVALID_REQUEST = "invalid_request"
REASON_UNKNOWN_FIELD = "unknown_field"
REASON_INCONSISTENT_FACTS = "inconsistent_facts"

_ERROR_MESSAGES = {
    REASON_INVALID_OVERRIDE: "Explicit mode override is not a valid router mode.",
    REASON_INVALID_INTENT: "intent_category is not a supported classification value.",
    REASON_INVALID_SYMBOL_COUNT: "symbol_count must be a non-negative integer.",
    REASON_INVALID_FLAG: "Boolean classification facts must be strict booleans.",
    REASON_INVALID_ENTRY_KIND: "entry_kind must be run or chat.",
    REASON_INVALID_MISS_RATE: "Miss-rate evidence must be a finite number in [0.0, 1.0].",
    REASON_INVALID_REQUEST: "Router request must be a mapping or AgentRouterRequest.",
    REASON_UNKNOWN_FIELD: "Request contains unknown classification fields.",
    REASON_INCONSISTENT_FACTS: "Classification facts contradict the depth or chat-path contract.",
}

_REQUIRED_FIELDS = (
    "intent_category",
    "symbol_count",
    "need_news",
    "need_risk",
    "entry_kind",
)
_OPTIONAL_BOOL_FIELDS = ("is_follow_up", "same_symbol", "tool_suitable")
_BOOL_FIELDS = ("need_news", "need_risk") + _OPTIONAL_BOOL_FIELDS
_REQUEST_FIELDS = _REQUIRED_FIELDS + _OPTIONAL_BOOL_FIELDS + (
    "user_mode_override",
    "miss_rate",
)
_REQUEST_FIELD_SET = frozenset(_REQUEST_FIELDS)
_EXPLAIN_KEYS = (
    "accepted",
    "intent_category",
    "symbol_count",
    "need_news",
    "need_risk",
    "entry_kind",
    "is_follow_up",
    "same_symbol",
    "tool_suitable",
    "override_present",
    "override_valid",
    "override_mode",
    "quick_eligible",
    "mode_floor",
    "miss_rate_present",
    "miss_rate_applied",
    "chosen_mode",
    "chosen_chat_path",
    "error_field",
)

MODE_FLOOR_NONE = "none"
MODE_FLOOR_STANDARD = "standard"
MODE_FLOOR_FULL = "full"


@dataclass(frozen=True)
class AgentRouterRequest:
    """Bounded classification facts. Callers must normalize upstream inputs."""

    intent_category: str
    symbol_count: int
    need_news: bool
    need_risk: bool
    entry_kind: str
    is_follow_up: bool = False
    same_symbol: bool = False
    tool_suitable: bool = False
    user_mode_override: Optional[str] = None
    miss_rate: Optional[float] = None


@dataclass(frozen=True)
class AgentRouterDecision:
    """Immutable router decision. Rejected decisions never invent a mode."""

    accepted: bool
    mode: Optional[str]
    chat_path: Optional[str]
    reason_code: str
    error: Optional[str] = None
    explain: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accepted": self.accepted,
            "mode": self.mode,
            "chat_path": self.chat_path,
            "reason_code": self.reason_code,
            "error": self.error,
            "explain": dict(self.explain),
        }


def normalize_router_mode(value: Any) -> Optional[str]:
    """Return a canonical router mode, or None when the value is not a valid override.

    Unlike ``normalize_budget_mode``, unknown values are not mapped to standard.
    Blank strings are invalid. Deprecated aliases ``strategy`` / ``skill``
    normalize to ``specialist``.
    """
    if not isinstance(value, str):
        return None
    raw = value.strip().lower()
    if not raw:
        return None
    if raw in OVERRIDE_ALIASES:
        return OVERRIDE_ALIASES[raw]
    if raw in ROUTER_MODES:
        return raw
    return None


class AgentRouter:
    """Deterministic rules-first depth and chat-path classifier."""

    def route(
        self, request: Union[AgentRouterRequest, Mapping[str, Any]]
    ) -> AgentRouterDecision:
        parsed, error = _parse_request(request)
        if error is not None:
            return error
        assert parsed is not None
        return _classify(parsed)


def route(request: Union[AgentRouterRequest, Mapping[str, Any]]) -> AgentRouterDecision:
    """Classify a single request using a stateless router instance."""
    return AgentRouter().route(request)


def _parse_request(
    request: Union[AgentRouterRequest, Mapping[str, Any]]
) -> Tuple[Optional[Dict[str, Any]], Optional[AgentRouterDecision]]:
    raw, project_error = _project_request(request)
    if project_error is not None:
        return None, project_error
    assert raw is not None

    intent, err = _parse_intent(raw.get("intent_category", _MISSING))
    if err is not None:
        return None, err
    symbol_count, err = _parse_symbol_count(raw.get("symbol_count", _MISSING))
    if err is not None:
        return None, err

    flags: Dict[str, bool] = {}
    for name in _BOOL_FIELDS:
        if name in _OPTIONAL_BOOL_FIELDS and name not in raw:
            flags[name] = False
            continue
        value, err = _parse_strict_bool(raw.get(name, _MISSING), name)
        if err is not None:
            return None, err
        flags[name] = bool(value)

    entry_kind, err = _parse_entry_kind(raw.get("entry_kind", _MISSING))
    if err is not None:
        return None, err

    override_present = "user_mode_override" in raw and raw["user_mode_override"] is not None
    override_mode = None
    if override_present:
        override_mode = normalize_router_mode(raw["user_mode_override"])
        if override_mode is None:
            return None, _reject(
                REASON_INVALID_OVERRIDE,
                error_field="user_mode_override",
                intent_category=intent,
                symbol_count=symbol_count,
                entry_kind=entry_kind,
                **flags,
                override_present=True,
                override_valid=False,
            )

    miss_rate_present = "miss_rate" in raw and raw["miss_rate"] is not None
    if miss_rate_present:
        _, err = _parse_miss_rate(raw["miss_rate"])
        if err is not None:
            return None, err

    parsed = {
        "intent_category": intent,
        "symbol_count": symbol_count,
        "entry_kind": entry_kind,
        "override_present": override_present,
        "override_mode": override_mode,
        "miss_rate_present": miss_rate_present,
        **flags,
    }
    inconsistent = _consistency_error(parsed)
    if inconsistent is not None:
        return None, inconsistent
    return parsed, None


class _Missing:
    pass


_MISSING = _Missing()


def _project_request(
    request: Any,
) -> Tuple[Optional[Dict[str, Any]], Optional[AgentRouterDecision]]:
    if isinstance(request, AgentRouterRequest):
        return {item.name: getattr(request, item.name) for item in fields(request)}, None
    if isinstance(request, Mapping):
        if any(key not in _REQUEST_FIELD_SET for key in request):
            return None, _reject(REASON_UNKNOWN_FIELD, error_field="request")
        return {key: request[key] for key in _REQUEST_FIELDS if key in request}, None
    return None, _reject(REASON_INVALID_REQUEST, error_field="request")


def _parse_intent(value: Any) -> Tuple[Optional[str], Optional[AgentRouterDecision]]:
    if not isinstance(value, str):
        return None, _reject(REASON_INVALID_INTENT, error_field="intent_category")
    normalized = value.strip().lower()
    if normalized not in INTENT_CATEGORIES:
        return None, _reject(REASON_INVALID_INTENT, error_field="intent_category")
    return normalized, None


def _parse_symbol_count(value: Any) -> Tuple[Optional[int], Optional[AgentRouterDecision]]:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None, _reject(REASON_INVALID_SYMBOL_COUNT, error_field="symbol_count")
    return int(value), None


def _parse_strict_bool(
    value: Any, field_name: str
) -> Tuple[Optional[bool], Optional[AgentRouterDecision]]:
    if type(value) is not bool:
        return None, _reject(REASON_INVALID_FLAG, error_field=field_name)
    return value, None


def _parse_entry_kind(value: Any) -> Tuple[Optional[str], Optional[AgentRouterDecision]]:
    if not isinstance(value, str):
        return None, _reject(REASON_INVALID_ENTRY_KIND, error_field="entry_kind")
    normalized = value.strip().lower()
    if normalized not in ENTRY_KINDS:
        return None, _reject(REASON_INVALID_ENTRY_KIND, error_field="entry_kind")
    return normalized, None


def _parse_miss_rate(value: Any) -> Tuple[Optional[float], Optional[AgentRouterDecision]]:
    # bool is a subclass of int; reject it before numeric coercion.
    if type(value) is bool or isinstance(value, str):
        return None, _reject(REASON_INVALID_MISS_RATE, error_field="miss_rate")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number) or number < MISS_RATE_MIN or number > MISS_RATE_MAX:
            return None, _reject(REASON_INVALID_MISS_RATE, error_field="miss_rate")
        return number, None
    return None, _reject(REASON_INVALID_MISS_RATE, error_field="miss_rate")


def _consistency_error(parsed: Mapping[str, Any]) -> Optional[AgentRouterDecision]:
    """Reject combinations that cannot be a normalized classification payload."""
    intent = str(parsed["intent_category"])
    need_news = bool(parsed["need_news"])
    need_risk = bool(parsed["need_risk"])
    symbol_count = int(parsed["symbol_count"])
    entry_kind = str(parsed["entry_kind"])
    is_follow_up = bool(parsed["is_follow_up"])
    same_symbol = bool(parsed["same_symbol"])
    tool_suitable = bool(parsed["tool_suitable"])
    common = {
        "intent_category": intent,
        "symbol_count": symbol_count,
        "need_news": need_news,
        "need_risk": need_risk,
        "entry_kind": entry_kind,
        "is_follow_up": is_follow_up,
        "same_symbol": same_symbol,
        "tool_suitable": tool_suitable,
        "override_present": bool(parsed["override_present"]),
        "miss_rate_present": bool(parsed["miss_rate_present"]),
    }
    if intent in RISK_INTENTS and not need_risk:
        return _reject(REASON_INCONSISTENT_FACTS, error_field="need_risk", **common)
    if intent in NEWS_INTENTS and not need_news:
        return _reject(REASON_INCONSISTENT_FACTS, error_field="need_news", **common)
    if intent in QUICK_ELIGIBLE_INTENTS and (
        need_news or need_risk or symbol_count != 1
    ):
        error_field = "symbol_count" if symbol_count != 1 else (
            "need_risk" if need_risk else "need_news"
        )
        return _reject(REASON_INCONSISTENT_FACTS, error_field=error_field, **common)
    if entry_kind == "run" and (is_follow_up or same_symbol or tool_suitable):
        return _reject(REASON_INCONSISTENT_FACTS, error_field="entry_kind", **common)
    if same_symbol and not is_follow_up:
        return _reject(REASON_INCONSISTENT_FACTS, error_field="same_symbol", **common)
    return None


def _classify(parsed: Mapping[str, Any]) -> AgentRouterDecision:
    intent = str(parsed["intent_category"])
    symbol_count = int(parsed["symbol_count"])
    need_news = bool(parsed["need_news"])
    need_risk = bool(parsed["need_risk"])
    entry_kind = str(parsed["entry_kind"])
    is_follow_up = bool(parsed["is_follow_up"])
    same_symbol = bool(parsed["same_symbol"])
    tool_suitable = bool(parsed["tool_suitable"])
    override_present = bool(parsed["override_present"])
    override_mode = parsed["override_mode"]
    miss_rate_present = bool(parsed["miss_rate_present"])

    mode_floor = _mode_floor(intent, symbol_count, need_news, need_risk)
    quick_eligible = _is_quick_eligible(intent, symbol_count, need_news, need_risk)

    if override_present:
        mode = str(override_mode)
        reason_code = REASON_EXPLICIT_OVERRIDE
    elif mode_floor == MODE_FLOOR_FULL:
        mode = "full"
        reason_code = _full_floor_reason(intent, need_risk)
    elif mode_floor == MODE_FLOOR_STANDARD:
        mode = "standard"
        reason_code = REASON_FLOOR_NEED_NEWS
    elif quick_eligible:
        mode = "quick"
        reason_code = REASON_QUICK_ELIGIBLE
    else:
        mode = "standard"
        reason_code = REASON_DEFAULT_STANDARD

    chat_path = _chat_path(
        entry_kind=entry_kind,
        is_follow_up=is_follow_up,
        same_symbol=same_symbol,
        need_news=need_news,
        need_risk=need_risk,
        tool_suitable=tool_suitable,
        mode=mode,
    )
    explain = _explain(
        accepted=True,
        intent_category=intent,
        symbol_count=symbol_count,
        need_news=need_news,
        need_risk=need_risk,
        entry_kind=entry_kind,
        is_follow_up=is_follow_up,
        same_symbol=same_symbol,
        tool_suitable=tool_suitable,
        override_present=override_present,
        override_valid=override_present,
        override_mode=override_mode if override_present else None,
        quick_eligible=quick_eligible,
        mode_floor=mode_floor,
        miss_rate_present=miss_rate_present,
        miss_rate_applied=False,
        chosen_mode=mode,
        chosen_chat_path=chat_path,
    )
    return AgentRouterDecision(
        accepted=True,
        mode=mode,
        chat_path=chat_path,
        reason_code=reason_code,
        error=None,
        explain=explain,
    )


def _mode_floor(intent: str, symbol_count: int, need_news: bool, need_risk: bool) -> str:
    if (
        need_risk
        or intent in RISK_INTENTS
        or intent in COMPARE_INTENTS
        or symbol_count >= 2
    ):
        return MODE_FLOOR_FULL
    if need_news or intent in NEWS_INTENTS:
        return MODE_FLOOR_STANDARD
    return MODE_FLOOR_NONE


def _full_floor_reason(intent: str, need_risk: bool) -> str:
    if need_risk or intent in RISK_INTENTS:
        return REASON_FLOOR_NEED_RISK
    if intent in COMPARE_INTENTS:
        return REASON_FLOOR_COMPARE
    return REASON_FLOOR_MULTI_SYMBOL


def _is_quick_eligible(
    intent: str, symbol_count: int, need_news: bool, need_risk: bool
) -> bool:
    return (
        intent in QUICK_ELIGIBLE_INTENTS
        and symbol_count == 1
        and not need_news
        and not need_risk
    )


def _chat_path(
    *,
    entry_kind: str,
    is_follow_up: bool,
    same_symbol: bool,
    need_news: bool,
    need_risk: bool,
    tool_suitable: bool,
    mode: str,
) -> str:
    if entry_kind != "chat":
        return "full_repipeline"
    if mode in {"full", "specialist"}:
        return "full_repipeline"
    if (
        is_follow_up
        and same_symbol
        and not need_news
        and not need_risk
        and tool_suitable
    ):
        return "incremental_tool"
    return "full_repipeline"


def _reject(reason_code: str, **explain_fields: Any) -> AgentRouterDecision:
    payload = dict(explain_fields)
    payload["accepted"] = False
    payload.setdefault("override_present", False)
    payload.setdefault("override_valid", False)
    payload.setdefault("miss_rate_present", False)
    payload.setdefault("miss_rate_applied", False)
    payload["chosen_mode"] = None
    payload["chosen_chat_path"] = None
    return AgentRouterDecision(
        accepted=False,
        mode=None,
        chat_path=None,
        reason_code=reason_code,
        error=_ERROR_MESSAGES[reason_code],
        explain=_explain(**payload),
    )


def _explain(**fields: Any) -> Mapping[str, Any]:
    payload: Dict[str, Any] = {}
    for key in _EXPLAIN_KEYS:
        if key not in fields:
            continue
        value = fields[key]
        if value is None and key in {"override_mode", "error_field", "chosen_mode", "chosen_chat_path"}:
            payload[key] = None
            continue
        if value is None:
            continue
        payload[key] = value
    return MappingProxyType(payload)


__all__ = [
    "CHAT_PATHS",
    "COMPARE_INTENTS",
    "ENTRY_KINDS",
    "INTENT_CATEGORIES",
    "MISS_RATE_MAX",
    "MISS_RATE_MIN",
    "NEWS_INTENTS",
    "OVERRIDE_ALIASES",
    "QUICK_ELIGIBLE_INTENTS",
    "REASON_DEFAULT_STANDARD",
    "REASON_EXPLICIT_OVERRIDE",
    "REASON_FLOOR_COMPARE",
    "REASON_FLOOR_MULTI_SYMBOL",
    "REASON_FLOOR_NEED_NEWS",
    "REASON_FLOOR_NEED_RISK",
    "REASON_INCONSISTENT_FACTS",
    "REASON_INVALID_ENTRY_KIND",
    "REASON_INVALID_FLAG",
    "REASON_INVALID_INTENT",
    "REASON_INVALID_MISS_RATE",
    "REASON_INVALID_OVERRIDE",
    "REASON_INVALID_REQUEST",
    "REASON_INVALID_SYMBOL_COUNT",
    "REASON_QUICK_ELIGIBLE",
    "REASON_UNKNOWN_FIELD",
    "RISK_INTENTS",
    "ROUTER_MODES",
    "AgentRouter",
    "AgentRouterDecision",
    "AgentRouterRequest",
    "normalize_router_mode",
    "route",
]
