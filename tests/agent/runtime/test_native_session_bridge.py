# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""RF-03: native runner routes every tool call through one bound session.

These tests characterize the migration bridge that is *not* exercised by the
36 replay fixtures (none of which hit the non-retriable cache or the stock
scope guard) and prove the native path now has a single tool authority:

* the runner builds one native-compatibility ``BoundToolSession`` per run,
  reuses it across steps and closes it at the terminal state;
* the migration mapper reproduces the legacy runner 6-tuple, including the
  ``cached`` flag and the reconstructed ``guard_result`` used by the tool log;
* unknown tools and post-close late results fail closed through the session.

Race scenarios are handler/event driven (no sleep-based ordering).
"""

from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock, patch

from src.agent import runner as runner_module
from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.runner import run_agent_loop
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.stock_scope import StockScope
from src.agent.tools.execution import (
    execute_runner_tool_call_via_session,
    serialize_tool_result,
)
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)
from src.plugins import build_agent_tool_extension_registry


class _TC:
    """Minimal runner tool-call stand-in."""

    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments
        self.id = f"tc_{name}"


def _native_session(registry: ToolRegistry, **overrides) -> BoundToolSession:
    params = {
        "execution_id": "native-bridge-test",
        "allowed_tools": registry.list_names(),
        "enforce_access_policy": False,
    }
    params.update(overrides)
    return BoundToolSession(registry, **params)


def _quote_registry(recorded=None) -> ToolRegistry:
    calls = recorded if recorded is not None else []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_realtime_quote",
            description="Realtime quote",
            parameters=[ToolParameter(name="stock_code", type="string", description="Stock")],
            handler=lambda stock_code: calls.append(stock_code) or {"stock_code": stock_code, "price": 1.0},
        )
    )
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo",
            parameters=[ToolParameter(name="message", type="string", description="Message")],
            handler=lambda message: {"echo": message},
        )
    )
    return registry


def _dashboard_response() -> LLMResponse:
    return LLMResponse(
        content=json.dumps({"decision_type": "hold", "stock_name": "x"}),
        tool_calls=[],
        usage={"total_tokens": 5},
        provider="openai",
        model="gpt-4o-mini",
    )


# ---------------------------------------------------------------------------
# Single authority: one session per run, reused and closed
# ---------------------------------------------------------------------------

def test_native_run_dispatches_every_tool_through_one_bound_session():
    registry = _quote_registry()
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="q1", name="get_realtime_quote", arguments={"stock_code": "600519"})],
            usage={"total_tokens": 3},
            provider="openai",
        ),
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="e1", name="echo", arguments={"message": "hi"})],
            usage={"total_tokens": 3},
            provider="openai",
        ),
        _dashboard_response(),
    ]

    seen_sessions = []
    real_mapper = execute_runner_tool_call_via_session

    def _spy(tool_call, session):
        seen_sessions.append(session)
        return real_mapper(tool_call, session)

    with patch.object(runner_module, "execute_runner_tool_call_via_session", new=_spy):
        result = run_agent_loop(
            messages=[{"role": "user", "content": "go"}],
            tool_registry=registry,
            llm_adapter=adapter,
            max_steps=5,
        )

    assert result.success
    # Two tool calls across two steps, all through the same session instance.
    assert len(seen_sessions) == 2
    assert seen_sessions[0] is seen_sessions[1]
    assert isinstance(seen_sessions[0], BoundToolSession)
    # Terminal state closed the session (late-result fence armed).
    assert seen_sessions[0].closed is True


# ---------------------------------------------------------------------------
# Mapper: cached flag (uncovered by the 36 fixtures)
# ---------------------------------------------------------------------------

def test_mapper_reports_cached_on_repeated_non_retriable_call():
    registry = ToolRegistry()
    handler_calls = []
    registry.register(
        ToolDefinition(
            name="denied",
            description="Non-retriable",
            parameters=[ToolParameter(name="stock_code", type="string", description="Stock")],
            handler=lambda stock_code: handler_calls.append(stock_code)
            or {"error": "denied", "retriable": False},
        )
    )
    session = _native_session(registry)
    tc = _TC("denied", {"stock_code": "600519"})

    _, first_str, first_ok, _, first_cached, first_guard = execute_runner_tool_call_via_session(tc, session)
    _, second_str, second_ok, _, second_cached, second_guard = execute_runner_tool_call_via_session(tc, session)

    # First call runs the handler successfully; the repeat is a cache skip that
    # the runner reports as non-success (legacy direct-path parity).
    assert first_ok is True
    assert first_cached is False
    assert second_ok is False
    assert second_cached is True
    assert first_str == second_str
    assert first_guard is None and second_guard is None
    # The memo prevented a second handler invocation.
    assert handler_calls == ["600519"]


# ---------------------------------------------------------------------------
# Mapper: guard_result reconstruction (uncovered by the 36 fixtures)
# ---------------------------------------------------------------------------

def test_mapper_reconstructs_guard_result_on_scope_violation():
    registry = _quote_registry()
    session = _native_session(
        registry,
        stock_scope=StockScope(expected_stock_code="600519", allowed_stock_codes={"600519"}),
    )
    tc = _TC("get_realtime_quote", {"stock_code": "AAPL"})

    _, res_str, ok, _, cached, guard_result = execute_runner_tool_call_via_session(tc, session)

    assert ok is False
    assert cached is False
    assert guard_result is not None
    assert guard_result["requested_stock_code"] == "AAPL"
    assert guard_result["expected_stock_code"] == "600519"
    assert guard_result["allowed_stock_codes"] == ["600519"]
    # res_str is byte-identical to the legacy serialization of the guard dict.
    assert res_str == serialize_tool_result(
        {
            "error": "stock_scope_violation",
            "expected_stock_code": "600519",
            "requested_stock_code": "AAPL",
            "allowed_stock_codes": ["600519"],
            "retriable": False,
        }
    )


def test_mapper_drops_guard_result_on_cached_scope_violation():
    registry = _quote_registry()
    session = _native_session(
        registry,
        stock_scope=StockScope(expected_stock_code="600519", allowed_stock_codes={"600519"}),
    )
    tc = _TC("get_realtime_quote", {"stock_code": "AAPL"})

    execute_runner_tool_call_via_session(tc, session)
    _, _, ok, _, cached, guard_result = execute_runner_tool_call_via_session(tc, session)

    # On the cached repeat the runner log carries no guarded fields, exactly
    # like the legacy direct path (guard_result is None when cached).
    assert ok is False
    assert cached is True
    assert guard_result is None


# ---------------------------------------------------------------------------
# Fail-closed through the session at the native entry point
# ---------------------------------------------------------------------------

def test_native_run_unknown_tool_fails_closed_via_session():
    registry = _quote_registry()
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="u1", name="get_fundamental_report", arguments={"stock_code": "600519"})],
            usage={"total_tokens": 3},
            provider="openai",
        ),
        _dashboard_response(),
    ]

    result = run_agent_loop(
        messages=[{"role": "user", "content": "go"}],
        tool_registry=registry,
        llm_adapter=adapter,
        max_steps=5,
    )

    assert result.success
    assert result.tool_calls_log[0]["success"] is False
    tool_messages = [m for m in result.messages if m.get("role") == "tool"]
    assert json.loads(tool_messages[0]["content"]) == {
        "error": "Tool not found.",
        "code": "tool_not_found",
        "retriable": False,
    }


def test_native_run_enforces_plugin_tool_schema_before_handler():
    registry = ToolRegistry()
    calls = []
    tool = ToolDefinition(
        name="bounded_plugin_tool",
        description="Bounded plugin tool",
        parameters=[
            ToolParameter(
                name="value",
                type="integer",
                description="Bounded value",
                maximum=1,
            )
        ],
        handler=lambda value: calls.append(value) or {"value": value},
        policy=ToolPolicy.declared(read_only=True),
        enforce_contract=True,
    )
    extension_registry = build_agent_tool_extension_registry(registry)
    extension_registry.register(
        plugin_id="test.bounded-tool",
        extension_point="agent_tool",
        registration_id=tool.name,
        implementation=tool,
    )
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    id="bounded-1",
                    name=tool.name,
                    arguments={"value": 2},
                )
            ],
            usage={"total_tokens": 3},
            provider="openai",
        ),
        _dashboard_response(),
    ]

    result = run_agent_loop(
        messages=[{"role": "user", "content": "go"}],
        tool_registry=registry,
        llm_adapter=adapter,
        max_steps=5,
    )

    assert result.success is True
    assert result.tool_calls_log[0]["success"] is False
    tool_messages = [m for m in result.messages if m.get("role") == "tool"]
    assert json.loads(tool_messages[0]["content"])["code"] == "invalid_arguments"
    assert calls == []


def test_mapper_drops_result_completing_after_session_close():
    """Event-driven late-result fence through the native mapper (no sleep)."""
    registry = ToolRegistry()
    holder = {}
    entered = threading.Event()
    may_return = threading.Event()

    def blocking_handler(stock_code):
        entered.set()
        may_return.wait(timeout=5)
        return {"stock_code": stock_code, "secret": "LATE_SECRET"}

    registry.register(
        ToolDefinition(
            name="get_realtime_quote",
            description="Blocks until released",
            parameters=[ToolParameter(name="stock_code", type="string", description="Stock")],
            handler=blocking_handler,
        )
    )
    session = _native_session(registry)
    holder["session"] = session
    tc = _TC("get_realtime_quote", {"stock_code": "600519"})

    out = {}

    def _dispatch():
        out["tuple"] = execute_runner_tool_call_via_session(tc, session)

    worker = threading.Thread(target=_dispatch)
    worker.start()
    entered.wait(timeout=5)
    session.close()  # terminal reached while the handler is still in flight
    may_return.set()
    worker.join(timeout=5)

    _, res_str, ok, _, cached, _ = out["tuple"]
    assert ok is False
    assert cached is False
    assert "LATE_SECRET" not in res_str
    assert json.loads(res_str)["code"] == "late_result_dropped"
    assert session.dropped_results == 1
