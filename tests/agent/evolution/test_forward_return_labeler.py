# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic no-network tests for the #1096 forward-return sidecar labeler."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from src.config import Config
from src.migrations.registry import (
    AGENT_CURATOR_GRADE_SCHEMA_MIGRATION,
    AGENT_EVOLUTION_EVENT_SCHEMA_MIGRATION,
    AGENT_FORWARD_RETURN_SCHEMA_MIGRATION,
    get_migrations,
)
from src.migrations.versions import (
    v202608250001_agent_forward_return_schema as migration_mod,
)
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_episode_tables import agent_episodes_table
from src.repositories.agent_forward_return_repo import (
    AgentForwardReturnRepository,
    validate_forward_return_bucket,
)
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.prediction_actuals import ACTUALS_STATUS_DATA_UNAVAILABLE, ACTUALS_STATUS_OK
from src.services.forward_return_labeler import (
    ForwardReturnLabeler,
    bucket_for_return_pct,
)
from src.storage import DatabaseManager
from scripts import label_forward_returns as label_cli


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "forward-return.db"
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
    symbol: Optional[str] = "600519",
    market: Optional[str] = "cn",
) -> None:
    AgentEpisodeRepository(db).append(
        AgentEpisodeCreate(
            episode_id=episode_id,
            run_id=run_id,
            mode="analysis",
            symbol=symbol,
            market=market,
            started_at=_started(),
            completed_at=_started(),
            success=True,
        )
    )


def _window(_episode: Any, horizon: str) -> Optional[Tuple[date, date]]:
    if horizon == "5d":
        return date(2026, 8, 10), date(2026, 8, 17)
    return date(2026, 8, 10), date(2026, 8, 11)


class _StubBar:
    def __init__(self, close: float) -> None:
        self.close = close


class _StubSnapshot:
    def __init__(
        self,
        *,
        status: str,
        return_pct: Optional[float] = None,
        as_of_bar: Any = None,
        end_bar: Any = None,
    ) -> None:
        self.status = status
        self.return_pct = return_pct
        self.as_of_bar = as_of_bar
        self.end_bar = end_bar
        self.ok = status == ACTUALS_STATUS_OK


def _ok_snapshot(return_pct: float) -> _StubSnapshot:
    return _StubSnapshot(
        status=ACTUALS_STATUS_OK,
        return_pct=return_pct,
        as_of_bar=_StubBar(100.0),
        end_bar=_StubBar(100.0 + return_pct),
    )


class _RecordingFetcher:
    def __init__(self, snapshot: _StubSnapshot) -> None:
        self.snapshot = snapshot
        self.calls: List[Dict[str, Any]] = []

    def fetch(self, **kwargs: Any) -> _StubSnapshot:
        self.calls.append(kwargs)
        return self.snapshot


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


def test_fresh_database_applies_forward_return_schema(isolated_db) -> None:
    inspector = inspect(isolated_db._engine)
    assert "agent_episode_forward_returns" in inspector.get_table_names()
    with isolated_db._engine.connect() as connection:
        ddl = str(
            connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' "
                "AND name = 'agent_episode_forward_returns'"
            ).scalar_one()
        )
    assert "ck_agent_episode_forward_returns_bucket" in ddl
    assert "uix_agent_episode_forward_returns_episode_horizon" in ddl
    assert get_migrations()[-1].id == AGENT_EVOLUTION_EVENT_SCHEMA_MIGRATION.id
    assert AGENT_FORWARD_RETURN_SCHEMA_MIGRATION.id in {
        migration.id for migration in get_migrations()
    }
    with isolated_db.get_session() as session:
        applied = session.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE version = :version"),
            {"version": AGENT_FORWARD_RETURN_SCHEMA_MIGRATION.id},
        ).scalar_one()
    assert applied == 1


def test_migration_upgrade_is_idempotent_and_downgrade_drops_sidecar(isolated_db) -> None:
    engine = isolated_db._engine
    with engine.begin() as connection:
        adapter = _ExecAdapter(connection)
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_episode_forward_returns" in names
        assert "agent_episodes" in names
        migration_mod.downgrade(adapter)  # type: ignore[arg-type]
        names = inspect(connection).get_table_names()
        assert "agent_episode_forward_returns" not in names
        assert "agent_episodes" in names
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        assert "agent_episode_forward_returns" in inspect(connection).get_table_names()


def test_upsert_merges_same_episode_horizon(isolated_db) -> None:
    _append_episode(isolated_db)
    repo = AgentForwardReturnRepository(isolated_db)
    first = repo.upsert(
        episode_id="ep-1",
        run_id="run-1",
        horizon="1d",
        forward_return_bucket="1d_up",
    )
    second = repo.upsert(
        episode_id="ep-1",
        run_id="run-1",
        horizon="1d",
        forward_return_bucket="1d_down",
    )
    assert first.forward_return_bucket == "1d_up"
    assert first.provenance_source == "system_resolve"
    assert second.forward_return_bucket == "1d_down"
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_forward_returns")
        ).scalar_one()
    assert count == 1
    five = repo.upsert(
        episode_id="ep-1",
        run_id="run-1",
        horizon="5d",
        forward_return_bucket="5d_flat",
    )
    assert five.horizon == "5d"
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_forward_returns")
        ).scalar_one()
    assert count == 2


def test_unknown_bucket_is_rejected(isolated_db) -> None:
    repo = AgentForwardReturnRepository(isolated_db)
    with pytest.raises(ValueError, match="unsupported forward_return_bucket"):
        repo.upsert(
            episode_id="ep-1",
            run_id="run-1",
            horizon="1d",
            forward_return_bucket="1d_moonshot",
        )
    with pytest.raises(ValueError, match="unsupported forward_return_bucket"):
        validate_forward_return_bucket("alpha")
    with pytest.raises(ValueError, match="does not match horizon"):
        repo.upsert(
            episode_id="ep-1",
            run_id="run-1",
            horizon="1d",
            forward_return_bucket="5d_up",
        )
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_forward_returns")
        ).scalar_one()
    assert count == 0


def test_labeler_upserts_allowlisted_bucket_from_actuals(isolated_db) -> None:
    _append_episode(isolated_db)
    fetcher = _RecordingFetcher(_ok_snapshot(1.5))
    labeler = ForwardReturnLabeler(
        db_manager=isolated_db,
        fetcher=fetcher,
        resolve_window=_window,
    )
    summary = labeler.label(as_of="2026-08-25", horizons=("1d",))
    assert summary.labeled == 1
    assert summary.noop is False
    assert summary.skipped_missing_bars == 0
    record = AgentForwardReturnRepository(isolated_db).get_by_episode_horizon(
        "ep-1", "1d"
    )
    assert record is not None
    assert record.forward_return_bucket == "1d_up"
    assert record.run_id == "run-1"
    assert fetcher.calls[0]["symbol"] == "600519"
    assert fetcher.calls[0]["end"] == date(2026, 8, 11)
    assert bucket_for_return_pct("1d", 0.0) == "1d_flat"
    assert bucket_for_return_pct("5d", -0.4) == "5d_down"


def test_missing_bars_skip_without_write(isolated_db) -> None:
    _append_episode(isolated_db)
    fetcher = _RecordingFetcher(
        _StubSnapshot(status=ACTUALS_STATUS_DATA_UNAVAILABLE)
    )
    labeler = ForwardReturnLabeler(
        db_manager=isolated_db,
        fetcher=fetcher,
        resolve_window=_window,
    )
    summary = labeler.label(as_of="2026-08-25", horizons=("1d",))
    assert summary.labeled == 0
    assert summary.skipped_missing_bars == 1
    assert AgentForwardReturnRepository(isolated_db).get_by_episode_horizon(
        "ep-1", "1d"
    ) is None
    assert fetcher.calls, "fetcher must be consulted before skipping"


def test_labeler_does_not_mutate_episode_rows(isolated_db) -> None:
    _append_episode(isolated_db)
    before = _episode_row(isolated_db, "ep-1")
    labeler = ForwardReturnLabeler(
        db_manager=isolated_db,
        fetcher=_RecordingFetcher(_ok_snapshot(2.0)),
        resolve_window=_window,
    )
    labeler.label(as_of="2026-08-25", horizons=("1d",))
    after = _episode_row(isolated_db, "ep-1")
    assert after.outcome_labels_json == before.outcome_labels_json
    assert after.created_at == before.created_at
    episode = AgentEpisodeRepository(isolated_db).get_by_episode_id("ep-1")
    assert episode is not None
    assert episode.outcome_labels is None
    with isolated_db.get_session() as session:
        with pytest.raises(IntegrityError, match="append-only"):
            session.execute(
                text(
                    "UPDATE agent_episodes SET outcome_labels_json = :payload "
                    "WHERE episode_id = :episode_id"
                ),
                {
                    "payload": '{"forward_return_bucket":"1d_up"}',
                    "episode_id": "ep-1",
                },
            )
            session.commit()


def test_noop_when_no_matching_episode(isolated_db) -> None:
    def _boom(**_kwargs: Any) -> Any:
        raise AssertionError("fetcher must not run when no episodes match")

    labeler = ForwardReturnLabeler(
        db_manager=isolated_db,
        fetch_fn=_boom,
        resolve_window=_window,
    )
    summary = labeler.label(as_of="2026-08-25", run_id="missing-run")
    assert summary.noop is True
    assert summary.scanned == 0
    assert summary.labeled == 0
    with isolated_db.get_session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM agent_episode_forward_returns")
        ).scalar_one()
    assert count == 0


def test_dry_run_does_not_write(isolated_db) -> None:
    _append_episode(isolated_db)
    labeler = ForwardReturnLabeler(
        db_manager=isolated_db,
        fetcher=_RecordingFetcher(_ok_snapshot(1.0)),
        resolve_window=_window,
    )
    summary = labeler.label(as_of="2026-08-25", horizons=("1d",), dry_run=True)
    assert summary.labeled == 1
    assert summary.dry_run is True
    assert AgentForwardReturnRepository(isolated_db).get_by_episode_horizon(
        "ep-1", "1d"
    ) is None


def test_horizon_not_due_is_skipped(isolated_db) -> None:
    _append_episode(isolated_db)
    labeler = ForwardReturnLabeler(
        db_manager=isolated_db,
        fetch_fn=lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("not-due windows must not fetch")
        ),
        resolve_window=_window,
    )
    summary = labeler.label(as_of="2026-08-10", horizons=("1d",))
    assert summary.skipped_not_due == 1
    assert summary.labeled == 0


def test_cli_rejects_invalid_as_of_without_touching_db(isolated_db, capsys) -> None:
    exit_code = label_cli.main(["--as-of", "not-a-date"])
    assert exit_code == 2
    err = capsys.readouterr().err
    assert "as_of must be YYYY-MM-DD" in err


def test_episode_table_projection_still_lacks_forward_return_writer() -> None:
    names = {column.name for column in agent_episodes_table.columns}
    assert "forward_return_bucket" not in names
    assert "outcome_labels_json" in names
