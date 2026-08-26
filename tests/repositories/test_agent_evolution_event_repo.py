# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Focused migration, append, query, and append-only tests for EvolutionEvent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from src.config import Config
from src.migrations.registry import (
    AGENT_CURATOR_GRADE_SCHEMA_MIGRATION,
    AGENT_EVOLUTION_EVENT_SCHEMA_MIGRATION,
    LAYERED_MEMORY_OBSERVATION_SCHEMA_MIGRATION,
    get_migrations,
)
from src.migrations.versions import (
    v202608250003_agent_evolution_event_schema as migration_mod,
)
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_evolution_event_repo import AgentEvolutionEventRepository
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.evolution_event import EvolutionEventCreate
from src.storage import DatabaseManager


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "evolution-event.db"
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


def _ts(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 25, hour, minute, tzinfo=timezone.utc)


def _create(**overrides: Any) -> EvolutionEventCreate:
    payload = {
        "event_type": "adapter.confidence_calibration",
        "actor": "system",
        "occurred_at": _ts(12),
        "reason_refs": {"prediction_ids": ["pred-1"], "run_ids": ["run-1"]},
        "before": {"factor": 1.0},
        "after": {"factor": 1.1},
    }
    payload.update(overrides)
    return EvolutionEventCreate.model_validate(payload)


def _append_episode(db: DatabaseManager) -> None:
    AgentEpisodeRepository(db).append(
        AgentEpisodeCreate(
            episode_id="ep-keep",
            run_id="run-keep",
            mode="analysis",
            symbol="600519",
            market="cn",
            started_at=_ts(11),
            completed_at=_ts(11),
            success=True,
        )
    )


def test_fresh_database_applies_evolution_event_schema(isolated_db) -> None:
    inspector = inspect(isolated_db._engine)
    assert "agent_evolution_events" in inspector.get_table_names()
    with isolated_db._engine.connect() as connection:
        ddl = str(
            connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'agent_evolution_events'"
            ).scalar_one()
        )
        triggers = {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND tbl_name = 'agent_evolution_events'"
            ).fetchall()
        }
    assert "ck_agent_evolution_events_actor" in ddl
    assert "uix_agent_evolution_events_event_id" in ddl
    assert "trg_agent_evolution_events_no_update" in triggers
    assert "trg_agent_evolution_events_no_delete" in triggers
    assert get_migrations()[-1].id == LAYERED_MEMORY_OBSERVATION_SCHEMA_MIGRATION.id
    assert AGENT_CURATOR_GRADE_SCHEMA_MIGRATION.id in {
        migration.id for migration in get_migrations()
    }
    with isolated_db.get_session() as session:
        applied = session.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"),
            {"version": AGENT_EVOLUTION_EVENT_SCHEMA_MIGRATION.id},
        ).scalar_one()
    assert applied == 1


def test_migration_upgrade_is_idempotent_and_downgrade_is_isolated(isolated_db) -> None:
    _append_episode(isolated_db)
    AgentEvolutionEventRepository(isolated_db).append(_create(event_id="evt-keep"))
    engine = isolated_db._engine
    with engine.begin() as connection:
        adapter = _ExecAdapter(connection)
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_evolution_events" in names
        assert "agent_episodes" in names
        assert "agent_episode_curator_grades" in names
        episode_count = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM agent_episodes WHERE episode_id = 'ep-keep'"
        ).scalar_one()
        assert episode_count == 1
        migration_mod.downgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_evolution_events" not in names
        assert "agent_episodes" in names
        assert "agent_episode_curator_grades" in names
        assert "agent_predictions" in names
        leftover = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM agent_episodes WHERE episode_id = 'ep-keep'"
        ).scalar_one()
        assert leftover == 1
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        assert "agent_evolution_events" in inspect(connection).get_table_names()
        restored = connection.exec_driver_sql(
            "SELECT COUNT(*) FROM agent_evolution_events"
        ).scalar_one()
        assert restored == 0


def test_append_serializes_and_round_trips(isolated_db) -> None:
    repo = AgentEvolutionEventRepository(isolated_db)
    stored = repo.append(
        _create(
            event_id="evt-1",
            actor="operator",
            event_type="skill.flag.rollback",
        )
    )
    assert stored.id >= 1
    assert stored.event_id == "evt-1"
    assert stored.actor == "operator"
    assert stored.event_type == "skill.flag.rollback"
    assert stored.reason_refs.prediction_ids == ["pred-1"]
    assert stored.reason_refs.run_ids == ["run-1"]
    assert stored.before == {"factor": 1.0}
    assert stored.after == {"factor": 1.1}
    assert stored.occurred_at == _ts(12)
    loaded = repo.list_events(occurred_from=_ts(12), occurred_to=_ts(12))
    assert len(loaded) == 1
    assert loaded[0].model_dump(mode="json") == stored.model_dump(mode="json")


def test_empty_reason_refs_persist_and_noop_snapshots_do_not_write(isolated_db) -> None:
    repo = AgentEvolutionEventRepository(isolated_db)
    stored = repo.append(
        _create(
            event_id="no-refs",
            reason_refs={"prediction_ids": [], "run_ids": []},
        )
    )
    assert stored.reason_refs.prediction_ids == []
    assert stored.reason_refs.run_ids == []
    with pytest.raises(ValidationError, match="must describe a mutation"):
        repo.append(
            _create(
                event_id="noop",
                before={"factor": 1.0},
                after={"factor": 1.0},
            )
        )
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_evolution_events")
        ).scalar_one()
    assert count == 1


def test_actor_and_type_validation_does_not_write(isolated_db) -> None:
    repo = AgentEvolutionEventRepository(isolated_db)
    with pytest.raises(ValidationError):
        repo.append(_create(actor="admin"))
    with pytest.raises(ValidationError):
        EvolutionEventCreate.model_validate(
            {
                "event_type": "",
                "actor": "system",
            }
        )
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_evolution_events")
        ).scalar_one()
    assert count == 0


def test_time_and_type_filters_are_inclusive_and_exact(isolated_db) -> None:
    repo = AgentEvolutionEventRepository(isolated_db)
    repo.append(
        _create(
            event_id="early",
            occurred_at=_ts(10),
            event_type="adapter.confidence_calibration",
        )
    )
    repo.append(
        _create(
            event_id="mid",
            occurred_at=_ts(12),
            event_type="adapter.confidence_calibration",
        )
    )
    repo.append(
        _create(
            event_id="late",
            occurred_at=_ts(14),
            event_type="skill.flag.enable",
        )
    )
    window = repo.list_events(occurred_from=_ts(10), occurred_to=_ts(14))
    assert [item.event_id for item in window] == ["early", "mid", "late"]
    inclusive = repo.list_events(occurred_from=_ts(12), occurred_to=_ts(12))
    assert [item.event_id for item in inclusive] == ["mid"]
    typed = repo.list_events(
        occurred_from=_ts(10),
        occurred_to=_ts(14),
        event_type="skill.flag.enable",
    )
    assert [item.event_id for item in typed] == ["late"]
    missing_type = repo.list_events(
        occurred_from=_ts(10),
        occurred_to=_ts(14),
        event_type="route.bias.update",
    )
    assert missing_type == []
    with pytest.raises(ValueError, match="nonempty"):
        repo.list_events(
            occurred_from=_ts(10),
            occurred_to=_ts(14),
            event_type="   ",
        )
    unfiltered = repo.list_events(
        occurred_from=_ts(10),
        occurred_to=_ts(14),
        event_type=None,
    )
    assert [item.event_id for item in unfiltered] == ["early", "mid", "late"]


def test_deterministic_limit_uses_occurred_at_then_id(isolated_db) -> None:
    repo = AgentEvolutionEventRepository(isolated_db)
    same = _ts(12)
    repo.append(_create(event_id="a", occurred_at=same, after={"n": 1}))
    repo.append(_create(event_id="b", occurred_at=same, after={"n": 2}))
    repo.append(_create(event_id="c", occurred_at=same + timedelta(minutes=1), after={"n": 3}))
    limited = repo.list_events(occurred_from=_ts(12), occurred_to=_ts(13), limit=2)
    assert [item.event_id for item in limited] == ["a", "b"]
    later = repo.list_events(occurred_from=_ts(12), occurred_to=_ts(13), limit=3)
    assert [item.event_id for item in later] == ["a", "b", "c"]


def test_empty_query_returns_empty_list(isolated_db) -> None:
    repo = AgentEvolutionEventRepository(isolated_db)
    assert repo.list_events(occurred_from=_ts(1), occurred_to=_ts(2)) == []
    repo.append(_create(event_id="outside", occurred_at=_ts(20)))
    assert repo.list_events(occurred_from=_ts(1), occurred_to=_ts(2)) == []


def test_update_and_delete_are_rejected(isolated_db) -> None:
    repo = AgentEvolutionEventRepository(isolated_db)
    stored = repo.append(_create(event_id="immutable"))
    with isolated_db.get_session() as session:
        with pytest.raises(IntegrityError, match="append-only"):
            session.execute(
                text(
                    "UPDATE agent_evolution_events SET after_json = :payload "
                    "WHERE event_id = :event_id"
                ),
                {"payload": '{"factor":9}', "event_id": "immutable"},
            )
            session.commit()
    with isolated_db.get_session() as session:
        with pytest.raises(IntegrityError, match="append-only"):
            session.execute(
                text("DELETE FROM agent_evolution_events WHERE event_id = :event_id"),
                {"event_id": "immutable"},
            )
            session.commit()
    reloaded = repo.list_events(occurred_from=_ts(12), occurred_to=_ts(12))
    assert len(reloaded) == 1
    assert reloaded[0].after == stored.after
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_evolution_events")
        ).scalar_one()
    assert count == 1


def test_repository_exposes_append_and_query_only() -> None:
    public = [
        name
        for name in dir(AgentEvolutionEventRepository)
        if not name.startswith("_") and callable(getattr(AgentEvolutionEventRepository, name))
    ]
    assert "append" in public
    assert "list_events" in public
    assert "update" not in public
    assert "delete" not in public
    assert "try_append" not in public
