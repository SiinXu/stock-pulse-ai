# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Project AgentRouterRequest from already-structured runtime facts.

Library slice for issue #1120. Callers supply StockScope-like mode / codes,
entry kind, and an optional explicit per-run override. This module never
parses prompts, messages, provider payloads, or tool catalogs, never reads
config / env / Settings, and never calls ``AgentRouter.route()``.

Production orchestrator / factory / Chat / API callers are out of scope.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Optional, Tuple

from src.agent.runtime.agent_router import (
    ENTRY_KINDS,
    INTENT_CATEGORIES,
    NEWS_INTENTS,
    QUICK_ELIGIBLE_INTENTS,
    REASON_INCONSISTENT_FACTS,
    REASON_INVALID_ENTRY_KIND,
    REASON_INVALID_FLAG,
    REASON_INVALID_INTENT,
    REASON_INVALID_OVERRIDE,
    REASON_INVALID_REQUEST,
    REASON_UNKNOWN_FIELD,
    RISK_INTENTS,
    AgentRouterRequest,
)

SCOPE_MODES: Tuple[str, ...] = ("maintain", "compare", "switch")
REASON_INVALID_SCOPE_MODE = "invalid_scope_mode"
REASON_INVALID_SYMBOL_CODES = "invalid_symbol_codes"

_FACT_FIELDS = frozenset(
    {
        "entry_kind",
        "scope_mode",
        "allowed_stock_codes",
        "symbol_codes",
        "expected_stock_code",
        "user_mode_override",
        "intent_category",
        "need_news",
        "need_risk",
        "tool_suitable",
    }
)
_ERROR_MESSAGES = {
    REASON_INVALID_ENTRY_KIND: "entry_kind must be run or chat.",
    REASON_INVALID_INTENT: "intent_category is not a supported classification value.",
    REASON_INVALID_FLAG: "Boolean classification facts must be strict booleans.",
    REASON_INVALID_REQUEST: "Fact payload must be a mapping of structured runtime facts.",
    REASON_UNKNOWN_FIELD: "Request contains unknown classification fields.",
    REASON_INCONSISTENT_FACTS: "Classification facts contradict the depth or chat-path contract.",
    REASON_INVALID_OVERRIDE: "Explicit mode override is not a valid router mode.",
    REASON_INVALID_SCOPE_MODE: "scope_mode must be maintain, compare, or switch.",
    REASON_INVALID_SYMBOL_CODES: "Symbol code collections must be sequences of nonempty strings.",
}


@dataclass(frozen=True)
class RouterFactProjection:
    """Accepted ``AgentRouterRequest`` or a typed reject. Never a routed decision."""

    accepted: bool
    request: Optional[AgentRouterRequest] = None
    reason_code: Optional[str] = None
    error: Optional[str] = None
    error_field: Optional[str] = None


def project_router_request(facts: Any) -> RouterFactProjection:
    """Project structured runtime facts into a legal ``AgentRouterRequest``.

    Unknown mapping keys fail closed without echoing names or values.
    Omitted optional flags stay false. Omitted intent becomes ``compare``
    when ``scope_mode`` is compare, otherwise ``unknown`` — never ``simple``.
    """
    if not isinstance(facts, Mapping):
        return _reject(REASON_INVALID_REQUEST, error_field="request")
    if any(key not in _FACT_FIELDS for key in facts):
        return _reject(REASON_UNKNOWN_FIELD, error_field="request")

    entry_kind, err = _parse_entry_kind(facts.get("entry_kind", _MISSING))
    if err is not None:
        return err

    scope_present = "scope_mode" in facts and facts["scope_mode"] is not None
    scope_mode = None
    if scope_present:
        scope_mode, err = _parse_scope_mode(facts["scope_mode"])
        if err is not None:
            return err

    allowed, err = _parse_code_collection(
        facts["allowed_stock_codes"] if "allowed_stock_codes" in facts else _MISSING,
        "allowed_stock_codes",
    )
    if err is not None:
        return err
    symbols, err = _parse_code_collection(
        facts["symbol_codes"] if "symbol_codes" in facts else _MISSING,
        "symbol_codes",
    )
    if err is not None:
        return err
    symbol_count = len(allowed) if allowed else len(symbols)

    expected, err = _parse_optional_code(
        facts.get("expected_stock_code", _MISSING), "expected_stock_code"
    )
    if err is not None:
        return err

    need_news, err = _parse_optional_bool(facts, "need_news")
    if err is not None:
        return err
    need_risk, err = _parse_optional_bool(facts, "need_risk")
    if err is not None:
        return err
    tool_suitable, err = _parse_optional_bool(facts, "tool_suitable")
    if err is not None:
        return err

    intent, err = _parse_optional_intent(
        facts.get("intent_category", _MISSING), scope_mode
    )
    if err is not None:
        return err

    override_present = (
        "user_mode_override" in facts and facts["user_mode_override"] is not None
    )
    override = None
    if override_present:
        override, err = _parse_override(facts["user_mode_override"])
        if err is not None:
            return err

    is_follow_up, same_symbol = _chat_scope_flags(
        entry_kind=entry_kind,
        scope_mode=scope_mode,
        expected_stock_code=expected,
    )
    if entry_kind == "run":
        is_follow_up = False
        same_symbol = False

    inconsistent = _consistency_error(
        intent=intent,
        symbol_count=symbol_count,
        need_news=need_news,
        need_risk=need_risk,
        entry_kind=entry_kind,
        is_follow_up=is_follow_up,
        same_symbol=same_symbol,
        tool_suitable=tool_suitable,
    )
    if inconsistent is not None:
        return inconsistent

    request = AgentRouterRequest(
        intent_category=intent,
        symbol_count=symbol_count,
        need_news=need_news,
        need_risk=need_risk,
        entry_kind=entry_kind,
        is_follow_up=is_follow_up,
        same_symbol=same_symbol,
        tool_suitable=tool_suitable,
        user_mode_override=override,
    )
    return RouterFactProjection(accepted=True, request=request)


class _Missing:
    pass


_MISSING = _Missing()


def _reject(reason_code: str, error_field: str) -> RouterFactProjection:
    return RouterFactProjection(
        accepted=False,
        request=None,
        reason_code=reason_code,
        error=_ERROR_MESSAGES[reason_code],
        error_field=error_field,
    )


def _parse_entry_kind(value: Any) -> Tuple[Optional[str], Optional[RouterFactProjection]]:
    if isinstance(value, _Missing) or not isinstance(value, str):
        return None, _reject(REASON_INVALID_ENTRY_KIND, error_field="entry_kind")
    normalized = value.strip().lower()
    if normalized not in ENTRY_KINDS:
        return None, _reject(REASON_INVALID_ENTRY_KIND, error_field="entry_kind")
    return normalized, None


def _parse_scope_mode(value: Any) -> Tuple[Optional[str], Optional[RouterFactProjection]]:
    if not isinstance(value, str):
        return None, _reject(REASON_INVALID_SCOPE_MODE, error_field="scope_mode")
    normalized = value.strip().lower()
    if normalized not in SCOPE_MODES:
        return None, _reject(REASON_INVALID_SCOPE_MODE, error_field="scope_mode")
    return normalized, None


def _parse_code_collection(
    value: Any, field_name: str
) -> Tuple[Tuple[str, ...], Optional[RouterFactProjection]]:
    if isinstance(value, _Missing):
        return (), None
    if value is None:
        return (), None
    if isinstance(value, (str, bytes, bytearray, Mapping)):
        return (), _reject(REASON_INVALID_SYMBOL_CODES, error_field=field_name)
    if not isinstance(value, Iterable):
        return (), _reject(REASON_INVALID_SYMBOL_CODES, error_field=field_name)
    items = tuple(value)
    if any(type(item) is not str or item == "" for item in items):
        return (), _reject(REASON_INVALID_SYMBOL_CODES, error_field=field_name)
    return items, None


def _parse_optional_code(
    value: Any, field_name: str
) -> Tuple[str, Optional[RouterFactProjection]]:
    if isinstance(value, _Missing) or value is None:
        return "", None
    if type(value) is not str:
        return "", _reject(REASON_INVALID_SYMBOL_CODES, error_field=field_name)
    return value, None


def _parse_optional_bool(
    facts: Mapping[str, Any], field_name: str
) -> Tuple[bool, Optional[RouterFactProjection]]:
    if field_name not in facts:
        return False, None
    value = facts[field_name]
    if type(value) is not bool:
        return False, _reject(REASON_INVALID_FLAG, error_field=field_name)
    return value, None


def _parse_optional_intent(
    value: Any, scope_mode: Optional[str]
) -> Tuple[Optional[str], Optional[RouterFactProjection]]:
    if isinstance(value, _Missing) or value is None:
        if scope_mode == "compare":
            return "compare", None
        return "unknown", None
    if not isinstance(value, str):
        return None, _reject(REASON_INVALID_INTENT, error_field="intent_category")
    normalized = value.strip().lower()
    if normalized not in INTENT_CATEGORIES:
        return None, _reject(REASON_INVALID_INTENT, error_field="intent_category")
    return normalized, None


def _parse_override(value: Any) -> Tuple[Optional[str], Optional[RouterFactProjection]]:
    if not isinstance(value, str):
        return None, _reject(REASON_INVALID_OVERRIDE, error_field="user_mode_override")
    return value, None


def _chat_scope_flags(
    *,
    entry_kind: str,
    scope_mode: Optional[str],
    expected_stock_code: str,
) -> Tuple[bool, bool]:
    if entry_kind != "chat" or scope_mode is None:
        return False, False
    if scope_mode == "maintain":
        return True, bool(expected_stock_code)
    if scope_mode == "switch":
        return True, False
    return False, False


def _consistency_error(
    *,
    intent: str,
    symbol_count: int,
    need_news: bool,
    need_risk: bool,
    entry_kind: str,
    is_follow_up: bool,
    same_symbol: bool,
    tool_suitable: bool,
) -> Optional[RouterFactProjection]:
    if intent in RISK_INTENTS and not need_risk:
        return _reject(REASON_INCONSISTENT_FACTS, error_field="need_risk")
    if intent in NEWS_INTENTS and not need_news:
        return _reject(REASON_INCONSISTENT_FACTS, error_field="need_news")
    if intent in QUICK_ELIGIBLE_INTENTS and (
        need_news or need_risk or symbol_count != 1
    ):
        error_field = "symbol_count" if symbol_count != 1 else (
            "need_risk" if need_risk else "need_news"
        )
        return _reject(REASON_INCONSISTENT_FACTS, error_field=error_field)
    if entry_kind == "run" and (is_follow_up or same_symbol or tool_suitable):
        return _reject(REASON_INCONSISTENT_FACTS, error_field="entry_kind")
    if same_symbol and not is_follow_up:
        return _reject(REASON_INCONSISTENT_FACTS, error_field="same_symbol")
    return None


__all__ = [
    "REASON_INVALID_SCOPE_MODE",
    "REASON_INVALID_SYMBOL_CODES",
    "SCOPE_MODES",
    "RouterFactProjection",
    "project_router_request",
]
