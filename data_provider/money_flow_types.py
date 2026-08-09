# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict money-flow snapshots and provider outcome contracts."""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


EASTMONEY_EM_ORDER_BUCKET_DEFINITION = (
    "eastmoney_em_order_size_buckets_v1"
    ":main=super_large+large;"
    "amount_unit=unknown;ratio_unit=percent;"
    "fields=main/super_large/large/medium/small_net_inflow|ratio"
)
MAX_HISTORY_DAYS = 20
MAX_ABS_AMOUNT = 1e18
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_AMOUNT_SCALES = {
    "unknown",
    "yuan",
    "thousand_yuan",
    "ten_thousand_yuan",
    "million_yuan",
}
_OUTCOME_MARKETS = {"cn", "hk", "us", "jp", "kr", "tw"}
_OUTCOME_CACHE_STATES = {"miss", "fresh", "stale"}


class MoneyFlowStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    NOT_SUPPORTED = "not_supported"
    FETCH_FAILED = "fetch_failed"
    EMPTY = "empty"
    STALE = "stale"
    FALLBACK = "fallback"


def validate_history_days(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("money-flow history days must be an integer")
    if value < 1 or value > MAX_HISTORY_DAYS:
        raise ValueError(f"money-flow history days must be between 1 and {MAX_HISTORY_DAYS}")
    return value


def _finite_optional(
    value: Any,
    *,
    field_name: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric, not boolean")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        raise TypeError(f"{field_name} must be numeric") from None
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if minimum is not None and numeric < minimum:
        raise ValueError(f"{field_name} is below its minimum")
    if maximum is not None and numeric > maximum:
        raise ValueError(f"{field_name} exceeds its maximum")
    return numeric


def _validate_date(value: str) -> str:
    if not value:
        raise ValueError("money-flow provider date is required")
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise ValueError("money-flow provider date must use YYYY-MM-DD") from None


def _validate_timestamp(value: str) -> str:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        raise ValueError("money-flow fetched_at must be ISO 8601") from None
    if parsed.tzinfo is None:
        raise ValueError("money-flow fetched_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass
class MoneyFlowSnapshot:
    """Validated provider observation; calibration is part of its identity."""

    code: str
    date: str
    source: str
    market: str = "cn"
    main_net_inflow: Optional[float] = None
    super_large_net_inflow: Optional[float] = None
    large_net_inflow: Optional[float] = None
    medium_net_inflow: Optional[float] = None
    small_net_inflow: Optional[float] = None
    main_net_inflow_ratio: Optional[float] = None
    super_large_net_inflow_ratio: Optional[float] = None
    large_net_inflow_ratio: Optional[float] = None
    medium_net_inflow_ratio: Optional[float] = None
    small_net_inflow_ratio: Optional[float] = None
    main_net_inflow_5d: Optional[float] = None
    main_net_inflow_10d: Optional[float] = None
    close: Optional[float] = None
    change_pct: Optional[float] = None
    unit: str = "unknown"
    amount_scale: str = "unknown"
    bucket_definition: str = ""
    raw_field_map: Dict[str, str] = field(default_factory=dict)
    as_of: str = ""
    requested_days: int = 5
    observed_days: int = 0
    completeness: str = "partial"

    def __post_init__(self) -> None:
        from data_provider.symbol_normalization import normalize_stock_code

        self.code = normalize_stock_code(self.code)
        if not (self.code.isdigit() and len(self.code) == 6 and self.market == "cn"):
            raise ValueError("money-flow snapshot identity must be one CN equity")
        self.date = _validate_date(self.date)
        self.as_of = _validate_timestamp(self.as_of)
        self.requested_days = validate_history_days(self.requested_days)
        if isinstance(self.observed_days, bool) or not isinstance(self.observed_days, int):
            raise TypeError("observed_days must be an integer")
        if self.observed_days < 1 or self.observed_days > self.requested_days:
            raise ValueError("observed_days must be within requested coverage")
        if not self.source or not self.bucket_definition:
            raise ValueError("money-flow source and bucket calibration are required")
        if type(self.source) is not str or type(self.bucket_definition) is not str:
            raise TypeError("money-flow source and bucket calibration must be strings")
        if len(self.source) > 160 or len(self.bucket_definition) > 1000:
            raise ValueError("money-flow provenance metadata is too long")
        if self.completeness not in {"complete", "partial"}:
            raise ValueError("money-flow completeness is invalid")
        if self.completeness == "complete" and self.observed_days != self.requested_days:
            raise ValueError("complete money-flow coverage must match the requested window")
        if self.completeness == "partial" and self.observed_days >= self.requested_days:
            raise ValueError("partial money-flow coverage must be shorter than requested")
        if self.amount_scale not in _AMOUNT_SCALES:
            raise ValueError("money-flow amount_scale is unsupported")
        if self.unit != "unknown" and _CURRENCY_PATTERN.fullmatch(self.unit) is None:
            raise ValueError("money-flow unit must be an ISO currency code or unknown")
        if (self.unit == "unknown") != (self.amount_scale == "unknown"):
            raise ValueError("money-flow currency and amount scale must be calibrated together")
        if not isinstance(self.raw_field_map, dict) or any(
            type(key) is not str or type(value) is not str
            for key, value in self.raw_field_map.items()
        ):
            raise TypeError("money-flow raw_field_map must map strings to strings")

        amount_fields = (
            "main_net_inflow", "super_large_net_inflow", "large_net_inflow",
            "medium_net_inflow", "small_net_inflow", "main_net_inflow_5d",
            "main_net_inflow_10d",
        )
        if self.unit == "unknown" or self.amount_scale == "unknown":
            if any(getattr(self, name) is not None for name in amount_fields):
                raise ValueError("uncalibrated money-flow amounts must not be exposed")
        for name in amount_fields:
            setattr(
                self,
                name,
                _finite_optional(
                    getattr(self, name), field_name=name,
                    minimum=-MAX_ABS_AMOUNT, maximum=MAX_ABS_AMOUNT,
                ),
            )
        for name in (
            "main_net_inflow_ratio", "super_large_net_inflow_ratio",
            "large_net_inflow_ratio", "medium_net_inflow_ratio",
            "small_net_inflow_ratio",
        ):
            setattr(
                self,
                name,
                _finite_optional(getattr(self, name), field_name=name, minimum=-100.0, maximum=100.0),
            )
        self.close = _finite_optional(
            self.close, field_name="close", minimum=0.0, maximum=1e12
        )
        self.change_pct = _finite_optional(
            self.change_pct, field_name="change_pct", minimum=-100.0, maximum=1000.0
        )

    @property
    def history_days(self) -> int:
        """Compatibility alias for the old snapshot field."""
        return self.requested_days

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if not payload.get("raw_field_map"):
            payload.pop("raw_field_map", None)
        return payload

    def attitude(self) -> str:
        value = self.main_net_inflow
        if value is None:
            value = self.main_net_inflow_ratio
        if value is None:
            return "unknown"
        return "inflow" if value > 0 else "outflow" if value < 0 else "neutral"


@dataclass
class MoneyFlowOutcome:
    """One explicit manager outcome, including failures and cache fallback."""

    status: MoneyFlowStatus
    code: str
    market: str
    requested_days: int
    fetched_at: str
    snapshot: Optional[MoneyFlowSnapshot] = None
    provider_date: Optional[str] = None
    age_days: Optional[int] = None
    source_chain: list[Dict[str, Any]] = field(default_factory=list)
    error_code: Optional[str] = None
    cache_state: str = "miss"
    fallback_from: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        from data_provider.symbol_normalization import normalize_stock_code

        if type(self.code) is not str or not self.code.strip():
            raise ValueError("money-flow outcome code is required")
        self.code = normalize_stock_code(self.code)
        if self.market not in _OUTCOME_MARKETS:
            raise ValueError("money-flow outcome market is unsupported")
        if self.market == "cn" and not (self.code.isdigit() and len(self.code) == 6):
            raise ValueError("CN money-flow outcome requires a canonical equity code")
        self.requested_days = validate_history_days(self.requested_days)
        self.fetched_at = _validate_timestamp(self.fetched_at)
        if self.provider_date is not None:
            self.provider_date = _validate_date(self.provider_date)
        if self.age_days is not None and (
            isinstance(self.age_days, bool) or not isinstance(self.age_days, int) or self.age_days < 0
        ):
            raise ValueError("money-flow age_days must be a nonnegative integer")
        if self.cache_state not in _OUTCOME_CACHE_STATES:
            raise ValueError("money-flow cache_state is invalid")
        if self.error_code is not None and (
            type(self.error_code) is not str
            or re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", self.error_code) is None
        ):
            raise ValueError("money-flow error_code is invalid")
        if not isinstance(self.source_chain, list) or any(
            not isinstance(item, dict) for item in self.source_chain
        ):
            raise TypeError("money-flow source_chain must be a list of mappings")
        for item in self.source_chain:
            provider = item.get("provider") or item.get("source")
            if provider is not None and (type(provider) is not str or not provider.strip()):
                raise ValueError("money-flow source-chain provider is invalid")
            latency = item.get("latency_ms")
            if latency is not None:
                _finite_optional(latency, field_name="source_chain.latency_ms", minimum=0.0, maximum=1e9)
        if not isinstance(self.warnings, list) or any(
            type(item) is not str or not item.strip() for item in self.warnings
        ):
            raise TypeError("money-flow warnings must be nonempty strings")
        if self.status in {MoneyFlowStatus.AVAILABLE, MoneyFlowStatus.PARTIAL, MoneyFlowStatus.FALLBACK, MoneyFlowStatus.STALE}:
            if self.snapshot is None:
                raise ValueError("data-bearing money-flow outcome requires a snapshot")
        elif self.snapshot is not None:
            raise ValueError("failure money-flow outcome must not contain a snapshot")
        if self.snapshot is not None:
            if self.snapshot.code != self.code or self.snapshot.market != self.market:
                raise ValueError("money-flow outcome and snapshot identity must match")
            if self.snapshot.requested_days != self.requested_days:
                raise ValueError("money-flow outcome and snapshot windows must match")
            if self.provider_date is not None and self.provider_date != self.snapshot.date:
                raise ValueError("money-flow outcome provider date must match the snapshot")
        if self.status == MoneyFlowStatus.STALE and (self.age_days is None or self.age_days < 1):
            raise ValueError("stale money-flow outcome requires positive session age")

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        if self.snapshot is not None:
            payload["snapshot"] = self.snapshot.to_dict()
        return payload


def is_meaningful_money_flow(snapshot: Any) -> bool:
    if isinstance(snapshot, MoneyFlowOutcome):
        snapshot = snapshot.snapshot
    if not isinstance(snapshot, MoneyFlowSnapshot):
        return False
    fields = (
        "main_net_inflow", "super_large_net_inflow", "large_net_inflow",
        "medium_net_inflow", "small_net_inflow", "main_net_inflow_ratio",
        "super_large_net_inflow_ratio", "large_net_inflow_ratio",
        "medium_net_inflow_ratio", "small_net_inflow_ratio",
    )
    return any(getattr(snapshot, field_name) is not None for field_name in fields)


__all__ = [
    "EASTMONEY_EM_ORDER_BUCKET_DEFINITION", "MAX_HISTORY_DAYS",
    "MoneyFlowOutcome", "MoneyFlowSnapshot", "MoneyFlowStatus",
    "is_meaningful_money_flow", "validate_history_days",
]
