# -*- coding: utf-8 -*-
"""Research / deep-research planning opt-in behind AGENT_PLANNING_ENABLED (#199)."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from src.agent.planning.product import PlanningGatherResult, RESEARCH_PRODUCT_PATH
from src.agent.research import ResearchAgent, research_token_budget_from_config
from src.agent.runtime.mode_budget import create_research_mode_budget_account
from src.agent.tools.registry import (
    ToolDefinition,
    ToolParameter,
    ToolPolicy,
    ToolRegistry,
)


def _registry_with_extra() -> ToolRegistry:
    registry = ToolRegistry()
    for name in ("get_stock_info", "get_realtime_quote", "delete_everything"):
        registry.register(
            ToolDefinition(
                name=name,
                description=name,
                parameters=[
                    ToolParameter(name="message", type="string", description="Message"),
                ],
                handler=lambda message="": {"message": message},
                category="data",
                policy=ToolPolicy.declared(
                    read_only=name != "delete_everything",
                    side_effects=[],
                    permissions=["analysis_context:read"],
                ),
            )
        )
    return registry


def _cfg(**overrides: Any) -> SimpleNamespace:
    values = dict(
        agent_planning_enabled=False,
        agent_mode_budget_enabled=True,
        agent_mode_budget_max_llm_turns=0,
        agent_mode_budget_max_tool_calls=0,
        agent_mode_budget_max_cost_usd=0.0,
        agent_mode_budget_max_tokens=0,
        agent_deep_research_budget=30000,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _agent(cfg: Any, registry: ToolRegistry | None = None) -> ResearchAgent:
    return ResearchAgent(
        tool_registry=registry or _registry_with_extra(),
        llm_adapter=MagicMock(),
        token_budget=cfg.agent_deep_research_budget,
        config=cfg,
    )


def _loop_result(**overrides: Any) -> SimpleNamespace:
    values = dict(
        success=True,
        content="classic-loop",
        total_tokens=4,
        cancelled=False,
        failure_reason=None,
        error=None,
        messages=[],
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_disabled_research_still_calls_run_agent_loop() -> None:
    agent = _agent(_cfg())
    with patch(
        "src.agent.research.run_agent_loop",
        return_value=_loop_result(),
    ) as loop, patch(
        "src.agent.planning.product.try_gather_with_planning",
        return_value=None,
    ) as gather:
        result = agent._research_sub_question(
            "What is the moat?",
            {"stock_code": "600519"},
            0,
            stock_scope=None,
        )
    gather.assert_called_once()
    loop.assert_called_once()
    assert result["success"] is True
    assert result["content"] == "classic-loop"
    assert gather.call_args.kwargs["product_path"] == RESEARCH_PRODUCT_PATH


def test_enabled_research_gather_skips_run_agent_loop() -> None:
    agent = _agent(_cfg(agent_planning_enabled=True))
    gathered = PlanningGatherResult(
        success=True,
        product_path=RESEARCH_PRODUCT_PATH,
        evidence="plan evidence",
        total_tokens=9,
        plan_tool_log=[{"tool": "get_stock_info", "ok": True}],
    )
    with patch(
        "src.agent.research.run_agent_loop",
        return_value=_loop_result(),
    ) as loop, patch(
        "src.agent.planning.product.try_gather_with_planning",
        return_value=gathered,
    ) as gather:
        result = agent._research_sub_question(
            "What is the moat?",
            {"stock_code": "600519"},
            0,
            stock_scope=None,
        )
    loop.assert_not_called()
    gather.assert_called_once()
    assert result["success"] is True
    assert result["content"] == "plan evidence"
    assert result["tokens"] == 9


def test_enabled_research_gather_failure_does_not_fail_open() -> None:
    agent = _agent(_cfg(agent_planning_enabled=True))
    gathered = PlanningGatherResult(
        success=False,
        product_path=RESEARCH_PRODUCT_PATH,
        error="Planning failed: cancelled",
        cancelled=False,
    )
    with patch(
        "src.agent.research.run_agent_loop",
    ) as loop, patch(
        "src.agent.planning.product.try_gather_with_planning",
        return_value=gathered,
    ):
        result = agent._research_sub_question(
            "What is the moat?",
            {},
            0,
            stock_scope=None,
        )
    loop.assert_not_called()
    assert result["success"] is False
    assert "Planning failed" in (result["error"] or "")


def test_enabled_passes_filtered_tools_not_full_registry() -> None:
    agent = _agent(_cfg(agent_planning_enabled=True))
    captured: Dict[str, Any] = {}

    def _capture_gather(*_args: Any, **kwargs: Any) -> PlanningGatherResult:
        captured["tools"] = list(kwargs.get("available_tools") or [])
        captured["product_path"] = kwargs.get("product_path")
        return PlanningGatherResult(
            success=True,
            product_path=RESEARCH_PRODUCT_PATH,
            evidence="ok",
        )

    with patch(
        "src.agent.research.run_agent_loop",
    ) as loop, patch(
        "src.agent.planning.product.try_gather_with_planning",
        side_effect=_capture_gather,
    ):
        agent._research_sub_question("Q", {}, 0, stock_scope=None)

    loop.assert_not_called()
    assert captured["product_path"] == RESEARCH_PRODUCT_PATH
    assert "get_stock_info" in captured["tools"]
    assert "get_realtime_quote" in captured["tools"]
    assert "delete_everything" not in captured["tools"]


def test_constructors_still_mint_the_same_token_ceiling() -> None:
    from src.api.v1.endpoints import agent as agent_endpoint
    from src.bot.commands.research import ResearchCommand
    from src.agent.runtime.native_adapter import NativeRuntimeAdapter as NativeCls

    cfg = _cfg(agent_deep_research_budget=12345)
    assert research_token_budget_from_config(cfg) == 12345
    assert "research_token_budget_from_config" in inspect.getsource(
        agent_endpoint.agent_research
    )
    assert "research_token_budget_from_config" in inspect.getsource(
        ResearchCommand.execute
    )
    assert "research_token_budget_from_config" in inspect.getsource(
        NativeCls._run_research
    )


def test_enabled_tool_cap_records_budget_tools_without_classic_loop() -> None:
    cfg = _cfg(
        agent_planning_enabled=True,
        agent_mode_budget_specialist_max_tool_calls=1,
    )
    agent = _agent(cfg)
    account = create_research_mode_budget_account(cfg, token_budget=30000)
    gathered = PlanningGatherResult(
        success=True,
        product_path=RESEARCH_PRODUCT_PATH,
        evidence="too many tools",
        total_tokens=3,
        plan_tool_log=[
            {"tool": "get_stock_info", "ok": True},
            {"tool": "get_realtime_quote", "ok": True},
        ],
    )
    with patch(
        "src.agent.research.run_agent_loop",
    ) as loop, patch(
        "src.agent.planning.product.try_gather_with_planning",
        return_value=gathered,
    ):
        result = agent._research_sub_question(
            "Q",
            {},
            0,
            stock_scope=None,
            account=account,
        )
    loop.assert_not_called()
    assert result["success"] is False
    assert result["budget_reason"] == "budget_tools"


def test_enabled_turn_cap_records_budget_turns_after_gather() -> None:
    cfg = _cfg(
        agent_planning_enabled=True,
        agent_mode_budget_specialist_max_llm_turns=1,
    )
    agent = _agent(cfg)
    account = create_research_mode_budget_account(cfg, token_budget=30000)
    assert account.record_llm_turn(tokens=10) is None
    # Probe would normally skip the sub-question; this counterexample records
    # a gather that still happened at the last remaining turn.
    account.llm_turns = 0
    gathered = PlanningGatherResult(
        success=True,
        product_path=RESEARCH_PRODUCT_PATH,
        evidence="one turn",
        total_tokens=5,
        plan_tool_log=[],
    )
    with patch(
        "src.agent.research.run_agent_loop",
    ) as loop, patch(
        "src.agent.planning.product.try_gather_with_planning",
        return_value=gathered,
    ):
        result = agent._research_sub_question(
            "Q",
            {},
            0,
            stock_scope=None,
            account=account,
        )
    loop.assert_not_called()
    assert account.llm_turns == 1
    assert result["success"] is True

    second = PlanningGatherResult(
        success=True,
        product_path=RESEARCH_PRODUCT_PATH,
        evidence="second",
        total_tokens=5,
    )
    with patch(
        "src.agent.research.run_agent_loop",
    ) as loop2, patch(
        "src.agent.planning.product.try_gather_with_planning",
        return_value=second,
    ):
        blocked = agent._research_sub_question(
            "Q2",
            {},
            0,
            stock_scope=None,
            account=account,
        )
    loop2.assert_not_called()
    assert blocked["success"] is False
    assert blocked["budget_reason"] == "budget_turns"
