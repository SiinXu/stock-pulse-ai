# -*- coding: utf-8 -*-
"""CoinGecko market data for explicit, allowlisted ``crypto:`` identities."""

from __future__ import annotations

import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import urlsplit

import pandas as pd
import requests

from src.security.outbound_policy import OutboundPolicyError, safe_get
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

import logging

logger = logging.getLogger(__name__)

_DEMO_API_BASE = "https://api.coingecko.com/api/v3"
_PRO_API_BASE = "https://pro-api.coingecko.com/api/v3"
_OFFICIAL_AUTH_ORIGINS = {
    "demo": "api.coingecko.com",
    "pro": "pro-api.coingecko.com",
}
_MAX_ATTEMPTS = 3
_MAX_RETRY_DELAY_SECONDS = 2.0

# Versioned MVP identity catalog. Unknown ticker text is rejected because ticker
# symbols are not globally unique or durable provider identifiers.
SUPPORTED_CRYPTO_ASSETS_VERSION = "2026-08-09"
_TICKER_TO_COINGECKO_ID: Dict[str, str] = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
    "DOGE": "dogecoin", "DOT": "polkadot", "AVAX": "avalanche-2",
    "LINK": "chainlink", "POL": "polygon-ecosystem-token", "LTC": "litecoin",
    "BCH": "bitcoin-cash", "ATOM": "cosmos", "UNI": "uniswap",
    "NEAR": "near", "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
    "SUI": "sui", "TRX": "tron", "TON": "the-open-network",
    "SHIB": "shiba-inu", "PEPE": "pepe", "WIF": "dogwifcoin",
}


def ticker_to_coingecko_id(ticker: str) -> str:
    """Resolve one supported ticker to its immutable CoinGecko ID."""
    key = (ticker or "").strip().upper()
    if not key:
        raise ValueError("crypto ticker is empty")
    try:
        return _TICKER_TO_COINGECKO_ID[key]
    except KeyError:
        raise ValueError(
            f"unsupported crypto asset {key!r}; catalog={SUPPORTED_CRYPTO_ASSETS_VERSION}"
        ) from None


def _finite_float(value: Any, *, positive: bool = False, nonnegative: bool = False) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError("numeric value is invalid") from None
    if not math.isfinite(parsed):
        raise ValueError("numeric value must be finite")
    if positive and parsed <= 0:
        raise ValueError("numeric value must be positive")
    if nonnegative and parsed < 0:
        raise ValueError("numeric value must be nonnegative")
    return parsed


def _parse_requested_dates(start_date: str, end_date: str) -> tuple[datetime, datetime]:
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        raise DataFetchError("crypto date range must use YYYY-MM-DD") from None
    if end < start:
        raise DataFetchError("crypto end_date must not precede start_date")
    return start, end


class CryptoCoingeckoFetcher(BaseFetcher):
    """CoinGecko provider restricted to the explicit crypto market."""

    name = "CryptoCoingeckoFetcher"
    priority = 10

    def __init__(
        self,
        *,
        config: Any = None,
        api_base: str | None = None,
        session: requests.Session | None = None,
        api_key: str | None = None,
        api_plan: str | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if config is None:
            from src.config import get_config
            config = get_config()
        self.priority = int(getattr(config, "crypto_coingecko_priority", 10))
        if self.priority < 0 or self.priority > 99:
            raise ValueError("crypto CoinGecko priority must be between 0 and 99")

        plan = (api_plan or getattr(config, "coingecko_api_plan", "keyless") or "keyless").strip().lower()
        if plan not in {"keyless", "demo", "pro"}:
            raise ValueError("CoinGecko API plan must be keyless, demo, or pro")
        key = api_key if api_key is not None else getattr(config, "coingecko_api_key", None)
        key = str(key or "").strip() or None
        configured_base = api_base or getattr(config, "coingecko_api_base", None)
        default_base = _PRO_API_BASE if plan == "pro" else _DEMO_API_BASE
        base = str(configured_base or default_base).rstrip("/")
        parsed_base = urlsplit(base)
        if parsed_base.scheme != "https" or not parsed_base.hostname:
            raise ValueError("CoinGecko API base must be an absolute HTTPS URL")
        if (parsed_base.query or parsed_base.fragment or parsed_base.username or parsed_base.password):
            raise ValueError("CoinGecko API base must not contain credentials, query, or fragment")
        if plan in {"demo", "pro"}:
            if not key:
                raise ValueError(f"CoinGecko {plan} plan requires an API key")
            if parsed_base.hostname.lower() != _OFFICIAL_AUTH_ORIGINS[plan]:
                raise ValueError("CoinGecko credentials may only be sent to the matching official origin")
        elif key:
            raise ValueError("CoinGecko keyless plan must not configure an API key")

        self._api_base = base
        self._api_plan = plan
        self._api_key = key
        self._session = session
        self._sleeper = sleeper
        self._cooldown_until = 0.0

    def _require_crypto_code(self, stock_code: str) -> str:
        normalized = normalize_crypto_symbol(stock_code)
        if normalized is None:
            raise DataFetchError(
                f"[{self.name}] use {CRYPTO_NAMESPACE_PREFIX}TICKER (for example crypto:BTC)"
            )
        ticker = parse_crypto_symbol(normalized)
        assert ticker is not None
        try:
            ticker_to_coingecko_id(ticker)
        except ValueError as exc:
            raise DataFetchError(f"[{self.name}] {exc}") from exc
        return normalized

    def _coin_id_for_code(self, stock_code: str) -> str:
        normalized = self._require_crypto_code(stock_code)
        ticker = parse_crypto_symbol(normalized)
        assert ticker is not None
        return ticker_to_coingecko_id(ticker)

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self._api_plan == "demo" and self._api_key:
            headers["x-cg-demo-api-key"] = self._api_key
        elif self._api_plan == "pro" and self._api_key:
            headers["x-cg-pro-api-key"] = self._api_key
        return headers

    def _request_json(self, path: str, params: Optional[Mapping[str, Any]] = None) -> Any:
        if not path.startswith("/"):
            raise DataFetchError(f"[{self.name}] request path is invalid")
        last_error = "request failed"
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = safe_get(
                    f"{self._api_base}{path}",
                    params=dict(params or {}),
                    headers=self._headers(),
                    timeout=20,
                    max_response_bytes=4 * 1024 * 1024,
                    allow_redirects=False,
                    transport=self._session,
                )
                if 300 <= int(response.status_code) < 400:
                    raise DataFetchError("CoinGecko redirects are not accepted")
                if response.status_code == 429:
                    retry_after_raw = response.headers.get("Retry-After")
                    try:
                        retry_after = float(retry_after_raw) if retry_after_raw else 2 ** attempt
                    except (TypeError, ValueError):
                        retry_after = 2 ** attempt
                    delay = max(0.0, min(retry_after, _MAX_RETRY_DELAY_SECONDS))
                    self._cooldown_until = time.monotonic() + delay
                    last_error = "rate_limited"
                    if attempt + 1 < _MAX_ATTEMPTS:
                        self._sleeper(delay)
                        continue
                    break
                response.raise_for_status()
                payload = response.json()
                self._cooldown_until = 0.0
                return payload
            except OutboundPolicyError as exc:
                raise DataFetchError(f"[{self.name}] {exc}") from exc
            except (requests.RequestException, ValueError, TypeError) as exc:
                last_error = str(exc)
                if attempt + 1 < _MAX_ATTEMPTS:
                    delay = min(2 ** attempt, _MAX_RETRY_DELAY_SECONDS)
                    self._cooldown_until = time.monotonic() + delay
                    self._sleeper(delay)
                    continue
        raise DataFetchError(f"[{self.name}] HTTP request failed for {path}: {last_error}")

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        coin_id = self._coin_id_for_code(stock_code)
        start, end = _parse_requested_dates(start_date, end_date)
        end_exclusive = end + timedelta(days=1)
        payload = self._request_json(
            f"/coins/{coin_id}/market_chart/range",
            params={
                "vs_currency": "usd",
                "from": int(start.timestamp()),
                "to": int(end_exclusive.timestamp()) - 1,
            },
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("prices"), list):
            raise DataFetchError(f"[{self.name}] malformed range response for {stock_code}")
        volume_by_ts: Dict[int, float] = {}
        for item in payload.get("total_volumes") or []:
            if isinstance(item, list) and len(item) >= 2:
                try:
                    volume_by_ts[int(item[0])] = _finite_float(item[1], nonnegative=True)
                except (TypeError, ValueError):
                    continue
        rows = []
        for item in payload["prices"]:
            if not isinstance(item, list) or len(item) < 2:
                continue
            try:
                ts = int(item[0])
                price = _finite_float(item[1], positive=True)
                observed = datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc)
            except (OSError, OverflowError, TypeError, ValueError):
                continue
            if start <= observed < end_exclusive:
                rows.append({"ts": ts, "price": price, "usd_value_24h": volume_by_ts.get(ts)})
        if not rows:
            raise DataFetchError(f"[{self.name}] no observations in requested UTC range")
        return pd.DataFrame(rows)

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=STANDARD_COLUMNS)
        out = df.copy().sort_values("ts").drop_duplicates("ts", keep="last")
        out["observed_at"] = pd.to_datetime(out["ts"], unit="ms", utc=True)
        out["date"] = out["observed_at"].dt.date
        daily = out.groupby("date", sort=True).agg(
            open=("price", "first"), high=("price", "max"), low=("price", "min"),
            close=("price", "last"), amount=("usd_value_24h", "last"),
            close_timestamp=("observed_at", "last"), observation_count=("price", "size"),
        ).reset_index()
        for column in ("open", "high", "low", "close"):
            daily[column] = daily[column].map(lambda value: _finite_float(value, positive=True))
        invalid = (
            (daily["high"] < daily[["open", "close"]].max(axis=1))
            | (daily["low"] > daily[["open", "close"]].min(axis=1))
            | (daily["high"] < daily["low"])
        )
        if bool(invalid.any()) or daily["date"].duplicated().any():
            raise DataFetchError(f"[{self.name}] invalid UTC daily OHLC invariants")
        daily["volume"] = 0.0
        daily["amount"] = (
            pd.to_numeric(daily["amount"], errors="coerce")
            .replace([float("inf"), float("-inf")], pd.NA)
            .fillna(0.0)
        )
        daily["pct_chg"] = daily["close"].pct_change().mul(100).fillna(0.0).round(2)
        daily["code"] = self._require_crypto_code(stock_code)
        daily["market"] = "crypto"
        daily["currency"] = "USD"
        daily["source"] = "coingecko"
        daily["granularity"] = "utc_calendar_day"
        current_utc_date = datetime.now(timezone.utc).date()
        daily["completeness"] = daily["date"].map(
            lambda value: "in_progress" if value == current_utc_date else "complete_utc_day"
        )
        daily["amount_period"] = "provider_total_volume_sample"
        daily["volume_unit"] = "unavailable"
        daily["close_timestamp"] = daily["close_timestamp"].map(lambda value: value.isoformat())
        keep = ["code"] + STANDARD_COLUMNS + [
            "market", "currency", "source", "granularity", "completeness",
            "close_timestamp", "observation_count", "amount_period", "volume_unit",
        ]
        return daily[[column for column in keep if column in daily.columns]]

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        if not is_crypto_symbol(stock_code):
            return None
        try:
            normalized = self._require_crypto_code(stock_code)
            coin_id = self._coin_id_for_code(normalized)
            payload = self._request_json(
                "/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd", "include_24hr_change": "true",
                        "include_24hr_vol": "true", "include_last_updated_at": "true"},
            )
            row = payload.get(coin_id) if isinstance(payload, dict) else None
            if not isinstance(row, dict):
                return None
            price = _finite_float(row.get("usd"), positive=True)
            change = None if row.get("usd_24h_change") is None else _finite_float(row["usd_24h_change"])
            amount = None if row.get("usd_24h_vol") is None else _finite_float(row["usd_24h_vol"], nonnegative=True)
            updated = int(_finite_float(row.get("last_updated_at"), positive=True))
            provider_timestamp = datetime.fromtimestamp(updated, tz=timezone.utc).isoformat()
        except (DataFetchError, OSError, OverflowError, TypeError, ValueError) as exc:
            log_safe_exception(logger, "CoinGecko realtime quote failed", exc,
                               error_code="crypto_coingecko_realtime_failed", level=logging.WARNING,
                               context={"symbol": stock_code})
            return None
        missing = [field for field, value in {"asset_volume": None, "previous_utc_close": None}.items() if value is None]
        return UnifiedRealtimeQuote(
            code=normalized, source=RealtimeSource.COINGECKO, price=price,
            change_pct=round(change, 2) if change is not None else None,
            change_amount=None, volume=None, amount=amount, pre_close=None,
            provider_timestamp=provider_timestamp, market="crypto", currency="USD",
            data_quality="partial", missing_fields=missing,
            granularity="realtime", amount_period="rolling_24h",
        )

    def get_stock_name(self, stock_code: str) -> Optional[str]:
        if not is_crypto_symbol(stock_code):
            return None
        normalized = self._require_crypto_code(stock_code)
        ticker = parse_crypto_symbol(normalized)
        assert ticker is not None
        return ticker

    def get_limit_up_pool(self, date: Optional[str] = None, n: int = 20) -> Optional[list]:
        del date, n
        return []

    def is_available_for_request(self, capability: str = "") -> bool:
        del capability
        return time.monotonic() >= self._cooldown_until


def build_crypto_provider_registration(*, config: Any = None) -> DataProviderRegistration:
    return DataProviderRegistration(
        provider_id="crypto_coingecko",
        factory=lambda: CryptoCoingeckoFetcher(config=config),
        markets=frozenset({"crypto"}),
        capabilities=frozenset({"daily_data", "realtime_quote", "stock_name"}),
    )


def attach_crypto_provider(manager: Any, *, config: Any = None) -> CryptoCoingeckoFetcher:
    """Compatibility helper; production registration uses the declared plugin contract."""
    fetcher = CryptoCoingeckoFetcher(config=config)
    add = getattr(manager, "add_fetcher", None)
    if not callable(add):
        raise TypeError("manager must provide add_fetcher(fetcher)")
    add(fetcher)
    return fetcher


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "CryptoCoingeckoFetcher", "SUPPORTED_CRYPTO_ASSETS_VERSION",
    "attach_crypto_provider", "build_crypto_provider_registration",
    "ticker_to_coingecko_id", "utc_now_iso",
]
