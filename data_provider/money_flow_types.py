# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Normalized money-flow (main-force / large-order) types and helpers.

Different upstream sources use incompatible order-size buckets (super-large /
large / medium / small). Callers must treat ``bucket_definition`` and
``source`` as part of the contract and must not mix numeric values across
sources without recalibration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


# Eastmoney (via AkShare stock_individual_fund_flow) order-size buckets.
# Thresholds are defined by Eastmoney and may change without notice; they are
# NOT interchangeable with Tushare moneyflow or Tonghuashun rankings.
EASTMONEY_EM_ORDER_BUCKET_DEFINITION = (
    "eastmoney_em_order_size_buckets_v1"
    ":main=super_large+large;"
    "unit=CNY_net_inflow;"
    "fields=主力/超大单/大单/中单/小单净流入-净额|净占比"
)


@dataclass
class MoneyFlowSnapshot:
    """Normalized single-day (or window-summary) money-flow snapshot."""

    code: str
    date: str = ""
    source: str = ""
    market: str = "cn"
    # Net inflow amounts (same unit as ``unit``; positive = net buy).
    main_net_inflow: Optional[float] = None
    super_large_net_inflow: Optional[float] = None
    large_net_inflow: Optional[float] = None
    medium_net_inflow: Optional[float] = None
    small_net_inflow: Optional[float] = None
    # Net inflow ratios as percentages when the source provides them (e.g. 1.23 => 1.23%).
    main_net_inflow_ratio: Optional[float] = None
    super_large_net_inflow_ratio: Optional[float] = None
    large_net_inflow_ratio: Optional[float] = None
    medium_net_inflow_ratio: Optional[float] = None
    small_net_inflow_ratio: Optional[float] = None
    # Optional multi-day rollups when derived from history.
    main_net_inflow_5d: Optional[float] = None
    main_net_inflow_10d: Optional[float] = None
    close: Optional[float] = None
    change_pct: Optional[float] = None
    unit: str = "CNY"
    bucket_definition: str = ""
    raw_field_map: Dict[str, str] = field(default_factory=dict)
    as_of: Optional[str] = None
    history_days: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Return a plain dict suitable for analysis context / JSON."""
        payload = asdict(self)
        # Keep empty raw_field_map out of hot context paths when unused.
        if not payload.get("raw_field_map"):
            payload.pop("raw_field_map", None)
        return payload

    def attitude(self) -> str:
        """Coarse capital attitude from main-force net inflow only."""
        value = self.main_net_inflow
        if value is None:
            return "unknown"
        if value > 0:
            return "inflow"
        if value < 0:
            return "outflow"
        return "neutral"


def is_meaningful_money_flow(snapshot: Any) -> bool:
    """Return True when a snapshot has usable main-force or size-bucket amounts."""
    if snapshot is None:
        return False
    main = _coerce_optional_float(getattr(snapshot, "main_net_inflow", None))
    if main is not None:
        return True
    for attr in (
        "super_large_net_inflow",
        "large_net_inflow",
        "medium_net_inflow",
        "small_net_inflow",
    ):
        if _coerce_optional_float(getattr(snapshot, attr, None)) is not None:
            return True
    return False


def _coerce_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric != numeric:  # NaN
        return None
    return numeric
