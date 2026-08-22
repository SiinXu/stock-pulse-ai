# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Real-SQLite tests for agent_prediction persistence (Issue #1112)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from src.config import Config
from src.migrations.registry import (
    AGENT_PREDICTION_SCHEMA_MIGRATION,
    MEMORY_WRITE_PROVENANCE_MIGRATION,
    get_migrations,
)
from src.migrations.runner import MigrationRunner
from src.migrations.versions import v202608130001_agent_prediction_schema as migration_mod
from src.repositories.agent_prediction_repo import (
    AgentPredictionRepository,
    _is_unique_or_primary_key_conflict,
)
from src.repositories.base import RepositoryError
from src.schemas.agent_prediction import (
    AGENT_PREDICTION_STATUSES,
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    STATUS_RESOLVING,
    AgentPredictionInsert,
)
from src.schemas.prediction_record import (
    PredictionRecord,
    build_no_verifiable_claim_record,
)
from src.storage import DatabaseManager


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "agent-prediction.db"
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
    return datetime(2026, 8, 12, 12, 0, 0)


def _direction_claim(direction: str = "up") -> dict:
    return {
        "claim_id": "direction-0",
        "type": "direction",
        "confidence": 0.7,
        "payload": {"direction": direction},
    }


def _insert(
    repo: AgentPredictionRepository,
    *,
    prediction_id: str = "pred-1",
    resolve_after: Optional[datetime] = None,
    symbol: str = "600519",
    market: str = "cn",
) -> None:
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id="run-1",
            symbol=symbol,
            market=market,
            as_of=_fixed_now().date(),
            horizon="5d",
            resolve_after=resolve_after or (_fixed_now() - timedelta(hours=1)),
            claims=[_direction_claim()],
            model_meta={"mode": "analysis"},
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


def _index_names(engine, table: str) -> set[str]:
    inspector = inspect(engine)
    return {str(item["name"]) for item in inspector.get_indexes(table)}


class _ExecAdapter:
    """Minimal MigrationExecution stand-in for direct upgrade/downgrade tests."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def exec_driver_sql(self, statement, parameters=None):
        return self._connection.exec_driver_sql(statement, parameters)

    def execute(self, statement, parameters=None):
        return self._connection.execute(statement, parameters)


def test_fresh_database_manager_applies_prediction_schema(isolated_db) -> None:
    inspector = inspect(isolated_db._engine)
    assert "agent_predictions" in inspector.get_table_names()
    ddl = _table_sql(isolated_db._engine, "agent_predictions")
    assert "ck_agent_prediction_status" in ddl
    assert "ck_agent_prediction_attempts" in ddl
    assert "ck_agent_prediction_claims_json" in ddl
    assert "ck_agent_prediction_lease_state" in ddl
    assert "ck_agent_prediction_outcome_state" in ddl
    assert "ck_agent_prediction_resolved_at" in ddl
    assert "ck_agent_prediction_no_verifiable_reason" in ddl
    assert "data_unavailable" in ddl
    assert "as_of DATE" in ddl
    # A1 PredictionRecord allows prediction_id/run_id up to 128 characters.
    assert "prediction_id VARCHAR(128)" in ddl
    assert "run_id VARCHAR(128)" in ddl
    indexes = _index_names(isolated_db._engine, "agent_predictions")
    assert {
        "ix_agent_prediction_status_resolve_after",
        "ix_agent_prediction_symbol_market_created",
        "ix_agent_prediction_run_id",
        "ix_agent_prediction_lease_expires_at",
    } <= indexes
    with isolated_db.get_session() as session:
        applied = session.execute(
            text(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = :version"
            ),
            {"version": AGENT_PREDICTION_SCHEMA_MIGRATION.id},
        ).scalar_one()
    assert applied == 1
    assert AGENT_PREDICTION_SCHEMA_MIGRATION.id in {
        migration.id for migration in get_migrations()
    }
    assert get_migrations()[-1].id == MEMORY_WRITE_PROVENANCE_MIGRATION.id


def test_due_query_uses_status_resolve_after_index(isolated_db) -> None:
    """Acceptance: due scans use index-friendly predicates (EXPLAIN)."""
    with isolated_db.get_session() as session:
        plan_rows = session.execute(
            text(
                "EXPLAIN QUERY PLAN "
                "SELECT prediction_id FROM agent_predictions "
                "WHERE status IN ('pending', 'data_unavailable') "
                "AND resolve_after <= :as_of "
                "ORDER BY resolve_after, prediction_id "
                "LIMIT 10"
            ),
            {"as_of": _fixed_now()},
        ).fetchall()
    plan_text = " ".join(str(row) for row in plan_rows).lower()
    assert "ix_agent_prediction_status_resolve_after" in plan_text


def test_migration_applies_on_existing_database_without_predictions(
    tmp_path, monkeypatch
) -> None:
    """Existing fully-migrated DB missing agent_predictions is repaired additively."""
    db_path = tmp_path / "existing.sqlite"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    first = DatabaseManager.get_instance()
    # Seed an unrelated business row so we can prove the upgrade is non-destructive.
    with first.get_session() as session:
        session.execute(
            text(
                "INSERT INTO stock_daily (code, date, close) "
                "VALUES ('600519', '2026-08-01', 100.0)"
            )
        )
        session.commit()
    DatabaseManager.reset_instance()

    # Simulate a pre-A3 database: drop prediction objects and un-stamp the migration.
    engine = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER IF EXISTS trg_agent_prediction_resolved_immutable"
            )
            connection.exec_driver_sql("DROP TABLE IF EXISTS agent_predictions")
            connection.exec_driver_sql(
                "DELETE FROM schema_migrations WHERE version = :version",
                {"version": AGENT_PREDICTION_SCHEMA_MIGRATION.id},
            )
            connection.exec_driver_sql(
                "DELETE FROM schema_migrations WHERE version = :version",
                {"version": MEMORY_WRITE_PROVENANCE_MIGRATION.id},
            )
            tables = {
                row[0]
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "agent_predictions" not in tables
            assert "stock_daily" in tables

        result = MigrationRunner().apply_pending(engine)
        assert result.success is True
        assert AGENT_PREDICTION_SCHEMA_MIGRATION.id in result.executed_ids
        assert MEMORY_WRITE_PROVENANCE_MIGRATION.id in result.executed_ids
        inspector = inspect(engine)
        assert "agent_predictions" in inspector.get_table_names()
        assert "ix_agent_prediction_status_resolve_after" in _index_names(
            engine, "agent_predictions"
        )
        with engine.connect() as connection:
            count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM stock_daily WHERE code = '600519'"
            ).scalar_one()
        assert count == 1
        verification = MigrationRunner().verify(engine)
        assert verification.success is True
        assert verification.current_version == MEMORY_WRITE_PROVENANCE_MIGRATION.id
    finally:
        engine.dispose()
        DatabaseManager.reset_instance()
        Config.reset_instance()


def test_migration_upgrade_is_idempotent_and_downgrade_removes_table(
    isolated_db,
) -> None:
    engine = isolated_db._engine
    with engine.begin() as connection:
        adapter = _ExecAdapter(connection)
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        assert "agent_predictions" in inspect(connection).get_table_names()
        migration_mod.downgrade(adapter)  # type: ignore[arg-type]
        assert "agent_predictions" not in inspect(connection).get_table_names()
        migration_mod.upgrade(adapter)  # type: ignore[arg-type]
        assert "agent_predictions" in inspect(connection).get_table_names()


def test_insert_is_idempotent_and_does_not_overwrite(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    first_created, first = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id="pred-dup",
            run_id="run-a",
            symbol="600519",
            market="cn",
            as_of=_fixed_now().date(),
            horizon="5d",
            resolve_after=_fixed_now(),
            claims=[_direction_claim()],
        )
    )
    second_created, second = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id="pred-dup",
            run_id="run-b",
            symbol="AAPL",
            market="us",
            as_of=_fixed_now().date(),
            horizon="1d",
            resolve_after=_fixed_now() + timedelta(days=1),
            claims=[_direction_claim("down")],
        )
    )
    assert first_created is True
    assert second_created is False
    assert second.run_id == first.run_id == "run-a"
    assert second.symbol == "600519"
    assert second.claims[0]["payload"]["direction"] == "up"


def test_real_a1_prediction_round_trips_resolution_metadata(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    source = PredictionRecord.model_validate(
        {
            "prediction_id": "pred-a1",
            "run_id": "run-a1",
            "symbol": "AAPL",
            "market": "US",
            "created_at": datetime(2026, 8, 11, 12, tzinfo=timezone.utc),
            "as_of": "2026-08-11",
            "horizon": "5d",
            "resolve_after": datetime(2026, 8, 18, 12, tzinfo=timezone.utc),
            "claims": [_direction_claim()],
            "status": "pending",
            "source_decision_id": "history-41",
            "model_meta": {
                "mode": "agent",
                "soul_version": "soul-v1",
                "skill_ids": ["trend"],
                "model_id": "model-a",
            },
            "notes": "horizon_source=structured",
        }
    )

    created, stored = repo.insert_pending(
        AgentPredictionInsert.from_prediction_record(source)
    )

    assert created is True
    assert stored.as_of == source.as_of
    assert stored.source_decision_id == "history-41"
    assert stored.model_meta == source.model_meta.model_dump(mode="json")
    assert stored.notes == "horizon_source=structured"
    assert stored.claims == [claim.model_dump(mode="json") for claim in source.claims]

    no_claim = build_no_verifiable_claim_record(
        prediction_id="pred-a1-no-claim",
        run_id="run-a1-no-claim",
        symbol="AAPL",
        market="us",
        created_at=datetime(2026, 8, 11, 12, tzinfo=timezone.utc),
        as_of=source.as_of,
        resolve_after=datetime(2026, 8, 18, 12, tzinfo=timezone.utc),
        reason="prose_only",
    )
    no_claim_created, stored_no_claim = repo.insert_pending(
        AgentPredictionInsert.from_prediction_record(no_claim)
    )
    assert no_claim_created is True
    assert stored_no_claim.status == "no_verifiable_claim"
    assert stored_no_claim.claims == []
    assert stored_no_claim.no_verifiable_reason == "prose_only"


def test_insert_rejects_non_a1_claims_and_invalid_status_claim_pairs(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    base = {
        "prediction_id": "pred-invalid",
        "run_id": "run-invalid",
        "symbol": "600519",
        "market": "cn",
        "as_of": _fixed_now().date(),
        "horizon": "5d",
        "resolve_after": _fixed_now(),
    }

    with pytest.raises(ValueError, match="A1 PredictionClaim"):
        repo.insert_pending(
            AgentPredictionInsert(
                **base,
                claims=[{"type": "direction", "payload": {"side": "up"}}],
            )
        )
    with pytest.raises(ValueError, match="pending predictions require"):
        repo.insert_pending(AgentPredictionInsert(**base, claims=[]))
    with pytest.raises(ValueError, match="no_verifiable_claim requires"):
        repo.insert_pending(
            AgentPredictionInsert(
                **base,
                claims=[],
                status="no_verifiable_claim",
            )
        )


def test_accepts_a1_max_length_ids_and_normalizes_market(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    prediction_id = "p" * 128
    run_id = "r" * 128
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id=run_id,
            symbol="600519",
            market="CN",
            as_of=_fixed_now().date(),
            horizon="5d",
            resolve_after=_fixed_now(),
            claims=[_direction_claim()],
        )
    )
    assert created is True
    assert record.prediction_id == prediction_id
    assert record.run_id == run_id
    assert record.market == "cn"
    listed = repo.list_by_symbol_market(symbol="600519", market="CN")
    assert [row.prediction_id for row in listed] == [prediction_id]
    with pytest.raises(ValueError, match="at most 128"):
        repo.insert_pending(
            AgentPredictionInsert(
                prediction_id="x" * 129,
                run_id="run",
                symbol="600519",
                market="cn",
                as_of=_fixed_now().date(),
                horizon="5d",
                resolve_after=_fixed_now(),
                claims=[],
            )
        )


def test_check_constraint_failure_is_not_treated_as_collision(
    isolated_db, monkeypatch
) -> None:
    """Counterexample: IntegrityError from CHECK must not look like PK race."""
    assert _is_unique_or_primary_key_conflict(
        Exception("UNIQUE constraint failed: agent_predictions.prediction_id")
    )
    assert not _is_unique_or_primary_key_conflict(
        Exception("CHECK constraint failed: ck_agent_prediction_status")
    )
    assert not _is_unique_or_primary_key_conflict(
        Exception("NOT NULL constraint failed: agent_predictions.claims_json")
    )

    # Expand the Python allowlist so the DB CHECK is the failing layer.
    monkeypatch.setattr(
        "src.repositories.agent_prediction_repo.AGENT_PREDICTION_STATUSES",
        frozenset(AGENT_PREDICTION_STATUSES | {"bogus_status"}),
    )
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    with pytest.raises(RepositoryError) as raised:
        repo.insert_pending(
            AgentPredictionInsert(
                prediction_id="pred-check",
                run_id="run-check",
                symbol="600519",
                market="cn",
                as_of=_fixed_now().date(),
                horizon="5d",
                resolve_after=_fixed_now(),
                claims=[_direction_claim()],
                status="bogus_status",
            )
        )
    assert raised.value.error_code == "agent_prediction_insert_constraint"
    assert repo.get("pred-check") is None


def test_due_query_and_symbol_market_list(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert(
        repo,
        prediction_id="due-1",
        resolve_after=_fixed_now() - timedelta(minutes=5),
    )
    _insert(
        repo,
        prediction_id="future-1",
        resolve_after=_fixed_now() + timedelta(days=2),
    )
    _insert(
        repo,
        prediction_id="other-1",
        symbol="AAPL",
        market="us",
        resolve_after=_fixed_now() - timedelta(minutes=1),
    )

    due = repo.list_due(as_of=_fixed_now(), limit=10)
    due_ids = {row.prediction_id for row in due}
    assert "due-1" in due_ids
    assert "other-1" in due_ids
    assert "future-1" not in due_ids

    cn_rows = repo.list_by_symbol_market(symbol="600519", market="cn", limit=10)
    assert {row.prediction_id for row in cn_rows} == {"due-1", "future-1"}


def test_claim_resolve_and_data_unavailable_state_machine(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert(repo, prediction_id="pred-sm")

    claimed = repo.claim_for_resolve(
        prediction_id="pred-sm",
        lease_owner="worker-a",
        lease_token="token-a",
        as_of=_fixed_now(),
    )
    assert claimed is not None
    assert claimed.status == STATUS_RESOLVING
    assert claimed.lease_owner == "worker-a"
    assert claimed.attempts == 1

    lost = repo.claim_for_resolve(
        prediction_id="pred-sm",
        lease_owner="worker-b",
        lease_token="token-b",
        as_of=_fixed_now(),
    )
    assert lost is None

    # Lease ownership is enforced, not merely documented.
    with pytest.raises(ValueError, match="expected_lease_token is required"):
        repo.mark_data_unavailable(
            prediction_id="pred-sm",
            reason="missing_token",
            as_of=_fixed_now(),
        )
    unbound_resolve_ok, _ = repo.resolve(
        prediction_id="pred-sm",
        outcome={"label": "hit", "score": 1.0},
        as_of=_fixed_now(),
    )
    assert unbound_resolve_ok is False

    wrong_token_ok, _ = repo.mark_data_unavailable(
        prediction_id="pred-sm",
        reason="should_fail",
        expected_lease_token="token-b",
        as_of=_fixed_now(),
    )
    assert wrong_token_ok is False
    assert repo.get("pred-sm").status == STATUS_RESOLVING  # type: ignore[union-attr]

    unavailable_ok, unavailable = repo.mark_data_unavailable(
        prediction_id="pred-sm",
        reason="provider_timeout",
        expected_lease_token="token-a",
        as_of=_fixed_now(),
        outcome={"label": "hit", "score": 1.0, "diagnostic": "timeout"},
    )
    assert unavailable_ok is True
    assert unavailable is not None
    assert unavailable.status == STATUS_DATA_UNAVAILABLE
    assert unavailable.outcome is not None
    assert unavailable.outcome["label"] == STATUS_DATA_UNAVAILABLE
    assert unavailable.outcome["reason"] == "provider_timeout"
    assert unavailable.outcome["diagnostic"] == "timeout"
    assert "score" not in unavailable.outcome
    assert repo.list_due(as_of=_fixed_now()) == []

    requeued_ok, requeued = repo.requeue_pending(
        prediction_id="pred-sm",
        as_of=_fixed_now(),
    )
    assert requeued_ok is True
    assert requeued is not None
    assert requeued.status == STATUS_PENDING
    assert requeued.outcome is None

    claimed2 = repo.claim_for_resolve(
        prediction_id="pred-sm",
        lease_owner="worker-c",
        lease_token="token-c",
        as_of=_fixed_now(),
    )
    assert claimed2 is not None
    applied, resolved = repo.resolve(
        prediction_id="pred-sm",
        outcome={"label": "hit", "score": 1.0},
        expected_lease_token="token-c",
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED
    assert resolved.outcome == {"label": "hit", "score": 1.0}
    assert resolved.resolved_at == _fixed_now()

    applied2, again = repo.resolve(
        prediction_id="pred-sm",
        outcome={"label": "miss", "score": 0.0},
        as_of=_fixed_now() + timedelta(seconds=1),
    )
    assert applied2 is False
    assert again is not None
    assert again.outcome == {"label": "hit", "score": 1.0}

    with pytest.raises(IntegrityError, match="resolved agent_predictions are immutable"):
        with isolated_db.session_scope() as session:
            session.execute(
                text(
                    "UPDATE agent_predictions SET status = 'pending' "
                    "WHERE prediction_id = :prediction_id"
                ),
                {"prediction_id": "pred-sm"},
            )


def test_concurrent_resolve_only_one_writer_wins(isolated_db) -> None:
    """Persistence-layer race: many threads resolve the same row; one outcome sticks."""
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert(repo, prediction_id="pred-race")
    claimed = repo.claim_for_resolve(
        prediction_id="pred-race",
        lease_owner="starter",
        lease_token="shared",
        as_of=_fixed_now(),
    )
    assert claimed is not None

    def _attempt(worker_id: int) -> Tuple[bool, Optional[str]]:
        worker_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
        applied, record = worker_repo.resolve(
            prediction_id="pred-race",
            outcome={"label": f"worker-{worker_id}", "worker_id": worker_id},
            expected_lease_token="shared",
            as_of=_fixed_now() + timedelta(milliseconds=worker_id),
        )
        label = None
        if record is not None and record.outcome is not None:
            label = str(record.outcome.get("label"))
        return applied, label

    results: List[Tuple[bool, Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(_attempt, index) for index in range(12)]
        for future in as_completed(futures):
            results.append(future.result())

    winners = [label for applied, label in results if applied]
    assert len(winners) == 1
    final = repo.get("pred-race")
    assert final is not None
    assert final.status == STATUS_RESOLVED
    assert final.outcome is not None
    assert final.outcome["label"] == winners[0]
    observed_labels = {label for _, label in results if label is not None}
    assert observed_labels == {winners[0]}


def test_concurrent_claim_only_one_owner(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert(repo, prediction_id="pred-claim-race")

    def _claim(worker_id: int) -> Optional[str]:
        worker_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
        claimed = worker_repo.claim_for_resolve(
            prediction_id="pred-claim-race",
            lease_owner=f"worker-{worker_id}",
            lease_token=f"token-{worker_id}",
            as_of=_fixed_now(),
        )
        return None if claimed is None else claimed.lease_owner

    owners: List[Optional[str]] = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(_claim, index) for index in range(10)]
        for future in as_completed(futures):
            owners.append(future.result())

    successful = [owner for owner in owners if owner is not None]
    assert len(successful) == 1
    final = repo.get("pred-claim-race")
    assert final is not None
    assert final.status == STATUS_RESOLVING
    assert final.lease_owner == successful[0]
    assert final.attempts == 1


def test_claim_rejects_future_rows_and_expired_lease_cannot_complete(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert(
        repo,
        prediction_id="pred-future",
        resolve_after=_fixed_now() + timedelta(hours=1),
    )
    assert (
        repo.claim_for_resolve(
            prediction_id="pred-future",
            lease_owner="worker-a",
            lease_token="token-a",
            as_of=_fixed_now(),
        )
        is None
    )

    _insert(repo, prediction_id="pred-expired-lease")
    claimed = repo.claim_for_resolve(
        prediction_id="pred-expired-lease",
        lease_owner="worker-a",
        lease_token="token-a",
        lease_ttl_seconds=10,
        as_of=_fixed_now(),
    )
    assert claimed is not None
    applied, still_resolving = repo.resolve(
        prediction_id="pred-expired-lease",
        outcome={"label": "hit", "score": 1.0},
        expected_lease_token="token-a",
        as_of=_fixed_now() + timedelta(seconds=11),
    )
    assert applied is False
    assert still_resolving is not None
    assert still_resolving.status == STATUS_RESOLVING


def test_corrupt_json_is_not_silently_coerced_to_empty_claims(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert(repo, prediction_id="pred-corrupt")
    with isolated_db._engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA ignore_check_constraints = ON")
        connection.exec_driver_sql(
            "UPDATE agent_predictions SET claims_json = 'not-json' "
            "WHERE prediction_id = 'pred-corrupt'"
        )
        connection.exec_driver_sql("PRAGMA ignore_check_constraints = OFF")

    with pytest.raises(RepositoryError) as raised:
        repo.get("pred-corrupt")
    assert raised.value.error_code == "agent_prediction_corrupt_json"
