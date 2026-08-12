# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create agent_predictions table for forecast verification persistence."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608120001_agent_prediction_schema"
DESCRIPTION = "Create agent_predictions table with due-scan and status indexes"

# Status set covers Issue #1112 (pending/resolved/data_unavailable + resolving)
# and remains open for the A1 PredictionRecord statuses (expired/error/
# no_verifiable_claim) so contract and persistence can land independently.
_STATUS_CHECK = (
    "'pending', 'resolving', 'resolved', 'data_unavailable', "
    "'expired', 'error', 'no_verifiable_claim'"
)

_TABLE_STATEMENTS = (
    f"""
    CREATE TABLE IF NOT EXISTS agent_predictions (
        prediction_id VARCHAR(64) NOT NULL PRIMARY KEY,
        run_id VARCHAR(64) NOT NULL,
        symbol VARCHAR(32) NOT NULL,
        market VARCHAR(16) NOT NULL,
        horizon VARCHAR(32) NOT NULL,
        resolve_after DATETIME NOT NULL,
        status VARCHAR(32) NOT NULL,
        lease_owner VARCHAR(128),
        lease_token VARCHAR(64),
        lease_expires_at DATETIME,
        claims_json TEXT NOT NULL,
        outcome_json TEXT,
        model_meta_json TEXT,
        attempts INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        resolved_at DATETIME,
        CONSTRAINT ck_agent_prediction_status
            CHECK (status IN ({_STATUS_CHECK})),
        CONSTRAINT ck_agent_prediction_attempts
            CHECK (attempts >= 0)
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_agent_prediction_status_resolve_after "
    "ON agent_predictions (status, resolve_after)",
    "CREATE INDEX IF NOT EXISTS ix_agent_prediction_symbol_market_created "
    "ON agent_predictions (symbol, market, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_agent_prediction_run_id "
    "ON agent_predictions (run_id)",
    "CREATE INDEX IF NOT EXISTS ix_agent_prediction_lease_expires_at "
    "ON agent_predictions (lease_expires_at)",
)

_TRIGGER_STATEMENTS = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_agent_prediction_resolved_immutable
    BEFORE UPDATE ON agent_predictions
    WHEN OLD.status = 'resolved'
    BEGIN
        SELECT RAISE(ABORT, 'resolved agent_predictions are immutable');
    END
    """,
)

_DROP_STATEMENTS = (
    "DROP TRIGGER IF EXISTS trg_agent_prediction_resolved_immutable",
    "DROP INDEX IF EXISTS ix_agent_prediction_lease_expires_at",
    "DROP INDEX IF EXISTS ix_agent_prediction_run_id",
    "DROP INDEX IF EXISTS ix_agent_prediction_symbol_market_created",
    "DROP INDEX IF EXISTS ix_agent_prediction_status_resolve_after",
    "DROP TABLE IF EXISTS agent_predictions",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive prediction table, indexes, and terminal guard (idempotent)."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _TRIGGER_STATEMENTS:
        execution.exec_driver_sql(statement)


def downgrade(execution: MigrationExecution) -> None:
    """Drop agent_predictions objects. Call only after stopping prediction writers."""
    for statement in _DROP_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
