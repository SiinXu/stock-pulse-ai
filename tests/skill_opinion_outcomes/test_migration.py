from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy import inspect, text

from src.config import Config
from src.migrations.registry import (
    SKILL_OPINION_OUTCOME_SCHEMA_MIGRATION,
)
from src.repositories.skill_opinion_outcome_repo import (
    SkillOpinionOutcomeRepository,
)
from src.repositories.skill_opinion_sample_repo import (
    SkillOpinionSampleRepository,
)
from src.schemas.skill_opinion_outcome import SkillOpinionOutcomeEvaluation
from src.storage import AnalysisHistory, DatabaseManager


def _add_sample(db: DatabaseManager) -> tuple[int, int]:
    with db.session_scope() as session:
        history = AnalysisHistory(
            query_id="migration-cleanup",
            code="600519",
            report_type="simple",
            raw_result=json.dumps({}),
            created_at=datetime(2024, 1, 2, 18, 0, 0),
        )
        session.add(history)
        session.flush()
        history_id = int(history.id)
    repo = SkillOpinionSampleRepository(db)
    repo.insert_missing(
        [
            {
                "analysis_history_id": history_id,
                "stock_code": "600519",
                "skill_id": "alpha",
                "skill_version": None,
                "signal": "buy",
                "confidence": 0.8,
                "horizon": None,
                "data_quality_level": None,
                "opinion_created_at": None,
                "sample_schema_version": "skill-opinion-sample-v1",
            }
        ]
    )
    return history_id, repo.list_for_history(history_id)[0].id


def test_schema_is_registered_idempotently_and_has_constraints(
    isolated_db,
    monkeypatch,
) -> None:
    database_path = isolated_db._engine.url.database
    inspector = inspect(isolated_db._engine)
    assert {
        "skill_opinion_samples",
        "skill_opinion_outcomes",
    }.issubset(inspector.get_table_names())
    with isolated_db._engine.connect() as connection:
        sample_ddl = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'skill_opinion_samples'"
        ).scalar_one()
        outcome_ddl = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'skill_opinion_outcomes'"
        ).scalar_one()
        trigger_names = {
            str(row[0])
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
        }
    assert {
        "ck_skill_opinion_sample_signal",
        "ck_skill_opinion_sample_confidence",
    } <= set(sample_ddl.split())
    assert {
        "ck_skill_opinion_outcome_horizon",
        "ck_skill_opinion_outcome_eval_status",
        "ck_skill_opinion_outcome_value",
        "ck_skill_opinion_outcome_state_fields",
    } <= set(outcome_ddl.split())
    assert trigger_names >= {
        "trg_skill_opinion_history_delete",
        "trg_skill_opinion_sample_delete",
    }

    DatabaseManager.reset_instance()
    Config.reset_instance()
    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    restarted = DatabaseManager.get_instance()
    with restarted.get_session() as session:
        applied = session.execute(
            text(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = :version"
            ),
            {"version": SKILL_OPINION_OUTCOME_SCHEMA_MIGRATION.id},
        ).scalar_one()
    assert applied == 1


def test_history_deletion_trigger_removes_samples_and_outcomes(
    isolated_db,
) -> None:
    history_id, sample_id = _add_sample(isolated_db)
    SkillOpinionOutcomeRepository(isolated_db).persist_outcome(
        sample_id=sample_id,
        horizon="1d",
        engine_version="skill-opinion-outcome-v1",
        evaluation=SkillOpinionOutcomeEvaluation(
            eval_status="pending",
            unable_reason="missing_start_bar",
        ),
    )

    assert isolated_db.delete_analysis_history_records([history_id]) == 1
    with isolated_db.get_session() as session:
        samples = session.execute(
            text("SELECT COUNT(*) FROM skill_opinion_samples")
        ).scalar_one()
        outcomes = session.execute(
            text("SELECT COUNT(*) FROM skill_opinion_outcomes")
        ).scalar_one()
    assert samples == 0
    assert outcomes == 0
