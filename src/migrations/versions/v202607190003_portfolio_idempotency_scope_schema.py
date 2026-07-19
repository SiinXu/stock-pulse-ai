# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Add Portfolio idempotency scope columns, unique index, and legacy guard."""

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202607190003_portfolio_idempotency_scope_schema"
DESCRIPTION = "Add portfolio idempotency scope columns, unique index, and guard trigger"

_TABLE = "portfolio_idempotency_records"

# Scope columns reproduced from the PortfolioIdempotencyRecord model. Fresh
# databases receive them and the unique index through metadata create_all;
# legacy databases created before scoped idempotency need them added here.
_SCOPE_COLUMNS = (
    ("client_operation_id", "VARCHAR(128)"),
    ("scope_key", "VARCHAR(64)"),
    ("scope_account_id", "INTEGER"),
    ("scope_owner_id", "VARCHAR(64)"),
)
_SCOPE_UNIQUE_INDEX = "uix_portfolio_idempotency_scope_operation"
_SCOPE_UNIQUE_INDEX_COLUMNS = ("operation_type", "scope_key", "client_operation_id")
_LEGACY_GUARD_TRIGGER = "trg_portfolio_idempotency_legacy_key_guard"


def _table_columns(connection: Connection) -> set:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({_TABLE})").fetchall()
    return {str(row[1]) for row in rows}


def _index_columns(connection: Connection, index_name: str) -> tuple:
    rows = connection.exec_driver_sql(
        f'PRAGMA index_info("{index_name}")'
    ).fetchall()
    return tuple(str(row[2]) for row in rows)


def _index_is_unique(connection: Connection, index_name: str) -> bool:
    for row in connection.exec_driver_sql(
        f"PRAGMA index_list({_TABLE})"
    ).fetchall():
        if str(row[1]) == index_name:
            return bool(row[2])
    return False


def _scoped_storage_id(
    *,
    operation_type: str,
    scope_key: str,
    client_operation_id: str,
) -> str:
    """Reproduce the frozen v2 physical idempotency key at authoring time."""
    payload = {
        "client_operation_id": client_operation_id,
        "operation_type": operation_type,
        "scope_key": scope_key,
        "version": 2,
    }
    serialized = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return "v2:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _backfill_legacy_scopes(connection: Connection) -> None:
    """Keep raw-key legacy rows outside the scoped lookup contract."""
    rows = connection.exec_driver_sql(
        "SELECT id, operation_id, operation_type, client_operation_id, scope_key "
        f"FROM {_TABLE} ORDER BY id"
    ).fetchall()
    for record_id, operation_id, operation_type, client_operation_id, scope_key in rows:
        operation_id = str(operation_id)
        if (
            client_operation_id
            and scope_key
            and operation_id
            == _scoped_storage_id(
                operation_type=str(operation_type),
                scope_key=str(scope_key),
                client_operation_id=str(client_operation_id),
            )
        ):
            continue
        # A raw operation_id cannot prove the owner at write time, so keep the
        # record for rollback compatibility but leave it outside the scoped
        # lookup contract; it can never cross owner boundaries.
        legacy_client_operation_id = str(client_operation_id or operation_id)
        connection.execute(
            text(
                f"UPDATE {_TABLE} SET "
                "client_operation_id = :client_operation_id, "
                "scope_key = NULL, "
                "scope_account_id = NULL, "
                "scope_owner_id = NULL "
                "WHERE id = :record_id"
            ),
            {
                "client_operation_id": legacy_client_operation_id,
                "record_id": record_id,
            },
        )


def upgrade(connection: Connection) -> None:
    """Add scope columns, normalize legacy rows, then add the index and guard.

    Column, index, and trigger names are authored constants, so composing DDL
    with them is safe. Backfilling before the unique index and only rewriting
    rows that are not already scoped keeps the migration idempotent under the
    runner's serialized re-execution.
    """
    columns = _table_columns(connection)
    if not columns:
        # No table to upgrade. Fresh databases create it with the scope columns,
        # unique index, and guard trigger through metadata create_all.
        return

    for column_name, column_type in _SCOPE_COLUMNS:
        if column_name in columns:
            continue
        connection.exec_driver_sql(
            f"ALTER TABLE {_TABLE} ADD COLUMN {column_name} {column_type}"
        )

    _backfill_legacy_scopes(connection)

    connection.exec_driver_sql(
        f'CREATE UNIQUE INDEX IF NOT EXISTS "{_SCOPE_UNIQUE_INDEX}" '
        f"ON {_TABLE} ({', '.join(_SCOPE_UNIQUE_INDEX_COLUMNS)})"
    )
    if (
        _index_columns(connection, _SCOPE_UNIQUE_INDEX)
        != _SCOPE_UNIQUE_INDEX_COLUMNS
        or not _index_is_unique(connection, _SCOPE_UNIQUE_INDEX)
    ):
        raise RuntimeError(
            "Portfolio idempotency scope index verification failed: "
            f"index={_SCOPE_UNIQUE_INDEX}"
        )

    connection.exec_driver_sql(
        f'CREATE TRIGGER IF NOT EXISTS "{_LEGACY_GUARD_TRIGGER}" '
        f"BEFORE INSERT ON {_TABLE} "
        "FOR EACH ROW "
        "WHEN NEW.client_operation_id IS NULL "
        "AND NEW.scope_key IS NULL "
        f"AND EXISTS (SELECT 1 FROM {_TABLE} "
        "WHERE client_operation_id = NEW.operation_id "
        "AND scope_key IS NOT NULL) "
        "BEGIN "
        "SELECT RAISE(ABORT, 'legacy idempotency key conflicts with scoped record'); "
        "END"
    )
    guard_rows = connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' "
        f"AND name = '{_LEGACY_GUARD_TRIGGER}'"
    ).fetchall()
    if not guard_rows:
        raise RuntimeError(
            "Portfolio legacy idempotency guard trigger verification failed"
        )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
