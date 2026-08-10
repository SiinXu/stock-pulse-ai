# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Thin OpenBB → data_provider adapter (external-framework demonstration).

This package is intentionally **not** part of the default plugin load set. Copy
it under an operator-owned ``PLUGINS_DIR`` parent (or point ``PLUGINS_DIR`` at
``docs/examples``) and install OpenBB manually. StockPulse never auto-installs
plugin dependencies and never sandboxes plugin code.

Design rules (surface v1, uncompromising):

- Registers only the frozen ``data_provider`` extension point.
- Normalizes fields to the repository daily-data contract.
- Missing OpenBB dependency or upstream failure **raises** so
  ``DataFetcherManager`` can continue its eligible fallback chain; never
  returns an empty frame to pretend success.
- Network/SDK timeouts are owned by this adapter (no universal host deadline).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, timedelta
from typing import Any, Protocol

import pandas as pd

from data_provider import DataProvider, DataProviderRegistration
from src.plugins import Plugin as BasePlugin
from src.plugins import PluginContext

# Lower priority numbers win. Stay behind typical built-ins so operators must
# deliberately prefer this adapter (pin / reorder) rather than having it steal
# traffic on first enable.
_DEFAULT_PRIORITY = 95
_DEFAULT_TIMEOUT_SECONDS = 15.0
_REQUIRED_COLUMNS = (
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pct_chg",
)
_MISSING_OPENBB_MESSAGE = (
    "OpenBB is not installed in this environment. Install it manually "
    "(for example `pip install openbb`) before enabling the "
    "stockpulse.openbb-data-provider plugin. StockPulse does not install "
    "plugin dependencies and does not sandbox external adapters; review the "
    "package before setting PLUGINS_DIR."
)


class OpenBBHistoricalClient(Protocol):
    """Minimal client surface used by the adapter (injectable for offline tests)."""

    def fetch_historical(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        timeout_seconds: float,
    ) -> pd.DataFrame:
        """Return a DataFrame with at least OHLCV columns (any reasonable casing)."""


class MissingOpenBBDependencyError(RuntimeError):
    """Raised when the optional OpenBB package is absent at call time."""


class OpenBBProviderTimeoutError(TimeoutError):
    """Raised when one OpenBB SDK provider attempt exceeds its deadline."""


class OpenBBDailyDataProvider(DataProvider):
    """Map OpenBB equity historical bars onto the StockPulse daily-data contract."""

    name = "OpenBBAdapterProvider"
    priority = _DEFAULT_PRIORITY

    def __init__(
        self,
        client: OpenBBHistoricalClient | None = None,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._client = client
        self._timeout_seconds = float(timeout_seconds)

    def get_daily_data(
        self,
        stock_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ) -> pd.DataFrame:
        symbol = str(stock_code or "").strip()
        if not symbol:
            raise ValueError("stock_code is required")

        resolved_start, resolved_end = _resolve_window(
            start_date=start_date,
            end_date=end_date,
            days=days,
        )
        client = self._resolve_client()
        raw = client.fetch_historical(
            symbol=symbol,
            start_date=resolved_start,
            end_date=resolved_end,
            timeout_seconds=self._timeout_seconds,
        )
        if raw is None:
            raise RuntimeError(
                f"OpenBB returned no payload for symbol={symbol!r}; "
                "failing this provider attempt so DataFetcherManager can fall back"
            )
        if not isinstance(raw, pd.DataFrame):
            raise TypeError(
                f"OpenBB historical client must return a pandas.DataFrame, got {type(raw)!r}"
            )
        if raw.empty:
            raise RuntimeError(
                f"OpenBB returned an empty historical frame for symbol={symbol!r}; "
                "failing this provider attempt so DataFetcherManager can fall back"
            )
        return normalize_openbb_daily_frame(raw)

    def _resolve_client(self) -> OpenBBHistoricalClient:
        if self._client is not None:
            return self._client
        return _SdkOpenBBClient()


class _SdkOpenBBClient:
    """Lazy OpenBB Platform client; import happens at first use, not at load time."""

    def fetch_historical(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        timeout_seconds: float,
    ) -> pd.DataFrame:
        obb = _import_openbb()
        # OpenBB Platform surface (equity.price.historical). Keep the call narrow:
        # StockPulse owns routing/fallback; this client owns one attempt only.
        kwargs: dict[str, Any] = {"symbol": symbol}
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        # Prefer an explicit provider when the installed OpenBB version accepts
        # it; fall back to the minimal signature otherwise.
        def _request() -> Any:
            try:
                return obb.equity.price.historical(
                    **kwargs,
                    provider="yfinance",
                )
            except TypeError:
                return obb.equity.price.historical(**kwargs)

        # Do not use the executor as a context manager: __exit__ waits for a
        # timed-out worker and would turn the deadline back into an unbounded
        # caller wait. Python cannot forcibly stop an in-flight SDK thread, but
        # this adapter owns the caller-facing wall-clock bound and immediately
        # raises into DataFetcherManager's normal fallback chain.
        executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="stockpulse-openbb",
        )
        try:
            future = executor.submit(_request)
            result = future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise OpenBBProviderTimeoutError(
                "OpenBB historical provider timed out after "
                f"{timeout_seconds:g}s for symbol={symbol!r}; "
                "failing this provider attempt so DataFetcherManager can fall back"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        frame = _coerce_openbb_result_to_frame(result)
        return frame


def _import_openbb() -> Any:
    try:
        from openbb import obb  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised via unit test path
        raise MissingOpenBBDependencyError(_MISSING_OPENBB_MESSAGE) from exc
    return obb


def _coerce_openbb_result_to_frame(result: Any) -> pd.DataFrame:
    if isinstance(result, pd.DataFrame):
        return result
    # OpenBB often returns an OBBject with to_dataframe() / results.
    to_dataframe = getattr(result, "to_dataframe", None)
    if callable(to_dataframe):
        frame = to_dataframe()
        if isinstance(frame, pd.DataFrame):
            return frame
    results = getattr(result, "results", None)
    if results is not None:
        return pd.DataFrame(results)
    raise TypeError(
        f"Unsupported OpenBB historical result type: {type(result)!r}"
    )


def normalize_openbb_daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize heterogeneous OpenBB / upstream column names to the host contract.

    Target columns: date, open, high, low, close, volume, amount, pct_chg.
    """

    if frame is None or not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas.DataFrame")
    if frame.empty:
        raise RuntimeError("cannot normalize an empty OpenBB frame")

    working = frame.copy()
    if not isinstance(working.index, pd.RangeIndex) and working.index.name in {
        None,
        "date",
        "Date",
        "datetime",
        "timestamp",
    }:
        # Many OpenBB equity historical responses use a DatetimeIndex.
        if "date" not in {str(c).lower() for c in working.columns}:
            working = working.reset_index()

    rename_map: dict[str, str] = {}
    lower_to_actual = {str(col).strip().lower(): col for col in working.columns}
    aliases = {
        "date": ("date", "datetime", "timestamp", "time", "index"),
        "open": ("open", "o", "adj_open", "adj open"),
        "high": ("high", "h", "adj_high", "adj high"),
        "low": ("low", "l", "adj_low", "adj low"),
        "close": ("close", "c", "adj_close", "adj close", "adjclose"),
        "volume": ("volume", "vol", "v"),
        "amount": ("amount", "value", "turnover", "dollar_volume"),
        "pct_chg": (
            "pct_chg",
            "pct_change",
            "percent_change",
            "change_percent",
            "change_pct",
            "returns",
        ),
    }
    for target, candidates in aliases.items():
        for candidate in candidates:
            actual = lower_to_actual.get(candidate)
            if actual is not None and actual not in rename_map:
                rename_map[actual] = target
                break

    working = working.rename(columns=rename_map)
    missing_ohlcv = [name for name in ("date", "open", "high", "low", "close") if name not in working.columns]
    if missing_ohlcv:
        raise ValueError(
            "OpenBB frame missing required columns after normalization: "
            + ", ".join(missing_ohlcv)
        )

    if "volume" not in working.columns:
        working["volume"] = 0
    if "amount" not in working.columns:
        working["amount"] = (
            pd.to_numeric(working["close"], errors="coerce").fillna(0.0)
            * pd.to_numeric(working["volume"], errors="coerce").fillna(0.0)
        )
    if "pct_chg" not in working.columns:
        closes = pd.to_numeric(working["close"], errors="coerce")
        working["pct_chg"] = closes.pct_change().fillna(0.0) * 100.0

    normalized = working.loc[:, list(_REQUIRED_COLUMNS)].copy()
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce").dt.strftime(
        "%Y-%m-%d"
    )
    for column in ("open", "high", "low", "close", "amount", "pct_chg"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["volume"] = (
        pd.to_numeric(normalized["volume"], errors="coerce").fillna(0).astype("int64")
    )
    normalized = normalized.dropna(subset=["date", "open", "high", "low", "close"])
    if normalized.empty:
        raise RuntimeError(
            "OpenBB frame had no usable rows after normalization; "
            "failing this provider attempt so DataFetcherManager can fall back"
        )
    return normalized.reset_index(drop=True)


def _resolve_window(
    *,
    start_date: str | None,
    end_date: str | None,
    days: int,
) -> tuple[str | None, str | None]:
    if start_date or end_date:
        return start_date, end_date
    if days and days > 0:
        end = date.today()
        start = end - timedelta(days=int(days))
        return start.isoformat(), end.isoformat()
    return start_date, end_date


def create_openbb_provider() -> DataProvider:
    """Factory used by ``DataProviderRegistration`` (no auto-install side effects)."""

    return OpenBBDailyDataProvider()


class Plugin(BasePlugin):
    """Register the OpenBB adapter with a manager-bound provider registry."""

    def onload(self, context: PluginContext) -> None:
        registration = DataProviderRegistration(
            provider_id="openbb-daily-data",
            factory=create_openbb_provider,
            markets=frozenset({"us", "hk", "cn"}),
            capabilities=frozenset({"daily_data"}),
        )
        context.register(
            "data_provider",
            registration.provider_id,
            registration,
            contract_version="1",
            priority=OpenBBDailyDataProvider.priority,
        )
