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
from src.agent.orchestrator_parts.chat import _build_dashboard_run_router_facts
from src.agent.public_contract import AGENT_EXECUTION_FAILURE_MESSAGE
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
    )
    assert facts["entry_kind"] == "run"
    assert facts["user_mode_override"] == "full"
    assert "agent_orchestrator_mode" not in facts


def test_run_applies_router_once_and_restores_constructor_mode():
    orch = _orchestrator("quick")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        captured["budget_mode"] = orch.mode_budget_limits.mode
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
    assert captured["mode"] == "standard"
    assert captured["budget_mode"] == "standard"
    assert orch.mode == "quick"
    assert orch.mode_budget_limits.mode == "quick"
    assert result.error is None


def test_run_compare_scope_routes_full_then_restores():
    orch = _orchestrator("quick")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        return OrchestratorResult(success=True)

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run(
            "compare 600519 and 000001",
            {"stock_code": "600519"},
        )

    assert result.success is True
    assert captured["mode"] == "full"
    assert orch.mode == "quick"


def test_run_explicit_override_wins_for_this_run_only():
    orch = _orchestrator("standard")
    captured = {}

    def fake_execute(ctx, **_kwargs):
        captured["mode"] = orch.mode
        return OrchestratorResult(success=True)

    with patch.object(orch, "_execute_pipeline", side_effect=fake_execute):
        result = orch.run(
            "analyze",
            {"stock_code": "600519", "user_mode_override": "specialist"},
        )

    assert result.success is True
    assert captured["mode"] == "specialist"
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
    assert captured["mode"] == "standard"
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
        assert orch.mode == "standard"
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


def test_chat_skips_router_and_still_executes_pipeline():
    orch = _orchestrator("quick")
    with patch.object(
        orch,
        "_execute_pipeline",
        return_value=OrchestratorResult(success=True, content="chat"),
    ) as pipeline:
        with patch(
            "src.agent.runtime.agent_router_facts.project_router_request"
        ) as projector:
            with patch.object(AgentRouter, "route") as route:
                with patch(
                    "src.agent.orchestrator.build_visible_chat_history",
                    return_value=[],
                ):
                    with patch(
                        "src.agent.conversation.conversation_manager.get_or_create"
                    ):
                        with patch(
                            "src.agent.conversation.conversation_manager.add_message"
                        ):
                            result = orch.chat("hello", "session-1")

    assert projector.call_count == 0
    assert route.call_count == 0
    assert pipeline.call_count == 1
    assert orch.mode == "quick"
    assert result.success is True
