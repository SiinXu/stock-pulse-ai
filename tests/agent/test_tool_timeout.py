# -*- coding: utf-8 -*-
"""Deterministic contract tests for per-category Agent tool timeouts (#1423)."""

from __future__ import annotations

import logging
import math
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from src.agent.llm_adapter import LLMResponse, ToolCall
from src.agent.runner import run_agent_loop
from src.agent.runtime.guards import (
    RuntimeGuardPolicy,
    StageFailurePolicy,
    resolve_category_tool_timeouts,
    shortest_positive_timeout,
)
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
    normalize_tool_timeout_category,
)
from src.config_parts.parsers import parse_optional_category_tool_timeout
from tests.security_audit_test_utils import SecurityAuditRecorderStub


CATEGORY_KEYS = (
    ("data", "AGENT_DATA_TOOL_TIMEOUT_S", "agent_data_tool_timeout_s"),
    ("search", "AGENT_SEARCH_TOOL_TIMEOUT_S", "agent_search_tool_timeout_s"),
    ("analysis", "AGENT_ANALYSIS_TOOL_TIMEOUT_S", "agent_analysis_tool_timeout_s"),
    ("action", "AGENT_ACTION_TOOL_TIMEOUT_S", "agent_action_tool_timeout_s"),
)


def _policy(**overrides):
    values = {
        "tool_timeout_seconds": 120.0,
        "max_identical_tool_calls": 3,
        "max_stage_entries": 1,
        "stage_failure_policy": StageFailurePolicy.ISOLATE,
    }
    values.update(overrides)
    return RuntimeGuardPolicy(**values)


def _register_echo(registry: ToolRegistry, *, name: str, category: str, handler):
    registry.register(
        ToolDefinition(
            name=name,
            description=f"Echo via {category}",
            parameters=[
                ToolParameter(
                    name="message",
                    type="string",
                    description="Message to echo",
                )
            ],
            handler=handler,
            category=category,
            policy=ToolPolicy.declared(
                read_only=True,
                permissions=["analysis_context:read"],
            ),
        )
    )
    return registry


def _run_named_tools(registry, calls, *, global_timeout=1.0, wall_clock=None):
    adapter = MagicMock()
    adapter.call_with_tools.side_effect = [
        LLMResponse(
            content="use tools",
            tool_calls=[
                ToolCall(id=f"call-{item['name']}", name=item["name"], arguments={"message": item["name"]})
                for item in calls
            ],
            provider="test",
        ),
        LLMResponse(content="done", provider="test"),
    ]
    return run_agent_loop(
        messages=[],
        tool_registry=registry,
        llm_adapter=adapter,
        max_steps=3,
        max_wall_clock_seconds=wall_clock,
        runtime_guard_policy=_policy(tool_timeout_seconds=global_timeout),
    )


def test_normalize_market_category_uses_data_bucket():
    assert normalize_tool_timeout_category("market") == "data"
    assert normalize_tool_timeout_category("DATA") == "data"
    assert normalize_tool_timeout_category("unknown") is None


def test_shortest_positive_timeout_ignores_zero_and_nonfinite():
    assert shortest_positive_timeout(0, None, float("nan"), -1, 5, 2.5) == 2.5
    assert shortest_positive_timeout(0, None, float("inf")) is None


@pytest.mark.parametrize("raw", ["", None, "0", "0.0"])
def test_optional_category_timeout_zero_or_unset(raw):
    assert parse_optional_category_tool_timeout(raw, field_name="AGENT_DATA_TOOL_TIMEOUT_S") == 0.0


@pytest.mark.parametrize("raw", ["abc", "nan", "inf", "-1", "-0.5"])
def test_optional_category_timeout_invalid_degrades_to_zero(raw, caplog):
    with caplog.at_level(logging.WARNING):
        assert parse_optional_category_tool_timeout(raw, field_name="AGENT_DATA_TOOL_TIMEOUT_S") == 0.0
    assert any("AGENT_DATA_TOOL_TIMEOUT_S" in record.getMessage() for record in caplog.records)


def test_config_load_degrades_invalid_category_timeouts(monkeypatch, caplog):
    from src.config import Config

    monkeypatch.setenv("AGENT_DATA_TOOL_TIMEOUT_S", "nope")
    monkeypatch.setenv("AGENT_SEARCH_TOOL_TIMEOUT_S", "nan")
    monkeypatch.setenv("AGENT_ANALYSIS_TOOL_TIMEOUT_S", "inf")
    monkeypatch.setenv("AGENT_ACTION_TOOL_TIMEOUT_S", "-8")
    with caplog.at_level(logging.WARNING):
        config = Config._load_from_env()
    assert config.agent_data_tool_timeout_s == 0.0
    assert config.agent_search_tool_timeout_s == 0.0
    assert math.isfinite(config.agent_analysis_tool_timeout_s)
    assert config.agent_analysis_tool_timeout_s == 0.0
    assert config.agent_action_tool_timeout_s == 0.0
    messages = [record.getMessage() for record in caplog.records]
    for key in (
        "AGENT_DATA_TOOL_TIMEOUT_S",
        "AGENT_SEARCH_TOOL_TIMEOUT_S",
        "AGENT_ANALYSIS_TOOL_TIMEOUT_S",
        "AGENT_ACTION_TOOL_TIMEOUT_S",
    ):
        assert any(key in message for message in messages), key


def test_config_load_preserves_positive_and_zero_category_timeouts(monkeypatch):
    from src.config import Config

    monkeypatch.setenv("AGENT_DATA_TOOL_TIMEOUT_S", "12.5")
    monkeypatch.setenv("AGENT_SEARCH_TOOL_TIMEOUT_S", "0")
    monkeypatch.delenv("AGENT_ANALYSIS_TOOL_TIMEOUT_S", raising=False)
    monkeypatch.setenv("AGENT_ACTION_TOOL_TIMEOUT_S", "3")
    config = Config._load_from_env()
    assert config.agent_data_tool_timeout_s == 12.5
    assert config.agent_search_tool_timeout_s == 0.0
    assert config.agent_analysis_tool_timeout_s == 0.0
    assert config.agent_action_tool_timeout_s == 3.0


def test_resolve_category_tool_timeouts_from_config_and_env(monkeypatch):
    monkeypatch.setenv("AGENT_DATA_TOOL_TIMEOUT_S", "9")
    monkeypatch.setenv("AGENT_SEARCH_TOOL_TIMEOUT_S", "bad")
    resolved = resolve_category_tool_timeouts()
    assert resolved["data"] == 9.0
    assert resolved["search"] == 0.0
    from_config = resolve_category_tool_timeouts(
        SimpleNamespace(
            agent_data_tool_timeout_s=1.5,
            agent_search_tool_timeout_s=0,
            agent_analysis_tool_timeout_s=4,
            agent_action_tool_timeout_s=0,
        )
    )
    assert from_config["data"] == 1.5
    assert from_config["analysis"] == 4.0
    assert from_config["search"] == 0.0


def test_registry_category_map_and_market_alias():
    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 11, "search": 0, "analysis": 7, "action": 2})
    _register_echo(registry, name="quote", category="market", handler=lambda message: {"echo": message})
    _register_echo(registry, name="web", category="search", handler=lambda message: {"echo": message})
    assert registry.category_timeout_seconds("market") == 11.0
    assert registry.category_timeout_seconds("data") == 11.0
    assert registry.category_timeout_seconds("search") == 0.0
    assert registry.category_timeout_seconds("other") == 0.0


def test_get_tool_registry_loads_category_map_and_refreshes_cache(monkeypatch):
    from src.agent import factory, runtime_assembly

    original = runtime_assembly._TOOL_REGISTRY
    original_building = runtime_assembly._TOOL_REGISTRY_BUILDING
    state = {"data": 21.0, "search": 0.0, "analysis": 8.0, "action": 5.0}

    def _fake_config():
        return SimpleNamespace(
            agent_data_tool_timeout_s=state["data"],
            agent_search_tool_timeout_s=state["search"],
            agent_analysis_tool_timeout_s=state["analysis"],
            agent_action_tool_timeout_s=state["action"],
        )

    monkeypatch.setattr("src.config.get_config", _fake_config)
    runtime_assembly._TOOL_REGISTRY = None
    runtime_assembly._TOOL_REGISTRY_BUILDING = None
    try:
        registry = runtime_assembly.get_tool_registry()
        assert registry.category_timeouts()["data"] == 21.0
        assert registry.category_timeouts()["search"] == 0.0
        assert registry.category_timeouts()["analysis"] == 8.0
        assert registry.category_timeouts()["action"] == 5.0
        assert runtime_assembly.get_tool_registry() is registry
        state["data"] = 4.0
        same = runtime_assembly.get_tool_registry()
        assert same is registry
        assert same.category_timeouts()["data"] == 4.0
        assert factory.apply_tool_category_timeouts is runtime_assembly.apply_tool_category_timeouts
    finally:
        runtime_assembly._TOOL_REGISTRY = original
        runtime_assembly._TOOL_REGISTRY_BUILDING = original_building


@pytest.mark.parametrize("category,env_name,_attr", CATEGORY_KEYS)
def test_positive_category_cap_times_out_only_that_category(category, env_name, _attr):
    registry = ToolRegistry()
    registry.set_category_timeouts({category: 0.05})
    timed = []
    kept = []

    def _slow(message):
        timed.append(message)
        time.sleep(0.2)
        return {"echo": message}

    def _fastish(message):
        kept.append(message)
        return {"echo": message}

    _register_echo(registry, name="capped", category=category, handler=_slow)
    other = "search" if category != "search" else "data"
    _register_echo(registry, name="other", category=other, handler=_fastish)

    result = _run_named_tools(
        registry,
        [{"name": "capped"}, {"name": "other"}],
        global_timeout=1.0,
    )
    logs = {entry["tool"]: entry for entry in result.tool_calls_log}
    assert logs["capped"]["timeout"] is True
    assert logs["capped"]["success"] is False
    assert "timeout" not in logs["other"]
    assert logs["other"]["success"] is True


def test_zero_and_unset_category_caps_keep_global_timeout():
    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 0, "search": 0, "analysis": 0, "action": 0})
    _register_echo(
        registry,
        name="slow",
        category="data",
        handler=lambda message: time.sleep(0.08) or {"echo": message},
    )
    result = _run_named_tools(registry, [{"name": "slow"}], global_timeout=0.02)
    assert result.tool_calls_log[0]["timeout"] is True
    assert result.tool_calls_log[0]["success"] is False

    registry.set_category_timeouts({})
    result = _run_named_tools(registry, [{"name": "slow"}], global_timeout=1.0)
    assert "timeout" not in result.tool_calls_log[0]
    assert result.tool_calls_log[0]["success"] is True


def test_market_tools_use_data_category_timeout():
    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 0.04})
    _register_echo(
        registry,
        name="indices",
        category="market",
        handler=lambda message: time.sleep(0.15) or {"echo": message},
    )
    result = _run_named_tools(registry, [{"name": "indices"}], global_timeout=1.0)
    assert result.tool_calls_log[0]["timeout"] is True
    assert result.tool_calls_log[0]["success"] is False


def test_shortest_budget_wins_between_category_global_and_remaining():
    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 2.0})
    _register_echo(
        registry,
        name="slow",
        category="data",
        handler=lambda message: time.sleep(0.12) or {"echo": message},
    )
    global_wins = _run_named_tools(registry, [{"name": "slow"}], global_timeout=0.04)
    assert global_wins.tool_calls_log[0]["timeout"] is True

    registry.set_category_timeouts({"data": 0.04})
    category_wins = _run_named_tools(registry, [{"name": "slow"}], global_timeout=2.0)
    assert category_wins.tool_calls_log[0]["timeout"] is True

    registry.set_category_timeouts({"data": 2.0})
    remaining_wins = _run_named_tools(
        registry,
        [{"name": "slow"}],
        global_timeout=2.0,
        wall_clock=0.04,
    )
    assert remaining_wins.timed_out is True or remaining_wins.tool_calls_log[0].get("timeout") is True


def test_category_timeout_late_result_cannot_become_success_or_cache():
    handler_calls = []
    first_handler_started = threading.Event()
    release_first_handler = threading.Event()
    late_completion_recorded = threading.Event()

    class _LateCompletionAudit(SecurityAuditRecorderStub):
        def record_completion(self, **fields):
            super().record_completion(**fields)
            if fields.get("reason_code") == "late_result_dropped":
                late_completion_recorded.set()

    def _handler(message):
        handler_calls.append(message)
        if len(handler_calls) == 1:
            first_handler_started.set()
            assert release_first_handler.wait(timeout=2)
            return {"error": "late failure", "retriable": False}
        return {"echo": message}

    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 0.08})
    _register_echo(registry, name="echo", category="data", handler=_handler)
    responses = iter(
        [
            LLMResponse(
                content="first",
                tool_calls=[ToolCall(id="first", name="echo", arguments={"message": "same"})],
                provider="test",
            ),
            LLMResponse(
                content="second",
                tool_calls=[ToolCall(id="second", name="echo", arguments={"message": "same"})],
                provider="test",
            ),
            LLMResponse(content="done", provider="test"),
        ]
    )
    adapter = MagicMock()

    def _next_response(*_args, **_kwargs):
        response = next(responses)
        if response.content == "second":
            assert first_handler_started.wait(timeout=1)
            release_first_handler.set()
            assert late_completion_recorded.wait(timeout=1)
        return response

    adapter.call_with_tools.side_effect = _next_response
    with patch(
        "src.agent.runner._get_security_audit_service",
        return_value=_LateCompletionAudit(),
    ):
        result = run_agent_loop(
            messages=[],
            tool_registry=registry,
            llm_adapter=adapter,
            max_steps=4,
            runtime_guard_policy=_policy(tool_timeout_seconds=5.0),
        )

    assert result.success is True
    assert late_completion_recorded.is_set()
    assert handler_calls == ["same", "same"]
    assert result.tool_calls_log[0]["timeout"] is True
    assert result.tool_calls_log[0]["success"] is False
    assert result.tool_calls_log[1]["success"] is True
    assert result.tool_calls_log[1]["cached"] is False


def test_unknown_category_does_not_inherit_data_cap():
    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 0.04})
    _register_echo(
        registry,
        name="misc",
        category="custom",
        handler=lambda message: time.sleep(0.12) or {"echo": message},
    )
    result = _run_named_tools(registry, [{"name": "misc"}], global_timeout=2.0)
    assert "timeout" not in result.tool_calls_log[0]
    assert result.tool_calls_log[0]["success"] is True


def test_mixed_deadlines_keep_long_success_when_short_times_out():
    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 0.05, "search": 0})
    _register_echo(
        registry,
        name="short",
        category="data",
        handler=lambda message: time.sleep(0.2) or {"echo": message},
    )
    _register_echo(
        registry,
        name="long",
        category="search",
        handler=lambda message: {"echo": message},
    )
    result = _run_named_tools(
        registry,
        [{"name": "short"}, {"name": "long"}],
        global_timeout=2.0,
    )
    logs = {entry["tool"]: entry for entry in result.tool_calls_log}
    assert logs["short"]["timeout"] is True
    assert logs["short"]["success"] is False
    assert logs["long"]["success"] is True
    assert "timeout" not in logs["long"]


def test_mixed_deadlines_reversed_completion_order_still_fences_late_short():
    short_started = threading.Event()
    long_finished = threading.Event()

    def short_handler(message):
        short_started.set()
        assert long_finished.wait(timeout=2)
        time.sleep(0.2)
        return {"echo": message, "late": True}

    def long_handler(message):
        assert short_started.wait(timeout=2)
        long_finished.set()
        return {"echo": message}

    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 0.05, "search": 0})
    _register_echo(registry, name="short", category="data", handler=short_handler)
    _register_echo(registry, name="long", category="search", handler=long_handler)
    result = _run_named_tools(
        registry,
        [{"name": "long"}, {"name": "short"}],
        global_timeout=2.0,
    )
    logs = {entry["tool"]: entry for entry in result.tool_calls_log}
    assert logs["long"]["success"] is True
    assert "timeout" not in logs["long"]
    assert logs["short"]["timeout"] is True
    assert logs["short"]["success"] is False
    assert '"late": true' not in str(result.messages).lower()


def test_in_flight_session_ignores_live_registry_timeout_refresh():
    started = threading.Event()
    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 0.05})

    def handler(message):
        started.set()
        registry.set_category_timeouts({"data": 0, "search": 0, "analysis": 0, "action": 0})
        time.sleep(0.2)
        return {"echo": message}

    _register_echo(registry, name="slow", category="data", handler=handler)
    result = _run_named_tools(registry, [{"name": "slow"}], global_timeout=2.0)
    assert started.is_set()
    assert result.tool_calls_log[0]["timeout"] is True
    assert result.tool_calls_log[0]["success"] is False


def test_new_session_uses_refreshed_registry_timeouts():
    registry = ToolRegistry()
    _register_echo(
        registry,
        name="slow",
        category="data",
        handler=lambda message: time.sleep(0.12) or {"echo": message},
    )
    registry.set_category_timeouts({"data": 0.04})
    first = _run_named_tools(registry, [{"name": "slow"}], global_timeout=2.0)
    assert first.tool_calls_log[0]["timeout"] is True
    registry.set_category_timeouts({"data": 0})
    second = _run_named_tools(registry, [{"name": "slow"}], global_timeout=2.0)
    assert "timeout" not in second.tool_calls_log[0]
    assert second.tool_calls_log[0]["success"] is True


def test_bound_session_freezes_category_timeout_snapshot():
    from src.agent.runtime.tool_session import BoundToolSession

    registry = ToolRegistry()
    registry.set_category_timeouts({"data": 9})
    _register_echo(
        registry,
        name="echo",
        category="data",
        handler=lambda message: {"echo": message},
    )
    session = BoundToolSession(
        registry,
        execution_id="session-freeze",
        allowed_tools=["echo"],
        derive_granted_permissions=True,
        security_audit=SecurityAuditRecorderStub(),
    )
    registry.set_category_timeouts({"data": 1})
    assert session.category_timeout_seconds("echo") == 9.0
    with pytest.raises(TypeError):
        session._category_timeouts["data"] = 0  # type: ignore[index]


def test_runtime_guard_policy_reads_category_timeouts(monkeypatch):
    monkeypatch.setenv("AGENT_DATA_TOOL_TIMEOUT_S", "6")
    monkeypatch.setenv("AGENT_SEARCH_TOOL_TIMEOUT_S", "0")
    monkeypatch.setenv("AGENT_ANALYSIS_TOOL_TIMEOUT_S", "not-a-number")
    monkeypatch.setenv("AGENT_ACTION_TOOL_TIMEOUT_S", "-2")
    policy = RuntimeGuardPolicy.from_sources()
    assert policy.category_timeouts["data"] == 6.0
    assert policy.category_timeouts["search"] == 0.0
    assert policy.category_timeouts["analysis"] == 0.0
    assert policy.category_timeouts["action"] == 0.0
