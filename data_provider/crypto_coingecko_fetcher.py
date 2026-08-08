# -*- coding: utf-8 -*-
"""Crypto market data via CoinGecko public API (Issue #236 / T13).

Design choices
--------------
* Market modeling: **Plan A** — ``crypto`` is a first-class value in
  ``DATA_PROVIDER_MARKETS`` so the existing ``DataProvider`` contract is reused.
  Equity providers do not declare the crypto market and are filtered out.
* Symbol namespace: only ``crypto:TICKER`` is accepted. Bare ``BTC`` / ``ETH``
  remain equity candidates so they never auto-resolve to crypto.
* Free default stack: CoinGecko public REST endpoints need no API key for the
  basic OHLC / simple-price paths used here (rate-limited; optional demo key
  via ``COINGECKO_API_KEY`` when the operator upgrades).
* 24×7 bar definition: daily OHLC bars are **UTC calendar days**. ``pre_close``
  is the previous UTC daily close; ``open`` is the current UTC day's open from
  the latest completed/in-progress daily candle returned by CoinGecko OHLC.
* Equity-only capabilities (limit-up pool, A-share chip distribution, PE/PB
  fundamentals) are intentionally unsupported and return empty/None rather
  than stock-shaped placeholders.

Manager wiring
--------------
``DataFetcherManager`` initialization lives in ``data_provider/base.py``
(owned by a parallel task). This module is self-contained: call
:func:`attach_crypto_provider` or register
:func:`build_crypto_provider_registration` after the manager exists. See the
PR Integration Point.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

import pandas as pd
import requests

from src.utils.sanitize import log_safe_exception

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .plugin_registry import DataProviderRegistration
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote
from .symbol_normalization import (
    CRYPTO_NAMESPACE_PREFIX,
    is_crypto_symbol,
    normalize_crypto_symbol,
    parse_crypto_symbol,
)

logger = logging.getLogger(__name__)

_COINGECKO_API_BASE = "https://api.coingecko.com/api/v3"

# Common tickers → CoinGecko coin ids. Unknown tickers fall back to lower-case
# id form (e.g. crypto:solana → "solana") so operators can pass CoinGecko ids
# directly after the namespace prefix.
_TICKER_TO_COINGECKO_ID: Dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "MATIC": "matic-network",
    "POL": "polygon-ecosystem-token",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "ATOM": "cosmos",
    "UNI": "uniswap",
    "NEAR": "near",
    "APT": "aptos",
    "ARB": "arbitrum",
    "OP": "optimism",
    "SUI": "sui",
    "TRX": "tron",
    "TON": "the-open-network",
    "SHIB": "shiba-inu",
    "PEPE": "pepe",
    "WIF": "dogwifcoin",
}


def ticker_to_coingecko_id(ticker: str) -> str:
    """Map a crypto ticker or CoinGecko id fragment to a CoinGecko coin id."""
    key = (ticker or "").strip().upper()
    if not key:
        raise ValueError("crypto ticker is empty")
    mapped = _TICKER_TO_COINGECKO_ID.get(key)
    if mapped:
        return mapped
    # Allow explicit CoinGecko ids: crypto:bitcoin, crypto:avalanche-2
    return (ticker or "").strip().lower()


def _clamp_ohlc_days(start_date: str, end_date: str) -> int:
    """CoinGecko OHLC accepts discrete day windows; pick the smallest covering window."""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        span = max((end - start).days + 1, 1)
    except ValueError:
        span = 30
    for candidate in (1, 7, 14, 30, 90, 180, 365):
        if span <= candidate:
            return candidate
    return 365


class CryptoCoingeckoFetcher(BaseFetcher):
    """CoinGecko-backed crypto daily/realtime provider (crypto market only)."""

    name = "CryptoCoingeckoFetcher"
    priority = int(os.getenv("CRYPTO_COINGECKO_PRIORITY", "10"))

    def __init__(
        self,
        *,
        api_base: str | None = None,
        session: requests.Session | None = None,
        api_key: str | None = None,
    ) -> None:
        self._api_base = (api_base or os.getenv("COINGECKO_API_BASE") or _COINGECKO_API_BASE).rstrip(
            "/"
        )
        self._session = session or requests.Session()
        self._api_key = (
            api_key
            if api_key is not None
            else (os.getenv("COINGECKO_API_KEY") or "").strip() or None
        )

    # ------------------------------------------------------------------
    # Symbol gates
    # ------------------------------------------------------------------
    def _require_crypto_code(self, stock_code: str) -> str:
        normalized = normalize_crypto_symbol(stock_code)
        if normalized is None:
            raise DataFetchError(
                f"[{self.name}] {stock_code!r} is not a crypto-namespaced symbol; "
                f"use {CRYPTO_NAMESPACE_PREFIX}TICKER (e.g. crypto:BTC)"
            )
        return normalized

    def _coin_id_for_code(self, stock_code: str) -> str:
        normalized = self._require_crypto_code(stock_code)
        ticker = parse_crypto_symbol(normalized)
        assert ticker is not None  # guarded by _require_crypto_code
        return ticker_to_coingecko_id(ticker)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _request_json(self, path: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        url = f"{self._api_base}{path}"
        query: Dict[str, Any] = dict(params or {})
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            # CoinGecko demo/pro keys use x-cg-demo-api-key / x-cg-pro-api-key.
            # Demo header is the low-friction paid tier; free public works without.
            headers["x-cg-demo-api-key"] = self._api_key
        try:
            self.random_sleep(0.2, 0.5)
            response = self._session.get(url, params=query, headers=headers, timeout=20)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise DataFetchError(f"[{self.name}] HTTP request failed for {path}: {exc}") from exc

    # ------------------------------------------------------------------
    # Daily data
    # ------------------------------------------------------------------
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        coin_id = self._coin_id_for_code(stock_code)
        days = _clamp_ohlc_days(start_date, end_date)
        payload = self._request_json(
            f"/coins/{coin_id}/ohlc",
            params={"vs_currency": "usd", "days": days},
        )
        if not isinstance(payload, list) or not payload:
            raise DataFetchError(f"[{self.name}] No OHLC data for {stock_code} ({coin_id})")
        return pd.DataFrame(payload, columns=["ts", "open", "high", "low", "close"])

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        out = df.copy()
        # CoinGecko OHLC timestamps are milliseconds since epoch (UTC).
        out["date"] = pd.to_datetime(out["ts"], unit="ms", utc=True).dt.tz_convert(None).dt.date
        for column in ("open", "high", "low", "close"):
            out[column] = pd.to_numeric(out[column], errors="coerce")
        out = out.dropna(subset=["open", "high", "low", "close"])
        out["volume"] = 0.0  # OHLC endpoint has no volume; do not invent values
        out["amount"] = out["volume"] * out["close"]
        out["pct_chg"] = out["close"].pct_change() * 100.0
        out["pct_chg"] = out["pct_chg"].fillna(0.0).round(2)
        out["code"] = normalize_crypto_symbol(stock_code) or stock_code

        keep = ["code"] + STANDARD_COLUMNS
        return out[[col for col in keep if col in out.columns]]

    # ------------------------------------------------------------------
    # Realtime + name
    # ------------------------------------------------------------------
    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        if not is_crypto_symbol(stock_code):
            return None
        try:
            normalized = self._require_crypto_code(stock_code)
            coin_id = self._coin_id_for_code(normalized)
            payload = self._request_json(
                "/simple/price",
                params={
                    "ids": coin_id,
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                    "include_last_updated_at": "true",
                },
            )
        except DataFetchError as exc:
            log_safe_exception(
                logger,
                "CoinGecko realtime quote failed",
                exc,
                error_code="crypto_coingecko_realtime_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
            return None

        if not isinstance(payload, dict):
            return None
        row = payload.get(coin_id)
        if not isinstance(row, dict):
            return None
        price = row.get("usd")
        if price is None:
            return None
        try:
            price_f = float(price)
        except (TypeError, ValueError):
            return None
        if price_f <= 0:
            return None

        change_pct = row.get("usd_24h_change")
        volume = row.get("usd_24h_vol")
        try:
            change_pct_f = float(change_pct) if change_pct is not None else None
        except (TypeError, ValueError):
            change_pct_f = None
        try:
            volume_f = float(volume) if volume is not None else None
        except (TypeError, ValueError):
            volume_f = None

        # 24×7 definition: pre_close is implied by 24h change against current price.
        pre_close = None
        if change_pct_f is not None and change_pct_f != -100.0:
            pre_close = price_f / (1.0 + change_pct_f / 100.0)

        return UnifiedRealtimeQuote(
            code=normalized,
            source=RealtimeSource.FALLBACK,
            price=price_f,
            change_pct=round(change_pct_f, 2) if change_pct_f is not None else None,
            change_amount=(
                round(price_f - pre_close, 6) if pre_close is not None else None
            ),
            volume=volume_f,
            amount=None,
            volume_ratio=None,
            turnover_rate=None,
            amplitude=None,
            open_price=None,  # CoinGecko simple price has no session open
            high=None,
            low=None,
            pre_close=round(pre_close, 6) if pre_close is not None else None,
        )

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        if not is_crypto_symbol(stock_code):
            return None
        try:
            coin_id = self._coin_id_for_code(stock_code)
            payload = self._request_json(
                f"/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
            )
        except DataFetchError as exc:
            log_safe_exception(
                logger,
                "CoinGecko coin name lookup failed",
                exc,
                error_code="crypto_coingecko_name_failed",
                level=logging.DEBUG,
                context={"symbol": stock_code},
            )
            return None
        if not isinstance(payload, dict):
            return None
        name = payload.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return None

    def get_limit_up_pool(
        self,
        date: Optional[str] = None,
        n: int = 20,
    ) -> Optional[list]:
        """Crypto has no limit-up regime; always empty rather than stock-shaped data."""
        del date, n
        return []

    def is_available_for_request(self, capability: str = "") -> bool:
        del capability
        return True


def build_crypto_provider_registration() -> DataProviderRegistration:
    """Build a plugin registration for the crypto CoinGecko provider."""
    return DataProviderRegistration(
        provider_id="crypto_coingecko",
        factory=CryptoCoingeckoFetcher,
        markets=frozenset({"crypto"}),
        capabilities=frozenset({"daily_data", "realtime_quote", "stock_name"}),
    )


def attach_crypto_provider(manager: Any) -> CryptoCoingeckoFetcher:
    """Attach the crypto provider to an existing ``DataFetcherManager``.

    Integration Point (after parallel-batch ownership of ``base.py`` clears)::

        from data_provider.crypto_coingecko_fetcher import attach_crypto_provider
        if os.getenv("CRYPTO_PROVIDER_ENABLED", "").strip().lower() in {"1", "true", "yes"}:
            attach_crypto_provider(self)
    """
    fetcher = CryptoCoingeckoFetcher()
    add = getattr(manager, "add_fetcher", None)
    if not callable(add):
        raise TypeError("manager must provide add_fetcher(fetcher)")
    add(fetcher)
    return fetcher


def utc_now_iso() -> str:
    """Helper for diagnostics (UTC clock; crypto has no exchange session close)."""
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "CryptoCoingeckoFetcher",
    "attach_crypto_provider",
    "build_crypto_provider_registration",
    "ticker_to_coingecko_id",
    "utc_now_iso",
]
