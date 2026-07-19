# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Add and backfill the decision_signals.decision_profile column and indexes."""

import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.migrations.types import Migration


MIGRATION_ID = "202607190002_decision_signal_profile_schema"
DESCRIPTION = "Add decision_signals decision_profile column, indexes, and backfill"

# Profile-aware indexes reproduced from the DecisionSignalRecord model. Fresh
# databases receive them through metadata create_all; legacy databases created
# before decision_profile need them added here. Names and column order are
# authored constants, not external input.
_PROFILE_INDEXES = (
    ("ix_decision_signals_decision_profile", ("decision_profile",)),
    (
        "ix_decision_signal_market_stock_profile_created",
        ("market", "stock_code", "decision_profile", "created_at"),
    ),
    (
        "ix_decision_signal_report_type_market_stock_profile_action_horizon_phase",
        (
            "source_report_id",
            "source_type",
            "market",
            "stock_code",
            "decision_profile",
            "action",
            "horizon",
            "market_phase",
        ),
    ),
    (
        "ix_decision_signal_trace_type_market_stock_profile_action_horizon_phase",
        (
            "trace_id",
            "source_type",
            "market",
            "stock_code",
            "decision_profile",
            "action",
            "horizon",
            "market_phase",
        ),
    ),
)

# Legacy identity values frozen at authoring time. A profile stored in
# metadata_json is only backfilled when it normalizes to one of these; every
# other value (missing, blank, invalid JSON, non-object, unknown label) leaves
# the row NULL so it reads as legacy/unknown.
_VALID_DECISION_PROFILES = ("conservative", "balanced", "aggressive")


def _table_columns(connection: Connection) -> set:
    rows = connection.exec_driver_sql(
        "PRAGMA table_info(decision_signals)"
    ).fetchall()
    return {str(row[1]) for row in rows}


def _index_columns(connection: Connection, index_name: str) -> tuple:
    rows = connection.exec_driver_sql(
        f'PRAGMA index_info("{index_name}")'
    ).fetchall()
    return tuple(str(row[2]) for row in rows)


def _normalize_profile(value) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip().lower()
    if text_value in _VALID_DECISION_PROFILES:
        return text_value
    return None


def _extract_decision_profile(metadata_json) -> str | None:
    if metadata_json is None:
        return None
    try:
        metadata = json.loads(metadata_json)
    except (TypeError, ValueError, RecursionError):
        return None
    if not isinstance(metadata, dict):
        return None
    return _normalize_profile(metadata.get("decision_profile"))


def upgrade(connection: Connection) -> None:
    """Add the column and indexes, then backfill legacy profiles from metadata.

    Index and column names are authored constants, so composing DDL with them is
    safe. Adding only when absent and updating only NULL rows keeps the migration
    idempotent under the runner's serialized re-execution.
    """
    columns = _table_columns(connection)
    if not columns:
        # No decision_signals table to upgrade. Fresh databases create it with
        # the column and indexes through metadata create_all.
        return

    if "decision_profile" not in columns:
        connection.exec_driver_sql(
            "ALTER TABLE decision_signals ADD COLUMN decision_profile VARCHAR(16)"
        )

    for index_name, index_columns in _PROFILE_INDEXES:
        connection.exec_driver_sql(
            f'CREATE INDEX IF NOT EXISTS "{index_name}" '
            f"ON decision_signals ({', '.join(index_columns)})"
        )
        actual_columns = _index_columns(connection, index_name)
        if actual_columns != index_columns:
            raise RuntimeError(
                "decision_profile index verification failed: "
                f"index={index_name} expected={index_columns} "
                f"actual={actual_columns}"
            )

    candidate_rows = connection.exec_driver_sql(
        "SELECT id, metadata_json FROM decision_signals "
        "WHERE decision_profile IS NULL ORDER BY id"
    ).fetchall()
    for signal_id, metadata_json in candidate_rows:
        profile = _extract_decision_profile(metadata_json)
        if profile is None:
            continue
        connection.execute(
            text(
                "UPDATE decision_signals SET decision_profile = :decision_profile "
                "WHERE id = :signal_id AND decision_profile IS NULL"
            ),
            {"decision_profile": profile, "signal_id": signal_id},
        )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
)
