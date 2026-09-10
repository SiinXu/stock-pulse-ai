# -*- coding: utf-8 -*-
"""yfinance Yahoo/Stooq outbound HTTP guard.

The URL tuple and context-manager factory are cloned onto
``src.data_provider.yfinance_fetcher`` globals (ADR-006) so
``with _yfinance_http_guard():`` call sites and test patches stay on the
compatibility facade. The guard remains a module-level function, not a
class method.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

from src.security.outbound_policy import guard_outbound_urls

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")

# Hosts owned by the yfinance SDK and the Stooq urllib fallback. LOCAL_ONLY_MODE
# rejects these at guard entry; strict_dns is off so extra Yahoo CDN hosts used
# when the flag is off do not become unexpected-target failures.
_YFINANCE_OUTBOUND_URLS = (
    "https://query1.finance.yahoo.com/",
    "https://query2.finance.yahoo.com/",
    "https://stooq.com/",
)


def _yfinance_http_guard():
    return guard_outbound_urls(_YFINANCE_OUTBOUND_URLS, strict_dns=False)


EXPECTED_HTTP_GUARD_NAMES: Tuple[str, ...] = (
    "_YFINANCE_OUTBOUND_URLS",
    "_yfinance_http_guard",
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
