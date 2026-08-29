# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline characterization tests for Tushare capability-domain extracts (Issue #1068)."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.data_provider.base import DataFetchError
from src.data_provider.tushare_fetcher import (
    TushareFetcher,
    _ETF_ALL_PREFIXES,
    _ETF_SH_PREFIXES,
    _ETF_SZ_PREFIXES,
    _EXPECTED_CLIENT_METHOD_NAMES,
    _EXPECTED_HISTORY_METHOD_NAMES,
    _EXPECTED_SYMBOL_METHOD_NAMES,
    _TUSHARE_DEFAULT_API_URL,
    _TushareHttpClient,
    _is_etf_code,
    _is_us_code,
    _resolve_tushare_api_url,
)
from src.data_provider.tushare_parts import client, symbols


def test_symbol_and_client_helpers_match_facade_and_parts_identity() -> None:
    assert symbols._is_etf_code is _is_etf_code
    assert symbols._is_us_code is _is_us_code
    assert symbols._ETF_SH_PREFIXES is _ETF_SH_PREFIXES
    assert symbols._ETF_SZ_PREFIXES is _ETF_SZ_PREFIXES
    assert symbols._ETF_ALL_PREFIXES is _ETF_ALL_PREFIXES
    assert client._resolve_tushare_api_url is _resolve_tushare_api_url
    assert client._TUSHARE_DEFAULT_API_URL == _TUSHARE_DEFAULT_API_URL
    assert client._TushareHttpClient is _TushareHttpClient


def test_tushare_http_client_imported_from_facade_is_owner_class() -> None:
    assert _TushareHttpClient is client._TushareHttpClient


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("510300", True),
        ("159915", True),
        ("600519", False),
        ("AAPL", False),
    ],
)
def test_is_etf_code_offline(code: str, expected: bool) -> None:
    assert _is_etf_code(code) is expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("AAPL", True),
        ("TSLA", True),
        ("BRK.B", True),
        ("600519", False),
        ("00700", False),
    ],
)
def test_is_us_code_offline(code: str, expected: bool) -> None:
    assert _is_us_code(code) is expected


def test_facade_rebound_methods_keep_tushare_fetcher_module() -> None:
    required = (
        *_EXPECTED_CLIENT_METHOD_NAMES,
        *_EXPECTED_SYMBOL_METHOD_NAMES,
        *_EXPECTED_HISTORY_METHOD_NAMES,
    )
    for name in required:
        bound = getattr(TushareFetcher, name)
        assert callable(bound), name
        assert bound.__module__ == "src.data_provider.tushare_fetcher", name
    assert not TushareFetcher.__abstractmethods__


def test_frozen_expected_names_match_bound_inventory() -> None:
    assert _EXPECTED_CLIENT_METHOD_NAMES == (
        "_init_api",
        "_build_api_client",
        "_check_rate_limit",
        "_call_api_with_rate_limit",
    )
    assert _EXPECTED_SYMBOL_METHOD_NAMES == (
        "_detect_exchange_hint",
        "_convert_stock_code",
        "_convert_hk_stock_code_for_tushare",
    )
    assert _EXPECTED_HISTORY_METHOD_NAMES == (
        "_fetch_raw_data",
        "_normalize_data",
    )


def test_convert_stock_code_rejects_us_via_facade_class() -> None:
    with patch.object(TushareFetcher, "_init_api", return_value=None):
        fetcher = TushareFetcher()
    with pytest.raises(DataFetchError, match="不支持美股"):
        fetcher._convert_stock_code("AAPL")


def test_http_client_query_is_intercepted_by_facade_safe_post() -> None:
    response = MagicMock(
        status_code=200,
        text='{"code": 0, "data": {"fields": ["ts_code"], "items": [["600519.SH"]]}}',
    )
    client_obj = _TushareHttpClient(token="demo-token", timeout=15)
    with patch("src.data_provider.tushare_fetcher.safe_post", return_value=response) as post_mock:
        df = client_obj.query("daily", ts_code="600519.SH")
    post_mock.assert_called_once()
    assert post_mock.call_args.args[0] == "http://api.tushare.pro"
    assert isinstance(df, pd.DataFrame)
    assert df.to_dict(orient="records") == [{"ts_code": "600519.SH"}]


def test_fetch_raw_data_has_tenacity_retry_wrapper() -> None:
    fetch = TushareFetcher._fetch_raw_data
    assert callable(fetch)
    assert getattr(fetch, "__wrapped__", None) is not None


def test_importlib_reload_keeps_public_surface() -> None:
    import src.data_provider.tushare_fetcher as mod

    reloaded = importlib.reload(mod)
    assert reloaded.TushareFetcher is not None
    assert callable(reloaded.TushareFetcher._fetch_raw_data)
    assert callable(reloaded.TushareFetcher.get_stock_name)
    assert reloaded._TushareHttpClient is reloaded._client_module._TushareHttpClient
    with patch.object(reloaded.TushareFetcher, "_init_api", return_value=None):
        fetcher = reloaded.TushareFetcher()
    assert fetcher.name == "TushareFetcher"
