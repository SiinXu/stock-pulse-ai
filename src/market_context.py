# -*- coding: utf-8 -*-
"""Compatibility facade for :mod:`src.market.context`."""

from src.market._facade import load_legacy_module as _load_legacy_module
from src.market.context import (
    Optional,
    detect_market,
    get_market_guidelines,
    get_market_role,
    get_suffix_market,
    re,
)


__all__ = (
    "Optional",
    "detect_market",
    "get_market_guidelines",
    "get_market_role",
    "get_suffix_market",
    "re",
)

_load_legacy_module("src.market.context", globals(), __all__)
del _load_legacy_module
