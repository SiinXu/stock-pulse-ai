"""Ordered migration runner contracts against isolated SQLite databases."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from functools import partial, wraps
import gc
import hashlib
import importlib
import json
import multiprocessing
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable, Iterable
import warnings

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

import src.migrations.runner as migration_runner_module
from src.config import Config
from src.migrations.legacy_profiles import (
    LEGACY_SCHEMA_PROFILES,
    match_legacy_schema_profile,
)
from src.migrations.registry import (
    LEGACY_BASELINE_MIGRATION,
    REGISTRY_METADATA_MIGRATION,
    TARGET_VERSION,
    get_migrations,
)
from src.migrations.cli import main as migration_cli_main
from src.migrations.runner import MigrationRunner
from src.migrations.types import (
    Migration,
    MigrationExecution,
    MigrationError,
    MigrationRegistryError,
    calculate_checksum,
    normalize_checksum_source,
    read_checksum_source,
    validate_registry,
)
from src.storage import Base, DatabaseManager


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "schema_migrations"
CORE_TABLES = {
    "analysis_history",
    "portfolio_accounts",
    "schema_migrations",
    "stock_daily",
}
STATUS_KEYS = {
    "applied_ids",
    "checksum_mismatches",
    "current_version",
    "description_mismatches",
    "failed_migration_id",
    "failure_code",
    "pending_ids",
    "success",
    "target_version",
    "unknown_ids",
}


@pytest.fixture(autouse=True)
def _reset_database_singletons() -> Iterable[None]:
    DatabaseManager.reset_instance()
    Config.reset_instance()
    yield
    DatabaseManager.reset_instance()
    Config.reset_instance()


def _no_op_upgrade(_execution: MigrationExecution) -> None:
    return None


async def _async_no_op_upgrade(_execution: MigrationExecution) -> None:
    return None


async def _async_generator_no_op_upgrade(_execution: MigrationExecution):
    yield None


def _generator_no_op_upgrade(_execution: MigrationExecution):
    yield None


@asynccontextmanager
async def _async_contextmanager_upgrade(_execution: MigrationExecution):
    yield None


@contextmanager
def _contextmanager_upgrade(_execution: MigrationExecution):
    yield None


class _AsyncCallableUpgrade:
    async def __call__(self, _execution: MigrationExecution) -> None:
        return None


class _AsyncGeneratorCallableUpgrade:
    async def __call__(self, _execution: MigrationExecution):
        yield None


class _GeneratorCallableUpgrade:
    def __call__(self, _execution: MigrationExecution):
        yield None


def _custom_migration(
    sequence: int,
    name: str,
    *,
    upgrade: Callable[[MigrationExecution], None] = _no_op_upgrade,
    source: str | None = None,
    description: str | None = None,
) -> Migration:
    migration_id = f"209901010{sequence:03d}_{name}"
    assert migration_id > TARGET_VERSION
    return Migration(
        id=migration_id,
        description=description or f"Test migration: {name}",
        upgrade=upgrade,
        checksum_source=source or f"test_migration={name}\nrevision={sequence}",
    )


def _source_bound_migration_from_source(tmp_path: Path, source: str) -> Migration:
    module_name = "migration_source_guard_probe"
    source_path = tmp_path / f"{module_name}.py"
    source_path.write_text(source, encoding="utf-8")
    namespace = {
        "__name__": module_name,
        "Connection": Connection,
        "MigrationExecution": MigrationExecution,
    }
    exec(compile(source, str(source_path), "exec"), namespace)
    return Migration.from_source_file(
        id="209901010001_source_guard_probe",
        description="Source guard probe",
        upgrade=namespace["upgrade"],
        source_file=source_path,
    )


def _source_bound_migration_from_body(tmp_path: Path, body: str) -> Migration:
    source = "def upgrade(connection):\n" + "\n".join(
        f"    {line}" for line in body.splitlines()
    ) + "\n"
    return _source_bound_migration_from_source(tmp_path, source)


def _runner_with(*migrations: Migration) -> MigrationRunner:
    return MigrationRunner((*get_migrations(), *migrations))


def _request_transaction_control(
    execution: MigrationExecution,
    operation: str,
) -> None:
    getattr(execution, operation)()


def _request_raw_dbapi_connection(execution: MigrationExecution):
    return getattr(getattr(execution, "connection"), "driver_connection")


def _assert_execution_capability_revoked(
    execution: MigrationExecution,
    migration_id: str,
) -> None:
    with pytest.raises(MigrationError) as error:
        execution.exec_driver_sql("SELECT 1")

    assert error.value.failure_code == "migration_transaction_control_forbidden"
    assert error.value.migration_id == migration_id
    assert str(error.value) == (
        "Database migration failed: "
        "code=migration_transaction_control_forbidden "
        f"migration_id={migration_id}"
    )


def _database_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _engine_with_applied_production_registry(path: Path) -> Engine:
    engine = create_engine(_database_url(path))
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE schema_migrations ("
            "version VARCHAR(64) NOT NULL PRIMARY KEY, "
            "description VARCHAR(255) NOT NULL, "
            "applied_at DATETIME NOT NULL, "
            "checksum VARCHAR(64))"
        )
        for migration in get_migrations():
            connection.exec_driver_sql(
                "INSERT INTO schema_migrations "
                "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
                (
                    migration.id,
                    migration.description,
                    "2099-01-01 00:00:00",
                    migration.checksum,
                ),
            )
    return engine


def _applied_rows(bind: Engine) -> list[tuple[str, str, str | None]]:
    with bind.connect() as connection:
        return [
            (str(row[0]), str(row[1]), None if row[2] is None else str(row[2]))
            for row in connection.exec_driver_sql(
                "SELECT version, description, checksum "
                "FROM schema_migrations ORDER BY version"
            ).fetchall()
        ]


def _applied_ids(bind: Engine) -> tuple[str, ...]:
    return tuple(row[0] for row in _applied_rows(bind))


def _table_exists(bind: Engine, table_name: str) -> bool:
    with bind.connect() as connection:
        return connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).scalar_one_or_none() == 1


def _load_sql_fixture(db_path: Path, fixture_name: str) -> None:
    sql = (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as connection:
        connection.executescript(sql)


def _recreate_table_without_clause(
    db_path: Path,
    table_name: str,
    clause: str,
) -> None:
    _recreate_table_with_replacement(
        db_path,
        table_name,
        f", \n\t{clause}",
        "",
    )


def _recreate_table_with_replacement(
    db_path: Path,
    table_name: str,
    old: str,
    new: str,
) -> None:
    with sqlite3.connect(db_path) as connection:
        create_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()[0]
        malformed_sql = create_sql.replace(old, new, 1)
        assert malformed_sql != create_sql
        connection.execute(f'DROP TABLE "{table_name}"')
        connection.execute(malformed_sql)


def _legacy_fact_snapshot(db_path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(db_path) as connection:
        return {
            "portfolio": connection.execute(
                "SELECT accounts.id, accounts.owner_id, accounts.name, "
                "accounts.base_currency, trades.id, trades.trade_uid, trades.symbol, "
                "trades.market, trades.currency, trades.trade_date, trades.side, "
                "trades.quantity, trades.price, trades.fee, trades.tax, trades.note "
                "FROM portfolio_accounts AS accounts "
                "JOIN portfolio_trades AS trades ON trades.account_id = accounts.id "
                "ORDER BY accounts.id, trades.id"
            ).fetchall(),
            "analysis": connection.execute(
                "SELECT id, query_id, code, name, report_type, sentiment_score, "
                "operation_advice, trend_prediction, analysis_summary, ideal_buy, "
                "secondary_buy, stop_loss, take_profit, created_at "
                "FROM analysis_history ORDER BY id"
            ).fetchall(),
        }


def _historical_fact_snapshot(db_path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(db_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        result = {
            "stock_daily": connection.execute(
                "SELECT id, code, date, open, high, low, close, volume, amount, "
                "data_source, created_at, updated_at FROM stock_daily ORDER BY id"
            ).fetchall(),
            "analysis_history": connection.execute(
                "SELECT id, query_id, code, name, report_type, sentiment_score, "
                "operation_advice, trend_prediction, analysis_summary, raw_result, "
                "created_at FROM analysis_history ORDER BY id"
            ).fetchall(),
        }
        if {"portfolio_accounts", "portfolio_trades"}.issubset(tables):
            portfolio_rows = connection.execute(
                "SELECT accounts.id, accounts.owner_id, accounts.name, "
                "accounts.base_currency, trades.id, trades.trade_uid, trades.symbol, "
                "trades.market, trades.currency, trades.trade_date, trades.side, "
                "trades.quantity, trades.price, trades.fee, trades.tax, trades.note "
                "FROM portfolio_accounts AS accounts "
                "JOIN portfolio_trades AS trades ON trades.account_id = accounts.id "
                "ORDER BY accounts.id, trades.id"
            ).fetchall()
            if portfolio_rows:
                result["portfolio"] = portfolio_rows
        return result


def _sqlite_master_snapshot(db_path: Path) -> list[tuple]:
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE sql IS NOT NULL ORDER BY type, name"
        ).fetchall()


def _sqlite_master_digest(db_path: Path) -> str:
    material = json.dumps(
        _sqlite_master_snapshot(db_path),
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _initialize_database_process(
    database_url: str,
    barrier,
    result_queue,
) -> None:
    """Initialize one isolated process and return only structured test state."""
    try:
        barrier.wait(timeout=20)
        database = DatabaseManager(db_url=database_url)
        result_queue.put(("ok", _applied_ids(database._engine)))
    except Exception as exc:
        result_queue.put(
            (
                "error",
                type(exc).__name__,
                getattr(exc, "failure_code", None),
            )
        )
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def test_production_registry_is_stable_unique_and_strictly_ordered_across_imports() -> None:
    import src.migrations.registry as registry_module

    before = tuple(
        (migration.id, migration.description, migration.checksum)
        for migration in registry_module.get_migrations()
    )
    reloaded = importlib.reload(registry_module)
    after = tuple(
        (migration.id, migration.description, migration.checksum)
        for migration in reloaded.get_migrations()
    )

    ids = tuple(item[0] for item in after)
    assert before == after
    assert ids == tuple(sorted(ids))
    assert len(ids) == len(set(ids))
    assert ids == (LEGACY_BASELINE_MIGRATION.id, REGISTRY_METADATA_MIGRATION.id)
    assert reloaded.TARGET_VERSION == ids[-1]
    assert all(len(checksum) == 64 for _, _, checksum in after)


def test_historical_fixture_manifest_is_fixed_and_schema_digests_match(
    tmp_path: Path,
) -> None:
    manifest = json.loads(
        (FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    expected_sources = {
        "v3.0.0": "52917baa02210fb7911491fcf48ecbf3f70e5812",
        "v3.4.0": "0154992e18f6a5a09199a151ee75661e78b9c12f",
        "v3.20.0": "d22ff1c42d37d1b1d7d955c6dfb00daf1f62e69d",
        "v3.21.0": "40c5c75b2ecfafafd5bbc6bbae9696c5b7d9a43d",
        "v3.26.3": "88f2eeef57a7c99ed484f3be5e8cfa7a54a9ece2",
    }
    entries = {entry["source_tag"]: entry for entry in manifest["fixtures"]}

    assert {tag: entry["source_commit"] for tag, entry in entries.items()} == (
        expected_sources
    )
    assert {profile.source_tag for profile in LEGACY_SCHEMA_PROFILES} == {
        "v3.0.0",
        "v3.4.0",
        "v3.20.0",
    }
    for profile in LEGACY_SCHEMA_PROFILES:
        entry = entries[profile.source_tag]
        assert profile.source_commit == entry["source_commit"]
        assert profile.schema_digest == entry["schema_digest"]
        assert profile.source_profile_digest == entry["profile_digest"]
    for tag, entry in entries.items():
        db_path = tmp_path / f"{tag}.sqlite"
        _load_sql_fixture(db_path, entry["file"])
        assert _sqlite_master_digest(db_path) == entry["schema_digest"]
        assert set(entry["canaries"]).issubset(
            {"stock_daily", "analysis_history", "portfolio_accounts", "portfolio_trades"}
        )


@pytest.mark.parametrize(
    ("fixture_name", "expected_profile_id"),
    (
        ("v3_0_0.sql", "stockpulse_v3_0_0"),
        ("v3_4_0.sql", "stockpulse_v3_4_0"),
        ("v3_20_0.sql", "stockpulse_v3_20_0"),
        ("v3_21_0.sql", None),
        ("v3_26_3.sql", None),
    ),
)
def test_fixed_historical_release_upgrades_preserve_facts_and_are_idempotent(
    tmp_path: Path,
    fixture_name: str,
    expected_profile_id: str | None,
) -> None:
    db_path = tmp_path / fixture_name.replace(".sql", ".sqlite")
    _load_sql_fixture(db_path, fixture_name)
    before_facts = _historical_fact_snapshot(db_path)

    inspection_engine = create_engine(_database_url(db_path))
    try:
        with inspection_engine.connect() as connection:
            table_names = {
                str(row[0])
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            matched = match_legacy_schema_profile(connection, table_names)
    finally:
        inspection_engine.dispose()
    assert (None if matched is None else matched.profile_id) == expected_profile_id

    database = DatabaseManager(db_url=_database_url(db_path))
    expected_rows = [
        (migration.id, migration.description, migration.checksum)
        for migration in get_migrations()
    ]
    assert _applied_rows(database._engine) == expected_rows
    assert _historical_fact_snapshot(db_path) == before_facts
    first_schema = _sqlite_master_snapshot(db_path)

    DatabaseManager.reset_instance()
    second_database = DatabaseManager(db_url=_database_url(db_path))
    assert _applied_rows(second_database._engine) == expected_rows
    assert _historical_fact_snapshot(db_path) == before_facts
    assert _sqlite_master_snapshot(db_path) == first_schema


def test_partial_newer_release_cannot_fall_back_to_an_older_profile(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "partial-v3.20.sqlite"
    _load_sql_fixture(db_path, "v3_20_0.sql")
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE agent_provider_turns")
    before_schema = _sqlite_master_snapshot(db_path)
    before_facts = _historical_fact_snapshot(db_path)

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert _sqlite_master_snapshot(db_path) == before_schema
    assert _historical_fact_snapshot(db_path) == before_facts
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
    assert registry is None


def test_registry_rejects_duplicate_and_non_increasing_ids() -> None:
    first = _custom_migration(1, "first")
    second = _custom_migration(2, "second")

    with pytest.raises(MigrationRegistryError) as duplicate_error:
        validate_registry((*get_migrations(), first, first))
    assert duplicate_error.value.failure_code == "duplicate_migration_id"
    assert duplicate_error.value.migration_id == first.id

    with pytest.raises(MigrationRegistryError) as order_error:
        validate_registry((*get_migrations(), second, first))
    assert order_error.value.failure_code == "migration_order_invalid"
    assert order_error.value.migration_id == first.id


def test_checksum_normalizes_line_endings_but_preserves_semantic_whitespace() -> None:
    lf_source = 'SQL = """tenant-a \nnext"""\n'
    crlf_source = 'SQL = """tenant-a \r\nnext"""\r\n'
    changed_source = 'SQL = """tenant-a\nnext"""\n'

    lf_checksum = calculate_checksum(
        migration_id="209901010001_checksum_probe",
        description="Checksum normalization probe",
        source=lf_source,
    )
    crlf_checksum = calculate_checksum(
        migration_id="209901010001_checksum_probe",
        description="Checksum normalization probe",
        source=crlf_source,
    )

    assert normalize_checksum_source(lf_source) == lf_source
    assert normalize_checksum_source(crlf_source) == normalize_checksum_source(lf_source)
    assert lf_checksum == crlf_checksum
    assert lf_checksum == calculate_checksum(
        migration_id="209901010001_checksum_probe",
        description="Checksum normalization probe",
        source=lf_source,
    )
    assert lf_checksum != calculate_checksum(
        migration_id="209901010001_checksum_probe",
        description="Checksum normalization probe",
        source=changed_source,
    )


def test_production_checksum_is_bound_to_complete_authored_upgrade_source() -> None:
    migration = REGISTRY_METADATA_MIGRATION
    source = read_checksum_source(migration.upgrade.__code__.co_filename)

    assert migration.source_bound is True
    assert migration.checksum == calculate_checksum(
        migration_id=migration.id,
        description=migration.description,
        source=source,
    )
    changed_upgrade_source = source.replace(
        "ADD COLUMN checksum VARCHAR(64)",
        "ADD COLUMN checksum VARCHAR(65)",
        1,
    )
    assert changed_upgrade_source != source
    assert migration.checksum != calculate_checksum(
        migration_id=migration.id,
        description=migration.description,
        source=changed_upgrade_source,
    )


def test_source_bound_migration_rejects_a_different_module_file() -> None:
    with pytest.raises(ValueError, match="does not match upgrade module"):
        Migration.from_source_file(
            id="209901010001_wrong_source",
            description="Wrong source binding probe",
            upgrade=_no_op_upgrade,
            source_file=REGISTRY_METADATA_MIGRATION.upgrade.__code__.co_filename,
        )


@pytest.mark.parametrize(
    "source",
    (
        "async def upgrade(connection):\n    return None\n",
        "async def upgrade(connection):\n    yield None\n",
        "def upgrade(connection):\n    yield None\n",
        (
            "from contextlib import asynccontextmanager\n\n"
            "@asynccontextmanager\n"
            "async def upgrade(connection):\n"
            "    yield None\n"
        ),
        (
            "from contextlib import contextmanager\n\n"
            "@contextmanager\n"
            "def upgrade(connection):\n"
            "    yield None\n"
        ),
    ),
    ids=(
        "coroutine",
        "async-generator",
        "generator",
        "async-contextmanager",
        "contextmanager",
    ),
)
def test_source_bound_migration_rejects_lazy_upgrade(
    tmp_path: Path,
    source: str,
) -> None:
    with pytest.raises(TypeError, match="upgrade must be synchronous"):
        _source_bound_migration_from_source(tmp_path, source)


@pytest.mark.parametrize(
    "upgrade",
    (
        _async_no_op_upgrade,
        partial(_async_no_op_upgrade),
        _AsyncCallableUpgrade(),
        partial(_AsyncCallableUpgrade()),
        _async_generator_no_op_upgrade,
        partial(_async_generator_no_op_upgrade),
        _AsyncGeneratorCallableUpgrade(),
        partial(_AsyncGeneratorCallableUpgrade()),
        _generator_no_op_upgrade,
        partial(_generator_no_op_upgrade),
        _GeneratorCallableUpgrade(),
        partial(_GeneratorCallableUpgrade()),
        _async_contextmanager_upgrade,
        _contextmanager_upgrade,
    ),
    ids=(
        "async-function",
        "partial-async-function",
        "async-callable-object",
        "partial-async-callable-object",
        "async-generator-function",
        "partial-async-generator-function",
        "async-generator-callable-object",
        "partial-async-generator-callable-object",
        "generator-function",
        "partial-generator-function",
        "generator-callable-object",
        "partial-generator-callable-object",
        "async-contextmanager",
        "contextmanager",
    ),
)
def test_migration_registration_rejects_lazy_callable(upgrade) -> None:
    with pytest.raises(TypeError, match="upgrade must be synchronous"):
        _custom_migration(1, "lazy_registration", upgrade=upgrade)


def test_migration_registration_rejects_wrapped_lazy_chain() -> None:
    @wraps(_generator_no_op_upgrade)
    def middle(_execution: MigrationExecution) -> None:
        return None

    @wraps(middle)
    def outer(_execution: MigrationExecution) -> None:
        return None

    with pytest.raises(TypeError, match="upgrade must be synchronous"):
        _custom_migration(1, "wrapped_lazy_registration", upgrade=outer)


def test_migration_registration_rejects_wrapped_cycle() -> None:
    def cyclic_upgrade(_execution: MigrationExecution) -> None:
        return None

    cyclic_upgrade.__wrapped__ = cyclic_upgrade

    with pytest.raises(TypeError, match="upgrade must be synchronous"):
        _custom_migration(1, "cyclic_registration", upgrade=cyclic_upgrade)


@pytest.mark.parametrize(
    "body",
    (
        "connection.begin()",
        "connection.close()",
        "connection.commit()",
        "connection.rollback()",
    ),
)
def test_source_bound_migration_rejects_transaction_control(
    tmp_path: Path,
    body: str,
) -> None:
    with pytest.raises(ValueError, match="forbidden transaction control"):
        _source_bound_migration_from_body(tmp_path, body)


@pytest.mark.parametrize(
    "body",
    (
        "raw_connection = connection.connection",
        "connection.connection.driver_connection.set_authorizer(None)",
    ),
)
def test_source_bound_migration_rejects_raw_dbapi_access(
    tmp_path: Path,
    body: str,
) -> None:
    with pytest.raises(ValueError, match="forbidden raw DBAPI access"):
        _source_bound_migration_from_body(tmp_path, body)


def test_source_bound_migration_rejects_nested_closure_raw_dbapi_access(
    tmp_path: Path,
) -> None:
    source = "\n".join(
        (
            "def upgrade(connection):",
            "    def helper():",
            "        dbapi = connection.connection",
            "        dbapi.set_authorizer(None)",
            "        dbapi.commit()",
            "    helper()",
            "",
        )
    )

    with pytest.raises(ValueError, match="forbidden raw DBAPI access"):
        _source_bound_migration_from_source(tmp_path, source)


def test_source_bound_migration_rejects_typed_helper_transaction_control(
    tmp_path: Path,
) -> None:
    source = "\n".join(
        (
            "def helper(execution: MigrationExecution):",
            "    execution.commit()",
            "",
            "def upgrade(execution):",
            "    helper(execution)",
            "",
        )
    )

    with pytest.raises(ValueError, match="forbidden transaction control"):
        _source_bound_migration_from_source(tmp_path, source)


def test_source_guard_ignores_transaction_control_text(tmp_path: Path) -> None:
    migration = _source_bound_migration_from_body(
        tmp_path,
        '# connection.commit() is forbidden\nreturn "connection.connection"',
    )

    assert migration.source_bound is True


def test_source_guard_allows_unrelated_domain_attributes(tmp_path: Path) -> None:
    migration = _source_bound_migration_from_body(
        tmp_path,
        "\n".join(
            (
                'row = type("Row", (), {"close": 10.5, "connection": "feed"})()',
                'result = type("Result", (), {"close": lambda self: None})()',
                "result.close()",
                'connection.exec_driver_sql("SELECT 1").close()',
                "return row.close, row.connection",
            )
        ),
    )

    assert migration.source_bound is True


def test_source_guard_keeps_connection_names_scoped_to_their_function(
    tmp_path: Path,
) -> None:
    migration = _source_bound_migration_from_source(
        tmp_path,
        "\n".join(
            (
                "def typed_helper(record: Connection):",
                "    return record",
                "",
                "def domain_helper(record):",
                "    return record.close",
                "",
                "def upgrade(connection):",
                "    return domain_helper(type('Row', (), {'close': 10.5})())",
                "",
            )
        ),
    )

    assert migration.source_bound is True


def test_source_guard_respects_nested_parameter_shadowing(tmp_path: Path) -> None:
    migration = _source_bound_migration_from_source(
        tmp_path,
        "\n".join(
            (
                "def upgrade(connection):",
                "    def domain_helper(connection):",
                "        return connection.close",
                "    return domain_helper(type('Row', (), {'close': 10.5})())",
                "",
            )
        ),
    )

    assert migration.source_bound is True


def test_fresh_memory_database_has_core_tables_and_two_applied_migrations() -> None:
    database = DatabaseManager(db_url="sqlite:///:memory:")

    assert CORE_TABLES.issubset(set(inspect(database._engine).get_table_names()))
    assert _applied_ids(database._engine) == tuple(
        migration.id for migration in get_migrations()
    )
    assert all(checksum for _, _, checksum in _applied_rows(database._engine))

    status = MigrationRunner().status(database._engine)
    verification = MigrationRunner().verify(database._engine)
    assert status.success is True
    assert status.current_version == TARGET_VERSION
    assert status.pending_ids == ()
    assert verification.success is True


def test_fresh_file_database_restart_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.sqlite"
    url = _database_url(db_path)

    first = DatabaseManager(db_url=url)
    first_rows = _applied_rows(first._engine)
    first_applied_at: list[tuple[str, str]]
    with sqlite3.connect(db_path) as connection:
        first_applied_at = connection.execute(
            "SELECT version, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()

    DatabaseManager.reset_instance()
    Config.reset_instance()
    second = DatabaseManager(db_url=url)
    with sqlite3.connect(db_path) as connection:
        second_applied_at = connection.execute(
            "SELECT version, applied_at FROM schema_migrations ORDER BY version"
        ).fetchall()

    assert CORE_TABLES.issubset(set(inspect(second._engine).get_table_names()))
    assert _applied_rows(second._engine) == first_rows
    assert second_applied_at == first_applied_at
    assert len(first_rows) == 2


@pytest.mark.parametrize(
    "fixture_name",
    (
        "legacy_baseline_no_checksum.sql",
        "legacy_baseline_null_checksum.sql",
    ),
)
def test_historical_fixture_upgrade_preserves_portfolio_and_analysis_facts(
    tmp_path: Path,
    fixture_name: str,
) -> None:
    db_path = tmp_path / fixture_name.replace(".sql", ".sqlite")
    _load_sql_fixture(db_path, fixture_name)
    before = _legacy_fact_snapshot(db_path)

    database = DatabaseManager(db_url=_database_url(db_path))
    after = _legacy_fact_snapshot(db_path)

    assert after == before
    assert len(after["portfolio"]) == 1
    assert len(after["analysis"]) == 1
    assert _applied_ids(database._engine) == tuple(
        migration.id for migration in get_migrations()
    )
    assert all(checksum for _, _, checksum in _applied_rows(database._engine))
    with sqlite3.connect(db_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(schema_migrations)").fetchall()
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert "checksum" in columns
    assert integrity == "ok"
    assert foreign_key_violations == []


def test_unknown_future_migration_fails_closed_without_stamping_baseline(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "unknown-future.sqlite"
    unknown_id = "999912312359_unknown_future_migration"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version VARCHAR(64) NOT NULL PRIMARY KEY, "
            "description VARCHAR(255) NOT NULL, "
            "applied_at DATETIME NOT NULL, checksum VARCHAR(64))"
        )
        connection.execute(
            "INSERT INTO schema_migrations "
            "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
            (unknown_id, "Unknown future migration", "2099-12-31 23:59:00", "f" * 64),
        )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "unknown_migration"
    assert error.value.migration_id == unknown_id
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT version, description, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert rows == [(unknown_id, "Unknown future migration", "f" * 64)]
    assert LEGACY_BASELINE_MIGRATION.id not in {row[0] for row in rows}
    with sqlite3.connect(db_path) as connection:
        stock_daily = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'stock_daily'"
        ).fetchone()
    assert stock_daily is None


def test_registry_without_version_primary_key_fails_closed(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "registry-without-primary-key.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version VARCHAR(64) NOT NULL, description VARCHAR(255) NOT NULL, "
            "applied_at DATETIME NOT NULL, checksum VARCHAR(64))"
        )
        connection.execute(
            "INSERT INTO schema_migrations "
            "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
            (
                LEGACY_BASELINE_MIGRATION.id,
                LEGACY_BASELINE_MIGRATION.description,
                "2026-06-05 00:00:00",
                LEGACY_BASELINE_MIGRATION.checksum,
            ),
        )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "registry_schema_invalid"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT version, description, checksum FROM schema_migrations"
        ).fetchall()
        stock_daily = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'stock_daily'"
        ).fetchone()
    assert rows == [
        (
            LEGACY_BASELINE_MIGRATION.id,
            LEGACY_BASELINE_MIGRATION.description,
            LEGACY_BASELINE_MIGRATION.checksum,
        )
    ]
    assert stock_daily is None


def test_duplicate_applied_rows_fail_closed_without_initialization_writes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "duplicate-applied-rows.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version VARCHAR(64) NOT NULL, description VARCHAR(255) NOT NULL, "
            "applied_at DATETIME NOT NULL, checksum VARCHAR(64))"
        )
        for migration in get_migrations():
            connection.executemany(
                "INSERT INTO schema_migrations "
                "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
                [
                    (
                        migration.id,
                        migration.description,
                        "2026-07-16 00:00:00",
                        migration.checksum,
                    ),
                    (
                        migration.id,
                        migration.description,
                        "2026-07-16 00:00:00",
                        migration.checksum,
                    ),
                ],
            )

    engine = create_engine(_database_url(db_path))
    try:
        verification = MigrationRunner().verify(engine)
    finally:
        engine.dispose()

    assert verification.success is False
    assert verification.failure_code == "duplicate_applied_migration"
    assert verification.failed_migration_id == LEGACY_BASELINE_MIGRATION.id

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))
    assert error.value.failure_code == "duplicate_applied_migration"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT version, COUNT(*) FROM schema_migrations "
            "GROUP BY version ORDER BY version"
        ).fetchall()
        table_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name != 'schema_migrations'"
        ).fetchone()[0]
    assert rows == [(migration.id, 2) for migration in get_migrations()]
    assert table_count == 0


def test_unrelated_database_is_not_stamped_or_modified_as_known_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SQLITE_WAL_ENABLED", "true")
    db_path = tmp_path / "untrusted.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE unrelated_application_data "
            "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO unrelated_application_data (id, value) VALUES (1, 'keep')"
        )
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    before_hash = hashlib.sha256(db_path.read_bytes()).hexdigest()

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert error.value.migration_id == LEGACY_BASELINE_MIGRATION.id
    with sqlite3.connect(db_path) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        rows = connection.execute(
            "SELECT id, value FROM unrelated_application_data"
        ).fetchall()
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
    assert tables == {"unrelated_application_data"}
    assert rows == [(1, "keep")]
    assert journal_mode == "delete"
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before_hash


def test_partial_known_table_is_not_enough_to_stamp_legacy_baseline(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "partial-known-table.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE stock_daily "
            "(id INTEGER PRIMARY KEY, code VARCHAR(10), date DATE)"
        )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    with sqlite3.connect(db_path) as connection:
        columns = [
            str(row[1])
            for row in connection.execute("PRAGMA table_info(stock_daily)").fetchall()
        ]
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert columns == ["id", "code", "date"]
    assert tables == {"stock_daily"}


def test_lookalike_table_with_all_column_names_but_wrong_shape_is_rejected(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "lookalike-known-table.sqlite"
    stock_daily_columns = tuple(Base.metadata.tables["stock_daily"].columns.keys())
    declarations = ", ".join(
        f'"{column_name}" TEXT' for column_name in stock_daily_columns
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"CREATE TABLE stock_daily ({declarations})")

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    with sqlite3.connect(db_path) as connection:
        table_info = connection.execute("PRAGMA table_info(stock_daily)").fetchall()
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
    assert tuple(str(row[1]) for row in table_info) == stock_daily_columns
    assert all(str(row[2]).upper() == "TEXT" and int(row[5]) == 0 for row in table_info)
    assert registry is None


@pytest.mark.parametrize(
    ("fixture_name", "table_name", "removed_clause", "inspection_sql"),
    (
        (
            "v3_0_0.sql",
            "stock_daily",
            "CONSTRAINT uix_code_date UNIQUE (code, date)",
            "PRAGMA index_list(stock_daily)",
        ),
        (
            "v3_20_0.sql",
            "portfolio_trades",
            "FOREIGN KEY(account_id) REFERENCES portfolio_accounts (id)",
            "PRAGMA foreign_key_list(portfolio_trades)",
        ),
    ),
)
def test_legacy_baseline_rejects_missing_table_constraints_without_stamping(
    tmp_path: Path,
    fixture_name: str,
    table_name: str,
    removed_clause: str,
    inspection_sql: str,
) -> None:
    db_path = tmp_path / f"missing-{table_name}-constraint.sqlite"
    _load_sql_fixture(db_path, fixture_name)
    _recreate_table_without_clause(db_path, table_name, removed_clause)

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert error.value.migration_id == LEGACY_BASELINE_MIGRATION.id
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        remaining_constraints = connection.execute(inspection_sql).fetchall()
    assert registry is None
    assert remaining_constraints == []


def test_legacy_baseline_rejects_partial_unique_index_as_incomplete_constraint(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "partial-unique-constraint.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    _recreate_table_without_clause(
        db_path,
        "stock_daily",
        "CONSTRAINT uix_code_date UNIQUE (code, date)",
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE UNIQUE INDEX partial_uix_code_date "
            "ON stock_daily (code, date) WHERE code != ''"
        )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        index_row = connection.execute(
            "SELECT partial FROM pragma_index_list('stock_daily') "
            "WHERE name = 'partial_uix_code_date'"
        ).fetchone()
    assert registry is None
    assert index_row == (1,)


def test_legacy_baseline_rejects_expression_unique_index_as_incomplete_constraint(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "expression-unique-constraint.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    _recreate_table_without_clause(
        db_path,
        "stock_daily",
        "CONSTRAINT uix_code_date UNIQUE (code, date)",
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE UNIQUE INDEX expression_uix_code_date "
            "ON stock_daily (code, date, coalesce(data_source, ''))"
        )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        expression_terms = connection.execute(
            "PRAGMA index_xinfo(expression_uix_code_date)"
        ).fetchall()
    assert registry is None
    assert any(int(term[1]) < 0 and bool(term[5]) for term in expression_terms)


def test_legacy_baseline_rejects_different_unique_collation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "collated-unique-constraint.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    _recreate_table_without_clause(
        db_path,
        "stock_daily",
        "CONSTRAINT uix_code_date UNIQUE (code, date)",
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE UNIQUE INDEX collated_uix_code_date "
            "ON stock_daily (code COLLATE NOCASE, date)"
        )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None


def test_legacy_baseline_rejects_different_unique_conflict_policy(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "unique-conflict-policy.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    unique_constraint = "CONSTRAINT uix_code_date UNIQUE (code, date)"
    _recreate_table_with_replacement(
        db_path,
        "stock_daily",
        unique_constraint,
        f"{unique_constraint} ON CONFLICT IGNORE",
    )
    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
    assert registry is None


def test_legacy_baseline_rejects_without_rowid_table_option(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "without-rowid.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    _recreate_table_with_replacement(
        db_path,
        "stock_daily",
        "\n)",
        "\n) WITHOUT ROWID",
    )
    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        table_options = connection.execute(
            "PRAGMA table_list('stock_daily')"
        ).fetchone()
    assert registry is None
    assert table_options is not None and int(table_options[4]) == 1


def test_legacy_baseline_rejects_different_foreign_key_timing(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "deferred-foreign-key.sqlite"
    _load_sql_fixture(db_path, "v3_20_0.sql")
    foreign_key = "FOREIGN KEY(account_id) REFERENCES portfolio_accounts (id)"
    _recreate_table_with_replacement(
        db_path,
        "portfolio_trades",
        foreign_key,
        f"{foreign_key} DEFERRABLE INITIALLY DEFERRED",
    )
    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None


def test_legacy_baseline_rejects_foreign_key_violations_without_stamping(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "orphaned-foreign-key.sqlite"
    _load_sql_fixture(db_path, "v3_20_0.sql")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO portfolio_trades "
            "(id, account_id, trade_uid, symbol, market, currency, trade_date, "
            "side, quantity, price) VALUES "
            "(999, 999, 'fixture-orphan', 'TEST0002', 'cn', 'CNY', "
            "'2020-01-03', 'buy', 1, 1)"
        )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_unproven"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        orphan = connection.execute(
            "SELECT trade_uid, account_id FROM portfolio_trades WHERE id = 999"
        ).fetchone()
    assert registry is None
    assert violations
    assert orphan == ("fixture-orphan", 999)


@pytest.mark.parametrize(
    ("old", "new"),
    (
        ("open FLOAT", "open FLOAT NOT NULL"),
        ("PRIMARY KEY (id)", "PRIMARY KEY (id, code)"),
        (
            "updated_at DATETIME, \n\tPRIMARY KEY",
            "updated_at DATETIME, \n\textra_shadow TEXT, \n\tPRIMARY KEY",
        ),
    ),
)
def test_legacy_baseline_requires_exact_column_and_key_shape(
    tmp_path: Path,
    old: str,
    new: str,
) -> None:
    db_path = tmp_path / "nonexact-column-shape.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    _recreate_table_with_replacement(db_path, "stock_daily", old, new)

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
    assert registry is None


def test_legacy_baseline_rejects_generated_hidden_column(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "generated-column.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "ALTER TABLE stock_daily ADD COLUMN hidden_probe TEXT "
            "GENERATED ALWAYS AS (code || ':' || date) VIRTUAL"
        )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        generated_column = connection.execute(
            "PRAGMA table_xinfo(stock_daily)"
        ).fetchall()[-1]
    assert registry is None
    assert generated_column[1] == "hidden_probe"
    assert int(generated_column[6]) != 0


def test_legacy_baseline_rejects_generated_replacement_column(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "generated-replacement.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    _recreate_table_with_replacement(
        db_path,
        "analysis_history",
        "analysis_summary TEXT",
        "analysis_summary TEXT GENERATED ALWAYS AS (code) VIRTUAL",
    )

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        generated_column = next(
            row
            for row in connection.execute(
                "PRAGMA table_xinfo(analysis_history)"
            ).fetchall()
            if row[1] == "analysis_summary"
        )
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
    assert int(generated_column[6]) != 0
    assert registry is None


def test_legacy_baseline_rejects_primary_key_without_rowid_alias(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "primary-key-backing-index.sqlite"
    _load_sql_fixture(db_path, "v3_0_0.sql")
    with sqlite3.connect(db_path) as connection:
        create_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'table' AND name = 'analysis_history'"
        ).fetchone()[0]
        malformed_sql = create_sql.replace(
            "id INTEGER NOT NULL",
            "id INTEGER NOT NULL PRIMARY KEY DESC",
            1,
        ).replace(
            ", \n\tPRIMARY KEY (id)",
            "",
            1,
        )
        assert malformed_sql != create_sql
        connection.execute("DROP TABLE analysis_history")
        connection.execute(malformed_sql)

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert DatabaseManager._instance is None
    with sqlite3.connect(db_path) as connection:
        primary_key_indexes = [
            row
            for row in connection.execute(
                "PRAGMA index_list(analysis_history)"
            ).fetchall()
            if row[3] == "pk"
        ]
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
    assert primary_key_indexes
    assert registry is None


def test_historical_database_without_registry_is_not_auto_stamped(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "history-without-registry.sqlite"
    _load_sql_fixture(db_path, "legacy_baseline_no_checksum.sql")
    before = _legacy_fact_snapshot(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE schema_migrations")

    with pytest.raises(MigrationError) as error:
        DatabaseManager(db_url=_database_url(db_path))

    assert error.value.failure_code == "legacy_baseline_untrusted"
    assert _legacy_fact_snapshot(db_path) == before
    with sqlite3.connect(db_path) as connection:
        registry = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
    assert registry is None


def test_known_applied_gap_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "known-gap.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    custom = _custom_migration(1, "known_gap")

    with database._engine.begin() as connection:
        connection.exec_driver_sql(
            "DELETE FROM schema_migrations WHERE version = ?",
            (REGISTRY_METADATA_MIGRATION.id,),
        )
        connection.exec_driver_sql(
            "INSERT INTO schema_migrations "
            "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
            (custom.id, custom.description, "2099-01-01 00:00:00", custom.checksum),
        )

    status = _runner_with(custom).status(database._engine)
    verification = _runner_with(custom).verify(database._engine)

    assert status.success is False
    assert status.failure_code == "migration_order_invalid"
    assert status.failed_migration_id == REGISTRY_METADATA_MIGRATION.id
    assert verification.success is False
    assert verification.failure_code == "migration_order_invalid"


def test_applied_checksum_drift_fails_closed(tmp_path: Path) -> None:
    db_path = tmp_path / "checksum-drift.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    original = _custom_migration(1, "checksum_drift", source="revision=original")

    applied = _runner_with(original).apply_pending(database._engine)
    changed = _custom_migration(1, "checksum_drift", source="revision=changed")
    drift_status = _runner_with(changed).status(database._engine)

    assert applied.success is True
    assert applied.executed_ids == (original.id,)
    assert drift_status.success is False
    assert drift_status.failure_code == "migration_checksum_mismatch"
    assert drift_status.failed_migration_id == original.id
    assert drift_status.checksum_mismatches == (original.id,)


def test_failure_before_ddl_records_nothing(tmp_path: Path) -> None:
    db_path = tmp_path / "failure-before-ddl.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))

    def fail_before_ddl(_execution: MigrationExecution) -> None:
        raise RuntimeError("injected before DDL")

    migration = _custom_migration(1, "failure_before_ddl", upgrade=fail_before_ddl)
    before_ids = _applied_ids(database._engine)
    result = _runner_with(migration).apply_pending(database._engine)

    assert result.success is False
    assert result.failure_code == "migration_upgrade_failed"
    assert result.failed_migration_id == migration.id
    assert _applied_ids(database._engine) == before_ids
    assert migration.id not in _applied_ids(database._engine)


@pytest.mark.parametrize(
    "invalid_kind",
    (
        "coroutine",
        "async-generator",
        "generator",
        "async-contextmanager",
        "contextmanager",
        "non-none",
    ),
)
def test_invalid_upgrade_return_rolls_back_ddl_dml_without_applied_row_or_warning(
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    db_path = tmp_path / f"{invalid_kind}-upgrade.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    table_name = f"migration_{invalid_kind.replace('-', '_')}_upgrade_probe"
    retained_execution: MigrationExecution | None = None

    def return_invalid_result(execution: MigrationExecution):
        nonlocal retained_execution
        retained_execution = execution
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        execution.exec_driver_sql(
            f"INSERT INTO {table_name} (id, value) VALUES (1, 'must-roll-back')"
        )

        async def coroutine_upgrade() -> None:
            return None

        async def async_generator_upgrade():
            yield None

        def generator_upgrade():
            yield None

        if invalid_kind == "coroutine":
            return coroutine_upgrade()
        if invalid_kind == "async-generator":
            return async_generator_upgrade()
        if invalid_kind == "generator":
            return generator_upgrade()
        if invalid_kind == "async-contextmanager":
            return _async_contextmanager_upgrade(execution)
        if invalid_kind == "contextmanager":
            return _contextmanager_upgrade(execution)
        return "unexpected return value"

    migration = _custom_migration(
        1,
        f"{invalid_kind.replace('-', '_')}_upgrade",
        upgrade=return_invalid_result,
    )
    before_ids = _applied_ids(database._engine)

    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always", RuntimeWarning)
        result = _runner_with(migration).apply_pending(database._engine)
        gc.collect()

    assert result.success is False
    assert result.failure_code == "migration_upgrade_invalid_return"
    assert result.failed_migration_id == migration.id
    assert _table_exists(database._engine, table_name) is False
    assert _applied_ids(database._engine) == before_ids
    assert not [
        warning
        for warning in caught_warnings
        if issubclass(warning.category, RuntimeWarning)
    ]
    assert retained_execution is not None
    _assert_execution_capability_revoked(retained_execution, migration.id)


def test_failure_after_real_ddl_and_dml_rolls_back_everything(tmp_path: Path) -> None:
    db_path = tmp_path / "failure-after-dml.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    table_name = "migration_failure_after_dml_probe"
    retained_execution: MigrationExecution | None = None

    def fail_after_dml(execution: MigrationExecution) -> None:
        nonlocal retained_execution
        retained_execution = execution
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        execution.exec_driver_sql(
            f"INSERT INTO {table_name} (id, value) VALUES (1, 'written-before-failure')"
        )
        raise RuntimeError("injected after DDL and DML")

    migration = _custom_migration(1, "failure_after_dml", upgrade=fail_after_dml)
    before_ids = _applied_ids(database._engine)
    result = _runner_with(migration).apply_pending(database._engine)

    assert result.success is False
    assert result.failure_code == "migration_upgrade_failed"
    assert _table_exists(database._engine, table_name) is False
    assert _applied_ids(database._engine) == before_ids
    assert retained_execution is not None
    _assert_execution_capability_revoked(retained_execution, migration.id)


def test_applied_insert_failure_rolls_back_real_ddl_and_dml(tmp_path: Path) -> None:
    db_path = tmp_path / "applied-insert-failure.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    table_name = "migration_applied_insert_failure_probe"

    def upgrade(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        execution.exec_driver_sql(
            f"INSERT INTO {table_name} (id, value) VALUES (1, 'transactional')"
        )

    migration = _custom_migration(1, "applied_insert_failure", upgrade=upgrade)
    before_rows = _applied_rows(database._engine)

    class AppliedInsertFailureRunner(MigrationRunner):
        def _insert_applied(self, connection: Connection, current: Migration) -> None:
            if current.id == migration.id:
                raise RuntimeError("injected applied insert failure")
            super()._insert_applied(connection, current)

    runner = AppliedInsertFailureRunner((*get_migrations(), migration))
    result = runner.apply_pending(database._engine)

    assert result.success is False
    assert result.failure_code == "applied_registry_write_failed"
    assert result.failed_migration_id == migration.id
    assert _table_exists(database._engine, table_name) is False
    assert _applied_rows(database._engine) == before_rows


def test_upgrade_receives_restricted_execution_capability_with_safe_results(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "restricted-execution-capability.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    observed: dict[str, object] = {}
    retained: dict[str, object] = {}

    def inspect_capability(execution: MigrationExecution) -> None:
        retained["execution"] = execution
        driver_result = execution.exec_driver_sql("SELECT 7 AS value")
        retained["driver_result"] = driver_result
        observed["driver_rows"] = driver_result.fetchall()
        mapping_result = execution.execute(
            text("SELECT :value AS value"),
            {"value": 9},
        ).mappings()
        retained["mapping_result"] = mapping_result
        mapping = mapping_result.one_or_none()
        observed["mapping"] = None if mapping is None else dict(mapping)

    migration = _custom_migration(
        1,
        "restricted_execution_capability",
        upgrade=inspect_capability,
    )
    try:
        result = _runner_with(migration).apply_pending(engine)
        observed["forbidden_execution_attributes"] = {
            name: hasattr(retained["execution"], name)
            for name in (
                "begin",
                "close",
                "commit",
                "connection",
                "cursor",
                "driver_connection",
                "engine",
                "executescript",
                "raw_connection",
                "rollback",
                "savepoint",
            )
        }
        observed["forbidden_result_attributes"] = {
            name: hasattr(retained["driver_result"], name)
            for name in (
                "begin",
                "close",
                "commit",
                "connection",
                "context",
                "cursor",
                "driver_connection",
                "engine",
                "executescript",
                "raw_connection",
                "rollback",
                "savepoint",
            )
        }
        observed["forbidden_mapping_result_attributes"] = {
            name: hasattr(retained["mapping_result"], name)
            for name in (
                "begin",
                "close",
                "commit",
                "connection",
                "context",
                "cursor",
                "driver_connection",
                "engine",
                "executescript",
                "raw_connection",
                "rollback",
                "savepoint",
            )
        }
    finally:
        engine.dispose()

    assert result.success is True
    assert observed == {
        "driver_rows": [(7,)],
        "forbidden_execution_attributes": {
            "begin": False,
            "close": False,
            "commit": False,
            "connection": False,
            "cursor": False,
            "driver_connection": False,
            "engine": False,
            "executescript": False,
            "raw_connection": False,
            "rollback": False,
            "savepoint": False,
        },
        "forbidden_result_attributes": {
            "begin": False,
            "close": False,
            "commit": False,
            "connection": False,
            "context": False,
            "cursor": False,
            "driver_connection": False,
            "engine": False,
            "executescript": False,
            "raw_connection": False,
            "rollback": False,
            "savepoint": False,
        },
        "forbidden_mapping_result_attributes": {
            "begin": False,
            "close": False,
            "commit": False,
            "connection": False,
            "context": False,
            "cursor": False,
            "driver_connection": False,
            "engine": False,
            "executescript": False,
            "raw_connection": False,
            "rollback": False,
            "savepoint": False,
        },
        "mapping": {"value": 9},
    }


@pytest.mark.parametrize(
    "caught_request",
    ("helper_commit", "result_cursor", "sql_commit"),
)
def test_caught_capability_violation_still_rolls_back_migration(
    tmp_path: Path,
    caught_request: str,
) -> None:
    db_path = tmp_path / f"caught-capability-violation-{caught_request}.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    table_name = "migration_caught_capability_violation_probe"

    def catch_forbidden_request(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"
        )
        try:
            if caught_request == "helper_commit":
                _request_transaction_control(execution, "commit")
            elif caught_request == "result_cursor":
                getattr(execution.exec_driver_sql("SELECT 1"), "cursor")
            else:
                execution.exec_driver_sql("COMMIT")
        except AttributeError:
            pass

    migration = _custom_migration(
        1,
        f"caught_capability_violation_{caught_request}",
        upgrade=catch_forbidden_request,
    )
    try:
        result = _runner_with(migration).apply_pending(engine)

        assert result.success is False
        assert result.failure_code == "migration_transaction_control_forbidden"
        assert result.failed_migration_id == migration.id
        assert _table_exists(engine, table_name) is False
        assert migration.id not in _applied_ids(engine)
    finally:
        engine.dispose()


def test_custom_sqlalchemy_executable_cannot_receive_connection_or_commit_ddl(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "custom-executable-callback.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    table_name = "migration_custom_executable_probe"
    callback_calls: list[str] = []

    class ConnectionCapturingStatement:
        def _execute_on_connection(
            self,
            connection: Connection,
            _distilled_parameters,
            _execution_options,
        ):
            callback_calls.append("called")
            dbapi_connection = connection.connection.driver_connection
            dbapi_connection.set_authorizer(None)
            dbapi_connection.commit()
            return connection.exec_driver_sql("SELECT 1")

    def attempt_callback_escape(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"
        )
        execution.execute(ConnectionCapturingStatement())  # type: ignore[arg-type]

    migration = _custom_migration(
        1,
        "custom_executable_callback",
        upgrade=attempt_callback_escape,
    )
    try:
        result = _runner_with(migration).apply_pending(engine)

        assert result.success is False
        assert result.failure_code == "migration_transaction_control_forbidden"
        assert result.failed_migration_id == migration.id
        assert callback_calls == []
        assert _table_exists(engine, table_name) is False
        assert migration.id not in _applied_ids(engine)
    finally:
        engine.dispose()


def test_exec_driver_sql_rejects_custom_string_subclass_and_rolls_back(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "custom-driver-sql-string.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    table_name = "migration_custom_driver_sql_string_probe"

    class CustomSqlString(str):
        pass

    def attempt_custom_string(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"
        )
        execution.exec_driver_sql(CustomSqlString("SELECT 1"))

    migration = _custom_migration(
        1,
        "custom_driver_sql_string",
        upgrade=attempt_custom_string,
    )
    try:
        result = _runner_with(migration).apply_pending(engine)

        assert result.success is False
        assert result.failure_code == "migration_transaction_control_forbidden"
        assert result.failed_migration_id == migration.id
        assert _table_exists(engine, table_name) is False
        assert migration.id not in _applied_ids(engine)
    finally:
        engine.dispose()


def test_mutated_text_clause_callback_cannot_receive_connection_or_commit_ddl(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "mutated-text-clause-callback.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    table_name = "migration_mutated_text_clause_probe"
    callback_calls: list[str] = []

    def attempt_callback_escape(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"
        )
        statement = text("SELECT 1")

        def capture_connection(
            connection: Connection,
            _distilled_parameters,
            _execution_options,
        ):
            callback_calls.append("called")
            dbapi_connection = connection.connection.driver_connection
            dbapi_connection.set_authorizer(None)
            dbapi_connection.commit()
            return connection.exec_driver_sql("SELECT 1")

        statement._execute_on_connection = capture_connection  # type: ignore[method-assign]
        execution.execute(statement)

    migration = _custom_migration(
        1,
        "mutated_text_clause_callback",
        upgrade=attempt_callback_escape,
    )
    try:
        result = _runner_with(migration).apply_pending(engine)

        assert result.success is True
        assert callback_calls == []
        assert _table_exists(engine, table_name) is True
        assert migration.id in _applied_ids(engine)
    finally:
        engine.dispose()


def test_retained_execution_capability_is_revoked_for_caller_owned_connection(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "retained-execution-capability.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    retained: dict[str, MigrationExecution] = {}

    def retain_capability(execution: MigrationExecution) -> None:
        retained["execution"] = execution

    migration = _custom_migration(
        1,
        "retained_execution_capability",
        upgrade=retain_capability,
    )
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE migration_retained_dml_probe "
                "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.commit()

            result = _runner_with(migration).apply_pending(connection)

            assert result.success is True
            assert connection.closed is False
            retained_execution = retained["execution"]
            with pytest.raises(MigrationError) as execute_error:
                retained_execution.execute(
                    text(
                        "INSERT INTO migration_retained_dml_probe (id, value) "
                        "VALUES (:id, :value)"
                    ),
                    {"id": 1, "value": "must-not-persist"},
                )
            with pytest.raises(MigrationError) as driver_error:
                retained_execution.exec_driver_sql(
                    "CREATE TABLE migration_retained_ddl_probe "
                    "(id INTEGER PRIMARY KEY)"
                )

            for error in (execute_error.value, driver_error.value):
                assert error.failure_code == "migration_transaction_control_forbidden"
                assert error.migration_id == migration.id
            row_count = connection.exec_driver_sql(
                "SELECT COUNT(*) FROM migration_retained_dml_probe"
            ).scalar_one()
            escaped_table = connection.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("migration_retained_ddl_probe",),
            ).scalar_one_or_none()

        assert row_count == 0
        assert escaped_table is None
    finally:
        engine.dispose()


def test_caller_owned_sqlite_authorizer_remains_installed_after_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "caller-owned-authorizer.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    migration = _custom_migration(1, "preserve_caller_authorizer")

    def preserve_user_version_policy(
        action_code,
        argument,
        _second_argument,
        _database,
        _trigger,
    ) -> int:
        if (
            action_code == sqlite3.SQLITE_PRAGMA
            and str(argument or "").lower() == "user_version"
        ):
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    try:
        with engine.connect() as connection:
            dbapi_connection = connection.connection.driver_connection
            dbapi_connection.set_authorizer(preserve_user_version_policy)
            try:
                result = _runner_with(migration).apply_pending(connection)

                assert result.success is True
                assert migration.id in _applied_ids(engine)
                with pytest.raises(sqlite3.DatabaseError):
                    dbapi_connection.execute("PRAGMA user_version").fetchall()
            finally:
                dbapi_connection.set_authorizer(None)
    finally:
        engine.dispose()


def test_in_flight_execution_finishes_before_capability_is_revoked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "in-flight-execution-capability.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    table_name = "migration_in_flight_execution_probe"
    probe_sql = f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"
    statement_entered = threading.Event()
    allow_statement = threading.Event()
    revoke_started = threading.Event()
    revoke_finished = threading.Event()
    apply_finished = threading.Event()
    worker_threads: list[threading.Thread] = []
    worker_errors: list[BaseException] = []
    late_errors: list[BaseException] = []
    apply_results = []
    apply_errors: list[BaseException] = []
    retained: dict[str, MigrationExecution] = {}

    original_exec_driver_sql = Connection.exec_driver_sql

    def blocking_exec_driver_sql(
        connection: Connection,
        statement: str,
        parameters=None,
        execution_options=None,
    ):
        if statement == probe_sql:
            statement_entered.set()
            if not allow_statement.wait(timeout=5):
                raise RuntimeError("Timed out waiting to release migration statement")
        return original_exec_driver_sql(
            connection,
            statement,
            parameters,
            execution_options=execution_options,
        )

    original_revoke = migration_runner_module._MigrationExecutionLease.revoke

    def observed_revoke(lease):
        revoke_started.set()
        try:
            return original_revoke(lease)
        finally:
            revoke_finished.set()

    monkeypatch.setattr(Connection, "exec_driver_sql", blocking_exec_driver_sql)
    monkeypatch.setattr(
        migration_runner_module._MigrationExecutionLease,
        "revoke",
        observed_revoke,
    )

    def start_in_flight_statement(execution: MigrationExecution) -> None:
        retained["execution"] = execution

        def execute_statement() -> None:
            try:
                execution.exec_driver_sql(probe_sql)
            except BaseException as exc:
                worker_errors.append(exc)

        worker = threading.Thread(target=execute_statement)
        worker_threads.append(worker)
        worker.start()
        if not statement_entered.wait(timeout=5):
            raise RuntimeError("Migration statement did not start")

    migration = _custom_migration(
        1,
        "in_flight_execution_capability",
        upgrade=start_in_flight_statement,
    )
    runner = _runner_with(migration)

    try:
        with engine.connect() as connection:
            def apply_migration() -> None:
                try:
                    apply_results.append(runner.apply_pending(connection))
                except BaseException as exc:
                    apply_errors.append(exc)
                finally:
                    apply_finished.set()

            apply_thread = threading.Thread(target=apply_migration)
            apply_thread.start()

            assert statement_entered.wait(timeout=5)
            assert revoke_started.wait(timeout=5)
            lease = getattr(
                retained["execution"],
                "_MigrationExecutionFacade__lease",
            )
            revoked = getattr(lease, "_MigrationExecutionLease__revoked")
            assert revoked.wait(timeout=5)
            assert revoke_finished.wait(timeout=0.2) is False
            assert apply_finished.is_set() is False

            late_table_name = "migration_late_execution_probe"

            def execute_after_revoke() -> None:
                try:
                    retained["execution"].exec_driver_sql(
                        f"CREATE TABLE {late_table_name} (id INTEGER PRIMARY KEY)"
                    )
                except BaseException as exc:
                    late_errors.append(exc)

            late_thread = threading.Thread(target=execute_after_revoke)
            late_thread.start()

            allow_statement.set()
            apply_thread.join(timeout=5)
            late_thread.join(timeout=5)
            for worker in worker_threads:
                worker.join(timeout=5)

            assert apply_thread.is_alive() is False
            assert late_thread.is_alive() is False
            assert all(worker.is_alive() is False for worker in worker_threads)
            assert revoke_finished.is_set() is True
            assert apply_errors == []
            assert worker_errors == []
            assert len(late_errors) == 1
            assert isinstance(late_errors[0], MigrationError)
            assert late_errors[0].failure_code == "migration_transaction_control_forbidden"
            assert late_errors[0].migration_id == migration.id
            assert len(apply_results) == 1
            assert apply_results[0].success is True
            assert _table_exists(engine, table_name) is True
            assert _table_exists(engine, late_table_name) is False
            assert migration.id in _applied_ids(engine)
    finally:
        allow_statement.set()
        engine.dispose()


def test_in_flight_statement_failure_rolls_back_without_applied_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "in-flight-statement-failure.sqlite"
    engine = _engine_with_applied_production_registry(db_path)
    table_name = "migration_in_flight_failure_probe"
    failing_sql = "SELECT migration_in_flight_failure()"
    statement_entered = threading.Event()
    allow_failure = threading.Event()
    retained: dict[str, object] = {}
    worker_errors: list[BaseException] = []
    apply_results = []

    original_exec_driver_sql = Connection.exec_driver_sql

    def failing_exec_driver_sql(
        connection: Connection,
        statement: str,
        parameters=None,
        execution_options=None,
    ):
        if statement == failing_sql:
            statement_entered.set()
            if not allow_failure.wait(timeout=5):
                raise RuntimeError("Timed out waiting to release failing statement")
            raise sqlite3.OperationalError("injected migration statement failure")
        return original_exec_driver_sql(
            connection,
            statement,
            parameters,
            execution_options=execution_options,
        )

    monkeypatch.setattr(Connection, "exec_driver_sql", failing_exec_driver_sql)

    def start_failing_statement(execution: MigrationExecution) -> None:
        retained["execution"] = execution
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)"
        )

        def execute_statement() -> None:
            try:
                execution.exec_driver_sql(failing_sql)
            except BaseException as exc:
                worker_errors.append(exc)

        worker = threading.Thread(target=execute_statement)
        retained["worker"] = worker
        worker.start()
        if not statement_entered.wait(timeout=5):
            raise RuntimeError("Failing migration statement did not start")

    migration = _custom_migration(
        1,
        "in_flight_statement_failure",
        upgrade=start_failing_statement,
    )
    runner = _runner_with(migration)

    try:
        with engine.connect() as connection:
            apply_thread = threading.Thread(
                target=lambda: apply_results.append(runner.apply_pending(connection))
            )
            apply_thread.start()

            assert statement_entered.wait(timeout=5)
            lease = getattr(
                retained["execution"],
                "_MigrationExecutionFacade__lease",
            )
            revoked = getattr(lease, "_MigrationExecutionLease__revoked")
            assert revoked.wait(timeout=5)

            allow_failure.set()
            apply_thread.join(timeout=5)
            worker = retained["worker"]
            assert isinstance(worker, threading.Thread)
            worker.join(timeout=5)

            assert apply_thread.is_alive() is False
            assert worker.is_alive() is False
            assert len(worker_errors) == 1
            assert isinstance(worker_errors[0], sqlite3.OperationalError)
            assert len(apply_results) == 1
            result = apply_results[0]
            assert result.success is False
            assert result.failure_code == "migration_upgrade_failed"
            assert result.failed_migration_id == migration.id
            assert _table_exists(engine, table_name) is False
            assert migration.id not in _applied_ids(engine)
    finally:
        allow_failure.set()
        engine.dispose()


@pytest.mark.parametrize(
    "transaction_control",
    (
        "begin",
        "commit",
        "rollback",
        "savepoint",
        "helper_begin",
        "helper_commit",
        "helper_rollback",
        "helper_savepoint",
        "sql_begin",
        "sql_bom_commit",
        "sql_commit",
        "sql_end",
        "sql_rollback",
        "sql_savepoint",
        "sql_release",
        "sql_commented_commit",
        "sql_commented_rollback",
        "sql_semicolon_commit",
        "executescript",
        "result_cursor",
        "raw_commit",
        "raw_rollback",
        "raw_cursor_commit",
    ),
)
def test_upgrade_cannot_control_runner_transaction(
    tmp_path: Path,
    transaction_control: str,
) -> None:
    db_path = tmp_path / f"forbidden-{transaction_control}.sqlite"
    engine = _engine_with_applied_production_registry(db_path)

    def control_transaction(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            "CREATE TABLE migration_transaction_control_probe "
            "(id INTEGER PRIMARY KEY)"
        )
        sql_controls = {
            "sql_begin": "BEGIN",
            "sql_bom_commit": " \ufeffCOMMIT",
            "sql_commit": "COMMIT",
            "sql_end": "END",
            "sql_rollback": "ROLLBACK",
            "sql_savepoint": "SAVEPOINT migration_forbidden_savepoint",
            "sql_release": "RELEASE SAVEPOINT migration_forbidden_savepoint",
            "sql_commented_commit": "/* helper */ COMMIT",
            "sql_commented_rollback": "-- helper\nROLLBACK",
            "sql_semicolon_commit": ";COMMIT",
        }
        if transaction_control in sql_controls:
            execution.exec_driver_sql(sql_controls[transaction_control])
        elif transaction_control.startswith("helper_"):
            _request_transaction_control(
                execution,
                transaction_control.removeprefix("helper_"),
            )
        elif transaction_control == "executescript":
            getattr(execution, "executescript")("COMMIT")
        elif transaction_control == "result_cursor":
            getattr(execution.exec_driver_sql("SELECT 1"), "cursor")
        elif transaction_control == "raw_cursor_commit":
            cursor = _request_raw_dbapi_connection(execution).cursor()
            try:
                cursor.execute("/* helper */ COMMIT")
            finally:
                cursor.close()
        elif transaction_control.startswith("raw_"):
            getattr(
                _request_raw_dbapi_connection(execution),
                transaction_control.removeprefix("raw_"),
            )()
        else:
            getattr(execution, transaction_control)()

    migration = _custom_migration(
        1,
        f"forbidden_{transaction_control}",
        upgrade=control_transaction,
    )
    try:
        result = _runner_with(migration).apply_pending(engine)

        assert result.success is False
        assert result.failure_code == "migration_transaction_control_forbidden"
        assert result.failed_migration_id == migration.id
        assert migration.id not in _applied_ids(engine)
        assert _table_exists(engine, "migration_transaction_control_probe") is False
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "open_replacement_transaction",
    [False, True],
    ids=["direct-commit", "replacement-transaction"],
)
def test_restricted_capability_blocks_authorizer_clear_and_commit_atomically(
    tmp_path: Path,
    open_replacement_transaction: bool,
) -> None:
    db_path = tmp_path / "forbidden-authorizer-clear-commit.sqlite"
    engine = _engine_with_applied_production_registry(db_path)

    def bypass_transaction_guard(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            "CREATE TABLE migration_authorizer_bypass_probe "
            "(id INTEGER PRIMARY KEY)"
        )
        dbapi_connection = _request_raw_dbapi_connection(execution)
        dbapi_connection.set_authorizer(None)
        dbapi_connection.commit()
        if open_replacement_transaction:
            dbapi_connection.execute("BEGIN IMMEDIATE")
            execution.exec_driver_sql(
                "CREATE TABLE migration_replacement_transaction_probe "
                "(id INTEGER PRIMARY KEY)"
            )

    migration = _custom_migration(
        1,
        "forbidden_authorizer_clear_commit",
        upgrade=bypass_transaction_guard,
    )
    try:
        result = _runner_with(migration).apply_pending(engine)

        assert result.success is False
        assert result.failure_code == "migration_transaction_control_forbidden"
        assert result.failed_migration_id == migration.id
        assert migration.id not in _applied_ids(engine)
        assert _table_exists(engine, "migration_authorizer_bypass_probe") is False
        assert _table_exists(engine, "migration_replacement_transaction_probe") is False
    finally:
        engine.dispose()


def test_failed_migration_can_be_fixed_and_retried_forward(tmp_path: Path) -> None:
    db_path = tmp_path / "forward-retry.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    table_name = "migration_forward_retry_probe"

    def broken_upgrade(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        execution.exec_driver_sql(
            f"INSERT INTO {table_name} (id, value) VALUES (1, 'rolled-back')"
        )
        raise RuntimeError("injected migration defect")

    broken = _custom_migration(
        1,
        "forward_retry",
        upgrade=broken_upgrade,
        source="revision=broken",
    )
    failed = _runner_with(broken).apply_pending(database._engine)
    assert failed.success is False
    assert broken.id not in _applied_ids(database._engine)
    assert _table_exists(database._engine, table_name) is False

    def fixed_upgrade(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        execution.exec_driver_sql(
            f"INSERT INTO {table_name} (id, value) VALUES (1, 'recovered')"
        )

    fixed = _custom_migration(
        1,
        "forward_retry",
        upgrade=fixed_upgrade,
        source="revision=fixed",
    )
    recovered = _runner_with(fixed).apply_pending(database._engine)

    assert recovered.success is True
    assert recovered.executed_ids == (fixed.id,)
    with database._engine.connect() as connection:
        values = connection.exec_driver_sql(
            f"SELECT id, value FROM {table_name} ORDER BY id"
        ).fetchall()
    assert values == [(1, "recovered")]
    assert _runner_with(fixed).verify(database._engine).success is True


def test_later_migration_does_not_run_after_prior_failure(tmp_path: Path) -> None:
    db_path = tmp_path / "later-not-run.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    later_calls: list[str] = []

    def first_upgrade(execution: MigrationExecution) -> None:
        execution.exec_driver_sql(
            "CREATE TABLE migration_first_failure_probe (id INTEGER PRIMARY KEY)"
        )
        raise RuntimeError("first migration failed")

    def later_upgrade(execution: MigrationExecution) -> None:
        later_calls.append("called")
        execution.exec_driver_sql(
            "CREATE TABLE migration_later_probe (id INTEGER PRIMARY KEY)"
        )

    first = _custom_migration(1, "first_failure", upgrade=first_upgrade)
    later = _custom_migration(2, "later_migration", upgrade=later_upgrade)
    result = _runner_with(first, later).apply_pending(database._engine)

    assert result.success is False
    assert result.failed_migration_id == first.id
    assert later_calls == []
    assert _table_exists(database._engine, "migration_first_failure_probe") is False
    assert _table_exists(database._engine, "migration_later_probe") is False
    assert first.id not in _applied_ids(database._engine)
    assert later.id not in _applied_ids(database._engine)


def test_two_independent_engines_execute_pending_migration_once(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent.sqlite"
    url = _database_url(db_path)
    DatabaseManager(db_url=url)
    DatabaseManager.reset_instance()
    Config.reset_instance()

    calls: list[str] = []
    call_lock = threading.Lock()

    def upgrade(execution: MigrationExecution) -> None:
        with call_lock:
            calls.append("called")
        execution.exec_driver_sql(
            "CREATE TABLE migration_concurrency_probe "
            "(id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        execution.exec_driver_sql(
            "INSERT INTO migration_concurrency_probe (id, value) VALUES (1, 'once')"
        )
        time.sleep(0.15)

    migration = _custom_migration(1, "concurrency_once", upgrade=upgrade)
    registry = (*get_migrations(), migration)
    engines = (
        create_engine(url, connect_args={"timeout": 2.0}, poolclass=NullPool),
        create_engine(url, connect_args={"timeout": 2.0}, poolclass=NullPool),
    )
    barrier = threading.Barrier(2)

    def apply(engine: Engine):
        barrier.wait(timeout=5)
        return MigrationRunner(registry).apply_pending(engine)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(apply, engines))
    finally:
        for engine in engines:
            engine.dispose()

    assert all(result.success for result in results)
    assert calls == ["called"]
    assert sorted(len(result.executed_ids) for result in results) == [0, 1]
    with sqlite3.connect(db_path) as connection:
        values = connection.execute(
            "SELECT id, value FROM migration_concurrency_probe ORDER BY id"
        ).fetchall()
        applied_count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
            (migration.id,),
        ).fetchone()[0]
    assert values == [(1, "once")]
    assert applied_count == 1


def test_locked_recheck_unknown_migration_preserves_failure_state(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "locked-recheck-unknown.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    pending = _custom_migration(1, "locked_recheck")
    unknown_id = "999912312359_locked_recheck_unknown"

    class InjectUnknownRunner(MigrationRunner):
        def _apply_one(self, bind, migration):
            with bind.begin() as connection:
                connection.exec_driver_sql(
                    "INSERT INTO schema_migrations "
                    "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
                    (
                        unknown_id,
                        "Concurrent future migration",
                        "2099-12-31 23:59:00",
                        "f" * 64,
                    ),
                )
            return super()._apply_one(bind, migration)

    runner = InjectUnknownRunner((*get_migrations(), pending))
    result = runner.apply_pending(database._engine)

    assert result.success is False
    assert result.failure_code == "unknown_migration"
    assert result.failed_migration_id == unknown_id
    assert result.current_version == unknown_id
    assert result.unknown_ids == (unknown_id,)
    assert result.pending_ids == (pending.id,)
    assert pending.id not in _applied_ids(database._engine)


def test_two_processes_can_initialize_the_same_fresh_database(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "concurrent-fresh-initialization.sqlite"
    database_url = _database_url(db_path)
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    result_queue = context.Queue()
    processes = [
        context.Process(
            target=_initialize_database_process,
            args=(database_url, barrier, result_queue),
        )
        for _ in range(2)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)

    try:
        assert all(not process.is_alive() for process in processes)
        assert all(process.exitcode == 0 for process in processes)
        results = [result_queue.get(timeout=5) for _ in processes]
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        result_queue.close()

    expected_ids = tuple(migration.id for migration in get_migrations())
    assert results == [("ok", expected_ids), ("ok", expected_ids)]
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT version, COUNT(*) FROM schema_migrations "
            "GROUP BY version ORDER BY version"
        ).fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    assert rows == [(migration_id, 1) for migration_id in expected_ids]
    assert integrity == "ok"


def test_held_write_lock_returns_database_locked_without_registry_damage(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "held-lock.sqlite"
    url = _database_url(db_path)
    database = DatabaseManager(db_url=url)
    before_rows = _applied_rows(database._engine)
    DatabaseManager.reset_instance()
    Config.reset_instance()

    migration = _custom_migration(
        1,
        "held_lock",
        upgrade=lambda execution: execution.exec_driver_sql(
            "CREATE TABLE migration_held_lock_probe (id INTEGER PRIMARY KEY)"
        ),
    )
    engine = create_engine(url, connect_args={"timeout": 0.05}, poolclass=NullPool)
    holder = sqlite3.connect(db_path, timeout=1.0, isolation_level=None)
    try:
        holder.execute("PRAGMA busy_timeout=1000")
        holder.execute("BEGIN IMMEDIATE")
        result = _runner_with(migration).apply_pending(engine)
    finally:
        holder.rollback()
        holder.close()

    try:
        assert result.success is False
        assert result.failure_code == "database_locked"
        assert result.failed_migration_id == migration.id
        assert _applied_rows(engine) == before_rows
        assert _table_exists(engine, "migration_held_lock_probe") is False
        pending = _runner_with(migration).status(engine)
        assert pending.success is True
        assert pending.pending_ids == (migration.id,)
    finally:
        engine.dispose()


def test_non_sqlite_backend_is_explicitly_unsupported() -> None:
    engine = create_engine("sqlite:///:memory:")
    original_name = engine.dialect.name
    engine.dialect.name = "postgresql"
    try:
        status = MigrationRunner().status(engine)
        verification = MigrationRunner().verify(engine)
        result = MigrationRunner().apply_pending(engine)
    finally:
        engine.dialect.name = original_name
        engine.dispose()

    assert status.success is False
    assert status.failure_code == "unsupported_backend"
    assert verification.success is False
    assert verification.failure_code == "unsupported_backend"
    assert result.success is False
    assert result.failure_code == "unsupported_backend"


def test_status_verify_and_apply_return_complete_structured_state(tmp_path: Path) -> None:
    db_path = tmp_path / "structured-state.sqlite"
    database = DatabaseManager(db_url=_database_url(db_path))
    migration = _custom_migration(1, "structured_state")
    runner = _runner_with(migration)

    status = runner.status(database._engine)
    verification_before = runner.verify(database._engine)
    applied = runner.apply_pending(database._engine)
    verification_after = runner.verify(database._engine)

    assert set(status.to_dict()) == STATUS_KEYS
    assert status.success is True
    assert status.current_version == TARGET_VERSION
    assert status.target_version == migration.id
    assert status.pending_ids == (migration.id,)
    assert verification_before.success is False
    assert verification_before.failure_code == "pending_migrations"
    assert verification_before.failed_migration_id == migration.id
    assert set(applied.to_dict()) == STATUS_KEYS | {"executed_ids"}
    assert applied.success is True
    assert applied.executed_ids == (migration.id,)
    assert verification_after.success is True
    assert verification_after.current_version == migration.id
    assert verification_after.pending_ids == ()


def test_cli_preserves_unknown_migration_state_and_failure_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "cli-unknown.sqlite"
    unknown_id = "999912312359_cli_unknown"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version VARCHAR(64) NOT NULL PRIMARY KEY, "
            "description VARCHAR(255) NOT NULL, "
            "applied_at DATETIME NOT NULL, checksum VARCHAR(64))"
        )
        connection.execute(
            "INSERT INTO schema_migrations "
            "(version, description, applied_at, checksum) VALUES (?, ?, ?, ?)",
            (unknown_id, "Unknown CLI migration", "2099-01-01", "f" * 64),
        )
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()

    exit_code = migration_cli_main(["status"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["failure_code"] == "unknown_migration"
    assert payload["failed_migration_id"] == unknown_id
    assert payload["current_version"] == unknown_id
    assert payload["unknown_ids"] == [unknown_id]


def test_cli_preserves_checksum_mismatch_state_and_failure_exit_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "cli-checksum.sqlite"
    DatabaseManager(db_url=_database_url(db_path))
    DatabaseManager.reset_instance()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = ?",
            ("0" * 64, REGISTRY_METADATA_MIGRATION.id),
        )
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()

    exit_code = migration_cli_main(["verify"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["success"] is False
    assert payload["failure_code"] == "migration_checksum_mismatch"
    assert payload["failed_migration_id"] == REGISTRY_METADATA_MIGRATION.id
    assert payload["checksum_mismatches"] == [REGISTRY_METADATA_MIGRATION.id]
