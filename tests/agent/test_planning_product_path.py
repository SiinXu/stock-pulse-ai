# -*- coding: utf-8 -*-
"""Production-path regression: AgentExecutor.run walks the planning loop (#199)."""

from __future__ import annotations

import inspect
import json
import os
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
from src.config import Config
from src.services.security_audit_service import get_security_audit_service
from src.storage import DatabaseManager


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
                        required=True,
                    )
                ],
                handler=lambda stock_code=None, _n=name, **kwargs: {
                    "status": "ok",
                    "tool": _n,
                    "stock_code": stock_code,
                },
                category="data",
                policy=ToolPolicy.declared(
                    read_only=True,
                    side_effects=[],
                    permissions=["analysis_context:read"],
                    scope_dimensions=["stock"],
                ),
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


class _SuccessfulSession:
    def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": True,
            "result_text": f"{name}-ok",
            "summary": f"{name}-ok",
        }

    def close(self) -> None:
        return None


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


@pytest.mark.parametrize(
    ("field_name", "raw_value"),
    [
        ("AGENT_PLANNING_PROPOSAL_TIMEOUT_SECONDS", "nan"),
        ("AGENT_PLANNING_PROPOSAL_TIMEOUT_SECONDS", "inf"),
        ("AGENT_PLANNING_PROPOSAL_TIMEOUT_SECONDS", "-inf"),
        ("AGENT_PLANNING_EXEC_TIMEOUT_SECONDS", "nan"),
        ("AGENT_PLANNING_EXEC_TIMEOUT_SECONDS", "inf"),
        ("AGENT_PLANNING_EXEC_TIMEOUT_SECONDS", "-inf"),
    ],
)
@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_config_loader_rejects_non_finite_planning_timeouts(
    _mock_groups: MagicMock,
    _mock_litellm: MagicMock,
    _mock_setup_env: MagicMock,
    field_name: str,
    raw_value: str,
) -> None:
    with patch.dict(
        os.environ,
        {"STOCK_LIST": "600519", field_name: raw_value},
        clear=True,
    ):
        with pytest.raises(ValueError, match=field_name):
            Config._load_from_env()


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

    assert result.success is True, result.tool_calls_log
    assert result.planning_metadata is not None
    assert result.planning_metadata.get("product_path") == "agent_executor_run"
    assert result.planning_metadata.get("success") is True
    assert result.planning_metadata.get("proposal_applied") is True
    assert result.planning_metadata.get("tool_call_count", 0) >= 1
    trace_events = result.planning_metadata.get("trace_events")
    assert isinstance(trace_events, list) and trace_events
    assert trace_events[0]["kind"] == "plan"
    assert trace_events[-1]["kind"] == "terminate"
    assert {
        event["run_id"] for event in trace_events
    } == {result.planning_metadata.get("planning_run_id")}
    # Real plan-loop tools were invoked (not only synthesis).
    assert session_calls, "plan loop must call BoundToolSession tools"
    assert all(row.get("source") == "plan_loop" for row in result.tool_calls_log if row.get("source"))
    assert any(row.get("source") == "plan_loop" for row in result.tool_calls_log)
    run_loop.assert_called_once()
    # Evidence must be injected into synthesis user message.
    messages = run_loop.call_args.args[0]
    user = next(m for m in messages if m.get("role") == "user")
    assert "Plan execution evidence" in user["content"]


def test_product_path_calls_real_reflection_adapter_with_trajectory_evidence() -> None:
    tools = ["get_realtime_quote", "get_daily_history", "analyze_trend"]
    llm = MagicMock()
    llm.call_completion.return_value = SimpleNamespace(
        provider="test",
        content=json.dumps(
            {
                "lessons": [
                    {
                        "kind": "evidence_gap",
                        "severity": "medium",
                        "remedy": "fetch another source",
                    }
                ],
                "revised": False,
            }
        ),
    )
    executor = AgentExecutor(_registry_with_tools(tools), llm, max_steps=3)
    synth = AgentResult(
        success=True,
        content='{"action":"hold"}',
        dashboard={"action": "hold"},
        total_steps=1,
    )

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=_enabled_config(
            agent_step_critique_enabled=True,
            agent_reflection_enabled=True,
            agent_reflection_llm_budget=1,
            agent_reflection_in_chat=False,
        ),
    ), patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=_SuccessfulSession(),
    ), patch.object(executor, "_run_loop", return_value=synth):
        result = executor.run("Analyze stock 600519", context={"stock_code": "600519"})

    assert result.success is True
    llm.call_completion.assert_called_once()
    messages = llm.call_completion.call_args.args[0]
    reflection_user = next(row["content"] for row in messages if row["role"] == "user")
    assert '"run_success": true' in reflection_user
    assert '"trajectory_summary"' in reflection_user
    reflection = result.planning_metadata["reflection_result"]
    assert reflection["status"] == "completed"
    assert reflection["validation_status"] == "valid"
    assert reflection["lessons"][0]["kind"] == "evidence_gap"


def test_reflection_provider_failure_is_explicit_without_changing_run_success() -> None:
    tools = ["get_realtime_quote", "get_daily_history", "analyze_trend"]
    llm = MagicMock()
    llm.call_completion.side_effect = RuntimeError("provider unavailable")
    executor = AgentExecutor(_registry_with_tools(tools), llm, max_steps=3)
    synth = AgentResult(
        success=True,
        content='{"action":"hold"}',
        dashboard={"action": "hold"},
        total_steps=1,
    )

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=_enabled_config(
            agent_reflection_enabled=True,
            agent_reflection_llm_budget=1,
            agent_reflection_in_chat=False,
        ),
    ), patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=_SuccessfulSession(),
    ), patch.object(executor, "_run_loop", return_value=synth):
        result = executor.run("Analyze stock 600519", context={"stock_code": "600519"})

    assert result.success is True
    reflection = result.planning_metadata["reflection_result"]
    assert reflection["status"] == "error"
    assert reflection["validation_status"] == "error"
    assert reflection["lessons"] == []
    assert "RuntimeError" in reflection["skip_reason"]


def test_agent_executor_run_uses_real_bound_session_and_durable_audit(tmp_path) -> None:
    """Exercise the production permission and SQLite audit gates without mocks."""
    DatabaseManager.reset_instance()
    DatabaseManager(f"sqlite:///{tmp_path / 'planning-product-audit.sqlite'}")
    try:
        tools = [
            "get_realtime_quote",
            "get_daily_history",
            "analyze_trend",
            "search_stock_news",
        ]
        executor = AgentExecutor(_registry_with_tools(tools), MagicMock(), max_steps=3)
        synth = AgentResult(
            success=True,
            content='{"action":"hold"}',
            dashboard={"action": "hold"},
            total_steps=1,
        )

        with patch(
            "src.agent.planning.product._resolve_config",
            return_value=_enabled_config(),
        ), patch.object(executor, "_run_loop", return_value=synth):
            result = executor.run(
                "Analyze stock 600519",
                context={"stock_code": "600519"},
            )

        audit_page = get_security_audit_service().list_events(
            page=1,
            page_size=100,
            event_type="tool.execute",
        )
    finally:
        DatabaseManager.reset_instance()

    assert result.success is True, result.tool_calls_log
    assert any(row.get("source") == "plan_loop" for row in result.tool_calls_log)
    assert audit_page.total >= 2
    assert {event.phase for event in audit_page.items} == {"attempt", "completion"}
    assert all(event.target.type == "tool" for event in audit_page.items)


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
