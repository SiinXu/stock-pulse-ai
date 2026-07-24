# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create versioned personal investment framework storage."""

from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202607240002_investment_framework_schema"
DESCRIPTION = "Create versioned personal investment framework storage"

_FRAMEWORK_TABLE = "investment_frameworks"
_VERSION_TABLE = "investment_framework_versions"
_FRAMEWORK_COLUMNS = (
    "id",
    "scope_key",
    "latest_version",
    "active_version",
    "revision",
    "created_at",
    "updated_at",
)
_VERSION_COLUMNS = (
    "id",
    "framework_id",
    "version",
    "content_json",
    "change_summary",
    "created_at",
)
_FRAMEWORK_UNIQUE_COLUMNS = ("scope_key",)
_VERSION_UNIQUE_COLUMNS = ("framework_id", "version")

_FRAMEWORK_DDL = (
    "CREATE TABLE investment_frameworks ("
    "id INTEGER NOT NULL, "
    "scope_key VARCHAR(32) NOT NULL, "
    "latest_version INTEGER NOT NULL, "
    "active_version INTEGER, "
    "revision INTEGER NOT NULL, "
    "created_at DATETIME NOT NULL, "
    "updated_at DATETIME NOT NULL, "
    "PRIMARY KEY (id), "
    "CONSTRAINT uix_investment_framework_scope UNIQUE (scope_key)"
    ")"
)
_VERSION_DDL = (
    "CREATE TABLE investment_framework_versions ("
    "id INTEGER NOT NULL, "
    "framework_id INTEGER NOT NULL, "
    "version INTEGER NOT NULL, "
    "content_json TEXT NOT NULL, "
    "change_summary VARCHAR(500), "
    "created_at DATETIME NOT NULL, "
    "PRIMARY KEY (id), "
    "CONSTRAINT uix_investment_framework_version "
    "UNIQUE (framework_id, version), "
    "FOREIGN KEY(framework_id) REFERENCES investment_frameworks (id) "
    "ON DELETE CASCADE"
    ")"
)


def _table_exists(connection: Connection, table_name: str) -> bool:
    row = connection.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).mappings().one_or_none()
    return row is not None


def _column_names(connection: Connection, table_name: str) -> tuple:
    rows = connection.exec_driver_sql(
        f'PRAGMA table_info("{table_name}")'
    ).fetchall()
    return tuple(str(row[1]) for row in rows)


def _unique_column_sets(connection: Connection, table_name: str) -> set:
    result = set()
    for row in connection.exec_driver_sql(
        f'PRAGMA index_list("{table_name}")'
    ).fetchall():
        if not bool(row[2]):
            continue
        columns = connection.exec_driver_sql(
            f'PRAGMA index_info("{str(row[1])}")'
        ).fetchall()
        result.add(tuple(str(column[2]) for column in columns))
    return result


def _verify_shape(connection: Connection) -> None:
    if _column_names(connection, _FRAMEWORK_TABLE) != _FRAMEWORK_COLUMNS:
        raise RuntimeError("Investment framework aggregate schema verification failed")
    if _column_names(connection, _VERSION_TABLE) != _VERSION_COLUMNS:
        raise RuntimeError("Investment framework version schema verification failed")
    if _FRAMEWORK_UNIQUE_COLUMNS not in _unique_column_sets(
        connection,
        _FRAMEWORK_TABLE,
    ):
        raise RuntimeError("Investment framework scope uniqueness verification failed")
    if _VERSION_UNIQUE_COLUMNS not in _unique_column_sets(
        connection,
        _VERSION_TABLE,
    ):
        raise RuntimeError("Investment framework version uniqueness verification failed")

    foreign_keys = connection.exec_driver_sql(
        f'PRAGMA foreign_key_list("{_VERSION_TABLE}")'
    ).fetchall()
    expected_key = (
        _FRAMEWORK_TABLE,
        "framework_id",
        "id",
        "CASCADE",
    )
    observed_keys = {
        (str(row[2]), str(row[3]), str(row[4]), str(row[6]).upper())
        for row in foreign_keys
    }
    if expected_key not in observed_keys:
        raise RuntimeError("Investment framework version foreign key verification failed")


def upgrade(connection: Connection) -> None:
    """Create both framework tables and verify their immutable key shape."""
    framework_exists = _table_exists(connection, _FRAMEWORK_TABLE)
    version_exists = _table_exists(connection, _VERSION_TABLE)
    if framework_exists != version_exists:
        raise RuntimeError("Investment framework storage is only partially present")
    if not framework_exists:
        connection.exec_driver_sql(_FRAMEWORK_DDL)
        connection.exec_driver_sql(_VERSION_DDL)
    _verify_shape(connection)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
