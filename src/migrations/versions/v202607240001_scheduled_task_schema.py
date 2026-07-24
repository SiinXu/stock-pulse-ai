# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create the versioned scheduled-task definition and run-record tables."""

from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202607240001_scheduled_task_schema"
DESCRIPTION = "Create scheduled task definition and run record tables"

_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS scheduled_tasks (
        id VARCHAR(32) NOT NULL PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        name VARCHAR(128) NOT NULL,
        task_type VARCHAR(32) NOT NULL,
        schedule_kind VARCHAR(16) NOT NULL,
        schedule_time VARCHAR(5) NOT NULL,
        timezone VARCHAR(64) NOT NULL,
        calendar_market VARCHAR(8) NOT NULL,
        non_trading_day_policy VARCHAR(16) NOT NULL,
        payload_json TEXT NOT NULL,
        enabled BOOLEAN NOT NULL,
        max_attempts INTEGER NOT NULL,
        next_run_at DATETIME,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scheduled_task_runs (
        id VARCHAR(32) NOT NULL PRIMARY KEY,
        task_id VARCHAR(32) NOT NULL,
        scheduled_for DATETIME NOT NULL,
        status VARCHAR(16) NOT NULL,
        attempt_count INTEGER NOT NULL,
        execution_task_ids_json TEXT NOT NULL,
        owned_execution_task_ids_json TEXT NOT NULL,
        result_refs_json TEXT NOT NULL,
        error_code VARCHAR(64),
        next_attempt_at DATETIME,
        started_at DATETIME,
        finished_at DATETIME,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_scheduled_task_run_occurrence
            UNIQUE (task_id, scheduled_for),
        FOREIGN KEY(task_id) REFERENCES scheduled_tasks (id) ON DELETE CASCADE
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_task_type ON scheduled_tasks (task_type)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_enabled ON scheduled_tasks (enabled)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_next_run_at ON scheduled_tasks (next_run_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_created_at ON scheduled_tasks (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_tasks_updated_at ON scheduled_tasks (updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_due ON scheduled_tasks (enabled, next_run_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_runs_task_id ON scheduled_task_runs (task_id)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_runs_scheduled_for ON scheduled_task_runs (scheduled_for)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_runs_status ON scheduled_task_runs (status)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_runs_error_code ON scheduled_task_runs (error_code)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_runs_next_attempt_at ON scheduled_task_runs (next_attempt_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_runs_finished_at ON scheduled_task_runs (finished_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_runs_created_at ON scheduled_task_runs (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_runs_updated_at ON scheduled_task_runs (updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_task_run_active ON scheduled_task_runs (status, next_attempt_at)",
)


def upgrade(connection: Connection) -> None:
    """Create additive tables and indexes when metadata has not done so."""
    for statement in _TABLE_STATEMENTS:
        connection.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        connection.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
