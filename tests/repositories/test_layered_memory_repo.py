# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Durable layered-memory observation store, migration, and lifecycle tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from src.agent.memory_governance import LayeredMemoryPolicy, PrincipalMemoryLifecycle
from src.agent.memory_layers import MemoryObservation
from src.config import Config
from src.migrations.registry import (
    AGENT_EPISODE_SCHEMA_MIGRATION,
    AGENT_EVOLUTION_EVENT_SCHEMA_MIGRATION,
    LAYERED_MEMORY_OBSERVATION_SCHEMA_MIGRATION,
    get_migrations,
)
from src.migrations.versions import (
    v202608260001_layered_memory_observation_schema as migration_mod,
)
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.layered_memory_repo import (
    DurableLayeredMemoryStore,
    LayeredMemoryRepository,
)
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.memory_provenance import PROVENANCE_SOURCE_SYSTEM_RESOLVE
from src.storage import DatabaseManager


_BASE = datetime(2026, 8, 1, tzinfo=timezone.utc)
AS_OF = "2026-08-09T00:00:00Z"


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "layered-memory.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


class _ExecAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def exec_driver_sql(self, statement, parameters=None):
        return self._connection.exec_driver_sql(statement, parameters)

    def execute(self, statement, parameters=None):
        return self._connection.execute(statement, parameters)


def _instant(offset_minutes: int) -> str:
    return (_BASE + timedelta(minutes=offset_minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _obs(index: int, *, principal: str = "local_admin", **overrides: Any) -> MemoryObservation:
    payload = {
        "principal_id": principal,
        "analysis_history_id": index,
        "stock_code": "600519",
        "observed_at": _instant(index),
        "expires_at": None,
        "signal": "buy",
        "sentiment_score": 60.0,
        "price_at_analysis": 100.0,
    }
    payload.update(overrides)
    return MemoryObservation(**payload)


def _lifecycle(db, **policy_kwargs) -> PrincipalMemoryLifecycle:
    repo = LayeredMemoryRepository(db)
    return PrincipalMemoryLifecycle(
        policy=LayeredMemoryPolicy(collection_enabled=True, **policy_kwargs),
        store=DurableLayeredMemoryStore(repo),
    )


def _append_episode(db: DatabaseManager) -> None:
    AgentEpisodeRepository(db).append(
        AgentEpisodeCreate(
            episode_id="ep-keep",
            run_id="run-keep",
            mode="analysis",
            symbol="600519",
            market="cn",
            started_at=datetime(2026, 8, 26, 11, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 26, 11, tzinfo=timezone.utc),
            success=True,
        )
    )


def test_fresh_database_applies_layered_memory_schema(isolated_db) -> None:
    inspector = inspect(isolated_db._engine)
    names = inspector.get_table_names()
    assert "layered_memory_observations" in names
    assert "layered_memory_consent" in names
    assert "layered_memory_access_audit" in names
    with isolated_db._engine.connect() as connection:
        ddl = str(
            connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'layered_memory_observations'"
            ).scalar_one()
        )
        triggers = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND tbl_name = 'layered_memory_access_audit'"
            ).fetchall()
        }
    assert "uix_layered_memory_observations_principal_history" in ddl
    assert "ck_layered_memory_observations_provenance" in ddl
    assert "trg_layered_memory_access_audit_no_update" in triggers
    assert "trg_layered_memory_access_audit_no_delete" in triggers
    assert get_migrations()[-1].id == LAYERED_MEMORY_OBSERVATION_SCHEMA_MIGRATION.id
    assert AGENT_EPISODE_SCHEMA_MIGRATION.id in {
        migration.id for migration in get_migrations()
    }
    with isolated_db.get_session() as session:
        applied = session.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"),
            {"version": LAYERED_MEMORY_OBSERVATION_SCHEMA_MIGRATION.id},
        ).scalar_one()
    assert applied == 1


def test_migration_upgrade_is_idempotent_and_downgrade_is_isolated(isolated_db) -> None:
    _append_episode(isolated_db)
    engine = isolated_db._engine
    with engine.begin() as connection:
        adapter = _ExecAdapter(connection)
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "layered_memory_observations" in names
        assert "agent_episodes" in names
        assert "agent_evolution_events" in names
        episode_count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM agent_episodes WHERE episode_id = 'ep-keep'"
        ).scalar_one()
        assert episode_count == 1
        migration_mod.downgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "layered_memory_observations" not in names
        assert "layered_memory_consent" not in names
        assert "layered_memory_access_audit" not in names
        assert "agent_episodes" in names
        assert "agent_evolution_events" in names
        assert "agent_predictions" in names
        leftover = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM agent_episodes WHERE episode_id = 'ep-keep'"
        ).scalar_one()
        assert leftover == 1
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        assert "layered_memory_observations" in inspect(connection).get_table_names()


def test_serialize_round_trip_and_idempotent_upsert(isolated_db) -> None:
    life = _lifecycle(isolated_db)
    life.grant_consent("local_admin", at=AS_OF)
    first = life.put(_obs(1), now=AS_OF)
    assert first.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE
    assert first.expires_at is not None
    second = life.put(_obs(1, sentiment_score=72.0), now=AS_OF)
    assert second.analysis_history_id == 1
    assert second.sentiment_score == 72.0
    rows = life.list_records("local_admin", as_of=AS_OF)
    assert len(rows) == 1
    assert rows[0].sentiment_score == 72.0
    repo = LayeredMemoryRepository(isolated_db)
    loaded = repo.get_observation("local_admin", 1)
    assert loaded is not None
    assert loaded.stock_code == "600519"
    assert loaded.provenance_source == PROVENANCE_SOURCE_SYSTEM_RESOLVE


def test_consent_retention_delete_clear_and_cross_principal(isolated_db) -> None:
    life = _lifecycle(isolated_db, retention_days=3)
    life.grant_consent("alice", at="2026-08-01T00:00:00Z")
    life.grant_consent("bob", at="2026-08-01T00:00:00Z")
    life.put(_obs(1, principal="alice"), now="2026-08-01T00:01:05Z")
    life.put(_obs(2, principal="bob"), now="2026-08-01T00:02:05Z")
    before_expiry = "2026-08-01T00:03:00Z"
    assert life.list_records("alice", as_of=before_expiry)[0].principal_id == "alice"
    assert life.delete("alice", 1, at=before_expiry) is True
    assert life.list_records("alice", as_of=before_expiry) == []
    assert len(life.list_records("bob", as_of=before_expiry)) == 1
    assert life.clear("bob", at=before_expiry) == 1
    life.put(_obs(3, principal="alice"), now="2026-08-01T00:03:05Z")
    assert life.expire_due(now="2026-08-04T00:03:05Z") == 1
    assert life.list_records("alice", as_of="2026-08-04T00:03:05Z") == []
    with pytest.raises(PermissionError):
        PrincipalMemoryLifecycle(
            policy=LayeredMemoryPolicy(collection_enabled=True),
            store=DurableLayeredMemoryStore(LayeredMemoryRepository(isolated_db)),
        ).put(_obs(4, principal="carol"), now=AS_OF)


def test_audit_is_append_only_and_project_reuses_existing_projector(isolated_db) -> None:
    life = _lifecycle(isolated_db)
    life.grant_consent("alice", at=AS_OF)
    for index in range(1, 4):
        life.put(_obs(index, principal="alice", was_correct=True, outcome_id=1000 + index,
                     outcome_horizon_days=5, evaluated_at="2026-08-08T00:00:00Z"), now=AS_OF)
    bundle = life.project("alice", stock_code="600519", as_of=AS_OF, query="buy")
    assert len(bundle.outcome_patterns) == 1
    actions = [event.action for event in life.auditor.list_for_principal("alice")]
    assert "collect" in actions and "project" in actions
    with isolated_db._engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql(
                "UPDATE layered_memory_access_audit SET detail = 'tamper'"
            )
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql("DELETE FROM layered_memory_access_audit")


def test_repository_project_does_not_cross_principals(isolated_db) -> None:
    repo = LayeredMemoryRepository(isolated_db)
    life = PrincipalMemoryLifecycle(
        policy=LayeredMemoryPolicy(collection_enabled=True),
        store=DurableLayeredMemoryStore(repo),
    )
    life.grant_consent("alice", at=AS_OF)
    life.grant_consent("bob", at=AS_OF)
    life.put(_obs(1, principal="alice"), now=AS_OF)
    life.put(_obs(2, principal="bob"), now=AS_OF)
    alice_rows = repo.list_records("alice", as_of=AS_OF)
    assert [row.principal_id for row in alice_rows] == ["alice"]
    bundle = repo.project("alice", stock_code="600519", as_of=AS_OF)
    assert all(entry.principal_id == "alice" for entry in bundle.episodic)
    assert AGENT_EVOLUTION_EVENT_SCHEMA_MIGRATION.id in {
        migration.id for migration in get_migrations()
    }
