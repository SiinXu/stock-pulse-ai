# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed regressions for the standard BoundToolSession double (#1055 T2)."""

from __future__ import annotations

import inspect

import pytest

from src.agent.llm_adapter import ToolCall
from src.agent.runner import _execute_tools
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)
from tests.agent.runtime.bound_tool_session_double import (
    EXECUTE_TOOLS_OBSERVER_REQUIRED_FIELDS,
    STANDARD_BOUND_TOOL_SESSION_FIELDS,
    ExecuteToolsObserverSession,
    make_bound_tool_session,
)
from tests.security_audit_test_utils import SecurityAuditRecorderStub


_TEST_CAPABILITY = "analysis_context:read"


def _echo_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=lambda message: {"message": message},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=[_TEST_CAPABILITY],
            ),
        )
    )
    return registry


def test_standard_double_constructs_real_bound_tool_session():
    session = make_bound_tool_session(_echo_registry())
    assert type(session) is BoundToolSession
    assert session.deadline_monotonic is None
    assert session.execution_id == "test-bound-session"


def test_standard_double_passes_production_required_session_fields(monkeypatch):
    captured: dict = {}
    original = BoundToolSession.__init__

    def wrapped(self, registry, **kwargs):
        captured.update(kwargs)
        return original(self, registry, **kwargs)

    monkeypatch.setattr(BoundToolSession, "__init__", wrapped)
    make_bound_tool_session(_echo_registry())

    missing = set(STANDARD_BOUND_TOOL_SESSION_FIELDS) - captured.keys()
    assert missing == set()
    assert "deadline_monotonic" in captured
    assert "cancelled_check" in captured


def test_standard_double_required_fields_remain_on_production_constructor():
    parameters = inspect.signature(BoundToolSession.__init__).parameters
    missing = [
        name
        for name in STANDARD_BOUND_TOOL_SESSION_FIELDS
        if name not in parameters
    ]
    assert missing == []
    assert parameters["deadline_monotonic"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["cancelled_check"].kind is inspect.Parameter.KEYWORD_ONLY


def test_execute_tools_fails_closed_when_deadline_monotonic_is_omitted():
    class MissingDeadlineSession:
        execution_id = "missing-deadline"
        cancelled_check = None

        @staticmethod
        def is_non_retriable_cached(_cache_key: str) -> bool:
            return False

        @staticmethod
        def execute(*_args, **_kwargs):
            raise AssertionError("must not dispatch without deadline_monotonic")

    with pytest.raises(AttributeError, match="deadline_monotonic"):
        _execute_tools(
            [ToolCall(id="call-1", name="echo", arguments={"message": "nope"})],
            MissingDeadlineSession(),
            step=1,
            progress_callback=None,
            tool_calls_log=[],
        )


def test_standard_double_wires_cancelled_check():
    calls = []

    def _handler(message):
        calls.append(message)
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
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=[_TEST_CAPABILITY],
            ),
        )
    )
    session = make_bound_tool_session(
        registry,
        cancelled_check=lambda: True,
        granted_permissions=[_TEST_CAPABILITY],
        security_audit=SecurityAuditRecorderStub(),
    )

    result = session.execute("echo", {"message": "must-not-run"})

    assert calls == []
    assert result["ok"] is False
    assert result["error"]["code"] == "cancelled"


def test_execute_tools_observer_carries_required_session_fields():
    for name in EXECUTE_TOOLS_OBSERVER_REQUIRED_FIELDS:
        assert name in ExecuteToolsObserverSession.__dataclass_fields__

    observer = ExecuteToolsObserverSession(
        execution_id="observer",
        execute_handler=lambda name, arguments: {"ok": True, "name": name},
    )
    assert observer.deadline_monotonic is None
    assert observer.cancelled_check is None
    assert observer.execution_id == "observer"
