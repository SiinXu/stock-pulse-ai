# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Offline pure-parser tests for AkShare capability-domain extracts (Issue #1068)."""

from __future__ import annotations

import importlib

import pytest

from data_provider.akshare_fetcher import (
    AkshareFetcher,
    _build_realtime_failure_message,
    _classify_realtime_http_error,
    _is_etf_code,
    _is_hk_code,
    _is_us_code,
    _normalize_tencent_volume,
    _parse_tencent_amount,
    _to_sina_tx_symbol,
    is_hk_stock_code,
)
from data_provider.akshare_parts import parse_tencent, realtime_errors, symbols


def test_symbol_helpers_match_facade_and_parts_identity() -> None:
    assert symbols._is_etf_code is _is_etf_code
    assert symbols._is_hk_code is _is_hk_code
    assert symbols.is_hk_stock_code is is_hk_stock_code
    assert symbols._is_us_code is _is_us_code
    assert symbols._to_sina_tx_symbol is _to_sina_tx_symbol


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("510300", True),
        ("159915", True),
        ("600519", False),
        ("00700", False),
    ],
)
def test_is_etf_code_offline(code: str, expected: bool) -> None:
    assert _is_etf_code(code) is expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("00700", True),
        ("hk00700", True),
        ("700.HK", True),
        ("600519", False),
        ("AAPL", False),
    ],
)
def test_is_hk_code_offline(code: str, expected: bool) -> None:
    assert _is_hk_code(code) is expected
    assert is_hk_stock_code(code) is expected


def test_to_sina_tx_symbol_routes_bse_sh_sz() -> None:
    assert _to_sina_tx_symbol("600519") == "sh600519"
    assert _to_sina_tx_symbol("000001") == "sz000001"
    assert _to_sina_tx_symbol("920000").startswith("bj")


def test_tencent_volume_parser_prefers_share_unit_when_cross_check_matches() -> None:
    # fields[6]=volume raw shares; fields[3]=price; [38]=turnover%; [44]=circ mv (yi)
    fields = [""] * 45
    fields[3] = "10"
    fields[6] = "1000000"
    fields[38] = "1"
    fields[44] = "10"  # 10 yi = 1e9; expected volume = (1e9/10)*(1/100)=1e6
    assert _normalize_tencent_volume(fields) == 1_000_000
    assert parse_tencent._normalize_tencent_volume is _normalize_tencent_volume


def test_tencent_volume_parser_falls_back_to_hand_unit() -> None:
    fields = [""] * 10
    fields[6] = "123"
    assert _normalize_tencent_volume(fields) == 12300


def test_tencent_amount_parser_prefers_precise_triplet() -> None:
    fields = [""] * 40
    fields[35] = "10.5/100/123456.7"
    fields[37] = "1"  # wan fallback should be ignored when precise exists
    assert _parse_tencent_amount(fields) == pytest.approx(123456.7)


def test_tencent_amount_parser_falls_back_to_wan_field() -> None:
    fields = [""] * 40
    fields[37] = "2.5"
    assert _parse_tencent_amount(fields) == pytest.approx(25000.0)


def test_realtime_error_classifier_categories() -> None:
    import requests

    cat, _ = _classify_realtime_http_error(TimeoutError("timed out"))
    assert cat == "timeout"
    cat, _ = _classify_realtime_http_error(requests.exceptions.ConnectionError("RemoteDisconnected"))
    assert cat == "remote_disconnect"
    msg = _build_realtime_failure_message(
        "Sina", "hq.sinajs.cn/list", "600519", "sh600519", "timeout", "x", 1.5, "TimeoutError"
    )
    assert "Sina" in msg and "600519" in msg and "timeout" in msg
    assert realtime_errors._classify_realtime_http_error is _classify_realtime_http_error


def test_facade_exposes_capability_domain_methods() -> None:
    required = (
        "_fetch_raw_data",
        "_normalize_data",
        "get_realtime_quote",
        "_get_stock_realtime_quote_em",
        "_get_hk_realtime_quote",
        "get_money_flow",
        "get_chip_distribution",
        "get_market_stats",
        "get_limit_up_pool",
        "_normalize_limit_time_value",
    )
    for name in required:
        assert callable(getattr(AkshareFetcher, name)), name
    assert AkshareFetcher._normalize_limit_time_value.__module__ == "src.data_provider.akshare_fetcher"
    assert AkshareFetcher._fetch_raw_data.__module__ == "src.data_provider.akshare_fetcher"
    assert not AkshareFetcher.__abstractmethods__


def test_facade_module_line_count_is_materially_smaller() -> None:
    from pathlib import Path

    facade = Path(__file__).resolve().parents[2] / "src" / "data_provider" / "akshare_fetcher.py"
    lines = len(facade.read_text(encoding="utf-8").splitlines())
    assert lines < 800, lines


def test_importlib_reload_keeps_public_surface() -> None:
    import data_provider.akshare_fetcher as mod

    reloaded = importlib.reload(mod)
    assert reloaded.AkshareFetcher is not None
    assert callable(reloaded.AkshareFetcher.get_realtime_quote)
    assert callable(reloaded._akshare_call_with_timeout)
    f = reloaded.AkshareFetcher(sleep_min=0.01, sleep_max=0.01)
    assert f.name == "AkshareFetcher"
