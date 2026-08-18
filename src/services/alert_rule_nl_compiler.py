# -*- coding: utf-8 -*-
"""Whitelist-bounded natural-language alert rule compiler (issue #1133 C5).

Compiles free-form phrases into structured Alert API create payloads without
arbitrary code execution. Outcomes: success | need_clarification | rejected.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.data_provider.base import normalize_stock_code
from src.services.event_alerts import CORPORATE_EVENT_CATEGORIES, CORPORATE_EVENT_CATEGORY_SET

CompilerOutcome = str

# Match AlertWorker.MAX_DB_ALERT_COOLDOWN_SECONDS without importing the worker.
_MAX_COOLDOWN_SECONDS = 365 * 24 * 60 * 60

_COMPARATORS = {
    "above": ("above", "over", "greater than", "高于", "上破", "突破", "超过", "大于"),
    "below": ("below", "under", "less than", "低于", "下破", "跌破", "小于"),
    "up": ("up", "rise", "gain", "涨", "上涨", "涨幅"),
    "down": ("down", "drop", "fall", "跌", "下跌", "跌幅"),
}

_METRIC_PATTERNS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("price_cross", ("price", "股价", "价格", "现价")),
    ("price_change_percent", ("change", "percent", "涨跌幅", "涨幅", "跌幅", "%")),
    ("volume_spike", ("volume", "成交量", "放量", "量能", "异动")),
    ("corporate_event", ("earnings", "财报", "公告", "事件", "corporate event", "业绩", "年报", "季报")),
    ("rsi_threshold", ("rsi",)),
)

_CATEGORY_HINTS: Dict[str, Tuple[str, ...]] = {
    "earnings": ("earnings", "财报", "业绩", "年报", "季报", "中报", "预告"),
    "shareholder": ("shareholder", "股东", "增持", "减持", "回购"),
    "mna": ("m&a", "merger", "acquisition", "并购", "重组", "收购"),
    "regulatory": ("regulatory", "监管", "立案", "处罚", "问询"),
    "analyst": ("analyst", "评级", "目标价", "上调", "下调", "研报"),
}

_SYMBOL_RE = re.compile(
    r"\b("
    r"(?:[Ss][Hh]|[Ss][Zz]|[Bb][Jj])?\d{6}"
    r"|[Hh][Kk]\d{4,5}"
    r"|\d{4,5}\.[Hh][Kk]"
    r"|[A-Z]{1,5}"
    r")\b"
)
_SYMBOL_STOPWORDS = frozenset(
    {
        "PRICE", "ABOVE", "BELOW", "VOLUME", "CHANGE", "PERCENT", "SPIKE", "ALERT",
        "EVENT", "CORPORATE", "EARNINGS", "RSI", "MACD", "WHEN", "THEN", "WITH",
        "AUTO", "DEEP", "ANALYSIS", "TRIGGER", "STOCK", "SHARE", "SHARES",
        "COOLDOWN",
    }
)
_NUMBER_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*%?")

_COOLDOWN_UNIT_SECONDS: Dict[str, int] = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "秒": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60, "分": 60, "分钟": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600, "时": 3600, "小时": 3600,
    "d": 86400, "day": 86400, "days": 86400, "天": 86400, "日": 86400,
}
_COOLDOWN_UNIT_PATTERN = (
    r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|s|m|h|d|秒|分钟|分|小时|时|天|日)(?![a-zA-Z])"
)
_COOLDOWN_KEYWORD_RE = re.compile(r"cooldown|冷却", re.IGNORECASE)
_COOLDOWN_CLAUSE_RES: Tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:cooldown|冷却(?:时间)?)\s*(?:of\s+|for\s+|[=:：]\s*)?(?<![\d.-])(\d+(?:\.\d+)?)\s*"
        + _COOLDOWN_UNIT_PATTERN,
        re.IGNORECASE,
    ),
    re.compile(
        r"(?<![\d.-])(\d+(?:\.\d+)?)\s*-?\s*"
        + _COOLDOWN_UNIT_PATTERN
        + r"\s*(?:的)?\s*(?:cooldown|冷却(?:时间)?)",
        re.IGNORECASE,
    ),
)


@dataclass
class _CooldownClause:
    """Outcome of extracting an optional cooldown clause from the phrase."""

    stripped_source: str
    cooldown_seconds: Optional[int] = None
    needs_clarification: bool = False
    reject_message: Optional[str] = None


def _extract_cooldown_clause(source: str) -> _CooldownClause:
    """Parse and strip a whitelist-bounded cooldown clause from the phrase.

    The clause is removed from the returned text so cooldown numbers can never
    be mistaken for metric thresholds. Ambiguous cooldown mentions ask for
    clarification instead of guessing a duration.
    """
    for pattern in _COOLDOWN_CLAUSE_RES:
        match = pattern.search(source)
        if match is None:
            continue
        value = float(match.group(1))
        unit_seconds = _COOLDOWN_UNIT_SECONDS.get(match.group(2).lower())
        if unit_seconds is None:
            break
        seconds = value * unit_seconds
        if not math.isfinite(seconds):
            return _CooldownClause(source, reject_message="cooldown duration must be finite")
        if seconds <= 0:
            return _CooldownClause(
                source,
                reject_message="cooldown duration must be at least 1 second",
            )
        if seconds > _MAX_COOLDOWN_SECONDS:
            return _CooldownClause(
                source,
                reject_message=(
                    f"cooldown exceeds the maximum of {_MAX_COOLDOWN_SECONDS} seconds (365 days)"
                ),
            )
        if seconds != int(seconds):
            return _CooldownClause(
                source,
                reject_message="cooldown duration must resolve to a whole number of seconds",
            )
        stripped = " ".join((source[: match.start()] + " " + source[match.end():]).split())
        return _CooldownClause(stripped, cooldown_seconds=int(seconds))
    if _COOLDOWN_KEYWORD_RE.search(source):
        return _CooldownClause(source, needs_clarification=True)
    return _CooldownClause(source)


@dataclass
class AlertRuleCompileResult:
    outcome: CompilerOutcome
    rule: Optional[Dict[str, Any]] = None
    ir: Optional[Dict[str, Any]] = None
    message: str = ""
    clarifications: List[str] = field(default_factory=list)
    rejected_reason: Optional[str] = None
    matched_metric: Optional[str] = None
    matched_symbols: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "message": self.message,
            "matched_metric": self.matched_metric,
            "matched_symbols": list(self.matched_symbols),
            "clarifications": list(self.clarifications),
            "rejected_reason": self.rejected_reason,
            "rule": self.rule,
            "ir": self.ir,
        }


def compile_alert_rule_nl(
    text: str,
    *,
    default_target_scope: str = "single_symbol",
    default_severity: str = "warning",
    default_enabled: bool = True,
    auto_analysis: Optional[bool] = None,
) -> AlertRuleCompileResult:
    source = " ".join(str(text or "").strip().split())
    if not source:
        return AlertRuleCompileResult(outcome="rejected", message="Empty input", rejected_reason="empty_input")
    if len(source) > 500:
        return AlertRuleCompileResult(
            outcome="rejected",
            message="Input too long (max 500 characters)",
            rejected_reason="input_too_long",
        )
    if _looks_like_code(source):
        return AlertRuleCompileResult(
            outcome="rejected",
            message="Natural-language compiler rejects code or executable snippets",
            rejected_reason="code_like_input",
        )

    cooldown = _extract_cooldown_clause(source)
    if cooldown.reject_message:
        return AlertRuleCompileResult(
            outcome="rejected",
            message=cooldown.reject_message,
            rejected_reason="invalid_parameters",
        )
    # Strip the cooldown clause first so its numbers and unit words can never
    # be mistaken for metric thresholds or symbols.
    source = cooldown.stripped_source
    lowered = source.lower()

    symbols = _extract_symbols(source)
    metric = _detect_metric(lowered)
    if metric is None:
        return AlertRuleCompileResult(
            outcome="rejected",
            message=(
                "Could not map the phrase to a supported monitor metric. "
                "Supported: price, percent change, volume spike, corporate event, RSI."
            ),
            rejected_reason="unsupported_metric",
            matched_symbols=symbols,
        )
    if cooldown.needs_clarification:
        return AlertRuleCompileResult(
            outcome="need_clarification",
            message=(
                "Cooldown was mentioned without a parseable duration. "
                "Use an explicit amount and unit, for example 'cooldown 30 minutes'."
            ),
            clarifications=["cooldown_duration"],
            matched_metric=metric,
            matched_symbols=symbols,
        )
    if not symbols:
        return AlertRuleCompileResult(
            outcome="need_clarification",
            message="Please include a stock code (for example 600519 or AAPL).",
            clarifications=["stock_code"],
            matched_metric=metric,
        )
    if len(symbols) > 1:
        return AlertRuleCompileResult(
            outcome="need_clarification",
            message="Multiple stock codes detected; specify exactly one symbol for this rule.",
            clarifications=["single_stock_code"],
            matched_metric=metric,
            matched_symbols=symbols,
        )

    symbol = symbols[0]
    parameters, missing, reject = _build_parameters(metric, source, lowered)
    if reject:
        return AlertRuleCompileResult(
            outcome="rejected",
            message=reject,
            rejected_reason="invalid_parameters",
            matched_metric=metric,
            matched_symbols=symbols,
        )
    if missing:
        return AlertRuleCompileResult(
            outcome="need_clarification",
            message=f"Missing required fields: {', '.join(missing)}",
            clarifications=missing,
            matched_metric=metric,
            matched_symbols=symbols,
        )

    rule: Dict[str, Any] = {
        "name": _default_name(metric, symbol, parameters),
        "target_scope": default_target_scope if default_target_scope in {"single_symbol", "watchlist", "portfolio_holdings"} else "single_symbol",
        "target": symbol,
        "alert_type": metric,
        "parameters": parameters,
        "severity": default_severity if default_severity in {"info", "warning", "critical"} else "warning",
        "enabled": bool(default_enabled),
        "source": "nl_compiler",
    }
    if metric == "corporate_event":
        categories = parameters.get("event_categories") or list(CORPORATE_EVENT_CATEGORIES)
        rule["parameters"] = {
            "event_categories": list(categories),
            "lookback_hours": int(parameters.get("lookback_hours") or 24),
            "min_items": int(parameters.get("min_items") or 1),
        }
        parameters = rule["parameters"]
    if cooldown.cooldown_seconds is not None:
        rule["cooldown_policy"] = {"cooldown_seconds": cooldown.cooldown_seconds}

    notification_policy: Dict[str, Any] = {}
    if auto_analysis is True or (auto_analysis is None and _wants_auto_analysis(lowered)):
        notification_policy["auto_analysis"] = True
    if notification_policy:
        rule["notification_policy"] = notification_policy

    ir = _structured_ir(symbol, metric, parameters, cooldown.cooldown_seconds)
    return AlertRuleCompileResult(
        outcome="success",
        rule=rule,
        ir=ir,
        message="Compiled to a whitelist-bounded alert rule payload",
        matched_metric=metric,
        matched_symbols=symbols,
    )


def _looks_like_code(text: str) -> bool:
    forbidden = ("import ", "exec(", "eval(", "__", "os.system", "subprocess", "lambda ", "#!/", "<?php", "<script")
    lowered = text.lower()
    if any(token in lowered for token in forbidden):
        return True
    if re.search(r"[{};]|=>|&&|\|\|", text) and re.search(r"\bdef\b|\bfunction\b|\bclass\b", lowered):
        return True
    return False


def _extract_symbols(text: str) -> List[str]:
    found: List[str] = []
    for match in _SYMBOL_RE.finditer(text):
        raw = match.group(1)
        if raw.upper() in _SYMBOL_STOPWORDS:
            continue
        # Pure letter tickers must appear in uppercase to avoid English words.
        if raw.isalpha() and raw != raw.upper():
            continue
        if raw.isdigit() and len(raw) < 6:
            span_start = max(0, match.start() - 2)
            prefix = text[span_start:match.start()].lower()
            if "hk" not in prefix and not raw.startswith("0"):
                continue
        try:
            normalized = normalize_stock_code(raw)
        except (TypeError, ValueError):
            continue
        if normalized and normalized not in found:
            found.append(normalized)
    return found


def _detect_metric(lowered: str) -> Optional[str]:
    scores: Dict[str, int] = {}
    for metric, keywords in _METRIC_PATTERNS:
        score = sum(1 for kw in keywords if kw.lower() in lowered)
        if score:
            scores[metric] = score
    if not scores:
        return None
    priority = ["corporate_event", "volume_spike", "price_change_percent", "rsi_threshold", "price_cross"]
    best = max(scores.values())
    candidates = [m for m, s in scores.items() if s == best]
    for metric in priority:
        if metric in candidates:
            return metric
    return candidates[0]


def _build_parameters(metric: str, source: str, lowered: str) -> Tuple[Dict[str, Any], List[str], Optional[str]]:
    symbols = set(_extract_symbols(source))
    numbers = []
    for match in _NUMBER_RE.finditer(source):
        raw = match.group(1)
        # Skip integers that are the stock code itself (e.g. 300750 volume spike 2.5x).
        if raw.isdigit() and (raw in symbols or any(raw in s for s in symbols)):
            continue
        number = float(raw)
        if not math.isfinite(number):
            return {}, [], "numeric parameters must be finite"
        numbers.append(number)
    if metric == "price_cross":
        direction = _detect_direction(lowered, for_price=True)
        if direction is None:
            return {}, ["direction"], None
        price = _first_positive(numbers)
        if price is None:
            return {}, ["price"], None
        return {"direction": direction, "price": price}, [], None
    if metric == "price_change_percent":
        direction = _detect_direction(lowered, for_change=True)
        if direction is None:
            return {}, ["direction"], None
        pct = _first_positive(numbers)
        if pct is None:
            return {}, ["change_pct"], None
        return {"direction": direction, "change_pct": pct}, [], None
    if metric == "volume_spike":
        multiplier = _first_positive(numbers) or 2.0
        if multiplier <= 0:
            return {}, [], "volume multiplier must be > 0"
        return {"multiplier": multiplier}, [], None
    if metric == "rsi_threshold":
        direction = _detect_direction(lowered, for_price=True) or "above"
        threshold = None
        for number in numbers:
            if 0 <= number <= 100:
                threshold = number
                break
        if threshold is None:
            return {}, ["threshold"], None
        return {"direction": direction, "period": 12, "threshold": threshold}, [], None
    if metric == "corporate_event":
        categories = _detect_event_categories(lowered) or list(CORPORATE_EVENT_CATEGORIES)
        lookback = 24
        for number in numbers:
            if 1 <= number <= 168 and number == int(number):
                lookback = int(number)
                break
        return {"event_categories": categories, "lookback_hours": lookback, "min_items": 1}, [], None
    return {}, [], f"unsupported metric: {metric}"


def _detect_direction(lowered: str, *, for_price: bool = False, for_change: bool = False) -> Optional[str]:
    if for_change:
        for direction, words in (("up", _COMPARATORS["up"]), ("down", _COMPARATORS["down"])):
            if any(word in lowered for word in words):
                return direction
        return None
    if for_price:
        for direction, words in (("above", _COMPARATORS["above"]), ("below", _COMPARATORS["below"])):
            if any(word in lowered for word in words):
                return direction
        return None
    return None


def _detect_event_categories(lowered: str) -> List[str]:
    matched: List[str] = []
    for category, hints in _CATEGORY_HINTS.items():
        if category not in CORPORATE_EVENT_CATEGORY_SET:
            continue
        if any(hint in lowered for hint in hints):
            matched.append(category)
    return matched


def _first_positive(numbers: Sequence[float]) -> Optional[float]:
    for number in numbers:
        if number > 0:
            return float(number)
    return None


def _wants_auto_analysis(lowered: str) -> bool:
    cues = ("deep analysis", "auto analysis", "trigger analysis", "深度分析", "自动分析", "触发分析", "跑一遍分析")
    return any(cue in lowered for cue in cues)


def _structured_ir(
    symbol: str,
    metric: str,
    parameters: Dict[str, Any],
    cooldown_seconds: Optional[int],
) -> Dict[str, Any]:
    comparator, threshold = _comparator_and_threshold(metric, parameters)
    return {
        "symbol": symbol,
        "metric": metric,
        "comparator": comparator,
        "threshold": threshold,
        "cooldown": cooldown_seconds,
    }


def _comparator_and_threshold(metric: str, parameters: Dict[str, Any]) -> Tuple[str, Any]:
    if metric == "price_cross":
        return str(parameters.get("direction") or "above"), parameters.get("price")
    if metric == "price_change_percent":
        return str(parameters.get("direction") or "up"), parameters.get("change_pct")
    if metric == "rsi_threshold":
        return str(parameters.get("direction") or "above"), parameters.get("threshold")
    if metric == "volume_spike":
        return "gte", parameters.get("multiplier")
    if metric == "corporate_event":
        return "any", parameters.get("min_items")
    return "eq", None


def _default_name(metric: str, symbol: str, parameters: Dict[str, Any]) -> str:
    if metric == "corporate_event":
        cats = ",".join(parameters.get("event_categories") or [])
        return f"{symbol} corporate event ({cats})"[:64]
    if metric == "volume_spike":
        return f"{symbol} volume x{parameters.get('multiplier')}"[:64]
    if metric == "price_cross":
        return f"{symbol} price {parameters.get('direction')} {parameters.get('price')}"[:64]
    if metric == "price_change_percent":
        return f"{symbol} change {parameters.get('direction')} {parameters.get('change_pct')}%"[:64]
    if metric == "rsi_threshold":
        return f"{symbol} RSI {parameters.get('direction')} {parameters.get('threshold')}"[:64]
    return f"{symbol} {metric}"[:64]
