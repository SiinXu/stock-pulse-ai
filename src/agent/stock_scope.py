# -*- coding: utf-8 -*-
"""Stock-scope helpers for ask-stock follow-up chat turns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from src.services.stock_code_utils import canonicalize_analysis_stock_code


SWITCH_CLEANUP_KEYS = {
    "stock_name",
    "previous_analysis_summary",
    "previous_strategy",
    "previous_price",
    "previous_change_pct",
    "realtime_quote",
    "daily_history",
    "chip_distribution",
    "trend_result",
    "news_context",
    "fundamental_context",
    "market_structure_context",
    "analysis_context_pack_summary",
    "market_phase_context",
}

_STRONG_COMPARE_PATTERN = re.compile(r"比较|对比|vs\b|和[^，。,.!?！？]{0,40}比", re.IGNORECASE)
_WEAK_COMPARE_HINT_PATTERN = re.compile(r"差异(?!化)|区别|不同|相比|对照|比一比")
_CHOICE_COMPARE_PATTERN = re.compile(r"哪个|哪只|哪一个|谁更|更值得|更适合|怎么选|选哪|二选一")
_LINKED_COMPARE_PATTERN = re.compile(
    r"(?:和|与|跟|同)(?P<body>[^，。,.!?！？]{0,40})(?:差异(?!化)|区别|不同|相比|对照|比一比)"
)
_SWITCH_PATTERN = re.compile(
    r"换成|改看|分析|看看|研究|诊断|\b(?:analy[sz]e|switch(?:\s+to)?|look\s+at|review)\b",
    re.IGNORECASE,
)
_LOWERCASE_SCAN_HINT_PATTERN = re.compile(r"换成|改看|分析|看看|研究|诊断")
_ENGLISH_SWITCH_TICKER_PATTERN = re.compile(
    r"\b(?:analy[sz]e|switch\s+to|switch|look\s+at|review)\s+"
    r"([a-z]{1,5}(?:\.[a-z]{1,2})?)\b",
    re.IGNORECASE,
)
_EXPLICIT_COMPARE_PAIR_PATTERN = re.compile(
    r"(?<![a-zA-Z.])([a-z]{1,5}(?:\.[a-z]{1,2})?)\s*"
    r"(?:vs\.?|versus|和|与|跟)\s*"
    r"([a-z]{1,5}(?:\.[a-z]{1,2})?)(?![a-zA-Z0-9])",
    re.IGNORECASE,
)
_LOWERCASE_TICKER_PATTERN = re.compile(r"(?<![a-zA-Z.])([a-z]{1,5}(?:\.[a-z]{1,2})?)(?![a-zA-Z0-9])")
_EXCHANGE_TOKEN_CANDIDATES = {"SH", "SZ", "BJ", "HK", "SS"}
_COMPARISON_TOKEN_CANDIDATES = {"VS"}
_ALWAYS_DENIED_TICKER_CANDIDATES = {
    "BOLL",
    "EMA",
    "KDJ",
    "MACD",
    "RSI",
    "SMA",
    "VWAP",
}
_CONTEXTUAL_INDICATOR_TOKENS = {"MA"}
_INDICATOR_CONTEXT_PATTERN = re.compile(
    r"指标|均线|移动平均|排列|多头|空头|金叉|死叉|支撑|压力|MA\d|SMA|EMA",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StockScope:
    """Runtime stock-scope contract for one chat turn."""

    expected_stock_code: str = ""
    allowed_stock_codes: Set[str] = field(default_factory=set)
    mode: str = "maintain"

    def as_log_payload(self) -> Dict[str, Any]:
        return {
            "expected_stock_code": self.expected_stock_code,
            "allowed_stock_codes": sorted(self.allowed_stock_codes),
            "mode": self.mode,
        }


@dataclass(frozen=True)
class StockScopeResolution:
    """Result produced before a chat turn enters the agent loop."""

    effective_context: Dict[str, Any]
    stock_scope: Optional[StockScope]


def _normalize_stock_code(value: Any) -> str:
    """Normalize a code with the shared analysis canonicalizer."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    return canonicalize_analysis_stock_code(text) or ""


def _is_denied_candidate(
    candidate: str,
    text: str = "",
    *,
    allow_common_word: bool = False,
) -> bool:
    token = candidate.strip().upper()
    if (
        token in _EXCHANGE_TOKEN_CANDIDATES
        or token in _COMPARISON_TOKEN_CANDIDATES
        or token in _ALWAYS_DENIED_TICKER_CANDIDATES
    ):
        return True
    if token in _CONTEXTUAL_INDICATOR_TOKENS and _INDICATOR_CONTEXT_PATTERN.search(text or ""):
        return True
    if allow_common_word:
        return False
    try:
        from src.agent.orchestrator import _COMMON_WORDS

        return token in _COMMON_WORDS
    except (ImportError, AttributeError):
        return False


def _append_candidate(
    candidates: List[str],
    candidate: str,
    text: str = "",
    *,
    explicit: bool = False,
) -> None:
    normalized = _normalize_stock_code(candidate)
    if not normalized or _is_denied_candidate(
        normalized,
        text,
        allow_common_word=explicit,
    ):
        return
    if normalized not in candidates:
        candidates.append(normalized)


def extract_stock_codes(text: str) -> List[str]:
    """Extract all explicit stock-code candidates from free text."""
    if not text:
        return []

    candidates: List[str] = []

    for pattern, flags in (
        (r"(?<![a-zA-Z])(?:SH|SZ|BJ)\d{6}(?!\d)", re.IGNORECASE),
        (r"(?<![a-zA-Z])hk\d{4,5}(?!\d)", re.IGNORECASE),
        (r"(?<![a-zA-Z])\d{1,5}\.HK(?![a-zA-Z])", re.IGNORECASE),
        (
            r"(?<![a-zA-Z0-9.])\d{4,6}\.(?:T|KS|KQ|TW|TWO)(?![a-zA-Z0-9])",
            re.IGNORECASE,
        ),
        (r"(?<!\d)(?:[03648]\d{5}|92\d{4})(?!\d)", 0),
        (r"(?<!\d)\d{5}(?!\d)", 0),
        (r"(?<![a-zA-Z.])([A-Z]{2,5}(?:\.[A-Z]{1,2})?)(?![a-zA-Z0-9])", 0),
    ):
        for match in re.finditer(pattern, text, flags):
            raw = match.group(1) if match.lastindex else match.group(0)
            _append_candidate(candidates, raw, text)

    for match in _ENGLISH_SWITCH_TICKER_PATTERN.finditer(text):
        _append_candidate(candidates, match.group(1), text, explicit=True)

    for match in _EXPLICIT_COMPARE_PAIR_PATTERN.finditer(text):
        for raw in match.groups():
            _append_candidate(
                candidates,
                raw,
                text,
                explicit=raw.isupper(),
            )

    bare_lowercase_ticker = re.fullmatch(
        r"[a-z]{1,5}(?:\.[a-z]{1,2})?",
        text.strip(),
    )
    bare_uppercase_ticker = re.fullmatch(
        r"[A-Z]{1,5}(?:\.[A-Z]{1,2})?",
        text.strip(),
    )
    if bare_uppercase_ticker:
        _append_candidate(
            candidates,
            bare_uppercase_ticker.group(0),
            text,
            explicit=True,
        )
    if (
        _LOWERCASE_SCAN_HINT_PATTERN.search(text)
        or _STRONG_COMPARE_PATTERN.search(text)
        or _WEAK_COMPARE_HINT_PATTERN.search(text)
        or _CHOICE_COMPARE_PATTERN.search(text)
        or bare_lowercase_ticker
    ):
        for match in _LOWERCASE_TICKER_PATTERN.finditer(text):
            _append_candidate(candidates, match.group(1), text)

    return candidates


def _is_compare_message(message: str, candidates: List[str], current_code: str) -> bool:
    if _STRONG_COMPARE_PATTERN.search(message):
        return True
    new_candidates = {code for code in candidates if code != current_code}
    if len(new_candidates) >= 2:
        return True
    if _CHOICE_COMPARE_PATTERN.search(message) and len(candidates) >= 2:
        return True
    if not _WEAK_COMPARE_HINT_PATTERN.search(message):
        return False
    if len(candidates) >= 2:
        return True

    if not new_candidates:
        return False

    for match in _LINKED_COMPARE_PATTERN.finditer(message):
        body_candidates = set(extract_stock_codes(f"比较 {match.group('body')}"))
        if body_candidates & new_candidates:
            return True
    return False


def _with_skills(context: Dict[str, Any], skills: Optional[Iterable[str]]) -> Dict[str, Any]:
    if skills is None:
        return context
    next_context = dict(context)
    next_context["skills"] = list(skills)
    return next_context


def _switch_context(context: Dict[str, Any], stock_code: str) -> Dict[str, Any]:
    next_context = {
        key: value
        for key, value in context.items()
        if key not in SWITCH_CLEANUP_KEYS and key != "allowed_stock_codes"
    }
    next_context["stock_code"] = stock_code
    next_context["stock_name"] = ""
    return next_context


def _clear_stock_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Remove fields tied to a prior single-stock analysis."""
    return {
        key: value
        for key, value in context.items()
        if key not in SWITCH_CLEANUP_KEYS
        and key not in {"stock_code", "allowed_stock_codes"}
    }


def resolve_stock_scope(
    message: str,
    context: Optional[Dict[str, Any]],
    *,
    skills: Optional[Iterable[str]] = None,
) -> StockScopeResolution:
    """Resolve the effective context and stock tool scope for one chat turn."""
    original_context = dict(context or {})
    message_text = message or ""
    current_code = _normalize_stock_code(original_context.get("stock_code"))
    invalid_context_code = bool(
        current_code
        and _is_denied_candidate(
            current_code,
            message_text,
            allow_common_word=True,
        )
    )
    original_context.pop("allowed_stock_codes", None)
    if invalid_context_code:
        original_context.pop("stock_code", None)
        original_context.pop("stock_name", None)
        current_code = ""

    if not current_code:
        candidates = extract_stock_codes(message_text)
        if candidates:
            allowed = set(candidates)
            expected = candidates[0] if len(candidates) == 1 else ""
            effective_context = dict(original_context)
            mode = "switch" if expected else "compare"
            if expected:
                effective_context["stock_code"] = expected
                effective_context["stock_name"] = ""
            return StockScopeResolution(
                effective_context=_with_skills(effective_context, skills),
                stock_scope=StockScope(
                    expected_stock_code=expected,
                    allowed_stock_codes=allowed,
                    mode=mode,
                ),
            )
        if invalid_context_code:
            return StockScopeResolution(
                effective_context=_with_skills(original_context, skills),
                stock_scope=StockScope(),
            )
        return StockScopeResolution(
            effective_context=_with_skills(original_context, skills),
            stock_scope=None,
        )

    candidates = extract_stock_codes(message_text)
    new_candidates = [code for code in candidates if code != current_code]
    mode = "maintain"
    effective_context = dict(original_context)
    expected = current_code
    allowed = {current_code}

    if _is_compare_message(message_text, candidates, current_code):
        mode = "compare"
        explicit_codes = set(candidates)
        if len(explicit_codes) >= 2:
            allowed = explicit_codes
            if current_code not in allowed:
                effective_context = _clear_stock_context(original_context)
        else:
            allowed.update(explicit_codes)
        expected = ""
    elif _SWITCH_PATTERN.search(message_text) and len(new_candidates) == 1:
        mode = "switch"
        expected = new_candidates[0]
        allowed = {expected}
        effective_context = _switch_context(original_context, expected)

    if mode == "switch":
        effective_context["stock_code"] = expected
    elif mode == "maintain" or current_code in allowed:
        effective_context["stock_code"] = current_code
    else:
        effective_context.pop("stock_code", None)
        effective_context.pop("stock_name", None)
    effective_context = _with_skills(effective_context, skills)

    return StockScopeResolution(
        effective_context=effective_context,
        stock_scope=StockScope(
            expected_stock_code=expected,
            allowed_stock_codes=allowed,
            mode=mode,
        ),
    )
