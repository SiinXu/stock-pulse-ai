# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regression coverage for applying AgentRouter once per AgentOrchestrator.run()."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.orchestrator import AgentOrchestrator, OrchestratorResult
from src.agent.orchestrator_parts.chat import (
    _ROUTER_DECISION_META_KEY,
    _build_chat_router_facts,
    _build_dashboard_run_router_facts,
)
from src.agent.public_contract import (
    AGENT_CHAT_FAILURE_MESSAGE,
    AGENT_EXECUTION_FAILURE_MESSAGE,
)
from src.agent.runtime.agent_router import AgentRouter
from src.agent.runtime.agent_router_facts import (
    RouterFactProjection,
    project_router_request,
)
from src.agent.stock_scope import StockScope, StockScopeResolution


def _orchestrator(mode="quick"):
    return AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        mode=mode,
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
    )


STAGE_CHAIN_BY_MODE = {
    "quick": ("technical", "decision"),
    "standard": ("technical", "intel", "decision"),
    "full": ("technical", "intel", "risk", "decision"),
    "specialist": ("technical", "intel", "risk", "decision"),
}


def test_dashboard_run_facts_use_stock_scope_without_env_or_report_type():
    scope = StockScope(
        expected_stock_code="600519",
        allowed_stock_codes={"600519"},
        mode="maintain",
    )
    resolution = StockScopeResolution(
        effective_context={"stock_code": "600519", "report_type": "full"},
        stock_scope=scope,
    )
    facts = _build_dashboard_run_router_facts(
        resolution,
        {
            "stock_code": "600519",
            "report_type": "full",
            "skills": ["x"],
            "AGENT_ORCHESTRATOR_MODE": "full",
        },
    )
    assert facts == {
        "entry_kind": "run",
        "scope_mode": "maintain",
        "allowed_stock_codes": ("600519",),
        "expected_stock_code": "600519",
    }
    assert "user_mode_override" not in facts
    assert "report_type" not in facts
    assert "skills" not in facts


def test_dashboard_run_facts_pass_through_explicit_per_run_override_only():
    resolution = StockScopeResolution(effective_context={}, stock_scope=None)
    facts = _build_dashboard_run_router_facts(
        resolution,
        {"user_mode_override": "full", "agent_orchestrator_mode": "quick"},
        constructor_mode="quick",
    )
    assert facts["entry_kind"] == "run"
    assert facts["user_mode_override"] == "full"
    assert "agent_orchestrator_mode" not in facts


def test_dashboard_run_facts_use_constructor_mode_when_context_has_no_override():
    resolution = StockScopeResolution(effective_context={}, stock_scope=None)
    facts = _build_dashboard_run_router_facts(
        resolution,
        {"stock_code": "600519", "agent_orchestrator_mode": "full"},
        constructor_mode="quick",
    )
    assert facts["user_mode_override"] == "quick"
    assert "agent_orchestrator_mode" not in facts


def test_run_applies_router_once_and_restores_constructor_mode():
    orch = _orchestrator("quick")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        captured["budget_mode"] = orch.mode_budget_limits.mode
        captured["stages"] = tuple(
            agent.agent_name for agent in orch._build_agent_chain(ctx)
        )
        return OrchestratorResult(success=True, content="ok")

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute) as pipeline:
        with patch(
            "src.agent.runtime.agent_router_facts.project_router_request",
            wraps=project_router_request,
        ) as projector:
            result = orch.run("analyze", {"stock_code": "600519"})

    assert result.success is True
    assert result.content == "ok"
    assert pipeline.call_count == 1
    assert projector.call_count == 1
    assert captured["mode"] == "quick"
    assert captured["budget_mode"] == "quick"
    assert captured["stages"] == STAGE_CHAIN_BY_MODE["quick"]
    assert orch.mode == "quick"
    assert orch.mode_budget_limits.mode == "quick"
    assert result.error is None


@pytest.mark.parametrize("mode", ("quick", "standard", "full", "specialist"))
def test_run_constructor_mode_keeps_factory_stage_chain(mode):
    """Omitted-intent single-symbol RUN must not rewire factory/Settings depth."""
    orch = _orchestrator(mode)
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        captured["stages"] = tuple(
            agent.agent_name for agent in orch._build_agent_chain(ctx)
        )
        return OrchestratorResult(success=True)

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run("analyze", {"stock_code": "600519"})

    assert result.success is True
    assert captured["mode"] == mode
    assert captured["stages"] == STAGE_CHAIN_BY_MODE[mode]
    assert orch.mode == mode
    assert orch.mode_budget_limits.mode == mode


def test_run_compare_scope_keeps_constructor_mode_then_restores():
    """Compare/multi-symbol floors must not discard factory depth on dashboard run()."""
    orch = _orchestrator("quick")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        captured["stages"] = tuple(
            agent.agent_name for agent in orch._build_agent_chain(ctx)
        )
        return OrchestratorResult(success=True)

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run(
            "compare 600519 and 000001",
            {"stock_code": "600519"},
        )

    assert result.success is True
    assert captured["mode"] == "quick"
    assert captured["stages"] == STAGE_CHAIN_BY_MODE["quick"]
    assert orch.mode == "quick"


def test_library_compare_floor_still_full_without_constructor_mode():
    """Slices 1–2: compare without a user mode still floors to full at the library."""
    resolution = StockScopeResolution(
        effective_context={},
        stock_scope=StockScope(
            expected_stock_code="600519",
            allowed_stock_codes={"600519", "000001"},
            mode="compare",
        ),
    )
    facts = _build_dashboard_run_router_facts(resolution, {})
    assert "user_mode_override" not in facts
    projection = project_router_request(facts)
    assert projection.accepted is True
    decision = AgentRouter().route(projection.request)
    assert decision.accepted is True
    assert decision.mode == "full"


def test_run_explicit_override_wins_for_this_run_only():
    orch = _orchestrator("standard")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        captured["stages"] = tuple(
            agent.agent_name for agent in orch._build_agent_chain(ctx)
        )
        return OrchestratorResult(success=True)

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run(
            "analyze",
            {"stock_code": "600519", "user_mode_override": "specialist"},
        )

    assert result.success is True
    assert captured["mode"] == "specialist"
    assert captured["stages"] == STAGE_CHAIN_BY_MODE["specialist"]
    assert orch.mode == "standard"


def test_run_does_not_copy_process_wide_env_as_override(monkeypatch):
    monkeypatch.setenv("AGENT_ORCHESTRATOR_MODE", "full")
    orch = _orchestrator("quick")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        return OrchestratorResult(success=True)

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run("analyze", {"stock_code": "600519"})

    assert os.environ["AGENT_ORCHESTRATOR_MODE"] == "full"
    assert result.success is True
    assert captured["mode"] == "quick"
    assert orch.mode == "quick"


def test_run_projection_failure_is_fail_closed_and_restores_mode():
    orch = _orchestrator("full")
    rejected = RouterFactProjection(
        accepted=False,
        request=None,
        reason_code="unknown_field",
        error="Request contains unknown classification fields.",
        error_field="request",
    )
    with patch(
        "src.agent.runtime.agent_router_facts.project_router_request",
        return_value=rejected,
    ) as projector:
        with patch.object(orch, "_execute_pipeline") as pipeline:
            result = orch.run("analyze", {"stock_code": "600519"})

    assert result.success is False
    assert result.error == AGENT_EXECUTION_FAILURE_MESSAGE
    assert result.content == ""
    assert pipeline.call_count == 0
    assert projector.call_count == 1
    assert orch.mode == "full"
    assert "unknown_field" not in (result.error or "")
    assert "stock_code" not in (result.error or "")


def test_run_routing_failure_is_fail_closed_and_restores_mode():
    orch = _orchestrator("quick")
    with patch.object(orch, "_execute_pipeline") as pipeline:
        result = orch.run(
            "analyze",
            {"stock_code": "600519", "user_mode_override": "not-a-mode"},
        )

    assert result.success is False
    assert result.error == AGENT_EXECUTION_FAILURE_MESSAGE
    assert pipeline.call_count == 0
    assert orch.mode == "quick"


def test_run_restores_constructor_mode_after_pipeline_exception():
    orch = _orchestrator("quick")
    configured_budget = orch.mode_budget_limits

    def boom(_ctx, **_kwargs):
        assert orch.mode == "quick"
        raise RuntimeError("pipeline exploded")

    with patch.object(orch, "_execute_pipeline", side_effect=boom):
        with pytest.raises(RuntimeError, match="pipeline exploded"):
            orch.run("analyze", {"stock_code": "600519"})

    assert orch.mode == "quick"
    assert orch.mode_budget_limits is configured_budget


def test_run_restores_constructor_mode_after_projection_exception():
    orch = _orchestrator("full")
    with patch(
        "src.agent.runtime.agent_router_facts.project_router_request",
        side_effect=RuntimeError("projection exploded"),
    ):
        with patch.object(orch, "_execute_pipeline") as pipeline:
            with pytest.raises(RuntimeError, match="projection exploded"):
                orch.run("analyze", {"stock_code": "600519"})

    assert pipeline.call_count == 0
    assert orch.mode == "full"


def _router_decision(result_or_meta):
    if isinstance(result_or_meta, dict):
        return result_or_meta.get(_ROUTER_DECISION_META_KEY)
    metadata = getattr(result_or_meta, "planning_metadata", None) or {}
    return metadata.get(_ROUTER_DECISION_META_KEY)


def test_run_records_secret_free_decision_on_ctx_meta_and_result():
    orch = _orchestrator("quick")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        captured["decision"] = dict(ctx.meta[_ROUTER_DECISION_META_KEY])
        return OrchestratorResult(success=True, content="ok")

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute) as pipeline:
        result = orch.run("analyze", {"stock_code": "600519"})

    assert pipeline.call_count == 1
    assert captured["mode"] == "quick"
    assert orch.mode == "quick"
    decision = captured["decision"]
    assert decision["accepted"] is True
    assert decision["mode"] == "quick"
    assert decision["chat_path"] == "full_repipeline"
    assert decision["reason_code"] == "explicit_override"
    assert "miss_rate" not in decision
    assert "miss_rate" not in decision["explain"]
    assert _router_decision(result) == decision


def test_run_explicit_override_records_applied_specialist_decision():
    orch = _orchestrator("standard")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["decision"] = dict(ctx.meta[_ROUTER_DECISION_META_KEY])
        return OrchestratorResult(success=True)

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run(
            "analyze",
            {"stock_code": "600519", "user_mode_override": "specialist"},
        )

    decision = captured["decision"]
    assert decision["mode"] == "specialist"
    assert decision["reason_code"] == "explicit_override"
    assert decision["explain"]["override_present"] is True
    assert _router_decision(result) == decision
    assert orch.mode == "standard"


def test_run_invalid_override_attaches_rejected_decision_without_leaking_raw_value():
    orch = _orchestrator("quick")
    with patch.object(orch, "_execute_pipeline") as pipeline:
        result = orch.run(
            "analyze",
            {"stock_code": "600519", "user_mode_override": "not-a-mode"},
        )

    assert pipeline.call_count == 0
    assert result.success is False
    assert result.error == AGENT_EXECUTION_FAILURE_MESSAGE
    decision = _router_decision(result)
    assert decision["accepted"] is False
    assert decision["reason_code"] == "invalid_override"
    assert decision["mode"] is None
    assert decision["chat_path"] is None
    dumped = repr(result.planning_metadata)
    assert "not-a-mode" not in dumped
    assert "not-a-mode" not in (result.error or "")


def test_run_projection_unknown_field_attaches_rejected_decision_without_key_names():
    orch = _orchestrator("full")
    rejected = RouterFactProjection(
        accepted=False,
        request=None,
        reason_code="unknown_field",
        error="Request contains unknown classification fields.",
        error_field="request",
    )
    with patch(
        "src.agent.runtime.agent_router_facts.project_router_request",
        return_value=rejected,
    ):
        with patch.object(orch, "_execute_pipeline") as pipeline:
            result = orch.run("analyze", {"stock_code": "600519"})

    assert pipeline.call_count == 0
    assert result.error == AGENT_EXECUTION_FAILURE_MESSAGE
    decision = _router_decision(result)
    assert decision["accepted"] is False
    assert decision["reason_code"] == "unknown_field"
    assert decision["explain"]["error_field"] == "request"
    dumped = repr(result.planning_metadata)
    assert "stock_code" not in dumped
    assert "unknown_field" not in (result.error or "")


def test_run_merges_router_decision_onto_preexisting_planning_metadata():
    orch = _orchestrator("quick")

    def fake_execute(_ctx, **_kwargs):
        return OrchestratorResult(
            success=True,
            planning_metadata={"preexisting": True},
        )

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run("analyze", {"stock_code": "600519"})

    metadata = result.planning_metadata or {}
    assert metadata["preexisting"] is True
    assert metadata[_ROUTER_DECISION_META_KEY]["accepted"] is True
    assert metadata[_ROUTER_DECISION_META_KEY]["mode"] == "quick"


def test_run_compare_scope_records_applied_constructor_mode_not_library_floor():
    orch = _orchestrator("quick")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["decision"] = dict(ctx.meta[_ROUTER_DECISION_META_KEY])
        return OrchestratorResult(success=True)

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run(
            "compare 600519 and 000001",
            {"stock_code": "600519"},
        )

    decision = captured["decision"]
    assert decision["mode"] == "quick"
    assert decision["mode"] != "full"
    assert _router_decision(result)["mode"] == "quick"
    assert orch.mode == "quick"


def _chat_patches(orch, *, pipeline_result=None):
    pipeline = patch.object(
        orch,
        "_execute_pipeline",
        return_value=pipeline_result
        or OrchestratorResult(success=True, content="chat"),
    )
    history = patch(
        "src.agent.orchestrator.build_visible_chat_history",
        return_value=[],
    )
    session = patch("src.agent.conversation.conversation_manager.get_or_create")
    add_user = patch("src.agent.conversation.conversation_manager.add_user_message")
    add_msg = patch("src.agent.conversation.conversation_manager.add_message")
    return pipeline, history, session, add_user, add_msg


def test_chat_default_wires_router_and_still_pipelines():
    orch = _orchestrator("quick")
    pipeline, history, session, add_user, add_msg = _chat_patches(orch)
    with pipeline as pipeline_mock:
        with patch(
            "src.agent.runtime.agent_router_facts.project_router_request",
            wraps=project_router_request,
        ) as projector:
            with history, session, add_user, add_msg:
                result = orch.chat("hello", "session-1")

    assert projector.call_count == 1
    assert pipeline_mock.call_count == 1
    assert orch.mode == "quick"
    assert result.success is True
    decision = _router_decision(result)
    assert decision["accepted"] is True
    assert decision["chat_path"] == "full_repipeline"


def test_chat_incremental_tool_skips_pipeline_and_multi_symbol():
    orch = _orchestrator("quick")
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
        tool_calls_log=[{"tool": "get_realtime_quote"}],
        total_steps=1,
        total_tokens=3,
        provider="mock",
        model="mock-model",
        error=None,
        cancelled=False,
        timed_out=False,
        budget_snapshot=None,
        failure_reason=None,
    )
    pipeline, history, session, add_user, add_msg = _chat_patches(orch)
    with pipeline as pipeline_mock:
        with patch.object(orch, "_execute_multi_symbol_chat") as multi:
            with patch(
                "src.agent.orchestrator.resolve_stock_scope",
                return_value=resolution,
            ):
                with patch(
                    "src.agent.orchestrator_parts.chat.run_agent_loop",
                    return_value=loop_result,
                ) as loop:
                    with history, session, add_user, add_msg:
                        result = orch.chat(
                            "price?",
                            "session-1",
                            context={
                                "stock_code": "600519",
                                "tool_suitable": True,
                            },
                        )

    assert pipeline_mock.call_count == 0
    assert multi.call_count == 0
    assert loop.call_count == 1
    decision = _router_decision(result)
    assert decision["chat_path"] == "incremental_tool"
    assert decision["accepted"] is True
    assert result.success is True
    assert result.content == "quote"


def test_chat_full_override_repipelines_even_when_tool_suitable():
    orch = _orchestrator("quick")
    scope = StockScope(
        expected_stock_code="600519",
        allowed_stock_codes={"600519"},
        mode="maintain",
    )
    resolution = StockScopeResolution(
        effective_context={"stock_code": "600519"},
        stock_scope=scope,
    )
    pipeline, history, session, add_user, add_msg = _chat_patches(orch)
    with pipeline as pipeline_mock:
        with patch(
            "src.agent.orchestrator.resolve_stock_scope",
            return_value=resolution,
        ):
            with patch(
                "src.agent.orchestrator_parts.chat.run_agent_loop"
            ) as loop:
                with history, session, add_user, add_msg:
                    result = orch.chat(
                        "price?",
                        "session-1",
                        context={
                            "stock_code": "600519",
                            "tool_suitable": True,
                            "user_mode_override": "full",
                        },
                    )

    assert pipeline_mock.call_count == 1
    assert loop.call_count == 0
    assert _router_decision(result)["chat_path"] == "full_repipeline"
    assert result.success is True


def test_chat_switch_or_compare_does_not_take_incremental():
    orch = _orchestrator("quick")
    switch = StockScope(
        expected_stock_code="000001",
        allowed_stock_codes={"000001"},
        mode="switch",
    )
    compare = StockScope(
        expected_stock_code="600519",
        allowed_stock_codes={"600519", "000001"},
        mode="compare",
    )
    pipeline, history, session, add_user, add_msg = _chat_patches(orch)
    with pipeline as pipeline_mock:
        with patch.object(
            orch,
            "_execute_multi_symbol_chat",
            return_value=OrchestratorResult(success=True, content="cmp"),
        ) as multi:
            with patch(
                "src.agent.orchestrator_parts.chat.run_agent_loop"
            ) as loop:
                with history, session, add_user, add_msg:
                    with patch(
                        "src.agent.orchestrator.resolve_stock_scope",
                        return_value=StockScopeResolution(
                            effective_context={"stock_code": "000001"},
                            stock_scope=switch,
                        ),
                    ):
                        switch_result = orch.chat(
                            "hello",
                            "s1",
                            context={"tool_suitable": True},
                        )
                    with patch(
                        "src.agent.orchestrator.resolve_stock_scope",
                        return_value=StockScopeResolution(
                            effective_context={"stock_code": "600519"},
                            stock_scope=compare,
                        ),
                    ):
                        compare_result = orch.chat(
                            "compare",
                            "s2",
                            context={"tool_suitable": True},
                        )

    assert loop.call_count == 0
    assert pipeline_mock.call_count == 1
    assert multi.call_count == 1
    assert _router_decision(switch_result)["chat_path"] == "full_repipeline"
    assert _router_decision(compare_result)["chat_path"] == "full_repipeline"


def test_chat_invalid_override_is_fail_closed_without_pipeline():
    orch = _orchestrator("quick")
    pipeline, history, session, add_user, add_msg = _chat_patches(orch)
    with pipeline as pipeline_mock:
        with history, session, add_user, add_msg:
            result = orch.chat(
                "hello",
                "session-1",
                context={"user_mode_override": "not-a-mode"},
            )

    assert pipeline_mock.call_count == 0
    assert result.success is False
    assert result.error == AGENT_CHAT_FAILURE_MESSAGE
    decision = _router_decision(result)
    assert decision["accepted"] is False
    assert decision["reason_code"] == "invalid_override"
    assert "not-a-mode" not in repr(result.planning_metadata)
    assert "not-a-mode" not in (result.error or "")


def test_chat_unknown_field_reject_does_not_echo_keys():
    orch = _orchestrator("quick")
    rejected = RouterFactProjection(
        accepted=False,
        request=None,
        reason_code="unknown_field",
        error="Request contains unknown classification fields.",
        error_field="request",
    )
    pipeline, history, session, add_user, add_msg = _chat_patches(orch)
    with pipeline as pipeline_mock:
        with patch(
            "src.agent.runtime.agent_router_facts.project_router_request",
            return_value=rejected,
        ):
            with history, session, add_user, add_msg:
                result = orch.chat("hello", "session-1")

    assert pipeline_mock.call_count == 0
    assert result.error == AGENT_CHAT_FAILURE_MESSAGE
    decision = _router_decision(result)
    assert decision["reason_code"] == "unknown_field"
    assert "hello" not in repr(result.planning_metadata)


def test_chat_router_facts_do_not_parse_message_or_report_type():
    scope = StockScope(
        expected_stock_code="600519",
        allowed_stock_codes={"600519"},
        mode="maintain",
    )
    resolution = StockScopeResolution(
        effective_context={"stock_code": "600519", "report_type": "full"},
        stock_scope=scope,
    )
    facts = _build_chat_router_facts(
        resolution,
        {
            "tool_suitable": True,
            "report_type": "full",
            "skills": ["x"],
            "need_news": False,
        },
    )
    assert facts["entry_kind"] == "chat"
    assert facts["scope_mode"] == "maintain"
    assert facts["tool_suitable"] is True
    assert facts["need_news"] is False
    assert "report_type" not in facts
    assert "skills" not in facts
    projection = project_router_request(facts)
    assert projection.accepted is True
    decision = AgentRouter().route(projection.request)
    assert decision.chat_path == "incremental_tool"
