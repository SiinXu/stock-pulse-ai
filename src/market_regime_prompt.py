# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.market.regime_prompt`."""

from src.market._facade import load_legacy_module as _load_legacy_module
from src.market.regime_prompt import (
    format_market_regime_prompt_section,
)


__all__ = (
    "format_market_regime_prompt_section",
)

_load_legacy_module("src.market.regime_prompt", globals(), __all__)
del _load_legacy_module
