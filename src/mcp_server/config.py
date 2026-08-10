# -*- coding: utf-8 -*-
"""Strict environment configuration for the optional MCP process."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

MCP_SERVER_ENABLED_ENV = "MCP_SERVER_ENABLED"
MCP_SERVER_TRANSPORT_ENV = "MCP_SERVER_TRANSPORT"
MCP_SERVER_HOST_ENV = "MCP_SERVER_HOST"
MCP_SERVER_PORT_ENV = "MCP_SERVER_PORT"

ALL_MCP_SCOPES = frozenset(
    {"market.read", "history.read", "portfolio.read", "analysis.trigger"}
)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_TRANSPORT = "stdio"
DEFAULT_ANALYSIS_MAX_STOCKS = 5

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class McpConfigError(ValueError):
    """Raised when an explicit MCP setting is malformed or unsafe."""


def _strict_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise McpConfigError(f"{name} must be a boolean (true/false), got {raw!r}")


def _strict_int(name: str, *, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise McpConfigError(f"{name} must be an integer, got {raw!r}") from exc
    if not minimum <= value <= maximum:
        raise McpConfigError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value


def _csv(name: str, *, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    values = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    if not values:
        raise McpConfigError(f"{name} must contain at least one value")
    return values


def _scope_set(name: str) -> frozenset[str]:
    scopes = frozenset(_csv(name))
    unknown = scopes - ALL_MCP_SCOPES
    if unknown:
        raise McpConfigError(f"{name} contains unsupported scopes: {', '.join(sorted(unknown))}")
    return scopes


def is_mcp_server_enabled() -> bool:
    """Return whether the operator explicitly enabled the MCP process."""
    return _strict_flag(MCP_SERVER_ENABLED_ENV, default=False)


@dataclass(frozen=True)
class McpServerConfig:
    """Resolved, startup-validated MCP process settings."""

    enabled: bool = False
    transport: str = DEFAULT_TRANSPORT
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    stdio_scopes: frozenset[str] = frozenset()
    stdio_principal: str = "local-operator"
    http_scopes: frozenset[str] = frozenset()
    http_session_token_sha256: str | None = None
    http_resource: str = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/mcp"
    allowed_hosts: tuple[str, ...] = ("127.0.0.1:*", "localhost:*", "[::1]:*")
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    )
    rate_limit_per_minute: int = 60
    analysis_rate_limit_per_minute: int = 2
    max_concurrent_tools: int = 8
    http_max_connections: int = 32
    http_backlog: int = 16
    http_max_body_bytes: int = 1_000_000
    http_max_header_bytes: int = 32_768
    http_read_timeout_seconds: int = 10
    http_keepalive_timeout_seconds: int = 5
    admin_session_max_age_hours: int = 24
    analysis_max_stocks: int = DEFAULT_ANALYSIS_MAX_STOCKS

    @property
    def is_stdio(self) -> bool:
        return self.transport == "stdio"

    @property
    def is_http(self) -> bool:
        return self.transport == "streamable-http"


def load_mcp_server_config() -> McpServerConfig:
    """Load configuration and reject every explicit invalid value."""
    enabled = is_mcp_server_enabled()
    raw_transport = (os.getenv(MCP_SERVER_TRANSPORT_ENV) or DEFAULT_TRANSPORT).strip().lower()
    if raw_transport == "http":
        raw_transport = "streamable-http"
    if raw_transport not in {"stdio", "streamable-http"}:
        raise McpConfigError(
            f"{MCP_SERVER_TRANSPORT_ENV} must be stdio or streamable-http, got {raw_transport!r}"
        )

    host = (os.getenv(MCP_SERVER_HOST_ENV) or DEFAULT_HOST).strip()
    if not host or any(char.isspace() for char in host) or "/" in host:
        raise McpConfigError(f"{MCP_SERVER_HOST_ENV} is not a valid bind host")
    port = _strict_int(MCP_SERVER_PORT_ENV, default=DEFAULT_PORT, minimum=1, maximum=65535)
    stdio_scopes = _scope_set("MCP_STDIO_SCOPES")
    http_scopes = _scope_set("MCP_HTTP_SCOPES")
    stdio_principal = (os.getenv("MCP_STDIO_PRINCIPAL") or "local-operator").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}", stdio_principal):
        raise McpConfigError("MCP_STDIO_PRINCIPAL contains unsupported characters")

    token_hash = (os.getenv("MCP_HTTP_SESSION_TOKEN_SHA256") or "").strip().lower() or None
    if token_hash is not None and not _SHA256_RE.fullmatch(token_hash):
        raise McpConfigError("MCP_HTTP_SESSION_TOKEN_SHA256 must be a 64-character SHA-256 hex digest")

    resource = (os.getenv("MCP_HTTP_RESOURCE") or f"http://{host}:{port}/mcp").strip()
    if not resource.startswith(("http://", "https://")):
        raise McpConfigError("MCP_HTTP_RESOURCE must be an absolute http(s) URL")

    config = McpServerConfig(
        enabled=enabled,
        transport=raw_transport,
        host=host,
        port=port,
        stdio_scopes=stdio_scopes,
        stdio_principal=stdio_principal,
        http_scopes=http_scopes,
        http_session_token_sha256=token_hash,
        http_resource=resource,
        allowed_hosts=_csv(
            "MCP_HTTP_ALLOWED_HOSTS",
            default=(f"{host}:*",) if host not in {"127.0.0.1", "localhost", "::1"} else ("127.0.0.1:*", "localhost:*", "[::1]:*"),
        ),
        allowed_origins=_csv(
            "MCP_HTTP_ALLOWED_ORIGINS",
            default=("http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"),
        ),
        rate_limit_per_minute=_strict_int("MCP_RATE_LIMIT_PER_MINUTE", default=60, minimum=1, maximum=10_000),
        analysis_rate_limit_per_minute=_strict_int("MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE", default=2, minimum=1, maximum=60),
        max_concurrent_tools=_strict_int("MCP_MAX_CONCURRENT_TOOLS", default=8, minimum=1, maximum=128),
        http_max_connections=_strict_int("MCP_HTTP_MAX_CONNECTIONS", default=32, minimum=1, maximum=1024),
        http_backlog=_strict_int("MCP_HTTP_BACKLOG", default=16, minimum=1, maximum=1024),
        http_max_body_bytes=_strict_int("MCP_HTTP_MAX_BODY_BYTES", default=1_000_000, minimum=1024, maximum=10_000_000),
        http_max_header_bytes=_strict_int("MCP_HTTP_MAX_HEADER_BYTES", default=32_768, minimum=4096, maximum=262_144),
        http_read_timeout_seconds=_strict_int("MCP_HTTP_READ_TIMEOUT_SECONDS", default=10, minimum=1, maximum=120),
        http_keepalive_timeout_seconds=_strict_int("MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS", default=5, minimum=1, maximum=120),
        admin_session_max_age_hours=_strict_int("ADMIN_SESSION_MAX_AGE_HOURS", default=24, minimum=1, maximum=720),
        analysis_max_stocks=_strict_int("MCP_ANALYSIS_MAX_STOCKS", default=DEFAULT_ANALYSIS_MAX_STOCKS, minimum=1, maximum=50),
    )

    if enabled and config.is_stdio and not config.stdio_scopes:
        raise McpConfigError("MCP_STDIO_SCOPES is required when the stdio MCP server is enabled")
    if enabled and config.is_http:
        if not config.http_scopes:
            raise McpConfigError("MCP_HTTP_SCOPES is required when Streamable HTTP is enabled")
        if config.http_session_token_sha256 is None:
            raise McpConfigError(
                "MCP_HTTP_SESSION_TOKEN_SHA256 is required to audience-pin the accepted admin session"
            )
    return config
