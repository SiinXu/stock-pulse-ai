# -*- coding: utf-8 -*-
"""Unit tests for agent evolution episode log (#1090)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.config import Config
from src.agent.executor import AgentExecutor, AgentResult
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_episode_tables import agent_episodes_table
from src.repositories.base import RepositoryError
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
    with pytest.raises(ValidationError):
        _valid_create(started_at=datetime(2026, 8, 12, 10, 0, 0))


def test_repository_rejects_corrupt_json_instead_of_fabricating_empty_data(
    isolated_db,
) -> None:
    with isolated_db.get_session() as session:
        session.execute(
            agent_episodes_table.insert().values(
                schema_version="agent-episode-v1",
                episode_id="ep-corrupt",
                run_id="run-corrupt",
                mode="single",
                trajectory_summary_json='{"not":"a-list"}',
                lessons_json="[]",
                created_at=datetime(2026, 8, 12, 10, 0, 0),
            )
        )
        session.commit()

    with pytest.raises(RepositoryError) as raised:
        AgentEpisodeRepository().get_by_episode_id("ep-corrupt")
    assert raised.value.error_code == "agent_episode_corrupt_json"


def test_episode_id_collision_requires_identical_payload(isolated_db) -> None:
    repo = AgentEpisodeRepository()
    original = _valid_create()
    first = repo.append(original)
    assert repo.append(original).id == first.id

    with pytest.raises(RepositoryError) as raised:
        repo.append(_valid_create(run_id="run-different"))
    assert raised.value.error_code == "agent_episode_id_collision"


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
    with pytest.raises(ValueError):
        repo.query(limit=True)
    with pytest.raises(ValueError):
        repo.query(created_from=True)
    with pytest.raises(ValueError):
        repo.get_by_run_id("run-1", limit=201)
    with pytest.raises(ValueError):
        repo.list_for_replay("ep-1")
    with pytest.raises(ValueError):
        repo.list_for_replay([f"ep-{index}" for index in range(201)])
    with pytest.raises(ValueError):
        repo.apply_capacity(max_rows=True)


def test_service_disabled_is_noop(isolated_db) -> None:
    service = AgentEpisodeService(config=SimpleNamespace(agent_episode_log_enabled=False))
    assert service.record_episode(_valid_create()) is None


def test_disabled_helper_does_not_initialize_repository() -> None:
    with patch(
        "src.services.agent_episode_service.AgentEpisodeRepository",
        side_effect=AssertionError("repository must stay lazy"),
    ):
        assert try_record_agent_episode_from_result(
            result=SimpleNamespace(success=True),
            config=SimpleNamespace(agent_episode_log_enabled=False),
        ) is None


def test_enabled_repository_initialization_failure_is_fail_soft() -> None:
    with patch(
        "src.services.agent_episode_service.AgentEpisodeRepository",
        side_effect=RuntimeError("database unavailable"),
    ):
        assert try_record_agent_episode_from_result(
            result=SimpleNamespace(success=True),
            config=SimpleNamespace(agent_episode_log_enabled=True),
        ) is None


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
            {"step": True, "tool": "get_daily_history", "success": True},
            {"tool": "", "success": True},
        ]
    )
    assert len(steps) == 2
    assert steps[0]["tool"] == "get_realtime_quote"
    assert "argument_fingerprint" in steps[0]
    assert "sk-secret" not in str(steps)
    assert steps[1]["step"] == 2


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
        context={
            "stock_code": "AAPL",
            "market": "us",
            "run_id": "run-correlated",
        },
    )
    assert stored is not None
    assert stored.symbol == "AAPL"
    assert stored.soul_hash == "abcdef0123456789"
    assert stored.run_id == "run-correlated"


def test_executor_episode_finalizer_cannot_mask_success() -> None:
    executor = AgentExecutor(
        MagicMock(),
        MagicMock(),
        config=SimpleNamespace(agent_episode_log_enabled=True),
    )
    planned = AgentResult(success=True, runtime_facts=MagicMock())
    with patch(
        "src.agent.planning.product.try_run_with_planning",
        return_value=planned,
    ), patch(
        "src.services.agent_episode_service.try_record_agent_episode_from_result",
        side_effect=RuntimeError("episode store unavailable"),
    ):
        assert executor.run("analyze") is planned


def test_executor_episode_finalizer_cannot_mask_original_failure() -> None:
    executor = AgentExecutor(
        MagicMock(),
        MagicMock(),
        config=SimpleNamespace(agent_episode_log_enabled=True),
    )
    with patch(
        "src.agent.planning.product.try_run_with_planning",
        side_effect=ValueError("primary failure"),
    ), patch(
        "src.services.agent_episode_service.try_record_agent_episode_from_result",
        side_effect=RuntimeError("episode store unavailable"),
    ):
        with pytest.raises(ValueError, match="primary failure"):
            executor.run("analyze")


def test_executor_default_off_has_no_episode_failure_side_effect() -> None:
    executor = AgentExecutor(
        MagicMock(),
        MagicMock(),
        config=SimpleNamespace(agent_episode_log_enabled=False),
    )
    with patch(
        "src.agent.planning.product.try_run_with_planning",
        side_effect=ValueError("primary failure"),
    ), patch(
        "src.services.agent_episode_service.try_record_agent_episode_from_result",
    ) as record_episode:
        with pytest.raises(ValueError, match="primary failure"):
            executor.run("analyze")

    record_episode.assert_not_called()
