# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Replace legacy intelligence_items url uniqueness with the scoped unique key."""

from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202607190005_intelligence_item_unique_index"
DESCRIPTION = "Rebuild legacy intelligence_items to the scoped composite unique key"

_TABLE = "intelligence_items"
_SCOPED_UNIQUE_INDEX = "uix_intel_item_scope"
_SCOPED_UNIQUE_COLUMNS = ("source_id", "url", "scope_type", "scope_value", "market")
_LEGACY_URL_UNIQUE_COLUMNS = ("url",)

# Frozen column order mirrored from the IntelligenceItem model, used to copy
# every row into the rebuilt table.
_COLUMNS = (
    "id",
    "source_id",
    "source_name",
    "source_type",
    "title",
    "summary",
    "url",
    "source",
    "published_at",
    "fetched_at",
    "scope_type",
    "scope_value",
    "market",
    "raw_payload",
)

# Frozen create_all-equivalent DDL for the rebuilt table. Column affinities,
# NOT NULL flags, the primary key, and the SET NULL foreign key match the model
# so the baseline proof accepts the rebuilt shape. scope_value is NOT NULL here;
# migration 202607190004 backfills null/blank scopes before this runs.
_TABLE_DDL = (
    'CREATE TABLE "{name}" ('
    "id INTEGER NOT NULL, "
    "source_id INTEGER, "
    "source_name VARCHAR(100), "
    "source_type VARCHAR(32) NOT NULL, "
    "title VARCHAR(300) NOT NULL, "
    "summary TEXT, "
    "url VARCHAR(1000) NOT NULL, "
    "source VARCHAR(100), "
    "published_at DATETIME, "
    "fetched_at DATETIME, "
    "scope_type VARCHAR(32) NOT NULL, "
    "scope_value VARCHAR(64) NOT NULL, "
    "market VARCHAR(32) NOT NULL, "
    "raw_payload TEXT, "
    "PRIMARY KEY (id), "
    "FOREIGN KEY(source_id) REFERENCES intelligence_sources (id) ON DELETE SET NULL"
    ")"
)

# Non-unique indexes recreated after the rebuild so the fresh and legacy shapes
# stay consistent (create_all builds all of these for fresh databases).
_INDEXES = (
    ("ix_intelligence_items_source_id", ("source_id",)),
    ("ix_intelligence_items_source_name", ("source_name",)),
    ("ix_intelligence_items_source_type", ("source_type",)),
    ("ix_intelligence_items_url", ("url",)),
    ("ix_intelligence_items_published_at", ("published_at",)),
    ("ix_intelligence_items_fetched_at", ("fetched_at",)),
    ("ix_intelligence_items_scope_type", ("scope_type",)),
    ("ix_intelligence_items_scope_value", ("scope_value",)),
    ("ix_intelligence_items_market", ("market",)),
    (
        "ix_intel_item_scope_time",
        ("scope_type", "scope_value", "market", "published_at"),
    ),
    ("ix_intel_item_fetch_time", ("fetched_at",)),
)


def _table_exists(connection: Connection) -> bool:
    rows = connection.exec_driver_sql(
        "SELECT 1 FROM sqlite_master "
        f"WHERE type = 'table' AND name = '{_TABLE}'"
    ).fetchall()
    return bool(rows)


def _unique_index_column_sets(connection: Connection) -> list:
    """Return the column tuple of every unique index on the table."""
    unique_sets = []
    for row in connection.exec_driver_sql(
        f"PRAGMA index_list({_TABLE})"
    ).fetchall():
        if int(row[2]) != 1:
            continue
        index_name = str(row[1])
        columns = tuple(
            str(info[2])
            for info in connection.exec_driver_sql(
                f'PRAGMA index_xinfo("{index_name}")'
            ).fetchall()
            if info[2] is not None
        )
        if columns:
            unique_sets.append(columns)
    return unique_sets


def _create_scoped_unique_index(connection: Connection) -> None:
    connection.exec_driver_sql(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{_SCOPED_UNIQUE_INDEX}" '
        f"ON {_TABLE} ({', '.join(_SCOPED_UNIQUE_COLUMNS)})"
    )


def _rebuild(connection: Connection) -> None:
    temporary_table = "intelligence_items_migrate_tmp"
    column_list = ", ".join(f'"{column}"' for column in _COLUMNS)
    connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{temporary_table}"')
    connection.exec_driver_sql(_TABLE_DDL.format(name=temporary_table))
    connection.exec_driver_sql(
        f'INSERT INTO "{temporary_table}" ({column_list}) '
        f"SELECT {column_list} FROM {_TABLE}"
    )
    connection.exec_driver_sql(f"DROP TABLE {_TABLE}")
    connection.exec_driver_sql(
        f'ALTER TABLE "{temporary_table}" RENAME TO {_TABLE}'
    )
    for index_name, index_columns in _INDEXES:
        connection.exec_driver_sql(
            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
            f"ON {_TABLE} ({', '.join(index_columns)})"
        )
    _create_scoped_unique_index(connection)


def upgrade(connection: Connection) -> None:
    """Ensure the scoped composite unique key, rebuilding away legacy url uniqueness.

    Table, column, and index names are authored constants. The rebuild copies
    every row into a fresh table shaped like the model, so it is safe to re-run:
    once the scoped unique index exists this migration returns immediately.
    """
    if not _table_exists(connection):
        # Fresh databases create intelligence_items with the scoped unique key
        # through metadata create_all.
        return

    unique_sets = _unique_index_column_sets(connection)
    if any(columns == _SCOPED_UNIQUE_COLUMNS for columns in unique_sets):
        return

    has_legacy_url_unique = any(
        columns == _LEGACY_URL_UNIQUE_COLUMNS for columns in unique_sets
    )
    if unique_sets and not has_legacy_url_unique:
        # Some other unique shape exists; add the scoped uniqueness directly
        # instead of rebuilding around an unknown constraint.
        _create_scoped_unique_index(connection)
        return

    _rebuild(connection)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
