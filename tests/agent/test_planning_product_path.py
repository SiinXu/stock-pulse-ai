# -*- coding: utf-8 -*-
"""Production-path regression: AgentExecutor.run walks the planning loop (#199)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from src.agent.executor import AgentExecutor, AgentResult
from src.agent.executor_parts.run import _RunMethods
from src.agent.planning.product import (
    is_agent_planning_enabled,
    resolve_planning_settings,
    try_run_with_planning,
)
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)


def _registry_with_tools(names: List[str]) -> ToolRegistry:
    registry = ToolRegistry()
    for name in names:
        registry.register(
            ToolDefinition(
                name=name,
                description=f"test tool {name}",
                parameters=[
                    ToolParameter(
                        name="stock_code",
                        type="string",
                        description="stock",
                        required=False,
                    )
                ],
                handler=lambda stock_code=None, _n=name, **kwargs: {
                    "status": "ok",
                    "tool": _n,
                    "stock_code": stock_code,
                },
                category="data",
                policy=ToolPolicy(permissions=["market_data_read"]),
            )
        )
    return registry


def _enabled_config(**overrides: Any) -> SimpleNamespace:
    base = dict(
        agent_planning_enabled=True,
        agent_planning_strategy="template",
        agent_planning_max_plan_steps=8,
        agent_planning_max_replans=0,
        agent_planning_max_tokens=1500,
        agent_planning_proposal_timeout_seconds=30.0,
        agent_planning_max_total_tool_calls=16,
        agent_planning_max_observation_replans=0,
        agent_planning_exec_timeout_seconds=60.0,
        agent_planning_on_step_failure="terminate",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_default_config_keeps_planning_disabled() -> None:
    cfg = SimpleNamespace(agent_planning_enabled=False)
    assert is_agent_planning_enabled(cfg) is False
    assert try_run_with_planning(MagicMock(), task="x", config=cfg) is None


def test_run_source_gates_on_try_run_with_planning() -> None:
    source = inspect.getsource(_RunMethods.run)
    assert "try_run_with_planning" in source
    assert "AgentExecutor.run" not in source  # method body, not recursive


def test_resolve_settings_reject_non_finite_timeout_via_settings() -> None:
    cfg = _enabled_config(agent_planning_exec_timeout_seconds=float("nan"))
    with pytest.raises(ValueError):
        resolve_planning_settings(cfg)
    cfg = _enabled_config(agent_planning_exec_timeout_seconds=float("inf"))
    with pytest.raises(ValueError):
        resolve_planning_settings(cfg)


def test_agent_executor_run_uses_planning_loop_when_enabled() -> None:
    """Prove the production AgentExecutor.run path enters plan→act→observe."""
    tools = ["get_realtime_quote", "get_daily_history", "analyze_trend", "search_stock_news"]
    registry = _registry_with_tools(tools)
    llm = MagicMock()
    executor = AgentExecutor(registry, llm, max_steps=3)

    session_calls: List[str] = []

    class FakeSession:
        def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            session_calls.append(name)
            return {
                "ok": True,
                "result_text": f"{name}-ok",
                "summary": f"{name}-ok",
            }

        def close(self) -> None:
            return None

    synth = AgentResult(
        success=True,
        content='{"action":"hold"}',
        dashboard={"action": "hold"},
        tool_calls_log=[{"tool": "synth", "ok": True}],
        total_steps=1,
        total_tokens=10,
    )

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=_enabled_config(),
    ), patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=FakeSession(),
    ), patch.object(executor, "_run_loop", return_value=synth) as run_loop:
        result = executor.run("Analyze stock 600519", context={"stock_code": "600519"})

    assert result.success is True
    assert result.planning_metadata is not None
    assert result.planning_metadata.get("product_path") == "agent_executor_run"
    assert result.planning_metadata.get("success") is True
    assert result.planning_metadata.get("proposal_applied") is True
    assert result.planning_metadata.get("tool_call_count", 0) >= 1
    # Real plan-loop tools were invoked (not only synthesis).
    assert session_calls, "plan loop must call BoundToolSession tools"
    assert all(row.get("source") == "plan_loop" for row in result.tool_calls_log if row.get("source"))
    assert any(row.get("source") == "plan_loop" for row in result.tool_calls_log)
    run_loop.assert_called_once()
    # Evidence must be injected into synthesis user message.
    messages = run_loop.call_args.args[0]
    user = next(m for m in messages if m.get("role") == "user")
    assert "Plan execution evidence" in user["content"]


def test_agent_executor_run_terminates_on_tool_failure_without_fail_open() -> None:
    tools = ["get_realtime_quote", "get_daily_history"]
    registry = _registry_with_tools(tools)
    executor = AgentExecutor(registry, MagicMock(), max_steps=3)

    class FailingSession:
        def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            del arguments
            return {"ok": False, "error": {"code": "provider_error", "message": "down"}}

        def close(self) -> None:
            return None

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=_enabled_config(),
    ), patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=FailingSession(),
    ), patch.object(executor, "_run_loop") as run_loop:
        result = executor.run("Analyze 600519", context={"stock_code": "600519"})

    assert result.success is False
    assert result.error and "Plan execution terminated" in result.error
    assert result.planning_metadata is not None
    assert result.planning_metadata.get("success") is False
    assert result.planning_metadata.get("reason") in {
        "step_failed",
        "max_observation_replans_exceeded",
    }
    run_loop.assert_not_called()


def test_disabled_run_path_does_not_enter_planning(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = _registry_with_tools(["get_realtime_quote"])
    executor = AgentExecutor(registry, MagicMock(), max_steps=2)
    classic = AgentResult(success=True, content="classic", total_steps=1)

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=SimpleNamespace(agent_planning_enabled=False),
    ), patch.object(executor, "_run_loop", return_value=classic) as run_loop:
        result = executor.run("Analyze 600519", context={"stock_code": "600519"})

    assert result.success is True
    assert result.planning_metadata is None
    assert result.content == "classic"
    run_loop.assert_called_once()
