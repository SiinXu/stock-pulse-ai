# -*- coding: utf-8 -*-
"""
Shared stock code utilities.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from data_provider.base import canonical_stock_code, is_bse_code, normalize_stock_code
from data_provider.us_index_mapping import is_us_index_code
from src.market.context import detect_market
from src.services.market_symbol_utils import (
    get_suffix_market,
    normalize_suffix_market_symbol,
    suffix_base_lookup_allowed,
)
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)


# Known exchange prefixes (case-insensitive) and the digit lengths they accept.
# e.g. SH600519 -> 600519, HK00700 -> 00700
_PREFIX_DIGIT_LENS: dict = {
    "SH": (6,),
    "SZ": (6,),
    "SS": (6,),
    "BJ": (6,),
    "HK": (1, 2, 3, 4, 5),
}

_SUFFIX_DIGIT_LENS: dict = {
    ".SH": (6,),
    ".SZ": (6,),
    ".SS": (6,),
    ".BJ": (6,),
    ".HK": (1, 2, 3, 4, 5),
    ".T": (4, 5),
    ".KS": (6,),
    ".KQ": (6,),
    # Taiwan: TWSE `.TW` and TPEx `.TWO`; base is 4-6 digits (ETFs up to 6).
    # `.TWO` listed before `.TW` as a defensive ordering convention.
    ".TWO": (4, 5, 6),
    ".TW": (4, 5, 6),
}

_PRESERVE_SUFFIXES = {".T", ".KS", ".KQ", ".TW", ".TWO"}


@dataclass(frozen=True)
class DailyStockIdentity:
    """One parsed identity shared by daily-bar lookup, calendar, and refill."""

    normalized_code: str
    market: str
    refill_code: str
    code_candidates: tuple[str, ...]


def _infer_cn_exchange(base: str) -> str:
    """Infer CN exchange from a 6-digit A/B-share code."""
    if not (base.isdigit() and len(base) == 6):
        return ""

    if is_bse_code(base):
        return "BJ"
    if base.startswith(("5", "6", "9")):
        return "SH"
    return "SZ"


def _valid_exchange_code(exchange: str, base: str, digit_lens: tuple[int, ...]) -> bool:
    if not (base.isdigit() and len(base) in digit_lens):
        return False
    if exchange in {"SH", "SS"}:
        return _infer_cn_exchange(base) == "SH"
    if exchange == "SZ":
        return _infer_cn_exchange(base) == "SZ"
    if exchange == "BJ":
        return _infer_cn_exchange(base) == "BJ"
    return True


def _strip_exchange_prefix(text: str) -> Optional[str]:
    """Strip leading exchange prefix (SH/SZ/HK etc.) and return the bare digits, or None."""
    for prefix, digit_lens in _PREFIX_DIGIT_LENS.items():
        dotted_prefix = f"{prefix}."
        if text.startswith(dotted_prefix):
            base = text[len(dotted_prefix):]
            if _valid_exchange_code(prefix, base, digit_lens):
                return base.zfill(5) if prefix == "HK" else base
        if text.startswith(prefix):
            base = text[len(prefix):]
            if _valid_exchange_code(prefix, base, digit_lens):
                return base.zfill(5) if prefix == "HK" else base
    return None


def _strip_exchange_suffix(text: str) -> Optional[str]:
    """Strip exchange suffix (.SH/.SZ/.SS/.HK) and return normalized bare digits, or None."""
    for suffix, digit_lens in _SUFFIX_DIGIT_LENS.items():
        if text.endswith(suffix):
            base = text[: -len(suffix)].strip()
            exchange = suffix.lstrip(".")
            if _valid_exchange_code(exchange, base, digit_lens):
                return base.zfill(5) if suffix == ".HK" else base
    return None


def is_code_like(value: str) -> bool:
    """Check if string looks like a supported stock-code input."""
    text = value.strip().upper()
    if not text:
        return False
    from data_provider.symbol_normalization import normalize_crypto_symbol
    if normalize_crypto_symbol(value) is not None:
        return True
    if text.isdigit() and len(text) in (4, 5, 6):
        return True
    if _strip_exchange_suffix(text) is not None:
        return True
    if re.match(r"^[A-Z]{1,5}(?:\.(?:US|[A-Z]))?$", text):
        return True
    # Support exchange-prefixed codes: SH600519, SZ000001, BJ920493, HK00700
    if _strip_exchange_prefix(text) is not None:
        return True
    return False


def normalize_code(raw: str) -> Optional[str]:
    """Normalize and validate a single stock code.

    Supports:
    - Plain digit codes: 600519, 00700, 0941 (bare HK)
    - Suffix format: 600519.SH, 600519.SZ, 920493.BJ, 00700.HK
    - Prefix format: SH600519, SH.600519, SZ000001, BJ920493, HK00700 (case-insensitive)
    - US ticker symbols: AAPL, TSLA
    """
    from data_provider.symbol_normalization import normalize_crypto_symbol

    crypto_symbol = normalize_crypto_symbol(raw)
    if crypto_symbol is not None:
        return crypto_symbol
    text = raw.strip().upper()
    if not text:
        return None
    if text.isdigit() and len(text) in (4, 5, 6):
        return text.zfill(5) if len(text) == 4 else text
    suffix_symbol = normalize_suffix_market_symbol(text)
    if suffix_symbol is not None:
        return suffix_symbol
    if any(text.endswith(suffix) for suffix in _PRESERVE_SUFFIXES):
        return None
    if re.match(r"^[A-Z]{1,5}(?:\.(?:US|[A-Z]))?$", text):
        return text
    stripped_suffix = _strip_exchange_suffix(text)
    if stripped_suffix is not None:
        return stripped_suffix
    # Support exchange-prefixed codes: SH600519 -> 600519, BJ920493 -> 920493
    stripped = _strip_exchange_prefix(text)
    if stripped is not None:
        return stripped
    return None


def _explicit_exchange(text: str) -> str:
    """Return a recognized explicit exchange without re-normalizing the code."""
    for suffix in _SUFFIX_DIGIT_LENS:
        if text.endswith(suffix):
            return suffix.lstrip(".")
    for prefix in _PREFIX_DIGIT_LENS:
        for marker in (f"{prefix}.", prefix):
            if text.startswith(marker) and text[len(marker):].isdigit():
                return prefix
    return ""


def _build_hk_market_variants(hk_digits: str) -> List[str]:
    """Build normalized HK variants for padded and legacy code shapes."""
    if not hk_digits.isdigit() or not hk_digits:
        return []

    padded = hk_digits.zfill(5)
    unpadded = padded.lstrip("0") or "0"
    variants = [
        f"HK{padded}",
        f"{padded}.HK",
        padded,
        f"HK{unpadded}",
        f"{unpadded}.HK",
        f"HK.{padded}",
    ]
    if unpadded == padded:
        variants.pop(3)
        variants.pop(3)
    if len(unpadded) <= 4 and unpadded != padded:
        variants.extend([unpadded, f"HK.{unpadded}"])
    return variants


def _build_market_code_variants(
    raw_code: str,
    normalized_code: str,
    explicit_exchange: str,
) -> List[str]:
    """Return additional market-formatted variants for stored-code matching."""
    variants: List[str] = []
    raw_code_upper = raw_code.upper()
    normalized_upper = normalized_code.upper()

    def _add_us_variants(code: str) -> None:
        if code.endswith(".US"):
            bare = code[:-3]
            if bare.isalpha() and 1 <= len(bare) <= 5:
                variants.append(bare)
        elif "." not in code and code.isalpha() and 1 <= len(code) <= 5:
            variants.append(f"{code}.US")

    _add_us_variants(raw_code_upper)
    if normalized_upper != raw_code_upper:
        _add_us_variants(normalized_upper)

    if normalized_upper.isdigit() and len(normalized_upper) == 6:
        if explicit_exchange in {"SH", "SS"}:
            exchange = "SH"
        elif explicit_exchange == "SZ":
            exchange = "SZ"
        elif explicit_exchange == "BJ" or is_bse_code(normalized_upper):
            exchange = "BJ"
        elif normalized_upper.startswith(("5", "6", "9")):
            exchange = "SH"
        else:
            exchange = "SZ"

        variants.extend(
            [
                f"{exchange}{normalized_upper}",
                f"{normalized_upper}.{exchange}",
                f"{exchange}.{normalized_upper}",
            ]
        )
        if exchange == "SH":
            variants.extend(
                [
                    f"SS{normalized_upper}",
                    f"{normalized_upper}.SS",
                    f"SS.{normalized_upper}",
                ]
            )

    if explicit_exchange == "HK" and normalized_upper.isdigit():
        variants.extend(_build_hk_market_variants(normalized_upper))
    elif raw_code_upper.isdigit() and len(raw_code_upper) in {4, 5}:
        variants.extend(_build_hk_market_variants(raw_code_upper))

    return variants


def _filter_cross_market_numeric_aliases(
    *,
    raw_code: str,
    market: str,
    candidates: List[str],
) -> tuple[str, ...]:
    """Drop derived numeric aliases that resolve to another offshore market."""
    from src.data.stock_index_loader import resolve_index_stock_code

    filtered: List[str] = []
    for candidate in dict.fromkeys(value for value in candidates if value):
        if candidate == raw_code or not candidate.isdigit():
            filtered.append(candidate)
            continue
        indexed_code = resolve_index_stock_code(candidate)
        indexed_market = get_suffix_market(indexed_code or "")
        if indexed_market and indexed_market != market:
            continue
        filtered.append(candidate)
    return tuple(filtered)


def resolve_daily_stock_identity(
    code: Optional[str],
    *,
    market_hint: Optional[str] = None,
) -> Optional[DailyStockIdentity]:
    """Resolve one market-aware identity for local bars and legacy aliases."""
    raw_code = str(code or "").strip().upper()
    if not raw_code:
        return None

    identity_code = raw_code
    trusted_market = str(market_hint or "").strip().lower()
    if raw_code.isdigit() and len(raw_code) in {4, 5, 6}:
        from src.data.stock_index_loader import resolve_index_stock_code

        indexed_code = resolve_index_stock_code(raw_code)
        indexed_market = get_suffix_market(indexed_code or "")
        if trusted_market in {"jp", "kr"}:
            if indexed_code and indexed_market == trusted_market:
                identity_code = indexed_code
            elif indexed_code:
                return None
            elif trusted_market == "jp" and len(raw_code) in {4, 5}:
                identity_code = f"{raw_code}.T"
            elif trusted_market == "kr" and len(raw_code) == 6:
                return DailyStockIdentity(
                    normalized_code=raw_code,
                    market="kr",
                    refill_code="",
                    code_candidates=(raw_code,),
                )
            else:
                return None
        elif trusted_market == "cn" and len(raw_code) != 6:
            return None
        elif trusted_market == "hk" and len(raw_code) not in {4, 5}:
            return None
        elif trusted_market and trusted_market not in {"cn", "hk"}:
            return None
        elif not trusted_market and len(raw_code) == 4 and indexed_market == "jp":
            identity_code = indexed_code or raw_code

    explicit_exchange = _explicit_exchange(identity_code)
    if is_us_index_code(identity_code):
        normalized_code = identity_code
    elif identity_code.isdigit() and len(identity_code) == 4:
        normalized_code = identity_code.zfill(5)
        explicit_exchange = "HK"
    else:
        normalized_code = normalize_code(identity_code)
    if normalized_code is None:
        return None

    suffix_market = get_suffix_market(normalized_code)
    if explicit_exchange in {"SH", "SS", "SZ", "BJ"}:
        market = "cn"
    elif explicit_exchange == "HK":
        market = "hk"
    elif suffix_market:
        market = suffix_market
    elif is_us_index_code(normalized_code):
        market = "us"
    elif re.fullmatch(r"[A-Z]{1,5}(?:\.(?:US|[A-Z]))?", normalized_code):
        market = "us"
    elif normalized_code.isdigit() and len(normalized_code) == 6:
        market = "cn"
    elif normalized_code.isdigit() and len(normalized_code) == 5:
        market = "hk"
    else:
        return None

    if market == "hk":
        normalized_code = normalized_code.zfill(5)
        refill_code = f"HK{normalized_code}"
        candidates = [raw_code, *_build_hk_market_variants(normalized_code)]
    else:
        if market == "us":
            normalized_code = normalized_code.removesuffix(".US")
        refill_code = normalized_code
        candidates = [raw_code, normalized_code, refill_code]
        if suffix_base_lookup_allowed(normalized_code):
            candidates.append(normalized_code.rsplit(".", 1)[0])
        if market not in {"jp", "kr", "tw"}:
            for candidate in list(candidates):
                candidates.extend(
                    _build_market_code_variants(
                        raw_code,
                        candidate,
                        explicit_exchange,
                    )
                )

    unique_candidates = _filter_cross_market_numeric_aliases(
        raw_code=raw_code,
        market=market,
        candidates=candidates,
    )
    return DailyStockIdentity(
        normalized_code=normalized_code,
        market=market,
        refill_code=refill_code,
        code_candidates=unique_candidates,
    )


def build_daily_code_candidates(code: Optional[str]) -> List[str]:
    """Build ordered stored-code variants from one market-aware identity."""
    identity = resolve_daily_stock_identity(code)
    return list(identity.code_candidates) if identity is not None else []


def canonicalize_analysis_stock_code(raw: str) -> Optional[str]:
    """Return the canonical downstream identity for one recognized symbol.

    This combines the repository's public format normalizer, index-backed
    JP/KR resolution, and provider-facing canonicalization. Five-digit Hong
    Kong symbols are made explicit before index resolution so they cannot be
    confused with another market.
    """
    text = (raw or "").strip()
    if not text:
        return None

    from data_provider.symbol_normalization import normalize_crypto_symbol

    crypto_symbol = normalize_crypto_symbol(text)
    if crypto_symbol is not None:
        return crypto_symbol

    # A four-digit base is ambiguous with index-backed Japanese listings.
    # Resolve the index first; only an unresolved value takes the documented
    # bare-HK default through normalize_code().
    resolved_input = (
        resolve_index_stock_code_for_analysis(text)
        if text.isdigit() and len(text) == 4
        else text
    )
    normalized = normalize_code(resolved_input)
    if normalized is None:
        return None

    # Downstream provider routing treats bare letter tickers as US symbols.
    # The public ``.US`` alias is accepted at the boundary but must not leak
    # through as a provider-facing identity, where it is otherwise classified
    # as an A-share code.
    if normalized.endswith(".US"):
        normalized = normalized[:-3]

    analysis_input = (
        f"HK{normalized}"
        if detect_market(normalized) == "hk"
        else normalized
    )
    try:
        resolved = resolve_index_stock_code_for_analysis(analysis_input)
    except Exception as exc:  # broad-exception: fallback_recorded - Index failures retain canonical A/HK/US chat routing.
        log_safe_exception(
            logger,
            "Stock symbol index resolution failed; using format-only fallback",
            exc,
            error_code="stock_symbol_index_resolution_failed",
            context={"market": detect_market(normalized)},
        )
        resolved = analysis_input
    canonical = canonical_stock_code(normalize_stock_code(resolved))
    return canonical or None


def resolve_index_stock_code_for_analysis(raw: str) -> str:
    """Resolve bare JP/KR candidates with an HK fallback for four digits.

    For code-like inputs and ambiguous 4-digit bare bases:
    - Existing index-backed entries (e.g. ``005930`` -> ``005930.KS``) are
      preferred.
    - An unresolved 4-digit base is interpreted as Hong Kong and rewritten to
      an explicit five-digit ``HK`` identity (e.g. ``0941`` -> ``HK00941``).
    - Other non-matching code-like inputs keep the canonicalized input.

    Existing explicit forms keep their caller-visible shape. This is important
    for task/API compatibility; callers that require a provider-facing identity
    use :func:`canonicalize_analysis_stock_code` after this resolution step.
    Non-code-like values are canonicalized only so callers retain their own
    validation or name-resolution policy.
    """
    text = (raw or "").strip()
    if not text:
        return ""

    if is_code_like(text):
        from src.data.stock_index_loader import resolve_index_stock_code

        resolved = resolve_index_stock_code(text)
        if resolved:
            return canonical_stock_code(resolved)

        if text.isdigit() and len(text) == 4:
            return f"HK{text.zfill(5)}"

    return canonical_stock_code(text)
