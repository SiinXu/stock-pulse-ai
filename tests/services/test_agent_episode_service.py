# -*- coding: utf-8 -*-
"""Unit tests for agent evolution episode log (#1090)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.config import Config
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.schemas.agent_episode import AgentEpisodeCreate
from src.services.agent_episode_service import (
    AgentEpisodeService,
    compact_trajectory_summary,
    is_agent_episode_log_enabled,
    try_record_agent_episode_from_result,
)
from src.storage import DatabaseManager


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "episode.db"))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _valid_create(**overrides):
    base = {
        "episode_id": "ep-test-001",
        "run_id": "run-abc",
        "mode": "single",
        "symbol": "AAPL",
        "market": "us",
        "started_at": datetime(2026, 8, 12, 10, 0, 0, tzinfo=timezone.utc),
        "completed_at": datetime(2026, 8, 12, 10, 1, 0, tzinfo=timezone.utc),
        "success": True,
        "soul_version": "v1",
        "soul_hash": "abcdef0123456789",
        "trajectory_summary": [
            {
                "step": 1,
                "tool": "get_realtime_quote",
                "success": True,
                "argument_fingerprint": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            }
        ],
        "lessons": [{"kind": "evidence_gap", "severity": "low"}],
    }
    base.update(overrides)
    return AgentEpisodeCreate.model_validate(base)


def test_flag_default_off(isolated_db) -> None:
    config = Config.get_instance()
    assert config.agent_episode_log_enabled is False
    assert is_agent_episode_log_enabled(config) is False
    assert not is_agent_episode_log_enabled(SimpleNamespace(agent_episode_log_enabled="true"))
    assert is_agent_episode_log_enabled(SimpleNamespace(agent_episode_log_enabled=True))


def test_serialize_round_trip(isolated_db) -> None:
    repo = AgentEpisodeRepository()
    create = _valid_create()
    stored = repo.append(create)
    assert stored.id >= 1
    loaded = repo.get_by_episode_id("ep-test-001")
    assert loaded is not None
    assert loaded.run_id == "run-abc"
    assert loaded.symbol == "AAPL"
    assert loaded.soul_hash == "abcdef0123456789"
    assert len(loaded.trajectory_summary) == 1
    assert loaded.trajectory_summary[0].tool == "get_realtime_quote"
    assert loaded.lessons[0].kind == "evidence_gap"
    with pytest.raises(ValidationError):
        _valid_create(soul_charter="full charter text is forbidden")


def test_query_by_run_symbol_and_time(isolated_db) -> None:
    repo = AgentEpisodeRepository()
    repo.append(_valid_create(episode_id="ep-1", run_id="run-1", symbol="AAPL"))
    repo.append(_valid_create(episode_id="ep-2", run_id="run-2", symbol="600519", market="cn"))
    by_run = repo.get_by_run_id("run-1")
    assert len(by_run) == 1
    page = repo.query(symbol="600519", limit=10)
    assert page.total == 1
    assert page.items[0].episode_id == "ep-2"
    replay = repo.list_for_replay(["ep-2", "ep-1", "missing"])
    assert [item.episode_id for item in replay] == ["ep-2", "ep-1"]


def test_service_disabled_is_noop(isolated_db) -> None:
    service = AgentEpisodeService(config=SimpleNamespace(agent_episode_log_enabled=False))
    assert service.record_episode(_valid_create()) is None


def test_service_enabled_persists(isolated_db) -> None:
    cfg = SimpleNamespace(
        agent_episode_log_enabled=True,
        agent_episode_retention_days=90,
        agent_episode_max_rows=50000,
    )
    service = AgentEpisodeService(config=cfg)
    stored = service.record_episode(_valid_create())
    assert stored is not None
    assert service.get_by_run_id("run-abc")[0].episode_id == "ep-test-001"


def test_persist_failure_does_not_raise(isolated_db) -> None:
    bad_repo = MagicMock()
    bad_repo.append.side_effect = RuntimeError("db down")
    service = AgentEpisodeService(
        repository=bad_repo,
        config=SimpleNamespace(
            agent_episode_log_enabled=True,
            agent_episode_retention_days=90,
            agent_episode_max_rows=50000,
        ),
    )
    assert service.record_episode(_valid_create()) is None


def test_compact_trajectory_redacts_arguments() -> None:
    steps = compact_trajectory_summary(
        [
            {
                "step": 1,
                "tool": "get_realtime_quote",
                "success": True,
                "arguments": {"symbol": "AAPL", "api_key": "sk-secret"},
                "duration": 0.12,
            },
            {"tool": "", "success": True},
        ]
    )
    assert len(steps) == 1
    assert steps[0]["tool"] == "get_realtime_quote"
    assert "argument_fingerprint" in steps[0]
    assert "sk-secret" not in str(steps)


def test_record_from_agent_result_fail_soft(isolated_db) -> None:
    result = SimpleNamespace(
        success=True,
        tool_calls_log=[
            {"tool": "get_daily_history", "success": True, "arguments": {"code": "AAPL"}}
        ],
        runtime_facts=SimpleNamespace(
            soul_version="v1",
            soul_hash="abcdef0123456789",
            to_metadata=lambda: {"soul_version": "v1", "soul_hash": "abcdef0123456789"},
        ),
    )
    stored = try_record_agent_episode_from_result(
        result=result,
        config=SimpleNamespace(
            agent_episode_log_enabled=True,
            agent_episode_retention_days=90,
            agent_episode_max_rows=50000,
        ),
        mode="single",
        context={"stock_code": "AAPL", "market": "us"},
    )
    assert stored is not None
    assert stored.symbol == "AAPL"
    assert stored.soul_hash == "abcdef0123456789"
