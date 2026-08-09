# -*- coding: utf-8 -*-
"""Official-SDK stdio and Streamable HTTP MCP process entry."""

from __future__ import annotations

import logging
from typing import Any

import anyio
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend
from mcp.server.stdio import stdio_server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.authentication import AuthenticationMiddleware
import uvicorn

from src.auth import is_auth_enabled
from src.mcp_server.auth_gate import AdminSessionTokenVerifier
from src.mcp_server.config import McpConfigError, McpServerConfig, load_mcp_server_config
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.protocol import McpProtocolServer
from src.security.http_bind import InsecurePublicBindError, enforce_http_bind_security
from src.services.security_audit_service import (
    SecurityAuditService,
    SecurityAuditUnavailable,
    get_security_audit_service,
    require_security_audit_recorder,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class McpServerDisabledError(RuntimeError):
    """Raised when the dedicated process is started without explicit opt-in."""


class McpServerStartError(RuntimeError):
    """Raised when startup cannot satisfy the MCP security contract."""


def ensure_enabled(config: McpServerConfig) -> None:
    if not config.enabled:
        raise McpServerDisabledError(
            "MCP server is disabled. Set MCP_SERVER_ENABLED=true and explicit scopes to start it."
        )


def enforce_transport_security(config: McpServerConfig) -> None:
    """Fail closed before either transport takes ownership of its streams/socket."""
    if config.is_stdio:
        if not config.stdio_scopes:
            raise McpServerStartError("stdio transport requires MCP_STDIO_SCOPES")
        return
    if not config.is_http:
        raise McpServerStartError(f"Unsupported MCP transport: {config.transport}")
    if not is_auth_enabled():
        raise McpServerStartError(
            "Streamable HTTP requires ADMIN_AUTH_ENABLED=true; loopback is not authorization"
        )
    if not config.http_scopes or not config.http_session_token_sha256:
        raise McpServerStartError("Streamable HTTP requires scopes and a pinned session digest")
    try:
        enforce_http_bind_security(
            config.host,
            auth_enabled=True,
            entrypoint="MCP Streamable HTTP server",
            event_logger=logger,
        )
    except InsecurePublicBindError as exc:
        raise McpServerStartError(str(exc)) from exc


def build_protocol_server(
    config: McpServerConfig | None = None,
    *,
    handlers: McpToolHandlers | None = None,
    security_audit: Any = None,
) -> tuple[McpServerConfig, McpProtocolServer]:
    resolved = config or load_mcp_server_config()
    ensure_enabled(resolved)
    enforce_transport_security(resolved)
    return resolved, McpProtocolServer(
        config=resolved,
        handlers=handlers,
        security_audit=security_audit,
    )


def run_stdio_server(
    config: McpServerConfig | None = None,
    *,
    handlers: McpToolHandlers | None = None,
) -> int:
    resolved, protocol = build_protocol_server(config, handlers=handlers)
    if not resolved.is_stdio:
        raise McpServerStartError("run_stdio_server requires transport=stdio")

    async def serve() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await protocol.sdk_server.run(
                read_stream,
                write_stream,
                protocol.sdk_server.create_initialization_options(),
            )

    anyio.run(serve)
    return 0


class _HttpBodyReadTimeout(RuntimeError):
    """Internal marker for a request-body receive deadline."""


class _ReceiveDeadlineMiddleware:
    """Apply a per-body-chunk read deadline before SDK parsing/dispatch."""

    def __init__(self, app: Any, timeout_seconds: int) -> None:
        self.app = app
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        body_complete = False

        async def receive_with_deadline() -> dict[str, Any]:
            nonlocal body_complete
            if body_complete:
                return await receive()
            try:
                with anyio.fail_after(self.timeout_seconds):
                    message = await receive()
            except TimeoutError as exc:
                raise _HttpBodyReadTimeout() from exc
            if message.get("type") == "http.request" and not message.get("more_body", False):
                body_complete = True
            return message

        try:
            await self.app(scope, receive_with_deadline, send)
        except _HttpBodyReadTimeout:
            body = b'{"error":"request_timeout","message":"HTTP body read timed out"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 408,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})


class _MissingBearerAuditMiddleware:
    """Durably audit missing/malformed HTTP credentials before SDK rejection."""

    def __init__(self, app: Any, security_audit: Any = None) -> None:
        self.app = app
        self.audit = require_security_audit_recorder(
            security_audit or get_security_audit_service()
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") != "/mcp":
            await self.app(scope, receive, send)
            return
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        if headers.get("authorization", "").lower().startswith("bearer "):
            await self.app(scope, receive, send)
            return
        correlation_id = SecurityAuditService.new_correlation_id()
        fields = {
            "event_type": "mcp.auth",
            "actor_type": "anonymous",
            "actor_id": "anonymous-http",
            "execution_id": correlation_id,
            "action": "mcp.authenticate",
            "target_type": "mcp_resource",
            "target_id": "stockpulse-mcp",
            "correlation_id": correlation_id,
            "metadata": {"transport": "streamable-http"},
        }
        try:
            self.audit.record_attempt(**fields)
            self.audit.record_completion(
                **fields,
                outcome="denied",
                reason_code="missing_bearer",
            )
        except SecurityAuditUnavailable:
            body = b'{"error":"security_audit_unavailable","message":"Security audit storage is unavailable"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"cache-control", b"no-store"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def build_http_app(
    config: McpServerConfig,
    protocol: McpProtocolServer,
    *,
    security_audit: Any = None,
) -> Any:
    """Build the authenticated standard Streamable HTTP ASGI application."""
    transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(config.allowed_hosts),
        allowed_origins=list(config.allowed_origins),
    )
    audit = security_audit or get_security_audit_service()
    verifier = AdminSessionTokenVerifier(config, security_audit=audit)
    app = protocol.sdk_server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=False,
        stateless_http=False,
        max_request_body_size=config.http_max_body_bytes,
        transport_security=transport_security,
        host=config.host,
        token_verifier=verifier,
    )
    # The low-level SDK route enforces token_verifier but only installs its
    # authentication middleware when OAuth AuthSettings are also supplied.
    # StockPulse deliberately reuses its existing audience-pinned admin session
    # instead of advertising a non-existent OAuth authorization server, so mount
    # the SDK's own bearer backend/context middleware explicitly.
    app = AuthContextMiddleware(app)
    app = AuthenticationMiddleware(app, backend=BearerAuthBackend(verifier))
    app = _MissingBearerAuditMiddleware(app, security_audit=audit)
    return _ReceiveDeadlineMiddleware(app, config.http_read_timeout_seconds)


def run_http_server(
    config: McpServerConfig | None = None,
    *,
    handlers: McpToolHandlers | None = None,
) -> int:
    resolved, protocol = build_protocol_server(config, handlers=handlers)
    if not resolved.is_http:
        raise McpServerStartError("run_http_server requires transport=streamable-http")
    app = build_http_app(resolved, protocol)
    uvicorn.run(
        app,
        host=resolved.host,
        port=resolved.port,
        workers=1,
        limit_concurrency=resolved.http_max_connections,
        backlog=resolved.http_backlog,
        timeout_keep_alive=resolved.http_keepalive_timeout_seconds,
        h11_max_incomplete_event_size=resolved.http_max_header_bytes,
        log_config=None,
    )
    return 0


def run(config: McpServerConfig | None = None, *, handlers: McpToolHandlers | None = None) -> int:
    resolved = config or load_mcp_server_config()
    ensure_enabled(resolved)
    if resolved.is_stdio:
        return run_stdio_server(resolved, handlers=handlers)
    if resolved.is_http:
        return run_http_server(resolved, handlers=handlers)
    raise McpServerStartError(f"Unsupported MCP transport: {resolved.transport}")


def main(argv: list[str] | None = None) -> int:
    del argv
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [mcp_server] %(message)s",
    )
    try:
        return run()
    except McpServerDisabledError as exc:
        log_safe_exception(
            logger,
            "MCP server is disabled",
            exc,
            error_code="mcp_server_disabled",
        )
        return 2
    except (McpConfigError, McpServerStartError) as exc:
        log_safe_exception(
            logger,
            "MCP server configuration or startup failed",
            exc,
            error_code="mcp_server_start_failed",
        )
        return 3
    except Exception as exc:  # broad-exception: fallback_recorded - Dedicated process entry logs and exits nonzero on fatal startup/runtime failure.
        log_safe_exception(
            logger,
            "MCP server failed",
            exc,
            error_code="mcp_server_failed",
        )
        return 1
