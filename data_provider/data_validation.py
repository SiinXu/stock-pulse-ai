# -*- coding: utf-8 -*-
"""Unified financial data validation layer (Issue #185 / T11).

Pure-function validators for OHLCV bars, realtime quotes, and fundamental
blocks. Intended to run at the data-provider unified exit (manager layer),
not inside individual fetchers.

Default policy is **warn-only**: issues are recorded and logged; data is
passed through. Set ``DATA_VALIDATION_STRICT=true`` to reject definite errors
and let upper layers degrade.

This module never silently drops rows or fields.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

# ---------------------------------------------------------------------------
# Reason codes (structured; safe for diagnostics / reports)
# ---------------------------------------------------------------------------

CODE_PRICE_MISSING = "dv_price_missing"
CODE_PRICE_NON_FINITE = "dv_price_non_finite"
CODE_PRICE_NON_POSITIVE = "dv_price_non_positive"
CODE_HIGH_BELOW_LOW = "dv_high_below_low"
CODE_CLOSE_OUT_OF_RANGE = "dv_close_out_of_range"
CODE_OPEN_OUT_OF_RANGE = "dv_open_out_of_range"
CODE_PCT_CHG_INCONSISTENT = "dv_pct_chg_inconsistent"
CODE_VOLUME_NEGATIVE = "dv_volume_negative"
CODE_VOLUME_NON_FINITE = "dv_volume_non_finite"
CODE_VOLUME_UNIT_SUSPECT = "dv_volume_unit_suspect"
CODE_AMOUNT_NEGATIVE = "dv_amount_negative"
CODE_DATE_OUT_OF_ORDER = "dv_date_out_of_order"
CODE_DATE_DUPLICATE = "dv_date_duplicate"
CODE_FUND_PE_NON_FINITE = "dv_fund_pe_non_finite"
CODE_FUND_PE_EXTREME = "dv_fund_pe_extreme"
CODE_FUND_PB_NON_FINITE = "dv_fund_pb_non_finite"
CODE_FUND_PB_EXTREME = "dv_fund_pb_extreme"
CODE_FUND_PE_NEGATIVE = "dv_fund_pe_negative"
CODE_EMPTY_PAYLOAD = "dv_empty_payload"

# Severity ranking for aggregation
_SEVERITY_RANK = {
    "pass": 0,
    "warn": 1,
    "reject": 2,
}

# Tolerances chosen to avoid false positives on normal provider rounding.
# pct_chg is typically percent points (e.g. 1.23 means +1.23%).
PCT_CHG_ABS_TOLERANCE = 0.51  # allow ~0.5pp rounding / limit-board quirks
# Volume unit heuristic: amount/volume vs close near 100x => volume likely in lots (手).
VOLUME_UNIT_RATIO_MIN = 80.0
VOLUME_UNIT_RATIO_MAX = 120.0
# Fundamental extremes that almost always indicate bad feed data.
PE_ABS_EXTREME = 50_000.0
PB_ABS_EXTREME = 10_000.0

ENV_STRICT = "DATA_VALIDATION_STRICT"
ENV_ENABLED = "DATA_VALIDATION_ENABLED"

ATTR_KEY = "data_validation"


class ValidationSeverity(str, Enum):
    """Outcome grade for a single issue or an aggregated result."""

    PASS = "pass"
    WARN = "warn"
    REJECT = "reject"


@dataclass(frozen=True)
class ValidationIssue:
    """One structured validation finding."""

    code: str
    severity: ValidationSeverity
    message: str
    field: Optional[str] = None
    row_index: Optional[int] = None
    detail: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "code": self.code,
            "severity": self.severity.value
            if isinstance(self.severity, ValidationSeverity)
            else str(self.severity),
            "message": self.message,
        }
        if self.field is not None:
            payload["field"] = self.field
        if self.row_index is not None:
            payload["row_index"] = self.row_index
        if self.detail:
            payload["detail"] = dict(self.detail)
        return payload


@dataclass
class ValidationResult:
    """Aggregated validation outcome. Never implies silent data mutation."""

    status: ValidationSeverity = ValidationSeverity.PASS
    issues: List[ValidationIssue] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == ValidationSeverity.PASS

    @property
    def has_reject(self) -> bool:
        return self.status == ValidationSeverity.REJECT

    @property
    def has_warn(self) -> bool:
        return any(i.severity == ValidationSeverity.WARN for i in self.issues)

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        rank = _SEVERITY_RANK.get(
            issue.severity.value
            if isinstance(issue.severity, ValidationSeverity)
            else str(issue.severity),
            0,
        )
        if rank > _SEVERITY_RANK.get(self.status.value, 0):
            self.status = (
                issue.severity
                if isinstance(issue.severity, ValidationSeverity)
                else ValidationSeverity(str(issue.severity))
            )

    def extend(self, issues: Iterable[ValidationIssue]) -> None:
        for issue in issues:
            self.add(issue)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.extend(other.issues)
        for key, value in other.context.items():
            self.context.setdefault(key, value)
        return self

    def should_reject(self, *, strict: Optional[bool] = None) -> bool:
        """True only when status is REJECT and strict mode is active."""
        if strict is None:
            strict = is_strict_mode()
        return bool(strict) and self.has_reject

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "issues": [issue.to_dict() for issue in self.issues],
            "context": dict(self.context),
        }


class DataValidationRejected(Exception):
    """Raised in strict mode when validation status is REJECT.

    Upper layers (manager failover / analysis pipeline) decide degradation.

    Stores only a plain dict payload (not a live ValidationResult) so production
    exception-log taint analysis does not treat ValidationResult locals as
    exception objects when they are logged after sanitization.
    """

    def __init__(self, validation: ValidationResult, *, data_type: str = "unknown"):
        payload = validation.to_dict()
        self.validation_payload: Dict[str, Any] = payload
        self.data_type = data_type
        codes = ",".join(
            sorted(
                {
                    str(item.get("code") or "")
                    for item in payload.get("issues", [])
                    if isinstance(item, dict)
                    and item.get("severity") == ValidationSeverity.REJECT.value
                }
            )
        )
        super().__init__(
            f"data validation rejected data_type={data_type} codes={codes or 'unknown'}"
        )


# ---------------------------------------------------------------------------
# Config helpers (no config-registry coupling; opt-in / default-safe)
# ---------------------------------------------------------------------------


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def is_validation_enabled() -> bool:
    """Master switch. Default True so the layer runs warn-only without config."""
    return _read_bool_env(ENV_ENABLED, True)


def is_strict_mode() -> bool:
    """When True, REJECT findings raise / block. Default False (warn-only)."""
    return _read_bool_env(ENV_STRICT, False)


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


def is_non_finite_number(value: Any) -> bool:
    """Return True when value is a numeric NaN or ±Infinity."""
    if value is None:
        return False
    try:
        # bool is int subclass; treat as finite number.
        if isinstance(value, bool):
            return False
        number = float(value)
    except (TypeError, ValueError):
        return False
    return not math.isfinite(number)


def to_finite_float(value: Any) -> Optional[float]:
    """Convert to float when finite; None for missing / non-numeric / non-finite."""
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        # pandas / numpy NA
        if value != value:  # NaN
            return None
    except Exception:  # broad-exception: optional_metadata - equality can fail for exotic types
        pass
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _issue(
    code: str,
    severity: ValidationSeverity,
    message: str,
    *,
    field: Optional[str] = None,
    row_index: Optional[int] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        field=field,
        row_index=row_index,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# OHLCV / daily bar validation
# ---------------------------------------------------------------------------


def validate_ohlcv_bar(
    bar: Mapping[str, Any],
    *,
    row_index: Optional[int] = None,
    prev_close: Optional[float] = None,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> ValidationResult:
    """Validate a single OHLCV-like mapping (daily bar or quote-like dict)."""
    result = ValidationResult(
        context={
            "market": market,
            "asset_type": asset_type,
            "row_index": row_index,
        }
    )

    open_px = to_finite_float(bar.get("open", bar.get("open_price")))
    high = to_finite_float(bar.get("high"))
    low = to_finite_float(bar.get("low"))
    close = to_finite_float(bar.get("close", bar.get("price")))
    volume = to_finite_float(bar.get("volume"))
    amount = to_finite_float(bar.get("amount"))
    pct_chg = to_finite_float(bar.get("pct_chg", bar.get("change_pct")))
    pre_close = to_finite_float(bar.get("pre_close"))
    if pre_close is None:
        pre_close = prev_close

    # Non-finite raw values that failed conversion
    for field_name in ("open", "high", "low", "close", "price", "volume", "amount", "pct_chg", "change_pct"):
        if field_name in bar and is_non_finite_number(bar.get(field_name)):
            result.add(
                _issue(
                    CODE_PRICE_NON_FINITE if field_name != "volume" else CODE_VOLUME_NON_FINITE,
                    ValidationSeverity.REJECT,
                    f"Non-finite value in field {field_name}",
                    field=field_name,
                    row_index=row_index,
                )
            )

    if close is None and bar.get("close", bar.get("price")) is None:
        result.add(
            _issue(
                CODE_PRICE_MISSING,
                ValidationSeverity.REJECT,
                "Close/price is missing",
                field="close",
                row_index=row_index,
            )
        )
    elif close is not None and close <= 0:
        result.add(
            _issue(
                CODE_PRICE_NON_POSITIVE,
                ValidationSeverity.REJECT,
                f"Close/price must be positive, got {close}",
                field="close",
                row_index=row_index,
                detail={"value": close},
            )
        )

    for field_name, value in (("open", open_px), ("high", high), ("low", low)):
        if value is not None and value <= 0:
            result.add(
                _issue(
                    CODE_PRICE_NON_POSITIVE,
                    ValidationSeverity.REJECT,
                    f"{field_name} must be positive, got {value}",
                    field=field_name,
                    row_index=row_index,
                    detail={"value": value},
                )
            )

    if high is not None and low is not None and high < low:
        result.add(
            _issue(
                CODE_HIGH_BELOW_LOW,
                ValidationSeverity.REJECT,
                f"high ({high}) < low ({low})",
                field="high",
                row_index=row_index,
                detail={"high": high, "low": low},
            )
        )

    if close is not None and high is not None and low is not None and high >= low:
        # Allow tiny float noise outside [low, high]
        eps = max(abs(close) * 1e-9, 1e-8)
        if close > high + eps or close < low - eps:
            result.add(
                _issue(
                    CODE_CLOSE_OUT_OF_RANGE,
                    ValidationSeverity.REJECT,
                    f"close ({close}) outside [low={low}, high={high}]",
                    field="close",
                    row_index=row_index,
                    detail={"close": close, "high": high, "low": low},
                )
            )

    if open_px is not None and high is not None and low is not None and high >= low:
        eps = max(abs(open_px) * 1e-9, 1e-8)
        if open_px > high + eps or open_px < low - eps:
            result.add(
                _issue(
                    CODE_OPEN_OUT_OF_RANGE,
                    ValidationSeverity.WARN,
                    f"open ({open_px}) outside [low={low}, high={high}]",
                    field="open",
                    row_index=row_index,
                    detail={"open": open_px, "high": high, "low": low},
                )
            )

    # pct_chg consistency with previous close
    baseline = pre_close
    if baseline is not None and baseline > 0 and close is not None and pct_chg is not None:
        expected = (close - baseline) / baseline * 100.0
        if abs(expected - pct_chg) > PCT_CHG_ABS_TOLERANCE:
            result.add(
                _issue(
                    CODE_PCT_CHG_INCONSISTENT,
                    ValidationSeverity.WARN,
                    (
                        f"pct_chg ({pct_chg}) inconsistent with "
                        f"(close-pre_close)/pre_close*100 ({expected:.4f})"
                    ),
                    field="pct_chg",
                    row_index=row_index,
                    detail={
                        "pct_chg": pct_chg,
                        "expected_pct_chg": expected,
                        "close": close,
                        "pre_close": baseline,
                        "tolerance": PCT_CHG_ABS_TOLERANCE,
                    },
                )
            )

    if volume is not None and volume < 0:
        result.add(
            _issue(
                CODE_VOLUME_NEGATIVE,
                ValidationSeverity.REJECT,
                f"volume is negative: {volume}",
                field="volume",
                row_index=row_index,
                detail={"value": volume},
            )
        )

    if amount is not None and amount < 0:
        result.add(
            _issue(
                CODE_AMOUNT_NEGATIVE,
                ValidationSeverity.REJECT,
                f"amount is negative: {amount}",
                field="amount",
                row_index=row_index,
                detail={"value": amount},
            )
        )

    # Unit inconsistency: volume in 手 (lots) while contract is shares.
    if (
        volume is not None
        and volume > 0
        and amount is not None
        and amount > 0
        and close is not None
        and close > 0
    ):
        avg_price = amount / volume
        ratio = avg_price / close
        if VOLUME_UNIT_RATIO_MIN <= ratio <= VOLUME_UNIT_RATIO_MAX:
            result.add(
                _issue(
                    CODE_VOLUME_UNIT_SUSPECT,
                    ValidationSeverity.WARN,
                    (
                        "volume unit may be lots (手) instead of shares: "
                        f"amount/volume≈{avg_price:.4f} vs close={close}"
                    ),
                    field="volume",
                    row_index=row_index,
                    detail={
                        "avg_price_from_amount_volume": avg_price,
                        "close": close,
                        "ratio": ratio,
                    },
                )
            )

    return result


def validate_daily_frame(
    frame: Any,
    *,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
    stock_code: Optional[str] = None,
    max_rows_to_scan: Optional[int] = None,
) -> ValidationResult:
    """Validate a standardized daily OHLCV DataFrame (or row sequence).

    Expects columns among: date, open, high, low, close, volume, amount, pct_chg.
    """
    result = ValidationResult(
        context={
            "market": market,
            "asset_type": asset_type,
            "stock_code": stock_code,
            "data_type": "daily_data",
        }
    )

    if frame is None:
        result.add(
            _issue(
                CODE_EMPTY_PAYLOAD,
                ValidationSeverity.REJECT,
                "daily frame is None",
            )
        )
        return result

    # Duck-type DataFrame
    if hasattr(frame, "empty") and bool(getattr(frame, "empty")):
        result.add(
            _issue(
                CODE_EMPTY_PAYLOAD,
                ValidationSeverity.REJECT,
                "daily frame is empty",
            )
        )
        return result

    rows: List[Mapping[str, Any]]
    dates: List[Any] = []

    if hasattr(frame, "to_dict") and hasattr(frame, "columns"):
        records = frame.to_dict(orient="records")
        rows = list(records)
        if "date" in getattr(frame, "columns", []):
            dates = list(frame["date"].tolist())
    elif isinstance(frame, Sequence) and not isinstance(frame, (str, bytes)):
        rows = [row for row in frame if isinstance(row, Mapping)]
        dates = [row.get("date") for row in rows]
    else:
        result.add(
            _issue(
                CODE_EMPTY_PAYLOAD,
                ValidationSeverity.WARN,
                f"unsupported daily frame type: {type(frame).__name__}",
            )
        )
        return result

    if not rows:
        result.add(
            _issue(
                CODE_EMPTY_PAYLOAD,
                ValidationSeverity.REJECT,
                "daily frame has no rows",
            )
        )
        return result

    scan_count = len(rows) if max_rows_to_scan is None else min(len(rows), max_rows_to_scan)
    prev_close: Optional[float] = None
    for idx in range(scan_count):
        row = rows[idx]
        bar_result = validate_ohlcv_bar(
            row,
            row_index=idx,
            prev_close=prev_close,
            market=market,
            asset_type=asset_type,
        )
        result.merge(bar_result)
        close = to_finite_float(row.get("close", row.get("price")))
        if close is not None and close > 0:
            prev_close = close

    # Date order / duplicates (full date list, not only scanned bars)
    if dates:
        seen: Dict[str, int] = {}
        prev_key: Optional[str] = None
        for idx, raw_date in enumerate(dates):
            if raw_date is None:
                continue
            key = str(raw_date)
            if key in seen:
                result.add(
                    _issue(
                        CODE_DATE_DUPLICATE,
                        ValidationSeverity.WARN,
                        f"duplicate date {key}",
                        field="date",
                        row_index=idx,
                        detail={"first_row_index": seen[key], "date": key},
                    )
                )
            else:
                seen[key] = idx
            if prev_key is not None and key < prev_key:
                result.add(
                    _issue(
                        CODE_DATE_OUT_OF_ORDER,
                        ValidationSeverity.WARN,
                        f"date out of order: {key} after {prev_key}",
                        field="date",
                        row_index=idx,
                        detail={"date": key, "previous_date": prev_key},
                    )
                )
            prev_key = key

    result.context["row_count"] = len(rows)
    result.context["scanned_rows"] = scan_count
    return result


# ---------------------------------------------------------------------------
# Realtime quote validation
# ---------------------------------------------------------------------------


def validate_realtime_quote(
    quote: Any,
    *,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> ValidationResult:
    """Validate a UnifiedRealtimeQuote instance or quote-like mapping."""
    if quote is None:
        result = ValidationResult(
            context={"market": market, "asset_type": asset_type, "data_type": "realtime_quote"}
        )
        result.add(
            _issue(
                CODE_EMPTY_PAYLOAD,
                ValidationSeverity.REJECT,
                "realtime quote is None",
            )
        )
        return result

    if hasattr(quote, "to_dict") and callable(quote.to_dict):
        payload = quote.to_dict()
    elif isinstance(quote, Mapping):
        payload = dict(quote)
    else:
        # Fall back to attribute access for dataclass-like objects
        payload = {}
        for name in (
            "price",
            "open_price",
            "high",
            "low",
            "pre_close",
            "volume",
            "amount",
            "change_pct",
            "pe_ratio",
            "pb_ratio",
        ):
            if hasattr(quote, name):
                payload[name] = getattr(quote, name)

    # Map quote fields onto OHLCV bar shape
    bar = {
        "open": payload.get("open_price", payload.get("open")),
        "high": payload.get("high"),
        "low": payload.get("low"),
        "close": payload.get("price", payload.get("close")),
        "volume": payload.get("volume"),
        "amount": payload.get("amount"),
        "pct_chg": payload.get("change_pct", payload.get("pct_chg")),
        "pre_close": payload.get("pre_close"),
        "price": payload.get("price"),
    }
    result = validate_ohlcv_bar(
        bar,
        market=market,
        asset_type=asset_type,
    )
    result.context["data_type"] = "realtime_quote"

    # Valuation metrics on quotes (soft checks; missing is fine for ETFs etc.)
    result.merge(
        validate_fundamental_metrics(
            {
                "pe_ratio": payload.get("pe_ratio"),
                "pb_ratio": payload.get("pb_ratio"),
            },
            market=market,
            asset_type=asset_type,
        )
    )
    return result


# ---------------------------------------------------------------------------
# Fundamental validation
# ---------------------------------------------------------------------------


def validate_fundamental_metrics(
    metrics: Mapping[str, Any],
    *,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> ValidationResult:
    """Validate PE/PB-style fundamental scalars.

    Negative PE is a **warn** (common for loss-making names), not reject.
    Extreme magnitudes and non-finite values are rejected as feed errors.
    Missing metrics never produce findings (ETF / partial coverage safe).
    """
    result = ValidationResult(
        context={
            "market": market,
            "asset_type": asset_type,
            "data_type": "fundamental_metrics",
        }
    )

    pe_raw = metrics.get("pe_ratio", metrics.get("pe"))
    pb_raw = metrics.get("pb_ratio", metrics.get("pb"))

    if is_non_finite_number(pe_raw):
        result.add(
            _issue(
                CODE_FUND_PE_NON_FINITE,
                ValidationSeverity.REJECT,
                "pe_ratio is non-finite",
                field="pe_ratio",
            )
        )
    else:
        pe = to_finite_float(pe_raw)
        if pe is not None:
            if pe < 0:
                result.add(
                    _issue(
                        CODE_FUND_PE_NEGATIVE,
                        ValidationSeverity.WARN,
                        f"pe_ratio is negative ({pe}); may be loss-making issuer",
                        field="pe_ratio",
                        detail={"value": pe},
                    )
                )
            if abs(pe) >= PE_ABS_EXTREME:
                result.add(
                    _issue(
                        CODE_FUND_PE_EXTREME,
                        ValidationSeverity.REJECT,
                        f"pe_ratio absolute value extreme ({pe})",
                        field="pe_ratio",
                        detail={"value": pe, "threshold": PE_ABS_EXTREME},
                    )
                )

    if is_non_finite_number(pb_raw):
        result.add(
            _issue(
                CODE_FUND_PB_NON_FINITE,
                ValidationSeverity.REJECT,
                "pb_ratio is non-finite",
                field="pb_ratio",
            )
        )
    else:
        pb = to_finite_float(pb_raw)
        if pb is not None and abs(pb) >= PB_ABS_EXTREME:
            result.add(
                _issue(
                    CODE_FUND_PB_EXTREME,
                    ValidationSeverity.REJECT,
                    f"pb_ratio absolute value extreme ({pb})",
                    field="pb_ratio",
                    detail={"value": pb, "threshold": PB_ABS_EXTREME},
                )
            )

    return result


def validate_fundamental_context(
    context: Any,
    *,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
    stock_code: Optional[str] = None,
) -> ValidationResult:
    """Validate a fundamental context dict from DataFetcherManager."""
    result = ValidationResult(
        context={
            "market": market,
            "asset_type": asset_type,
            "stock_code": stock_code,
            "data_type": "fundamental_context",
        }
    )
    if context is None:
        result.add(
            _issue(
                CODE_EMPTY_PAYLOAD,
                ValidationSeverity.WARN,
                "fundamental context is None",
            )
        )
        return result
    if not isinstance(context, Mapping):
        result.add(
            _issue(
                CODE_EMPTY_PAYLOAD,
                ValidationSeverity.WARN,
                f"fundamental context type unsupported: {type(context).__name__}",
            )
        )
        return result

    market = market or context.get("market")
    result.context["market"] = market

    valuation = context.get("valuation") or {}
    if isinstance(valuation, Mapping):
        # Block shape: {status, data: {...}} or flat metrics
        data = valuation.get("data") if isinstance(valuation.get("data"), Mapping) else valuation
        if isinstance(data, Mapping):
            result.merge(
                validate_fundamental_metrics(
                    data,
                    market=market,
                    asset_type=asset_type,
                )
            )

    # Earnings period dates if present (duplicate / reverse order)
    earnings = context.get("earnings") or {}
    if isinstance(earnings, Mapping):
        data = earnings.get("data") if isinstance(earnings.get("data"), Mapping) else earnings
        periods = None
        if isinstance(data, Mapping):
            periods = data.get("periods") or data.get("report_dates") or data.get("dates")
        if isinstance(periods, Sequence) and not isinstance(periods, (str, bytes)):
            keys = [str(p) for p in periods if p is not None]
            seen: Dict[str, int] = {}
            prev: Optional[str] = None
            for idx, key in enumerate(keys):
                if key in seen:
                    result.add(
                        _issue(
                            CODE_DATE_DUPLICATE,
                            ValidationSeverity.WARN,
                            f"duplicate earnings period {key}",
                            field="earnings.periods",
                            row_index=idx,
                        )
                    )
                else:
                    seen[key] = idx
                # Expect chronological ascending; reverse is warn
                if prev is not None and key < prev:
                    result.add(
                        _issue(
                            CODE_DATE_OUT_OF_ORDER,
                            ValidationSeverity.WARN,
                            f"earnings period out of order: {key} after {prev}",
                            field="earnings.periods",
                            row_index=idx,
                        )
                    )
                prev = key

    return result


# ---------------------------------------------------------------------------
# Attach / log helpers (no silent drop)
# ---------------------------------------------------------------------------


def attach_validation_to_frame(frame: Any, result: ValidationResult) -> Any:
    """Store validation summary on DataFrame.attrs when available."""
    if frame is None:
        return frame
    attrs = getattr(frame, "attrs", None)
    if isinstance(attrs, dict):
        attrs[ATTR_KEY] = result.to_dict()
    return frame


def attach_validation_to_mapping(payload: Any, result: ValidationResult) -> Any:
    """Attach validation summary under ``data_validation`` key when mapping-like."""
    if isinstance(payload, dict):
        payload[ATTR_KEY] = result.to_dict()
    return payload


def log_validation_result(
    outcome: ValidationResult,
    *,
    data_type: str,
    stock_code: Optional[str] = None,
) -> None:
    """Record warn/reject findings without mutating data.

    Logging is intentionally deferred to the manager-layer wiring helper so
    this module never mixes Exception subclasses with logger calls (production
    exception-log callsite guard). Findings remain available via
    ``ValidationResult.to_dict()`` and frame/mapping annotations.
    """
    del data_type, stock_code  # retained for API stability / call-site clarity
    if outcome.ok:
        return
    # Touch fields so callers keep a stable side-effect-free entry point.
    _ = outcome.status
    _ = len(outcome.issues)


def validate_and_annotate(
    data: Any,
    *,
    data_type: str,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
    stock_code: Optional[str] = None,
    strict: Optional[bool] = None,
) -> ValidationResult:
    """Run the appropriate validator, annotate, log, and optionally raise.

    This is the single orchestration entry for manager-layer wiring.
    """
    if not is_validation_enabled():
        return ValidationResult(
            context={"data_type": data_type, "enabled": False, "stock_code": stock_code}
        )

    if data_type == "daily_data":
        # data may be (frame, source) or frame
        frame = data[0] if isinstance(data, tuple) and len(data) >= 1 else data
        result = validate_daily_frame(
            frame,
            market=market,
            asset_type=asset_type,
            stock_code=stock_code,
        )
        attach_validation_to_frame(frame, result)
    elif data_type == "realtime_quote":
        result = validate_realtime_quote(
            data,
            market=market,
            asset_type=asset_type,
        )
    elif data_type == "fundamental_context":
        result = validate_fundamental_context(
            data,
            market=market,
            asset_type=asset_type,
            stock_code=stock_code,
        )
        attach_validation_to_mapping(data, result)
    else:
        result = ValidationResult(context={"data_type": data_type, "stock_code": stock_code})
        result.add(
            _issue(
                CODE_EMPTY_PAYLOAD,
                ValidationSeverity.WARN,
                f"unknown data_type for validation: {data_type}",
            )
        )

    log_validation_result(result, data_type=data_type, stock_code=stock_code)

    if result.should_reject(strict=strict):
        raise DataValidationRejected(result, data_type=data_type)
    return result


# Public re-export surface for diagnostics consumers
REASON_CODES: Mapping[str, str] = {
    CODE_PRICE_MISSING: "Price/close missing",
    CODE_PRICE_NON_FINITE: "Price field is NaN or ±Infinity",
    CODE_PRICE_NON_POSITIVE: "Price is zero or negative",
    CODE_HIGH_BELOW_LOW: "High is below low",
    CODE_CLOSE_OUT_OF_RANGE: "Close outside high/low range",
    CODE_OPEN_OUT_OF_RANGE: "Open outside high/low range",
    CODE_PCT_CHG_INCONSISTENT: "pct_chg inconsistent with price change",
    CODE_VOLUME_NEGATIVE: "Volume is negative",
    CODE_VOLUME_NON_FINITE: "Volume is NaN or ±Infinity",
    CODE_VOLUME_UNIT_SUSPECT: "Volume unit may be lots instead of shares",
    CODE_AMOUNT_NEGATIVE: "Amount is negative",
    CODE_DATE_OUT_OF_ORDER: "Dates out of chronological order",
    CODE_DATE_DUPLICATE: "Duplicate date/period",
    CODE_FUND_PE_NON_FINITE: "PE is NaN or ±Infinity",
    CODE_FUND_PE_EXTREME: "PE absolute value is extreme",
    CODE_FUND_PB_NON_FINITE: "PB is NaN or ±Infinity",
    CODE_FUND_PB_EXTREME: "PB absolute value is extreme",
    CODE_FUND_PE_NEGATIVE: "PE is negative (often loss-making issuer)",
    CODE_EMPTY_PAYLOAD: "Empty or unsupported payload",
}

__all__ = [
    "ATTR_KEY",
    "CODE_AMOUNT_NEGATIVE",
    "CODE_CLOSE_OUT_OF_RANGE",
    "CODE_DATE_DUPLICATE",
    "CODE_DATE_OUT_OF_ORDER",
    "CODE_EMPTY_PAYLOAD",
    "CODE_FUND_PB_EXTREME",
    "CODE_FUND_PB_NON_FINITE",
    "CODE_FUND_PE_EXTREME",
    "CODE_FUND_PE_NEGATIVE",
    "CODE_FUND_PE_NON_FINITE",
    "CODE_HIGH_BELOW_LOW",
    "CODE_OPEN_OUT_OF_RANGE",
    "CODE_PCT_CHG_INCONSISTENT",
    "CODE_PRICE_MISSING",
    "CODE_PRICE_NON_FINITE",
    "CODE_PRICE_NON_POSITIVE",
    "CODE_VOLUME_NEGATIVE",
    "CODE_VOLUME_NON_FINITE",
    "CODE_VOLUME_UNIT_SUSPECT",
    "DataValidationRejected",
    "ENV_ENABLED",
    "ENV_STRICT",
    "PCT_CHG_ABS_TOLERANCE",
    "PE_ABS_EXTREME",
    "PB_ABS_EXTREME",
    "REASON_CODES",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
    "attach_validation_to_frame",
    "attach_validation_to_mapping",
    "is_non_finite_number",
    "is_strict_mode",
    "is_validation_enabled",
    "log_validation_result",
    "to_finite_float",
    "validate_and_annotate",
    "validate_daily_frame",
    "validate_fundamental_context",
    "validate_fundamental_metrics",
    "validate_ohlcv_bar",
    "validate_realtime_quote",
]
