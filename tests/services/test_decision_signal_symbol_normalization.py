"""Market-hint precedence for DecisionSignal stock identities."""

from unittest.mock import patch

import pytest

from src.services.decision_signal_service import DecisionSignalService


def test_explicit_jp_market_hint_is_not_rewritten_as_hk() -> None:
    with patch("src.data.stock_index_loader.resolve_index_stock_code", return_value=None):
        assert (
            DecisionSignalService.normalize_stock_code_for_signal(
                "7203",
                market="jp",
            )
            == "7203.T"
        )


def test_same_bare_code_uses_hk_identity_with_hk_hint() -> None:
    with patch("src.data.stock_index_loader.resolve_index_stock_code", return_value=None):
        assert (
            DecisionSignalService.normalize_stock_code_for_signal(
                "7203",
                market="hk",
            )
            == "HK07203"
        )


def test_four_digit_code_is_rejected_with_cn_hint() -> None:
    with patch("src.data.stock_index_loader.resolve_index_stock_code", return_value=None):
        with pytest.raises(ValueError, match="invalid for market=cn"):
            DecisionSignalService.normalize_stock_code_for_signal(
                "7203",
                market="cn",
            )
