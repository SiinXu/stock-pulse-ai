# -*- coding: utf-8 -*-
"""Compare multi-symbol Chat planning opt-in behind AGENT_PLANNING_ENABLED (#199)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from src.agent.orchestrator import AgentOrchestrator, OrchestratorResult
from src.agent.planning.product import ORCH_CHAT_PRODUCT_PATH, PlanningGatherResult
from src.agent.stock_scope import StockScope, StockScopeResolution


def _orchestrator(*, planning_enabled: bool) -> AgentOrchestrator:
    return AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        mode="quick",
        config=SimpleNamespace(
            agent_orchestrator_timeout_s=0,
            agent_planning_enabled=planning_enabled,
        ),
    )


def _compare_scope() -> StockScope:
    return StockScope(
        expected_stock_code="600519",
        allowed_stock_codes={"600519", "000001"},
        mode="compare",
    )


def _run_compare(orch: AgentOrchestrator) -> OrchestratorResult:
    return orch._execute_multi_symbol_chat(
        message="compare 600519 and 000001",
        session_id="s-compare",
        context={"stock_code": "600519"},
        stock_scope=_compare_scope(),
        history=[],
        market_context=SimpleNamespace(stock_codes=["600519", "000001"], prompt_section=""),
        report_language="zh",
        progress_callback=None,
        cancelled_check=None,
    )


def test_disabled_compare_chat_still_pipelines_each_leg() -> None:
    orch = _orchestrator(planning_enabled=False)
    pipeline_codes: List[str] = []

    def _pipeline(ctx: Any, **_kwargs: Any) -> OrchestratorResult:
        pipeline_codes.append(ctx.stock_code)
        return OrchestratorResult(success=True, content=f"pipe-{ctx.stock_code}")

    with patch(
        "src.agent.planning.product.try_gather_with_planning",
        return_value=None,
    ) as gather, patch.object(
        orch, "_execute_pipeline", side_effect=_pipeline
    ) as pipeline, patch.object(
        orch,
        "_synthesize_multi_symbol_chat",
        return_value=OrchestratorResult(success=True, content="synth"),
    ):
        result = _run_compare(orch)

    assert result.success is True
    assert gather.call_count == 2
    assert pipeline.call_count == 2
    assert pipeline_codes == ["600519", "000001"]
    assert all(
        call.kwargs.get("product_path") == ORCH_CHAT_PRODUCT_PATH
        for call in gather.call_args_list
    )


def test_enabled_compare_chat_gathers_per_symbol_then_pipelines() -> None:
    orch = _orchestrator(planning_enabled=True)
    gathered_contexts: List[Dict[str, Any]] = []
    pipeline_queries: List[str] = []

    def _gather(_owner: Any, **kwargs: Any) -> PlanningGatherResult:
        context = dict(kwargs.get("context") or {})
        gathered_contexts.append(context)
        code = str(context.get("stock_code") or "")
        return PlanningGatherResult(
            success=True,
            product_path=ORCH_CHAT_PRODUCT_PATH,
            evidence=f"evidence-{code}",
            total_tokens=2,
            plan_tool_log=[{"tool": "get_realtime_quote", "ok": True}],
        )

    def _pipeline(ctx: Any, **_kwargs: Any) -> OrchestratorResult:
        pipeline_queries.append(ctx.query)
        return OrchestratorResult(success=True, content=f"pipe-{ctx.stock_code}")

    with patch(
        "src.agent.planning.product.try_gather_with_planning",
        side_effect=_gather,
    ) as gather, patch.object(
        orch, "_execute_pipeline", side_effect=_pipeline
    ) as pipeline, patch.object(
        orch,
        "_synthesize_multi_symbol_chat",
        return_value=OrchestratorResult(success=True, content="synth"),
    ):
        result = _run_compare(orch)

    assert result.success is True
    assert gather.call_count == 2
    assert pipeline.call_count == 2
    assert [ctx["stock_code"] for ctx in gathered_contexts] == ["600519", "000001"]
    assert any("evidence-600519" in query for query in pipeline_queries)
    assert any("evidence-000001" in query for query in pipeline_queries)


def test_enabled_compare_gather_failure_skips_pipeline_for_that_leg() -> None:
    orch = _orchestrator(planning_enabled=True)
    pipeline_codes: List[str] = []

    def _gather(_owner: Any, **kwargs: Any) -> PlanningGatherResult:
        code = str((kwargs.get("context") or {}).get("stock_code") or "")
        if code == "600519":
            return PlanningGatherResult(
                success=False,
                product_path=ORCH_CHAT_PRODUCT_PATH,
                error="Planning failed: cancelled",
            )
        return PlanningGatherResult(
            success=True,
            product_path=ORCH_CHAT_PRODUCT_PATH,
            evidence="ok",
        )

    def _pipeline(ctx: Any, **_kwargs: Any) -> OrchestratorResult:
        pipeline_codes.append(ctx.stock_code)
        return OrchestratorResult(success=True, content=f"pipe-{ctx.stock_code}")

    synthesized: List[Any] = []

    def _synth(**kwargs: Any) -> OrchestratorResult:
        synthesized.append(kwargs["per_symbol_results"])
        return OrchestratorResult(success=True, content="partial-synth")

    with patch(
        "src.agent.planning.product.try_gather_with_planning",
        side_effect=_gather,
    ), patch.object(
        orch, "_execute_pipeline", side_effect=_pipeline
    ) as pipeline, patch.object(
        orch, "_synthesize_multi_symbol_chat", side_effect=_synth
    ):
        result = _run_compare(orch)

    assert result.success is True
    assert pipeline.call_count == 1
    assert pipeline_codes == ["000001"]
    legs = synthesized[0]
    assert legs[0][0] == "600519"
    assert legs[0][1].success is False
    assert "Planning failed" in (legs[0][1].error or "")
    assert legs[1][0] == "000001"
    assert legs[1][1].success is True


def test_incremental_facts_skip_compare_helper_and_planning() -> None:
    orch = _orchestrator(planning_enabled=True)
    scope = StockScope(
        expected_stock_code="600519",
        allowed_stock_codes={"600519"},
        mode="maintain",
    )
    resolution = StockScopeResolution(
        effective_context={"stock_code": "600519"},
        stock_scope=scope,
    )
    loop_result = SimpleNamespace(
        success=True,
        content="quote",
        tool_calls_log=[],
        total_steps=1,
        total_tokens=0,
        provider="",
        model="",
        error=None,
        cancelled=False,
        timed_out=False,
        budget_snapshot=None,
        failure_reason=None,
    )
    with patch.object(
        orch,
        "_execute_pipeline",
        return_value=OrchestratorResult(success=True, content="chat"),
    ) as pipeline, patch.object(
        orch, "_execute_multi_symbol_chat"
    ) as multi, patch(
        "src.agent.orchestrator.resolve_stock_scope",
        return_value=resolution,
    ), patch(
        "src.agent.orchestrator_parts.chat.run_agent_loop",
        return_value=loop_result,
    ), patch(
        "src.agent.planning.product.try_gather_with_planning"
    ) as gather, patch(
        "src.agent.orchestrator.build_visible_chat_history",
        return_value=[],
    ), patch(
        "src.agent.conversation.conversation_manager.get_or_create"
    ), patch(
        "src.agent.conversation.conversation_manager.add_user_message"
    ), patch(
        "src.agent.conversation.conversation_manager.add_message"
    ):
        result = orch.chat(
            "price?",
            "session-1",
            context={"stock_code": "600519", "tool_suitable": True},
        )

    assert multi.call_count == 0
    assert pipeline.call_count == 0
    assert gather.call_count == 0
    assert result.success is True
    assert result.content == "quote"
    assert (result.planning_metadata or {}).get("router_decision", {}).get(
        "chat_path"
    ) == "incremental_tool"
