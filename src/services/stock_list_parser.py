# -*- coding: utf-8 -*-
"""Helpers for parsing the user-facing STOCK_LIST value."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

_STOCK_LIST_SEPARATOR_RE = re.compile(r"[\s,;\uFF0C\u3001\uFF1B]+")
SUPPORTED_PORTFOLIO_SOURCES = ("futu",)


def split_stock_list(value: str) -> List[str]:
    """Split STOCK_LIST values on common copy/paste separators."""
    return [
        item.strip()
        for item in _STOCK_LIST_SEPARATOR_RE.split(value or "")
        if item.strip()
    ]


def serialize_stock_list(value: str) -> str:
    """Return STOCK_LIST in the canonical comma-separated storage form."""
    return ",".join(split_stock_list(value))


def normalize_stock_codes(
    values: Iterable[str],
    *,
    reject_invalid: bool = False,
) -> List[str]:
    """Normalize an ordered stock list with the shared analysis canonicalizer."""
    from src.services.stock_code_utils import canonicalize_analysis_stock_code

    normalized: List[str] = []
    seen = set()
    for value in values:
        code = canonicalize_analysis_stock_code(value) if isinstance(value, str) else None
        if not code:
            if reject_invalid:
                raise ValueError(f"Unsupported stock code: {value!r}")
            continue
        if code not in seen:
            seen.add(code)
            normalized.append(code)
    return normalized


def resolve_portfolio_stock_list(source: Optional[str]) -> Optional[List[str]]:
    """Resolve an explicitly selected live portfolio, preserving None versus []."""
    if source is None or (isinstance(source, str) and not source.strip()):
        return None
    if not isinstance(source, str):
        raise ValueError(f"Unsupported portfolio source: {source!r}")
    normalized_source = source.strip().lower()
    if normalized_source not in SUPPORTED_PORTFOLIO_SOURCES:
        raise ValueError(f"Unsupported portfolio source: {source}")

    from src.brokers.futu.portfolio import load_futu_stock_codes

    return normalize_stock_codes(load_futu_stock_codes(), reject_invalid=True)
