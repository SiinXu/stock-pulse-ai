# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.analysis_context_pack.prompt`."""

from src.analysis_context_pack._facade import load_legacy_module as _load_legacy_module
from src.analysis_context_pack.prompt import (
    Any,
    BLOCK_LABELS_EN,
    BLOCK_LABELS_ZH,
    CONSERVATIVE_MARKET_PHASES,
    CORE_DEGRADED_STATUSES,
    Dict,
    INTRADAY_MARKET_PHASES,
    Iterable,
    KNOWN_MARKET_PHASES,
    List,
    Mapping,
    Optional,
    QUALITY_LEVEL_LABELS_EN,
    QUALITY_LEVEL_LABELS_ZH,
    SENSITIVE_MARKERS,
    STATUS_LABELS_EN,
    STATUS_LABELS_ZH,
    analysis_context_pack_to_dict,
    annotations,
    format_analysis_context_pack_prompt_section,
    get_analysis_context_pack_block_labels,
    iter_analysis_context_pack_block_keys,
    normalize_analysis_context_pack_language,
)


__all__ = (
    "Any",
    "BLOCK_LABELS_EN",
    "BLOCK_LABELS_ZH",
    "CONSERVATIVE_MARKET_PHASES",
    "CORE_DEGRADED_STATUSES",
    "Dict",
    "INTRADAY_MARKET_PHASES",
    "Iterable",
    "KNOWN_MARKET_PHASES",
    "List",
    "Mapping",
    "Optional",
    "QUALITY_LEVEL_LABELS_EN",
    "QUALITY_LEVEL_LABELS_ZH",
    "SENSITIVE_MARKERS",
    "STATUS_LABELS_EN",
    "STATUS_LABELS_ZH",
    "analysis_context_pack_to_dict",
    "annotations",
    "format_analysis_context_pack_prompt_section",
    "get_analysis_context_pack_block_labels",
    "iter_analysis_context_pack_block_keys",
    "normalize_analysis_context_pack_language",
)

_load_legacy_module("src.analysis_context_pack.prompt", globals(), __all__)
del _load_legacy_module
