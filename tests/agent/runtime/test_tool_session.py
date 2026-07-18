# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed tests for the execution-bound tool session (AR-PY-02).

Every gate must reject with the shared structured error contract and an
audit record; nothing may silently degrade. Race-style scenarios are
built deterministically (handler-driven close / cancellation flips and a
barrier for parallel budget contention) - no sleep-based timing.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.agent.runtime.tool_session import BoundToolSession
from src.agent.stock_scope import StockScope
from src.agent.tool_surface import ToolSurface
from src.agent.tools.execution import ToolAccessContext
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)


def _echo_registry(calls=None, permissions=("test:read",)) -> ToolRegistry:
    recorded = calls if calls is not None else []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=lambda message: recorded.append(message) or {"message": message},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=[],
                permissions=list(permissions),
            ),
        )
    )
    return registry


def _session(registry, **overrides) -> BoundToolSession:
    params = {
        "execution_id": "exec-1",
        "allowed_tools": ["echo"],
        "granted_permissions": ["test:read"],
    }
    params.update(overrides)
    return BoundToolSession(registry, **params)


# ---------------------------------------------------------------------------
# Construction and identity
# ---------------------------------------------------------------------------

def test_session_requires_execution_id():
    with pytest.raises(ValueError):
        BoundToolSession(_echo_registry(), execution_id="  ", allowed_tools=["echo"])


def test_session_freezes_identity_and_allowlist():
    session = _session(
        _echo_registry(),
        stage="technical",
        attempt=2,
        principal="native-runtime",
    )
    assert session.execution_id == "exec-1"
    assert session.stage == "technical"
    assert session.attempt == 2
    assert session.principal == "native-runtime"
    assert session.allowed_tools == frozenset({"echo"})
    assert session.granted_permissions == frozenset({"test:read"})


# ---------------------------------------------------------------------------
# Success parity with the direct surface path
# ---------------------------------------------------------------------------

def test_success_passthrough_matches_direct_surface_result():
    registry = _echo_registry()
    session = _session(registry)

    via_session = session.execute("echo", {"message": "hi"})
    direct = ToolSurface(registry).execute_tool("echo", {"message": "hi"}, ToolAccessContext())

    assert via_session["ok"] is True
    for key in ("ok", "tool_name", "result", "result_text", "error", "diagnostics"):
        assert via_session[key] == direct[key]
    assert session.dispatched_calls == 1


def test_session_audit_carries_execution_identity():
    session = _session(_echo_registry(), stage="intel", attempt=1)
    result = session.execute("echo", {"message": "hi"})
    audit_context = result["audit"]["audit_context"]
    assert "exec-1" in audit_context
    assert "intel" in audit_context


# ---------------------------------------------------------------------------
# Fail-closed gates
# ---------------------------------------------------------------------------

def test_tool_outside_allowlist_is_rejected_without_dispatch():
    calls = []
    session = _session(_echo_registry(calls), allowed_tools=["other_tool"])

    result = session.execute("echo", {"message": "hi"})

    assert result["ok"] is False
    assert result["error"]["code"] == "tool_not_allowed"
    assert result["error"]["retriable"] is False
    assert calls == []
    assert session.dispatched_calls == 0


def test_empty_allowlist_rejects_everything():
    session = _session(_echo_registry(), allowed_tools=[])
    result = session.execute("echo", {"message": "hi"})
    assert result["error"]["code"] == "tool_not_allowed"


def test_allowed_tool_missing_from_registry_is_tool_not_found():
    session = _session(_echo_registry(), allowed_tools=["echo", "ghost"])
    result = session.execute("ghost", {})
    assert result["ok"] is False
    assert result["error"]["code"] == "tool_not_found"


def test_non_string_tool_name_is_invalid():
    session = _session(_echo_registry())
    result = session.execute(None, {})
    assert result["error"]["code"] == "invalid_tool_name"


def test_undeclared_policy_is_rejected():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="legacy",
            description="Tool without declared policy.",
            parameters=[],
            handler=lambda: {"ok": True},
            policy=ToolPolicy.unknown(),
        )
    )
    session = _session(registry, allowed_tools=["legacy"], granted_permissions=[])

    result = session.execute("legacy", {})

    assert result["error"]["code"] == "policy_undeclared"
    assert result["error"]["details"]["policy_status"] == "unknown"


def test_missing_permission_is_rejected_with_details():
    calls = []
    session = _session(
        _echo_registry(calls, permissions=("market_data:read", "intel:read")),
        granted_permissions=["market_data:read"],
    )

    result = session.execute("echo", {"message": "hi"})

    assert result["error"]["code"] == "permission_denied"
    assert result["error"]["details"]["missing_permissions"] == ["intel:read"]
    assert result["error"]["details"]["required_permissions"] == [
        "intel:read",
        "market_data:read",
    ]
    assert calls == []


def test_stock_scope_violation_propagates_through_session():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="quote",
            description="Quote",
            parameters=[
                ToolParameter(name="stock_code", type="string", description="Stock"),
            ],
            handler=lambda stock_code: {"code": stock_code},
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["market_data:read"],
                scope_dimensions=["stock"],
            ),
        )
    )
    session = _session(
        registry,
        allowed_tools=["quote"],
        granted_permissions=["market_data:read"],
        stock_scope=StockScope(expected_stock_code="600519", allowed_stock_codes={"600519"}),
    )

    result = session.execute("quote", {"stock_code": "000001"})

    assert result["ok"] is False
    assert result["error"]["code"] == "stock_scope_violation"


# ---------------------------------------------------------------------------
# Budget, cache, deadline and cancellation
# ---------------------------------------------------------------------------

def test_budget_exhausted_after_max_tool_calls():
    session = _session(_echo_registry(), max_tool_calls=1)

    first = session.execute("echo", {"message": "one"})
    second = session.execute("echo", {"message": "two"})

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error"]["code"] == "budget_exhausted"
    assert second["error"]["details"] == {"max_tool_calls": 1}
    assert session.dispatched_calls == 1


def test_non_retriable_result_is_cached_without_consuming_budget():
    calls = []
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="denied",
            description="Always non-retriable.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=lambda message: calls.append(message)
            or {"error": "denied", "retriable": False},
            policy=ToolPolicy.declared(read_only=True, permissions=["test:read"]),
        )
    )
    session = _session(registry, allowed_tools=["denied"], max_tool_calls=1)

    first = session.execute("denied", {"message": "same"})
    second = session.execute("denied", {"message": "same"})

    assert calls == ["same"]
    assert second is first
    assert session.dispatched_calls == 1


def test_cancellation_token_rejects_before_dispatch():
    calls = []
    session = _session(_echo_registry(calls), cancelled_check=lambda: True)

    result = session.execute("echo", {"message": "hi"})

    assert result["error"]["code"] == "cancelled"
    assert calls == []


def test_elapsed_deadline_rejects_before_dispatch():
    calls = []
    session = _session(_echo_registry(calls), deadline_seconds=0)

    result = session.execute("echo", {"message": "hi"})

    assert result["error"]["code"] == "deadline_exceeded"
    assert calls == []


def test_call_timeout_is_clamped_to_remaining_deadline():
    captured = {}

    class RecordingSurface:
        def execute_tool(self, name, arguments, context):
            captured["context"] = context
            return {
                "ok": True,
                "tool_name": name,
                "result": None,
                "result_text": "{}",
                "error": None,
                "audit": {"tool_name": name},
                "diagnostics": {},
            }

    session = _session(
        _echo_registry(),
        call_timeout_seconds=100.0,
        deadline_seconds=50.0,
        surface=RecordingSurface(),
    )

    assert session.execute("echo", {"message": "hi"})["ok"] is True
    timeout = captured["context"].timeout_seconds
    assert 0 < timeout <= 50.0


def test_max_result_bytes_is_enforced_per_call():
    session = _session(_echo_registry(), max_result_bytes=5)
    result = session.execute("echo", {"message": "a-very-long-message"})
    assert result["diagnostics"]["result_truncated"] is True
    assert len(result["result_text"].encode("utf-8")) <= 5


# ---------------------------------------------------------------------------
# Close and late-result fence
# ---------------------------------------------------------------------------

def test_closed_session_rejects_calls():
    session = _session(_echo_registry())
    session.close()
    result = session.execute("echo", {"message": "hi"})
    assert result["error"]["code"] == "session_closed"


def test_result_completing_after_close_is_dropped():
    registry = ToolRegistry()
    holder = {}

    def closing_handler(message):
        holder["session"].close()
        return {"message": message}

    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo that closes the session mid-flight.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=closing_handler,
            policy=ToolPolicy.declared(read_only=True, permissions=["test:read"]),
        )
    )
    session = _session(registry)
    holder["session"] = session

    result = session.execute("echo", {"message": "secret"})

    assert result["ok"] is False
    assert result["error"]["code"] == "late_result_dropped"
    assert "secret" not in result["result_text"]
    assert session.dropped_results == 1


def test_result_completing_after_cancellation_is_dropped():
    cancelled = {"flag": False}
    registry = ToolRegistry()

    def flipping_handler(message):
        cancelled["flag"] = True
        return {"message": message}

    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo that flips cancellation mid-flight.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=flipping_handler,
            policy=ToolPolicy.declared(read_only=True, permissions=["test:read"]),
        )
    )
    session = _session(
        registry,
        cancelled_check=lambda: cancelled["flag"],
    )

    result = session.execute("echo", {"message": "secret"})

    assert result["error"]["code"] == "late_result_dropped"
    assert session.dropped_results == 1


# ---------------------------------------------------------------------------
# Parallel calls
# ---------------------------------------------------------------------------

def test_parallel_calls_respect_budget_exactly():
    workers = 4
    barrier = threading.Barrier(workers)
    session = _session(_echo_registry(), max_tool_calls=2)

    def contend(index):
        barrier.wait()
        return session.execute("echo", {"message": f"msg-{index}"})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(contend, range(workers)))

    succeeded = [r for r in results if r["ok"]]
    rejected = [r for r in results if not r["ok"]]
    assert len(succeeded) == 2
    assert len(rejected) == 2
    assert {r["error"]["code"] for r in rejected} == {"budget_exhausted"}
    assert session.dispatched_calls == 2


# ---------------------------------------------------------------------------
# Descriptors and audit trail
# ---------------------------------------------------------------------------

def test_describe_tools_only_covers_allowed_registry_tools():
    registry = _echo_registry()
    registry.register(
        ToolDefinition(
            name="hidden",
            description="Not allowed.",
            parameters=[],
            handler=lambda: {},
            policy=ToolPolicy.declared(read_only=True),
        )
    )
    session = _session(registry, allowed_tools=["echo", "ghost"])

    descriptors = session.describe_tools()

    assert [d["name"] for d in descriptors] == ["echo"]
    assert "handler" not in descriptors[0]
    assert descriptors[0]["policy"]["permissions"] == ["test:read"]


def test_audit_trail_records_rejections_and_successes():
    session = _session(_echo_registry(), max_tool_calls=1)

    session.execute("echo", {"message": "ok"})
    session.execute("not_allowed", {})
    session.execute("echo", {"message": "over-budget"})

    trail = session.audit_trail
    assert len(trail) == 3
    assert trail[0]["error_code"] is None
    assert trail[1]["error_code"] == "tool_not_allowed"
    assert trail[2]["error_code"] == "budget_exhausted"
