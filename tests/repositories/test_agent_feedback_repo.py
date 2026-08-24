# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Real-SQLite tests for optional agent run/prediction feedback sidecars."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool
from sqlalchemy import create_engine

from src.config import Config
from src.migrations.registry import (
    AGENT_FEEDBACK_SCHEMA_MIGRATION,
    AGENT_PREDICTION_SCHEMA_MIGRATION,
    get_migrations,
)
from src.migrations.runner import MigrationRunner
from src.migrations.versions import v202608240001_agent_feedback_schema as migration_mod
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_feedback_repo import AgentFeedbackRepository
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.repositories.agent_prediction_tables import agent_predictions_table
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.agent_prediction import (
    STATUS_PENDING,
    STATUS_RESOLVED,
    AgentPredictionInsert,
)
from src.schemas.memory_fact_opinion import FactOpinionMixError
from src.schemas.memory_provenance import MemoryProvenanceError
from src.schemas.memory_write_guard import MemoryWriteRejectedError
from src.services.agent_feedback_service import (
    AgentFeedbackNotFoundError,
    AgentFeedbackService,
    AgentFeedbackUnresolvedError,
)
from src.services.prediction_persist import prediction_id_for_run
from src.storage import AnalysisHistory, DatabaseManager


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "agent-feedback.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _fixed_now() -> datetime:
    return datetime(2026, 8, 24, 12, 0, 0)


def _direction_claim() -> dict:
    return {
        "claim_id": "direction-0",
        "type": "direction",
        "confidence": 0.7,
        "payload": {"direction": "up"},
    }


def _insert_prediction(
    db: DatabaseManager,
    *,
    prediction_id: str = "pred-1",
    run_id: str = "run-1",
) -> None:
    repo = AgentPredictionRepository(db, clock=_fixed_now)
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id=run_id,
            symbol="600519",
            market="cn",
            as_of=_fixed_now().date(),
            horizon="5d",
            resolve_after=_fixed_now() - timedelta(hours=1),
            claims=[_direction_claim()],
            created_at=_fixed_now() - timedelta(days=1),
        )
    )
    assert created is True
    assert record.status == STATUS_PENDING


def _table_sql(engine, name: str) -> str:
    with engine.connect() as connection:
        return str(
            connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name",
                {"name": name},
            ).scalar_one()
        )


class _ExecAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def exec_driver_sql(self, statement, parameters=None):
        return self._connection.exec_driver_sql(statement, parameters)

    def execute(self, statement, parameters=None):
        return self._connection.execute(statement, parameters)


def test_fresh_database_applies_feedback_schema(isolated_db) -> None:
    inspector = inspect(isolated_db._engine)
    tables = inspector.get_table_names()
    assert "agent_run_feedback" in tables
    assert "agent_prediction_feedback" in tables
    run_ddl = _table_sql(isolated_db._engine, "agent_run_feedback")
    pred_ddl = _table_sql(isolated_db._engine, "agent_prediction_feedback")
    assert "ck_agent_run_feedback_value" in run_ddl
    assert "ck_agent_prediction_feedback_value" in pred_ddl
    assert "run_id VARCHAR(128) NOT NULL" in pred_ddl
    assert get_migrations()[-1].id == AGENT_FEEDBACK_SCHEMA_MIGRATION.id
    assert AGENT_FEEDBACK_SCHEMA_MIGRATION.id in {
        migration.id for migration in get_migrations()
    }
    with isolated_db.get_session() as session:
        applied = session.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"),
            {"version": AGENT_FEEDBACK_SCHEMA_MIGRATION.id},
        ).scalar_one()
    assert applied == 1


def test_migration_upgrade_is_idempotent_and_downgrade_drops_sidecars(
    isolated_db,
) -> None:
    engine = isolated_db._engine
    with engine.begin() as connection:
        adapter = _ExecAdapter(connection)
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_run_feedback" in names
        assert "agent_prediction_feedback" in names
        migration_mod.downgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_run_feedback" not in names
        assert "agent_prediction_feedback" not in names
        assert "agent_predictions" in names
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_run_feedback" in names
        assert "agent_prediction_feedback" in names


def test_upsert_run_and_prediction_feedback_is_idempotent(isolated_db) -> None:
    _insert_prediction(isolated_db)
    repo = AgentFeedbackRepository(isolated_db)
    first = repo.upsert_run_feedback(
        "run-1",
        {
            "feedback_value": "useful",
            "note": "first",
            "source": "api",
        },
    )
    second = repo.upsert_run_feedback(
        "run-1",
        {
            "feedback_value": "partial",
            "note": "second",
            "source": "web",
        },
    )
    assert first.subject_id == "run-1"
    assert first.feedback_value == "useful"
    assert first.provenance_source == "user_feedback"
    assert first.actor_id == "local_admin"
    assert second.feedback_value == "partial"
    assert second.note == "second"
    assert second.source == "web"
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    with isolated_db.get_session() as session:
        count = session.execute(text("SELECT COUNT(*) FROM agent_run_feedback")).scalar_one()
    assert count == 1

    pred_first = repo.upsert_prediction_feedback(
        "pred-1",
        {
            "feedback_value": "agree_hit",
            "source": "api",
        },
        run_id="run-1",
    )
    pred_second = repo.upsert_prediction_feedback(
        "pred-1",
        {
            "feedback_value": "disagree_score",
            "note": "score too high",
            "source": "web",
        },
        run_id="run-1",
    )
    assert pred_first.feedback_value == "agree_hit"
    assert pred_first.run_id == "run-1"
    assert pred_second.feedback_value == "disagree_score"
    assert pred_second.note == "score too high"
    assert pred_second.created_at == pred_first.created_at
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_prediction_feedback")
        ).scalar_one()
        stored_run = session.execute(
            text(
                "SELECT run_id FROM agent_prediction_feedback "
                "WHERE prediction_id = :prediction_id"
            ),
            {"prediction_id": "pred-1"},
        ).scalar_one()
    assert count == 1
    assert stored_run == "run-1"


def test_upsert_rejects_identity_keys_in_opinion_payload(isolated_db) -> None:
    _insert_prediction(isolated_db)
    repo = AgentFeedbackRepository(isolated_db)
    with pytest.raises(FactOpinionMixError):
        repo.upsert_prediction_feedback(
            "pred-1",
            {
                "prediction_id": "pred-1",
                "feedback_value": "agree_hit",
                "source": "api",
            },
            run_id="run-1",
        )
    with pytest.raises(FactOpinionMixError):
        repo.upsert_run_feedback(
            "run-1",
            {
                "feedback_value": "useful",
                "source": "api",
                "outcome": "miss",
            },
        )
    assert repo.get_prediction_feedback("pred-1") is None
    assert repo.get_run_feedback("run-1") is None


def test_run_identity_from_history_without_prediction(isolated_db) -> None:
    service = AgentFeedbackService(db_manager=isolated_db)
    with pytest.raises(AgentFeedbackNotFoundError):
        service.get_run_feedback("hist-run")
    with isolated_db.get_session() as session:
        session.add(
            AnalysisHistory(
                query_id="hist-run",
                code="600519",
                report_type="simple",
            )
        )
        session.commit()
    payload = service.put_run_feedback("hist-run", feedback_value="partial")
    assert payload["feedback_value"] == "partial"
    assert payload["run_id"] == "hist-run"


def test_episode_only_run_is_not_a_feedback_parent(isolated_db) -> None:
    started = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    AgentEpisodeRepository(isolated_db).append(
        AgentEpisodeCreate(
            episode_id="ep-1",
            run_id="episode-run",
            mode="analysis",
            started_at=started,
            completed_at=started,
            success=True,
        )
    )
    service = AgentFeedbackService(db_manager=isolated_db)
    with pytest.raises(AgentFeedbackNotFoundError):
        service.put_run_feedback("episode-run", feedback_value="wrong")
    episode = AgentEpisodeRepository(isolated_db).get_by_run_id("episode-run")[0]
    assert episode.outcome_labels is None


def test_unresolved_prediction_feedback_is_rejected(isolated_db) -> None:
    prediction_id = prediction_id_for_run("run-a", "600519")
    _insert_prediction(isolated_db, prediction_id=prediction_id, run_id="run-a")
    service = AgentFeedbackService(db_manager=isolated_db)
    empty = service.get_prediction_feedback(prediction_id)
    assert empty["feedback_value"] is None
    with pytest.raises(AgentFeedbackUnresolvedError):
        service.put_prediction_feedback(
            prediction_id,
            feedback_value="agree_hit",
        )
    assert service.get_prediction_feedback(prediction_id)["feedback_value"] is None
    parent = AgentPredictionRepository(isolated_db).get(prediction_id)
    assert parent is not None
    assert parent.status == STATUS_PENDING
    assert parent.outcome is None


def test_opinion_write_does_not_mutate_prediction_or_episode(isolated_db) -> None:
    _insert_prediction(isolated_db)
    pred_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    applied, resolved = pred_repo.resolve(
        prediction_id="pred-1",
        outcome={"label": "hit", "score": 1.0},
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED
    before_outcome = dict(resolved.outcome or {})
    before_updated = resolved.updated_at
    before_resolved_at = resolved.resolved_at

    started = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    AgentEpisodeRepository(isolated_db).append(
        AgentEpisodeCreate(
            episode_id="ep-pred-1",
            run_id="run-1",
            mode="analysis",
            started_at=started,
            completed_at=started,
            success=True,
        )
    )

    service = AgentFeedbackService(db_manager=isolated_db)
    service.put_prediction_feedback(
        "pred-1",
        feedback_value="disagree_score",
        note="user disputes the hit",
        source="web",
    )
    service.put_run_feedback("run-1", feedback_value="harmful")

    after = pred_repo.get("pred-1")
    assert after is not None
    assert after.status == STATUS_RESOLVED
    assert after.outcome == before_outcome
    assert after.updated_at == before_updated
    assert after.resolved_at == before_resolved_at
    with isolated_db.get_session() as session:
        raw = session.execute(
            select(
                agent_predictions_table.c.outcome_json,
                agent_predictions_table.c.status,
                agent_predictions_table.c.resolved_at,
            ).where(agent_predictions_table.c.prediction_id == "pred-1")
        ).one()
    assert '"label": "hit"' in str(raw.outcome_json) or '"label":"hit"' in str(
        raw.outcome_json
    ).replace(" ", "")
    assert raw.status == STATUS_RESOLVED
    assert raw.resolved_at == before_resolved_at
    episode = AgentEpisodeRepository(isolated_db).get_by_run_id("run-1")[0]
    assert episode.outcome_labels is None
    with isolated_db.get_session() as session:
        with pytest.raises(IntegrityError, match="append-only"):
            session.execute(
                text(
                    "UPDATE agent_episodes SET outcome_labels_json = :payload "
                    "WHERE run_id = :run_id"
                ),
                {"payload": '{"user_feedback":"harmful"}', "run_id": "run-1"},
            )
            session.commit()


def test_mixed_soul_provenance_and_oversize_do_not_persist(isolated_db) -> None:
    _insert_prediction(isolated_db)
    repo = AgentFeedbackRepository(isolated_db)
    with pytest.raises(FactOpinionMixError):
        repo.upsert_prediction_feedback(
            "pred-1",
            {
                "feedback_value": "agree_hit",
                "source": "api",
                "outcome": "miss",
                "score": 0,
            },
            run_id="run-1",
        )
    with pytest.raises(MemoryProvenanceError):
        repo.upsert_run_feedback(
            "run-1",
            {
                "feedback_value": "useful",
                "source": "api",
                "provenance_source": "operator",
            },
        )
    with pytest.raises(MemoryWriteRejectedError):
        repo.upsert_prediction_feedback(
            "pred-1",
            {
                "feedback_value": "context_note",
                "note": "stockpulse-agent-soul",
                "source": "api",
            },
            run_id="run-1",
        )
    with pytest.raises(MemoryWriteRejectedError):
        repo.upsert_run_feedback(
            "run-1",
            {
                "feedback_value": "partial",
                "note": "x" * 1001,
                "source": "api",
            },
        )
    assert repo.get_prediction_feedback("pred-1") is None
    assert repo.get_run_feedback("run-1") is None


def test_resolver_still_resolves_with_zero_feedback(isolated_db) -> None:
    _insert_prediction(isolated_db, prediction_id="pred-due", run_id="run-due")
    repo = AgentFeedbackRepository(isolated_db)
    pred_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    assert repo.get_prediction_feedback("pred-due") is None
    due = pred_repo.list_due(as_of=_fixed_now(), limit=10)
    assert any(row.prediction_id == "pred-due" for row in due)
    applied, resolved = pred_repo.resolve(
        prediction_id="pred-due",
        outcome={"label": "miss", "score": 0.0},
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED
    assert resolved.outcome == {"label": "miss", "score": 0.0}
    assert repo.get_prediction_feedback("pred-due") is None
    assert repo.get_run_feedback("run-due") is None


def test_apply_pending_repairs_missing_feedback_tables(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "existing-feedback.sqlite"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    first = DatabaseManager.get_instance()
    with first.get_session() as session:
        session.execute(
            text(
                "INSERT INTO stock_daily (code, date, close) "
                "VALUES ('600519', '2026-08-01', 100.0)"
            )
        )
        session.commit()
    DatabaseManager.reset_instance()

    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS agent_prediction_feedback")
            connection.exec_driver_sql("DROP TABLE IF EXISTS agent_run_feedback")
            connection.exec_driver_sql(
                "DELETE FROM schema_migrations WHERE version = :version",
                {"version": AGENT_FEEDBACK_SCHEMA_MIGRATION.id},
            )
        result = MigrationRunner().apply_pending(engine)
        assert result.success is True
        assert AGENT_FEEDBACK_SCHEMA_MIGRATION.id in result.executed_ids
        inspector = inspect(engine)
        assert "agent_run_feedback" in inspector.get_table_names()
        assert "agent_prediction_feedback" in inspector.get_table_names()
        assert "agent_predictions" in inspector.get_table_names()
        verification = MigrationRunner().verify(engine)
        assert verification.success is True
        assert verification.current_version == AGENT_FEEDBACK_SCHEMA_MIGRATION.id
        assert AGENT_PREDICTION_SCHEMA_MIGRATION.id in {
            migration.id for migration in get_migrations()
        }
    finally:
        engine.dispose()
        DatabaseManager.reset_instance()
        Config.reset_instance()
