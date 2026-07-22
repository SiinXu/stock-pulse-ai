# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.market.structure_prompt`."""

from src.market._facade import load_legacy_module as _load_legacy_module
from src.market.structure_prompt import (
    Any,
    Iterable,
    List,
    MARKET_STRUCTURE_SCHEMA_VERSION,
    annotations,
    format_market_structure_prompt_section,
    normalize_report_language,
)


__all__ = (
    "Any",
    "Iterable",
    "List",
    "MARKET_STRUCTURE_SCHEMA_VERSION",
    "annotations",
    "format_market_structure_prompt_section",
    "normalize_report_language",
)

_load_legacy_module("src.market.structure_prompt", globals(), __all__)
del _load_legacy_module
