# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Pipeline episode persist of secret-free router_decision (#1120 leftover)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agent.orchestrator import AgentOrchestrator
from src.agent.protocols import AgentContext
from src.config import Config
from src.services.agent_episode_service import AgentEpisodeService
from src.storage import DatabaseManager


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "router-episode.db"))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _orchestrator(mode="quick"):
    return AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        mode=mode,
        config=SimpleNamespace(agent_orchestrator_timeout_s=0),
    )


def _logging_orchestrator(mode="quick"):
    return AgentOrchestrator(
        tool_registry=MagicMock(),
        llm_adapter=MagicMock(),
        mode=mode,
        config=SimpleNamespace(
            agent_orchestrator_timeout_s=0,
            agent_episode_log_enabled=True,
            agent_episode_retention_days=90,
            agent_episode_max_rows=50000,
        ),
    )


def _stub_empty_pipeline(orch):
    return (
        patch.object(orch, "_build_agent_chain", return_value=[]),
        patch.object(
            orch,
            "_resolve_final_output",
            return_value=({"decision_type": "hold"}, "ok"),
        ),
    )


def test_dashboard_run_persists_bounded_router_decision_on_episode(isolated_db):
    orch = _logging_orchestrator("quick")
    chain, output = _stub_empty_pipeline(orch)
    with chain, output:
        result = orch.run("analyze", {"stock_code": "600519"})

    assert result.success is True
    decision = (result.planning_metadata or {}).get("router_decision") or {}
    assert decision["mode"] == "quick"
    page = AgentEpisodeService(config=orch.config).query(symbol="600519", limit=10)
    assert page.total == 1
    labels = page.items[0].outcome_labels
    assert labels is not None
    assert labels.router_accepted is True
    assert labels.router_mode == "quick"
    assert labels.router_chat_path == "full_repipeline"
    assert labels.router_reason_code == "explicit_override"
    dumped = labels.model_dump()
    assert "error" not in dumped
    assert "explain" not in dumped


def test_pipeline_persist_omits_router_fields_when_decision_missing(isolated_db):
    orch = _logging_orchestrator("quick")
    ctx = AgentContext(query="analyze", stock_code="600519")
    chain, output = _stub_empty_pipeline(orch)
    with chain, output:
        result = orch._execute_pipeline(ctx, parse_dashboard=True)

    assert result.success is True
    page = AgentEpisodeService(config=orch.config).query(symbol="600519", limit=10)
    assert page.total == 1
    labels = page.items[0].outcome_labels
    assert labels is None or (
        labels.router_accepted is None
        and labels.router_mode is None
        and labels.router_chat_path is None
        and labels.router_reason_code is None
    )


def test_pipeline_persist_exception_does_not_change_success(isolated_db):
    orch = _logging_orchestrator("quick")
    chain, output = _stub_empty_pipeline(orch)
    with chain, output:
        with patch(
            "src.services.agent_episode_service.try_record_agent_episode_from_result",
            side_effect=RuntimeError("episode store unavailable"),
        ):
            result = orch.run("analyze", {"stock_code": "600519"})

    assert result.success is True
    assert result.content == "ok"
    assert AgentEpisodeService(config=orch.config).query(symbol="600519", limit=10).total == 0


def test_pipeline_flag_off_does_not_write_episode(isolated_db):
    orch = _orchestrator("quick")
    chain, output = _stub_empty_pipeline(orch)
    with chain, output:
        result = orch.run("analyze", {"stock_code": "600519"})

    assert result.success is True
    assert AgentEpisodeService(config=orch.config).query(limit=10).total == 0
