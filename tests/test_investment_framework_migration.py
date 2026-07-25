"""Migration contracts for versioned personal investment framework storage."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Connection

from src.migrations.registry import (
    INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION,
    get_migrations,
)
from src.migrations.runner import MigrationRunner
from src.migrations.types import Migration
from src.migrations.versions.v202607240003_investment_framework_schema import (
    upgrade as upgrade_framework_storage,
)
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


def _create_framework_lookalike_tables(
    connection: Connection,
    *,
    temporary: bool = False,
    latest_version_type: str = "INTEGER",
    framework_autoincrement: bool = False,
    scope_not_null_conflict: str = "",
    framework_primary_conflict: str = "",
    framework_unique_conflict: str = "",
    version_unique_conflict: str = "",
    content_json_collation: str = "",
    foreign_key_match: str = "",
    foreign_key_timing: str = "",
    framework_extra_constraint: str | None = None,
) -> None:
    create_table = "CREATE TEMP TABLE" if temporary else "CREATE TABLE"
    framework_parts = [
        (
            "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT"
            if framework_autoincrement
            else "id INTEGER NOT NULL"
        ),
        f"scope_key VARCHAR(32) NOT NULL{scope_not_null_conflict}",
        f"latest_version {latest_version_type} NOT NULL",
        "active_version INTEGER",
        "revision INTEGER NOT NULL",
        "created_at DATETIME NOT NULL",
        "updated_at DATETIME NOT NULL",
        (
            "CONSTRAINT uix_investment_framework_scope "
            f"UNIQUE (scope_key){framework_unique_conflict}"
        ),
    ]
    if not framework_autoincrement:
        framework_parts.insert(
            -1,
            f"PRIMARY KEY (id){framework_primary_conflict}",
        )
    if framework_extra_constraint is not None:
        framework_parts.append(framework_extra_constraint)
    connection.exec_driver_sql(
        f"{create_table} investment_frameworks ("
        + ", ".join(framework_parts)
        + ")"
    )
    connection.exec_driver_sql(
        f"{create_table} investment_framework_versions ("
        "id INTEGER NOT NULL, "
        "framework_id INTEGER NOT NULL, "
        "version INTEGER NOT NULL, "
        f"content_json TEXT{content_json_collation} NOT NULL, "
        "change_summary VARCHAR(500), "
        "created_at DATETIME NOT NULL, "
        "PRIMARY KEY (id), "
        "CONSTRAINT uix_investment_framework_version "
        f"UNIQUE (framework_id, version){version_unique_conflict}, "
        "FOREIGN KEY(framework_id) REFERENCES investment_frameworks (id) "
        f"{foreign_key_match} ON DELETE CASCADE{foreign_key_timing}"
        ")"
    )


def _framework_schema_snapshot(connection: Connection) -> tuple:
    parameters = (
        "investment_frameworks",
        "investment_framework_versions",
        "investment_frameworks",
        "investment_framework_versions",
    )
    query = (
        "SELECT type, name, tbl_name, sql FROM {master} "
        "WHERE name IN (?, ?) OR tbl_name IN (?, ?) ORDER BY type, name"
    )
    return (
        tuple(
            ("main", *row)
            for row in connection.exec_driver_sql(
                query.format(master="sqlite_master"),
                parameters,
            ).fetchall()
        ),
        tuple(
            ("temp", *row)
            for row in connection.exec_driver_sql(
                query.format(master="sqlite_temp_master"),
                parameters,
            ).fetchall()
        ),
    )


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


@pytest.mark.parametrize(
    ("integer_type", "required"),
    (
        pytest.param("TEXT", "NOT NULL", id="wrong-affinity"),
        pytest.param("INTEGER", "", id="missing-not-null"),
    ),
)
def test_framework_migration_rejects_lookalike_table_shape(
    tmp_path: Path,
    integer_type: str,
    required: str,
) -> None:
    engine = _engine_before_framework_migration(
        tmp_path / f"lookalike-{integer_type}-{required or 'nullable'}.sqlite"
    )
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE investment_frameworks ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "scope_key VARCHAR(32) NOT NULL UNIQUE, "
                f"latest_version {integer_type} {required}, "
                "active_version INTEGER, "
                f"revision {integer_type} {required}, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL"
                ")"
            )
            connection.exec_driver_sql(
                "CREATE TABLE investment_framework_versions ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "framework_id INTEGER NOT NULL, "
                f"version {integer_type} {required}, "
                "content_json TEXT NOT NULL, "
                "change_summary VARCHAR(500), "
                "created_at DATETIME NOT NULL, "
                "UNIQUE (framework_id, version), "
                "FOREIGN KEY(framework_id) "
                "REFERENCES investment_frameworks (id) ON DELETE CASCADE"
                ")"
            )

        result = MigrationRunner().apply_pending(engine)
        assert result.success is False
        assert result.failure_code == "migration_upgrade_failed"
        assert result.failed_migration_id == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id
        with engine.connect() as connection:
            applied = connection.exec_driver_sql(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id,),
            ).one_or_none()
        assert applied is None
    finally:
        engine.dispose()


def test_framework_migration_rejects_partial_unique_lookalikes(
    tmp_path: Path,
) -> None:
    engine = _engine_before_framework_migration(
        tmp_path / "lookalike-partial-unique.sqlite"
    )
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE investment_frameworks ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "scope_key VARCHAR(32) NOT NULL, "
                "latest_version INTEGER NOT NULL, "
                "active_version INTEGER, "
                "revision INTEGER NOT NULL, "
                "created_at DATETIME NOT NULL, "
                "updated_at DATETIME NOT NULL"
                ")"
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX uix_investment_framework_scope "
                "ON investment_frameworks (scope_key) "
                "WHERE scope_key <> 'local'"
            )
            connection.exec_driver_sql(
                "CREATE TABLE investment_framework_versions ("
                "id INTEGER NOT NULL PRIMARY KEY, "
                "framework_id INTEGER NOT NULL, "
                "version INTEGER NOT NULL, "
                "content_json TEXT NOT NULL, "
                "change_summary VARCHAR(500), "
                "created_at DATETIME NOT NULL, "
                "FOREIGN KEY(framework_id) "
                "REFERENCES investment_frameworks (id) ON DELETE CASCADE"
                ")"
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX uix_investment_framework_version "
                "ON investment_framework_versions (framework_id, version) "
                "WHERE version < 0"
            )

        result = MigrationRunner().apply_pending(engine)
        assert result.success is False
        assert result.failure_code == "migration_upgrade_failed"
        assert result.failed_migration_id == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id
        with engine.connect() as connection:
            applied = connection.exec_driver_sql(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id,),
            ).one_or_none()
        assert applied is None
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "lookalike_options",
    (
        pytest.param(
            {"framework_unique_conflict": " ON CONFLICT IGNORE"},
            id="aggregate-unique-conflict-policy",
        ),
        pytest.param(
            {"version_unique_conflict": " ON CONFLICT REPLACE"},
            id="version-unique-conflict-policy",
        ),
        pytest.param(
            {"framework_primary_conflict": " ON CONFLICT FAIL"},
            id="table-primary-key-conflict-policy",
        ),
        pytest.param(
            {"scope_not_null_conflict": " ON CONFLICT IGNORE"},
            id="column-not-null-conflict-policy",
        ),
        pytest.param(
            {"framework_extra_constraint": "CHECK(latest_version = 1)"},
            id="unexpected-check-constraint",
        ),
        pytest.param(
            {"framework_autoincrement": True},
            id="unexpected-autoincrement",
        ),
        pytest.param(
            {"content_json_collation": " COLLATE NOCASE"},
            id="unexpected-non-key-collation",
        ),
        pytest.param(
            {"foreign_key_match": " MATCH FULL"},
            id="unexpected-foreign-key-match",
        ),
        pytest.param(
            {"foreign_key_timing": " DEFERRABLE INITIALLY DEFERRED"},
            id="unexpected-foreign-key-timing",
        ),
        pytest.param(
            {
                "framework_extra_constraint": (
                    "FOREIGN KEY(active_version) "
                    "REFERENCES investment_frameworks(id)"
                )
            },
            id="unexpected-aggregate-foreign-key",
        ),
        pytest.param(
            {"framework_extra_constraint": "UNIQUE(scope_key)"},
            id="duplicate-identical-unique-key",
        ),
    ),
)
def test_framework_migration_rejects_noncanonical_ddl_semantics_without_mutation(
    tmp_path: Path,
    lookalike_options: dict[str, object],
) -> None:
    engine = _engine_before_framework_migration(
        tmp_path / "lookalike-ddl-semantics.sqlite"
    )
    try:
        with engine.begin() as connection:
            _create_framework_lookalike_tables(
                connection,
                **lookalike_options,
            )
            before = _framework_schema_snapshot(connection)

        result = MigrationRunner().apply_pending(engine)

        assert result.success is False
        assert result.failure_code == "migration_upgrade_failed"
        assert result.failed_migration_id == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id
        with engine.connect() as connection:
            applied = connection.exec_driver_sql(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id,),
            ).one_or_none()
            after = _framework_schema_snapshot(connection)
        assert applied is None
        assert after == before
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("target_table", "temporary"),
    (
        pytest.param("investment_frameworks", False, id="aggregate-main"),
        pytest.param("investment_framework_versions", False, id="version-main"),
        pytest.param("investment_frameworks", True, id="aggregate-temp"),
        pytest.param("investment_framework_versions", True, id="version-temp"),
    ),
)
def test_framework_migration_rejects_table_triggers_without_mutation(
    tmp_path: Path,
    target_table: str,
    temporary: bool,
) -> None:
    engine = _engine_before_framework_migration(
        tmp_path / f"trigger-{target_table}-{temporary}.sqlite"
    )
    connection = engine.connect()
    try:
        _create_framework_lookalike_tables(connection)
        trigger_name = f"tamper_{target_table}_{'temp' if temporary else 'main'}"
        if target_table == "investment_frameworks":
            trigger_body = (
                "UPDATE investment_frameworks SET revision = revision + 1 "
                "WHERE id = NEW.id;"
            )
        else:
            trigger_body = (
                "UPDATE investment_framework_versions "
                "SET change_summary = 'triggered' WHERE id = NEW.id;"
            )
        connection.exec_driver_sql(
            f"CREATE {'TEMP ' if temporary else ''}TRIGGER {trigger_name} "
            f"AFTER INSERT ON {target_table} BEGIN {trigger_body} END"
        )
        connection.commit()
        before = _framework_schema_snapshot(connection)
        connection.rollback()

        result = MigrationRunner().apply_pending(connection)

        assert result.success is False
        assert result.failure_code == "migration_upgrade_failed"
        assert result.failed_migration_id == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id
        applied = connection.exec_driver_sql(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id,),
        ).one_or_none()
        assert applied is None
        assert _framework_schema_snapshot(connection) == before
    finally:
        connection.close()
        engine.dispose()


@pytest.mark.parametrize(
    "auxiliary_sql",
    (
        pytest.param(
            "CREATE INDEX unexpected_framework_version_timestamp "
            "ON investment_framework_versions (created_at)",
            id="standalone-index",
        ),
        pytest.param(
            "CREATE TEMP VIEW investment_frameworks "
            "AS SELECT * FROM main.investment_frameworks",
            id="temp-shadow-view",
        ),
    ),
)
def test_framework_migration_rejects_auxiliary_schema_objects_without_mutation(
    tmp_path: Path,
    auxiliary_sql: str,
) -> None:
    engine = _engine_before_framework_migration(
        tmp_path / "auxiliary-schema-object.sqlite"
    )
    connection = engine.connect()
    try:
        _create_framework_lookalike_tables(connection)
        connection.exec_driver_sql(auxiliary_sql)
        connection.commit()
        before = _framework_schema_snapshot(connection)
        connection.rollback()

        result = MigrationRunner().apply_pending(connection)

        assert result.success is False
        assert result.failure_code == "migration_upgrade_failed"
        assert result.failed_migration_id == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id
        applied = connection.exec_driver_sql(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id,),
        ).one_or_none()
        assert applied is None
        assert _framework_schema_snapshot(connection) == before
    finally:
        connection.close()
        engine.dispose()


def test_framework_migration_rejects_bad_main_shape_behind_temp_shadow(
    tmp_path: Path,
) -> None:
    engine = _engine_before_framework_migration(tmp_path / "temp-shadow.sqlite")
    connection = engine.connect()
    try:
        _create_framework_lookalike_tables(
            connection,
            latest_version_type="TEXT",
        )
        _create_framework_lookalike_tables(connection, temporary=True)
        connection.commit()
        before = _framework_schema_snapshot(connection)
        connection.rollback()

        result = MigrationRunner().apply_pending(connection)

        assert result.success is False
        assert result.failure_code == "migration_upgrade_failed"
        assert result.failed_migration_id == INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id
        applied = connection.exec_driver_sql(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (INVESTMENT_FRAMEWORK_SCHEMA_MIGRATION.id,),
        ).one_or_none()
        assert applied is None
        assert _framework_schema_snapshot(connection) == before
    finally:
        connection.close()
        engine.dispose()


def test_framework_shape_verification_falls_back_without_table_list() -> None:
    engine = create_engine("sqlite:///:memory:")

    class EmptyTableListResult:
        @staticmethod
        def fetchall() -> list:
            return []

    class LegacyPragmaFacade:
        def __init__(self, connection):
            self.connection = connection

        def exec_driver_sql(self, statement, parameters=None):
            if statement == "PRAGMA table_list":
                return EmptyTableListResult()
            if parameters is None:
                return self.connection.exec_driver_sql(statement)
            return self.connection.exec_driver_sql(statement, parameters)

    try:
        with engine.begin() as connection:
            upgrade_framework_storage(connection)
            upgrade_framework_storage(LegacyPragmaFacade(connection))
    finally:
        engine.dispose()
