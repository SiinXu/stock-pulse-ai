# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create durable read-state table for the in-app notification inbox."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608090020_notification_inbox_read_state"
DESCRIPTION = "Create notification_inbox_read_state for in-app inbox read markers"


_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS notification_inbox_read_state (
        item_id VARCHAR(128) NOT NULL PRIMARY KEY,
        kind VARCHAR(32) NOT NULL,
        read_at DATETIME NOT NULL
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_notification_inbox_read_state_kind "
    "ON notification_inbox_read_state (kind)",
    "CREATE INDEX IF NOT EXISTS ix_notification_inbox_read_state_read_at "
    "ON notification_inbox_read_state (read_at)",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive inbox read-state table and indexes (restart-idempotent)."""
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
