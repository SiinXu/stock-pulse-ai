# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""AkShare-backed A-share individual money-flow fetch and normalization.

Primary API: ``ak.stock_individual_fund_flow(stock, market)``
(Eastmoney day-level fund-flow kline).

This module is intentionally free of manager/config concerns so it can be
unit-tested offline with fixture DataFrames.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import pandas as pd
import requests

from data_provider.money_flow_types import (
    EASTMONEY_EM_ORDER_BUCKET_DEFINITION,
    MoneyFlowSnapshot,
    validate_history_days,
)
from data_provider.symbol_normalization import (
    _is_hk_market,
    _is_jp_market,
    _is_kr_market,
    _is_tw_market,
    _is_us_market,
    is_bse_code,
    normalize_stock_code,
)

logger = logging.getLogger(__name__)

# Column names returned by ak.stock_individual_fund_flow (Eastmoney).
_EM_FIELD_MAP: Dict[str, str] = {
    "date": "日期",
    "close": "收盘价",
    "change_pct": "涨跌幅",
    "main_net_inflow": "主力净流入-净额",
    "main_net_inflow_ratio": "主力净流入-净占比",
    "super_large_net_inflow": "超大单净流入-净额",
    "super_large_net_inflow_ratio": "超大单净流入-净占比",
    "large_net_inflow": "大单净流入-净额",
    "large_net_inflow_ratio": "大单净流入-净占比",
    "medium_net_inflow": "中单净流入-净额",
    "medium_net_inflow_ratio": "中单净流入-净占比",
    "small_net_inflow": "小单净流入-净额",
    "small_net_inflow_ratio": "小单净流入-净占比",
}

SOURCE_ID = "akshare:stock_individual_fund_flow"


def resolve_cn_exchange_market(stock_code: str) -> Optional[str]:
    """Map a normalized CN equity code to AkShare market token ``sh``/``sz``/``bj``.

    Returns None when the code is not a 6-digit A-share / BSE symbol.
    """
    code = normalize_stock_code(stock_code or "")
    if not code or not code.isdigit() or len(code) != 6:
        return None
    if (
        _is_us_market(code)
        or _is_hk_market(code)
        or _is_jp_market(code)
        or _is_kr_market(code)
        or _is_tw_market(code)
    ):
        return None
    if is_bse_code(code):
        return "bj"
    # Shanghai: main board 60xxxx / 68x STAR / 5xxxx ETF / 90xxxx B-shares.
    if code.startswith(("6", "5", "90")):
        return "sh"
    return "sz"


def normalize_eastmoney_fund_flow_df(
    df: pd.DataFrame,
    *,
    stock_code: str,
    history_days: int = 5,
    amount_unit: str = "unknown",
    amount_scale: str = "unknown",
) -> Optional[MoneyFlowSnapshot]:
    """Normalize an Eastmoney individual fund-flow DataFrame into a snapshot.

    ``history_days`` controls optional 5d/10d main-force rollups from the same
    frame; the primary fields always reflect the latest row.
    """
    if df is None or getattr(df, "empty", True):
        return None

    requested_days = validate_history_days(history_days)
    work = df.copy()
    date_col = _EM_FIELD_MAP["date"]
    if date_col not in work.columns:
        raise ValueError("money-flow provider response has no date column")
    parsed_dates = pd.to_datetime(work[date_col], errors="coerce")
    if parsed_dates.isna().any():
        raise ValueError("money-flow provider response contains an invalid date")
    work = work.assign(_provider_date=parsed_dates.dt.date)
    work = work.sort_values(by="_provider_date").drop_duplicates("_provider_date", keep="last")
    work = work.iloc[-requested_days:]
    latest = work.iloc[-1]

    code = normalize_stock_code(stock_code)
    calibrated_amounts = amount_unit != "unknown" and amount_scale != "unknown"

    def numeric(field: str) -> Optional[float]:
        value = latest.get(_EM_FIELD_MAP[field])
        if value is None or pd.isna(value):
            return None
        if isinstance(value, bool):
            raise TypeError(f"{field} must not be boolean")
        return float(value)

    snapshot = MoneyFlowSnapshot(
        code=code,
        date=latest["_provider_date"].isoformat(),
        source=SOURCE_ID,
        market="cn",
        main_net_inflow=numeric("main_net_inflow") if calibrated_amounts else None,
        super_large_net_inflow=numeric("super_large_net_inflow") if calibrated_amounts else None,
        large_net_inflow=numeric("large_net_inflow") if calibrated_amounts else None,
        medium_net_inflow=numeric("medium_net_inflow") if calibrated_amounts else None,
        small_net_inflow=numeric("small_net_inflow") if calibrated_amounts else None,
        main_net_inflow_ratio=numeric("main_net_inflow_ratio"),
        super_large_net_inflow_ratio=numeric("super_large_net_inflow_ratio"),
        large_net_inflow_ratio=numeric("large_net_inflow_ratio"),
        medium_net_inflow_ratio=numeric("medium_net_inflow_ratio"),
        small_net_inflow_ratio=numeric("small_net_inflow_ratio"),
        close=numeric("close"),
        change_pct=numeric("change_pct"),
        unit=amount_unit,
        amount_scale=amount_scale,
        bucket_definition=EASTMONEY_EM_ORDER_BUCKET_DEFINITION,
        raw_field_map=dict(_EM_FIELD_MAP),
        as_of=datetime.now(timezone.utc).isoformat(),
        requested_days=requested_days,
        observed_days=len(work),
        completeness="complete" if len(work) == requested_days else "partial",
    )

    main_col = _EM_FIELD_MAP["main_net_inflow"]
    if calibrated_amounts and main_col in work.columns:
        series = pd.to_numeric(work[main_col], errors="coerce").dropna()
        if not series.empty:
            if requested_days >= 5 and len(series) >= 5:
                snapshot.main_net_inflow_5d = float(series.iloc[-5:].sum())
            if requested_days >= 10 and len(series) >= 10:
                snapshot.main_net_inflow_10d = float(series.iloc[-10:].sum())

    return snapshot


def fetch_akshare_individual_money_flow(
    stock_code: str,
    *,
    history_days: int = 5,
    ak_module: Any = None,
    rate_limit: Optional[Callable[[], None]] = None,
    timeout_runner: Optional[Callable[..., Any]] = None,
    timeout_seconds: float = 12.0,
    sleeper: Callable[[float], None] = time.sleep,
) -> Optional[MoneyFlowSnapshot]:
    """Fetch and normalize A-share individual money flow via AkShare.

    Non-CN symbols return None without network I/O.
    """
    requested_days = validate_history_days(history_days)
    code = normalize_stock_code(stock_code or "")
    market = resolve_cn_exchange_market(code)
    if market is None:
        logger.debug(
            "[money_flow] skip non-CN or unsupported code for akshare fund flow: %s",
            stock_code,
        )
        return None

    if ak_module is None:
        import akshare as ak_module  # type: ignore

    if timeout_runner is None:
        from data_provider.retry_policy import call_with_timeout

        timeout_runner = call_with_timeout

    retryable = (TimeoutError, ConnectionError, requests.RequestException)
    last_error: Optional[BaseException] = None
    for attempt in range(2):
        if rate_limit is not None:
            rate_limit()
        logger.info(
            "[API调用] ak.stock_individual_fund_flow(stock=%s, market=%s)",
            code,
            market,
        )
        try:
            df = timeout_runner(
                ak_module.stock_individual_fund_flow,
                stock=code,
                market=market,
                timeout=timeout_seconds,
                call_name="akshare_money_flow",
            )
            break
        except retryable as exc:
            last_error = exc
            if attempt == 0:
                sleeper(0.25)
                continue
            raise
    else:
        assert last_error is not None
        raise last_error

    if df is None or getattr(df, "empty", True):
        logger.warning(
            "[API返回] stock_individual_fund_flow empty for %s (%s)",
            code,
            market,
        )
        return None

    return normalize_eastmoney_fund_flow_df(
        df,
        stock_code=code,
        history_days=requested_days,
    )
