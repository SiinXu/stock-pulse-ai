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
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import pandas as pd

from data_provider.money_flow_types import (
    EASTMONEY_EM_ORDER_BUCKET_DEFINITION,
    MoneyFlowSnapshot,
)
from data_provider.realtime_types import safe_float
from data_provider.symbol_normalization import (
    _is_hk_market,
    _is_jp_market,
    _is_kr_market,
    _is_tw_market,
    _is_us_market,
    is_bse_code,
    normalize_stock_code,
)
from src.utils.sanitize import log_safe_exception

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
) -> Optional[MoneyFlowSnapshot]:
    """Normalize an Eastmoney individual fund-flow DataFrame into a snapshot.

    ``history_days`` controls optional 5d/10d main-force rollups from the same
    frame; the primary fields always reflect the latest row.
    """
    if df is None or getattr(df, "empty", True):
        return None

    work = df.copy()
    date_col = _EM_FIELD_MAP["date"]
    if date_col in work.columns:
        work = work.sort_values(by=date_col)
    latest = work.iloc[-1]

    code = normalize_stock_code(stock_code)
    main = safe_float(latest.get(_EM_FIELD_MAP["main_net_inflow"]))
    snapshot = MoneyFlowSnapshot(
        code=code,
        date=_stringify_date(latest.get(date_col)),
        source=SOURCE_ID,
        market="cn",
        main_net_inflow=main,
        super_large_net_inflow=safe_float(
            latest.get(_EM_FIELD_MAP["super_large_net_inflow"])
        ),
        large_net_inflow=safe_float(latest.get(_EM_FIELD_MAP["large_net_inflow"])),
        medium_net_inflow=safe_float(latest.get(_EM_FIELD_MAP["medium_net_inflow"])),
        small_net_inflow=safe_float(latest.get(_EM_FIELD_MAP["small_net_inflow"])),
        main_net_inflow_ratio=safe_float(
            latest.get(_EM_FIELD_MAP["main_net_inflow_ratio"])
        ),
        super_large_net_inflow_ratio=safe_float(
            latest.get(_EM_FIELD_MAP["super_large_net_inflow_ratio"])
        ),
        large_net_inflow_ratio=safe_float(
            latest.get(_EM_FIELD_MAP["large_net_inflow_ratio"])
        ),
        medium_net_inflow_ratio=safe_float(
            latest.get(_EM_FIELD_MAP["medium_net_inflow_ratio"])
        ),
        small_net_inflow_ratio=safe_float(
            latest.get(_EM_FIELD_MAP["small_net_inflow_ratio"])
        ),
        close=safe_float(latest.get(_EM_FIELD_MAP["close"])),
        change_pct=safe_float(latest.get(_EM_FIELD_MAP["change_pct"])),
        unit="CNY",
        bucket_definition=EASTMONEY_EM_ORDER_BUCKET_DEFINITION,
        raw_field_map=dict(_EM_FIELD_MAP),
        as_of=datetime.now(timezone.utc).isoformat(),
        history_days=int(history_days) if history_days else 0,
    )

    main_col = _EM_FIELD_MAP["main_net_inflow"]
    if main_col in work.columns:
        series = pd.to_numeric(work[main_col], errors="coerce").dropna()
        if not series.empty:
            if len(series) >= 5:
                snapshot.main_net_inflow_5d = float(series.iloc[-5:].sum())
            if len(series) >= 10:
                snapshot.main_net_inflow_10d = float(series.iloc[-10:].sum())

    return snapshot


def fetch_akshare_individual_money_flow(
    stock_code: str,
    *,
    history_days: int = 5,
    ak_module: Any = None,
    rate_limit: Optional[Callable[[], None]] = None,
) -> Optional[MoneyFlowSnapshot]:
    """Fetch and normalize A-share individual money flow via AkShare.

    Non-CN symbols return None without network I/O.
    """
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

    if rate_limit is not None:
        rate_limit()

    try:
        logger.info(
            "[API调用] ak.stock_individual_fund_flow(stock=%s, market=%s)",
            code,
            market,
        )
        df = ak_module.stock_individual_fund_flow(stock=code, market=market)
    except Exception as exc:  # broad-exception: fallback_recorded - provider failure logged
        log_safe_exception(
            logger,
            "Akshare individual money flow fetch failed",
            exc,
            error_code="akshare_money_flow_failed",
            level=logging.WARNING,
            context={"symbol": code, "market": market},
        )
        return None

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
        history_days=history_days,
    )


def _stringify_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError, AttributeError):
            return str(value).strip()
    text = str(value).strip()
    return text
