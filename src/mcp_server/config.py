# -*- coding: utf-8 -*-
"""Environment-backed configuration for the optional MCP server.

Configuration is read only from process environment variables so this module
does not require changes to the shared config registry (owned by other tasks).
Defaults keep the feature off with zero network impact.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

MCP_SERVER_ENABLED_ENV = "MCP_SERVER_ENABLED"
MCP_SERVER_TRANSPORT_ENV = "MCP_SERVER_TRANSPORT"
MCP_SERVER_HOST_ENV = "MCP_SERVER_HOST"
MCP_SERVER_PORT_ENV = "MCP_SERVER_PORT"
MCP_SESSION_TOKEN_ENV = "MCP_SESSION_TOKEN"
MCP_ANALYSIS_TIMEOUT_SECONDS_ENV = "MCP_ANALYSIS_TIMEOUT_SECONDS"
MCP_ANALYSIS_MAX_STOCKS_ENV = "MCP_ANALYSIS_MAX_STOCKS"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TRANSPORT = "stdio"
DEFAULT_ANALYSIS_TIMEOUT_SECONDS = 120
DEFAULT_ANALYSIS_MAX_STOCKS = 5

SUPPORTED_TRANSPORTS = frozenset({"stdio", "http"})


def _env_flag(name: str, default: str = "false") -> bool:
    raw = os.getenv(name, default)
    return str(raw).strip().lower() in _TRUE_VALUES


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 86400) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def is_mcp_server_enabled() -> bool:
    """Return whether the operator opted into the MCP server surface."""
    return _env_flag(MCP_SERVER_ENABLED_ENV, "false")


@dataclass(frozen=True)
class McpServerConfig:
    """Resolved MCP server settings."""

    enabled: bool
    transport: str
    host: str
    port: int
    session_token: Optional[str]
    analysis_timeout_seconds: int
    analysis_max_stocks: int

    @property
    def is_stdio(self) -> bool:
        return self.transport == "stdio"

    @property
    def is_http(self) -> bool:
        return self.transport == "http"


def load_mcp_server_config() -> McpServerConfig:
    """Load MCP server configuration from the process environment."""
    transport = (os.getenv(MCP_SERVER_TRANSPORT_ENV) or DEFAULT_TRANSPORT).strip().lower()
    if transport not in SUPPORTED_TRANSPORTS:
        transport = DEFAULT_TRANSPORT

    host = (os.getenv(MCP_SERVER_HOST_ENV) or DEFAULT_HOST).strip() or DEFAULT_HOST
    port = _env_int(MCP_SERVER_PORT_ENV, DEFAULT_PORT, minimum=1, maximum=65535)
    token_raw = os.getenv(MCP_SESSION_TOKEN_ENV)
    session_token = token_raw.strip() if token_raw and token_raw.strip() else None

    return McpServerConfig(
        enabled=is_mcp_server_enabled(),
        transport=transport,
        host=host,
        port=port,
        session_token=session_token,
        analysis_timeout_seconds=_env_int(
            MCP_ANALYSIS_TIMEOUT_SECONDS_ENV,
            DEFAULT_ANALYSIS_TIMEOUT_SECONDS,
            minimum=5,
            maximum=3600,
        ),
        analysis_max_stocks=_env_int(
            MCP_ANALYSIS_MAX_STOCKS_ENV,
            DEFAULT_ANALYSIS_MAX_STOCKS,
            minimum=1,
            maximum=50,
        ),
    )
