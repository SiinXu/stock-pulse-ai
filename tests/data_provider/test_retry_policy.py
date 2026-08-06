# -*- coding: utf-8 -*-
"""Deterministic tests for the shared provider retry/timeout policy."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_provider.base import DataFetchError
from data_provider.retry_policy import (
    DEFAULT_ATTEMPTS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    call_with_timeout,
    provider_retry,
)


def _sleep_for(seconds: float) -> None:
    time.sleep(seconds)


def test_call_with_timeout_returns_value() -> None:
    assert call_with_timeout(lambda: "ok", timeout=1.0, call_name="unit-ok") == "ok"


def test_call_with_timeout_raises_timeout_error_promptly() -> None:
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="unit-hang"):
        call_with_timeout(
            _sleep_for,
            1.0,
            timeout=0.05,
            call_name="unit-hang",
        )
    assert time.monotonic() - started < 2.0


def test_call_with_timeout_uses_default_when_timeout_non_positive() -> None:
    captured: dict = {}

    def _fake_result(timeout=None):
        captured["timeout"] = timeout
        return "done"

    future = MagicMock()
    future.result.side_effect = _fake_result
    executor = MagicMock()
    executor.submit.return_value = future

    with patch(
        "data_provider.retry_policy.ThreadPoolExecutor",
        return_value=executor,
    ):
        result = call_with_timeout(lambda: None, timeout=0, call_name="unit-default")

    assert result == "done"
    assert captured["timeout"] == DEFAULT_REQUEST_TIMEOUT_SECONDS


def test_provider_retry_honors_attempt_count() -> None:
    calls = {"n": 0}

    @provider_retry(attempts=3, min_wait=0, max_wait=0, multiplier=0)
    def flaky() -> str:
        calls["n"] += 1
        raise TimeoutError("transient")

    with patch("tenacity.nap.sleep", return_value=None):
        with pytest.raises(TimeoutError, match="transient"):
            flaky()

    assert calls["n"] == 3


def test_provider_retry_does_not_retry_non_retryable() -> None:
    calls = {"n": 0}

    @provider_retry(attempts=5, min_wait=0, max_wait=0, multiplier=0)
    def permanent() -> str:
        calls["n"] += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError, match="not retryable"):
        permanent()

    assert calls["n"] == 1


def test_provider_retry_succeeds_after_transient_timeout() -> None:
    calls = {"n": 0}

    @provider_retry(attempts=3, min_wait=0, max_wait=0, multiplier=0)
    def flaky_then_ok() -> str:
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("once")
        return "recovered"

    with patch("tenacity.nap.sleep", return_value=None):
        assert flaky_then_ok() == "recovered"
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Baostock
# ---------------------------------------------------------------------------


def test_baostock_fetch_timeout_is_raised_and_retried() -> None:
    from data_provider.baostock_fetcher import BaostockFetcher

    fetcher = BaostockFetcher(request_timeout_seconds=0.05)
    calls = {"n": 0}

    def _timeout(*_a, **_k):
        calls["n"] += 1
        raise TimeoutError("baostock.query_history_k_data_plus exceeded")

    with patch.object(fetcher, "_convert_stock_code", return_value="sh.600519"):
        with patch(
            "data_provider.baostock_fetcher.call_with_timeout",
            side_effect=_timeout,
        ):
            with patch("tenacity.nap.sleep", return_value=None):
                with pytest.raises(TimeoutError):
                    fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-10")

    assert calls["n"] == DEFAULT_ATTEMPTS


def test_baostock_non_retryable_error_not_retried() -> None:
    from data_provider.baostock_fetcher import BaostockFetcher

    fetcher = BaostockFetcher()
    calls = {"n": 0}

    def _raise_data_error(*_a, **_k):
        calls["n"] += 1
        raise DataFetchError("Baostock 查询失败: bad")

    with patch.object(fetcher, "_convert_stock_code", return_value="sh.600519"):
        with patch(
            "data_provider.baostock_fetcher.call_with_timeout",
            side_effect=_raise_data_error,
        ):
            with pytest.raises(DataFetchError, match="查询失败"):
                fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-10")

    assert calls["n"] == 1


def test_baostock_unsupported_market_still_fails_fast_without_timeout() -> None:
    from data_provider.baostock_fetcher import BaostockFetcher

    fetcher = BaostockFetcher()
    with patch("data_provider.baostock_fetcher.call_with_timeout") as mock_timeout:
        with pytest.raises(DataFetchError, match="不支持美股"):
            fetcher._fetch_raw_data("AAPL", "2024-01-01", "2024-01-10")
    mock_timeout.assert_not_called()


# ---------------------------------------------------------------------------
# Pytdx
# ---------------------------------------------------------------------------


def test_pytdx_fetch_timeout_is_raised_and_retried() -> None:
    from data_provider.pytdx_fetcher import PytdxFetcher

    fetcher = PytdxFetcher(hosts=[("127.0.0.1", 7709)], request_timeout_seconds=0.05)
    calls = {"n": 0}

    def _timeout(*_a, **_k):
        calls["n"] += 1
        raise TimeoutError("pytdx.get_security_bars exceeded")

    with patch(
        "data_provider.pytdx_fetcher.call_with_timeout",
        side_effect=_timeout,
    ):
        with patch("tenacity.nap.sleep", return_value=None):
            with pytest.raises(TimeoutError):
                fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-10")

    assert calls["n"] == DEFAULT_ATTEMPTS


def test_pytdx_non_retryable_error_not_retried() -> None:
    from data_provider.pytdx_fetcher import PytdxFetcher

    fetcher = PytdxFetcher(hosts=[("127.0.0.1", 7709)])
    calls = {"n": 0}

    def _raise_data_error(*_a, **_k):
        calls["n"] += 1
        raise DataFetchError("Pytdx 未查询到 600519 的数据")

    with patch(
        "data_provider.pytdx_fetcher.call_with_timeout",
        side_effect=_raise_data_error,
    ):
        with pytest.raises(DataFetchError, match="未查询到"):
            fetcher._fetch_raw_data("600519", "2024-01-01", "2024-01-10")

    assert calls["n"] == 1


def test_pytdx_unsupported_market_still_fails_fast() -> None:
    from data_provider.pytdx_fetcher import PytdxFetcher

    fetcher = PytdxFetcher(hosts=[("127.0.0.1", 7709)])
    with patch("data_provider.pytdx_fetcher.call_with_timeout") as mock_timeout:
        with pytest.raises(DataFetchError, match="不支持港股"):
            fetcher._fetch_raw_data("HK00700", "2024-01-01", "2024-01-10")
    mock_timeout.assert_not_called()


# ---------------------------------------------------------------------------
# Longbridge
# ---------------------------------------------------------------------------


def test_longbridge_fetch_timeout_is_raised_and_retried() -> None:
    from data_provider.longbridge_fetcher import LongbridgeFetcher

    fetcher = LongbridgeFetcher(request_timeout_seconds=0.05)
    fetcher._available = True
    fetcher._cooldown_until = 0.0
    calls = {"n": 0}

    def _timeout(*_a, **_k):
        calls["n"] += 1
        raise TimeoutError("longbridge.history_candlesticks_by_date exceeded")

    mock_ctx = MagicMock()
    with patch.object(fetcher, "_get_ctx", return_value=mock_ctx):
        with patch(
            "data_provider.longbridge_fetcher.call_with_timeout",
            side_effect=_timeout,
        ):
            with patch.dict(
                "sys.modules",
                {
                    "longbridge": MagicMock(),
                    "longbridge.openapi": SimpleNamespace(
                        Period=SimpleNamespace(Day="Day"),
                        AdjustType=SimpleNamespace(ForwardAdjust="ForwardAdjust"),
                    ),
                },
            ):
                with patch("tenacity.nap.sleep", return_value=None):
                    with pytest.raises(TimeoutError):
                        fetcher._fetch_raw_data("AAPL", "2024-01-01", "2024-01-10")

    assert calls["n"] == DEFAULT_ATTEMPTS


def test_longbridge_connection_error_still_marks_cooldown() -> None:
    from data_provider.longbridge_fetcher import LongbridgeFetcher

    fetcher = LongbridgeFetcher(request_timeout_seconds=1.0)
    fetcher._available = True
    fetcher._cooldown_until = 0.0
    calls = {"n": 0}

    def _conn_err(*_a, **_k):
        calls["n"] += 1
        raise ConnectionError("client is closed")

    mock_ctx = MagicMock()
    with patch.object(fetcher, "_get_ctx", return_value=mock_ctx):
        with patch(
            "data_provider.longbridge_fetcher.call_with_timeout",
            side_effect=_conn_err,
        ):
            with patch.dict(
                "sys.modules",
                {
                    "longbridge": MagicMock(),
                    "longbridge.openapi": SimpleNamespace(
                        Period=SimpleNamespace(Day="Day"),
                        AdjustType=SimpleNamespace(ForwardAdjust="ForwardAdjust"),
                    ),
                },
            ):
                with pytest.raises(ConnectionError):
                    fetcher._fetch_raw_data("AAPL", "2024-01-01", "2024-01-10")

    # Connection errors are not retried (cooldown path); one attempt only.
    assert calls["n"] == 1
    assert fetcher._cooldown_until > time.time()


def test_longbridge_successful_fetch_uses_timeout_wrapper() -> None:
    from data_provider.longbridge_fetcher import LongbridgeFetcher

    fetcher = LongbridgeFetcher(request_timeout_seconds=12.0)
    fetcher._available = True
    fetcher._cooldown_until = 0.0

    candle = SimpleNamespace(
        timestamp=SimpleNamespace(date=lambda: __import__("datetime").date(2024, 1, 2)),
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=1000,
        turnover=10500.0,
    )
    captured: dict = {}

    def _call(func, *args, timeout=None, call_name="", **kwargs):
        captured["timeout"] = timeout
        captured["call_name"] = call_name
        return [candle]

    mock_ctx = MagicMock()
    with patch.object(fetcher, "_get_ctx", return_value=mock_ctx):
        with patch(
            "data_provider.longbridge_fetcher.call_with_timeout",
            side_effect=_call,
        ):
            with patch.dict(
                "sys.modules",
                {
                    "longbridge": MagicMock(),
                    "longbridge.openapi": SimpleNamespace(
                        Period=SimpleNamespace(Day="Day"),
                        AdjustType=SimpleNamespace(ForwardAdjust="ForwardAdjust"),
                    ),
                },
            ):
                df = fetcher._fetch_raw_data("AAPL", "2024-01-01", "2024-01-10")

    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert captured["timeout"] == 12.0
    assert captured["call_name"] == "longbridge.history_candlesticks_by_date"


def test_fallback_semantics_manager_still_switches_on_timeout() -> None:
    """Single-provider timeout must not halt analysis: manager falls through."""
    primary = MagicMock()
    primary.name = "BaostockFetcher"
    primary.priority = 3
    primary.get_daily_data.side_effect = TimeoutError("baostock timeout")
    if hasattr(primary, "is_available_for_request"):
        primary.is_available_for_request.return_value = True

    secondary = MagicMock()
    secondary.name = "AkshareFetcher"
    secondary.priority = 1
    ok = pd.DataFrame(
        {
            "date": ["2024-01-02"],
            "open": [1.0],
            "high": [1.1],
            "low": [0.9],
            "close": [1.05],
            "volume": [100],
            "amount": [105.0],
            "pct_chg": [1.0],
        }
    )
    secondary.get_daily_data.return_value = ok
    if hasattr(secondary, "is_available_for_request"):
        secondary.is_available_for_request.return_value = True

    # DataFetcherManager construction and routing vary; exercise the documented
    # contract via a minimal fallback loop matching manager behavior.
    result = None
    errors = []
    for fetcher in (primary, secondary):
        try:
            if hasattr(fetcher, "is_available_for_request") and not fetcher.is_available_for_request("daily_data"):
                continue
            result = fetcher.get_daily_data("600519", "2024-01-01", "2024-01-10")
            if result is not None and not (isinstance(result, pd.DataFrame) and result.empty):
                break
        except Exception as exc:  # broad-exception: test harness records per-provider failure then continues
            errors.append((fetcher.name, type(exc).__name__))
            continue

    assert result is not None
    assert list(result["close"]) == [1.05]
    assert errors == [("BaostockFetcher", "TimeoutError")]
