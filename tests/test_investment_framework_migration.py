"""Migration contracts for versioned personal investment framework storage."""

from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection

from src.migrations.registry import (
    INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION,
    get_migrations,
)
from src.migrations.runner import MigrationRunner
from src.migrations.types import Migration
from src.storage import DatabaseManager


def _database_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _engine_before_framework_migration(path: Path):
    engine = create_engine(_database_url(path))
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE schema_migrations ("
            "version VARCHAR(64) NOT NULL PRIMARY KEY, "
            "description VARCHAR(255) NOT NULL, "
            "applied_at DATETIME NOT NULL, "
            "checksum VARCHAR(64))"
        )
        for migration in get_migrations()[:-1]:
            connection.exec_driver_sql(
                "INSERT INTO schema_migrations "
                "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
                (
                    migration.id,
                    migration.description,
                    "2026-07-24 00:00:00",
                    migration.checksum,
                ),
            )
    return engine


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def test_fresh_database_has_framework_tables_and_applied_migration() -> None:
    DatabaseManager.reset_instance()
    database = DatabaseManager(db_url="sqlite:///:memory:")
    try:
        assert {
            "investment_frameworks",
            "investment_framework_versions",
        }.issubset(_tables(database._engine))
        status = MigrationRunner().status(database._engine)
        assert status.current_version == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id
        assert status.pending_ids == ()
    finally:
        DatabaseManager.reset_instance()


def test_framework_migration_upgrades_legacy_registry_once(tmp_path: Path) -> None:
    engine = _engine_before_framework_migration(tmp_path / "legacy.sqlite")
    try:
        result = MigrationRunner().apply_pending(engine)
        assert result.success is True
        assert result.executed_ids == (INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id,)
        assert {
            "investment_frameworks",
            "investment_framework_versions",
        }.issubset(_tables(engine))

        rerun = MigrationRunner().apply_pending(engine)
        assert rerun.success is True
        assert rerun.executed_ids == ()
    finally:
        engine.dispose()


def test_framework_migration_rolls_back_tables_when_applied_row_fails(
    tmp_path: Path,
) -> None:
    engine = _engine_before_framework_migration(tmp_path / "rollback.sqlite")

    class AppliedInsertFailureRunner(MigrationRunner):
        def _insert_applied(
            self,
            connection: Connection,
            migration: Migration,
        ) -> None:
            if migration.id == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id:
                raise RuntimeError("injected applied insert failure")
            super()._insert_applied(connection, migration)

    try:
        result = AppliedInsertFailureRunner().apply_pending(engine)
        assert result.success is False
        assert result.failure_code == "applied_registry_write_failed"
        assert result.failed_migration_id == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id
        assert "investment_frameworks" not in _tables(engine)
        assert "investment_framework_versions" not in _tables(engine)
    finally:
        engine.dispose()
