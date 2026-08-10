# -*- coding: utf-8 -*-
"""Symbol and market code normalization helpers for data providers.

Extracted from :mod:`data_provider.base` as an ADR-006 behavior-preserving
slice. Callers should continue to import public names from
``data_provider.base`` (compatibility facade) unless a later retirement PR
migrates them.
"""

from __future__ import annotations

from src.services.market_symbol_utils import is_suffix_market_symbol

# Explicit crypto namespace. Bare tickers (BTC, ETH) are never auto-promoted to
# crypto — they continue to follow equity market detection (US letter tickers).
CRYPTO_NAMESPACE_PREFIX = "crypto:"


def is_crypto_symbol(stock_code: str) -> bool:
    """Return True only for explicit ``crypto:`` namespaced symbols."""
    return (stock_code or "").strip().lower().startswith(CRYPTO_NAMESPACE_PREFIX)


def parse_crypto_symbol(stock_code: str) -> str | None:
    """Return the upper-case crypto ticker from ``crypto:TICKER``, else None.

    Empty residual after the prefix is rejected so ``crypto:`` alone is never
    treated as a valid asset id.
    """
    raw = (stock_code or "").strip()
    if not raw.lower().startswith(CRYPTO_NAMESPACE_PREFIX):
        return None
    ticker = raw[len(CRYPTO_NAMESPACE_PREFIX) :].strip().upper()
    if not ticker or any(ch.isspace() for ch in ticker):
        return None
    # Allow letters, digits, hyphen, underscore (e.g. crypto:BTC, crypto:1INCH).
    if not all(ch.isalnum() or ch in "-_" for ch in ticker):
        return None
    return ticker


def normalize_crypto_symbol(stock_code: str) -> str | None:
    """Return canonical ``crypto:TICKER`` form, or None if not namespaced crypto."""
    ticker = parse_crypto_symbol(stock_code)
    if ticker is None:
        return None
    return f"{CRYPTO_NAMESPACE_PREFIX}{ticker}"


def normalize_stock_code(stock_code: str) -> str:
    """
    Normalize stock code by stripping exchange prefixes/suffixes.

    Accepted formats and their normalized results:
    - '600519'      -> '600519'   (already clean)
    - 'SH600519'    -> '600519'   (strip SH prefix)
    - 'SH.600519'   -> '600519'   (strip SH. prefix)
    - 'SZ000001'    -> '000001'   (strip SZ prefix)
    - 'SS600519'    -> '600519'   (strip legacy Yahoo Shanghai prefix)
    - 'SZ.000001'   -> '000001'   (strip SZ. prefix)
    - 'BJ920748'    -> '920748'   (strip BJ prefix, BSE)
    - 'BJ.920748'   -> '920748'   (strip BJ. prefix, BSE)
    - 'sh600519'    -> '600519'   (case-insensitive)
    - '600519.SH'   -> '600519'   (strip .SH suffix)
    - '000001.SZ'   -> '000001'   (strip .SZ suffix)
    - '920748.BJ'   -> '920748'   (strip .BJ suffix, BSE)
    - 'HK00700'     -> 'HK00700'  (keep HK prefix for HK stocks)
    - '1810.HK'     -> 'HK01810'  (normalize HK suffix to canonical prefix form)
    - '7203.T'      -> '7203.T'   (keep Japan Yahoo suffix form)
    - '005930.KS'   -> '005930.KS' (keep Korea Yahoo suffix form)
    - '2330.TW'     -> '2330.TW'  (keep Taiwan TWSE Yahoo suffix form)
    - '6505.TWO'    -> '6505.TWO' (keep Taiwan TPEx Yahoo suffix form)
    - 'AAPL'        -> 'AAPL'     (keep US stock ticker as-is)
    - 'crypto:btc'  -> 'crypto:BTC' (explicit crypto namespace; bare BTC stays equity)

    This function is applied at the DataProviderManager layer so that
    all individual fetchers receive a clean 6-digit code (for A-shares/ETFs).
    """
    code = stock_code.strip()
    upper = code.upper()

    # Crypto namespace must be resolved before equity prefix/suffix rules so a
    # token like crypto:ETH is never stripped or reclassified as a US ticker.
    crypto_normalized = normalize_crypto_symbol(code)
    if crypto_normalized is not None:
        return crypto_normalized

    # Normalize HK prefix to a canonical 5-digit form (e.g. hk1810 -> HK01810)
    if upper.startswith('HK') and not upper.startswith('HK.'):
        candidate = upper[2:]
        if candidate.isdigit() and 1 <= len(candidate) <= 5:
            return f"HK{candidate.zfill(5)}"

    # Strip SH/SZ/SS prefix (e.g. SH600519 -> 600519, SS600519 -> 600519)
    if upper.startswith(('SH', 'SZ', 'SS')) and not upper.startswith(('SH.', 'SZ.', 'SS.')):
        candidate = code[2:]
        # Only strip if the remainder looks like a valid numeric code
        if candidate.isdigit() and len(candidate) in (5, 6):
            return candidate

    # Strip dotted SH/SZ/SS prefix (e.g. SH.600519 -> 600519)
    if upper.startswith(('SH.', 'SZ.', 'SS.')):
        candidate = code[3:]
        if candidate.isdigit() and len(candidate) in (5, 6):
            return candidate

    # Strip BJ prefix (e.g. BJ920748 -> 920748)
    if upper.startswith('BJ') and not upper.startswith('BJ.'):
        candidate = code[2:]
        if candidate.isdigit() and len(candidate) == 6:
            return candidate

    # Strip dotted BJ prefix (e.g. BJ.920748 -> 920748)
    if upper.startswith('BJ.'):
        candidate = code[3:]
        if candidate.isdigit() and len(candidate) == 6:
            return candidate

    # Strip .SH/.SZ/.BJ suffix (e.g. 600519.SH -> 600519, 920748.BJ -> 920748)
    # while preserving explicit Yahoo suffix forms for JP/KR/TW.
    if '.' in code:
        base, suffix = code.rsplit('.', 1)
        if suffix.upper() == 'T' and base.isdigit() and len(base) in (4, 5):
            return f"{base}.{suffix.upper()}"
        if suffix.upper() in ('KS', 'KQ') and base.isdigit() and len(base) == 6:
            return f"{base}.{suffix.upper()}"
        if suffix.upper() in ('TW', 'TWO') and base.isdigit() and 4 <= len(base) <= 6:
            return f"{base}.{suffix.upper()}"
        if suffix.upper() == 'HK' and base.isdigit() and 1 <= len(base) <= 5:
            return f"HK{base.zfill(5)}"
        if base.upper() in ('SH', 'SS', 'SZ', 'BJ') and suffix.isdigit():
            return suffix
        if suffix.upper() in ('SH', 'SZ', 'SS', 'BJ') and base.isdigit():
            return base

    return code


ETF_PREFIXES = ("51", "52", "56", "58", "15", "16", "18")


def _is_us_market(code: str) -> bool:
    """判断是否为美股/美股指数代码（不含中文前后缀）。"""
    from .us_index_mapping import is_us_stock_code, is_us_index_code

    normalized = (code or "").strip().upper()
    return is_us_index_code(normalized) or is_us_stock_code(normalized)


def _is_hk_market(code: str) -> bool:
    """Return whether a symbol follows the Hong Kong market contract.

    Accepted forms are an ``HK`` prefix, a ``.HK`` suffix, or a four- to
    five-digit bare code. Mainland and Beijing listings use six digits, so
    they do not overlap with the bare Hong Kong form.
    """
    normalized = (code or "").strip().upper()
    if normalized.endswith(".HK"):
        base = normalized[:-3]
        return base.isdigit() and 1 <= len(base) <= 5
    if normalized.startswith("HK"):
        digits = normalized[2:]
        return digits.isdigit() and 1 <= len(digits) <= 5
    if normalized.isdigit() and 4 <= len(normalized) <= 5:
        return True
    return False


def _is_jp_market(code: str) -> bool:
    """判定是否为日本 Yahoo Finance suffix 代码（如 7203.T）。"""
    return is_suffix_market_symbol(code, "jp")


def _is_kr_market(code: str) -> bool:
    """判定是否为韩国 Yahoo Finance suffix 代码（如 005930.KS / 035720.KQ）。"""
    return is_suffix_market_symbol(code, "kr")


def _is_tw_market(code: str) -> bool:
    """判定是否为台湾 Yahoo Finance suffix 代码（TWSE 上市 2330.TW / TPEx 上柜 6505.TWO）。

    台股 base 为 4-6 位（普通股 4 位，ETF/其他至 6 位，如 00878 / 006208）。
    仅带 .TW/.TWO 后缀的代码才识别为台股，裸 6 位代码仍按 A 股语义处理。
    """
    return is_suffix_market_symbol(code, "tw")


def _is_etf_code(code: str) -> bool:
    """判定 A 股 ETF 基金代码（保守规则）。"""
    normalized = normalize_stock_code(code)
    return (
        normalized.isdigit()
        and len(normalized) == 6
        and normalized.startswith(ETF_PREFIXES)
    )


def _market_tag(code: str) -> str:
    """返回市场标签: cn/us/hk/jp/kr/tw/crypto."""
    # Explicit crypto namespace only — bare BTC/ETH remain equity candidates.
    if is_crypto_symbol(code):
        return "crypto"
    if _is_us_market(code):
        return "us"
    if _is_hk_market(code):
        return "hk"
    if _is_jp_market(code):
        return "jp"
    if _is_kr_market(code):
        return "kr"
    if _is_tw_market(code):
        return "tw"
    return "cn"


def is_bse_code(code: str) -> bool:
    """
    Check if the code is a Beijing Stock Exchange (BSE) A-share code.

    BSE rules (2026):
    - New format (2024+): 92xxxx main trading codes
    - Historical ranges: 43xxxx, 83xxxx, 87xxxx, 88xxxx
    - Special instruments: 81xxxx convertible bonds, 82xxxx preferred shares
    - Subscription codes: 889xxx
    Note: 900xxx are Shanghai B-shares and must return False.
    """
    c = (code or "").strip().split(".")[0]
    if len(c) != 6 or not c.isdigit():
        return False

    if c.startswith("900"):
        return False

    return c.startswith(("92", "43", "81", "82", "83", "87", "88"))


def is_st_stock(name: str) -> bool:
    """
    Check if the stock is an ST or *ST stock based on its name.

    ST stocks have special trading rules and typically a ±5% limit.
    """
    n = (name or "").upper()
    return 'ST' in n


def is_kc_cy_stock(code: str) -> bool:
    """
    Check if the stock is a STAR Market (科创板) or ChiNext (创业板) stock based on its code.

    - STAR Market: Codes starting with 688
    - ChiNext: Codes starting with 300
    Both have a ±20% limit.
    """
    c = (code or "").strip().split(".")[0]
    return c.startswith("688") or c.startswith("30")


def canonical_stock_code(code: str) -> str:
    """
    Return the canonical (uppercase) form of a stock code.

    This is a display/storage layer concern, distinct from normalize_stock_code
    which strips exchange prefixes. Apply at system input boundaries to ensure
    consistent case across BOT, WEB UI, API, and CLI paths (Issue #355).

    Examples:
        'aapl'    -> 'AAPL'
        'AAPL'    -> 'AAPL'
        '600519'  -> '600519'  (digits are unchanged)
        'hk00700' -> 'HK00700'
        'crypto:btc' -> 'crypto:BTC'
    """
    crypto_normalized = normalize_crypto_symbol(code)
    if crypto_normalized is not None:
        return crypto_normalized
    return (code or "").strip().upper()


__all__ = [
    "CRYPTO_NAMESPACE_PREFIX",
    "ETF_PREFIXES",
    "canonical_stock_code",
    "is_bse_code",
    "is_crypto_symbol",
    "is_kc_cy_stock",
    "is_st_stock",
    "normalize_crypto_symbol",
    "normalize_stock_code",
    "parse_crypto_symbol",
]
