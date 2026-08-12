# -*- coding: utf-8 -*-
"""Request-local outbound notification delivery intent."""

from __future__ import annotations

from contextvars import ContextVar, Token


_OUTBOUND_NOTIFICATIONS_ENABLED: ContextVar[bool] = ContextVar(
    "outbound_notifications_enabled",
    default=True,
)


def outbound_notifications_enabled() -> bool:
    """Return the delivery intent for the current execution context."""
    return _OUTBOUND_NOTIFICATIONS_ENABLED.get() is True


def set_outbound_notifications_enabled(enabled: bool) -> Token:
    """Set an exact boolean delivery intent and return its reset token."""
    return _OUTBOUND_NOTIFICATIONS_ENABLED.set(enabled is True)


def reset_outbound_notifications_enabled(token: Token) -> None:
    """Restore the delivery intent that preceded *token*."""
    _OUTBOUND_NOTIFICATIONS_ENABLED.reset(token)


__all__ = [
    "outbound_notifications_enabled",
    "reset_outbound_notifications_enabled",
    "set_outbound_notifications_enabled",
]
