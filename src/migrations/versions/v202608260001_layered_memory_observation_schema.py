# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create principal-scoped layered memory observation, consent, and audit tables."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608260001_layered_memory_observation_schema"
DESCRIPTION = (
    "Create durable PrincipalMemoryLifecycle observation, consent, and audit store"
)


_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS layered_memory_observations (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        schema_version VARCHAR(32) NOT NULL,
        principal_id VARCHAR(128) NOT NULL,
        analysis_history_id INTEGER NOT NULL,
        stock_code VARCHAR(32) NOT NULL,
        observed_at DATETIME NOT NULL,
        expires_at DATETIME,
        signal VARCHAR(8) NOT NULL,
        sentiment_score FLOAT NOT NULL,
        price_at_analysis FLOAT NOT NULL,
        outcome_id INTEGER,
        outcome_horizon_days INTEGER,
        evaluated_at DATETIME,
        was_correct BOOLEAN,
        provenance_source VARCHAR(32) NOT NULL,
        actor_id VARCHAR(128),
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_layered_memory_observations_principal_history
            UNIQUE (principal_id, analysis_history_id),
        CONSTRAINT ck_layered_memory_observations_signal
            CHECK (signal IN ('buy', 'hold', 'sell')),
        CONSTRAINT ck_layered_memory_observations_provenance
            CHECK (provenance_source IN ('system_resolve', 'user_feedback', 'operator')),
        CONSTRAINT ck_layered_memory_observations_horizon
            CHECK (
                outcome_horizon_days IS NULL
                OR outcome_horizon_days IN (5, 20)
            )
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS layered_memory_consent (
        principal_id VARCHAR(128) NOT NULL PRIMARY KEY,
        granted_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS layered_memory_access_audit (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        event_id VARCHAR(64) NOT NULL,
        principal_id VARCHAR(128) NOT NULL,
        action VARCHAR(32) NOT NULL,
        at DATETIME NOT NULL,
        detail VARCHAR(200) NOT NULL DEFAULT '',
        resource_count INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL,
        CONSTRAINT uix_layered_memory_access_audit_event_id UNIQUE (event_id),
        CONSTRAINT ck_layered_memory_access_audit_action
            CHECK (action IN (
                'consent_grant',
                'consent_revoke',
                'collect',
                'project',
                'export',
                'delete',
                'clear',
                'expire'
            ))
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_layered_memory_observations_principal_observed "
    "ON layered_memory_observations (principal_id, observed_at, analysis_history_id)",
    "CREATE INDEX IF NOT EXISTS ix_layered_memory_observations_principal_expires "
    "ON layered_memory_observations (principal_id, expires_at)",
    "CREATE INDEX IF NOT EXISTS ix_layered_memory_observations_principal_stock "
    "ON layered_memory_observations (principal_id, stock_code, observed_at)",
    "CREATE INDEX IF NOT EXISTS ix_layered_memory_access_audit_principal_at "
    "ON layered_memory_access_audit (principal_id, at, id)",
)

_TRIGGER_STATEMENTS = (
    """
    CREATE TRIGGER IF NOT EXISTS trg_layered_memory_access_audit_no_update
    BEFORE UPDATE ON layered_memory_access_audit
    BEGIN
        SELECT RAISE(ABORT, 'layered_memory_access_audit is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_layered_memory_access_audit_no_delete
    BEFORE DELETE ON layered_memory_access_audit
    BEGIN
        SELECT RAISE(ABORT, 'layered_memory_access_audit is append-only');
    END
    """,
)

_DROP_STATEMENTS = (
    "DROP TRIGGER IF EXISTS trg_layered_memory_access_audit_no_delete",
    "DROP TRIGGER IF EXISTS trg_layered_memory_access_audit_no_update",
    "DROP INDEX IF EXISTS ix_layered_memory_access_audit_principal_at",
    "DROP INDEX IF EXISTS ix_layered_memory_observations_principal_stock",
    "DROP INDEX IF EXISTS ix_layered_memory_observations_principal_expires",
    "DROP INDEX IF EXISTS ix_layered_memory_observations_principal_observed",
    "DROP TABLE IF EXISTS layered_memory_access_audit",
    "DROP TABLE IF EXISTS layered_memory_consent",
    "DROP TABLE IF EXISTS layered_memory_observations",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive layered-memory tables, indexes, and audit immutability."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _TRIGGER_STATEMENTS:
        execution.exec_driver_sql(statement)


def downgrade(execution: MigrationExecution) -> None:
    """Drop only this slice's tables, indexes, and triggers."""
    for statement in _DROP_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
