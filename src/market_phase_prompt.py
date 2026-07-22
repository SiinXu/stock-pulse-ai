# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.market.phase_prompt`."""

from src.market._facade import load_legacy_module as _load_legacy_module
from src.market.phase_prompt import (
    Any,
    Dict,
    List,
    Optional,
    annotations,
    format_market_phase_prompt_section,
)


__all__ = (
    "Any",
    "Dict",
    "List",
    "Optional",
    "annotations",
    "format_market_phase_prompt_section",
)

_load_legacy_module("src.market.phase_prompt", globals(), __all__)
del _load_legacy_module
