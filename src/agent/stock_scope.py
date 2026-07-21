# -*- coding: utf-8 -*-
"""Stock-scope helpers for ask-stock follow-up chat turns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from src.data.stock_index_loader import get_stock_name_index_map
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
    "daily_market_context",
}

_STRONG_COMPARE_PATTERN = re.compile(
    r"比较|对比|和[^，。,.!?！？]{0,40}比"
)
_VS_COMPARE_PATTERN = re.compile(
    r"(?<=\S)\s+(?P<operator>vs\.?|versus)\s+(?=\S)",
    re.IGNORECASE,
)
_ENGLISH_COMPARE_HINT_PATTERN = re.compile(
    r"\bcompar(?:e|ed)\b|\bversus\b",
    re.IGNORECASE,
)
_WEAK_COMPARE_HINT_PATTERN = re.compile(r"差异(?!化)|区别|不同|相比|对照|比一比")
_CHOICE_COMPARE_PATTERN = re.compile(r"哪个|哪只|哪一个|谁更|更值得|更适合|怎么选|选哪|二选一")
_LINKED_COMPARE_PATTERN = re.compile(
    r"(?:和|与|跟|同)(?P<body>[^，。,.!?！？]{0,40})(?:差异(?!化)|区别|不同|相比|对照|比一比)"
)
_SWITCH_PATTERN = re.compile(
    r"换成|改看|分析|看看|研究|诊断|\b(?:analy[sz]e|switch(?:\s+to)?|look\s+at|review)\b",
    re.IGNORECASE,
)
_LOWERCASE_SCAN_HINT_PATTERN = re.compile(
    r"换成|改看|分析|看看|研究|诊断|比较|对比|和[^，。,.!?！？]{0,40}比"
)
_ENGLISH_EXPLICIT_TICKER_PATTERN = re.compile(
    r"(?i:^\s*(?:analy[sz]e|switch(?:\s+to)?|look\s+at|review)\s+)"
    r"([A-Z]{1,5}(?:\.[A-Z]{1,2})?)(?![a-zA-Z0-9.])"
)
_ENGLISH_LOWERCASE_COMMAND_TICKER_PATTERN = re.compile(
    r"(?i:^\s*(?:analy[sz]e|switch(?:\s+to)?|look\s+at|review)\s+)"
    r"([a-z]{1,5}(?:\.[a-z]{1,2})?)(?![a-zA-Z0-9.])"
)
_CJK_EXPLICIT_TICKER_PATTERN = re.compile(
    r"^\s*(?:换成|改看|分析|看看|研究|诊断)\s*"
    r"([A-Z]{1,5}(?:\.[A-Z]{1,2})?)(?![a-zA-Z0-9.])"
)
_EXPLICIT_COMPARE_PAIR_PATTERN = re.compile(
    r"(?<![a-zA-Z.])([a-z]{1,5}(?:\.[a-z]{1,2})?)\s*"
    r"(?:vs\.?|versus|和|与|跟)\s*"
    r"([a-z]{1,5}(?:\.[a-z]{1,2})?)(?![a-zA-Z0-9])",
    re.IGNORECASE,
)
_ENGLISH_AND_COMPARE_PAIR_PATTERN = re.compile(
    r"\bcompare\s+([a-z]{1,5}(?:\.[a-z]{1,2})?)\s+and\s+"
    r"([a-z]{1,5}(?:\.[a-z]{1,2})?)(?![a-zA-Z0-9])",
    re.IGNORECASE,
)
_EXPLICIT_SINGLE_TICKER_COMPARE_PATTERNS = (
    re.compile(
        r"(?<![a-zA-Z.])([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s*"
        r"(?:vs\.?|versus|和|与|跟)"
    ),
    re.compile(
        r"(?:vs\.?|versus|和|与|跟)\s*"
        r"([A-Z]{1,5}(?:\.[A-Z]{1,2})?)(?![a-zA-Z0-9])"
    ),
    re.compile(
        r"(?i:\bcompar(?:e|ed))\s+"
        r"([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\s+"
        r"(?i:and|with)\b"
    ),
    re.compile(
        r"(?i:\bcompar(?:e|ed))\b[^,.!?！？]{0,40}"
        r"(?i:\b(?:and|with))\s+"
        r"([A-Z]{1,5}(?:\.[A-Z]{1,2})?)(?![a-zA-Z0-9])",
    ),
)
_EXPLICIT_LOWERCASE_COMPARE_TICKER_PATTERNS = (
    re.compile(
        r"(?<![a-zA-Z.])([a-z]{1,5}(?:\.[a-z]{1,2})?)\s*"
        r"(?i:vs\.?|versus|和|与|跟)"
    ),
    re.compile(
        r"(?i:vs\.?|versus|和|与|跟)\s*"
        r"([a-z]{1,5}(?:\.[a-z]{1,2})?)(?![a-zA-Z0-9])"
    ),
    re.compile(
        r"(?i:\bcompar(?:e|ed))\s+"
        r"([a-z]{1,5}(?:\.[a-z]{1,2})?)\s+"
        r"(?i:and|with)\b"
    ),
    re.compile(
        r"(?i:\bcompar(?:e|ed))\b[^,.!?！？]{0,40}"
        r"(?i:\b(?:and|with))\s+"
        r"([a-z]{1,5}(?:\.[a-z]{1,2})?)(?![a-zA-Z0-9])",
    ),
)
_LOWERCASE_TICKER_PATTERN = re.compile(r"(?<![a-zA-Z.])([a-z]{1,5}(?:\.[a-z]{1,2})?)(?![a-zA-Z0-9])")
_EXCHANGE_QUALIFIED_TOKEN_PATTERN = re.compile(
    r"(?<![a-zA-Z0-9.])(?:"
    r"(?:SH|SZ|SS|BJ|HK)\.?\d+|"
    r"\d+\.(?:SH|SZ|SS|BJ|HK|US|T|KS|KQ|TW|TWO)"
    r")(?![a-zA-Z0-9.])",
    re.IGNORECASE,
)
_EXCHANGE_TOKEN_CANDIDATES = {"SH", "SZ", "BJ", "HK", "SS"}
_COMPARISON_TOKEN_CANDIDATES = {"VS"}
_ALWAYS_DENIED_TICKER_CANDIDATES = {
    "BOLL",
    "EMA",
    "KDJ",
    "MA",
    "MACD",
    "RSI",
    "SMA",
    "VWAP",
}
_EXPLICIT_TICKER_COLLISIONS = {
    "BJ",
    "BOLL",
    "EMA",
    "MA",
    "RSI",
    "SH",
    "SMA",
    "VS",
}
_INDICATOR_CONTEXT_PATTERN = re.compile(
    r"指标|均线|移动平均|排列|多头|空头|金叉|死叉|支撑|压力|"
    r"\b(?:indicator|crossover)\b|MA\d|SMA|EMA",
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
    explicit_or_established: bool = False,
) -> bool:
    token = candidate.strip().upper()
    if (
        token in _EXCHANGE_TOKEN_CANDIDATES
        or token in _COMPARISON_TOKEN_CANDIDATES
        or token in _ALWAYS_DENIED_TICKER_CANDIDATES
    ):
        return not (
            explicit_or_established and token in _EXPLICIT_TICKER_COLLISIONS
        )
    if explicit_or_established:
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
        explicit_or_established=explicit,
    ):
        return
    if normalized not in candidates:
        candidates.append(normalized)


def _append_lowercase_slot_candidate(
    candidates: List[str],
    candidate: str,
    text: str,
) -> None:
    """Accept lowercase symbols only with positive, reusable symbol evidence."""
    normalized = _normalize_stock_code(candidate)
    if not normalized:
        return
    if "." not in candidate and normalized not in get_stock_name_index_map():
        return
    _append_candidate(candidates, candidate, text)


def _is_explicit_command_slot(text: str, match: re.Match[str]) -> bool:
    """Keep indicator prose out of otherwise explicit ticker slots."""
    token = match.group(1).strip().upper()
    trailing_text = text[match.end(1):]
    return not (
        token in _ALWAYS_DENIED_TICKER_CANDIDATES
        and _INDICATOR_CONTEXT_PATTERN.search(trailing_text)
    )


def _is_strong_compare_message(text: str) -> bool:
    """Distinguish comparison operators from an explicit ``VS`` ticker slot."""
    if _STRONG_COMPARE_PATTERN.search(text):
        return True

    command_spans = {
        match.span(1)
        for pattern in (
            _ENGLISH_EXPLICIT_TICKER_PATTERN,
            _ENGLISH_LOWERCASE_COMMAND_TICKER_PATTERN,
            _CJK_EXPLICIT_TICKER_PATTERN,
        )
        for match in pattern.finditer(text)
    }
    for match in _VS_COMPARE_PATTERN.finditer(text):
        if (
            match.group("operator").rstrip(".").upper() == "VS"
            and match.span("operator") in command_spans
        ):
            continue
        return True
    return False


def _is_spaced_exchange_affix(
    text: str,
    candidate: str,
    candidate_start: int,
) -> bool:
    """Identify exchange labels attached to a preceding numeric symbol."""
    if candidate.strip().upper() not in _EXCHANGE_TOKEN_CANDIDATES:
        return False
    return bool(
        re.search(
            r"(?<!\d)\d{5,6}\s+$",
            text[:candidate_start],
        )
    )


def extract_stock_codes(text: str) -> List[str]:
    """Extract all explicit stock-code candidates from free text."""
    if not text:
        return []

    candidates: List[str] = []
    qualified_spans = []
    for match in _EXCHANGE_QUALIFIED_TOKEN_PATTERN.finditer(text):
        qualified_spans.append(match.span())
        _append_candidate(candidates, match.group(0), text)

    for pattern, flags in (
        (
            r"(?<![a-zA-Z0-9.])(?:[03648]\d{5}|92\d{4})(?![a-zA-Z0-9.])",
            0,
        ),
        (r"(?<![a-zA-Z0-9.])\d{5}(?![a-zA-Z0-9.])", 0),
        (r"(?<![a-zA-Z.])([A-Z]{2,5}(?:\.[A-Z]{1,2})?)(?![a-zA-Z0-9])", 0),
    ):
        for match in re.finditer(pattern, text, flags):
            if any(
                match.start() < qualified_end and match.end() > qualified_start
                for qualified_start, qualified_end in qualified_spans
            ):
                continue
            raw = match.group(1) if match.lastindex else match.group(0)
            _append_candidate(candidates, raw, text)

    for match in _ENGLISH_EXPLICIT_TICKER_PATTERN.finditer(text):
        _append_candidate(
            candidates,
            match.group(1),
            text,
            explicit=_is_explicit_command_slot(text, match),
        )

    for match in _ENGLISH_LOWERCASE_COMMAND_TICKER_PATTERN.finditer(text):
        _append_lowercase_slot_candidate(
            candidates,
            match.group(1),
            text,
        )

    for match in _CJK_EXPLICIT_TICKER_PATTERN.finditer(text):
        _append_candidate(
            candidates,
            match.group(1),
            text,
            explicit=_is_explicit_command_slot(text, match),
        )

    for pattern in (
        _EXPLICIT_COMPARE_PAIR_PATTERN,
        _ENGLISH_AND_COMPARE_PAIR_PATTERN,
    ):
        for match in pattern.finditer(text):
            for group_index, raw in enumerate(match.groups(), start=1):
                if not raw.isupper():
                    _append_lowercase_slot_candidate(candidates, raw, text)
                    continue
                _append_candidate(
                    candidates,
                    raw,
                    text,
                    explicit=(
                        raw.isupper()
                        and not _is_spaced_exchange_affix(
                            text,
                            raw,
                            match.start(group_index),
                        )
                    ),
                )

    for pattern in _EXPLICIT_SINGLE_TICKER_COMPARE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1)
            _append_candidate(
                candidates,
                raw,
                text,
                explicit=not _is_spaced_exchange_affix(
                    text,
                    raw,
                    match.start(1),
                ),
            )

    for pattern in _EXPLICIT_LOWERCASE_COMPARE_TICKER_PATTERNS:
        for match in pattern.finditer(text):
            _append_lowercase_slot_candidate(
                candidates,
                match.group(1),
                text,
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
        or _WEAK_COMPARE_HINT_PATTERN.search(text)
        or _CHOICE_COMPARE_PATTERN.search(text)
        or bare_lowercase_ticker
    ):
        for match in _LOWERCASE_TICKER_PATTERN.finditer(text):
            _append_lowercase_slot_candidate(
                candidates,
                match.group(1),
                text,
            )

    return candidates


def _is_compare_message(message: str, candidates: List[str], current_code: str) -> bool:
    if _is_strong_compare_message(message):
        return True
    new_candidates = {code for code in candidates if code != current_code}
    if _ENGLISH_COMPARE_HINT_PATTERN.search(message):
        return len(candidates) >= 2 or bool(current_code and new_candidates)
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
    has_context_code = "stock_code" in original_context
    raw_context_code = original_context.get("stock_code")
    current_code = _normalize_stock_code(raw_context_code)
    invalid_context_code = has_context_code and (
        not current_code
        or _is_denied_candidate(
            current_code,
            message_text,
            explicit_or_established=True,
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
