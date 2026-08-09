# -*- coding: utf-8 -*-
"""Official MCP SDK protocol adapter with scoped, audited dispatch."""

from __future__ import annotations

from collections import defaultdict, deque
from functools import partial
import json
import logging
import threading
import time
from typing import Any, Awaitable, Callable

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.lowlevel import Server
from mcp_types import CallToolRequestParams, CallToolResult, ListToolsResult, PaginatedRequestParams, TextContent, Tool
from pydantic import ValidationError

from src.mcp_server import SERVER_NAME, SERVER_VERSION
from src.mcp_server.config import McpServerConfig
from src.mcp_server.errors import McpBusyError, mcp_error_payload
from src.mcp_server.handlers import McpToolHandlers
from src.mcp_server.tools import call_tool, list_tool_definitions, required_scope
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
    get_security_audit_service,
    require_security_audit_recorder,
)

logger = logging.getLogger(__name__)


class McpRateLimitExceeded(RuntimeError):
    """Raised when a principal exhausts a tool-specific request budget."""


class McpCapacityExceeded(RuntimeError):
    """Raised when all bounded tool execution slots are occupied."""


class PerPrincipalToolRateLimiter:
    """Small in-process sliding-window limiter keyed by principal and tool."""

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def consume(self, principal: str, tool: str) -> None:
        limit = (
            self.config.analysis_rate_limit_per_minute
            if tool == "trigger_analysis"
            else self.config.rate_limit_per_minute
        )
        now = time.monotonic()
        cutoff = now - 60.0
        key = (principal, tool)
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                raise McpRateLimitExceeded(f"Rate limit exceeded for {tool}")
            events.append(now)


class McpProtocolServer:
    """StockPulse handlers hosted by the official MCP low-level server."""

    def __init__(
        self,
        *,
        config: McpServerConfig,
        handlers: McpToolHandlers | None = None,
        security_audit: SecurityAuditRecorder | None = None,
        rate_limiter: PerPrincipalToolRateLimiter | None = None,
    ) -> None:
        self.config = config
        self.handlers = handlers or McpToolHandlers(config=config)
        self.audit = require_security_audit_recorder(
            security_audit or get_security_audit_service()
        )
        self.rate_limiter = rate_limiter or PerPrincipalToolRateLimiter(config)
        self._capacity = threading.BoundedSemaphore(config.max_concurrent_tools)
        self.sdk_server: Server[dict[str, Any]] = Server(
            SERVER_NAME,
            version=SERVER_VERSION,
            description="Curated StockPulse market, history, portfolio, and async analysis tools.",
            instructions=(
                "Every tool requires an explicit scope. Management-plane configuration, "
                "credentials, audit administration, and financial mutations are not exposed."
            ),
            on_list_tools=self._list_tools,
            on_call_tool=self._call_tool,
        )
        self.sdk_server.middleware.append(self._observe_cancellation)

    async def _list_tools(
        self,
        ctx: ServerRequestContext[dict[str, Any]],
        params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        del params
        actor_type, actor_id, scopes = self._principal()
        correlation_id = self._record_attempt(
            actor_type=actor_type,
            actor_id=actor_id,
            action="mcp.tools.list",
            target_type="mcp_inventory",
            target_id="curated-tools",
            metadata={"transport": self.config.transport},
        )
        try:
            self.rate_limiter.consume(actor_id, "tools.list")
            tools = [Tool.model_validate(item) for item in list_tool_definitions(scopes)]
            self._record_completion(
                actor_type=actor_type,
                actor_id=actor_id,
                action="mcp.tools.list",
                target_type="mcp_inventory",
                target_id="curated-tools",
                correlation_id=correlation_id,
                outcome="success",
                reason_code="listed",
                metadata={"tool_count": len(tools)},
            )
            return ListToolsResult(tools=tools)
        except McpRateLimitExceeded:
            self._record_completion_if_available(
                actor_type,
                actor_id,
                "mcp.tools.list",
                "mcp_inventory",
                "curated-tools",
                correlation_id,
                "rejected",
                "rate_limited",
            )
            raise
        except SecurityAuditUnavailable:
            raise

    async def _call_tool(
        self,
        ctx: ServerRequestContext[dict[str, Any]],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        del ctx
        actor_type, actor_id, scopes = self._principal()
        target_id = _bounded_target(params.name)
        correlation_id = self._record_attempt(
            actor_type=actor_type,
            actor_id=actor_id,
            action="mcp.tool.call",
            target_type="mcp_tool",
            target_id=target_id,
            metadata={"transport": self.config.transport},
        )
        try:
            scope = required_scope(params.name)
            if scope not in scopes:
                self._record_completion(
                    actor_type=actor_type,
                    actor_id=actor_id,
                    action="mcp.tool.call",
                    target_type="mcp_tool",
                    target_id=target_id,
                    correlation_id=correlation_id,
                    outcome="denied",
                    reason_code="insufficient_scope",
                    metadata={"required_scope": scope},
                )
                return _error_result("insufficient_scope", f"Required scope: {scope}")
            self.rate_limiter.consume(actor_id, params.name)
            if not self._capacity.acquire(blocking=False):
                raise McpCapacityExceeded("MCP tool capacity is exhausted")
            try:
                # Service APIs are synchronous and Python workers cannot be
                # force-cancelled safely. Shield ownership until the worker
                # finishes so client cancellation cannot release capacity or
                # report completion while an uncontrolled mutation continues.
                with anyio.CancelScope(shield=True):
                    payload = await anyio.to_thread.run_sync(
                        partial(call_tool, self.handlers, params.name, params.arguments or {}),
                        abandon_on_cancel=False,
                    )
            finally:
                self._capacity.release()
            # Deliver a pending client cancellation only after the synchronous
            # worker is owned to completion, then persist a cancellation result
            # instead of a misleading success.
            await anyio.lowlevel.checkpoint()
            self._record_completion(
                actor_type=actor_type,
                actor_id=actor_id,
                action="mcp.tool.call",
                target_type="mcp_tool",
                target_id=target_id,
                correlation_id=correlation_id,
                outcome="accepted" if params.name == "trigger_analysis" else "success",
                reason_code="submitted" if params.name == "trigger_analysis" else "completed",
                metadata={"required_scope": scope},
            )
            return _success_result(payload)
        except anyio.get_cancelled_exc_class():
            self._record_failure(
                actor_type,
                actor_id,
                target_id,
                correlation_id,
                "cancelled_after_owned_completion",
                outcome="rejected",
            )
            raise
        except ValidationError as exc:
            self._record_failure(actor_type, actor_id, target_id, correlation_id, "validation_error")
            return _error_result("validation_error", "Tool arguments failed strict validation", exc.errors(include_url=False))
        except ValueError as exc:
            self._record_failure(actor_type, actor_id, target_id, correlation_id, "validation_error")
            return _error_result("validation_error", str(exc) or "Invalid parameters")
        except McpRateLimitExceeded as exc:
            self._record_failure(actor_type, actor_id, target_id, correlation_id, "rate_limited", outcome="rejected")
            return _error_result("rate_limited", str(exc))
        except McpCapacityExceeded as exc:
            self._record_failure(actor_type, actor_id, target_id, correlation_id, "capacity_exceeded", outcome="rejected")
            return _error_result("busy", str(exc))
        except McpBusyError as exc:
            self._record_failure(actor_type, actor_id, target_id, correlation_id, "analysis_busy", outcome="rejected")
            return _error_result("busy", str(exc))
        except SecurityAuditUnavailable:
            return _error_result("security_audit_unavailable", "Security audit storage is unavailable")
        except Exception as exc:  # broad-exception: fallback_recorded - Keep the official MCP session alive after a service boundary failure.
            logger.exception("MCP tool %s failed", params.name)
            self._record_completion_if_available(
                actor_type,
                actor_id,
                "mcp.tool.call",
                "mcp_tool",
                target_id,
                correlation_id,
                "failure",
                "internal_error",
                {"exception_type": type(exc).__name__},
            )
            return _error_result("internal_error", "Internal server error")

    async def _observe_cancellation(
        self,
        ctx: ServerRequestContext[dict[str, Any]],
        call_next: CallNext,
    ) -> HandlerResult:
        if ctx.method != "notifications/cancelled":
            return await call_next(ctx)
        actor_type, actor_id, _scopes = self._principal()
        correlation_id = self._record_attempt(
            actor_type=actor_type,
            actor_id=actor_id,
            action="mcp.request.cancel",
            target_type="mcp_request",
            target_id="client-request",
            metadata={"transport": self.config.transport},
        )
        result = await call_next(ctx)
        self._record_completion(
            actor_type=actor_type,
            actor_id=actor_id,
            action="mcp.request.cancel",
            target_type="mcp_request",
            target_id="client-request",
            correlation_id=correlation_id,
            outcome="success",
            reason_code="cancelled",
        )
        return result

    def _principal(self) -> tuple[str, str, frozenset[str]]:
        token = get_access_token()
        if token is not None:
            actor_id = token.subject or token.client_id
            return "admin_session", _bounded_actor(actor_id), frozenset(token.scopes)
        return "local_process", self.config.stdio_principal, self.config.stdio_scopes

    def _record_attempt(
        self,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        correlation_id = SecurityAuditService.new_correlation_id()
        self.audit.record_attempt(
            event_type="mcp.request",
            actor_type=actor_type,
            actor_id=actor_id,
            execution_id=correlation_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            correlation_id=correlation_id,
            metadata=metadata,
        )
        return correlation_id

    def _record_completion(
        self,
        *,
        actor_type: str,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        correlation_id: str,
        outcome: str,
        reason_code: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.audit.record_completion(
            event_type="mcp.request",
            actor_type=actor_type,
            actor_id=actor_id,
            execution_id=correlation_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            reason_code=reason_code,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    def _record_failure(
        self,
        actor_type: str,
        actor_id: str,
        target_id: str,
        correlation_id: str,
        reason_code: str,
        *,
        outcome: str = "failure",
    ) -> None:
        self._record_completion(
            actor_type=actor_type,
            actor_id=actor_id,
            action="mcp.tool.call",
            target_type="mcp_tool",
            target_id=target_id,
            correlation_id=correlation_id,
            outcome=outcome,
            reason_code=reason_code,
        )

    def _record_completion_if_available(
        self,
        actor_type: str,
        actor_id: str,
        action: str,
        target_type: str,
        target_id: str,
        correlation_id: str,
        outcome: str,
        reason_code: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._record_completion(
                actor_type=actor_type,
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                correlation_id=correlation_id,
                outcome=outcome,
                reason_code=reason_code,
                metadata=metadata,
            )
        except SecurityAuditUnavailable:
            logger.error("MCP security audit completion could not be persisted")


def _success_result(payload: Any) -> CallToolResult:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, default=str)
    structured = {"text": payload} if isinstance(payload, str) else payload
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=structured if isinstance(structured, dict) else {"result": structured},
        is_error=False,
    )


def _error_result(error: str, message: str, details: Any = None) -> CallToolResult:
    payload = mcp_error_payload(error, message, details=details)
    return CallToolResult(
        content=[TextContent(type="text", text=f"{payload['error']}: {payload['message']}")],
        structured_content=payload,
        is_error=True,
    )


def _bounded_target(value: str) -> str:
    if value and len(value) <= 64 and all(char.isalnum() or char in "_.-" for char in value):
        return value
    return "invalid-tool"


def _bounded_actor(value: str) -> str:
    if value and len(value) <= 128 and all(char.isalnum() or char in "_.:@/-" for char in value):
        return value
    return "unknown-principal"
