# -*- coding: utf-8 -*-
"""Multi public AgentResult must keep mode-budget snapshot and reason (Refs #1121)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.agent.orchestrator import AgentOrchestrator, OrchestratorResult
from src.agent.protocols import (
    StageFailureReason,
    StageResult,
    StageStatus,
)
from src.agent.runtime.mode_budget import get_or_create_context_budget_account
from src.agent.runner import RunLoopResult
from src.agent.tools.registry import ToolRegistry


def _budget_snapshot(*, reason: str = "budget_turns") -> dict:
    return {
        "limits": {
            "mode": "standard",
            "enabled": True,
            "max_llm_turns": 1,
            "max_tool_calls": 32,
            "max_cost_usd": 0.5,
            "max_tokens": 0,
        },
        "used": {
            "llm_turns": 2,
            "tool_calls": 0,
            "tokens": 0,
            "cost_usd": 0.0,
            "wall_clock_skips": 0,
        },
        "breach": {
            "reason": reason,
            "message": "LLM turn budget exceeded",
            "used": 2.0,
            "limit": 1.0,
            "dimension": "llm_turns",
            "failure_reason": reason,
        },
    }


def _orchestrator(**config_attrs) -> AgentOrchestrator:
    attrs = {
        "agent_orchestrator_timeout_s": 0,
        "agent_mode_budget_enabled": True,
        "agent_mode_budget_max_llm_turns": 1,
        "agent_mode_budget_max_tool_calls": 0,
        "agent_mode_budget_max_cost_usd": 0.0,
        "agent_mode_budget_max_tokens": 0,
    }
    attrs.update(config_attrs)
    return AgentOrchestrator(
        tool_registry=ToolRegistry(),
        llm_adapter=MagicMock(),
        mode="standard",
        config=SimpleNamespace(**attrs),
    )


def _chat_patches():
    return (
        patch(
            "src.agent.orchestrator.build_visible_chat_history",
            return_value=[],
        ),
        patch("src.agent.conversation.conversation_manager.get_or_create"),
        patch("src.agent.conversation.conversation_manager.add_user_message"),
        patch("src.agent.conversation.conversation_manager.add_message"),
    )


def test_run_wrapper_forwards_budget_exhausted_snapshot_and_reason():
    """Public AgentResult keeps budget_turns after Multi run() aggregation."""
    orch = _orchestrator()
    snapshot = _budget_snapshot()
    pipeline_result = OrchestratorResult(
        success=False,
        content="",
        error="Mode 'standard' LLM turn budget exceeded: 2/1",
        failure_reason=StageFailureReason.BUDGET_TURNS.value,
        budget_snapshot=snapshot,
    )

    with patch.object(orch, "_execute_pipeline", return_value=pipeline_result):
        result = orch.run("Analyze 600519", {"stock_code": "600519"})

    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TURNS
    assert result.budget_snapshot is snapshot
    assert result.budget_snapshot["breach"]["reason"] == "budget_turns"
    assert result.content == ""
    assert result.cancelled is False


def test_chat_wrapper_forwards_budget_exhausted_snapshot_and_reason():
    """Public AgentResult keeps budget_turns after Multi chat() aggregation."""
    orch = _orchestrator()
    snapshot = _budget_snapshot(reason="budget_tools")
    pipeline_result = OrchestratorResult(
        success=False,
        content="",
        error="Mode 'chat' tool-call budget exceeded: 2/1",
        failure_reason=StageFailureReason.BUDGET_TOOLS.value,
        budget_snapshot=snapshot,
    )
    history, get_or_create, add_user, add_message = _chat_patches()
    with history, get_or_create, add_user, add_message:
        with patch.object(orch, "_execute_pipeline", return_value=pipeline_result):
            result = orch.chat("hello", "budget-chat")

    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TOOLS
    assert result.budget_snapshot is snapshot
    assert result.budget_snapshot["breach"]["reason"] == "budget_tools"


def test_run_wrapper_absent_budget_metadata_stays_unset():
    """Callers without budget metadata keep None fields and success ordering."""
    orch = _orchestrator()
    pipeline_result = OrchestratorResult(success=True, content="done")

    with patch.object(orch, "_execute_pipeline", return_value=pipeline_result):
        result = orch.run("Analyze 600519", {"stock_code": "600519"})

    assert result.success is True
    assert result.content == "done"
    assert result.budget_snapshot is None
    assert result.failure_reason is None


def test_chat_wrapper_absent_budget_metadata_stays_unset():
    orch = _orchestrator()
    pipeline_result = OrchestratorResult(success=True, content="assistant reply")
    history, get_or_create, add_user, add_message = _chat_patches()
    with history, get_or_create, add_user, add_message:
        with patch.object(orch, "_execute_pipeline", return_value=pipeline_result):
            result = orch.chat("hello", "no-budget-chat")

    assert result.success is True
    assert result.content == "assistant reply"
    assert result.budget_snapshot is None
    assert result.failure_reason is None


def test_run_pipeline_hard_budget_reaches_public_agent_result():
    """Counterexample: intel budget_turns fail-fast is visible on AgentResult."""
    orch = _orchestrator()
    ran = []

    def _run_stage(agent, ctx, **_kwargs):
        ran.append(agent.agent_name)
        if agent.agent_name != "intel":
            return StageResult(
                stage_name=agent.agent_name,
                status=StageStatus.COMPLETED,
            )
        account = get_or_create_context_budget_account(
            ctx, orch.config, mode=orch.mode
        )
        account.record_llm_turn()
        account.record_llm_turn()
        return StageResult(
            stage_name="intel",
            status=StageStatus.FAILED,
            error="Mode 'standard' LLM turn budget exceeded: 2/1",
            failure_reason=StageFailureReason.BUDGET_TURNS,
        )

    with patch.object(orch, "_run_stage_agent", side_effect=_run_stage):
        result = orch.run("Analyze 600519", {"stock_code": "600519"})

    assert "intel" in ran
    assert "decision" not in ran
    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TURNS
    assert result.budget_snapshot is not None
    assert result.budget_snapshot["breach"]["reason"] == "budget_turns"
    assert result.budget_snapshot["used"]["llm_turns"] >= 2


def test_multi_symbol_cancelled_result_keeps_leg_budget_snapshot():
    snapshot = _budget_snapshot()
    cancelled = AgentOrchestrator._build_multi_symbol_cancelled_result(
        [
            (
                "AAPL",
                OrchestratorResult(
                    success=False,
                    cancelled=True,
                    error="Pipeline cancelled",
                    budget_snapshot=snapshot,
                    failure_reason=StageFailureReason.BUDGET_TURNS.value,
                ),
            )
        ]
    )

    assert cancelled.cancelled is True
    assert cancelled.success is False
    assert cancelled.budget_snapshot is snapshot
    assert cancelled.failure_reason == StageFailureReason.BUDGET_TURNS


def test_multi_symbol_cancelled_without_budget_metadata_stays_unset():
    cancelled = AgentOrchestrator._build_multi_symbol_cancelled_result(
        [("AAPL", OrchestratorResult(success=False, cancelled=True))]
    )
    assert cancelled.cancelled is True
    assert cancelled.success is False
    assert cancelled.budget_snapshot is None
    assert cancelled.failure_reason is None


def test_multi_symbol_synthesis_keeps_budget_exhausted_leg_observable():
    orch = _orchestrator()
    snapshot = _budget_snapshot()
    exhausted = OrchestratorResult(
        success=False,
        error="Mode 'chat' LLM turn budget exceeded: 2/1",
        failure_reason=StageFailureReason.BUDGET_TURNS.value,
        budget_snapshot=snapshot,
    )

    result = orch._synthesize_multi_symbol_chat(
        message="Compare AAPL and MSFT",
        market_context=SimpleNamespace(prompt_section="Market context"),
        report_language="en",
        per_symbol_results=[
            ("AAPL", exhausted),
            ("MSFT", exhausted),
        ],
        cancelled_check=None,
        timeout_seconds=None,
    )

    assert result.success is False
    assert result.failure_reason == StageFailureReason.BUDGET_TURNS
    assert result.budget_snapshot is snapshot
    assert result.budget_snapshot["breach"]["reason"] == "budget_turns"


def test_multi_symbol_synthesis_success_keeps_snapshot_without_flipping_success():
    """A successful comparison stays successful; a leg snapshot remains visible."""
    orch = _orchestrator()
    snapshot = _budget_snapshot()
    exhausted = OrchestratorResult(
        success=False,
        error="Mode 'chat' LLM turn budget exceeded: 2/1",
        failure_reason=StageFailureReason.BUDGET_TURNS.value,
        budget_snapshot=snapshot,
    )
    ok = OrchestratorResult(success=True, content="MSFT evidence")

    with patch(
        "src.agent.orchestrator.run_agent_loop",
        return_value=RunLoopResult(success=True, content="comparison"),
    ):
        result = orch._synthesize_multi_symbol_chat(
            message="Compare AAPL and MSFT",
            market_context=SimpleNamespace(prompt_section="Market context"),
            report_language="en",
            per_symbol_results=[
                ("AAPL", exhausted),
                ("MSFT", ok),
            ],
            cancelled_check=None,
            timeout_seconds=None,
        )

    assert result.success is True
    assert "comparison" in result.content
    assert result.failure_reason is None
    assert result.budget_snapshot is snapshot
    assert result.budget_snapshot["breach"]["reason"] == "budget_turns"


def test_run_does_not_invent_budget_fields_on_router_rejection():
    orch = _orchestrator()
    with patch(
        "src.agent.runtime.agent_router_facts.project_router_request",
        return_value=SimpleNamespace(accepted=False, request=None),
    ):
        result = orch.run("Analyze 600519")

    assert result.success is False
    assert result.budget_snapshot is None
    assert result.failure_reason is None
