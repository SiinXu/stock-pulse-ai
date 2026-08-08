# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create watchlist group and membership tables for organized watchlists."""

from src.migrations.types import Migration, MigrationExecution


MIGRATION_ID = "202608090001_watchlist_groups_schema"
DESCRIPTION = "Create watchlist groups and membership tables"

_TABLE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS watchlist_groups (
        id INTEGER NOT NULL PRIMARY KEY,
        group_key VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        sort_order INTEGER NOT NULL,
        is_default BOOLEAN NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_watchlist_groups_group_key UNIQUE (group_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist_group_members (
        id INTEGER NOT NULL PRIMARY KEY,
        group_id INTEGER NOT NULL,
        stock_code VARCHAR(32) NOT NULL,
        sort_order INTEGER NOT NULL,
        attrs_json TEXT NOT NULL DEFAULT '{}',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        CONSTRAINT uix_watchlist_group_member UNIQUE (group_id, stock_code),
        FOREIGN KEY(group_id) REFERENCES watchlist_groups (id) ON DELETE CASCADE
    )
    """,
)

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_watchlist_groups_sort_order "
    "ON watchlist_groups (sort_order)",
    "CREATE INDEX IF NOT EXISTS ix_watchlist_groups_is_default "
    "ON watchlist_groups (is_default)",
    "CREATE INDEX IF NOT EXISTS ix_watchlist_group_members_group_id "
    "ON watchlist_group_members (group_id)",
    "CREATE INDEX IF NOT EXISTS ix_watchlist_group_members_stock_code "
    "ON watchlist_group_members (stock_code)",
    "CREATE INDEX IF NOT EXISTS ix_watchlist_group_members_group_sort "
    "ON watchlist_group_members (group_id, sort_order)",
)

_DROP_STATEMENTS = (
    "DROP TABLE IF EXISTS watchlist_group_members",
    "DROP TABLE IF EXISTS watchlist_groups",
)


def upgrade(execution: MigrationExecution) -> None:
    """Create additive watchlist group tables and indexes (restart-idempotent)."""
    for statement in _TABLE_STATEMENTS:
        execution.exec_driver_sql(statement)
    for statement in _INDEX_STATEMENTS:
        execution.exec_driver_sql(statement)


def downgrade(execution: MigrationExecution) -> None:
    """Drop watchlist group tables. Membership data is removed; STOCK_LIST is untouched."""
    for statement in _DROP_STATEMENTS:
        execution.exec_driver_sql(statement)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
