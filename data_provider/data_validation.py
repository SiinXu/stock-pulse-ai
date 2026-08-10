# -*- coding: utf-8 -*-
"""Validated, observable financial-data boundary contracts.

The validators in this module are pure except for the explicit
``validate_and_annotate`` orchestration entry point. Provider candidates use
that entry point before acceptance and caching; callers in warn-only mode keep
their established return values while receiving versioned evidence.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


EVIDENCE_SCHEMA_VERSION = "data_quality_evidence.v1"
ATTR_KEY = "data_validation"

MAX_EVIDENCE_ISSUES = 24
MAX_EVIDENCE_TEXT = 160

PCT_CHG_ABS_TOLERANCE = 0.51
VOLUME_UNIT_RATIO_MIN = 80.0
VOLUME_UNIT_RATIO_MAX = 120.0
PE_ABS_EXTREME = 50_000.0
PB_ABS_EXTREME = 10_000.0

CODE_DATE_OUT_OF_ORDER = "dv_daily_date_out_of_order"
CODE_DATE_DUPLICATE = "dv_daily_date_duplicate"
CODE_FUND_PE_INVALID_TYPE = "dv_fund_pe_invalid_type"
CODE_FUND_PE_NON_FINITE = "dv_fund_pe_non_finite"
CODE_FUND_PE_EXTREME = "dv_fund_pe_out_of_range"
CODE_FUND_PB_INVALID_TYPE = "dv_fund_pb_invalid_type"
CODE_FUND_PB_NON_FINITE = "dv_fund_pb_non_finite"
CODE_FUND_PB_EXTREME = "dv_fund_pb_out_of_range"
CODE_FUND_PE_NEGATIVE = "dv_fund_pe_negative"
CODE_EMPTY_PAYLOAD = "dv_payload_empty"

_MARKETS = frozenset({"cn", "hk", "us", "jp", "kr", "tw"})
_INSTRUMENT_TYPES = frozenset({"equity", "etf", "index"})
_TECHNICAL_CONTRACTS: Mapping[str, Tuple[Optional[float], Optional[float]]] = {
    "ma5": (0.0, None),
    "ma10": (0.0, None),
    "ma20": (0.0, None),
    "bias_ma5": (-100.0, None),
    "bias_ma10": (-100.0, None),
    "trend_strength": (0.0, 100.0),
    "signal_score": (0.0, 100.0),
}
_SEVERITY_RANK = {"pass": 0, "warn": 1, "reject": 2}


class ValidationSeverity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    REJECT = "reject"


class NumericKind(str, Enum):
    MISSING = "missing"
    INVALID_TYPE = "invalid_type"
    NON_FINITE = "non_finite"
    FINITE = "finite"


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: ValidationSeverity
    message: str
    field: Optional[str] = None
    row_index: Optional[int] = None
    detail: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "code": _bounded_text(self.code, 96),
            "severity": self.severity.value,
            "message": _bounded_text(self.message, MAX_EVIDENCE_TEXT),
        }
        if self.field is not None:
            payload["field"] = _bounded_text(self.field, 96)
        if self.row_index is not None:
            payload["row_index"] = max(0, int(self.row_index))
        if self.detail:
            payload["detail"] = _json_safe(self.detail)
        return payload


@dataclass
class ValidationResult:
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
        return any(issue.severity == ValidationSeverity.WARN for issue in self.issues)

    def add(self, issue: ValidationIssue) -> None:
        self.issues.append(issue)
        if _SEVERITY_RANK[issue.severity.value] > _SEVERITY_RANK[self.status.value]:
            self.status = issue.severity

    def extend(self, issues: Iterable[ValidationIssue]) -> None:
        for issue in issues:
            self.add(issue)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.extend(other.issues)
        for key, value in other.context.items():
            self.context.setdefault(key, value)
        return self

    def should_reject(
        self,
        *,
        strict: Optional[bool] = None,
        market: Optional[str] = None,
        instrument_type: Optional[str] = None,
    ) -> bool:
        if strict is None:
            strict = is_strict_mode(
                market=market or self.context.get("market"),
                instrument_type=(
                    instrument_type
                    or self.context.get("instrument_type")
                    or self.context.get("asset_type")
                ),
            )
        return bool(strict) and self.has_reject

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "issues": [issue.to_dict() for issue in self.issues[:MAX_EVIDENCE_ISSUES]],
            "issue_count": len(self.issues),
            "truncated": len(self.issues) > MAX_EVIDENCE_ISSUES,
            "context": _json_safe(self.context),
        }

    def to_evidence(
        self,
        *,
        data_type: str,
        stock_code: Optional[str] = None,
        provider: Optional[str] = None,
        market: Optional[str] = None,
        instrument_type: Optional[str] = None,
        rejected: bool = False,
        provenance: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        evidence = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "data_type": _bounded_text(data_type, 64),
            "severity": self.status.value,
            "symbol": _bounded_optional_text(stock_code, 80),
            "provider": _bounded_optional_text(provider, 120),
            "market": canonical_market(market),
            "instrument_type": canonical_instrument_type(instrument_type),
            "rejected": bool(rejected),
            "issue_count": len(self.issues),
            "issues": [issue.to_dict() for issue in self.issues[:MAX_EVIDENCE_ISSUES]],
            "truncated": len(self.issues) > MAX_EVIDENCE_ISSUES,
        }
        safe_provenance = _json_safe(provenance or {})
        if safe_provenance:
            evidence["provenance"] = safe_provenance
        return evidence


class DataValidationRejected(Exception):
    """Provider candidate rejection with bounded, serializable reason evidence."""

    def __init__(
        self,
        validation: ValidationResult,
        *,
        data_type: str = "unknown",
        evidence: Optional[Mapping[str, Any]] = None,
    ):
        self.validation_payload = validation.to_dict()
        self.data_type = data_type
        self.evidence = dict(evidence or {})
        self.reason_codes = tuple(
            sorted(
                {
                    issue.code
                    for issue in validation.issues
                    if issue.severity == ValidationSeverity.REJECT
                }
            )
        )
        super().__init__(
            "data validation rejected "
            f"data_type={_bounded_text(data_type, 64)} "
            f"codes={','.join(self.reason_codes) or 'unknown'}"
        )


def _bounded_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _bounded_optional_text(value: Any, limit: int) -> Optional[str]:
    text = _bounded_text(value, limit)
    return text or None


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    """Return a finite, bounded value accepted by strict JSON encoders."""
    if depth > 4:
        return "<truncated>"
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        return _bounded_text(value, MAX_EVIDENCE_TEXT)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return _json_safe(value.value, depth=depth + 1)
    if isinstance(value, Mapping):
        payload: Dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 24:
                payload["truncated"] = True
                break
            payload[_bounded_text(key, 80)] = _json_safe(item, depth=depth + 1)
        return payload
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [_json_safe(item, depth=depth + 1) for item in list(value)[:24]]
    return _bounded_text(value, MAX_EVIDENCE_TEXT)


def _validation_config() -> Any:
    """Resolve validation policy through the repository configuration owner."""
    from src.application_services import get_application_services

    return get_application_services().config


def is_validation_enabled() -> bool:
    return bool(getattr(_validation_config(), "data_validation_enabled", True))


def canonical_market(value: Optional[str]) -> str:
    normalized = str(value or "unknown").strip().lower()
    aliases = {"a": "cn", "a_share": "cn", "china": "cn", "usa": "us"}
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _MARKETS else "unknown"


def canonical_instrument_type(value: Optional[str]) -> str:
    normalized = str(value or "equity").strip().lower()
    aliases = {
        "stock": "equity",
        "share": "equity",
        "fund": "etf",
        "indices": "index",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in _INSTRUMENT_TYPES else "equity"


def infer_instrument_type(
    stock_code: Optional[str],
    *,
    explicit: Optional[str] = None,
) -> str:
    if explicit:
        return canonical_instrument_type(explicit)
    code = str(stock_code or "").strip()
    try:
        from data_provider.symbol_normalization import normalize_stock_code

        canonical_code = normalize_stock_code(code).upper()
        raw_overrides = str(
            getattr(
                _validation_config(),
                "data_validation_instrument_overrides",
                "",
            )
            or ""
        )
        for raw_item in raw_overrides.split(","):
            symbol, separator, raw_type = raw_item.strip().partition("=")
            if not separator:
                continue
            if normalize_stock_code(symbol).upper() != canonical_code:
                continue
            normalized_type = str(raw_type).strip().lower()
            if normalized_type in _INSTRUMENT_TYPES:
                return normalized_type
    except (ImportError, RuntimeError, TypeError, ValueError):
        pass
    try:
        from data_provider.symbol_normalization import _is_etf_code
        from data_provider.us_index_mapping import is_us_index_code

        if is_us_index_code(code):
            return "index"
        if _is_etf_code(code):
            return "etf"
    except (ImportError, TypeError, ValueError):
        pass
    return "equity"


def _strict_scope_matches(
    market: str,
    instrument_type: str,
    raw: str,
) -> bool:
    valid_scopes = []
    for scope in (item.strip().lower() for item in raw.split(",")):
        if "/" not in scope:
            continue
        scope_market, scope_instrument = (part.strip() for part in scope.split("/", 1))
        if scope_market not in _MARKETS | {"*"}:
            continue
        if scope_instrument not in _INSTRUMENT_TYPES | {"*"}:
            continue
        valid_scopes.append((scope_market, scope_instrument))
    for scope_market, scope_instrument in valid_scopes or [("*", "*")]:
        if scope_market in {"*", market} and scope_instrument in {"*", instrument_type}:
            return True
    return False


def is_strict_mode(
    *,
    market: Optional[str] = None,
    instrument_type: Optional[str] = None,
) -> bool:
    config = _validation_config()
    if not bool(getattr(config, "data_validation_strict", False)):
        return False
    return _strict_scope_matches(
        canonical_market(market),
        canonical_instrument_type(instrument_type),
        str(getattr(config, "data_validation_strict_scopes", "*/*") or "*/*"),
    )


def upper_layer_rejection_enabled() -> bool:
    return (
        getattr(_validation_config(), "data_validation_upper_layer_mode", "warn")
        == "reject"
    )


def classify_numeric(value: Any) -> Tuple[NumericKind, Optional[float]]:
    """Classify every numeric input using one repository-wide contract."""
    if value is None:
        return NumericKind.MISSING, None
    if isinstance(value, str) and value.strip() in {"", "-", "--", "N/A", "n/a"}:
        return NumericKind.MISSING, None
    value_type = type(value)
    if isinstance(value, bool) or (
        value_type.__name__ in {"bool", "bool_"}
        and value_type.__module__.split(".", 1)[0] == "numpy"
    ):
        return NumericKind.INVALID_TYPE, None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return NumericKind.INVALID_TYPE, None
    if not math.isfinite(number):
        return NumericKind.NON_FINITE, None
    return NumericKind.FINITE, number


def _issue(
    code: str,
    severity: ValidationSeverity,
    message: str,
    *,
    field: Optional[str] = None,
    row_index: Optional[int] = None,
    detail: Optional[Dict[str, Any]] = None,
) -> ValidationIssue:
    return ValidationIssue(code, severity, message, field, row_index, detail)


def _numeric_code(namespace: str, field_name: str, kind: str) -> str:
    normalized = field_name.replace(".", "_")
    return f"dv_{namespace}_{normalized}_{kind}"


def _validate_numeric_field(
    result: ValidationResult,
    *,
    namespace: str,
    field_name: str,
    raw_value: Any,
    required: bool = False,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    minimum_exclusive: bool = False,
    row_index: Optional[int] = None,
) -> Optional[float]:
    kind, number = classify_numeric(raw_value)
    if kind == NumericKind.MISSING:
        if required:
            result.add(
                _issue(
                    _numeric_code(namespace, field_name, "missing"),
                    ValidationSeverity.REJECT,
                    f"{field_name} is missing",
                    field=field_name,
                    row_index=row_index,
                )
            )
        return None
    if kind == NumericKind.INVALID_TYPE:
        result.add(
            _issue(
                _numeric_code(namespace, field_name, "invalid_type"),
                ValidationSeverity.REJECT,
                f"{field_name} is not numeric",
                field=field_name,
                row_index=row_index,
            )
        )
        return None
    if kind == NumericKind.NON_FINITE:
        result.add(
            _issue(
                _numeric_code(namespace, field_name, "non_finite"),
                ValidationSeverity.REJECT,
                f"{field_name} is not finite",
                field=field_name,
                row_index=row_index,
            )
        )
        return None
    assert number is not None
    below_minimum = minimum is not None and (
        number <= minimum if minimum_exclusive else number < minimum
    )
    above_maximum = maximum is not None and number > maximum
    if below_minimum or above_maximum:
        result.add(
            _issue(
                _numeric_code(namespace, field_name, "out_of_range"),
                ValidationSeverity.REJECT,
                f"{field_name} is outside its accepted range",
                field=field_name,
                row_index=row_index,
                detail={"value": number, "minimum": minimum, "maximum": maximum},
            )
        )
    return number


def validate_ohlcv_bar(
    bar: Mapping[str, Any],
    *,
    row_index: Optional[int] = None,
    prev_close: Optional[float] = None,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
    namespace: str = "ohlcv",
) -> ValidationResult:
    instrument_type = canonical_instrument_type(asset_type)
    result = ValidationResult(
        context={
            "market": canonical_market(market),
            "instrument_type": instrument_type,
            "row_index": row_index,
        }
    )
    price_field = "price" if namespace == "quote" else "close"
    raw_values = {
        "open": bar.get("open", bar.get("open_price")),
        "high": bar.get("high"),
        "low": bar.get("low"),
        price_field: bar.get("price", bar.get("close")) if namespace == "quote" else bar.get("close", bar.get("price")),
        "volume": bar.get("volume"),
        "amount": bar.get("amount"),
        "pct_chg": bar.get("pct_chg", bar.get("change_pct")),
        "pre_close": bar.get("pre_close"),
    }
    values: Dict[str, Optional[float]] = {}
    for field_name in ("open", "high", "low"):
        values[field_name] = _validate_numeric_field(
            result,
            namespace=namespace,
            field_name=field_name,
            raw_value=raw_values[field_name],
            minimum=0.0,
            minimum_exclusive=True,
            row_index=row_index,
        )
    values[price_field] = _validate_numeric_field(
        result,
        namespace=namespace,
        field_name=price_field,
        raw_value=raw_values[price_field],
        required=True,
        minimum=0.0,
        minimum_exclusive=True,
        row_index=row_index,
    )
    values["volume"] = _validate_numeric_field(
        result,
        namespace=namespace,
        field_name="volume",
        raw_value=raw_values["volume"],
        minimum=0.0,
        row_index=row_index,
    )
    values["amount"] = _validate_numeric_field(
        result,
        namespace=namespace,
        field_name="amount",
        raw_value=raw_values["amount"],
        minimum=0.0,
        row_index=row_index,
    )
    values["pct_chg"] = _validate_numeric_field(
        result,
        namespace=namespace,
        field_name="pct_chg",
        raw_value=raw_values["pct_chg"],
        row_index=row_index,
    )
    pre_close = _validate_numeric_field(
        result,
        namespace=namespace,
        field_name="pre_close",
        raw_value=raw_values["pre_close"],
        minimum=0.0,
        minimum_exclusive=True,
        row_index=row_index,
    )
    if pre_close is None:
        pre_close = prev_close

    close = values[price_field]
    high = values["high"]
    low = values["low"]
    open_px = values["open"]
    volume = values["volume"]
    amount = values["amount"]
    pct_chg = values["pct_chg"]

    if high is not None and low is not None and high < low:
        result.add(
            _issue(
                _numeric_code(namespace, "high", "below_low"),
                ValidationSeverity.REJECT,
                "high is below low",
                field="high",
                row_index=row_index,
                detail={"high": high, "low": low},
            )
        )
    if close is not None and high is not None and low is not None and high >= low:
        eps = max(abs(close) * 1e-9, 1e-8)
        if close > high + eps or close < low - eps:
            result.add(
                _issue(
                    _numeric_code(namespace, price_field, "out_of_range"),
                    ValidationSeverity.REJECT,
                    f"{price_field} is outside the high/low range",
                    field=price_field,
                    row_index=row_index,
                    detail={price_field: close, "high": high, "low": low},
                )
            )
    if open_px is not None and high is not None and low is not None and high >= low:
        eps = max(abs(open_px) * 1e-9, 1e-8)
        if open_px > high + eps or open_px < low - eps:
            result.add(
                _issue(
                    _numeric_code(namespace, "open", "outside_range"),
                    ValidationSeverity.WARN,
                    "open is outside the high/low range",
                    field="open",
                    row_index=row_index,
                )
            )
    if pre_close is not None and close is not None and pct_chg is not None:
        expected = (close - pre_close) / pre_close * 100.0
        if abs(expected - pct_chg) > PCT_CHG_ABS_TOLERANCE:
            result.add(
                _issue(
                    _numeric_code(namespace, "pct_chg", "inconsistent"),
                    ValidationSeverity.WARN,
                    "pct_chg is inconsistent with close and pre_close",
                    field="pct_chg",
                    row_index=row_index,
                    detail={
                        "value": pct_chg,
                        "expected": expected,
                        "tolerance": PCT_CHG_ABS_TOLERANCE,
                    },
                )
            )
    if (
        volume is not None
        and volume > 0
        and amount is not None
        and amount > 0
        and close is not None
        and close > 0
    ):
        ratio = (amount / volume) / close
        if VOLUME_UNIT_RATIO_MIN <= ratio <= VOLUME_UNIT_RATIO_MAX:
            result.add(
                _issue(
                    _numeric_code(namespace, "volume", "unit_suspect"),
                    ValidationSeverity.WARN,
                    "volume may be expressed in lots instead of shares",
                    field="volume",
                    row_index=row_index,
                    detail={"ratio": ratio},
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
    instrument_type = infer_instrument_type(stock_code, explicit=asset_type)
    result = ValidationResult(
        context={
            "market": canonical_market(market),
            "instrument_type": instrument_type,
            "stock_code": stock_code,
            "data_type": "daily_data",
        }
    )
    if frame is None or (hasattr(frame, "empty") and bool(frame.empty)):
        result.add(_issue(CODE_EMPTY_PAYLOAD, ValidationSeverity.REJECT, "daily data is empty"))
        return result

    rows: List[Mapping[str, Any]]
    dates: List[Any]
    if hasattr(frame, "to_dict") and hasattr(frame, "columns"):
        rows = list(frame.to_dict(orient="records"))
        dates = list(frame["date"].tolist()) if "date" in frame.columns else []
    elif isinstance(frame, Sequence) and not isinstance(frame, (str, bytes)):
        rows = [row for row in frame if isinstance(row, Mapping)]
        dates = [row.get("date") for row in rows]
    else:
        result.add(_issue(CODE_EMPTY_PAYLOAD, ValidationSeverity.REJECT, "daily data type is unsupported"))
        return result
    if not rows:
        result.add(_issue(CODE_EMPTY_PAYLOAD, ValidationSeverity.REJECT, "daily data has no rows"))
        return result

    scan_count = len(rows) if max_rows_to_scan is None else min(len(rows), max_rows_to_scan)
    prev_close: Optional[float] = None
    for index, row in enumerate(rows[:scan_count]):
        result.merge(
            validate_ohlcv_bar(
                row,
                row_index=index,
                prev_close=prev_close,
                market=market,
                asset_type=instrument_type,
            )
        )
        close_kind, close = classify_numeric(row.get("close", row.get("price")))
        if close_kind == NumericKind.FINITE and close is not None and close > 0:
            prev_close = close

    seen: Dict[str, int] = {}
    previous: Optional[str] = None
    for index, raw_date in enumerate(dates):
        if raw_date is None:
            continue
        key = str(raw_date)
        if key in seen:
            result.add(
                _issue(
                    CODE_DATE_DUPLICATE,
                    ValidationSeverity.WARN,
                    "daily data contains a duplicate date",
                    field="date",
                    row_index=index,
                    detail={"date": key, "first_row_index": seen[key]},
                )
            )
        else:
            seen[key] = index
        if previous is not None and key < previous:
            result.add(
                _issue(
                    CODE_DATE_OUT_OF_ORDER,
                    ValidationSeverity.WARN,
                    "daily dates are out of order",
                    field="date",
                    row_index=index,
                    detail={"date": key, "previous_date": previous},
                )
            )
        previous = key
    result.context.update({"row_count": len(rows), "scanned_rows": scan_count})
    return result


def _mapping_from_value(value: Any) -> Dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        return dict(payload) if isinstance(payload, Mapping) else {}
    return {
        name: getattr(value, name)
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
        )
        if hasattr(value, name)
    }


def validate_realtime_quote(
    quote: Any,
    *,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
    stock_code: Optional[str] = None,
) -> ValidationResult:
    instrument_type = infer_instrument_type(stock_code, explicit=asset_type)
    if quote is None:
        result = ValidationResult(
            context={
                "market": canonical_market(market),
                "instrument_type": instrument_type,
                "data_type": "realtime_quote",
            }
        )
        result.add(_issue(CODE_EMPTY_PAYLOAD, ValidationSeverity.REJECT, "realtime quote is empty"))
        return result
    payload = _mapping_from_value(quote)
    result = validate_ohlcv_bar(
        payload,
        market=market,
        asset_type=instrument_type,
        namespace="quote",
    )
    result.context["data_type"] = "realtime_quote"
    result.merge(
        validate_fundamental_metrics(
            payload,
            market=market,
            asset_type=instrument_type,
        )
    )
    return result


def validate_fundamental_metrics(
    metrics: Mapping[str, Any],
    *,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> ValidationResult:
    instrument_type = canonical_instrument_type(asset_type)
    result = ValidationResult(
        context={
            "market": canonical_market(market),
            "instrument_type": instrument_type,
            "data_type": "fundamental_metrics",
        }
    )
    pe_raw = metrics.get("pe_ratio", metrics.get("pe"))
    pb_raw = metrics.get("pb_ratio", metrics.get("pb"))
    pe_kind, pe = classify_numeric(pe_raw)
    if pe_kind not in {NumericKind.MISSING, NumericKind.FINITE}:
        result.add(
            _issue(
                CODE_FUND_PE_INVALID_TYPE if pe_kind == NumericKind.INVALID_TYPE else CODE_FUND_PE_NON_FINITE,
                ValidationSeverity.REJECT,
                "pe_ratio is invalid" if pe_kind == NumericKind.INVALID_TYPE else "pe_ratio is not finite",
                field="pe_ratio",
            )
        )
    elif pe is not None:
        if pe < 0:
            result.add(
                _issue(
                    CODE_FUND_PE_NEGATIVE,
                    ValidationSeverity.WARN,
                    "negative PE can represent a loss-making issuer",
                    field="pe_ratio",
                    detail={"value": pe},
                )
            )
        if abs(pe) >= PE_ABS_EXTREME:
            result.add(
                _issue(
                    CODE_FUND_PE_EXTREME,
                    ValidationSeverity.REJECT,
                    "pe_ratio is outside the accepted feed range",
                    field="pe_ratio",
                    detail={"value": pe, "absolute_limit": PE_ABS_EXTREME},
                )
            )
    pb_kind, pb = classify_numeric(pb_raw)
    if pb_kind not in {NumericKind.MISSING, NumericKind.FINITE}:
        result.add(
            _issue(
                CODE_FUND_PB_INVALID_TYPE if pb_kind == NumericKind.INVALID_TYPE else CODE_FUND_PB_NON_FINITE,
                ValidationSeverity.REJECT,
                "pb_ratio is invalid" if pb_kind == NumericKind.INVALID_TYPE else "pb_ratio is not finite",
                field="pb_ratio",
            )
        )
    elif pb is not None and abs(pb) >= PB_ABS_EXTREME:
        result.add(
            _issue(
                CODE_FUND_PB_EXTREME,
                ValidationSeverity.REJECT,
                "pb_ratio is outside the accepted feed range",
                field="pb_ratio",
                detail={"value": pb, "absolute_limit": PB_ABS_EXTREME},
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
    instrument_type = infer_instrument_type(stock_code, explicit=asset_type)
    result = ValidationResult(
        context={
            "market": canonical_market(market),
            "instrument_type": instrument_type,
            "stock_code": stock_code,
            "data_type": "fundamental_context",
        }
    )
    if context is None:
        result.add(_issue(CODE_EMPTY_PAYLOAD, ValidationSeverity.WARN, "fundamental context is empty"))
        return result
    if not isinstance(context, Mapping):
        result.add(_issue(CODE_EMPTY_PAYLOAD, ValidationSeverity.REJECT, "fundamental context type is unsupported"))
        return result
    resolved_market = market or context.get("market")
    result.context["market"] = canonical_market(resolved_market)
    valuation = context.get("valuation") or {}
    if isinstance(valuation, Mapping):
        data = valuation.get("data") if isinstance(valuation.get("data"), Mapping) else valuation
        result.merge(
            validate_fundamental_metrics(
                data,
                market=resolved_market,
                asset_type=instrument_type,
            )
        )
    earnings = context.get("earnings") or {}
    if isinstance(earnings, Mapping):
        data = (
            earnings.get("data")
            if isinstance(earnings.get("data"), Mapping)
            else earnings
        )
        periods = None
        if isinstance(data, Mapping):
            periods = (
                data.get("periods")
                or data.get("report_dates")
                or data.get("dates")
            )
        if isinstance(periods, Sequence) and not isinstance(periods, (str, bytes)):
            seen: Dict[str, int] = {}
            previous: Optional[str] = None
            for index, raw_period in enumerate(periods):
                if raw_period is None:
                    continue
                key = str(raw_period)
                if key in seen:
                    result.add(
                        _issue(
                            CODE_DATE_DUPLICATE,
                            ValidationSeverity.WARN,
                            "earnings periods contain a duplicate date",
                            field="earnings.periods",
                            row_index=index,
                        )
                    )
                else:
                    seen[key] = index
                if previous is not None and key < previous:
                    result.add(
                        _issue(
                            CODE_DATE_OUT_OF_ORDER,
                            ValidationSeverity.WARN,
                            "earnings periods are out of order",
                            field="earnings.periods",
                            row_index=index,
                        )
                    )
                previous = key
    return result


def validate_technical_indicators(
    indicators: Any,
    *,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
    stock_code: Optional[str] = None,
) -> ValidationResult:
    instrument_type = infer_instrument_type(stock_code, explicit=asset_type)
    result = ValidationResult(
        context={
            "market": canonical_market(market),
            "instrument_type": instrument_type,
            "stock_code": stock_code,
            "data_type": "technical_indicators",
        }
    )
    payload = _mapping_from_value(indicators)
    if not payload:
        result.add(_issue(CODE_EMPTY_PAYLOAD, ValidationSeverity.WARN, "technical indicators are empty"))
        return result
    for field_name, (minimum, maximum) in _TECHNICAL_CONTRACTS.items():
        if field_name not in payload:
            continue
        _validate_numeric_field(
            result,
            namespace="technical",
            field_name=field_name,
            raw_value=payload.get(field_name),
            minimum=minimum,
            maximum=maximum,
            minimum_exclusive=field_name.startswith("ma"),
        )
    return result


def project_technical_indicators(
    indicators: Any,
    *,
    market: Optional[str] = None,
    instrument_type: Optional[str] = None,
    stock_code: Optional[str] = None,
    provider: str = "StockTrendAnalyzer",
) -> Dict[str, Any]:
    """Validate, record, and return the finite synthesis projection."""
    payload = _mapping_from_value(indicators)
    result = validate_technical_indicators(
        payload,
        market=market,
        asset_type=instrument_type,
        stock_code=stock_code,
    )
    log_validation_result(
        result,
        data_type="technical_indicators",
        stock_code=stock_code,
        provider=provider,
        market=market,
        instrument_type=instrument_type,
        rejected=False,
    )
    rejected_fields = {
        issue.field
        for issue in result.issues
        if issue.severity == ValidationSeverity.REJECT and issue.field
    }
    return {key: value for key, value in payload.items() if key not in rejected_fields}


def attach_validation_to_frame(frame: Any, result: ValidationResult) -> Any:
    attrs = getattr(frame, "attrs", None)
    if isinstance(attrs, dict):
        attrs[ATTR_KEY] = result.to_dict()
    return frame


def log_validation_result(
    outcome: ValidationResult,
    *,
    data_type: str,
    stock_code: Optional[str] = None,
    provider: Optional[str] = None,
    market: Optional[str] = None,
    instrument_type: Optional[str] = None,
    rejected: bool = False,
    provenance: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    evidence = outcome.to_evidence(
        data_type=data_type,
        stock_code=stock_code,
        provider=provider,
        market=market or outcome.context.get("market"),
        instrument_type=(instrument_type or outcome.context.get("instrument_type")),
        rejected=rejected,
        provenance=provenance,
    )
    if outcome.ok:
        return evidence
    from src.services.run_diagnostics import record_data_quality_evidence

    record_data_quality_evidence(
        data_type=evidence["data_type"],
        severity=evidence["severity"],
        symbol=evidence.get("symbol"),
        provider=evidence.get("provider"),
        market=evidence.get("market"),
        instrument_type=evidence.get("instrument_type"),
        rejected=evidence["rejected"],
        issues=evidence["issues"],
        issue_count=evidence["issue_count"],
        truncated=evidence["truncated"],
        schema_version=evidence["schema_version"],
        provenance=evidence.get("provenance"),
    )
    return evidence


def validate_and_annotate(
    data: Any,
    *,
    data_type: str,
    market: Optional[str] = None,
    asset_type: Optional[str] = None,
    instrument_type: Optional[str] = None,
    stock_code: Optional[str] = None,
    provider: Optional[str] = None,
    strict: Optional[bool] = None,
) -> ValidationResult:
    if not is_validation_enabled():
        return ValidationResult(
            context={"data_type": data_type, "enabled": False, "stock_code": stock_code}
        )
    frame = data[0] if data_type == "daily_data" and isinstance(data, tuple) and data else data
    payload_instrument = None
    if data_type == "daily_data":
        attrs = getattr(frame, "attrs", None)
        if isinstance(attrs, Mapping):
            payload_instrument = attrs.get("instrument_type")
    elif data is not None:
        payload_instrument = getattr(data, "instrument_type", None)
    resolved_instrument = infer_instrument_type(
        stock_code,
        explicit=instrument_type or asset_type or payload_instrument,
    )
    if data_type == "daily_data":
        result = validate_daily_frame(
            frame,
            market=market,
            asset_type=resolved_instrument,
            stock_code=stock_code,
        )
        attach_validation_to_frame(frame, result)
    elif data_type == "realtime_quote":
        result = validate_realtime_quote(
            data,
            market=market,
            asset_type=resolved_instrument,
            stock_code=stock_code,
        )
    elif data_type == "fundamental_context":
        result = validate_fundamental_context(
            data,
            market=market,
            asset_type=resolved_instrument,
            stock_code=stock_code,
        )
    elif data_type == "technical_indicators":
        result = validate_technical_indicators(
            data,
            market=market,
            asset_type=resolved_instrument,
            stock_code=stock_code,
        )
    else:
        result = ValidationResult(
            context={"data_type": data_type, "stock_code": stock_code}
        )
        result.add(_issue(CODE_EMPTY_PAYLOAD, ValidationSeverity.WARN, "unknown validation data type"))

    reject = result.should_reject(
        strict=strict,
        market=market,
        instrument_type=resolved_instrument,
    )
    provenance: Dict[str, Any] = {}
    if data_type == "daily_data":
        attrs = getattr(frame, "attrs", None)
        if isinstance(attrs, Mapping) and isinstance(attrs.get("provider_cache"), Mapping):
            provenance["provider_cache"] = attrs["provider_cache"]
    elif data_type == "realtime_quote" and data is not None:
        for field_name in (
            "fallback_from",
            "fetched_at",
            "provider_timestamp",
            "is_stale",
            "stale_seconds",
        ):
            field_value = getattr(data, field_name, None)
            if field_value is not None:
                provenance[field_name] = field_value
    evidence = log_validation_result(
        result,
        data_type=data_type,
        stock_code=stock_code,
        provider=provider,
        market=market,
        instrument_type=resolved_instrument,
        rejected=reject,
        provenance=provenance,
    )
    if data_type == "realtime_quote" and data is not None:
        try:
            setattr(data, "data_quality_evidence", evidence)
        except (AttributeError, TypeError):
            pass
    if reject:
        raise DataValidationRejected(
            result,
            data_type=data_type,
            evidence=evidence,
        )
    return result
