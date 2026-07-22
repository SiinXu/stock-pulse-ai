# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.market.phase_summary`."""

from src.market._facade import load_legacy_module as _load_legacy_module
from src.market.phase_summary import (
    Any,
    Dict,
    List,
    MARKET_PHASE_SUMMARY_KEY,
    Mapping,
    MarketPhase,
    Optional,
    annotations,
    build_market_phase_context,
    datetime,
    extract_market_phase_summary,
    format_public_market_status_line,
    format_public_phase_pack_excerpt,
    get_market_for_stock,
    json,
    normalize_analysis_phase_bucket,
    rebuild_market_phase_summary_for_stock_code,
    render_market_phase_summary,
)


__all__ = (
    "Any",
    "Dict",
    "List",
    "MARKET_PHASE_SUMMARY_KEY",
    "Mapping",
    "MarketPhase",
    "Optional",
    "annotations",
    "build_market_phase_context",
    "datetime",
    "extract_market_phase_summary",
    "format_public_market_status_line",
    "format_public_phase_pack_excerpt",
    "get_market_for_stock",
    "json",
    "normalize_analysis_phase_bucket",
    "rebuild_market_phase_summary_for_stock_code",
    "render_market_phase_summary",
)

_load_legacy_module("src.market.phase_summary", globals(), __all__)
del _load_legacy_module
