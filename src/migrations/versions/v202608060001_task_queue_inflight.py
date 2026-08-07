# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create process-local task-queue in-flight checkpoint table."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608060001_task_queue_inflight"
DESCRIPTION = "Create task_queue_inflight restart-recovery checkpoints"


_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS task_queue_inflight (
        task_id VARCHAR(64) NOT NULL PRIMARY KEY,
        kind VARCHAR(64) NOT NULL,
        status VARCHAR(32) NOT NULL,
        stock_code VARCHAR(32),
        recovery_class VARCHAR(32) NOT NULL,
        dedupe_key VARCHAR(128),
        idempotency_key VARCHAR(128),
        idempotency_fingerprint VARCHAR(128),
        failure_error_code VARCHAR(64),
        none_is_success BOOLEAN NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_task_queue_inflight_status ON task_queue_inflight (status)",
    "CREATE INDEX IF NOT EXISTS ix_task_queue_inflight_kind ON task_queue_inflight (kind)",
    "CREATE INDEX IF NOT EXISTS ix_task_queue_inflight_recovery_class ON task_queue_inflight (recovery_class)",
    "CREATE INDEX IF NOT EXISTS ix_task_queue_inflight_updated_at ON task_queue_inflight (updated_at)",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive checkpoint table and indexes (restart-idempotent)."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
