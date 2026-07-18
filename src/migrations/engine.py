# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Shared SQLAlchemy engine construction for startup and migration diagnostics."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional, Union

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Connection, Engine, URL, make_url

from src.migrations.types import MigrationError


DatabaseUrl = Union[str, URL]
EngineFactory = Callable[..., Engine]


def create_database_engine(
    db_url: DatabaseUrl,
    *,
    sqlite_busy_timeout_ms: int,
    read_only: bool = False,
    engine_factory: Optional[EngineFactory] = None,
) -> Engine:
    """Create the shared application engine or a guarded SQLite read-only engine."""
    factory = engine_factory or create_engine
    engine_url: DatabaseUrl = db_url

    if read_only:
        try:
            parsed_url = make_url(db_url)
        except Exception as exc:
            raise MigrationError("database_configuration_invalid") from exc

        if parsed_url.get_backend_name() != "sqlite":
            raise MigrationError("unsupported_backend")

        database = parsed_url.database
        if not database or database == ":memory:":
            raise MigrationError("database_not_found")

        database_path = Path(database).absolute()
        try:
            database_exists = database_path.is_file()
        except OSError as exc:
            raise MigrationError("database_open_failed") from exc
        if not database_exists:
            raise MigrationError("database_not_found")

        engine_url = URL.create(
            drivername=parsed_url.drivername,
            database=f"file:{database_path.as_posix()}",
            query={"mode": "ro", "uri": "true"},
        )

    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }
    if str(engine_url).startswith("sqlite:") and sqlite_busy_timeout_ms > 0:
        engine_kwargs["connect_args"] = {
            "timeout": sqlite_busy_timeout_ms / 1000,
        }

    engine = factory(engine_url, **engine_kwargs)
    if read_only:
        event.listen(engine, "connect", _enable_sqlite_query_only)
    return engine


@contextmanager
def read_only_migration_connection(
    db_url: DatabaseUrl,
    *,
    sqlite_busy_timeout_ms: int,
) -> Iterator[Connection]:
    """Open one disposable diagnostic connection that cannot write SQLite state."""
    engine = create_database_engine(
        db_url,
        sqlite_busy_timeout_ms=sqlite_busy_timeout_ms,
        read_only=True,
    )
    try:
        try:
            connection = engine.connect()
        except Exception as exc:
            raise MigrationError("database_open_failed") from exc

        try:
            yield connection
        finally:
            try:
                connection.close()
            except Exception:
                pass
    finally:
        try:
            engine.dispose()
        except Exception:
            pass


def _enable_sqlite_query_only(dbapi_connection, _connection_record) -> None:
    """Enable and verify SQLite query-only mode for every diagnostic connection."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA query_only=ON")
        row = cursor.execute("PRAGMA query_only").fetchone()
        if row is None or int(row[0]) != 1:
            raise RuntimeError("sqlite_query_only_unavailable")
    finally:
        cursor.close()
