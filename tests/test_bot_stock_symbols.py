# -*- coding: utf-8 -*-
"""Tests for the Bot multi-market stock symbol boundary."""

import pytest

from bot.commands.analyze import AnalyzeCommand
from bot.commands.help import HelpCommand
from bot.stock_symbols import (
    BotStockSymbolError,
    is_recognized_stock_symbol,
    parse_bot_stock_symbol,
)


@pytest.mark.parametrize(
    ("raw", "expected_code", "expected_market"),
    [
        ("600519", "600519", "cn"),
        ("SH600519", "600519", "cn"),
        ("hk00700", "HK00700", "hk"),
        ("HK700", "HK00700", "hk"),
        ("00700", "HK00700", "hk"),
        ("00700.HK", "HK00700", "hk"),
        ("aapl", "AAPL", "us"),
        ("BRK.B", "BRK.B", "us"),
    ],
)
def test_parse_bot_stock_symbol_uses_shared_normalization(
    raw: str,
    expected_code: str,
    expected_market: str,
) -> None:
    symbol = parse_bot_stock_symbol(raw)

    assert symbol.code == expected_code
    assert symbol.market == expected_market


def test_recognized_symbol_token_includes_supported_and_known_unsupported_markets() -> None:
    assert is_recognized_stock_symbol("00700.HK,") is True
    assert is_recognized_stock_symbol("7203.T") is True
    assert is_recognized_stock_symbol("not-a-symbol") is False


def test_unsupported_market_returns_actionable_bilingual_guidance() -> None:
    with pytest.raises(BotStockSymbolError) as exc_info:
        parse_bot_stock_symbol("7203.T")

    message = str(exc_info.value)
    assert "暂不支持日股" in message
    assert "does not currently support Japan stocks" in message
    assert "HK00700" in message
    assert "AAPL" in message


def test_index_resolved_unsupported_market_uses_final_symbol_market() -> None:
    with pytest.raises(BotStockSymbolError) as exc_info:
        parse_bot_stock_symbol("005930")

    message = str(exc_info.value)
    assert "暂不支持韩股" in message
    assert "does not currently support Korea stocks" in message


def test_invalid_symbol_returns_actionable_bilingual_guidance() -> None:
    with pytest.raises(BotStockSymbolError) as exc_info:
        parse_bot_stock_symbol("abc123")

    message = str(exc_info.value)
    assert "无法识别股票代码" in message
    assert "Unrecognized stock symbol" in message
    assert "600519" in message


def test_help_lists_representative_symbols_for_all_supported_markets() -> None:
    text = HelpCommand()._format_help_list([AnalyzeCommand()], "/")

    assert "/analyze 600519 - A 股 / A-share" in text
    assert "/analyze HK00700 - 港股 / Hong Kong" in text
    assert "/analyze AAPL - 美股 / US" in text
