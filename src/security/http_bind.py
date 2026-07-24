"""Fail-closed policy for HTTP service bind addresses."""

from __future__ import annotations

import ipaddress
import logging
import os
from typing import Optional


ALLOW_INSECURE_PUBLIC_BIND_ENV = "ALLOW_INSECURE_PUBLIC_BIND"
INSECURE_PUBLIC_BIND_ERROR_MESSAGE = (
    "Refusing to start the HTTP service: administrator authentication is disabled "
    "and the requested bind is not local-only. Enable ADMIN_AUTH_ENABLED or bind "
    "to a loopback address or Unix socket. ALLOW_INSECURE_PUBLIC_BIND=true is an "
    "emergency-only, high-risk override."
)
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_LOCAL_HOSTNAMES = frozenset({"localhost", "localhost."})


class InsecurePublicBindError(RuntimeError):
    """Raised when an unauthenticated HTTP service requests a non-local bind."""


def is_local_only_bind(host: Optional[str], *, unix_socket: Optional[str] = None) -> bool:
    """Return whether a bind is explicitly limited to the local machine."""
    if unix_socket:
        return True

    normalized = (host or "").strip().lower()
    if normalized in _LOCAL_HOSTNAMES:
        return True
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    if not normalized:
        return False

    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def insecure_public_bind_override_enabled() -> bool:
    """Return whether the explicit high-risk public-bind override is enabled."""
    return os.getenv(ALLOW_INSECURE_PUBLIC_BIND_ENV, "false").strip().lower() in _TRUE_VALUES


def enforce_http_bind_security(
    host: Optional[str],
    *,
    unix_socket: Optional[str] = None,
    inherited_socket: bool = False,
    auth_enabled: Optional[bool] = None,
    allow_insecure_public_bind: Optional[bool] = None,
    event_logger: Optional[logging.Logger] = None,
    entrypoint: str = "HTTP service",
) -> None:
    """Reject non-local HTTP binds when administrator authentication is disabled."""
    if not inherited_socket and is_local_only_bind(host, unix_socket=unix_socket):
        return

    if auth_enabled is None:
        from src.auth import is_auth_enabled

        auth_enabled = is_auth_enabled()
    if auth_enabled:
        return

    if allow_insecure_public_bind is None:
        allow_insecure_public_bind = insecure_public_bind_override_enabled()
    if allow_insecure_public_bind:
        (event_logger or logging.getLogger(__name__)).warning(
            "SECURITY WARNING [insecure_public_bind_override]: %s is allowing a "
            "non-local HTTP bind while administrator authentication is disabled "
            "because ALLOW_INSECURE_PUBLIC_BIND=true. Requests are exposed without "
            "authentication.",
            entrypoint,
        )
        return

    raise InsecurePublicBindError(INSECURE_PUBLIC_BIND_ERROR_MESSAGE)
