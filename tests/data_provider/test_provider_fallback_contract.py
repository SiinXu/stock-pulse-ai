# -*- coding: utf-8 -*-
"""Offline manager + parse-path fallback contract tests.

Extends the happy-path suite in ``test_provider_contracts.py`` and the circuit
suite in ``test_provider_resilience.py`` with explicit AGENTS.md data-source
fallback contracts:

1. Single provider failure → priority-ordered fallback; request does not abort.
2. All providers fail → ``DataFetchError`` with a readable message (never an
   empty DataFrame presented as success).
3. Field normalization → different raw provider shapes land on
   ``STANDARD_COLUMNS``.
4. Timeout / retry policy is bounded (no infinite retry).

All tests are offline (``pytest -m "not network"``). Failure fixtures live under
``tests/fixtures/provider_contracts/failures/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_provider.akshare_fetcher import AkshareFetcher
from data_provider.base import (
    STANDARD_COLUMNS,
    DataFetchError,
    DataFetcherManager,
    RateLimitError,
)
from data_provider.realtime_types import CircuitBreaker
from data_provider.retry_policy import DEFAULT_ATTEMPTS, provider_retry
from data_provider.tencent_fetcher import TencentFetcher, _extract_kline_rows
from data_provider.tushare_fetcher import TushareFetcher, _TushareHttpClient
from data_provider.yfinance_fetcher import YfinanceFetcher
from src.services.run_diagnostics import (
    activate_run_diagnostic_context,
    current_diagnostic_snapshot,
    reset_run_diagnostic_context,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "provider_contracts"
FAILURE_DIR = FIXTURE_DIR / "failures"
DAILY_REQUIRED = list(STANDARD_COLUMNS)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _frame_from_table(payload: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(payload["rows"], columns=payload["columns"])


def _ok_daily_frame(close: float = 10.2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2026-05-08"],
            "open": [10.0],
            "high": [10.5],
            "low": [9.8],
            "close": [close],
            "volume": [1000],
            "amount": [10200],
            "pct_chg": [2.0],
        }
    )


def _fresh_breaker() -> CircuitBreaker:
    """Process-local health is shared; isolate each manager contract case."""
    return CircuitBreaker(
        failure_threshold=99,
        cooldown_seconds=60.0,
        health_window_size=20,
    )


class _SequencedProvider:
    """Minimal DataProvider-shaped stub for manager fallback contracts."""

    def __init__(self, name: str, priority: int, outcomes: list[object]) -> None:
        self.name = name
        self.priority = priority
        self.outcomes = list(outcomes)
        self.calls = 0

    def get_daily_data(self, **_kwargs) -> Optional[pd.DataFrame]:
        self.calls += 1
        if not self.outcomes:
            raise AssertionError(f"{self.name} called more times than scripted")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome is None:
            return None
        assert isinstance(outcome, pd.DataFrame)
        return outcome.copy(deep=True)


# ---------------------------------------------------------------------------
# Contract inventory (asserted so the PR checklist cannot drift silently)
# ---------------------------------------------------------------------------


def test_builtin_daily_provider_market_support_inventory() -> None:
    """Document markets each builtin daily fetcher declares support for."""
    from data_provider._capability_catalog import _DAILY_MARKET_FETCHER_SUPPORT

    expected = {
        "EfinanceFetcher": {"cn"},
        "TencentFetcher": {"cn"},
        "AkshareFetcher": {"cn", "hk"},
        "TushareFetcher": {"cn", "hk"},
        "TickFlowFetcher": {"cn"},
        "PytdxFetcher": {"cn"},
        "BaostockFetcher": {"cn"},
        "YfinanceFetcher": {"cn", "hk", "us", "jp", "kr", "tw"},
        "LongbridgeFetcher": {"hk", "us"},
        "FinnhubFetcher": {"us"},
        "AlphaVantageFetcher": {"us"},
        "CryptoCoingeckoFetcher": {"crypto"},
    }
    assert _DAILY_MARKET_FETCHER_SUPPORT == expected


def test_failure_fixture_files_exist_and_declare_mode() -> None:
    """Guard the failure-fixture set listed in the contract inventory."""
    required = {
        "akshare_em_daily_empty.json": "empty",
        "akshare_em_daily_missing_close.json": "missing_field",
        "tencent_daily_kline_empty.json": "empty",
        "tencent_daily_kline_malformed.json": "format_error",
        "tushare_daily_pro_empty_items.json": "empty",
        "tushare_daily_pro_rate_limit.json": "rate_limit",
        "yfinance_daily_missing_volume.json": "missing_field",
    }
    for filename, mode in required.items():
        path = FAILURE_DIR / filename
        assert path.is_file(), f"missing failure fixture {filename}"
        payload = _load_json(path)
        assert payload["meta"]["failure_mode"] == mode


# ---------------------------------------------------------------------------
# Manager fallback: single source fails → next priority succeeds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError("upstream timeout"),
        RateLimitError("429 rate limited"),
        DataFetchError("provider empty after normalize"),
        pd.DataFrame(),
        None,
    ],
    ids=["timeout", "rate_limit", "data_fetch_error", "empty_frame", "none"],
)
def test_single_provider_failure_falls_back_by_priority(failure: object) -> None:
    """One failing source must not abort the request when a later source works."""
    primary = _SequencedProvider("EfinanceFetcher", 0, [failure])
    backup = _SequencedProvider("TencentFetcher", 1, [_ok_daily_frame(11.0)])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        token = activate_run_diagnostic_context(
            trace_id="trace-fallback-single",
            stock_code="600519",
        )
        try:
            frame, source = manager.get_daily_data("600519")
            diagnostics = current_diagnostic_snapshot()
        finally:
            reset_run_diagnostic_context(token)

    assert source == "TencentFetcher"
    assert not frame.empty
    assert float(frame.iloc[0]["close"]) == pytest.approx(11.0)
    assert primary.calls == 1
    assert backup.calls == 1
    # Exception failures always record a failed provider_run with fallback_to.
    # Empty/None are quality failures: they still continue the chain.
    assert diagnostics["provider_runs"][-1]["success"] is True
    assert diagnostics["provider_runs"][-1]["provider"] == "TencentFetcher"
    failed_runs = [run for run in diagnostics["provider_runs"] if not run["success"]]
    assert failed_runs, "primary failure must be recorded"
    assert failed_runs[0]["provider"] == "EfinanceFetcher"
    assert failed_runs[0]["fallback_to"] == "TencentFetcher"


def test_us_named_route_timeout_falls_back_to_next_named_source() -> None:
    """U.S. daily named route continues after the preferred source raises."""
    primary = _SequencedProvider("FinnhubFetcher", 2, [TimeoutError("finnhub down")])
    backup = _SequencedProvider("YfinanceFetcher", 4, [_ok_daily_frame(190.0)])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        frame, source = manager.get_daily_data("AAPL")

    assert source == "YfinanceFetcher"
    assert not frame.empty
    assert primary.calls == 1
    assert backup.calls == 1


# ---------------------------------------------------------------------------
# Manager fallback: all fail → explicit error, not empty success
# ---------------------------------------------------------------------------


def test_all_providers_raise_emits_readable_data_fetch_error() -> None:
    """Every exception path must raise DataFetchError listing each provider."""
    primary = _SequencedProvider("EfinanceFetcher", 0, [TimeoutError("t1")])
    backup = _SequencedProvider(
        "AkshareFetcher",
        1,
        [RateLimitError("quota exceeded")],
    )
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        with pytest.raises(DataFetchError) as exc_info:
            manager.get_daily_data("600519")

    message = str(exc_info.value)
    # Must not look like a successful empty payload.
    assert "600519" in message
    assert "EfinanceFetcher" in message
    assert "AkshareFetcher" in message
    assert "TimeoutError" in message or "t1" in message
    assert "RateLimitError" in message or "quota" in message
    assert primary.calls == 1
    assert backup.calls == 1


@pytest.mark.parametrize(
    "outcome",
    [pd.DataFrame(), None],
    ids=["empty_frame", "none"],
)
def test_all_providers_empty_still_raises_not_empty_success(outcome: object) -> None:
    """Empty / None results must not be returned as a successful empty frame.

    Defect note (documented, not fixed in this PR): when every provider returns
    empty/None without raising, the error summary currently has no per-provider
    detail lines. The hard contract is still: raise ``DataFetchError``, never
    return ``(empty_df, source)``.
    """
    primary = _SequencedProvider("EfinanceFetcher", 0, [outcome])
    backup = _SequencedProvider("TencentFetcher", 1, [outcome])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        with pytest.raises(DataFetchError) as exc_info:
            result = manager.get_daily_data("600519")
            # If the manager ever starts returning, force a hard failure here.
            pytest.fail(f"expected DataFetchError, got success: {result!r}")

    message = str(exc_info.value)
    assert "600519" in message
    assert "失败" in message or "fail" in message.lower()
    # After empty-result aggregation fix, per-provider lines must be present.
    assert "EfinanceFetcher" in message
    assert "TencentFetcher" in message
    assert "empty" in message.lower()


def test_no_eligible_providers_raises_readable_error() -> None:
    """Zero eligible providers must fail closed with a readable message.

    ``DataFetcherManager(fetchers=[])`` installs the default real providers
    (falsy list → defaults). Construct with a stub then clear the in-memory
    list so the daily route sees total_fetchers == 0 without network.
    """
    placeholder = _SequencedProvider("PlaceholderFetcher", 0, [_ok_daily_frame()])
    manager = DataFetcherManager(fetchers=[placeholder])
    with manager._fetchers_lock:
        manager._fetchers.clear()
        manager._fetchers_by_name.clear()

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        with pytest.raises(DataFetchError) as exc_info:
            manager.get_daily_data("600519")

    message = str(exc_info.value)
    assert "600519" in message
    assert "暂无可用数据源" in message or "数据源" in message
    assert placeholder.calls == 0


def test_non_cn_market_skips_unsupported_builtin_providers() -> None:
    """Outside CN, market support inventory filters builtins (e.g. Finnhub on HK)."""
    only_us = _SequencedProvider("FinnhubFetcher", 2, [_ok_daily_frame()])
    hk_capable = _SequencedProvider("YfinanceFetcher", 4, [_ok_daily_frame(88.0)])
    manager = DataFetcherManager(fetchers=[only_us, hk_capable])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        frame, source = manager.get_daily_data("hk00700")

    assert source == "YfinanceFetcher"
    assert float(frame.iloc[0]["close"]) == pytest.approx(88.0)
    assert only_us.calls == 0
    assert hk_capable.calls == 1


# ---------------------------------------------------------------------------
# Field normalization: multi-provider STANDARD_COLUMNS consistency
# ---------------------------------------------------------------------------


def test_normalized_daily_columns_match_across_recorded_providers() -> None:
    """Happy-path fixtures from different vendors must share STANDARD_COLUMNS."""
    frames: dict[str, pd.DataFrame] = {}

    ak = _load_json(FIXTURE_DIR / "akshare_em_daily.json")
    ak_fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)
    frames["akshare"] = ak_fetcher._clean_data(
        ak_fetcher._normalize_data(_frame_from_table(ak), "600519")
    )

    tx = _load_json(FIXTURE_DIR / "tencent_daily_kline.json")
    rows = _extract_kline_rows(tx["payload"], symbol="sz000001")
    tx_fetcher = TencentFetcher()
    frames["tencent"] = tx_fetcher._clean_data(
        tx_fetcher._normalize_data(pd.DataFrame(rows), "000001")
    )

    ts = _load_json(FIXTURE_DIR / "tushare_daily_pro.json")["response"]
    client = _TushareHttpClient(token="fixture-token-not-real", timeout=5)
    response = MagicMock(status_code=200, text=json.dumps(ts))
    with patch("data_provider.tushare_fetcher.safe_post", return_value=response):
        raw_ts = client.query("daily", ts_code="600519.SH")
    with patch(
        "data_provider.tushare_fetcher.get_config",
        return_value=SimpleNamespace(tushare_token=""),
    ):
        ts_fetcher = TushareFetcher()
    frames["tushare"] = ts_fetcher._clean_data(
        ts_fetcher._normalize_data(raw_ts, "600519")
    )

    yf = _load_json(FIXTURE_DIR / "yfinance_daily.json")
    raw_rows = pd.DataFrame(yf["rows"])
    raw_yf = raw_rows.set_index(pd.to_datetime(raw_rows["Date"])).drop(columns=["Date"])
    yf_fetcher = YfinanceFetcher()
    frames["yfinance"] = yf_fetcher._clean_data(
        yf_fetcher._normalize_data(raw_yf, "AAPL")
    )

    for name, frame in frames.items():
        for column in DAILY_REQUIRED:
            assert column in frame.columns, f"{name} missing {column}"
        assert len(frame) >= 1, f"{name} produced no rows"
        closes = pd.to_numeric(frame["close"], errors="coerce")
        assert closes.notna().all() and (closes > 0).all(), f"{name} invalid close"


# ---------------------------------------------------------------------------
# Failure fixtures through parse / normalize paths
# ---------------------------------------------------------------------------


def test_akshare_empty_daily_fixture_normalizes_to_empty_or_raises() -> None:
    payload = _load_json(FAILURE_DIR / "akshare_em_daily_empty.json")
    raw = _frame_from_table(payload)
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)
    normalized = fetcher._normalize_data(raw, "600519")
    cleaned = fetcher._clean_data(normalized)
    assert cleaned.empty or len(cleaned) == 0


def test_akshare_missing_close_fixture_fails_normalize_or_clean() -> None:
    payload = _load_json(FAILURE_DIR / "akshare_em_daily_missing_close.json")
    raw = _frame_from_table(payload)
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)
    with pytest.raises((KeyError, DataFetchError, ValueError)):
        cleaned = fetcher._clean_data(fetcher._normalize_data(raw, "600519"))
        # If clean "succeeds" without close, that is itself a contract breach.
        if "close" not in cleaned.columns:
            raise KeyError("close")
        if cleaned.empty:
            raise DataFetchError("missing close produced empty frame")


def test_tencent_empty_and_malformed_kline_yield_no_rows() -> None:
    empty_payload = _load_json(FAILURE_DIR / "tencent_daily_kline_empty.json")["payload"]
    malformed = _load_json(FAILURE_DIR / "tencent_daily_kline_malformed.json")["payload"]
    assert _extract_kline_rows(empty_payload, symbol="sz000001") == []
    assert _extract_kline_rows(malformed, symbol="sz000001") == []


def test_tencent_empty_http_payload_returns_empty_not_fake_bars() -> None:
    """Full get_daily_data path with empty recorded HTTP body stays empty."""
    fixture = _load_json(FAILURE_DIR / "tencent_daily_kline_empty.json")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return fixture["payload"]

    with patch("data_provider.tencent_fetcher.requests.get", return_value=FakeResponse()):
        df = TencentFetcher().get_daily_data(
            "000001",
            start_date="2026-05-01",
            end_date="2026-05-10",
        )

    assert df is not None
    assert df.empty


def test_tushare_empty_items_fixture_is_empty_dataframe() -> None:
    body = _load_json(FAILURE_DIR / "tushare_daily_pro_empty_items.json")["response"]
    client = _TushareHttpClient(token="fixture-token-not-real", timeout=5)
    response = MagicMock(status_code=200, text=json.dumps(body))
    with patch("data_provider.tushare_fetcher.safe_post", return_value=response):
        raw = client.query("daily", ts_code="600519.SH")
    assert isinstance(raw, pd.DataFrame)
    assert raw.empty


def test_tushare_rate_limit_body_becomes_rate_limit_error() -> None:
    """Quota wording in Tushare error path must surface as RateLimitError."""
    body = _load_json(FAILURE_DIR / "tushare_daily_pro_rate_limit.json")["response"]
    client = _TushareHttpClient(token="fixture-token-not-real", timeout=5)
    response = MagicMock(status_code=200, text=json.dumps(body))

    with patch(
        "data_provider.tushare_fetcher.get_config",
        return_value=SimpleNamespace(tushare_token="fixture-token-not-real"),
    ):
        fetcher = TushareFetcher()
    fetcher._api = client

    with patch("data_provider.tushare_fetcher.safe_post", return_value=response):
        with pytest.raises(RateLimitError):
            fetcher._fetch_raw_data("600519", "2026-05-06", "2026-05-08")


def test_yfinance_missing_volume_fixture_fails_normalize() -> None:
    payload = _load_json(FAILURE_DIR / "yfinance_daily_missing_volume.json")
    raw = pd.DataFrame(payload["rows"])
    raw = raw.set_index(pd.to_datetime(raw["Date"])).drop(columns=["Date"])
    fetcher = YfinanceFetcher()
    with pytest.raises((KeyError, DataFetchError, ValueError)):
        cleaned = fetcher._clean_data(fetcher._normalize_data(raw, "AAPL"))
        if "volume" not in cleaned.columns:
            raise KeyError("volume")


def test_manager_falls_back_when_primary_normalize_raises() -> None:
    """Missing-field KeyError from a provider must not abort the manager."""
    primary = _SequencedProvider("EfinanceFetcher", 0, [KeyError("close")])
    backup = _SequencedProvider("AkshareFetcher", 1, [_ok_daily_frame(12.5)])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        frame, source = manager.get_daily_data("600519")

    assert source == "AkshareFetcher"
    assert float(frame.iloc[0]["close"]) == pytest.approx(12.5)


# ---------------------------------------------------------------------------
# Timeout / retry bounds
# ---------------------------------------------------------------------------


def test_provider_retry_default_attempts_is_finite_and_honored() -> None:
    """Shared retry policy must stop after DEFAULT_ATTEMPTS (no infinite loop)."""
    assert DEFAULT_ATTEMPTS >= 1
    assert DEFAULT_ATTEMPTS <= 10

    calls = {"n": 0}

    @provider_retry(
        attempts=DEFAULT_ATTEMPTS,
        min_wait=0,
        max_wait=0,
        multiplier=0,
    )
    def always_timeout() -> str:
        calls["n"] += 1
        raise TimeoutError("still hanging")

    with patch("tenacity.nap.sleep", return_value=None):
        with pytest.raises(TimeoutError, match="still hanging"):
            always_timeout()

    assert calls["n"] == DEFAULT_ATTEMPTS


def test_manager_does_not_reinvoke_failed_provider_within_single_request() -> None:
    """Within one get_daily_data call each provider is attempted once."""
    primary = _SequencedProvider(
        "EfinanceFetcher",
        0,
        [TimeoutError("once is enough")],
    )
    backup = _SequencedProvider("TencentFetcher", 1, [_ok_daily_frame()])
    manager = DataFetcherManager(fetchers=[primary, backup])

    with patch.object(DataFetcherManager, "_daily_source_health", _fresh_breaker()):
        _, source = manager.get_daily_data("600519")

    assert source == "TencentFetcher"
    assert primary.calls == 1
    assert backup.calls == 1
