# -*- coding: utf-8 -*-
"""MCP server process entry: stdio and optional HTTP transports.

Default-off: this process refuses to start unless MCP_SERVER_ENABLED=true.
It is never auto-started by ``server.py`` / ``main.py``; operators must run
``python -m src.mcp_server`` explicitly.
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

from src.mcp_server.config import McpServerConfig, load_mcp_server_config
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.protocol import McpProtocolServer
from src.security.http_bind import (
    InsecurePublicBindError,
    enforce_http_bind_security,
    is_local_only_bind,
)

logger = logging.getLogger(__name__)


class McpServerDisabledError(RuntimeError):
    """Raised when the process is started while MCP_SERVER_ENABLED is false."""


class McpServerStartError(RuntimeError):
    """Raised when the MCP server cannot start safely."""


def ensure_enabled(config: McpServerConfig) -> None:
    """Fail closed when the feature flag is off."""
    if not config.enabled:
        raise McpServerDisabledError(
            "MCP server is disabled. Set MCP_SERVER_ENABLED=true to start "
            "`python -m src.mcp_server`. Default is off (zero network impact)."
        )


def enforce_transport_security(config: McpServerConfig) -> None:
    """Apply bind / auth policy consistent with the HTTP API security baseline."""
    if config.is_stdio:
        # stdio is process-local; still warn when auth is off so operators know
        # any process that can spawn this server inherits full tool access.
        from src.auth import is_auth_enabled

        if not is_auth_enabled():
            logger.warning(
                "SECURITY WARNING [mcp_stdio_auth_disabled]: MCP stdio server is "
                "running with administrator authentication disabled. Any local "
                "process that can speak MCP to this stdio session can invoke "
                "exposed tools."
            )
        return

    if not config.is_http:
        raise McpServerStartError(f"Unsupported MCP transport: {config.transport}")

    try:
        enforce_http_bind_security(
            config.host,
            auth_enabled=None,
            entrypoint="MCP HTTP server",
            event_logger=logger,
        )
    except InsecurePublicBindError as exc:
        raise McpServerStartError(str(exc)) from exc

    if not is_local_only_bind(config.host):
        logger.warning(
            "SECURITY WARNING [mcp_public_bind]: MCP HTTP server binding to "
            "non-local host %s. Ensure ADMIN_AUTH_ENABLED=true, HTTPS at the edge, "
            "and that you intend to expose this surface. Prefer 127.0.0.1.",
            config.host,
        )


def build_protocol_server(
    config: Optional[McpServerConfig] = None,
    *,
    handlers: Optional[McpToolHandlers] = None,
) -> Tuple[McpServerConfig, McpProtocolServer]:
    """Load config (if needed) and build a protocol server instance."""
    resolved = config or load_mcp_server_config()
    ensure_enabled(resolved)
    enforce_transport_security(resolved)
    protocol = McpProtocolServer(
        config=resolved,
        handlers=handlers or McpToolHandlers(config=resolved),
    )
    return resolved, protocol


def run_stdio_server(
    config: Optional[McpServerConfig] = None,
    *,
    handlers: Optional[McpToolHandlers] = None,
    stdin=None,
    stdout=None,
) -> int:
    """Run newline-delimited JSON-RPC over stdio until EOF."""
    resolved, protocol = build_protocol_server(config, handlers=handlers)
    if not resolved.is_stdio:
        # Allow explicit stdio runner only for stdio transport.
        raise McpServerStartError(
            f"run_stdio_server requires transport=stdio, got {resolved.transport}"
        )

    in_stream = stdin if stdin is not None else sys.stdin
    out_stream = stdout if stdout is not None else sys.stdout
    logger.info(
        "MCP stdio server started (enabled=%s, auth_token_configured=%s)",
        resolved.enabled,
        bool(resolved.session_token),
    )

    while True:
        line = in_stream.readline()
        if line == "" or line is None:
            break
        if not str(line).strip():
            continue
        response = protocol.handle_raw(str(line))
        if response is None:
            continue
        out_stream.write(response + "\n")
        out_stream.flush()
    return 0


def run_http_server(
    config: Optional[McpServerConfig] = None,
    *,
    handlers: Optional[McpToolHandlers] = None,
) -> int:
    """Run a minimal HTTP JSON-RPC endpoint for MCP clients."""
    resolved, protocol = build_protocol_server(config, handlers=handlers)
    if not resolved.is_http:
        raise McpServerStartError(
            f"run_http_server requires transport=http, got {resolved.transport}"
        )

    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            logger.info("mcp_http: " + fmt, *args)

        def _read_json_body(self) -> Any:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return None
            if length > 1_000_000:
                raise ValueError("Request body too large")
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in {"/health", "/mcp/health"}:
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "transport": "http",
                        "enabled": True,
                    },
                )
                return
            self._send_json(
                404,
                {"error": "not_found", "message": "Not found"},
            )

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in {"/mcp", "/mcp/jsonrpc", "/"}:
                self._send_json(
                    404,
                    {"error": "not_found", "message": "Not found"},
                )
                return
            headers = {k: v for k, v in self.headers.items()}
            try:
                message = self._read_json_body()
            except Exception:
                self._send_json(
                    400,
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    },
                )
                return
            response = protocol.handle_message(message, headers=headers)
            if response is None:
                # Notifications: empty 204
                self.send_response(204)
                self.end_headers()
                return
            self._send_json(200, response)

    server = ThreadingHTTPServer((resolved.host, resolved.port), _Handler)
    logger.info(
        "MCP HTTP server listening on http://%s:%s/mcp (local_only=%s)",
        resolved.host,
        resolved.port,
        is_local_only_bind(resolved.host),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("MCP HTTP server interrupted")
    finally:
        server.server_close()
    return 0


def run(
    config: Optional[McpServerConfig] = None,
    *,
    handlers: Optional[McpToolHandlers] = None,
) -> int:
    """Start the configured MCP transport."""
    resolved = config or load_mcp_server_config()
    ensure_enabled(resolved)
    if resolved.is_stdio:
        return run_stdio_server(resolved, handlers=handlers)
    if resolved.is_http:
        return run_http_server(resolved, handlers=handlers)
    raise McpServerStartError(f"Unsupported MCP transport: {resolved.transport}")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry used by ``python -m src.mcp_server``."""
    _ = argv
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [mcp_server] %(message)s",
    )
    try:
        return run()
    except McpServerDisabledError as exc:
        logger.error("%s", exc)
        return 2
    except McpServerStartError as exc:
        logger.error("%s", exc)
        return 3
    except Exception as exc:  # broad-exception: process entry hard-fail
        logger.exception("MCP server failed: %s", exc)
        return 1


# Silence unused import warning for threading if static checkers complain.
_ = threading
