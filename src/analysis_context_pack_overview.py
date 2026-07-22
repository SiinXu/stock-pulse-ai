# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.analysis_context_pack.overview`."""

import src.analysis_context_pack_prompt as _legacy_prompt
from src.analysis_context_pack._facade import load_legacy_module as _load_legacy_module
from src.analysis_context_pack.overview import (
    ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY,
    Any,
    ContextFieldStatus,
    Dict,
    List,
    MARKET_PHASE_SUMMARY_KEY,
    Mapping,
    Optional,
    SENSITIVE_MARKERS,
    analysis_context_pack_to_dict,
    annotations,
    extract_analysis_context_pack_overview,
    get_analysis_context_pack_block_labels,
    iter_analysis_context_pack_block_keys,
    json,
    log_safe_exception,
    logger,
    logging,
    render_analysis_context_pack_overview,
    sanitize_context_snapshot_for_api,
)


__all__ = (
    "ANALYSIS_CONTEXT_PACK_OVERVIEW_KEY",
    "Any",
    "ContextFieldStatus",
    "Dict",
    "List",
    "MARKET_PHASE_SUMMARY_KEY",
    "Mapping",
    "Optional",
    "SENSITIVE_MARKERS",
    "analysis_context_pack_to_dict",
    "annotations",
    "extract_analysis_context_pack_overview",
    "get_analysis_context_pack_block_labels",
    "iter_analysis_context_pack_block_keys",
    "json",
    "log_safe_exception",
    "logger",
    "logging",
    "render_analysis_context_pack_overview",
    "sanitize_context_snapshot_for_api",
)

_load_legacy_module("src.analysis_context_pack.overview", globals(), __all__)
for _prompt_binding in (
    "SENSITIVE_MARKERS",
    "analysis_context_pack_to_dict",
    "get_analysis_context_pack_block_labels",
    "iter_analysis_context_pack_block_keys",
):
    globals()[_prompt_binding] = getattr(_legacy_prompt, _prompt_binding)
del _prompt_binding
del _legacy_prompt
del _load_legacy_module
