# -*- coding: utf-8 -*-
"""TickFlow daily history methods: raw fetch and normalize.

Method bodies are rebound onto ``TickFlowFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.tickflow_fetcher``. Mirrors the domain split of
``yfinance_parts.history`` and ``tushare_parts.history``.

No tenacity wrapper and no sibling method moves. Symbol conversion, daily
cache helpers, client access, and ``_prepare_daily_frame`` stay on the
facade; the rebind resolves free names from the facade globals and sibling
methods through ``self`` at call time.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.tickflow_fetcher`` globals at runtime (ADR-006).
DataFetchError = Exception  # type: ignore[assignment,misc]
STANDARD_COLUMNS = ()  # type: ignore[assignment]
normalize_stock_code = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _HistoryMethods:
    """Source descriptors rebound onto ``TickFlowFetcher``."""

    def _fetch_raw_data(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        symbol = self._to_tickflow_symbol(stock_code)
        if not symbol:
            raise DataFetchError("TickFlowFetcher only supports A-share/ETF symbols")

        cache_key = self._daily_cache_key(symbol, start_date, end_date)
        cached = self._get_daily_cache(cache_key)
        if cached is not None:
            return cached

        client = self._get_client()
        if client is None:
            raise DataFetchError("TickFlow API key is not configured")

        request_count = self._daily_kline_count(start_date, end_date)
        try:
            df = client.klines.get(
                symbol,
                period="1d",
                count=request_count,
                start_time=self._date_to_ms(start_date),
                end_time=self._date_to_ms(end_date, end_of_day=True),
                adjust=self.kline_adjust,
                as_dataframe=True,
            )
        except Exception as exc:
            raise DataFetchError(f"TickFlow daily K-line request failed: {exc}") from exc

        raw_df = self._prepare_daily_frame(
            df,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            count=request_count,
            context="single",
        )
        self._set_daily_cache(cache_key, raw_df)
        return raw_df.copy()

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        raw = self._coerce_frame(df)
        if raw.empty:
            return pd.DataFrame(columns=["code", *STANDARD_COLUMNS])

        normalized = pd.DataFrame()
        normalized["date"] = self._extract_date_series(raw)
        normalized["code"] = normalize_stock_code(stock_code)
        for column in ("open", "high", "low", "close", "amount"):
            normalized[column] = pd.to_numeric(raw.get(column), errors="coerce")

        # TickFlow daily volume is in lots for A-shares; project standard is shares.
        normalized["volume"] = self._cn_lots_to_shares(raw.get("volume"))

        if "pct_chg" in raw.columns:
            normalized["pct_chg"] = pd.to_numeric(raw["pct_chg"], errors="coerce")
        elif "change_pct" in raw.columns:
            normalized["pct_chg"] = self._ratio_series_to_percent(raw["change_pct"])
        else:
            close = pd.to_numeric(normalized["close"], errors="coerce")
            normalized["pct_chg"] = close.pct_change().fillna(0.0) * 100.0

        normalized = normalized.dropna(subset=["date", "close", "volume"])
        normalized = normalized.sort_values("date", ascending=True).reset_index(drop=True)
        return normalized[["code", *STANDARD_COLUMNS]]


EXPECTED_HISTORY_METHOD_NAMES: Tuple[str, ...] = (
    "_fetch_raw_data",
    "_normalize_data",
)


def bind_history_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind daily-history descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _HistoryMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_HISTORY_METHOD_NAMES,
    )


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""

    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""

    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
