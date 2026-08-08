# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create portfolio_health_snapshots for daily health score idempotency."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608090001_portfolio_health_snapshots"
DESCRIPTION = "Create portfolio_health_snapshots daily health score table"


_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS portfolio_health_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_key VARCHAR(32) NOT NULL,
        snapshot_date DATE NOT NULL,
        cost_method VARCHAR(8) NOT NULL DEFAULT 'fifo',
        score FLOAT,
        status VARCHAR(32) NOT NULL,
        band VARCHAR(16),
        payload_json TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
)

_INDEX_STATEMENTS = (
    """
    CREATE UNIQUE INDEX IF NOT EXISTS
    uix_portfolio_health_account_date_method
    ON portfolio_health_snapshots
    (account_key, snapshot_date, cost_method)
    """,
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive health snapshot table and unique index."""
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
