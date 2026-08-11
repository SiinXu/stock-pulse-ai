# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Canonical identity helpers shared by flat and grouped watchlists."""

from __future__ import annotations

import re

from data_provider.base import normalize_stock_code


def watchlist_match_key(code: str) -> str:
    """Return the market-aware identity used by every watchlist owner."""
    normalized = normalize_stock_code(str(code or "").strip())
    if re.fullmatch(r"\d{5}", normalized):
        return f"HK{normalized}"
    return normalized.upper()


def canonicalize_watchlist_codes(codes: list[str]) -> list[str]:
    """Canonicalize and de-duplicate codes while preserving first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        key = watchlist_match_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result
