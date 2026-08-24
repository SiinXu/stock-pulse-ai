# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create sidecar tables for optional run and prediction user feedback."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608240001_agent_feedback_schema"
DESCRIPTION = "Create agent run and prediction feedback sidecar tables"

_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS agent_run_feedback (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        run_id VARCHAR(128) NOT NULL,
        feedback_value VARCHAR(16) NOT NULL,
        note TEXT,
        source VARCHAR(16) NOT NULL DEFAULT 'api',
        provenance_source VARCHAR(32),
        actor_id VARCHAR(128),
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_agent_run_feedback_run_id UNIQUE (run_id),
        CONSTRAINT ck_agent_run_feedback_value
            CHECK (feedback_value IN ('useful', 'partial', 'wrong', 'harmful')),
        CONSTRAINT ck_agent_run_feedback_source
            CHECK (source IN ('web', 'api'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_prediction_feedback (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        prediction_id VARCHAR(128) NOT NULL,
        run_id VARCHAR(128) NOT NULL,
        feedback_value VARCHAR(16) NOT NULL,
        note TEXT,
        source VARCHAR(16) NOT NULL DEFAULT 'api',
        provenance_source VARCHAR(32),
        actor_id VARCHAR(128),
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_agent_prediction_feedback_prediction_id UNIQUE (prediction_id),
        CONSTRAINT ck_agent_prediction_feedback_value
            CHECK (feedback_value IN (
                'agree_hit', 'agree_miss', 'disagree_score', 'context_note'
            )),
        CONSTRAINT ck_agent_prediction_feedback_source
            CHECK (source IN ('web', 'api'))
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_agent_prediction_feedback_run_id "
    "ON agent_prediction_feedback (run_id)",
)

_DROP_STATEMENTS = (
    "DROP INDEX IF EXISTS ix_agent_prediction_feedback_run_id",
    "DROP TABLE IF EXISTS agent_prediction_feedback",
    "DROP TABLE IF EXISTS agent_run_feedback",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive feedback sidecar tables and indexes (restart-idempotent)."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)


def downgrade(execution: MigrationExecution) -> None:
    """Drop feedback sidecar tables. Prediction actuals and episodes are untouched."""
    for statement in _DROP_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
