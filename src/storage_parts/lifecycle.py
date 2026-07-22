# -*- coding: utf-8 -*-
"""Database lifecycle, migration startup, and session methods."""

import atexit
from contextlib import contextmanager
from datetime import datetime
import logging
import time
from typing import Any, Callable, Optional, Tuple

import pandas as pd
from sqlalchemy import UniqueConstraint, create_engine, event, inspect, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_config
from src.migrations.engine import create_database_engine
from src.migrations.legacy_profiles import (
    match_legacy_schema_profile,
    sqlite_type_affinity,
)
from src.migrations.registry import LEGACY_BASELINE_MIGRATION
from src.migrations.runner import (
    apply_pending_within_transaction,
    preflight_existing,
)
from src.migrations.types import MigrationError
from src.storage import (
    Base,
    CURRENT_SCHEMA_VERSION,
    DatabaseManager,
    DatabaseSchemaMigration,
    T,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class _LifecycleMethods:
    """Source container rebound onto ``DatabaseManager`` by the facade."""

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_url: Optional[str] = None):
        """
        初始化数据库管理器
        
        Args:
            db_url: 数据库连接 URL（可选，默认从配置读取）
        """
        if getattr(self, '_initialized', False):
            return

        created_engine = None

        try:
            config = get_config()
            if db_url is None:
                db_url = config.get_db_url()

            self._db_url = db_url
            self._sqlite_wal_enabled = config.sqlite_wal_enabled
            self._sqlite_busy_timeout_ms = config.sqlite_busy_timeout_ms
            self._sqlite_write_retry_max = config.sqlite_write_retry_max
            self._sqlite_write_retry_base_delay = config.sqlite_write_retry_base_delay

            # Create the database engine
            created_engine = create_database_engine(
                db_url,
                sqlite_busy_timeout_ms=self._sqlite_busy_timeout_ms,
                engine_factory=create_engine,
            )
            self._engine = created_engine
            self._is_sqlite_engine = self._engine.url.get_backend_name() == 'sqlite'
            self._sqlite_file_db = self._is_sqlite_engine and self._is_file_sqlite_database()
            self._install_sqlite_pragma_handler()

            # Create the Session factory
            self._SessionLocal = sessionmaker(
                bind=self._engine,
                autocommit=False,
                autoflush=False,
            )

            with self._schema_initialization_scope() as connection:
                self._schema_initialization_connection = connection
                try:
                    preexisting_tables = self._sqlite_user_tables(connection)
                    preflight = preflight_existing(connection)
                    if not preflight.success:
                        raise MigrationError.from_state(preflight)

                    baseline_already_applied = (
                        CURRENT_SCHEMA_VERSION in preflight.applied_ids
                    )
                    can_stamp_baseline = (
                        not preexisting_tables
                        or self._has_known_baseline_anchor(
                            connection,
                            preexisting_tables,
                        )
                    )
                    if not baseline_already_applied and not can_stamp_baseline:
                        raise MigrationError(
                            "legacy_baseline_untrusted",
                            CURRENT_SCHEMA_VERSION,
                        )

                    # Serialize create_all and the remaining not-yet-migrated
                    # compatibility repairs across processes, then let the ordered
                    # runner apply pending migrations inside this same transaction
                    # before the baseline is proven and committed.
                    Base.metadata.create_all(connection)
                    self._ensure_schema_migration_record(
                        allow_insert=can_stamp_baseline,
                    )
                    migration_result = apply_pending_within_transaction(connection)
                    if not migration_result.success:
                        raise MigrationError.from_state(migration_result)
                    if not baseline_already_applied:
                        self._verify_create_all_baseline(connection)
                finally:
                    self._schema_initialization_connection = None

            self._enable_sqlite_wal_mode()

            self._initialized = True
            logger.info(
                "Database initialized: backend=%s",
                self._engine.url.get_backend_name(),
            )

            # Register an exit hook to close the database connection when the process exits
            atexit.register(DatabaseManager._cleanup_engine, self._engine)
        except Exception:
            self._initialized = False
            try:
                if created_engine is not None:
                    created_engine.dispose()
            except Exception as cleanup_exc:
                # broad-exception: cleanup - Dispose failures are logged while the original initialization error remains authoritative.
                log_safe_exception(
                    logger,
                    "Database engine cleanup failed after initialization error",
                    cleanup_exc,
                    error_code="storage_database_init_cleanup_failed",
                    level=logging.WARNING,
                )
            self._engine = None
            self._SessionLocal = None
            self.__class__._instance = None
            raise

    @contextmanager
    def _schema_initialization_scope(self):
        """Serialize create_all and legacy compatibility work across processes."""
        with self._engine.connect() as connection:
            try:
                if self._is_sqlite_engine:
                    connection.exec_driver_sql("BEGIN IMMEDIATE")
                else:
                    connection.begin()
            except OperationalError as exc:
                code = (
                    "database_locked"
                    if self._is_sqlite_locked_error(exc)
                    else "initialization_lock_failed"
                )
                raise MigrationError(code) from exc
            except Exception as exc:
                # broad-exception: cleanup - Normalize lock failures while the enclosing connection context unwinds.
                raise MigrationError("initialization_lock_failed") from exc

            try:
                yield connection
                connection.commit()
            except Exception:
                try:
                    connection.rollback()
                except Exception as rollback_exc:
                    # broad-exception: cleanup - Log rollback failure before re-raising the original migration error.
                    log_safe_exception(
                        logger,
                        "Database initialization rollback failed",
                        rollback_exc,
                        error_code="storage_database_init_rollback_failed",
                        level=logging.WARNING,
                    )
                raise

    @contextmanager
    def _schema_connection(self):
        """Reuse the initialization transaction or open one for direct repairs."""
        connection = getattr(self, "_schema_initialization_connection", None)
        if connection is not None:
            yield connection
            return
        with self._engine.begin() as standalone_connection:
            yield standalone_connection

    def _schema_bind(self):
        connection = getattr(self, "_schema_initialization_connection", None)
        return connection if connection is not None else self._engine

    @staticmethod
    def _sqlite_user_tables(connection) -> set[str]:
        if connection.dialect.name != "sqlite":
            return set()
        rows = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {str(row[0]) for row in rows}

    @staticmethod
    def _has_known_baseline_anchor(connection, table_names: set[str]) -> bool:
        """Match an immutable supported release profile before any schema write."""
        return match_legacy_schema_profile(connection, table_names) is not None

    @staticmethod
    def _sqlite_ddl_tokens(create_sql: str) -> Tuple[str, ...]:
        """Tokenize SQLite DDL outside quoted values, identifiers, and comments."""
        tokens = []
        token = []
        index = 0
        length = len(create_sql)

        def finish_token() -> None:
            if token:
                tokens.append("".join(token).upper())
                token.clear()

        while index < length:
            character = create_sql[index]
            following = create_sql[index + 1] if index + 1 < length else ""

            if character in ("'", '"', "`"):
                finish_token()
                quote = character
                index += 1
                while index < length:
                    if create_sql[index] == quote:
                        if index + 1 < length and create_sql[index + 1] == quote:
                            index += 2
                            continue
                        index += 1
                        break
                    index += 1
                continue
            if character == "[":
                finish_token()
                closing = create_sql.find("]", index + 1)
                index = length if closing < 0 else closing + 1
                continue
            if character == "-" and following == "-":
                finish_token()
                newline = create_sql.find("\n", index + 2)
                index = length if newline < 0 else newline + 1
                continue
            if character == "/" and following == "*":
                finish_token()
                closing = create_sql.find("*/", index + 2)
                index = length if closing < 0 else closing + 2
                continue
            if character.isalnum() or character == "_":
                token.append(character)
            else:
                finish_token()
            index += 1

        finish_token()
        return tuple(tokens)

    @staticmethod
    def _sqlite_has_explicit_conflict_policy(create_sql: str) -> bool:
        """Detect an explicit ON CONFLICT clause in SQLite table DDL."""
        tokens = DatabaseManager._sqlite_ddl_tokens(create_sql)
        return any(
            current == "ON" and following == "CONFLICT"
            for current, following in zip(tokens, tokens[1:])
        )

    @staticmethod
    def _verify_create_all_baseline(connection) -> None:
        """Prove compatibility work produced a complete runnable metadata shape."""
        actual_tables = DatabaseManager._sqlite_user_tables(connection)
        if not set(Base.metadata.tables).issubset(actual_tables):
            raise MigrationError(
                "legacy_baseline_unproven",
                CURRENT_SCHEMA_VERSION,
            )

        inspector = inspect(connection)
        table_options = {
            str(row[1]): (bool(row[4]), bool(row[5]))
            for row in connection.exec_driver_sql("PRAGMA table_list").fetchall()
            if len(row) > 5 and str(row[2]).lower() == "table"
        }

        def reject_unproven_baseline() -> None:
            raise MigrationError(
                "legacy_baseline_unproven",
                CURRENT_SCHEMA_VERSION,
            )

        for table_name, table in Base.metadata.tables.items():
            create_sql = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = ?",
                (table_name,),
            ).scalar_one_or_none()
            if (
                create_sql is None
                or DatabaseManager._sqlite_has_explicit_conflict_policy(
                    str(create_sql)
                )
            ):
                reject_unproven_baseline()

            ddl_tokens = DatabaseManager._sqlite_ddl_tokens(str(create_sql))
            actual_table_options = table_options.get(table_name)
            if actual_table_options is None:
                actual_table_options = (
                    any(
                        current == "WITHOUT" and following == "ROWID"
                        for current, following in zip(
                            ddl_tokens,
                            ddl_tokens[1:],
                        )
                    ),
                    ddl_tokens[-1:] == ("STRICT",),
                )
            expected_table_options = (
                not bool(
                    table.dialect_options["sqlite"].get("with_rowid", True)
                ),
                bool(table.dialect_options["sqlite"].get("strict", False)),
            )
            if actual_table_options != expected_table_options:
                reject_unproven_baseline()

            column_rows = connection.exec_driver_sql(
                f'PRAGMA table_xinfo("{table_name}")'
            ).fetchall()
            if any(
                len(row) < 7 or int(row[6]) != 0
                for row in column_rows
            ):
                reject_unproven_baseline()
            actual_columns = {
                str(row[1]): (
                    sqlite_type_affinity(str(row[2] or "")),
                    bool(row[5]),
                    bool(row[3]) and not bool(row[5]),
                )
                for row in column_rows
            }
            expected_columns = {
                column.name: (
                    sqlite_type_affinity(str(column.type)),
                    bool(column.primary_key),
                    bool(not column.nullable and not column.primary_key),
                )
                for column in table.columns
            }
            if actual_columns != expected_columns:
                reject_unproven_baseline()

            expected_unique_keys = {
                (
                    tuple(column.name for column in constraint.columns),
                    tuple(
                        str(getattr(column.type, "collation", None) or "BINARY").upper()
                        for column in constraint.columns
                    ),
                )
                for constraint in table.constraints
                if isinstance(constraint, UniqueConstraint)
            }
            expected_unique_keys.update(
                (
                    tuple(column.name for column in index.columns),
                    tuple(
                        str(getattr(column.type, "collation", None) or "BINARY").upper()
                        for column in index.columns
                    ),
                )
                for index in table.indexes
                if index.unique
            )
            actual_unique_keys = set()
            unsupported_unique_index = False
            for index in connection.exec_driver_sql(
                f'PRAGMA index_list("{table_name}")'
            ).fetchall():
                if not bool(index[2]) or str(index[3]).lower() == "pk":
                    continue
                if len(index) > 4 and bool(index[4]):
                    unsupported_unique_index = True
                    continue
                index_name = str(index[1]).replace('"', '""')
                key_terms = tuple(
                    info
                    for info in connection.exec_driver_sql(
                        f'PRAGMA index_xinfo("{index_name}")'
                    ).fetchall()
                    if bool(info[5])
                )
                if any(int(info[1]) < 0 or info[2] is None for info in key_terms):
                    unsupported_unique_index = True
                    continue
                columns = tuple(str(info[2]) for info in key_terms)
                collations = tuple(
                    str(info[4] or "BINARY").upper()
                    for info in key_terms
                )
                if columns:
                    actual_unique_keys.add((columns, collations))
            if unsupported_unique_index or actual_unique_keys != expected_unique_keys:
                reject_unproven_baseline()

            expected_foreign_keys = {
                (
                    tuple(element.parent.name for element in constraint.elements),
                    str(constraint.referred_table.schema or ""),
                    constraint.referred_table.name,
                    tuple(element.column.name for element in constraint.elements),
                    (constraint.ondelete or "").upper(),
                    (constraint.onupdate or "").upper(),
                    bool(constraint.deferrable),
                    (constraint.initially or "").upper(),
                    (constraint.match or "").upper(),
                )
                for constraint in table.foreign_key_constraints
            }
            actual_foreign_keys = {
                (
                    tuple(foreign_key.get("constrained_columns") or ()),
                    str(foreign_key.get("referred_schema") or ""),
                    str(foreign_key.get("referred_table") or ""),
                    tuple(foreign_key.get("referred_columns") or ()),
                    str((foreign_key.get("options") or {}).get("ondelete") or "").upper(),
                    str((foreign_key.get("options") or {}).get("onupdate") or "").upper(),
                    bool((foreign_key.get("options") or {}).get("deferrable")),
                    str((foreign_key.get("options") or {}).get("initially") or "").upper(),
                    str((foreign_key.get("options") or {}).get("match") or "").upper(),
                )
                for foreign_key in inspector.get_foreign_keys(table_name)
            }
            if actual_foreign_keys != expected_foreign_keys:
                reject_unproven_baseline()

        if connection.exec_driver_sql("PRAGMA foreign_key_check").fetchone() is not None:
            reject_unproven_baseline()

    def _ensure_schema_migration_record(self, *, allow_insert: bool = True) -> None:
        values = {
            "version": CURRENT_SCHEMA_VERSION,
            "description": LEGACY_BASELINE_MIGRATION.description,
        }
        with self._schema_connection() as connection:
            existing_versions = set(
                connection.execute(select(DatabaseSchemaMigration.version)).scalars()
            )
            if CURRENT_SCHEMA_VERSION in existing_versions:
                return
            if existing_versions or not allow_insert:
                raise MigrationError(
                    "legacy_baseline_untrusted",
                    CURRENT_SCHEMA_VERSION,
                )
            if self._is_sqlite_engine:
                statement = sqlite_insert(DatabaseSchemaMigration).values(**values)
                statement = statement.on_conflict_do_nothing(index_elements=["version"])
                connection.execute(statement)
            else:
                connection.execute(
                    DatabaseSchemaMigration.__table__.insert().values(**values)
                )

    @classmethod
    def get_instance(cls) -> 'DatabaseManager':
        """获取单例实例"""
        with cls._init_lock:
            if cls._instance is None:
                cls()
            return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（用于测试）"""
        with cls._init_lock:
            if cls._instance is not None:
                if hasattr(cls._instance, '_engine') and cls._instance._engine is not None:
                    cls._instance._engine.dispose()
                cls._instance._initialized = False
                cls._instance = None

    @classmethod
    def _cleanup_engine(cls, engine) -> None:
        """
        清理数据库引擎（atexit 钩子）

        确保程序退出时关闭所有数据库连接，避免 ResourceWarning

        Args:
            engine: SQLAlchemy 引擎对象
        """
        try:
            if engine is not None:
                engine.dispose()
                logger.debug("Database engine disposed")
        except Exception as exc:
            # broad-exception: cleanup - Process-exit engine disposal failures are logged and cannot be recovered at shutdown.
            log_safe_exception(
                logger,
                "Database engine disposal failed",
                exc,
                error_code="storage_database_engine_disposal_failed",
                level=logging.WARNING,
            )

    def _install_sqlite_pragma_handler(self) -> None:
        """为 SQLite 连接安装竞争保护参数。"""
        if not self._is_sqlite_engine:
            return

        @event.listens_for(self._engine, "connect")
        def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f"PRAGMA busy_timeout={int(self._sqlite_busy_timeout_ms)}")
            except Exception as exc:
                # broad-exception: fallback_recorded - A logged PRAGMA failure retains SQLite's connection default.
                log_safe_exception(
                    logger,
                    "SQLite busy timeout initialization failed",
                    exc,
                    error_code="storage_sqlite_busy_timeout_initialization_failed",
                    level=logging.WARNING,
                )
            finally:
                cursor.close()

    def _enable_sqlite_wal_mode(self) -> None:
        """Enable persistent WAL only after the database is proven and migrated."""
        if not (
            self._is_sqlite_engine
            and self._sqlite_file_db
            and self._sqlite_wal_enabled
        ):
            return

        raw_connection = None
        cursor = None
        try:
            raw_connection = self._engine.raw_connection()
            cursor = raw_connection.cursor()
            row = cursor.execute("PRAGMA journal_mode=WAL").fetchone()
            if row is None or str(row[0]).lower() != "wal":
                raise RuntimeError("sqlite_wal_mode_unavailable")
        except Exception as exc:
            # broad-exception: cleanup - Close setup resources while retaining the current journal mode after failure.
            error_text = str(exc).lower()
            if any(token in error_text for token in ("locked", "busy")):
                logger.debug(
                    "SQLite WAL initialization deferred because another "
                    "process holds the database write lock"
                )
            else:
                log_safe_exception(
                    logger,
                    "SQLite WAL initialization failed",
                    exc,
                    error_code="storage_sqlite_wal_initialization_failed",
                    level=logging.WARNING,
                )
        finally:
            if cursor is not None:
                cursor.close()
            if raw_connection is not None:
                raw_connection.close()

    def _is_file_sqlite_database(self) -> bool:
        database = (self._engine.url.database or "").strip()
        return bool(database) and database.lower() != ":memory:"

    def _run_write_transaction(
        self,
        operation_name: str,
        write_operation: Callable[[Session], T],
    ) -> T:
        max_retries = self._sqlite_write_retry_max if self._is_sqlite_engine else 0

        for attempt in range(max_retries + 1):
            session = self.get_session()
            try:
                if self._is_sqlite_engine:
                    # Acquire the SQLite writer lock before any reads inside
                    # `write_operation()` so pre-write existence checks and the
                    # later upsert share one consistent write window.
                    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
                result = write_operation(session)
                session.commit()
                return result
            except OperationalError as exc:
                session.rollback()
                if (
                    self._is_sqlite_engine
                    and self._is_sqlite_locked_error(exc)
                    and attempt < max_retries
                ):
                    delay = self._sqlite_write_retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "SQLite write lock conflict; retrying: %s (%s/%s, %.2fs)",
                        operation_name,
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    if delay > 0:
                        time.sleep(delay)
                    continue
                raise
            except Exception:
                # broad-exception: cleanup - Roll back and re-raise non-lock write failures before closing the session.
                session.rollback()
                raise
            finally:
                session.close()

    @staticmethod
    def _is_sqlite_locked_error(exc: OperationalError) -> bool:
        err_text = str(getattr(exc, "orig", exc)).lower()
        return any(
            token in err_text
            for token in (
                "database is locked",
                "database schema is locked",
                "database table is locked",
            )
        )

    @staticmethod
    def _is_sqlite_duplicate_column_error(exc: OperationalError, column: str) -> bool:
        err_text = str(getattr(exc, "orig", exc)).lower()
        return "duplicate column name" in err_text and column.lower() in err_text

    @staticmethod
    def _normalize_daily_date(value: Any) -> Any:
        if isinstance(value, str):
            return datetime.strptime(value, '%Y-%m-%d').date()
        if isinstance(value, pd.Timestamp):
            return value.date()
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _normalize_sql_value(value: Any) -> Any:
        return None if pd.isna(value) else value
    
    def get_session(self) -> Session:
        """
        获取数据库 Session
        
        使用示例:
            with db.get_session() as session:
                # 执行查询
                session.commit()  # 如果需要
        """
        if not getattr(self, '_initialized', False) or not hasattr(self, '_SessionLocal'):
            raise RuntimeError(
                "DatabaseManager 未正确初始化。"
                "请确保通过 DatabaseManager.get_instance() 获取实例。"
            )
        session = self._SessionLocal()
        try:
            return session
        except Exception:
            session.close()
            raise

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            # broad-exception: cleanup - Roll back and re-raise transaction failures before closing the session.
            session.rollback()
            raise
        finally:
            session.close()
