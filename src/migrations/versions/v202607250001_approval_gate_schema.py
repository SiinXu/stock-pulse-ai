# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Create owner-scoped approval rules and durable one-shot proposals."""

from sqlalchemy.engine import Connection

from src.migrations.legacy_profiles import (
    _conflict_policies,
    _ddl_tokens,
    sqlite_type_affinity,
)
from src.migrations.types import Migration


MIGRATION_ID = "202607250001_approval_gate_schema"
DESCRIPTION = "Create Human-in-the-Loop approval gate storage"
_RULE_TABLE = "approval_rules"
_PROPOSAL_TABLE = "approval_proposals"
_TARGET_TABLES = (_RULE_TABLE, _PROPOSAL_TABLE)
_EXPECTED_AUTOINDEXES = {
    _RULE_TABLE: {"sqlite_autoindex_approval_rules_1"},
    _PROPOSAL_TABLE: {
        "sqlite_autoindex_approval_proposals_1",
        "sqlite_autoindex_approval_proposals_2",
    },
}
_RULE_COLUMN_SHAPE = (
    ("id", "INTEGER", True, None, 1),
    ("owner_id", "TEXT", True, None, 0),
    ("action", "TEXT", True, None, 0),
    ("enabled", "NUMERIC", True, None, 0),
    ("risk_sources_json", "TEXT", True, None, 0),
    ("expires_in_seconds", "INTEGER", True, None, 0),
    ("version", "INTEGER", True, None, 0),
    ("created_at", "NUMERIC", True, None, 0),
    ("updated_at", "NUMERIC", True, None, 0),
)
_PROPOSAL_COLUMN_SHAPE = (
    ("id", "TEXT", True, None, 1),
    ("owner_id", "TEXT", True, None, 0),
    ("action", "TEXT", True, None, 0),
    ("risk_source", "TEXT", True, None, 0),
    ("status", "TEXT", True, None, 0),
    ("version", "INTEGER", True, None, 0),
    ("idempotency_key", "TEXT", True, None, 0),
    ("execution_id", "TEXT", True, None, 0),
    ("context_json", "TEXT", True, None, 0),
    ("expires_at", "NUMERIC", True, None, 0),
    ("consumed_at", "NUMERIC", False, None, 0),
    ("decided_at", "NUMERIC", False, None, 0),
    ("created_at", "NUMERIC", True, None, 0),
    ("updated_at", "NUMERIC", True, None, 0),
)
_RULE_UNIQUE_KEYS = {
    ("u", False, (("owner_id", "BINARY", False), ("action", "BINARY", False))),
}
_PROPOSAL_UNIQUE_KEYS = {
    ("u", False, (("idempotency_key", "BINARY", False),)),
}
_EXPECTED_EXPLICIT_INDEXES = {
    "ix_approval_proposals_owner_id": ("owner_id",),
    "ix_approval_proposals_action": ("action",),
    "ix_approval_proposals_risk_source": ("risk_source",),
    "ix_approval_proposals_status": ("status",),
    "ix_approval_proposals_execution_id": ("execution_id",),
    "ix_approval_proposals_expires_at": ("expires_at",),
    "ix_approval_proposal_owner_status_expiry": (
        "owner_id",
        "status",
        "expires_at",
    ),
}
_FORBIDDEN_DDL_TOKENS = frozenset(
    {
        "AUTOINCREMENT",
        "CHECK",
        "COLLATE",
        "DEFERRABLE",
        "FOREIGN",
        "GENERATED",
        "REFERENCES",
        "STRICT",
        "WITHOUT",
    }
)

_RULE_DDL = (
    "CREATE TABLE approval_rules ("
    "id INTEGER NOT NULL, owner_id VARCHAR(128) NOT NULL, "
    "action VARCHAR(64) NOT NULL, enabled BOOLEAN NOT NULL, "
    "risk_sources_json TEXT NOT NULL, expires_in_seconds INTEGER NOT NULL, "
    "version INTEGER NOT NULL, created_at DATETIME NOT NULL, "
    "updated_at DATETIME NOT NULL, PRIMARY KEY (id), "
    "CONSTRAINT uix_approval_rule_owner_action UNIQUE (owner_id, action))"
)
_PROPOSAL_DDL = (
    "CREATE TABLE approval_proposals ("
    "id VARCHAR(32) NOT NULL, owner_id VARCHAR(128) NOT NULL, "
    "action VARCHAR(64) NOT NULL, risk_source VARCHAR(32) NOT NULL, "
    "status VARCHAR(16) NOT NULL, version INTEGER NOT NULL, "
    "idempotency_key VARCHAR(64) NOT NULL, execution_id VARCHAR(128) NOT NULL, "
    "context_json TEXT NOT NULL, expires_at DATETIME NOT NULL, "
    "consumed_at DATETIME, decided_at DATETIME, "
    "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
    "PRIMARY KEY (id), UNIQUE (idempotency_key))"
)
_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_approval_proposals_owner_id "
    "ON approval_proposals (owner_id)",
    "CREATE INDEX IF NOT EXISTS ix_approval_proposals_action "
    "ON approval_proposals (action)",
    "CREATE INDEX IF NOT EXISTS ix_approval_proposals_risk_source "
    "ON approval_proposals (risk_source)",
    "CREATE INDEX IF NOT EXISTS ix_approval_proposals_status "
    "ON approval_proposals (status)",
    "CREATE INDEX IF NOT EXISTS ix_approval_proposals_execution_id "
    "ON approval_proposals (execution_id)",
    "CREATE INDEX IF NOT EXISTS ix_approval_proposals_expires_at "
    "ON approval_proposals (expires_at)",
    "CREATE INDEX IF NOT EXISTS ix_approval_proposal_owner_status_expiry "
    "ON approval_proposals (owner_id, status, expires_at)",
)


def _table_exists(connection: Connection, table_name: str) -> bool:
    rows = connection.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchall()
    return bool(rows)


def _create_sql(connection: Connection, table_name: str) -> str:
    rows = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchall()
    if len(rows) != 1 or rows[0][0] is None:
        raise RuntimeError("Approval table DDL is unavailable")
    return str(rows[0][0])


def _column_shape(connection: Connection, table_name: str) -> tuple:
    rows = connection.exec_driver_sql(
        f'PRAGMA main.table_xinfo("{table_name}")'
    ).fetchall()
    if any(len(row) < 7 or int(row[6]) != 0 for row in rows):
        raise RuntimeError("Approval schema has hidden columns")
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


def _index_terms(connection: Connection, index_name: str) -> tuple:
    return tuple(
        (
            None if row[2] is None else str(row[2]),
            str(row[4] or "BINARY").upper(),
            bool(row[3]),
        )
        for row in connection.exec_driver_sql(
            f'PRAGMA main.index_xinfo("{index_name}")'
        ).fetchall()
        if bool(row[5])
    )


def _unique_keys(connection: Connection, table_name: str) -> set:
    result = set()
    for row in connection.exec_driver_sql(
        f'PRAGMA main.index_list("{table_name}")'
    ).fetchall():
        origin = str(row[3]).lower()
        if not bool(row[2]) or origin == "pk":
            continue
        result.add(
            (
                origin,
                bool(row[4]) if len(row) > 4 else False,
                _index_terms(connection, str(row[1])),
            )
        )
    return result


def _explicit_indexes(connection: Connection) -> dict[str, tuple[str, ...]]:
    result = {}
    for row in connection.exec_driver_sql(
        f'PRAGMA main.index_list("{_PROPOSAL_TABLE}")'
    ).fetchall():
        if str(row[3]).lower() != "c":
            continue
        if bool(row[2]) or (len(row) > 4 and bool(row[4])):
            raise RuntimeError("Approval proposal query index is invalid")
        terms = _index_terms(connection, str(row[1]))
        if any(term[0] is None or term[1:] != ("BINARY", False) for term in terms):
            raise RuntimeError("Approval proposal query index terms are invalid")
        result[str(row[1])] = tuple(str(term[0]) for term in terms)
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


def _verify_object_inventory(connection: Connection) -> None:
    parameters = (*_TARGET_TABLES, *_TARGET_TABLES)
    query = (
        "SELECT type, name, tbl_name, sql FROM {master} "
        "WHERE name IN (?, ?) OR tbl_name IN (?, ?) ORDER BY type, name"
    )
    if connection.exec_driver_sql(
        query.format(master="sqlite_temp_master"),
        parameters,
    ).fetchall():
        raise RuntimeError("Approval temporary schema objects are invalid")
    for object_type, name, table_name, create_sql in connection.exec_driver_sql(
        query.format(master="sqlite_master"),
        parameters,
    ).fetchall():
        kind = str(object_type).lower()
        normalized_name = str(name)
        normalized_table = str(table_name)
        if (
            kind == "table"
            and normalized_name == normalized_table
            and normalized_name in _TARGET_TABLES
        ):
            continue
        if (
            kind == "index"
            and normalized_table in _TARGET_TABLES
            and normalized_name in _EXPECTED_AUTOINDEXES[normalized_table]
            and create_sql is None
        ):
            continue
        if (
            kind == "index"
            and normalized_table == _PROPOSAL_TABLE
            and normalized_name in _EXPECTED_EXPLICIT_INDEXES
            and create_sql is not None
        ):
            continue
        raise RuntimeError("Approval persistent schema objects are invalid")


def _verify_ddl(connection: Connection, table_name: str) -> None:
    create_sql = _create_sql(connection, table_name)
    tokens = _ddl_tokens(create_sql)
    if _conflict_policies(create_sql):
        raise RuntimeError("Approval DDL conflict policies are invalid")
    if _FORBIDDEN_DDL_TOKENS.intersection(tokens):
        raise RuntimeError("Approval DDL clauses are invalid")
    if tokens.count("PRIMARY") != 1 or tokens.count("UNIQUE") != 1:
        raise RuntimeError("Approval DDL constraint declarations are invalid")
    options = connection.exec_driver_sql("PRAGMA table_list").fetchall()
    matching = [
        row
        for row in options
        if str(row[0]) == "main" and str(row[1]) == table_name
    ]
    if len(matching) != 1 or bool(matching[0][4]) or bool(matching[0][5]):
        raise RuntimeError("Approval table options are invalid")
    if connection.exec_driver_sql(
        f'PRAGMA main.foreign_key_list("{table_name}")'
    ).fetchall():
        raise RuntimeError("Approval foreign keys are invalid")


def _verify(connection: Connection) -> None:
    _verify_object_inventory(connection)
    if _column_shape(connection, _RULE_TABLE) != _RULE_COLUMN_SHAPE:
        raise RuntimeError("Approval rule schema verification failed")
    if _column_shape(connection, _PROPOSAL_TABLE) != _PROPOSAL_COLUMN_SHAPE:
        raise RuntimeError("Approval proposal schema verification failed")
    if _has_primary_key_backing_index(connection, _RULE_TABLE):
        raise RuntimeError("Approval rule primary key is invalid")
    if not _has_primary_key_backing_index(connection, _PROPOSAL_TABLE):
        raise RuntimeError("Approval proposal primary key is invalid")
    if _unique_keys(connection, _RULE_TABLE) != _RULE_UNIQUE_KEYS:
        raise RuntimeError("Approval rule uniqueness verification failed")
    if _unique_keys(connection, _PROPOSAL_TABLE) != _PROPOSAL_UNIQUE_KEYS:
        raise RuntimeError("Approval proposal uniqueness verification failed")
    if _explicit_indexes(connection) != _EXPECTED_EXPLICIT_INDEXES:
        raise RuntimeError("Approval query index verification failed")
    for table_name in _TARGET_TABLES:
        _verify_ddl(connection, table_name)


def upgrade(connection: Connection) -> None:
    """Create both tables, add query indexes, and reject incompatible shapes."""
    rule_exists = _table_exists(connection, _RULE_TABLE)
    proposal_exists = _table_exists(connection, _PROPOSAL_TABLE)
    if rule_exists != proposal_exists:
        raise RuntimeError("Approval storage is only partially present")
    if not rule_exists:
        connection.exec_driver_sql(_RULE_DDL)
        connection.exec_driver_sql(_PROPOSAL_DDL)
        for statement in _INDEXES:
            connection.exec_driver_sql(statement)
    _verify(connection)


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
