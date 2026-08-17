# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Issue #1077: registry → ToolSurface deny-by-default convergence.

These tests drive the real authz / timeout / audit layers. They do not mock
ToolSurface, BoundToolSession gates, or ``build_tool_audit``.
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from src.agent.executor import AgentExecutor
from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.runner import run_agent_loop
from src.agent.tools.execution import ToolAccessContext
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)
from src.agent.tools.surface import (
    NEW_TOOL_CHECKLIST,
    ToolSurface,
    tool_surface_dispatch_authorized,
)


_CAPABILITY = "analysis_context:read"


def _policy() -> ToolPolicy:
    return ToolPolicy.declared(
        read_only=True,
        side_effects=[],
        permissions=[_CAPABILITY],
    )


def _authorized_context(**values) -> ToolAccessContext:
    return ToolAccessContext(
        granted_capabilities=frozenset({_CAPABILITY}),
        **values,
    )


def _echo_registry(calls=None) -> ToolRegistry:
    recorded = calls if calls is not None else []

    def _handler(message: str) -> dict:
        recorded.append(
            {
                "message": message,
                "surface_authorized": tool_surface_dispatch_authorized(),
            }
        )
        return {"message": message}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=_handler,
            policy=_policy(),
        )
    )
    return registry


def test_new_tool_checklist_covers_required_risk_fields() -> None:
    assert NEW_TOOL_CHECKLIST == (
        "permission",
        "timeout",
        "audit",
        "hitl_need",
    )


def test_canonical_and_compatibility_imports_are_the_same_class() -> None:
    from src.agent.tool_surface import ToolSurface as CompatSurface
    from src.agent.tools import ToolSurface as PackageSurface

    assert CompatSurface is ToolSurface
    assert PackageSurface is ToolSurface


def test_registered_authorized_call_runs_handler_under_surface_authority() -> None:
    calls = []
    result = ToolSurface(_echo_registry(calls)).execute_tool(
        "echo",
        {"message": "hello"},
        _authorized_context(backend="native", session_id="s-1077"),
    )

    assert result["ok"] is True
    assert result["result"] == {"message": "hello"}
    assert result["audit"]["tool_name"] == "echo"
    assert result["audit"]["backend"] == "native"
    assert result["audit"]["session_id"] == "s-1077"
    assert result["audit"]["error_code"] is None
    assert calls == [{"message": "hello", "surface_authorized": True}]


def test_unregistered_tool_is_denied_before_any_handler() -> None:
    calls = []
    result = ToolSurface(_echo_registry(calls)).execute_tool(
        "not_registered",
        {"message": "nope"},
        _authorized_context(),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "tool_not_found"
    assert result["audit"]["error_code"] == "tool_not_found"
    assert calls == []


def test_unauthorized_tool_is_denied_before_handler() -> None:
    calls = []
    result = ToolSurface(_echo_registry(calls)).execute_tool(
        "echo",
        {"message": "blocked"},
        ToolAccessContext(),
    )

    assert result["error"]["code"] == "permission_denied"
    assert result["error"]["details"]["missing_capabilities"] == [_CAPABILITY]
    assert result["audit"]["error_code"] == "permission_denied"
    assert calls == []


def test_timeout_denies_before_handler_completes() -> None:
    calls = []

    def _slow() -> dict:
        calls.append({"surface_authorized": tool_surface_dispatch_authorized()})
        time.sleep(0.4)
        return {"done": True}

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="slow",
            description="Slow",
            parameters=[],
            handler=_slow,
            policy=_policy(),
        )
    )

    started = time.time()
    result = ToolSurface(registry).execute_tool(
        "slow",
        {},
        _authorized_context(timeout_seconds=0.01),
    )

    assert result["error"]["code"] == "timeout"
    assert result["audit"]["error_code"] == "timeout"
    assert time.time() - started < 0.2


def test_implementation_failure_is_audited_handler_error() -> None:
    def _boom() -> dict:
        raise RuntimeError("secret-failure-token")

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="boom",
            description="Boom",
            parameters=[],
            handler=_boom,
            policy=_policy(),
        )
    )

    result = ToolSurface(registry).execute_tool(
        "boom",
        {},
        _authorized_context(),
    )

    assert result["error"]["code"] == "handler_error"
    assert result["audit"]["error_code"] == "handler_error"
    visible = json.dumps(result, ensure_ascii=False)
    assert "secret-failure-token" not in visible
    assert "Traceback" not in visible


def test_registry_execute_bypass_is_rejected_and_does_not_run_handler() -> None:
    calls = []
    registry = _echo_registry(calls)

    with pytest.raises(RuntimeError, match="direct_tool_execution_disabled"):
        registry.execute("echo", message="bypass")

    assert calls == []


def test_executor_cannot_invoke_registry_execute_bypass() -> None:
    calls = []
    executor = AgentExecutor(_echo_registry(calls), MagicMock(), max_steps=1)

    with pytest.raises(RuntimeError, match="direct_tool_execution_disabled"):
        executor.tool_registry.execute("echo", message="executor-bypass")

    assert calls == []


def test_executor_run_denies_unregistered_tool_through_real_surface(
    monkeypatch,
) -> None:
    from tests.security_audit_test_utils import SecurityAuditRecorderStub

    monkeypatch.setattr(
        "src.agent.runner._get_security_audit_service",
        lambda: SecurityAuditRecorderStub(),
    )
    calls = []
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="ghost-1",
                    name="ghost_transfer",
                    arguments={"amount": 1},
                )
            ],
            usage={"total_tokens": 2},
            provider="openai",
        ),
        LLMResponse(
            content=json.dumps({"decision_type": "hold", "stock_name": "test"}),
            tool_calls=[],
            usage={"total_tokens": 2},
            provider="openai",
        ),
    ]

    result = AgentExecutor(
        _echo_registry(calls),
        adapter,
        max_steps=2,
    ).run("call an unregistered tool", context={"stock_code": "AAPL"})

    assert result.tool_calls_log[0]["success"] is False
    tool_messages = [item for item in result.messages if item.get("role") == "tool"]
    assert tool_messages
    denied = json.loads(tool_messages[0]["content"])
    assert denied["code"] in {"tool_not_found", "tool_not_allowed", "invalid_tool_name"}
    assert calls == []


def test_runner_authorized_dispatch_sets_surface_token(monkeypatch) -> None:
    from tests.security_audit_test_utils import SecurityAuditRecorderStub

    calls = []
    monkeypatch.setattr(
        "src.agent.runner._get_security_audit_service",
        lambda: SecurityAuditRecorderStub(),
    )
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(id="echo-1", name="echo", arguments={"message": "via-runner"})
            ],
            usage={"total_tokens": 2},
            provider="openai",
        ),
        LLMResponse(
            content=json.dumps({"decision_type": "hold", "stock_name": "test"}),
            tool_calls=[],
            usage={"total_tokens": 2},
            provider="openai",
        ),
    ]

    result = run_agent_loop(
        messages=[{"role": "user", "content": "echo"}],
        tool_registry=_echo_registry(calls),
        llm_adapter=adapter,
        max_steps=2,
    )

    assert result.tool_calls_log[0]["success"] is True
    assert calls == [{"message": "via-runner", "surface_authorized": True}]


def test_direct_handler_call_is_outside_surface_authority() -> None:
    """Documented deferred bypass: plugin contract tests still call handlers.

    Production dispatch must set the ToolSurface token. A bare handler call
    does not, so tests can detect the gap without breaking issue #539.
    """
    calls = []
    registry = _echo_registry(calls)
    handler = registry.get("echo").handler

    assert handler is not None
    assert handler(message="raw") == {"message": "raw"}
    assert calls == [{"message": "raw", "surface_authorized": False}]
