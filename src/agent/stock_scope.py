# -*- coding: utf-8 -*-
"""Stock-scope helpers for ask-stock follow-up chat turns."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from src.data.stock_index_loader import get_stock_symbol_index_set
from src.services.stock_list_parser import normalize_stock_codes


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
_EXCHANGE_QUALIFIED_TOKEN_PATTERN = re.compile(
    r"(?<![-A-Za-z0-9._/:\\+|&,;=])(?:"
    r"(?:SH|SZ|SS|BJ|HK)\.?\d+|"
    r"\d+\.(?:SH|SZ|SS|BJ|HK|US|T|KS|KQ|TW|TWO)"
    r")(?![-A-Za-z0-9._/:\\+|&,;=])",
    re.IGNORECASE,
)
_RAW_SYMBOL_TOKEN = (
    r"[A-Za-z0-9](?:[-A-Za-z0-9._/:\\+|&,;=]*[A-Za-z0-9])?"
)
_SPACED_EXCHANGE_RAW_SLOT = (
    r"(?:(?:SH|SZ|SS|BJ|HK)\s+\d{1,6}|"
    r"\d{1,6}\s+(?:SH|SZ|SS|BJ|HK))"
)
_COMPARISON_RAW_SLOT = rf"(?:{_SPACED_EXCHANGE_RAW_SLOT}|{_RAW_SYMBOL_TOKEN})"
_JOINED_SLOT_WHITESPACE_PATTERN = re.compile(
    r"(?<=[A-Za-z0-9])\s*([:/\\+|&_;=\-])\s*(?=[A-Za-z0-9])"
)
_JOINED_COMMA_WHITESPACE_PATTERN = re.compile(
    r"(?<=[A-Za-z0-9])\s*,\s*"
    r"(?!(?:and|with|to|vs\.?|versus|和|与|跟)\b)"
    r"(?=[A-Za-z0-9])",
    re.IGNORECASE,
)
_EXPLICIT_COMMAND_RAW_SLOT_PATTERNS = (
    re.compile(
        r"\b(?:analy[sz]e|switch(?:\s+to)?|look\s+at|review)\s+"
        rf"(?P<slot>{_RAW_SYMBOL_TOKEN})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:换成|改看|分析|看看|看一下|查看|查一下|评估|研究|诊断)\s*"
        rf"(?P<slot>{_RAW_SYMBOL_TOKEN})",
    ),
)
_EXPLICIT_ENGLISH_RAW_COMPARE_PAIR_PATTERN = re.compile(
    rf"\bcompare\s+(?P<left>{_COMPARISON_RAW_SLOT})(?:\s+|\s*,\s*)"
    rf"(?:and|with|to)\s+(?P<right>{_COMPARISON_RAW_SLOT})",
    re.IGNORECASE,
)
_EXPLICIT_CHINESE_RAW_COMPARE_PAIR_PATTERN = re.compile(
    rf"(?P<left>{_COMPARISON_RAW_SLOT})\s*"
    rf"(?:相比|对比|比较)\s*(?P<right>{_COMPARISON_RAW_SLOT})",
    re.IGNORECASE,
)
_EXPLICIT_RAW_CONNECTOR_PAIR_PATTERN = re.compile(
    rf"(?<![-A-Za-z0-9._/:\\+|&,;=])"
    rf"(?P<left>{_COMPARISON_RAW_SLOT})\s*"
    rf"(?:vs\.?|versus|和|与|跟)\s*"
    rf"(?P<right>{_COMPARISON_RAW_SLOT})"
    rf"(?![-A-Za-z0-9._/:\\+|&,;=])",
    re.IGNORECASE,
)
_ACTIVE_COMPARE_RAW_SLOT_PATTERNS = (
    re.compile(
        rf"\bcompar(?:e|ed)\s+(?:(?:it|this|that)\s+)?(?:with|to)\s+"
        rf"(?P<slot>{_COMPARISON_RAW_SLOT})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:再\s*)?(?:和|与|跟|同)\s*"
        rf"(?P<slot>{_COMPARISON_RAW_SLOT})\s*"
        r"(?:比(?:较|一比|一下)?|对比|相比)",
    ),
    re.compile(
        rf"(?:对比|比较)\s*(?P<slot>{_COMPARISON_RAW_SLOT})",
    ),
    re.compile(
        rf"拿\s*(?P<slot>{_COMPARISON_RAW_SLOT})\s*"
        r"(?:对比|比较|相比)",
    ),
    re.compile(
        rf"(?:和|与|跟|同)\s*(?P<slot>{_COMPARISON_RAW_SLOT})\s*"
        r"(?:的\s*)?(?:差异(?!化)|区别|不同|对照)",
    ),
)
_INFIX_ENGLISH_RAW_COMPARE_PAIR_PATTERN = re.compile(
    rf"(?<![-A-Za-z0-9._/:\\+|&,;=])"
    rf"(?P<left>{_COMPARISON_RAW_SLOT})\s+"
    rf"compar(?:e|ed)\s+(?:with|to)\s+"
    rf"(?P<right>{_COMPARISON_RAW_SLOT})"
    rf"(?![-A-Za-z0-9._/:\\+|&,;=])",
    re.IGNORECASE,
)
_LEADING_COMPARE_RAW_SLOT_PATTERN = re.compile(
    rf"^\s*(?:vs\.?|versus)\s+(?P<slot>{_COMPARISON_RAW_SLOT})",
    re.IGNORECASE,
)
_NATURAL_TARGET_RAW_SLOT_PATTERNS = (
    re.compile(
        rf"\b(?:what\s+about|how\s+is|"
        rf"(?:say|says|said|think|thinks)\s+about|"
        rf"tell\s+(?:me|us)\s+about|"
        rf"(?:comments?|thoughts?|opinions?|views?)\s+(?:on|about))\s+"
        rf"(?P<slot>{_RAW_SYMBOL_TOKEN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bwhat\s+is\s+(?P<slot>{_RAW_SYMBOL_TOKEN})\s+"
        r"(?:worth|doing|trading\s+at)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bshould\s+(?:i|we)\s+(?:buy|sell|hold)\s+"
        rf"(?P<slot>{_RAW_SYMBOL_TOKEN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bi\s+think\s+(?P<slot>{_RAW_SYMBOL_TOKEN})\s+"
        r"(?:looks?|seems?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bexplain\s+(?P<slot>{_RAW_SYMBOL_TOKEN})\s+"
        r"(?:GAAP|EPS|valuation|earnings?|filings?|guidance)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:assess|evaluate|check(?:\s+out)?)\s+"
        rf"(?P<slot>{_RAW_SYMBOL_TOKEN})(?=\s*[?.!。！？]*\s*$)",
        re.IGNORECASE,
    ),
)
_NATURAL_SUFFIX_RAW_SLOT_PATTERN = re.compile(
    rf"^\s*(?P<slot>{_RAW_SYMBOL_TOKEN})\s*"
    r"(?:的\s*)?(?:stock\s+|share\s+)?"
    r"(?:price|performance|outlook|quote|valuation|fundamentals?|"
    r"earnings?|news|trend|走势|怎么样|股价|估值|基本面|新闻|前景|展望)"
    r"(?:\s+(?:today|now))?\s*[?.!。！？]*\s*$",
    re.IGNORECASE,
)
_BARE_SYMBOL_RAW_SLOT_PATTERN = re.compile(
    rf"^\s*(?P<slot>{_RAW_SYMBOL_TOKEN})\s*[?.!。！？]*\s*$"
)
_WEAK_STOCK_QUESTION_PATTERN = re.compile(
    r"\b(?:what\s+about|doing|worth|outlook|buy|sell|hold|earnings?|"
    r"valuation|fundamentals?|news|comments?|filing|guidance|explain|"
    r"say|says|said|think|"
    r"looks?|expensive|cheap|trend)\b|"
    r"怎么样|怎么走|怎么看|走势|股价|估值|基本面|新闻|能买吗|前景|展望",
    re.IGNORECASE,
)
_SPACED_EXCHANGE_TOKEN_PATTERN = re.compile(
    r"(?<![-A-Za-z0-9._/:\\+|&,;=])(?:"
    r"(?P<prefix>SH|SZ|SS|BJ|HK)\s+(?P<prefix_digits>\d{1,6})|"
    r"(?P<suffix_digits>\d{1,6})\s+(?P<suffix>SH|SZ|SS|BJ|HK)"
    r")(?![-A-Za-z0-9._/:\\+|&,;=])",
    re.IGNORECASE,
)
_SPACED_EXCHANGE_SLOT_PATTERN = re.compile(
    r"(?:"
    r"(?P<prefix>SH|SZ|SS|BJ|HK)\s+(?P<prefix_digits>\d{1,6})|"
    r"(?P<suffix_digits>\d{1,6})\s+(?P<suffix>SH|SZ|SS|BJ|HK)"
    r")",
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


def _normalize_evidence_text(text: str) -> str:
    """Normalize compatibility punctuation before applying atomic slot grammar."""
    normalized = unicodedata.normalize("NFKC", text).replace("、", ",")
    normalized = _JOINED_SLOT_WHITESPACE_PATTERN.sub(r"\1", normalized)
    return _JOINED_COMMA_WHITESPACE_PATTERN.sub(",", normalized)


def _normalize_comparison_slot(candidate: str) -> str:
    """Fold a spaced exchange-qualified comparison operand into one token."""
    stripped = candidate.strip()
    match = _SPACED_EXCHANGE_SLOT_PATTERN.fullmatch(stripped)
    if match is None:
        return stripped
    if match.group("prefix"):
        return match.group("prefix") + match.group("prefix_digits")
    return match.group("suffix_digits") + "." + match.group("suffix")


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


@dataclass(frozen=True)
class _StockCodeExtraction:
    """Internal symbol candidates plus the evidence governing scope changes."""

    stock_codes: tuple[str, ...] = ()
    switch_evidence: bool = False
    compare_evidence: bool = False
    malformed_explicit_slot: bool = False


def _normalize_stock_code(value: Any) -> str:
    """Normalize a code with the shared analysis canonicalizer."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    normalized = normalize_stock_codes([text])
    return normalized[0] if normalized else ""


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


def _append_indexed_slot_candidate(
    candidates: List[str],
    candidate: str,
    text: str,
    *,
    explicit: bool = False,
) -> None:
    """Accept non-uppercase symbols only with positive index evidence."""
    normalized = _normalize_stock_code(candidate)
    if not normalized:
        return
    known_symbols = get_stock_symbol_index_set()
    evidence_keys = {normalized}
    if normalized.endswith(".US"):
        evidence_keys.add(normalized[:-3])
    if not evidence_keys.intersection(known_symbols):
        return
    _append_candidate(
        candidates,
        candidate,
        text,
        explicit=explicit,
    )


def _append_explicit_slot_candidate(
    candidates: List[str],
    candidate: str,
    text: str,
    *,
    explicit: bool,
) -> None:
    """Route non-uppercase slots through the index-backed evidence policy."""
    normalized = _normalize_stock_code(candidate)
    has_numeric_identity = bool(
        normalized and any(character.isdigit() for character in candidate)
    )
    if candidate.isupper() or has_numeric_identity:
        _append_candidate(
            candidates,
            candidate,
            text,
            explicit=explicit,
        )
        return
    _append_indexed_slot_candidate(
        candidates,
        candidate,
        text,
        explicit=explicit,
    )


def _classify_explicit_slot(candidate: str, text: str) -> str:
    """Classify a raw explicit slot as valid, ordinary topic, or malformed."""
    normalized = _normalize_stock_code(candidate)
    if normalized:
        accepted: List[str] = []
        _append_explicit_slot_candidate(
            accepted,
            candidate,
            text,
            explicit=True,
        )
        if accepted:
            return "valid"

    has_separator_or_digit = any(
        character.isdigit() or character in ".-_/\\:+|&,;="
        for character in candidate
    )
    if has_separator_or_digit:
        return "malformed"
    if candidate != candidate.lower() and candidate != candidate.upper():
        return "malformed"
    return "topic"


def _is_indicator_command_topic(text: str, slot: str, slot_end: int) -> bool:
    return bool(
        slot.upper() in _ALWAYS_DENIED_TICKER_CANDIDATES
        and _INDICATOR_CONTEXT_PATTERN.search(text[slot_end:])
    )


def _is_compare_pronoun(slot: str) -> bool:
    """Keep English pronouns out of explicit comparison symbol slots."""
    lowered = slot.lower()
    return lowered in {"i", "this", "that"} or (
        lowered == "it" and slot != "IT"
    )


def _has_malformed_explicit_stock_request(text: str) -> bool:
    """Detect explicit malformed slots before stale context can be reused."""
    text = _normalize_evidence_text(text)
    for match in _SPACED_EXCHANGE_TOKEN_PATTERN.finditer(text):
        if match.group("prefix"):
            candidate = match.group("prefix") + match.group("prefix_digits")
        else:
            candidate = match.group("suffix_digits") + "." + match.group("suffix")
        if not _normalize_stock_code(candidate):
            return True

    for pattern in _EXPLICIT_COMMAND_RAW_SLOT_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        slot = match.group("slot")
        if _is_indicator_command_topic(text, slot, match.end("slot")):
            return False
        return _classify_explicit_slot(slot, text) == "malformed"

    pair_matches = list(_EXPLICIT_ENGLISH_RAW_COMPARE_PAIR_PATTERN.finditer(text))
    pair_matches.extend(_EXPLICIT_CHINESE_RAW_COMPARE_PAIR_PATTERN.finditer(text))
    pair_matches.extend(_EXPLICIT_RAW_CONNECTOR_PAIR_PATTERN.finditer(text))
    pair_matches.extend(_INFIX_ENGLISH_RAW_COMPARE_PAIR_PATTERN.finditer(text))
    for match in pair_matches:
        left = _normalize_comparison_slot(match.group("left"))
        right = _normalize_comparison_slot(match.group("right"))
        left_is_pronoun = _is_compare_pronoun(left)
        right_is_pronoun = _is_compare_pronoun(right)
        if left_is_pronoun or right_is_pronoun:
            other = right if left_is_pronoun else left
            if _classify_explicit_slot(other, text) == "malformed":
                return True
            continue
        statuses = {
            _classify_explicit_slot(left, text),
            _classify_explicit_slot(right, text),
        }
        if "malformed" in statuses:
            return True
        if statuses == {"topic", "valid"}:
            return True

    for pattern in (
        *_ACTIVE_COMPARE_RAW_SLOT_PATTERNS,
        _LEADING_COMPARE_RAW_SLOT_PATTERN,
        *_NATURAL_TARGET_RAW_SLOT_PATTERNS,
        _NATURAL_SUFFIX_RAW_SLOT_PATTERN,
    ):
        for match in pattern.finditer(text):
            slot = _normalize_comparison_slot(match.group("slot"))
            if _classify_explicit_slot(slot, text) == "malformed":
                return True

    bare_slot = _BARE_SYMBOL_RAW_SLOT_PATTERN.fullmatch(text)
    if (
        bare_slot is not None
        and _classify_explicit_slot(bare_slot.group("slot"), text) == "malformed"
    ):
        return True
    return False


def _append_comparison_operand(
    candidates: List[str],
    candidate: str,
    text: str,
    candidate_start: int,
) -> None:
    """Append one explicit operand, folding a spaced exchange affix."""
    if _is_spaced_exchange_affix(text, candidate, candidate_start):
        numeric = re.search(r"(?<!\d)(\d{5,6})\s+$", text[:candidate_start])
        if numeric is not None:
            _append_explicit_slot_candidate(
                candidates,
                numeric.group(1),
                text,
                explicit=True,
            )
        return
    _append_explicit_slot_candidate(
        candidates,
        candidate,
        text,
        explicit=True,
    )


def _is_strong_compare_message(text: str) -> bool:
    """Distinguish comparison operators from an explicit ``VS`` ticker slot."""
    if _STRONG_COMPARE_PATTERN.search(text):
        return True

    command_spans = {
        match.span("slot")
        for pattern in _EXPLICIT_COMMAND_RAW_SLOT_PATTERNS
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


def _append_natural_target_candidate(
    candidates: List[str],
    candidate: str,
    text: str,
) -> None:
    """Accept direct natural-language targets with format or index evidence."""
    normalized = _normalize_stock_code(candidate)
    if not normalized or _is_compare_pronoun(candidate):
        return
    if any(character.isdigit() for character in candidate):
        _append_candidate(candidates, candidate, text, explicit=True)
        return
    _append_indexed_slot_candidate(
        candidates,
        candidate,
        text,
        explicit=False,
    )


def _extract_stock_code_evidence(text: str) -> _StockCodeExtraction:
    """Extract candidates while preserving the evidence that authorizes scope."""
    if not text:
        return _StockCodeExtraction()
    text = _normalize_evidence_text(text)
    if _has_malformed_explicit_stock_request(text):
        return _StockCodeExtraction(malformed_explicit_slot=True)

    weak_candidates: List[str] = []
    qualified_spans = []
    for match in _EXCHANGE_QUALIFIED_TOKEN_PATTERN.finditer(text):
        qualified_spans.append(match.span())
        _append_candidate(weak_candidates, match.group(0), text)

    for pattern in (
        (
            r"(?<![-A-Za-z0-9._/:\\+|&,;=])(?:[03648]\d{5}|92\d{4})"
            r"(?![-A-Za-z0-9._/:\\+|&,;=])"
        ),
        (
            r"(?<![-A-Za-z0-9._/:\\+|&,;=])\d{5}"
            r"(?![-A-Za-z0-9._/:\\+|&,;=])"
        ),
    ):
        for match in re.finditer(pattern, text):
            if (
                (match.start() > 0 and text[match.start() - 1] == ":")
                or (match.end() < len(text) and text[match.end()] == ":")
            ):
                continue
            if any(
                match.start() < qualified_end and match.end() > qualified_start
                for qualified_start, qualified_end in qualified_spans
            ):
                continue
            _append_candidate(weak_candidates, match.group(0), text)

    command_candidates: List[str] = []
    for pattern in _EXPLICIT_COMMAND_RAW_SLOT_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        raw = match.group("slot")
        spaced_match = _SPACED_EXCHANGE_TOKEN_PATTERN.match(
            text,
            match.start("slot"),
        )
        if spaced_match is not None and spaced_match.group("prefix"):
            raw = (
                spaced_match.group("prefix")
                + spaced_match.group("prefix_digits")
            )
        if _is_indicator_command_topic(text, raw, match.end("slot")):
            break
        if raw.lower() == "it" and raw != "IT":
            break
        if _classify_explicit_slot(raw, text) == "valid":
            _append_explicit_slot_candidate(
                command_candidates,
                raw,
                text,
                explicit=True,
            )
        break

    comparison_candidates: List[str] = []
    pair_patterns = (
        _EXPLICIT_ENGLISH_RAW_COMPARE_PAIR_PATTERN,
        _EXPLICIT_CHINESE_RAW_COMPARE_PAIR_PATTERN,
        _EXPLICIT_RAW_CONNECTOR_PAIR_PATTERN,
        _INFIX_ENGLISH_RAW_COMPARE_PAIR_PATTERN,
    )
    for pattern in pair_patterns:
        for match in pattern.finditer(text):
            left = _normalize_comparison_slot(match.group("left"))
            right = _normalize_comparison_slot(match.group("right"))
            left_is_pronoun = _is_compare_pronoun(left)
            right_is_pronoun = _is_compare_pronoun(right)
            if left_is_pronoun or right_is_pronoun:
                other = right if left_is_pronoun else left
                other_group = "right" if left_is_pronoun else "left"
                if _classify_explicit_slot(other, text) == "valid":
                    _append_comparison_operand(
                        comparison_candidates,
                        other,
                        text,
                        match.start(other_group),
                    )
                continue
            if {
                _classify_explicit_slot(left, text),
                _classify_explicit_slot(right, text),
            } != {"valid"}:
                continue
            _append_comparison_operand(
                comparison_candidates,
                left,
                text,
                match.start("left"),
            )
            _append_comparison_operand(
                comparison_candidates,
                right,
                text,
                match.start("right"),
            )

    for pattern in (
        *_ACTIVE_COMPARE_RAW_SLOT_PATTERNS,
        _LEADING_COMPARE_RAW_SLOT_PATTERN,
    ):
        for match in pattern.finditer(text):
            raw = _normalize_comparison_slot(match.group("slot"))
            if _classify_explicit_slot(raw, text) == "valid":
                _append_comparison_operand(
                    comparison_candidates,
                    raw,
                    text,
                    match.start("slot"),
                )

    bare_ticker = _BARE_SYMBOL_RAW_SLOT_PATTERN.fullmatch(text)
    bare_candidates: List[str] = []
    if (
        bare_ticker
        and _classify_explicit_slot(bare_ticker.group("slot"), text) == "valid"
    ):
        _append_explicit_slot_candidate(
            bare_candidates,
            bare_ticker.group("slot"),
            text,
            explicit=True,
        )

    natural_target_candidates: List[str] = []
    for pattern in _NATURAL_TARGET_RAW_SLOT_PATTERNS:
        for match in pattern.finditer(text):
            _append_natural_target_candidate(
                natural_target_candidates,
                match.group("slot"),
                text,
            )
    suffix_match = _NATURAL_SUFFIX_RAW_SLOT_PATTERN.fullmatch(text)
    if suffix_match is not None:
        _append_natural_target_candidate(
            natural_target_candidates,
            suffix_match.group("slot"),
            text,
        )

    if comparison_candidates:
        return _StockCodeExtraction(
            stock_codes=tuple(comparison_candidates),
            compare_evidence=True,
        )
    if command_candidates:
        return _StockCodeExtraction(
            stock_codes=tuple(command_candidates),
            switch_evidence=True,
        )
    if bare_candidates:
        return _StockCodeExtraction(
            stock_codes=tuple(bare_candidates),
            switch_evidence=True,
        )
    if natural_target_candidates:
        return _StockCodeExtraction(
            stock_codes=tuple(natural_target_candidates),
            switch_evidence=True,
        )

    legacy_compare_evidence = bool(
        _is_strong_compare_message(text)
        or _ENGLISH_COMPARE_HINT_PATTERN.search(text)
        or _WEAK_COMPARE_HINT_PATTERN.search(text)
        or _CHOICE_COMPARE_PATTERN.search(text)
    )
    has_linked_compare_operand = bool(
        weak_candidates and _LINKED_COMPARE_PATTERN.search(text)
    )
    if legacy_compare_evidence and (
        len(weak_candidates) >= 2 or has_linked_compare_operand
    ):
        return _StockCodeExtraction(
            stock_codes=tuple(weak_candidates),
            compare_evidence=True,
        )
    if len(weak_candidates) == 1 and _WEAK_STOCK_QUESTION_PATTERN.search(text):
        return _StockCodeExtraction(
            stock_codes=tuple(weak_candidates),
            switch_evidence=True,
        )
    return _StockCodeExtraction()


def extract_stock_codes(text: str) -> List[str]:
    """Extract stock codes authorized by explicit or indexed text evidence."""
    return list(_extract_stock_code_evidence(text).stock_codes)


def _is_compare_message(message: str, candidates: List[str], current_code: str) -> bool:
    if _is_strong_compare_message(message):
        return True
    new_candidates = {code for code in candidates if code != current_code}
    if _ENGLISH_COMPARE_HINT_PATTERN.search(message):
        return len(candidates) >= 2 or bool(current_code and new_candidates)
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
    message_text = _normalize_evidence_text(message or "")
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

    extraction = _extract_stock_code_evidence(message_text)
    if extraction.malformed_explicit_slot:
        effective_context = _clear_stock_context(original_context)
        return StockScopeResolution(
            effective_context=_with_skills(effective_context, skills),
            stock_scope=StockScope(),
        )

    if not current_code:
        candidates = list(extraction.stock_codes)
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

    candidates = list(extraction.stock_codes)
    new_candidates = [code for code in candidates if code != current_code]
    mode = "maintain"
    effective_context = dict(original_context)
    expected = current_code
    allowed = {current_code}

    if extraction.compare_evidence or _is_compare_message(
        message_text,
        candidates,
        current_code,
    ):
        mode = "compare"
        explicit_codes = set(candidates)
        if len(explicit_codes) >= 2:
            allowed = explicit_codes
            if current_code not in allowed:
                effective_context = _clear_stock_context(original_context)
        else:
            allowed.update(explicit_codes)
        expected = ""
    elif (
        extraction.switch_evidence or _SWITCH_PATTERN.search(message_text)
    ) and len(new_candidates) == 1:
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
