"""Startup security gates and official-client transport interoperability."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from unittest.mock import MagicMock

import anyio
from mcp.client import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
import httpx2
import pytest

from src.mcp_server.config import ALL_MCP_SCOPES, McpServerConfig
from src.mcp_server.server import (
    _MissingBearerAuditMiddleware,
    _ReceiveDeadlineMiddleware,
    McpServerDisabledError,
    McpServerStartError,
    build_protocol_server,
    enforce_transport_security,
    main,
)
from src.services.security_audit_service import SecurityAuditUnavailable


class _BearerAuth(httpx2.Auth):
    def __init__(self, token: str) -> None:
        self.token = token

    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _stdio_config() -> McpServerConfig:
    return McpServerConfig(enabled=True, transport="stdio", stdio_scopes=ALL_MCP_SCOPES)


def _http_config(token: str, *, port: int = 8765) -> McpServerConfig:
    return McpServerConfig(
        enabled=True,
        transport="streamable-http",
        host="127.0.0.1",
        port=port,
        http_scopes=ALL_MCP_SCOPES,
        http_session_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        http_resource=f"http://127.0.0.1:{port}/mcp",
    )


def test_disabled_process_fails_before_server_construction() -> None:
    with pytest.raises(McpServerDisabledError):
        build_protocol_server(McpServerConfig())


def test_http_requires_admin_auth_even_on_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.mcp_server.server.is_auth_enabled", lambda: False)
    with pytest.raises(McpServerStartError, match="loopback is not authorization"):
        enforce_transport_security(_http_config("token"))


def test_http_security_gate_accepts_authenticated_explicit_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.mcp_server.server.is_auth_enabled", lambda: True)
    monkeypatch.setattr("src.mcp_server.server.enforce_http_bind_security", MagicMock())
    enforce_transport_security(_http_config("token"))


def test_main_returns_config_error_for_invalid_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_SERVER_ENABLED", "true")
    monkeypatch.setenv("MCP_SERVER_TRANSPORT", "htp")
    assert main([]) == 3


@pytest.mark.anyio
async def test_http_body_read_deadline_returns_408_within_bound() -> None:
    async def consuming_app(scope, receive, send) -> None:
        del scope, send
        await receive()

    middleware = _ReceiveDeadlineMiddleware(consuming_app, 0.05)
    messages: list[dict] = []

    async def slow_receive() -> dict:
        await anyio.sleep(1)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def capture(message: dict) -> None:
        messages.append(message)

    began = time.monotonic()
    await middleware({"type": "http", "method": "POST"}, slow_receive, capture)
    assert time.monotonic() - began < 0.5
    assert messages[0]["status"] == 408


@pytest.mark.anyio
async def test_missing_bearer_is_durably_audited_before_rejection() -> None:
    audit = MagicMock()
    inner_called = False

    async def inner(scope, receive, send) -> None:
        nonlocal inner_called
        del scope, receive, send
        inner_called = True

    middleware = _MissingBearerAuditMiddleware(inner, security_audit=audit)
    await middleware(
        {"type": "http", "path": "/mcp", "headers": []},
        MagicMock(),
        MagicMock(),
    )
    assert inner_called is True
    assert audit.record_attempt.call_count == 1
    assert audit.record_completion.call_args.kwargs["reason_code"] == "missing_bearer"


@pytest.mark.anyio
async def test_missing_bearer_fails_closed_when_audit_is_unavailable() -> None:
    audit = MagicMock()
    audit.record_attempt.side_effect = SecurityAuditUnavailable()
    inner = MagicMock()
    messages: list[dict] = []

    async def capture(message: dict) -> None:
        messages.append(message)

    middleware = _MissingBearerAuditMiddleware(inner, security_audit=audit)
    await middleware(
        {"type": "http", "path": "/mcp", "headers": []},
        MagicMock(),
        capture,
    )
    inner.assert_not_called()
    assert messages[0]["status"] == 503


@pytest.mark.anyio
async def test_official_stdio_client_real_subprocess(tmp_path: Path) -> None:
    env = {
        "MCP_SERVER_ENABLED": "true",
        "MCP_SERVER_TRANSPORT": "stdio",
        "MCP_STDIO_SCOPES": "market.read,history.read",
        "DATABASE_PATH": str(tmp_path / "stdio.db"),
        "ENV_FILE": str(tmp_path / "missing.env"),
        "PYTHONPATH": str(Path.cwd()),
    }
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "src.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as client:
            initialized = await client.initialize()
            listing = await client.list_tools()
            assert initialized.server_info.name == "stock-pulse-ai"
            assert {tool.name for tool in listing.tools} == {
                "get_realtime_quote",
                "get_stock_history",
                "list_analysis_history",
                "get_analysis_detail",
                "get_analysis_report",
                "get_analysis_status",
            }


@pytest.mark.anyio
async def test_official_streamable_http_client_real_server(tmp_path: Path) -> None:
    port = _unused_tcp_port()
    base_env = os.environ.copy()
    base_env.update(
        {
            "ADMIN_AUTH_ENABLED": "true",
            "ADMIN_SESSION_MAX_AGE_HOURS": "24",
            "DATABASE_PATH": str(tmp_path / "http.db"),
            "ENV_FILE": str(tmp_path / "missing.env"),
            "PYTHONPATH": str(Path.cwd()),
        }
    )
    token_result = subprocess.run(
        [sys.executable, "-c", "from src.auth import create_session; print(create_session())"],
        cwd=Path.cwd(),
        env=base_env,
        check=True,
        capture_output=True,
        text=True,
    )
    token = token_result.stdout.strip()
    server_env = dict(base_env)
    server_env.update(
        {
            "MCP_SERVER_ENABLED": "true",
            "MCP_SERVER_TRANSPORT": "streamable-http",
            "MCP_SERVER_HOST": "127.0.0.1",
            "MCP_SERVER_PORT": str(port),
            "MCP_HTTP_SCOPES": "market.read,history.read",
            "MCP_HTTP_SESSION_TOKEN_SHA256": hashlib.sha256(token.encode()).hexdigest(),
            "MCP_HTTP_RESOURCE": f"http://127.0.0.1:{port}/mcp",
        }
    )
    process = await anyio.open_process(
        [sys.executable, "-m", "src.mcp_server"],
        cwd=Path.cwd(),
        env=server_env,
        stdout=None,
        stderr=None,
    )
    try:
        await _wait_for_port(port)
        initialize_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "security-probe", "version": "1"},
            },
        }
        required_headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        async with httpx2.AsyncClient(auth=_BearerAuth(token), timeout=10) as raw_client:
            malicious_origin = await raw_client.post(
                f"http://127.0.0.1:{port}/mcp",
                json=initialize_payload,
                headers={**required_headers, "Origin": "https://attacker.example"},
            )
            assert malicious_origin.status_code == 403
            rebinding_host = await raw_client.post(
                f"http://127.0.0.1:{port}/mcp",
                json=initialize_payload,
                headers={**required_headers, "Host": "attacker.example"},
            )
            assert rebinding_host.status_code == 421
            simple_request = await raw_client.post(
                f"http://127.0.0.1:{port}/mcp",
                content=b"{}",
                headers={"Content-Type": "text/plain", "Accept": required_headers["Accept"]},
            )
            assert simple_request.status_code == 400
            wrong_accept = await raw_client.post(
                f"http://127.0.0.1:{port}/mcp",
                json=initialize_payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            assert wrong_accept.status_code == 406
            preflight = await raw_client.options(
                f"http://127.0.0.1:{port}/mcp",
                headers={"Origin": "https://attacker.example"},
            )
            assert preflight.status_code == 403
        async with httpx2.AsyncClient(timeout=10) as anonymous_client:
            unauthenticated = await anonymous_client.post(
                f"http://127.0.0.1:{port}/mcp",
                json=initialize_payload,
                headers=required_headers,
            )
            assert unauthenticated.status_code == 401

        authorization_seen: list[bool] = []

        async def observe_request(request) -> None:
            authorization_seen.append("authorization" in request.headers)

        async with httpx2.AsyncClient(
            auth=_BearerAuth(token),
            timeout=10,
            event_hooks={"request": [observe_request]},
        ) as http_client:
            async with streamable_http_client(
                f"http://127.0.0.1:{port}/mcp",
                http_client=http_client,
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as client:
                    initialized = await client.initialize()
                    listing = await client.list_tools()
                    assert initialized.server_info.name == "stock-pulse-ai"
                    assert "get_realtime_quote" in {tool.name for tool in listing.tools}
                    assert "get_portfolio_snapshot" not in {tool.name for tool in listing.tools}
        assert authorization_seen and all(authorization_seen)
    finally:
        process.terminate()
        with anyio.move_on_after(3):
            await process.wait()
        if process.returncode is None:
            process.kill()
            await process.wait()


def _unused_tcp_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_for_port(port: int) -> None:
    for _ in range(150):
        try:
            stream = await anyio.connect_tcp("127.0.0.1", port)
        except OSError:
            await anyio.sleep(0.1)
            continue
        await stream.aclose()
        return
    raise AssertionError(f"server did not listen on port {port}")
