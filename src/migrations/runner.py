# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""SQLite ordered migration runner with transactional applied records."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import logging
import secrets
import sqlite3
from threading import Event, RLock
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple, Union

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.elements import TextClause

from src.migrations.legacy_profiles import sqlite_type_affinity
from src.migrations.registry import get_migrations
from src.migrations.types import (
    Migration,
    MigrationError,
    MigrationMappingResult,
    MigrationParameters,
    MigrationRegistryError,
    MigrationResult,
    MigrationState,
    MigrationStatementResult,
    MigrationStatus,
    VerificationResult,
    validate_registry,
)


logger = logging.getLogger(__name__)
MigrationBind = Union[Engine, Connection]


@dataclass(frozen=True)
class _AppliedMigration:
    id: str
    description: str
    checksum: Optional[str]


@dataclass(frozen=True)
class _RegistryColumn:
    affinity: str
    not_null: bool
    primary_key_position: int


class _ForbiddenMigrationCapabilityAccess(AttributeError):
    """A migration requested connection state outside its execution capability."""


_FORBIDDEN_CAPABILITY_ATTRIBUTES = frozenset(
    {
        "begin",
        "begin_nested",
        "begin_twophase",
        "close",
        "commit",
        "connection",
        "context",
        "cursor",
        "dbapi_connection",
        "detach",
        "driver_connection",
        "engine",
        "executescript",
        "execution_options",
        "get_nested_transaction",
        "get_transaction",
        "in_transaction",
        "invalidate",
        "raw_connection",
        "rollback",
        "savepoint",
        "set_authorizer",
    }
)
_TRANSACTION_CONTROL_SQL_KEYWORDS = frozenset(
    {
        "BEGIN",
        "COMMIT",
        "END",
        "RELEASE",
        "ROLLBACK",
        "SAVEPOINT",
    }
)


def _leading_sql_keyword(statement: str) -> str:
    """Return SQLite's first keyword after empty statements and comments."""
    offset = 0
    statement_length = len(statement)
    while offset < statement_length:
        if (
            statement[offset].isspace()
            or statement[offset] == ";"
            or statement[offset] == "\ufeff"
        ):
            offset += 1
            continue
        if statement.startswith("--", offset):
            newline = statement.find("\n", offset + 2)
            if newline < 0:
                return ""
            offset = newline + 1
            continue
        if statement.startswith("/*", offset):
            comment_end = statement.find("*/", offset + 2)
            if comment_end < 0:
                return ""
            offset = comment_end + 2
            continue
        break

    keyword_start = offset
    while offset < statement_length and (
        statement[offset].isalpha() or statement[offset] == "_"
    ):
        offset += 1
    return statement[keyword_start:offset].upper()


def _is_transaction_control_sql(statement: str) -> bool:
    return _leading_sql_keyword(statement) in _TRANSACTION_CONTROL_SQL_KEYWORDS


class _MigrationMappingResult:
    """Detached mapping rows with no SQLAlchemy cursor or connection surface."""

    __slots__ = ("__lease", "__rows")

    def __init__(
        self,
        rows: Tuple[Mapping[str, Any], ...],
        lease: _MigrationExecutionLease,
    ) -> None:
        self.__lease = lease
        self.__rows = rows

    def one_or_none(self) -> Optional[Mapping[str, Any]]:
        if len(self.__rows) > 1:
            raise RuntimeError("Expected at most one migration result row")
        if not self.__rows:
            return None
        return dict(self.__rows[0])

    def __getattr__(self, name: str):
        if name in _FORBIDDEN_CAPABILITY_ATTRIBUTES:
            self.__lease.reject_capability_access(name)
        raise AttributeError(name)


class _MigrationStatementResult:
    """Detached statement result exposed to trusted migration code."""

    __slots__ = ("__keys", "__lease", "__rows")

    def __init__(
        self,
        *,
        keys: Tuple[str, ...],
        lease: _MigrationExecutionLease,
        rows: Tuple[Tuple[Any, ...], ...],
    ) -> None:
        self.__keys = keys
        self.__lease = lease
        self.__rows = rows

    def fetchall(self) -> list[Tuple[Any, ...]]:
        return list(self.__rows)

    def mappings(self) -> MigrationMappingResult:
        rows = tuple(
            dict(zip(self.__keys, row))
            for row in self.__rows
        )
        return _MigrationMappingResult(rows, self.__lease)

    def __getattr__(self, name: str):
        if name in _FORBIDDEN_CAPABILITY_ATTRIBUTES:
            self.__lease.reject_capability_access(name)
        raise AttributeError(name)


@dataclass(frozen=True)
class _MigrationExecutionOutcome:
    """Latched capability violations and statement failures for one upgrade."""

    capability_violation: bool
    statement_failed: bool


class _MigrationExecutionLease:
    """Runner-owned lifetime for one migration execution capability."""

    __slots__ = (
        "__capability_violation",
        "__connection",
        "__lock",
        "__migration_id",
        "__revoked",
        "__statement_failed",
    )

    def __init__(self, connection: Connection, migration_id: str) -> None:
        self.__connection: Optional[Connection] = connection
        self.__capability_violation = Event()
        self.__lock = RLock()
        self.__migration_id = migration_id
        self.__revoked = Event()
        self.__statement_failed = Event()

    @contextmanager
    def connection_scope(self) -> Iterator[Connection]:
        with self.__lock:
            connection = self.__connection
            if self.__revoked.is_set() or connection is None:
                raise MigrationError(
                    "migration_transaction_control_forbidden",
                    self.__migration_id,
                )
            try:
                yield connection
            except BaseException:
                self.__statement_failed.set()
                raise

    def reject_capability_access(self, name: str) -> None:
        self.__capability_violation.set()
        raise _ForbiddenMigrationCapabilityAccess(name)

    def revoke(self) -> _MigrationExecutionOutcome:
        self.__revoked.set()
        with self.__lock:
            self.__connection = None
            return _MigrationExecutionOutcome(
                capability_violation=self.__capability_violation.is_set(),
                statement_failed=self.__statement_failed.is_set(),
            )


class _MigrationExecutionFacade:
    """Expose statement execution while keeping transaction ownership in runner."""

    __slots__ = ("__lease",)

    def __init__(self, lease: _MigrationExecutionLease) -> None:
        self.__lease = lease

    def execute(
        self,
        statement: TextClause,
        parameters: MigrationParameters = None,
    ) -> MigrationStatementResult:
        # SQLAlchemy's executable protocol can invoke a statement-owned callback
        # with the real Connection. Extract only the plain SQL from the exact
        # object produced by sqlalchemy.text(), then use the runner-owned driver
        # path so instance-level callback overrides are never invoked.
        sql = statement.text if type(statement) is TextClause else None
        if type(sql) is not str:
            self.__lease.reject_capability_access("statement")
        if _is_transaction_control_sql(sql):
            self.__lease.reject_capability_access("statement")
        with self.__lease.connection_scope() as connection:
            if parameters is None:
                result = connection.exec_driver_sql(sql)
            else:
                result = connection.exec_driver_sql(sql, parameters)
            return self._materialize(result)

    def exec_driver_sql(
        self,
        statement: str,
        parameters: MigrationParameters = None,
    ) -> MigrationStatementResult:
        if type(statement) is not str:
            self.__lease.reject_capability_access("statement")
        if _is_transaction_control_sql(statement):
            self.__lease.reject_capability_access("statement")
        with self.__lease.connection_scope() as connection:
            if parameters is None:
                result = connection.exec_driver_sql(statement)
            else:
                result = connection.exec_driver_sql(statement, parameters)
            return self._materialize(result)

    def _materialize(self, result) -> MigrationStatementResult:
        try:
            if result.returns_rows:
                keys = tuple(str(key) for key in result.keys())
                rows = tuple(tuple(row) for row in result.fetchall())
            else:
                keys = ()
                rows = ()
            return _MigrationStatementResult(
                keys=keys,
                lease=self.__lease,
                rows=rows,
            )
        finally:
            result.close()

    def __getattr__(self, name: str):
        if name in _FORBIDDEN_CAPABILITY_ATTRIBUTES:
            self.__lease.reject_capability_access(name)
        raise AttributeError(name)


class MigrationRunner:
    """Apply an immutable registry in strict order."""

    def __init__(self, migrations: Optional[Sequence[Migration]] = None):
        selected_migrations = get_migrations() if migrations is None else tuple(migrations)
        self.migrations = validate_registry(tuple(selected_migrations))
        baselines = tuple(
            migration for migration in self.migrations if migration.is_legacy_baseline
        )
        bootstraps = tuple(
            migration for migration in self.migrations if migration.bootstraps_registry
        )
        if len(baselines) != 1 or baselines[0] is not self.migrations[0]:
            raise MigrationRegistryError("legacy_baseline_contract_invalid")
        if len(bootstraps) != 1:
            raise MigrationRegistryError("registry_bootstrap_contract_invalid")
        self._baseline = baselines[0]
        self._registry_bootstrap = bootstraps[0]
        self._by_id = {migration.id: migration for migration in self.migrations}
        self.target_version = self.migrations[-1].id

    def status(self, bind: MigrationBind) -> MigrationStatus:
        """Inspect ordered migration state without changing schema or rows."""
        try:
            with self._connection_scope(bind) as connection:
                had_transaction = connection.in_transaction()
                try:
                    return self._inspect_connection(connection)
                finally:
                    if not had_transaction and connection.in_transaction():
                        connection.rollback()
        except MigrationError as exc:
            return self._failure_status(
                failure_code=exc.failure_code,
                failed_migration_id=exc.migration_id,
            )
        except OperationalError as exc:
            code = "database_locked" if self._is_locked_error(exc) else "registry_read_failed"
            return self._failure_status(failure_code=code)
        except Exception:
            return self._failure_status(failure_code="database_inspection_failed")

    def verify(self, bind: MigrationBind) -> VerificationResult:
        """Verify that the database is trusted and fully at the target version."""
        current = self.status(bind)
        if not current.success:
            return self._verification_from_state(current, success=False)
        if current.pending_ids:
            return self._verification_from_state(
                current,
                success=False,
                failure_code="pending_migrations",
                failed_migration_id=current.pending_ids[0],
            )
        return self._verification_from_state(current, success=True)

    def preflight_existing(self, bind: MigrationBind) -> MigrationStatus:
        """Validate any pre-existing registry before compatibility code can write."""
        try:
            with self._connection_scope(bind) as connection:
                had_transaction = connection.in_transaction()
                try:
                    if connection.dialect.name != "sqlite":
                        return self._failure_status(failure_code="unsupported_backend")

                    columns = self._registry_columns(connection)
                    if not columns:
                        return MigrationStatus(
                            target_version=self.target_version,
                            pending_ids=tuple(
                                migration.id for migration in self.migrations
                            ),
                            success=True,
                        )
                    required_columns = {"version", "description", "applied_at"}
                    if not required_columns.issubset(columns):
                        return self._failure_status(
                            failure_code="registry_schema_invalid"
                        )

                    has_checksum = "checksum" in columns
                    checksum_selection = (
                        "checksum" if has_checksum else "NULL AS checksum"
                    )
                    rows = connection.exec_driver_sql(
                        "SELECT version, description, "
                        f"{checksum_selection} FROM schema_migrations ORDER BY version"
                    ).fetchall()
                    duplicate_ids = self._duplicate_applied_ids(rows)
                    if duplicate_ids:
                        return self._failure_status(
                            failure_code="duplicate_applied_migration",
                            failed_migration_id=duplicate_ids[0],
                        )
                    if not self._registry_schema_is_valid(columns):
                        return self._failure_status(
                            failure_code="registry_schema_invalid"
                        )
                    if not rows:
                        return MigrationStatus(
                            target_version=self.target_version,
                            pending_ids=tuple(
                                migration.id for migration in self.migrations
                            ),
                            success=True,
                        )
                    applied = {
                        str(row[0]): _AppliedMigration(
                            id=str(row[0]),
                            description=str(row[1]),
                            checksum=None if row[2] is None else str(row[2]),
                        )
                        for row in rows
                    }
                    return self._evaluate(applied, has_checksum=has_checksum)
                finally:
                    if not had_transaction and connection.in_transaction():
                        connection.rollback()
        except MigrationError as exc:
            return self._failure_status(
                failure_code=exc.failure_code,
                failed_migration_id=exc.migration_id,
            )
        except OperationalError as exc:
            code = (
                "database_locked"
                if self._is_locked_error(exc)
                else "registry_read_failed"
            )
            return self._failure_status(failure_code=code)
        except Exception:
            return self._failure_status(failure_code="database_inspection_failed")

    def apply_pending(self, bind: MigrationBind) -> MigrationResult:
        """Apply every pending migration, one database transaction at a time."""
        current = self.status(bind)
        executed_ids = []
        if not current.success:
            return self._result_from_state(current, executed_ids=())

        while current.pending_ids:
            migration_id = current.pending_ids[0]
            migration = self._by_id[migration_id]
            if migration.is_legacy_baseline:
                return self._result_from_state(
                    current,
                    success=False,
                    failure_code="legacy_baseline_missing",
                    failed_migration_id=migration.id,
                    executed_ids=tuple(executed_ids),
                )
            try:
                executed = self._apply_one(bind, migration)
            except MigrationError as exc:
                return self._result_from_state(
                    exc.state or current,
                    success=False,
                    failure_code=exc.failure_code,
                    failed_migration_id=exc.migration_id,
                    executed_ids=tuple(executed_ids),
                )
            if executed:
                executed_ids.append(migration.id)

            current = self.status(bind)
            if not current.success:
                return self._result_from_state(
                    current,
                    executed_ids=tuple(executed_ids),
                )

        return self._result_from_state(
            current,
            success=True,
            executed_ids=tuple(executed_ids),
        )

    def apply_pending_within_transaction(self, connection: Connection) -> MigrationResult:
        """Apply pending migrations inside a caller-owned open transaction.

        Startup already serializes compatibility work behind a single
        BEGIN IMMEDIATE and owns commit/rollback, so each migration runs in that
        same transaction instead of taking its own write lock. Applied rows are
        written but never committed here; a failure surfaces as an unsuccessful
        result and the caller rolls the whole transaction back atomically.
        """
        if not isinstance(connection, Connection):
            raise MigrationError("invalid_connection")
        if not connection.in_transaction():
            raise MigrationError("initialization_transaction_required")

        current = self._inspect_connection(connection)
        executed_ids: list[str] = []
        if not current.success:
            return self._result_from_state(current, executed_ids=())

        while current.pending_ids:
            migration_id = current.pending_ids[0]
            migration = self._by_id[migration_id]
            if migration.is_legacy_baseline:
                return self._result_from_state(
                    current,
                    success=False,
                    failure_code="legacy_baseline_missing",
                    failed_migration_id=migration.id,
                    executed_ids=tuple(executed_ids),
                )
            try:
                executed = self._execute_within_transaction(connection, migration)
            except MigrationError as exc:
                return self._result_from_state(
                    exc.state or current,
                    success=False,
                    failure_code=exc.failure_code,
                    failed_migration_id=exc.migration_id,
                    executed_ids=tuple(executed_ids),
                )
            if executed:
                executed_ids.append(migration.id)

            current = self._inspect_connection(connection)
            if not current.success:
                return self._result_from_state(
                    current,
                    executed_ids=tuple(executed_ids),
                )

        return self._result_from_state(
            current,
            success=True,
            executed_ids=tuple(executed_ids),
        )

    def _execute_within_transaction(
        self,
        connection: Connection,
        migration: Migration,
    ) -> bool:
        locked_state = self._inspect_connection(connection)
        if not locked_state.success:
            raise MigrationError.from_state(locked_state)
        if migration.id in locked_state.applied_ids:
            return False
        if not locked_state.pending_ids or locked_state.pending_ids[0] != migration.id:
            raise MigrationError("migration_order_invalid", migration.id)
        self._run_guarded_upgrade(connection, migration)
        return True

    def _apply_one(self, bind: MigrationBind, migration: Migration) -> bool:
        with self._connection_scope(bind) as connection:
            if connection.in_transaction():
                raise MigrationError("active_transaction", migration.id)

            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            except OperationalError as exc:
                code = "database_locked" if self._is_locked_error(exc) else "lock_acquire_failed"
                raise MigrationError(code, migration.id) from exc
            except Exception as exc:
                raise MigrationError("lock_acquire_failed", migration.id) from exc

            try:
                locked_state = self._inspect_connection(connection)
                if not locked_state.success:
                    raise MigrationError.from_state(locked_state)
                if migration.id in locked_state.applied_ids:
                    self._commit(connection, migration.id)
                    return False
                if not locked_state.pending_ids or locked_state.pending_ids[0] != migration.id:
                    raise MigrationError("migration_order_invalid", migration.id)

                self._run_guarded_upgrade(connection, migration)

                self._commit(connection, migration.id)
                return True
            except MigrationError:
                self._rollback(connection, migration.id)
                raise
            except Exception as exc:
                self._rollback(connection, migration.id)
                raise MigrationError("migration_execution_failed", migration.id) from exc

    def _run_guarded_upgrade(self, connection: Connection, migration: Migration) -> None:
        """Run one migration upgrade under the transaction guard and record it.

        The caller owns the surrounding transaction (a per-migration
        BEGIN IMMEDIATE for the engine path, or the startup transaction for the
        in-initialization path); this only isolates the upgrade with a savepoint
        and writes the applied row.
        """
        try:
            with self._guard_upgrade_transaction(connection, migration.id):
                execution_lease = _MigrationExecutionLease(
                    connection,
                    migration.id,
                )
                try:
                    upgrade_result = migration.upgrade(
                        _MigrationExecutionFacade(execution_lease)
                    )
                finally:
                    execution_outcome = execution_lease.revoke()
                if execution_outcome.capability_violation:
                    raise MigrationError(
                        "migration_transaction_control_forbidden",
                        migration.id,
                    )
                if execution_outcome.statement_failed:
                    raise MigrationError(
                        "migration_upgrade_failed",
                        migration.id,
                    )
                if upgrade_result is not None:
                    cleanup_error = None
                    if inspect.iscoroutine(upgrade_result) or inspect.isgenerator(
                        upgrade_result
                    ):
                        try:
                            upgrade_result.close()
                        except Exception as exc:
                            cleanup_error = exc
                    invalid_return = MigrationError(
                        "migration_upgrade_invalid_return",
                        migration.id,
                    )
                    if cleanup_error is not None:
                        raise invalid_return from cleanup_error
                    raise invalid_return
        except MigrationError:
            raise
        except _ForbiddenMigrationCapabilityAccess as exc:
            raise MigrationError(
                "migration_transaction_control_forbidden",
                migration.id,
            ) from exc
        except Exception as exc:
            raise MigrationError("migration_upgrade_failed", migration.id) from exc

        if migration.bootstraps_registry:
            bootstrapped_state = self._inspect_connection(connection)
            if not bootstrapped_state.success:
                raise MigrationError.from_state(bootstrapped_state)

        try:
            self._insert_applied(connection, migration)
        except Exception as exc:
            raise MigrationError("applied_registry_write_failed", migration.id) from exc

    def _inspect_connection(self, connection: Connection) -> MigrationStatus:
        if connection.dialect.name != "sqlite":
            return self._failure_status(failure_code="unsupported_backend")

        columns = self._registry_columns(connection)
        if not columns:
            return self._failure_status(failure_code="registry_table_missing")
        required_columns = {"version", "description", "applied_at"}
        if not required_columns.issubset(columns):
            return self._failure_status(failure_code="registry_schema_invalid")

        has_checksum = "checksum" in columns
        checksum_selection = "checksum" if has_checksum else "NULL AS checksum"
        rows = connection.exec_driver_sql(
            "SELECT version, description, "
            f"{checksum_selection} FROM schema_migrations ORDER BY version"
        ).fetchall()
        duplicate_ids = self._duplicate_applied_ids(rows)
        if duplicate_ids:
            return self._failure_status(
                failure_code="duplicate_applied_migration",
                failed_migration_id=duplicate_ids[0],
            )
        if not self._registry_schema_is_valid(columns):
            return self._failure_status(failure_code="registry_schema_invalid")
        applied = {
            str(row[0]): _AppliedMigration(
                id=str(row[0]),
                description=str(row[1]),
                checksum=None if row[2] is None else str(row[2]),
            )
            for row in rows
        }
        return self._evaluate(applied, has_checksum=has_checksum)

    def _evaluate(
        self,
        applied: Dict[str, _AppliedMigration],
        *,
        has_checksum: bool,
    ) -> MigrationStatus:
        known_ids = tuple(migration.id for migration in self.migrations)
        applied_known = tuple(migration_id for migration_id in known_ids if migration_id in applied)
        pending_ids = tuple(migration_id for migration_id in known_ids if migration_id not in applied)
        unknown_ids = tuple(sorted(set(applied) - set(known_ids)))
        current_version = max(applied) if applied else None

        base_kwargs = {
            "current_version": current_version,
            "target_version": self.target_version,
            "applied_ids": applied_known,
            "pending_ids": pending_ids,
            "unknown_ids": unknown_ids,
        }
        if unknown_ids:
            return MigrationStatus(
                **base_kwargs,
                success=False,
                failure_code="unknown_migration",
                failed_migration_id=unknown_ids[0],
            )
        if self._baseline.id not in applied:
            return MigrationStatus(
                **base_kwargs,
                success=False,
                failure_code="legacy_baseline_missing",
                failed_migration_id=self._baseline.id,
            )

        expected_prefix = known_ids[: len(applied_known)]
        if applied_known != expected_prefix:
            first_gap = next(
                migration_id
                for migration_id in known_ids
                if migration_id not in applied
            )
            return MigrationStatus(
                **base_kwargs,
                success=False,
                failure_code="migration_order_invalid",
                failed_migration_id=first_gap,
            )

        description_mismatches = tuple(
            migration.id
            for migration in self.migrations
            if migration.id in applied
            and applied[migration.id].description != migration.description
        )
        if description_mismatches:
            return MigrationStatus(
                **base_kwargs,
                description_mismatches=description_mismatches,
                success=False,
                failure_code="migration_description_mismatch",
                failed_migration_id=description_mismatches[0],
            )

        bootstrap_pending = self._registry_bootstrap.id not in applied
        legacy_null_checksum_allowed = (
            bootstrap_pending
            and applied_known == (self._baseline.id,)
            and applied[self._baseline.id].checksum is None
        )
        checksum_mismatches = []
        for migration in self.migrations:
            row = applied.get(migration.id)
            if row is None:
                continue
            if (
                migration.is_legacy_baseline
                and legacy_null_checksum_allowed
            ):
                continue
            if row.checksum != migration.checksum:
                checksum_mismatches.append(migration.id)

        if not has_checksum and not legacy_null_checksum_allowed:
            for migration_id in applied_known:
                if migration_id not in checksum_mismatches:
                    checksum_mismatches.append(migration_id)
        checksum_mismatches_tuple = tuple(checksum_mismatches)
        if checksum_mismatches_tuple:
            return MigrationStatus(
                **base_kwargs,
                checksum_mismatches=checksum_mismatches_tuple,
                success=False,
                failure_code="migration_checksum_mismatch",
                failed_migration_id=checksum_mismatches_tuple[0],
            )

        return MigrationStatus(**base_kwargs, success=True)

    @staticmethod
    def _registry_columns(connection: Connection) -> Dict[str, _RegistryColumn]:
        table_exists = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).scalar_one_or_none()
        if table_exists is None:
            return {}
        rows = connection.exec_driver_sql("PRAGMA table_info(schema_migrations)").fetchall()
        return {
            str(row[1]): _RegistryColumn(
                affinity=sqlite_type_affinity(str(row[2] or "")),
                not_null=bool(row[3]),
                primary_key_position=int(row[5]),
            )
            for row in rows
        }

    @staticmethod
    def _registry_schema_is_valid(columns: Dict[str, _RegistryColumn]) -> bool:
        version = columns["version"]
        description = columns["description"]
        applied_at = columns["applied_at"]
        checksum = columns.get("checksum")
        primary_key_columns = tuple(
            name
            for name, column in columns.items()
            if column.primary_key_position > 0
        )
        return (
            primary_key_columns == ("version",)
            and version.primary_key_position == 1
            and version.not_null
            and version.affinity == "TEXT"
            and description.not_null
            and description.affinity == "TEXT"
            and applied_at.not_null
            and applied_at.affinity == "NUMERIC"
            and (checksum is None or checksum.affinity == "TEXT")
        )

    @staticmethod
    def _duplicate_applied_ids(rows) -> Tuple[str, ...]:
        seen = set()
        duplicates = []
        for row in rows:
            migration_id = str(row[0])
            if migration_id in seen and migration_id not in duplicates:
                duplicates.append(migration_id)
            seen.add(migration_id)
        return tuple(duplicates)

    @staticmethod
    @contextmanager
    def _guard_upgrade_transaction(
        connection: Connection,
        migration_id: str,
    ) -> Iterator[None]:
        """Keep transaction ownership inside the runner while upgrade executes."""
        guarded_attributes = []
        missing = object()

        def forbidden(*_args, **_kwargs):
            raise MigrationError(
                "migration_transaction_control_forbidden",
                migration_id,
            )

        def guard_attribute(target, name: str) -> None:
            if not hasattr(target, name):
                return
            previous = getattr(target, "__dict__", {}).get(name, missing)
            setattr(target, name, forbidden)
            guarded_attributes.append((target, name, previous))

        raw_connection = connection.connection
        dbapi_connection = raw_connection.driver_connection
        if not isinstance(dbapi_connection, sqlite3.Connection):
            raise MigrationError(
                "migration_transaction_guard_unavailable",
                migration_id,
            )

        savepoint_name = f"stockpulse_migration_guard_{secrets.token_hex(16)}"
        try:
            dbapi_connection.execute(f"SAVEPOINT {savepoint_name}").close()
        except sqlite3.Error as exc:
            raise MigrationError(
                "migration_transaction_guard_unavailable",
                migration_id,
            ) from exc

        for method_name in (
            "begin",
            "begin_nested",
            "begin_twophase",
            "close",
            "commit",
            "detach",
            "execution_options",
            "get_nested_transaction",
            "get_transaction",
            "invalidate",
            "rollback",
        ):
            guard_attribute(connection, method_name)
        for method_name in ("close", "commit", "rollback"):
            guard_attribute(raw_connection, method_name)

        try:
            yield
            if not dbapi_connection.in_transaction:
                forbidden()
            try:
                dbapi_connection.execute(
                    f"RELEASE SAVEPOINT {savepoint_name}"
                ).close()
            except sqlite3.Error as exc:
                raise MigrationError(
                    "migration_transaction_control_forbidden",
                    migration_id,
                ) from exc
            if not dbapi_connection.in_transaction:
                forbidden()
        finally:
            for target, name, previous in reversed(guarded_attributes):
                if previous is missing:
                    delattr(target, name)
                else:
                    setattr(target, name, previous)

    @staticmethod
    def _insert_applied(connection: Connection, migration: Migration) -> None:
        applied_at = datetime.now(timezone.utc).replace(tzinfo=None)
        connection.execute(
            text(
                "INSERT INTO schema_migrations "
                "(version, description, applied_at, checksum) "
                "VALUES (:version, :description, :applied_at, :checksum)"
            ),
            {
                "version": migration.id,
                "description": migration.description,
                "applied_at": applied_at,
                "checksum": migration.checksum,
            },
        )

    @staticmethod
    def _commit(connection: Connection, migration_id: str) -> None:
        try:
            connection.commit()
        except Exception as exc:
            raise MigrationError("migration_commit_failed", migration_id) from exc

    @staticmethod
    def _rollback(connection: Connection, migration_id: str) -> None:
        try:
            connection.rollback()
        except Exception as exc:
            logger.warning(
                "Migration rollback failed: code=migration_rollback_failed "
                "migration_id=%s exception_type=%s",
                migration_id,
                type(exc).__name__,
            )

    @staticmethod
    def _is_locked_error(exc: OperationalError) -> bool:
        message = str(getattr(exc, "orig", exc)).lower()
        return any(
            token in message
            for token in (
                "database is locked",
                "database schema is locked",
                "database table is locked",
            )
        )

    @staticmethod
    @contextmanager
    def _connection_scope(bind: MigrationBind) -> Iterator[Connection]:
        if isinstance(bind, Engine):
            with bind.connect() as connection:
                yield connection
            return
        if isinstance(bind, Connection):
            yield bind
            return
        raise MigrationError("invalid_connection")

    def _failure_status(
        self,
        *,
        failure_code: str,
        failed_migration_id: Optional[str] = None,
    ) -> MigrationStatus:
        return MigrationStatus(
            target_version=self.target_version,
            success=False,
            failure_code=failure_code,
            failed_migration_id=failed_migration_id,
        )

    @staticmethod
    def _verification_from_state(
        state: MigrationState,
        *,
        success: bool,
        failure_code: Optional[str] = None,
        failed_migration_id: Optional[str] = None,
    ) -> VerificationResult:
        return VerificationResult(
            current_version=state.current_version,
            target_version=state.target_version,
            applied_ids=state.applied_ids,
            pending_ids=state.pending_ids,
            unknown_ids=state.unknown_ids,
            checksum_mismatches=state.checksum_mismatches,
            description_mismatches=state.description_mismatches,
            success=success,
            failure_code=failure_code if failure_code is not None else state.failure_code,
            failed_migration_id=(
                failed_migration_id
                if failed_migration_id is not None
                else state.failed_migration_id
            ),
        )

    @staticmethod
    def _result_from_state(
        state: MigrationState,
        *,
        success: Optional[bool] = None,
        failure_code: Optional[str] = None,
        failed_migration_id: Optional[str] = None,
        executed_ids: Tuple[str, ...],
    ) -> MigrationResult:
        return MigrationResult(
            current_version=state.current_version,
            target_version=state.target_version,
            applied_ids=state.applied_ids,
            pending_ids=state.pending_ids,
            unknown_ids=state.unknown_ids,
            checksum_mismatches=state.checksum_mismatches,
            description_mismatches=state.description_mismatches,
            success=state.success if success is None else success,
            failure_code=failure_code if failure_code is not None else state.failure_code,
            failed_migration_id=(
                failed_migration_id
                if failed_migration_id is not None
                else state.failed_migration_id
            ),
            executed_ids=executed_ids,
        )


_DEFAULT_RUNNER = MigrationRunner()


def status(bind: MigrationBind) -> MigrationStatus:
    """Inspect the production registry."""
    return _DEFAULT_RUNNER.status(bind)


def verify(bind: MigrationBind) -> VerificationResult:
    """Verify the production registry."""
    return _DEFAULT_RUNNER.verify(bind)


def apply_pending(bind: MigrationBind) -> MigrationResult:
    """Apply the production registry."""
    return _DEFAULT_RUNNER.apply_pending(bind)


def apply_pending_within_transaction(connection: Connection) -> MigrationResult:
    """Apply the production registry inside a caller-owned open transaction."""
    return _DEFAULT_RUNNER.apply_pending_within_transaction(connection)


def preflight_existing(bind: MigrationBind) -> MigrationStatus:
    """Validate a registry that existed before startup compatibility work."""
    return _DEFAULT_RUNNER.preflight_existing(bind)
