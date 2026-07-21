# -*- coding: utf-8 -*-
"""Bot-facing stock symbol validation and market policy."""

from __future__ import annotations

from dataclasses import dataclass

from data_provider.base import canonical_stock_code, normalize_stock_code
from src.market_context import detect_market
from src.services.stock_code_utils import (
    normalize_code,
    resolve_index_stock_code_for_analysis,
)


_SUPPORTED_MARKET_NAMES = {
    "cn": "A 股 (CN) / A-share",
    "hk": "港股 (HK) / Hong Kong",
    "us": "美股 (US) / US stock",
}

_OTHER_MARKET_NAMES = {
    "jp": ("日股", "Japan stocks"),
    "kr": ("韩股", "Korea stocks"),
    "tw": ("台股", "Taiwan stocks"),
}

_SUPPORTED_FORMATS_MESSAGE = (
    "支持格式 / Supported formats: "
    "A 股/A-share `600519`; "
    "港股/Hong Kong `HK00700` or `00700.HK`; "
    "美股/US `AAPL`."
)


class BotStockSymbolError(ValueError):
    """Public validation error for a Bot stock symbol."""


@dataclass(frozen=True)
class BotStockSymbol:
    """A canonical Bot stock symbol and its supported market."""

    code: str
    market: str

    @property
    def market_display_name(self) -> str:
        return _SUPPORTED_MARKET_NAMES[self.market]


def supported_stock_formats_message() -> str:
    """Return actionable bilingual guidance for supported Bot symbols."""

    return _SUPPORTED_FORMATS_MESSAGE


def is_recognized_stock_symbol(value: str) -> bool:
    """Return whether the shared symbol normalizer recognizes a token."""

    token = (value or "").strip().strip(",，")
    return normalize_code(token) is not None


def parse_bot_stock_symbol(value: str) -> BotStockSymbol:
    """Validate and canonicalize an A-share, Hong Kong, or US symbol.

    Formatting and market detection stay authoritative in the shared helpers.
    This module only applies the Bot capability boundary and public guidance.
    """

    raw = (value or "").strip()
    normalized = normalize_code(raw)
    if normalized is None:
        display = raw.upper() or "(empty)"
        raise BotStockSymbolError(
            f"无法识别股票代码 / Unrecognized stock symbol: `{display}`.\n"
            f"{_SUPPORTED_FORMATS_MESSAGE}"
        )

    # Five-digit HK inputs are valid but the shared queue/provider identity uses
    # the explicit HK prefix. Other markets retain their normal shared resolver.
    input_market = detect_market(normalized)
    analysis_input = f"HK{normalized}" if input_market == "hk" else raw
    resolved = resolve_index_stock_code_for_analysis(analysis_input)
    code = canonical_stock_code(normalize_stock_code(resolved))
    if not code:
        raise BotStockSymbolError(
            f"无法识别股票代码 / Unrecognized stock symbol: `{raw.upper()}`.\n"
            f"{_SUPPORTED_FORMATS_MESSAGE}"
        )

    market = detect_market(code)
    if market not in _SUPPORTED_MARKET_NAMES:
        zh_name, en_name = _OTHER_MARKET_NAMES.get(
            market,
            ("该市场", "this market"),
        )
        raise BotStockSymbolError(
            f"Bot 分析暂不支持{zh_name}代码 `{raw.upper()}` / "
            f"Bot analysis does not currently support {en_name}: `{raw.upper()}`.\n"
            f"{_SUPPORTED_FORMATS_MESSAGE}"
        )

    return BotStockSymbol(code=code, market=market)
