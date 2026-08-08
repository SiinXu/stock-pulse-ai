# -*- coding: utf-8 -*-
"""Authentication gate for MCP requests.

Reuses the existing administrator session model from ``src.auth``
(``is_auth_enabled`` / ``verify_session``). No parallel auth scheme is introduced.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

from src.auth import is_auth_enabled, verify_session
from src.mcp_server.config import McpServerConfig


class McpAuthError(Exception):
    """Raised when an MCP request fails authentication."""

    def __init__(self, error: str = "unauthorized", message: str = "Login required") -> None:
        self.error = error
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class McpAuthContext:
    """Resolved credentials for one MCP request or session."""

    session_token: Optional[str]
    authenticated: bool
    auth_enabled: bool


def extract_session_token(
    *,
    config: McpServerConfig,
    headers: Optional[Mapping[str, str]] = None,
    explicit_token: Optional[str] = None,
) -> Optional[str]:
    """Resolve a session token from request headers, explicit arg, or env config."""
    if explicit_token and explicit_token.strip():
        return explicit_token.strip()

    if headers:
        lowered = {str(k).lower(): str(v) for k, v in headers.items()}
        auth = lowered.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
            if token:
                return token
        for key in ("x-dsa-session", "x-mcp-session", "cookie"):
            raw = lowered.get(key)
            if not raw:
                continue
            if key == "cookie":
                for part in raw.split(";"):
                    part = part.strip()
                    if part.lower().startswith("dsa_session="):
                        value = part.split("=", 1)[1].strip()
                        if value:
                            return value
            else:
                value = raw.strip()
                if value:
                    return value

    if config.session_token:
        return config.session_token
    return None


def build_auth_context(
    *,
    config: McpServerConfig,
    headers: Optional[Mapping[str, str]] = None,
    explicit_token: Optional[str] = None,
) -> McpAuthContext:
    """Build auth context without raising (for capability probes)."""
    auth_enabled = is_auth_enabled()
    token = extract_session_token(
        config=config,
        headers=headers,
        explicit_token=explicit_token,
    )
    if not auth_enabled:
        return McpAuthContext(
            session_token=token,
            authenticated=True,
            auth_enabled=False,
        )
    authenticated = bool(token) and verify_session(token)
    return McpAuthContext(
        session_token=token,
        authenticated=authenticated,
        auth_enabled=True,
    )


def require_mcp_auth(
    *,
    config: McpServerConfig,
    headers: Optional[Mapping[str, str]] = None,
    explicit_token: Optional[str] = None,
) -> McpAuthContext:
    """Require a valid admin session when administrator auth is enabled."""
    ctx = build_auth_context(
        config=config,
        headers=headers,
        explicit_token=explicit_token,
    )
    if not ctx.auth_enabled:
        return ctx
    if not ctx.authenticated:
        raise McpAuthError("unauthorized", "Login required")
    return ctx
