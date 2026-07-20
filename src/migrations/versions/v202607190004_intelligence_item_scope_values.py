# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Normalize legacy intelligence_items scope_value so scoped unique keys work."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202607190004_intelligence_item_scope_values"
DESCRIPTION = "Backfill null/blank intelligence_items scope_value to the null-scope sentinel"

_TABLE = "intelligence_items"
# Frozen sentinel mirrored from INTELLIGENCE_ITEM_NULL_SCOPE_VALUE. Legacy rows
# with a NULL or blank scope_value are normalized to this value so the scoped
# unique key treats "no scope" as a single concrete value instead of many
# distinct NULLs.
_NULL_SCOPE_VALUE = "__dsa_null_scope__"


def _table_columns(connection: Connection) -> set:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({_TABLE})").fetchall()
    return {str(row[1]) for row in rows}


def upgrade(connection: Connection) -> None:
    """Normalize NULL/blank scope_value rows to the frozen null-scope sentinel.

    The sentinel and column name are authored constants. Updating only NULL or
    blank rows keeps the migration idempotent under the runner's serialized
    re-execution; fresh databases default the column and have nothing to fix.
    """
    if "scope_value" not in _table_columns(connection):
        # No intelligence_items table or no scope_value column to normalize.
        # Fresh databases create the column with a NOT NULL default.
        return
    connection.execute(
        text(
            f"UPDATE {_TABLE} SET scope_value = :scope_value "
            "WHERE scope_value IS NULL OR scope_value = ''"
        ),
        {"scope_value": _NULL_SCOPE_VALUE},
    )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
