# -*- coding: utf-8 -*-
"""Regression: bare 4-digit Hong Kong codes normalize to HKxxxxx.

Examples: ``0001`` (CK Hutchison), ``0941`` (China Mobile), ``1810``.
A-share codes are 6 digits, so the bare-4-digit namespace does not collide
with CN listings. JP/KR/TW require an explicit Yahoo suffix at this layer.
"""

from data_provider.symbol_normalization import (
    _is_hk_market,
    canonical_stock_code,
    normalize_stock_code,
)


def test_bare_four_digit_hk_codes_normalize_to_canonical_prefix() -> None:
    assert normalize_stock_code("0001") == "HK00001"
    assert normalize_stock_code("0941") == "HK00941"
    assert normalize_stock_code("1810") == "HK01810"


def test_context_free_canonical_helper_does_not_infer_a_market() -> None:
    assert canonical_stock_code("0001") == "0001"
    assert canonical_stock_code("0941") == "0941"
    assert canonical_stock_code("7203") == "7203"


def test_bare_five_digit_hk_and_a_share_and_us_unchanged_at_normalize() -> None:
    # 5-digit bare HK remains the historical bare form here; analysis may
    # still promote it. 6-digit A-share and US tickers must not rewrite.
    assert normalize_stock_code("00700") == "00700"
    assert normalize_stock_code("600519") == "600519"
    assert normalize_stock_code("000001") == "000001"
    assert normalize_stock_code("AAPL") == "AAPL"
    assert canonical_stock_code("00700") == "00700"
    assert canonical_stock_code("600519") == "600519"
    assert canonical_stock_code("AAPL") == "AAPL"


def test_prefixed_and_suffixed_hk_still_pad_to_five_digits() -> None:
    assert normalize_stock_code("hk0001") == "HK00001"
    assert normalize_stock_code("HK1810") == "HK01810"
    assert normalize_stock_code("0001.HK") == "HK00001"
    assert normalize_stock_code("1810.HK") == "HK01810"


def test_mixed_list_normalization_preserves_non_hk_and_promotes_bare_four() -> None:
    codes = ["0001", "00700", "600519", "AAPL", "0941"]
    assert [normalize_stock_code(c) for c in codes] == [
        "HK00001",
        "00700",
        "600519",
        "AAPL",
        "HK00941",
    ]


def test_bare_four_digit_is_hk_market() -> None:
    for code in ("0001", "0941", "1810", "HK00001"):
        assert _is_hk_market(code) is True
    assert _is_hk_market("600519") is False
    assert _is_hk_market("AAPL") is False
