# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Add persistent checksums to the legacy applied-migration registry."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.migrations.types import Migration
from src.migrations.versions.v20260605_create_all_baseline import (
    MIGRATION as LEGACY_BASELINE_MIGRATION,
)


MIGRATION_ID = "202607160001_migration_runner_registry"
DESCRIPTION = "Add deterministic checksums to the ordered migration registry"


def _column_names(connection: Connection) -> set[str]:
    rows = connection.exec_driver_sql("PRAGMA table_info(schema_migrations)").fetchall()
    return {str(row[1]) for row in rows}


def upgrade(connection: Connection) -> None:
    """Add checksum metadata and stamp only the proven legacy baseline."""
    if "checksum" not in _column_names(connection):
        connection.exec_driver_sql(
            "ALTER TABLE schema_migrations ADD COLUMN checksum VARCHAR(64)"
        )

    baseline = connection.execute(
        text(
            "SELECT description, checksum FROM schema_migrations "
            "WHERE version = :version"
        ),
        {"version": LEGACY_BASELINE_MIGRATION.id},
    ).mappings().one_or_none()
    if baseline is None:
        raise RuntimeError("Known legacy baseline is missing")
    if baseline["description"] != LEGACY_BASELINE_MIGRATION.description:
        raise RuntimeError("Known legacy baseline description does not match")
    if baseline["checksum"] not in (None, LEGACY_BASELINE_MIGRATION.checksum):
        raise RuntimeError("Known legacy baseline checksum does not match")

    if baseline["checksum"] is None:
        connection.execute(
            text(
                "UPDATE schema_migrations SET checksum = :checksum "
                "WHERE version = :version AND checksum IS NULL"
            ),
            {
                "checksum": LEGACY_BASELINE_MIGRATION.checksum,
                "version": LEGACY_BASELINE_MIGRATION.id,
            },
        )


MIGRATION = Migration.from_source_file(
    id=MIGRATION_ID,
    description=DESCRIPTION,
    upgrade=upgrade,
    source_file=__file__,
    bootstraps_registry=True,
)
