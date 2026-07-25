# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create versioned personal investment framework storage."""

from sqlalchemy.engine import Connection

from src.migrations.legacy_profiles import (
    _conflict_policies,
    _ddl_tokens,
    sqlite_type_affinity,
)
from src.migrations.types import Migration


MIGRATION_ID = "202607240003_investment_framework_schema"
DESCRIPTION = "Create versioned personal investment framework storage"

_FRAMEWORK_TABLE = "investment_frameworks"
_VERSION_TABLE = "investment_framework_versions"
_TARGET_TABLES = (_FRAMEWORK_TABLE, _VERSION_TABLE)
_EXPECTED_AUTOINDEXES = {
    _FRAMEWORK_TABLE: "sqlite_autoindex_investment_frameworks_1",
    _VERSION_TABLE: "sqlite_autoindex_investment_framework_versions_1",
}
_FRAMEWORK_COLUMN_SHAPE = (
    ("id", "INTEGER", True, None, 1),
    ("scope_key", "TEXT", True, None, 0),
    ("latest_version", "INTEGER", True, None, 0),
    ("active_version", "INTEGER", False, None, 0),
    ("revision", "INTEGER", True, None, 0),
    ("created_at", "NUMERIC", True, None, 0),
    ("updated_at", "NUMERIC", True, None, 0),
)
_VERSION_COLUMN_SHAPE = (
    ("id", "INTEGER", True, None, 1),
    ("framework_id", "INTEGER", True, None, 0),
    ("version", "INTEGER", True, None, 0),
    ("content_json", "TEXT", True, None, 0),
    ("change_summary", "TEXT", False, None, 0),
    ("created_at", "NUMERIC", True, None, 0),
)
_FRAMEWORK_UNIQUE_KEYS = {
    ("u", False, (("scope_key", "BINARY", False),)),
}
_VERSION_UNIQUE_KEYS = {
    (
        "u",
        False,
        (
            ("framework_id", "BINARY", False),
            ("version", "BINARY", False),
        ),
    ),
}
_FORBIDDEN_DDL_TOKENS = frozenset(
    {
        "AUTOINCREMENT",
        "CHECK",
        "COLLATE",
        "DEFERRABLE",
        "GENERATED",
        "INITIALLY",
        "MATCH",
        "STORED",
        "VIRTUAL",
    }
)

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


def _create_sql(connection: Connection, table_name: str) -> str:
    row = connection.exec_driver_sql(
        "SELECT sql AS create_sql FROM sqlite_master "
        "WHERE type = 'table' AND name = ?",
        (table_name,),
    ).mappings().one_or_none()
    if row is None or row["create_sql"] is None:
        raise RuntimeError("Investment framework table DDL is unavailable")
    return str(row["create_sql"])


def _column_shape(connection: Connection, table_name: str) -> tuple:
    rows = connection.exec_driver_sql(
        f'PRAGMA main.table_xinfo("{table_name}")'
    ).fetchall()
    if any(len(row) < 7 or int(row[6]) != 0 for row in rows):
        raise RuntimeError("Investment framework schema has hidden columns")
    return tuple(
        (
            str(row[1]),
            sqlite_type_affinity(str(row[2] or "")),
            bool(row[3]),
            None if row[4] is None else str(row[4]),
            int(row[5]),
        )
        for row in rows
    )


def _unique_keys(connection: Connection, table_name: str) -> set:
    result = set()
    for row in connection.exec_driver_sql(
        f'PRAGMA main.index_list("{table_name}")'
    ).fetchall():
        origin = str(row[3]).lower()
        if not bool(row[2]) or origin == "pk":
            continue
        terms = connection.exec_driver_sql(
            f'PRAGMA main.index_xinfo("{str(row[1])}")'
        ).fetchall()
        result.add(
            (
                origin,
                bool(row[4]) if len(row) > 4 else False,
                tuple(
                    (
                        None if term[2] is None else str(term[2]),
                        str(term[4] or "BINARY").upper(),
                        bool(term[3]),
                    )
                    for term in terms
                    if bool(term[5])
                ),
            )
        )
    return result


def _has_primary_key_backing_index(
    connection: Connection,
    table_name: str,
) -> bool:
    return any(
        str(row[3]).lower() == "pk"
        for row in connection.exec_driver_sql(
            f'PRAGMA main.index_list("{table_name}")'
        ).fetchall()
    )


def _table_options(
    connection: Connection,
    table_name: str,
    create_sql: str,
) -> tuple:
    rows = connection.exec_driver_sql("PRAGMA table_list").fetchall()
    for row in rows:
        if (
            str(row[0]) == "main"
            and str(row[1]) == table_name
            and str(row[2]).lower() == "table"
        ):
            if len(row) < 6:
                break
            return bool(row[4]), bool(row[5])
    tokens = _ddl_tokens(create_sql)
    without_rowid = any(
        current == "WITHOUT" and following == "ROWID"
        for current, following in zip(tokens, tokens[1:])
    )
    return without_rowid, tokens[-1:] == ("STRICT",)


def _verify_ddl_semantics(
    create_sql: str,
    *,
    error_label: str,
    expected_keyword_counts: dict[str, int],
) -> None:
    tokens = _ddl_tokens(create_sql)
    if _conflict_policies(create_sql):
        raise RuntimeError(
            f"Investment framework {error_label} conflict policies are invalid"
        )
    forbidden_tokens = sorted(_FORBIDDEN_DDL_TOKENS.intersection(tokens))
    if forbidden_tokens:
        raise RuntimeError(
            f"Investment framework {error_label} DDL clauses are invalid"
        )
    if any(
        tokens.count(keyword) != expected_count
        for keyword, expected_count in expected_keyword_counts.items()
    ):
        raise RuntimeError(
            f"Investment framework {error_label} constraint declarations are invalid"
        )


def _verify_schema_object_inventory(connection: Connection) -> None:
    parameters = (*_TARGET_TABLES, *_TARGET_TABLES)
    query = (
        "SELECT type, name, tbl_name, sql FROM {master} "
        "WHERE name IN (?, ?) OR tbl_name IN (?, ?) ORDER BY type, name"
    )
    main_objects = connection.exec_driver_sql(
        query.format(master="sqlite_master"),
        parameters,
    ).fetchall()
    temp_objects = connection.exec_driver_sql(
        query.format(master="sqlite_temp_master"),
        parameters,
    ).fetchall()
    if temp_objects:
        raise RuntimeError(
            "Investment framework temporary schema objects are invalid"
        )

    for object_type, name, table_name, create_sql in main_objects:
        normalized_type = str(object_type).lower()
        normalized_name = str(name)
        normalized_table = str(table_name)
        if (
            normalized_type == "table"
            and normalized_name == normalized_table
            and normalized_name in _TARGET_TABLES
        ):
            continue
        if (
            normalized_type == "index"
            and normalized_table in _TARGET_TABLES
            and normalized_name == _EXPECTED_AUTOINDEXES[normalized_table]
            and create_sql is None
        ):
            continue
        raise RuntimeError(
            "Investment framework persistent schema objects are invalid"
        )


def _verify_shape(connection: Connection) -> None:
    _verify_schema_object_inventory(connection)
    framework_sql = _create_sql(connection, _FRAMEWORK_TABLE)
    version_sql = _create_sql(connection, _VERSION_TABLE)
    if _column_shape(connection, _FRAMEWORK_TABLE) != _FRAMEWORK_COLUMN_SHAPE:
        raise RuntimeError("Investment framework aggregate schema verification failed")
    if _column_shape(connection, _VERSION_TABLE) != _VERSION_COLUMN_SHAPE:
        raise RuntimeError("Investment framework version schema verification failed")
    if _has_primary_key_backing_index(connection, _FRAMEWORK_TABLE):
        raise RuntimeError("Investment framework aggregate primary key is invalid")
    if _has_primary_key_backing_index(connection, _VERSION_TABLE):
        raise RuntimeError("Investment framework version primary key is invalid")
    if _table_options(
        connection,
        _FRAMEWORK_TABLE,
        framework_sql,
    ) != (False, False):
        raise RuntimeError("Investment framework aggregate table options are invalid")
    if _table_options(
        connection,
        _VERSION_TABLE,
        version_sql,
    ) != (False, False):
        raise RuntimeError("Investment framework version table options are invalid")
    if _unique_keys(connection, _FRAMEWORK_TABLE) != _FRAMEWORK_UNIQUE_KEYS:
        raise RuntimeError("Investment framework scope uniqueness verification failed")
    if _unique_keys(connection, _VERSION_TABLE) != _VERSION_UNIQUE_KEYS:
        raise RuntimeError("Investment framework version uniqueness verification failed")
    _verify_ddl_semantics(
        framework_sql,
        error_label="aggregate",
        expected_keyword_counts={
            "CONSTRAINT": 1,
            "FOREIGN": 0,
            "PRIMARY": 1,
            "REFERENCES": 0,
            "UNIQUE": 1,
        },
    )
    _verify_ddl_semantics(
        version_sql,
        error_label="version",
        expected_keyword_counts={
            "CONSTRAINT": 1,
            "FOREIGN": 1,
            "PRIMARY": 1,
            "REFERENCES": 1,
            "UNIQUE": 1,
        },
    )

    aggregate_foreign_keys = connection.exec_driver_sql(
        f'PRAGMA main.foreign_key_list("{_FRAMEWORK_TABLE}")'
    ).fetchall()
    if aggregate_foreign_keys:
        raise RuntimeError(
            "Investment framework aggregate foreign keys are invalid"
        )

    foreign_keys = connection.exec_driver_sql(
        f'PRAGMA main.foreign_key_list("{_VERSION_TABLE}")'
    ).fetchall()
    expected_key = (
        _FRAMEWORK_TABLE,
        "framework_id",
        "id",
        "NO ACTION",
        "CASCADE",
        "NONE",
    )
    observed_keys = {
        (
            str(row[2]),
            str(row[3]),
            str(row[4]),
            str(row[5]).upper(),
            str(row[6]).upper(),
            str(row[7]).upper(),
        )
        for row in foreign_keys
    }
    if len(foreign_keys) != 1 or observed_keys != {expected_key}:
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
