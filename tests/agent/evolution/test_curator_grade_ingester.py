# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic tests for the #1096 curator-grade eval-fixture ingest path."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from src.config import Config
from src.migrations.registry import (
    AGENT_CURATOR_GRADE_SCHEMA_MIGRATION,
    get_migrations,
)
from src.migrations.versions import (
    v202608250002_agent_curator_grade_schema as migration_mod,
)
from src.repositories.agent_curator_grade_repo import (
    AgentCuratorGradeRepository,
    validate_curator_grade,
)
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_episode_tables import agent_episodes_table
from src.schemas.agent_episode import AgentEpisodeCreate, EpisodeOutcomeLabels
from src.schemas.curator_grade import normalize_curator_grade
from src.storage import DatabaseManager
from src.services.curator_grade_ingester import CuratorGradeIngester
from scripts import label_curator_grades as label_cli


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "curator-grade.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _started() -> datetime:
    return datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


def _append_episode(
    db: DatabaseManager,
    *,
    episode_id: str = "ep-1",
    run_id: str = "run-1",
    manual_grade: Any = None,
) -> None:
    labels = None
    if manual_grade is not None:
        labels = EpisodeOutcomeLabels.model_validate({"manual_grade": manual_grade})
    AgentEpisodeRepository(db).append(
        AgentEpisodeCreate(
            episode_id=episode_id,
            run_id=run_id,
            mode="analysis",
            symbol="600519",
            market="cn",
            started_at=_started(),
            completed_at=_started(),
            success=True,
            outcome_labels=labels,
        )
    )


def _write_fixture(tmp_path, payload: Any, name: str = "grades.json") -> str:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


class _ExecAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def exec_driver_sql(self, statement, parameters=None):
        return self._connection.exec_driver_sql(statement, parameters)

    def execute(self, statement, parameters=None):
        return self._connection.execute(statement, parameters)


def _episode_row(db: DatabaseManager, episode_id: str) -> Any:
    with db.get_session() as session:
        return session.execute(
            text(
                "SELECT episode_id, run_id, outcome_labels_json, created_at "
                "FROM agent_episodes WHERE episode_id = :episode_id"
            ),
            {"episode_id": episode_id},
        ).one()


def test_fresh_database_applies_curator_grade_schema(isolated_db) -> None:
    inspector = inspect(isolated_db._engine)
    assert "agent_episode_curator_grades" in inspector.get_table_names()
    with isolated_db._engine.connect() as connection:
        ddl = str(
            connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'agent_episode_curator_grades'"
            ).scalar_one()
        )
    assert "ck_agent_episode_curator_grades_grade" in ddl
    assert "uix_agent_episode_curator_grades_episode" in ddl
    assert get_migrations()[-1].id == AGENT_CURATOR_GRADE_SCHEMA_MIGRATION.id
    with isolated_db.get_session() as session:
        applied = session.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"),
            {"version": AGENT_CURATOR_GRADE_SCHEMA_MIGRATION.id},
        ).scalar_one()
    assert applied == 1


def test_migration_upgrade_is_idempotent_and_downgrade_drops_sidecar(isolated_db) -> None:
    engine = isolated_db._engine
    with engine.begin() as connection:
        adapter = _ExecAdapter(connection)
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_episode_curator_grades" in names
        assert "agent_episodes" in names
        migration_mod.downgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_episode_curator_grades" not in names
        assert "agent_episodes" in names
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        assert "agent_episode_curator_grades" in inspect(connection).get_table_names()


def test_upsert_merges_same_episode(isolated_db) -> None:
    _append_episode(isolated_db)
    repo = AgentCuratorGradeRepository(isolated_db)
    first = repo.upsert(
        episode_id="ep-1",
        run_id="run-1",
        manual_grade="pass",
    )
    second = repo.upsert(
        episode_id="ep-1",
        run_id="run-1",
        manual_grade="fail",
    )
    assert first.manual_grade == "pass"
    assert first.provenance_source == "operator"
    assert second.manual_grade == "fail"
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_curator_grades")
        ).scalar_one()
    assert count == 1
    other = repo.upsert(
        episode_id="ep-2",
        run_id="run-2",
        manual_grade="partial",
    )
    assert other.episode_id == "ep-2"
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_curator_grades")
        ).scalar_one()
    assert count == 2


def test_unknown_token_is_rejected(isolated_db) -> None:
    repo = AgentCuratorGradeRepository(isolated_db)
    with pytest.raises(ValueError, match="unsupported manual_grade"):
        repo.upsert(
            episode_id="ep-1",
            run_id="run-1",
            manual_grade="moonshot",
        )
    with pytest.raises(ValueError, match="unsupported manual_grade"):
        validate_curator_grade("alpha")
    with pytest.raises(ValueError, match="unsupported manual_grade"):
        normalize_curator_grade("wrong")
    labels = EpisodeOutcomeLabels.model_validate({"manual_grade": "wrong"})
    assert labels.manual_grade == "wrong"
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_curator_grades")
        ).scalar_one()
    assert count == 0


def test_missing_grade_is_absence_not_neutral_write(isolated_db, tmp_path) -> None:
    _append_episode(isolated_db)
    fixture = _write_fixture(
        tmp_path,
        {
            "version": "curator_grade/1.0",
            "grades": [
                {"episode_id": "ep-1", "run_id": "run-1"},
                {"episode_id": "ep-1", "run_id": "run-1", "manual_grade": ""},
                {"episode_id": "ep-1", "run_id": "run-1", "manual_grade": None},
            ],
        },
    )
    summary = CuratorGradeIngester(db_manager=isolated_db).ingest(fixture=fixture)
    assert summary.scanned == 3
    assert summary.labeled == 0
    assert summary.skipped_missing_grade == 3
    assert summary.noop is True
    assert AgentCuratorGradeRepository(isolated_db).get_by_episode_id("ep-1") is None
    assert normalize_curator_grade("") is None
    assert normalize_curator_grade(None) is None
    assert normalize_curator_grade("   ") is None


def test_ingester_upserts_allowlisted_grade_from_fixture(isolated_db, tmp_path) -> None:
    _append_episode(isolated_db)
    fixture = _write_fixture(
        tmp_path,
        {
            "version": "curator_grade/1.0",
            "grades": [
                {"episode_id": "ep-1", "run_id": "run-1", "manual_grade": "PASS"},
            ],
        },
    )
    summary = CuratorGradeIngester(db_manager=isolated_db).ingest(fixture=fixture)
    assert summary.labeled == 1
    assert summary.noop is False
    record = AgentCuratorGradeRepository(isolated_db).get_by_episode_id("ep-1")
    assert record is not None
    assert record.manual_grade == "pass"
    assert record.run_id == "run-1"
    assert record.provenance_source == "operator"


def test_unknown_token_fails_closed_without_partial_write(
    isolated_db, tmp_path
) -> None:
    _append_episode(isolated_db, episode_id="ep-1")
    _append_episode(isolated_db, episode_id="ep-2", run_id="run-2")
    fixture = _write_fixture(
        tmp_path,
        [
            {"episode_id": "ep-1", "manual_grade": "pass"},
            {"episode_id": "ep-2", "manual_grade": "moonshot"},
        ],
    )
    with pytest.raises(ValueError, match="unsupported manual_grade"):
        CuratorGradeIngester(db_manager=isolated_db).ingest(fixture=fixture)
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_curator_grades")
        ).scalar_one()
    assert count == 0


def test_missing_episode_skips_without_write(isolated_db, tmp_path) -> None:
    fixture = _write_fixture(
        tmp_path,
        {"grades": [{"episode_id": "missing-ep", "manual_grade": "pass"}]},
    )
    summary = CuratorGradeIngester(db_manager=isolated_db).ingest(fixture=fixture)
    assert summary.labeled == 0
    assert summary.skipped_missing_episode == 1
    assert AgentCuratorGradeRepository(isolated_db).get_by_episode_id(
        "missing-ep"
    ) is None


def test_ingester_does_not_mutate_episode_rows(isolated_db, tmp_path) -> None:
    _append_episode(isolated_db, manual_grade="partial")
    before = _episode_row(isolated_db, "ep-1")
    fixture = _write_fixture(
        tmp_path,
        {"grades": [{"episode_id": "ep-1", "manual_grade": "fail"}]},
    )
    CuratorGradeIngester(db_manager=isolated_db).ingest(fixture=fixture)
    after = _episode_row(isolated_db, "ep-1")
    assert after.outcome_labels_json == before.outcome_labels_json
    assert after.created_at == before.created_at
    episode = AgentEpisodeRepository(isolated_db).get_by_episode_id("ep-1")
    assert episode is not None
    assert episode.outcome_labels is not None
    assert episode.outcome_labels.manual_grade == "partial"
    sidecar = AgentCuratorGradeRepository(isolated_db).get_by_episode_id("ep-1")
    assert sidecar is not None
    assert sidecar.manual_grade == "fail"
    with isolated_db.get_session() as session:
        with pytest.raises(IntegrityError, match="append-only"):
            session.execute(
                text(
                    "UPDATE agent_episodes SET outcome_labels_json = :payload "
                    "WHERE episode_id = :episode_id"
                ),
                {
                    "payload": '{"manual_grade":"pass"}',
                    "episode_id": "ep-1",
                },
            )
            session.commit()


def test_historical_wrong_manual_grade_still_reads_while_cli_rejects(
    isolated_db, tmp_path, capsys
) -> None:
    _append_episode(isolated_db, manual_grade="wrong")
    episode = AgentEpisodeRepository(isolated_db).get_by_episode_id("ep-1")
    assert episode is not None
    assert episode.outcome_labels is not None
    assert episode.outcome_labels.manual_grade == "wrong"
    labels = EpisodeOutcomeLabels.model_validate({"manual_grade": "wrong"})
    assert labels.manual_grade == "wrong"
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_curator_grades")
        ).scalar_one()
    assert count == 0
    fixture = _write_fixture(
        tmp_path,
        {"grades": [{"episode_id": "ep-1", "manual_grade": "wrong"}]},
    )
    exit_code = label_cli.main(["--fixture", fixture])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "unsupported manual_grade" in err
    assert AgentCuratorGradeRepository(isolated_db).get_by_episode_id("ep-1") is None


def test_dry_run_does_not_write(isolated_db, tmp_path) -> None:
    _append_episode(isolated_db)
    fixture = _write_fixture(
        tmp_path,
        {"grades": [{"episode_id": "ep-1", "manual_grade": "pass"}]},
    )
    summary = CuratorGradeIngester(db_manager=isolated_db).ingest(
        fixture=fixture, dry_run=True
    )
    assert summary.labeled == 1
    assert summary.dry_run is True
    assert AgentCuratorGradeRepository(isolated_db).get_by_episode_id("ep-1") is None


def test_run_id_mismatch_fails_closed_without_write(isolated_db, tmp_path) -> None:
    _append_episode(isolated_db)
    fixture = _write_fixture(
        tmp_path,
        {"grades": [{"episode_id": "ep-1", "run_id": "other-run", "manual_grade": "pass"}]},
    )
    with pytest.raises(ValueError, match="does not match episode"):
        CuratorGradeIngester(db_manager=isolated_db).ingest(fixture=fixture)
    assert AgentCuratorGradeRepository(isolated_db).get_by_episode_id("ep-1") is None


def test_cli_rejects_unknown_token_without_touching_db(
    isolated_db, tmp_path, capsys
) -> None:
    fixture = _write_fixture(
        tmp_path,
        {"grades": [{"episode_id": "ep-1", "manual_grade": "alpha"}]},
    )
    exit_code = label_cli.main(["--fixture", fixture])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "unsupported manual_grade" in err


def test_episode_table_projection_still_lacks_curator_grade_writer() -> None:
    names = {column.name for column in agent_episodes_table.columns}
    assert "manual_grade" not in names
    assert "outcome_labels_json" in names
