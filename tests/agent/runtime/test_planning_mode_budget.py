# -*- coding: utf-8 -*-
"""Real-layer planning gather vs ModeBudgetAccount counterexamples (Refs #1121)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from src.agent.executor import AgentExecutor, AgentResult
from src.agent.runner import RunLoopResult
from src.agent.runtime.mode_budget import ModeBudgetAccount, ModeBudgetLimits
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


def _planning_budget_config(**overrides: Any) -> SimpleNamespace:
    values: Dict[str, Any] = dict(
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
        agent_mode_budget_enabled=True,
        agent_mode_budget_max_llm_turns=0,
        agent_mode_budget_max_tool_calls=0,
        agent_mode_budget_max_cost_usd=0.0,
        agent_mode_budget_max_tokens=0,
        agent_reflection_enabled=False,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class _SuccessfulSession:
    def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "ok": True,
            "result_text": f"{name}-ok",
            "summary": f"{name}-ok",
        }

    def close(self) -> None:
        return None


_TOOLS = ["get_realtime_quote", "get_daily_history", "analyze_trend"]


def _chat_patches():
    return (
        patch("src.agent.conversation.conversation_manager.get_or_create"),
        patch("src.agent.conversation.conversation_manager.add_user_message"),
        patch("src.agent.conversation.conversation_manager.add_message"),
    )


def test_run_planning_gather_over_tool_cap_terminates_with_budget_tools() -> None:
    executor = AgentExecutor(_registry_with_tools(_TOOLS), MagicMock(), max_steps=3)
    cfg = _planning_budget_config(agent_mode_budget_max_tool_calls=1)

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=cfg,
    ), patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=_SuccessfulSession(),
    ), patch.object(executor, "_run_loop") as run_loop:
        result = executor.run("Analyze stock 600519", context={"stock_code": "600519"})

    run_loop.assert_not_called()
    assert result.success is False
    assert result.failure_reason == "budget_tools"
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["breach"]["reason"] == "budget_tools"
    assert result.budget_snapshot["used"]["tool_calls"] > 1
    assert isinstance(executor.mode_budget_account, ModeBudgetAccount)


def test_run_planning_gather_over_turn_cap_terminates_with_budget_turns() -> None:
    executor = AgentExecutor(_registry_with_tools(_TOOLS), MagicMock(), max_steps=3)
    account = ModeBudgetAccount(
        limits=ModeBudgetLimits(
            mode="chat",
            enabled=True,
            max_llm_turns=1,
            max_tool_calls=24,
            max_cost_usd=0.0,
            max_tokens=0,
        ),
        llm_turns=1,
    )
    executor.mode_budget_account = account
    cfg = _planning_budget_config()

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=cfg,
    ), patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=_SuccessfulSession(),
    ), patch.object(executor, "_run_loop") as run_loop:
        result = executor.run("Analyze stock 600519", context={"stock_code": "600519"})

    run_loop.assert_not_called()
    assert result.success is False
    assert result.failure_reason == "budget_turns"
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["breach"]["reason"] == "budget_turns"
    assert account.llm_turns == 2
    assert executor.mode_budget_account is account


def test_run_planning_synthesis_reuses_gather_account() -> None:
    executor = AgentExecutor(_registry_with_tools(_TOOLS), MagicMock(), max_steps=3)
    cfg = _planning_budget_config()
    synth = AgentResult(success=True, content='{"action":"hold"}', dashboard={"action": "hold"})
    seen: Dict[str, Any] = {}

    def _loop(*_args: Any, **_kwargs: Any) -> AgentResult:
        seen["account"] = executor.mode_budget_account
        seen["llm_turns"] = int(executor.mode_budget_account.llm_turns)
        seen["tool_calls"] = int(executor.mode_budget_account.tool_calls)
        return synth

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=cfg,
    ), patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=_SuccessfulSession(),
    ), patch.object(executor, "_run_loop", side_effect=_loop):
        result = executor.run("Analyze stock 600519", context={"stock_code": "600519"})

    assert result.success is True
    assert seen["account"] is executor.mode_budget_account
    assert seen["llm_turns"] == 1
    assert seen["tool_calls"] >= 1
    assert isinstance(seen["account"], ModeBudgetAccount)


def test_run_planning_disabled_mints_classic_loop_account() -> None:
    executor = AgentExecutor(_registry_with_tools(_TOOLS), MagicMock(), max_steps=3)
    minted: Dict[str, Any] = {}

    def _fake_loop(**kwargs: Any) -> RunLoopResult:
        minted["account"] = kwargs["mode_budget_account"]
        return RunLoopResult(
            success=True,
            content='{"action":"hold"}',
            total_steps=1,
            models_used=["test-model"],
            budget_snapshot=kwargs["mode_budget_account"].snapshot(),
        )

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=_planning_budget_config(agent_planning_enabled=False),
    ), patch(
        "src.agent.executor.run_agent_loop",
        side_effect=_fake_loop,
    ):
        result = executor.run("Analyze stock 600519", context={"stock_code": "600519"})

    assert result.success is True
    assert minted["account"] is executor.mode_budget_account
    assert minted["account"].llm_turns == 0
    assert minted["account"].tool_calls == 0


def test_chat_planning_gather_over_tool_cap_terminates_with_budget_tools() -> None:
    cfg = _planning_budget_config(agent_mode_budget_max_tool_calls=1)
    executor = AgentExecutor(
        _registry_with_tools(_TOOLS),
        MagicMock(),
        max_steps=3,
        config=cfg,
    )
    get_or_create, add_user, add_msg = _chat_patches()
    with get_or_create, add_user, add_msg, patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=_SuccessfulSession(),
    ), patch.object(executor, "_run_loop") as run_loop:
        result = executor.chat("hello", "session-1")

    run_loop.assert_not_called()
    assert result.success is False
    assert result.failure_reason == "budget_tools"
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["breach"]["reason"] == "budget_tools"


def test_chat_planning_gather_over_turn_cap_terminates_with_budget_turns() -> None:
    cfg = _planning_budget_config()
    executor = AgentExecutor(
        _registry_with_tools(_TOOLS),
        MagicMock(),
        max_steps=3,
        config=cfg,
    )
    account = ModeBudgetAccount(
        limits=ModeBudgetLimits(
            mode="chat",
            enabled=True,
            max_llm_turns=1,
            max_tool_calls=24,
            max_cost_usd=0.0,
            max_tokens=0,
        ),
        llm_turns=1,
    )
    executor.mode_budget_account = account
    get_or_create, add_user, add_msg = _chat_patches()
    with get_or_create, add_user, add_msg, patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=_SuccessfulSession(),
    ), patch.object(executor, "_run_loop") as run_loop:
        result = executor.chat("hello", "session-1")

    run_loop.assert_not_called()
    assert result.success is False
    assert result.failure_reason == "budget_turns"
    assert account.llm_turns == 2
    assert executor.mode_budget_account is account


def test_chat_planning_disabled_mints_classic_loop_account() -> None:
    cfg = _planning_budget_config(agent_planning_enabled=False)
    executor = AgentExecutor(
        _registry_with_tools(_TOOLS),
        MagicMock(),
        max_steps=3,
        config=cfg,
    )
    minted: Dict[str, Any] = {}

    def _fake_loop(**kwargs: Any) -> RunLoopResult:
        minted["account"] = kwargs["mode_budget_account"]
        return RunLoopResult(
            success=True,
            content="classic-chat",
            total_steps=1,
            models_used=["test-model"],
            budget_snapshot=kwargs["mode_budget_account"].snapshot(),
        )

    get_or_create, add_user, add_msg = _chat_patches()
    with get_or_create, add_user, add_msg, patch(
        "src.agent.executor.run_agent_loop",
        side_effect=_fake_loop,
    ):
        result = executor.chat("hello", "session-1")

    assert result.success is True
    assert result.content == "classic-chat"
    assert minted["account"] is executor.mode_budget_account
    assert minted["account"].llm_turns == 0


def test_disabled_mode_budget_does_not_fail_close_planning_gather() -> None:
    executor = AgentExecutor(_registry_with_tools(_TOOLS), MagicMock(), max_steps=3)
    cfg = _planning_budget_config(
        agent_mode_budget_enabled=False,
        agent_mode_budget_max_tool_calls=1,
    )
    synth = AgentResult(success=True, content='{"action":"hold"}', dashboard={"action": "hold"})

    with patch(
        "src.agent.planning.product._resolve_config",
        return_value=cfg,
    ), patch(
        "src.agent.planning.product._open_plan_tool_session",
        return_value=_SuccessfulSession(),
    ), patch.object(executor, "_run_loop", return_value=synth) as run_loop:
        result = executor.run("Analyze stock 600519", context={"stock_code": "600519"})

    run_loop.assert_called_once()
    assert result.success is True
    assert result.failure_reason is None
    assert executor.mode_budget_account.limits.enabled is False
