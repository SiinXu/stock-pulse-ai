# -*- coding: utf-8 -*-
"""Longbridge daily history methods: raw fetch and normalize.

Method bodies are rebound onto ``LongbridgeFetcher`` by the compatibility
facade (ADR-006) so free-name lookups and test patches stay on
``src.data_provider.longbridge_fetcher``. Tenacity ``provider_retry`` is
re-applied on the facade after bind, only for ``_fetch_raw_data``.

Connection ownership stays on the facade. ``_get_ctx``,
``is_available_for_request``, ``_is_connection_error``, and
``_mark_connection_cooldown`` are reached through ``self`` at call time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional, Tuple, Type

import pandas as pd

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.longbridge_fetcher`` globals at runtime (ADR-006).
STANDARD_COLUMNS = ()  # type: ignore[assignment]
_to_longbridge_symbol = None  # type: ignore[assignment]
safe_float = None  # type: ignore[assignment]
call_with_timeout = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _HistoryMethods:
    """Source descriptors rebound onto ``LongbridgeFetcher``."""

    def _fetch_raw_data(
        self, stock_code: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        """Fetch historical candlesticks from Longbridge."""
        if not self.is_available_for_request("daily_data"):
            raise RuntimeError("Longbridge temporarily unavailable for daily_data")

        symbol = _to_longbridge_symbol(stock_code)
        if symbol is None:
            raise ValueError(f"Cannot convert {stock_code} to Longbridge symbol")

        ctx = self._get_ctx()
        if ctx is None:
            raise RuntimeError("Longbridge QuoteContext not available")

        from longbridge.openapi import Period, AdjustType

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

        try:
            candles = call_with_timeout(
                ctx.history_candlesticks_by_date,
                symbol,
                Period.Day,
                AdjustType.ForwardAdjust,
                start_dt,
                end_dt,
                timeout=self._request_timeout_seconds,
                call_name="longbridge.history_candlesticks_by_date",
            )
        except Exception as e:
            if self._is_connection_error(e):
                self._mark_connection_cooldown(e)
            raise

        if not candles:
            return pd.DataFrame()

        rows = []
        for c in candles:
            ts = getattr(c, "timestamp", None)
            if ts is None:
                continue
            if hasattr(ts, "date"):
                dt = ts.date()
            else:
                dt = datetime.fromtimestamp(int(ts)).date()

            rows.append({
                "date": dt.strftime("%Y-%m-%d"),
                "open": safe_float(getattr(c, "open", None)),
                "high": safe_float(getattr(c, "high", None)),
                "low": safe_float(getattr(c, "low", None)),
                "close": safe_float(getattr(c, "close", None)),
                "volume": int(getattr(c, "volume", 0) or 0),
                "turnover": safe_float(getattr(c, "turnover", None)),
            })

        return pd.DataFrame(rows)

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """Normalize column names to standard format."""
        if df.empty:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        rename_map = {"turnover": "amount"}
        df = df.rename(columns=rename_map)

        if "pct_chg" not in df.columns and "close" in df.columns:
            df["pct_chg"] = df["close"].pct_change() * 100

        for col in STANDARD_COLUMNS:
            if col not in df.columns:
                df[col] = None

        return df[STANDARD_COLUMNS]


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
