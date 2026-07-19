# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only migration CLI contracts against isolated SQLite files."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Iterator

import pytest
from sqlalchemy.exc import OperationalError

from src.config import Config
from src.migrations import cli as migration_cli
from src.migrations.engine import read_only_migration_connection
from src.migrations.registry import (
    DECISION_SIGNAL_PROFILE_MIGRATION,
    LEGACY_BASELINE_MIGRATION,
    LLM_USAGE_TELEMETRY_MIGRATION,
    REGISTRY_METADATA_MIGRATION,
    TARGET_VERSION,
    get_migrations,
)
from src.migrations.runner import verify
from src.storage import DatabaseManager


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_database_singletons() -> Iterator[None]:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    yield
    DatabaseManager.reset_instance()
    Config.reset_instance()


def _create_registry_table(
    connection: sqlite3.Connection,
    *,
    include_checksum: bool = True,
    valid_primary_key: bool = True,
) -> None:
    checksum_column = ", checksum VARCHAR(64)" if include_checksum else ""
    primary_key = " PRIMARY KEY" if valid_primary_key else ""
    connection.execute(
        "CREATE TABLE schema_migrations ("
        f"version VARCHAR(64) NOT NULL{primary_key}, "
        "description VARCHAR(255) NOT NULL, "
        f"applied_at DATETIME NOT NULL{checksum_column})"
    )


def _insert_migration(
    connection: sqlite3.Connection,
    migration,
    *,
    include_checksum: bool = True,
    checksum: str | None = None,
) -> None:
    if include_checksum:
        connection.execute(
            "INSERT INTO schema_migrations "
            "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
            (
                migration.id,
                migration.description,
                "2026-07-16 00:00:00",
                migration.checksum if checksum is None else checksum,
            ),
        )
        return
    connection.execute(
        "INSERT INTO schema_migrations "
        "(version, description, applied_at) VALUES (?, ?, ?)",
        (migration.id, migration.description, "2026-07-16 00:00:00"),
    )


def _create_baseline_only_database(
    db_path: Path,
    *,
    include_checksum: bool = True,
) -> None:
    with sqlite3.connect(db_path) as connection:
        _create_registry_table(connection, include_checksum=include_checksum)
        _insert_migration(
            connection,
            LEGACY_BASELINE_MIGRATION,
            include_checksum=include_checksum,
        )
        connection.execute(
            "CREATE TABLE cli_business_canary (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO cli_business_canary (id, value) VALUES (1, 'keep-me')"
        )
        connection.execute("PRAGMA user_version=73")


def _database_snapshot(db_path: Path) -> dict:
    with sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        master = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall()
        registry_columns = connection.execute(
            "PRAGMA table_info(schema_migrations)"
        ).fetchall()
        registry_rows = connection.execute(
            "SELECT * FROM schema_migrations ORDER BY version"
        ).fetchall()
        canary_rows = connection.execute(
            "SELECT id, value FROM cli_business_canary ORDER BY id"
        ).fetchall()
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
    file_stat = db_path.stat()
    return {
        "master": master,
        "registry_columns": registry_columns,
        "registry_rows": registry_rows,
        "canary_rows": canary_rows,
        "journal_mode": journal_mode,
        "user_version": user_version,
        "file_hash": hashlib.sha256(db_path.read_bytes()).hexdigest(),
        "file_size": file_stat.st_size,
        "file_mtime_ns": file_stat.st_mtime_ns,
        "directory_entries": tuple(sorted(path.name for path in db_path.parent.iterdir())),
    }


def _run_cli(command: str, db_path: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    environment = os.environ.copy()
    environment["DATABASE_PATH"] = str(db_path)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(REPO_ROOT)
    completed = subprocess.run(
        [sys.executable, "-m", "src.migrations.cli", command],
        cwd=REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return completed, json.loads(completed.stdout)


@pytest.mark.parametrize(
    ("command", "expected_exit", "expected_success", "expected_failure"),
    (
        ("status", 0, True, None),
        ("verify", 1, False, "pending_migrations"),
    ),
)
def test_pending_cli_subprocess_is_read_only(
    tmp_path: Path,
    command: str,
    expected_exit: int,
    expected_success: bool,
    expected_failure: str | None,
) -> None:
    db_path = tmp_path / f"pending-{command}.sqlite"
    _create_baseline_only_database(db_path)
    before = _database_snapshot(db_path)

    completed, payload = _run_cli(command, db_path)

    assert completed.returncode == expected_exit
    assert payload["success"] is expected_success
    assert payload["failure_code"] == expected_failure
    assert payload["applied_ids"] == [LEGACY_BASELINE_MIGRATION.id]
    assert payload["pending_ids"] == [
        REGISTRY_METADATA_MIGRATION.id,
        LLM_USAGE_TELEMETRY_MIGRATION.id,
        DECISION_SIGNAL_PROFILE_MIGRATION.id,
    ]
    assert payload["target_version"] == TARGET_VERSION
    assert str(db_path) not in completed.stdout
    assert str(db_path) not in completed.stderr
    assert _database_snapshot(db_path) == before


def test_read_only_connection_enforces_query_only(tmp_path: Path) -> None:
    db_path = tmp_path / "query-only.sqlite"
    _create_baseline_only_database(db_path)
    before = _database_snapshot(db_path)

    with read_only_migration_connection(
        f"sqlite:///{db_path}",
        sqlite_busy_timeout_ms=1000,
    ) as connection:
        assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
        with pytest.raises(OperationalError):
            connection.exec_driver_sql(
                "INSERT INTO cli_business_canary (id, value) VALUES (2, 'blocked')"
            )

    assert _database_snapshot(db_path) == before


def test_missing_database_does_not_create_file_or_parent(tmp_path: Path) -> None:
    missing_parent = tmp_path / "MISSING_DATABASE_PATH_CANARY"
    db_path = missing_parent / "missing.sqlite"

    completed, payload = _run_cli("status", db_path)

    assert completed.returncode == 1
    assert payload["success"] is False
    assert payload["failure_code"] == "database_not_found"
    assert not missing_parent.exists()
    assert str(db_path) not in completed.stdout
    assert str(db_path) not in completed.stderr


def test_legacy_registry_without_checksum_is_reported_without_alter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "legacy-no-checksum.sqlite"
    _create_baseline_only_database(db_path, include_checksum=False)
    before = _database_snapshot(db_path)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()

    exit_code = migration_cli.main(["status"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["success"] is True
    assert payload["pending_ids"] == [
        REGISTRY_METADATA_MIGRATION.id,
        LLM_USAGE_TELEMETRY_MIGRATION.id,
        DECISION_SIGNAL_PROFILE_MIGRATION.id,
    ]
    assert _database_snapshot(db_path) == before
    assert "checksum" not in {row[1] for row in before["registry_columns"]}


def test_non_sqlite_backend_is_rejected_before_engine_open(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "NON_SQLITE_CONNECTION_CANARY"
    engine_opened = False

    class _NonSqliteConfig:
        sqlite_busy_timeout_ms = 1000

        @staticmethod
        def get_db_url(*, create_parent: bool = True) -> str:
            assert create_parent is False
            return f"postgresql://user:{canary}@database.invalid/app"

    def unexpected_engine_open(*_args, **_kwargs):
        nonlocal engine_opened
        engine_opened = True
        raise AssertionError("engine must not be opened")

    monkeypatch.setattr(migration_cli, "get_config", lambda: _NonSqliteConfig())
    monkeypatch.setattr("src.migrations.engine.create_engine", unexpected_engine_open)

    exit_code = migration_cli.main(["status"])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 1
    assert payload["failure_code"] == "unsupported_backend"
    assert engine_opened is False
    assert canary not in output.out
    assert canary not in output.err


@pytest.mark.parametrize(
    ("setup", "expected_failure", "expected_field", "expected_value"),
    (
        (
            "unknown",
            "unknown_migration",
            "unknown_ids",
            ["999912312359_cli_unknown"],
        ),
        (
            "checksum",
            "migration_checksum_mismatch",
            "checksum_mismatches",
            [REGISTRY_METADATA_MIGRATION.id],
        ),
        ("malformed", "registry_schema_invalid", "unknown_ids", []),
    ),
)
def test_cli_failures_are_structured_and_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    setup: str,
    expected_failure: str,
    expected_field: str,
    expected_value: list[str],
) -> None:
    db_path = tmp_path / f"{setup}.sqlite"
    with sqlite3.connect(db_path) as connection:
        _create_registry_table(
            connection,
            valid_primary_key=setup != "malformed",
        )
        if setup == "unknown":
            connection.execute(
                "INSERT INTO schema_migrations "
                "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
                (
                    expected_value[0],
                    "Unknown migration",
                    "2099-01-01 00:00:00",
                    "f" * 64,
                ),
            )
        else:
            for migration in get_migrations():
                checksum = (
                    "0" * 64
                    if setup == "checksum" and migration is REGISTRY_METADATA_MIGRATION
                    else migration.checksum
                )
                _insert_migration(connection, migration, checksum=checksum)
        connection.execute(
            "CREATE TABLE cli_business_canary (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO cli_business_canary (id, value) VALUES (1, 'keep-me')"
        )
    before = _database_snapshot(db_path)
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()

    exit_code = migration_cli.main(["status"])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["failure_code"] == expected_failure
    assert payload[expected_field] == expected_value
    assert str(db_path) not in output.out
    assert str(db_path) not in output.err
    assert _database_snapshot(db_path) == before


def test_unexpected_cli_error_does_not_expose_exception(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    canary = "CLI_EXCEPTION_SECRET_CANARY"

    class _ConfigStub:
        sqlite_busy_timeout_ms = 1000

        @staticmethod
        def get_db_url(*, create_parent: bool = True) -> str:
            assert create_parent is False
            return "sqlite:////unused.sqlite"

    @contextmanager
    def failing_connection(*_args, **_kwargs):
        raise RuntimeError(canary)
        yield

    monkeypatch.setattr(migration_cli, "get_config", lambda: _ConfigStub())
    monkeypatch.setattr(migration_cli, "read_only_migration_connection", failing_connection)

    exit_code = migration_cli.main(["verify"])
    output = capsys.readouterr()
    payload = json.loads(output.out)

    assert exit_code == 1
    assert payload["failure_code"] == "database_inspection_failed"
    assert canary not in output.out
    assert canary not in output.err


def test_normal_startup_still_applies_pending_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "startup-applies.sqlite"
    _create_baseline_only_database(db_path)

    database = DatabaseManager(db_url=f"sqlite:///{db_path}")
    verification = verify(database._engine)

    assert verification.success is True
    assert verification.pending_ids == ()
    with sqlite3.connect(db_path) as connection:
        applied_ids = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            ).fetchall()
        )
        canary_rows = connection.execute(
            "SELECT id, value FROM cli_business_canary ORDER BY id"
        ).fetchall()
    assert applied_ids == tuple(migration.id for migration in get_migrations())
    assert canary_rows == [(1, "keep-me")]
