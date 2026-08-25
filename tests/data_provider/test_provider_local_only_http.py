# -*- coding: utf-8 -*-
"""LOCAL_ONLY_MODE must block remaining data-provider HTTP before egress.

Epic #218 item 2: these fetchers used raw requests/urllib and bypassed the
outbound wrapper. A gate block must surface as the same coded failure the
fallback layer already handles (DataFetchError or the fetcher's existing
network-error return), never as empty success and never as an unhandled
abort of an analysis run.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.data_provider.akshare_fetcher import AkshareFetcher
from src.data_provider.alphavantage_fetcher import AlphaVantageFetcher
from src.data_provider.base import DataFetchError, DataFetcherManager
from src.data_provider.finnhub_fetcher import FinnhubFetcher
from src.data_provider.realtime_types import CircuitBreaker
from src.data_provider.tencent_fetcher import TencentFetcher
from src.data_provider.tw_institutional_fetcher import TwInstitutionalFetcher
from src.data_provider.yfinance_fetcher import YfinanceFetcher
from src.security.outbound_policy import (
    LOCAL_ONLY_MODE_ENV,
    OutboundPolicyError,
    clear_outbound_activity_for_tests,
)
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)
from tests.data_provider.test_provider_fallback_contract import (
    _SequencedProvider,
    _ok_daily_frame,
)


@pytest.fixture(autouse=True)
def _clean_local_only_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(LOCAL_ONLY_MODE_ENV, raising=False)
    monkeypatch.delenv("OUTBOUND_HTTP_ALLOWLIST", raising=False)
    clear_outbound_activity_for_tests()
    monkeypatch.setattr(
        "src.data_provider.base.BaseFetcher.random_sleep",
        staticmethod(lambda *args, **kwargs: None),
    )
    yield
    clear_outbound_activity_for_tests()
    monkeypatch.delenv(LOCAL_ONLY_MODE_ENV, raising=False)


def _fresh_breaker() -> CircuitBreaker:
    return CircuitBreaker(
        failure_threshold=99,
        cooldown_seconds=60.0,
        health_window_size=20,
    )


def _tencent_daily() -> None:
    TencentFetcher().get_daily_data(
        "000001",
        start_date="2026-05-01",
        end_date="2026-05-10",
    )


def _alphavantage_daily() -> None:
    fetcher = AlphaVantageFetcher()
    fetcher._api_key = "test-key"
    fetcher._fetch_raw_data("AAPL", "2024-06-10", "2024-06-11")


def _finnhub_daily() -> None:
    fetcher = FinnhubFetcher()
    fetcher._api_key = "test-key"
    fetcher._fetch_raw_data("AAPL", "2024-06-10", "2024-06-11")


def _yfinance_daily() -> None:
    YfinanceFetcher()._fetch_raw_data("AAPL", "2024-06-10", "2024-06-11")


def _akshare_sina_quote():
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)
    fetcher._enforce_rate_limit = lambda: None
    return fetcher._get_stock_realtime_quote_sina("601006")


def _akshare_tencent_quote():
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)
    fetcher._enforce_rate_limit = lambda: None
    return fetcher._get_stock_realtime_quote_tencent("601006")


def _tw_institutional():
    return TwInstitutionalFetcher(min_request_interval=0).get_institutional_net(
        "2330.TW",
        "20260626",
    )


@pytest.mark.parametrize(
    ("fetcher_name", "invoke", "transport_target"),
    [
        ("TencentFetcher", _tencent_daily, "src.data_provider.tencent_fetcher.requests.get"),
        (
            "AlphaVantageFetcher",
            _alphavantage_daily,
            "src.data_provider.alphavantage_fetcher.requests.get",
        ),
        (
            "FinnhubFetcher",
            _finnhub_daily,
            "src.data_provider.finnhub_fetcher.requests.get",
        ),
        (
            "YfinanceFetcher",
            _yfinance_daily,
            "src.data_provider.yfinance_fetcher.urlopen",
        ),
        (
            "AkshareFetcher",
            _akshare_sina_quote,
            "src.data_provider.akshare_fetcher.requests.get",
        ),
        (
            "TwInstitutionalFetcher",
            _tw_institutional,
            "src.data_provider.tw_institutional_fetcher.requests.get",
        ),
    ],
)
def test_local_only_blocks_each_provider_http_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    fetcher_name: str,
    invoke,
    transport_target: str,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    transport = MagicMock(side_effect=AssertionError(f"{fetcher_name} egressed"))
    with patch(transport_target, transport):
        if fetcher_name in {"AkshareFetcher", "TwInstitutionalFetcher"}:
            result = invoke()
            assert result is None, (
                f"{fetcher_name} must keep its existing network-error return "
                "(None), not empty success data"
            )
        else:
            with pytest.raises(DataFetchError, match="LOCAL_ONLY_MODE") as exc_info:
                invoke()
            assert isinstance(exc_info.value.__cause__, OutboundPolicyError)
            assert exc_info.value.__cause__.reason == "local_only_mode_blocked"
    transport.assert_not_called()


def test_local_only_blocks_akshare_tencent_realtime_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    transport = MagicMock(side_effect=AssertionError("Akshare tencent realtime egressed"))
    with patch("src.data_provider.akshare_fetcher.requests.get", transport):
        assert _akshare_tencent_quote() is None
    transport.assert_not_called()


def test_local_only_tw_get_json_raises_coded_policy_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    transport = MagicMock(side_effect=AssertionError("tw institutional egressed"))
    fetcher = TwInstitutionalFetcher(min_request_interval=0)
    with patch("src.data_provider.tw_institutional_fetcher.requests.get", transport):
        with pytest.raises(OutboundPolicyError, match="local_only_mode_blocked") as exc_info:
            fetcher._get_json("https://www.twse.com.tw/rwd/zh/fund/T86")
    assert exc_info.value.reason == "local_only_mode_blocked"
    transport.assert_not_called()


def test_blocked_provider_does_not_abort_manager_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A LOCAL_ONLY block on one daily source must fall through to the next."""
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    tencent = TencentFetcher()
    tencent.priority = 0
    backup = _SequencedProvider("AkshareFetcher", 1, [_ok_daily_frame(11.0)])
    manager = DataFetcherManager(fetchers=[tencent, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        token = activate_run_diagnostic_context(
            trace_id="trace-local-only-isolation",
            stock_code="600519",
        )
        try:
            frame, source = manager.get_daily_data(
                "600519",
                start_date="2026-05-01",
                end_date="2026-05-10",
            )
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    assert source == "AkshareFetcher"
    assert not frame.empty
    assert float(frame.iloc[0]["close"]) == pytest.approx(11.0)
    assert backup.calls == 1
    failed_runs = [run for run in diagnostics["provider_runs"] if not run["success"]]
    assert failed_runs, "blocked TencentFetcher must be recorded as a provider failure"
    assert failed_runs[0]["provider"] == "TencentFetcher"
    assert failed_runs[0]["fallback_to"] == "AkshareFetcher"
    assert "OutboundPolicyError" in failed_runs[0]["error_type"] or "local_only" in (
        failed_runs[0].get("error_message") or ""
    ).lower()


def test_tencent_local_only_block_is_not_empty_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """allow_empty_daily_data must not turn a gate block into a successful empty frame."""
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    with pytest.raises(DataFetchError, match="LOCAL_ONLY_MODE"):
        TencentFetcher().get_daily_data(
            "000001",
            start_date="2026-05-01",
            end_date="2026-05-10",
        )


def test_yfinance_stooq_fallback_is_blocked_without_urlopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LOCAL_ONLY_MODE_ENV, "true")
    transport = MagicMock(side_effect=AssertionError("stooq urlopen egressed"))
    with patch("src.data_provider.yfinance_fetcher.urlopen", transport):
        quote = YfinanceFetcher()._get_us_stock_quote_from_stooq("AAPL")
    assert quote is None
    transport.assert_not_called()
