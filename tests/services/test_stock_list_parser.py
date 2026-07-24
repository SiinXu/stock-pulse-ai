# -*- coding: utf-8 -*-
"""Tests for STOCK_LIST separator handling."""

from unittest.mock import patch

import pytest

from src.services.stock_list_parser import (
    normalize_stock_codes,
    resolve_portfolio_stock_list,
    serialize_stock_list,
    split_stock_list,
)


def test_split_stock_list_accepts_common_copy_paste_separators() -> None:
    value = "600519，300750  hk00700;AAPL、7203.T\n005930.KS；002594"

    assert split_stock_list(value) == [
        "600519",
        "300750",
        "hk00700",
        "AAPL",
        "7203.T",
        "005930.KS",
        "002594",
    ]


def test_serialize_stock_list_uses_canonical_commas() -> None:
    assert serialize_stock_list("600519，300750\nAAPL") == "600519,300750,AAPL"


def test_normalize_stock_codes_matches_agent_and_analysis_identities() -> None:
    assert normalize_stock_codes(
        ["SH.600519", "HK.00700", "AAPL.US", "aapl", "invalid symbol"]
    ) == ["600519", "HK00700", "AAPL"]


def test_normalize_stock_codes_can_reject_invalid_broker_values() -> None:
    with pytest.raises(ValueError, match="Unsupported stock code"):
        normalize_stock_codes(["US.INVALID-SYMBOL"], reject_invalid=True)


def test_resolve_portfolio_stock_list_preserves_unselected_and_empty_states() -> None:
    assert resolve_portfolio_stock_list(None) is None
    with patch("src.brokers.futu.portfolio.load_futu_stock_codes", return_value=[]):
        assert resolve_portfolio_stock_list("futu") == []


def test_resolve_portfolio_stock_list_normalizes_and_deduplicates_adapter_codes() -> None:
    with patch(
        "src.brokers.futu.portfolio.load_futu_stock_codes",
        return_value=["600519.SH", "HK00700", "AAPL", "aapl"],
    ):
        assert resolve_portfolio_stock_list("FUTU") == ["600519", "HK00700", "AAPL"]


def test_resolve_portfolio_stock_list_rejects_unknown_source() -> None:
    with pytest.raises(ValueError, match="Unsupported portfolio source"):
        resolve_portfolio_stock_list("other")

    with pytest.raises(ValueError, match="Unsupported portfolio source"):
        resolve_portfolio_stock_list(42)  # type: ignore[arg-type]
