"""End-to-end contract checks for the default-off crypto market-data slice."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from data_provider.base import BaseFetcher, DataFetcherManager
from data_provider.crypto_coingecko_fetcher import CryptoCoingeckoFetcher
from data_provider.realtime_types import RealtimeSource, UnifiedRealtimeQuote
from src.core.trading_calendar import (
    MarketPhase,
    MarketSessionStatus,
    build_market_phase_context,
    classify_market_session,
    get_market_for_stock,
)
from src.market.context import detect_market, get_market_guidelines
from src.services.stock_code_utils import canonicalize_analysis_stock_code
from src.services.stock_list_parser import normalize_stock_codes


def _crypto_config(**overrides):
    values = {
        "crypto_coingecko_priority": 10,
        "coingecko_api_plan": "keyless",
        "coingecko_api_key": None,
        "coingecko_api_base": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_public_identity_context_and_calendar_are_crypto_specific() -> None:
    assert canonicalize_analysis_stock_code("CRYPTO:btc") == "crypto:BTC"
    assert canonicalize_analysis_stock_code("BTC") == "BTC"
    assert detect_market("crypto:BTC") == "crypto"
    assert get_market_for_stock("crypto:BTC") == "crypto"
    assert "A-share" not in get_market_guidelines("crypto:BTC", "en")
    assert "24x7 UTC" in get_market_guidelines("crypto:BTC", "en")
    now = datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    context = build_market_phase_context(market="crypto", current_time=now)
    assert context.phase == MarketPhase.INTRADAY
    assert context.is_trading_day is True
    assert context.is_market_open_now is True
    assert classify_market_session("crypto", now.date()) == MarketSessionStatus.OPEN


def test_api_cli_bot_and_chat_keep_the_same_identity() -> None:
    from api.v1.services.analysis_api_service import AnalysisApiService
    from bot.stock_symbols import parse_bot_stock_symbol
    from src.agent.chat_context import build_agent_chat_market_context

    service = AnalysisApiService()
    assert service.resolve_and_normalize_input("crypto:btc") == "crypto:BTC"
    assert normalize_stock_codes(["crypto:btc", "BTC"]) == ["crypto:BTC", "BTC"]
    bot_symbol = parse_bot_stock_symbol("crypto:btc")
    assert (bot_symbol.code, bot_symbol.market) == ("crypto:BTC", "crypto")
    chat = build_agent_chat_market_context({"stock_code": "crypto:btc"}, report_language="en")
    assert chat.stock_codes == ("crypto:BTC",)
    assert chat.markets == ("crypto",)
    assert "UTC (24x7)" in chat.prompt_section


@pytest.mark.parametrize(
    "plan,base,header",
    [
        ("demo", "https://api.coingecko.com/api/v3", "x-cg-demo-api-key"),
        ("pro", "https://pro-api.coingecko.com/api/v3", "x-cg-pro-api-key"),
    ],
)
def test_credentials_are_bound_to_matching_official_plan(plan, base, header) -> None:
    fetcher = CryptoCoingeckoFetcher(
        config=_crypto_config(), api_plan=plan, api_base=base, api_key="secret"
    )
    assert fetcher._headers() == {"Accept": "application/json", header: "secret"}
    with pytest.raises(ValueError, match="official origin"):
        CryptoCoingeckoFetcher(
            config=_crypto_config(), api_plan=plan,
            api_base="https://example.com/api/v3", api_key="secret",
        )


def test_keyless_mode_rejects_accidental_credentials() -> None:
    with pytest.raises(ValueError, match="must not configure"):
        CryptoCoingeckoFetcher(config=_crypto_config(), api_key="secret")


def test_local_only_blocks_before_injected_transport(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_ONLY_MODE", "true")
    transport = MagicMock()
    fetcher = CryptoCoingeckoFetcher(config=_crypto_config(), session=transport, sleeper=lambda _: None)
    with pytest.raises(Exception, match="LOCAL_ONLY_MODE"):
        fetcher._request_json("/ping")
    transport.get.assert_not_called()


def test_bounded_429_retry_and_cooldown(monkeypatch) -> None:
    responses = []
    for _ in range(3):
        response = MagicMock(status_code=429, headers={"Retry-After": "99"})
        response.raise_for_status.side_effect = RuntimeError("unexpected")
        responses.append(response)
    safe_get = MagicMock(side_effect=responses)
    monkeypatch.setattr("data_provider.crypto_coingecko_fetcher.safe_get", safe_get)
    sleeps = []
    fetcher = CryptoCoingeckoFetcher(
        config=_crypto_config(), sleeper=lambda delay: sleeps.append(delay)
    )
    with pytest.raises(Exception, match="rate_limited"):
        fetcher._request_json("/ping")
    assert safe_get.call_count == 3
    assert sleeps == [2.0, 2.0]
    assert fetcher.is_available_for_request() is False


class _EquitySpy(BaseFetcher):
    name = "YfinanceFetcher"
    priority = 1

    def __init__(self) -> None:
        self.daily_calls = 0
        self.realtime_calls = 0

    def _fetch_raw_data(self, stock_code, start_date, end_date):
        self.daily_calls += 1
        raise AssertionError("equity provider received crypto daily request")

    def _normalize_data(self, df, stock_code):
        return df

    def get_realtime_quote(self, stock_code):
        self.realtime_calls += 1
        raise AssertionError("equity provider received crypto realtime request")


class _CryptoSpy(BaseFetcher):
    name = "CryptoCoingeckoFetcher"
    priority = 10

    def _fetch_raw_data(self, stock_code, start_date, end_date):
        return pd.DataFrame(
            [{"date": start_date, "open": 1.0, "high": 2.0, "low": 1.0,
              "close": 2.0, "volume": 0.0, "amount": 10.0, "pct_chg": 0.0}]
        )

    def _normalize_data(self, df, stock_code):
        return df

    def get_realtime_quote(self, stock_code):
        return UnifiedRealtimeQuote(
            code=stock_code, source=RealtimeSource.COINGECKO, price=2.0,
            market="crypto", currency="USD",
        )


def test_manager_routes_crypto_without_touching_equity(monkeypatch) -> None:
    equity = _EquitySpy()
    crypto = _CryptoSpy()
    manager = DataFetcherManager(fetchers=[equity, crypto])
    frame, source = manager.get_daily_data(
        "crypto:BTC", start_date="2024-01-01", end_date="2024-01-01"
    )
    assert not frame.empty
    assert source == "CryptoCoingeckoFetcher"
    monkeypatch.setattr(
        "src.config.get_config",
        lambda: SimpleNamespace(enable_realtime_quote=True, realtime_cache_ttl=600),
    )
    quote = manager.get_realtime_quote("crypto:BTC")
    assert quote is not None and quote.code == "crypto:BTC"
    assert equity.daily_calls == 0
    assert equity.realtime_calls == 0


def test_production_manager_registers_exactly_one_provider_when_enabled(monkeypatch) -> None:
    import src.config as config_module

    configured = replace(
        config_module.get_config(),
        crypto_provider_enabled=True,
        coingecko_api_plan="keyless",
        coingecko_api_key=None,
        coingecko_api_base=None,
        crypto_coingecko_priority=10,
    )
    monkeypatch.setattr(config_module, "get_config", lambda: configured)
    manager = DataFetcherManager()
    assert manager.available_fetchers.count("CryptoCoingeckoFetcher") == 1
    assert [
        fetcher.name
        for fetcher in manager._get_fetchers_for_capability(
            "realtime_quote", market="crypto"
        )
    ] == ["CryptoCoingeckoFetcher"]


def test_crypto_fundamentals_are_explicitly_not_supported(monkeypatch) -> None:
    manager = DataFetcherManager(fetchers=[_CryptoSpy()])
    monkeypatch.setattr(
        "src.config.get_config",
        lambda: SimpleNamespace(enable_fundamental_pipeline=True),
    )
    result = manager.get_fundamental_context("crypto:BTC")
    assert result["market"] == "crypto"
    assert result["status"] == "not_supported"
    assert "do not apply" in " ".join(result.get("errors", [])).lower()
