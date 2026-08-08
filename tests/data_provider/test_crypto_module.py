# -*- coding: utf-8 -*-
"""Offline tests for crypto market enum, symbol namespace, and CoinGecko fetcher.

Issue #236 / T13. Network is mocked; this file must stay out of the network mark.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data_provider.crypto_coingecko_fetcher import (
    CryptoCoingeckoFetcher,
    attach_crypto_provider,
    build_crypto_provider_registration,
    ticker_to_coingecko_id,
)
from data_provider.plugin_registry import DATA_PROVIDER_MARKETS, DataProviderRegistration
from data_provider.symbol_normalization import (
    _market_tag,
    canonical_stock_code,
    is_crypto_symbol,
    normalize_crypto_symbol,
    normalize_stock_code,
    parse_crypto_symbol,
)
from data_provider.us_index_mapping import is_us_stock_code


# ---------------------------------------------------------------------------
# Market enum regression: legacy six markets remain valid
# ---------------------------------------------------------------------------


def test_data_provider_markets_includes_legacy_six_and_crypto() -> None:
    legacy = {"cn", "hk", "us", "jp", "kr", "tw"}
    assert legacy.issubset(DATA_PROVIDER_MARKETS)
    assert "crypto" in DATA_PROVIDER_MARKETS


def test_crypto_registration_accepted_by_contract() -> None:
    registration = build_crypto_provider_registration()
    assert registration.provider_id == "crypto_coingecko"
    assert registration.markets == frozenset({"crypto"})
    assert "daily_data" in registration.capabilities


def test_legacy_market_registration_still_valid() -> None:
    """Existing equity market sets must still construct after enum expansion."""
    for markets in (
        frozenset({"cn"}),
        frozenset({"cn", "hk"}),
        frozenset({"us"}),
        frozenset({"jp", "kr", "tw"}),
        frozenset({"cn", "hk", "us", "jp", "kr", "tw"}),
    ):
        reg = DataProviderRegistration(
            provider_id="legacy-probe",
            factory=lambda: None,
            markets=markets,
            capabilities=frozenset({"daily_data"}),
        )
        assert reg.markets == markets


# ---------------------------------------------------------------------------
# Symbol namespace: crypto must not collide with equity bare tickers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("crypto:BTC", "crypto:BTC"),
        ("CRYPTO:eth", "crypto:ETH"),
        ("crypto:bitcoin", "crypto:BITCOIN"),
        ("crypto:1INCH", "crypto:1INCH"),
    ],
)
def test_normalize_crypto_namespace(raw: str, expected: str) -> None:
    assert normalize_stock_code(raw) == expected
    assert normalize_crypto_symbol(raw) == expected
    assert is_crypto_symbol(raw) is True
    assert _market_tag(raw) == "crypto"
    assert canonical_stock_code(raw) == expected


@pytest.mark.parametrize(
    "bare",
    ["BTC", "ETH", "SOL", "AAPL", "MSFT"],
)
def test_bare_tickers_are_not_crypto_and_remain_us_candidates(bare: str) -> None:
    assert is_crypto_symbol(bare) is False
    assert parse_crypto_symbol(bare) is None
    assert normalize_crypto_symbol(bare) is None
    assert _market_tag(bare) != "crypto"
    # Letter tickers stay on the equity US pattern (the collision risk).
    assert is_us_stock_code(bare) is True
    assert normalize_stock_code(bare) == bare


def test_crypto_eth_not_misclassified_as_us_equity() -> None:
    assert is_us_stock_code("crypto:ETH") is False
    assert is_us_stock_code(normalize_stock_code("crypto:eth")) is False
    assert _market_tag("crypto:ETH") == "crypto"
    assert _market_tag("ETH") == "us"


def test_equity_codes_unchanged_by_crypto_helpers() -> None:
    assert normalize_stock_code("600519") == "600519"
    assert normalize_stock_code("hk00700") == "HK00700"
    assert normalize_stock_code("7203.T") == "7203.T"
    assert _market_tag("600519") == "cn"
    assert _market_tag("HK00700") == "hk"


def test_invalid_crypto_namespace_rejected() -> None:
    assert parse_crypto_symbol("crypto:") is None
    assert parse_crypto_symbol("crypto: ") is None
    assert parse_crypto_symbol("crypto:BTC ETH") is None


# ---------------------------------------------------------------------------
# CoinGecko fetcher (offline fixtures)
# ---------------------------------------------------------------------------


def _ohlc_fixture() -> list[list[float]]:
    # Two UTC daily candles (ms timestamps).
    return [
        [1_704_067_200_000, 42000.0, 43000.0, 41000.0, 42500.0],  # 2024-01-01
        [1_704_153_600_000, 42500.0, 44000.0, 42000.0, 43200.0],  # 2024-01-02
    ]


def test_ticker_to_coingecko_id_mapping() -> None:
    assert ticker_to_coingecko_id("BTC") == "bitcoin"
    assert ticker_to_coingecko_id("ETH") == "ethereum"
    assert ticker_to_coingecko_id("bitcoin") == "bitcoin"


def test_fetcher_rejects_non_crypto_symbols() -> None:
    fetcher = CryptoCoingeckoFetcher(session=MagicMock())
    with pytest.raises(Exception) as excinfo:
        fetcher.get_daily_data("BTC", start_date="2024-01-01", end_date="2024-01-10")
    assert "crypto:" in str(excinfo.value).lower() or "namespace" in str(excinfo.value).lower()


def test_fetcher_normalizes_ohlc_fixture_offline() -> None:
    session = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = _ohlc_fixture()
    session.get.return_value = response

    fetcher = CryptoCoingeckoFetcher(session=session)
    # Bypass random_sleep for speed/determinism
    fetcher.random_sleep = lambda *a, **k: None  # type: ignore[method-assign]

    df = fetcher.get_daily_data(
        "crypto:BTC",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )
    assert not df.empty
    for column in ("date", "open", "high", "low", "close", "volume", "amount", "pct_chg"):
        assert column in df.columns
    assert len(df) >= 2
    assert float(df.iloc[-1]["close"]) == pytest.approx(43200.0)
    # Volume is explicitly zero when CoinGecko OHLC has none (no fabrication).
    assert (pd.to_numeric(df["volume"], errors="coerce") >= 0).all()
    called_url = session.get.call_args.args[0]
    assert "bitcoin" in called_url
    assert "ohlc" in called_url


def test_fetcher_realtime_quote_offline() -> None:
    session = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "bitcoin": {
            "usd": 50000.0,
            "usd_24h_change": 2.5,
            "usd_24h_vol": 1.2e9,
        }
    }
    session.get.return_value = response
    fetcher = CryptoCoingeckoFetcher(session=session)
    fetcher.random_sleep = lambda *a, **k: None  # type: ignore[method-assign]

    quote = fetcher.get_realtime_quote("crypto:BTC")
    assert quote is not None
    assert quote.code == "crypto:BTC"
    assert quote.price == pytest.approx(50000.0)
    assert quote.change_pct == pytest.approx(2.5)
    assert quote.pre_close is not None
    assert quote.pre_close == pytest.approx(50000.0 / 1.025, rel=1e-4)

    # Bare equity-shaped ticker must not be served as crypto.
    assert fetcher.get_realtime_quote("BTC") is None


def test_limit_up_pool_empty_for_crypto() -> None:
    fetcher = CryptoCoingeckoFetcher(session=MagicMock())
    assert fetcher.get_limit_up_pool() == []


def test_attach_crypto_provider_uses_add_fetcher() -> None:
    attached: list[Any] = []
    manager = SimpleNamespace(add_fetcher=lambda f: attached.append(f))
    fetcher = attach_crypto_provider(manager)
    assert isinstance(fetcher, CryptoCoingeckoFetcher)
    assert attached == [fetcher]


def test_capability_catalog_lists_crypto_fetcher() -> None:
    from data_provider import _capability_catalog as catalog

    assert "crypto" in catalog._DAILY_MARKETS
    assert catalog._DAILY_MARKET_FETCHER_SUPPORT["CryptoCoingeckoFetcher"] == {"crypto"}
    assert catalog._BUILTIN_DATA_PROVIDER_IDS["CryptoCoingeckoFetcher"] == "crypto_coingecko"
