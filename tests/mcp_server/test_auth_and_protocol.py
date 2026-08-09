"""Official SDK lifecycle, scope, rate, and fail-closed audit tests."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import anyio
from mcp.client import Client, ClientSession
from mcp.shared.exceptions import MCPError
from mcp.shared.memory import create_client_server_memory_streams
from mcp_types import CallToolRequestParams
import pytest

from src.mcp_server.config import ALL_MCP_SCOPES, McpServerConfig
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.protocol import McpProtocolServer
from src.services.security_audit_service import SecurityAuditUnavailable


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _config(**overrides) -> McpServerConfig:
    values = {
        "enabled": True,
        "transport": "stdio",
        "stdio_scopes": ALL_MCP_SCOPES,
        "rate_limit_per_minute": 20,
        "analysis_rate_limit_per_minute": 2,
    }
    values.update(overrides)
    return McpServerConfig(**values)


def _protocol(config: McpServerConfig | None = None, audit: MagicMock | None = None) -> tuple[McpProtocolServer, MagicMock]:
    stock = MagicMock()
    stock.get_realtime_quote.return_value = {"stock_code": "AAPL", "current_price": 100.0}
    recorder = audit or MagicMock()
    cfg = config or _config()
    handlers = McpToolHandlers(config=cfg, stock_service=stock)
    return McpProtocolServer(config=cfg, handlers=handlers, security_audit=recorder), recorder


@pytest.mark.anyio
async def test_official_client_negotiates_and_calls_scoped_tool() -> None:
    protocol, audit = _protocol()
    async with Client(protocol.sdk_server, mode="legacy") as client:
        assert client.protocol_version
        assert client.server_info is not None
        assert client.server_info.name == "stock-pulse-ai"
        listing = await client.list_tools(cache_mode="reload")
        assert "get_realtime_quote" in {tool.name for tool in listing.tools}
        result = await client.call_tool("get_realtime_quote", {"stock_code": "AAPL"})
        assert result.is_error is False
        assert result.structured_content["stock_code"] == "AAPL"
    assert audit.record_attempt.call_count >= 2
    assert audit.record_completion.call_count >= 2


@pytest.mark.anyio
async def test_listing_is_filtered_and_call_is_denied_without_tool_scope() -> None:
    protocol, _audit = _protocol(_config(stdio_scopes=frozenset({"market.read"})))
    async with Client(protocol.sdk_server, mode="legacy") as client:
        listing = await client.list_tools(cache_mode="reload")
        names = {tool.name for tool in listing.tools}
        assert names == {"get_realtime_quote", "get_stock_history"}
        result = await client.session.call_tool("get_portfolio_snapshot", arguments={})
        assert result.is_error is True
        assert result.structured_content["error"] == "insufficient_scope"


@pytest.mark.anyio
async def test_per_principal_per_tool_rate_limit() -> None:
    protocol, _audit = _protocol(_config(rate_limit_per_minute=1))
    async with Client(protocol.sdk_server, mode="legacy") as client:
        first = await client.session.call_tool("get_realtime_quote", arguments={"stock_code": "AAPL"})
        second = await client.session.call_tool("get_realtime_quote", arguments={"stock_code": "AAPL"})
        assert first.is_error is False
        assert second.is_error is True
        assert second.structured_content["error"] == "rate_limited"


@pytest.mark.anyio
async def test_audit_unavailable_fails_closed_before_discovery() -> None:
    audit = MagicMock()
    audit.record_attempt.side_effect = SecurityAuditUnavailable()
    protocol, _audit = _protocol(audit=audit)
    async with Client(protocol.sdk_server, mode="legacy") as client:
        with pytest.raises(MCPError):
            await client.list_tools(cache_mode="reload")


@pytest.mark.anyio
async def test_tool_call_before_initialize_is_rejected_by_sdk_lifecycle() -> None:
    protocol, _audit = _protocol()
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(
                protocol.sdk_server.run,
                server_read,
                server_write,
                protocol.sdk_server.create_initialization_options(),
            )
            async with ClientSession(client_read, client_write) as session:
                with pytest.raises(MCPError):
                    await session.list_tools()
            await client_write.aclose()
            await server_write.aclose()
            task_group.cancel_scope.cancel()


@pytest.mark.anyio
async def test_concurrent_clients_have_independent_sdk_connections() -> None:
    protocol, _audit = _protocol(_config(rate_limit_per_minute=20))

    async def connect_and_list() -> str:
        async with Client(protocol.sdk_server, mode="legacy") as client:
            listing = await client.list_tools(cache_mode="reload")
            return client.protocol_version if listing.tools else ""

    versions: list[str] = []

    async def collect() -> None:
        versions.append(await connect_and_list())

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(collect)
        task_group.start_soon(collect)
    assert len(versions) == 2
    assert all(versions)


@pytest.mark.anyio
async def test_cancellation_does_not_abandon_owned_service_worker() -> None:
    started = threading.Event()
    finished = threading.Event()
    stock = MagicMock()

    def slow_quote(_stock_code: str) -> dict:
        started.set()
        time.sleep(0.2)
        finished.set()
        return {"stock_code": "AAPL", "current_price": 100.0}

    stock.get_realtime_quote.side_effect = slow_quote
    config = _config()
    audit = MagicMock()
    protocol = McpProtocolServer(
        config=config,
        handlers=McpToolHandlers(config=config, stock_service=stock),
        security_audit=audit,
    )
    began = time.monotonic()

    async def invoke() -> None:
        await protocol._call_tool(  # noqa: SLF001 - focused ownership-boundary regression
            None,
            CallToolRequestParams(name="get_realtime_quote", arguments={"stock_code": "AAPL"}),
        )

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(invoke)
        await anyio.to_thread.run_sync(started.wait)
        task_group.cancel_scope.cancel()
    assert finished.is_set()
    assert time.monotonic() - began >= 0.19
    reasons = [
        call.kwargs.get("reason_code")
        for call in audit.record_completion.call_args_list
    ]
    assert "cancelled_after_owned_completion" in reasons
