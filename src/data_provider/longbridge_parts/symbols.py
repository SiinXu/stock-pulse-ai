# -*- coding: utf-8 -*-
"""Longbridge US/HK classifiers and symbol conversion helpers.

The helpers are cloned onto ``src.data_provider.longbridge_fetcher`` globals
(ADR-006) so ``_is_us_code``, ``_is_hk_code``, and ``_to_longbridge_symbol``
call sites and test patches stay on the compatibility facade. The classifiers
remain module-level functions, not class methods.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from src.data_provider.us_index_mapping import is_us_index_code, is_us_stock_code

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")

# Facade free-name anchors for flake8 F821 / independent owner callability.
# The cloned functions resolve ``is_us_stock_code``, ``is_us_index_code``,
# ``_is_us_code``, and ``_is_hk_code`` from
# ``src.data_provider.longbridge_fetcher`` globals at runtime (ADR-006).


def _is_us_code(stock_code: str) -> bool:
    normalized = stock_code.strip().upper()
    return is_us_stock_code(normalized) or is_us_index_code(normalized)


def _is_hk_code(stock_code: str) -> bool:
    """Return whether a symbol follows the shared Hong Kong code contract."""
    normalized = (stock_code or "").strip().upper()
    if normalized.startswith("HK"):
        digits = normalized[2:]
        return digits.isdigit() and 1 <= len(digits) <= 5
    if normalized.endswith(".HK"):
        base = normalized[:-3]
        return base.isdigit() and 1 <= len(base) <= 5
    if normalized.isdigit() and 4 <= len(normalized) <= 5:
        return True
    return False


def _to_longbridge_symbol(stock_code: str) -> Optional[str]:
    """Convert internal stock code to Longbridge symbol format.

    Examples:
        AAPL      -> AAPL.US
        HK00700   -> 0700.HK
        00700     -> 0700.HK (5-digit pure number treated as HK)
    """
    code = stock_code.strip()
    upper = code.upper()

    if upper.endswith(".US"):
        return upper
    if upper.endswith(".HK"):
        return upper

    if _is_us_code(code):
        return f"{upper}.US"

    if _is_hk_code(code):
        upper = code.upper()
        if upper.startswith("HK"):
            digits = upper[2:]
        else:
            digits = upper
        digits = digits.lstrip("0") or "0"
        return f"{digits.zfill(4)}.HK"

    return None


EXPECTED_SYMBOL_NAMES: Tuple[str, ...] = (
    "_is_us_code",
    "_is_hk_code",
    "_to_longbridge_symbol",
)


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""

    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""

    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
