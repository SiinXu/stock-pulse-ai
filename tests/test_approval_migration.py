"""Migration and restart contracts for approval storage."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from src.migrations.versions.v202607250001_approval_gate_schema import upgrade


def test_approval_migration_is_idempotent_and_has_required_indexes(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'approval.sqlite'}")
    with engine.begin() as connection:
        upgrade(connection)
        upgrade(connection)

    inspector = inspect(engine)
    assert {"approval_rules", "approval_proposals"} <= set(
        inspector.get_table_names()
    )
    rule_uniques = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("approval_rules")
    }
    proposal_uniques = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("approval_proposals")
    }
    assert ("owner_id", "action") in rule_uniques
    assert ("idempotency_key",) in proposal_uniques
    indexes = {
        item["name"] for item in inspector.get_indexes("approval_proposals")
    }
    assert "ix_approval_proposal_owner_status_expiry" in indexes


def test_approval_migration_rejects_same_column_lookalikes_without_keys(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'malformed.sqlite'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE approval_rules ("
            "id INTEGER, owner_id TEXT, action TEXT, enabled BOOLEAN, "
            "risk_sources_json TEXT, expires_in_seconds INTEGER, version INTEGER, "
            "created_at DATETIME, updated_at DATETIME)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE approval_proposals ("
            "id TEXT, owner_id TEXT, action TEXT, risk_source TEXT, status TEXT, "
            "version INTEGER, idempotency_key TEXT, execution_id TEXT, "
            "context_json TEXT, expires_at DATETIME, consumed_at DATETIME, "
            "decided_at DATETIME, created_at DATETIME, updated_at DATETIME)"
        )

    with pytest.raises(RuntimeError, match="verification"):
        with engine.begin() as connection:
            upgrade(connection)

    inspector = inspect(engine)
    assert inspector.get_unique_constraints("approval_rules") == []
    assert inspector.get_unique_constraints("approval_proposals") == []


def test_approval_migration_rejects_partial_preexisting_storage(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'partial.sqlite'}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE approval_rules (id INTEGER NOT NULL PRIMARY KEY)"
        )

    with pytest.raises(RuntimeError, match="partially present"):
        with engine.begin() as connection:
            upgrade(connection)

    assert inspect(engine).get_table_names() == ["approval_rules"]
