# -*- coding: utf-8 -*-
"""Eastmoney request-failure classifier for efinance history-failure formatting.

The helper is cloned onto ``src.data_provider.efinance_fetcher`` globals
(ADR-006) so ``_classify_eastmoney_error`` call sites and test patches stay on
the compatibility facade. The classifier remains a module-level function, not a
class method.
"""

from __future__ import annotations

from typing import Callable, Optional, Tuple

import requests  # Facade free-name anchor; the clone resolves ``requests`` from facade globals.

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


def _classify_eastmoney_error(exc: Exception) -> Tuple[str, str]:
    """
    Classify Eastmoney request failures into stable log categories.
    """
    message = str(exc).strip()
    lowered = message.lower()

    remote_disconnect_keywords = (
        'remotedisconnected',
        'remote end closed connection without response',
        'connection aborted',
        'connection broken',
        'protocolerror',
    )
    timeout_keywords = (
        'timeout',
        'timed out',
        'readtimeout',
        'connecttimeout',
    )
    rate_limit_keywords = (
        'banned',
        'blocked',
        '频率',
        'rate limit',
        'too many requests',
        '429',
        '限制',
        'forbidden',
        '403',
    )

    if any(keyword in lowered for keyword in remote_disconnect_keywords):
        return "remote_disconnect", message
    if isinstance(exc, (TimeoutError, requests.exceptions.Timeout)) or any(
        keyword in lowered for keyword in timeout_keywords
    ):
        return "timeout", message
    if any(keyword in lowered for keyword in rate_limit_keywords):
        return "rate_limit_or_anti_bot", message
    if isinstance(exc, requests.exceptions.RequestException):
        return "request_error", message
    return "unknown_request_error", message


EXPECTED_EASTMONEY_ERROR_NAMES: Tuple[str, ...] = (
    "_classify_eastmoney_error",
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
