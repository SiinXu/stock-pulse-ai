# Database Migrations

[Chinese](database-migrations.md) | [English](database-migrations_EN.md)

StockPulse uses an in-repository Python Migration Runner to manage SQLite schema evolution. The first phase does not introduce Alembic and does not replace the existing `Base.metadata.create_all()` or startup `_ensure_*` compatibility logic.

The current production registry target is `202607160001_migration_runner_registry`. This migration establishes additive metadata required by the ordered registry. It does not migrate Portfolio or other business fields.

## Core Contract

Each migration has these stable properties:

| Property | Contract |
| --- | --- |
| `id` | Globally unique, strictly increasing, and immutable after release |
| `description` | Stable English diagnostic text |
| `checksum` | Deterministic SHA-256 of the complete normalized migration module source |
| `upgrade` | Synchronous upgrade function accepting a SQLAlchemy `Connection` |

`src.migrations.registry` is the only source of truth for execution order. The runner does not use filesystem traversal order and does not infer upgrade functions from filenames. Repeated imports must produce the same IDs, order, and checksums.

Production migrations use `Migration.from_source_file()` so the checksum covers the complete module containing the real `upgrade`, helper functions, and constants. Normalization changes only CRLF/CR physical line endings to LF; every other character, including semantic whitespace inside strings and the final file newline, remains covered. Absolute paths never enter the hash. A released migration must never be edited, reordered, or deleted. Add a migration with a higher ID whenever schema or data behavior must change. Editing an applied migration causes checksum verification to fail and the application to fail closed.

## Applied Registry

`schema_migrations` preserves the historical `version`, `description`, and `applied_at` semantics and persists checksums through an additive change.

- A known legacy baseline can receive a deterministic checksum or legacy marker.
- An unknown historical row is never silently rewritten or stamped as trusted.
- Registry `version` must be the unique primary key, and `version`, `description`, and `applied_at` remain `NOT NULL`. A malformed registry or duplicate applied ID fails closed instead of being collapsed during reads.
- An applied row is inserted only after that migration's schema and data changes fully succeed.
- Applied rows are never updated, deleted, or overwritten. The sole exception is the registry metadata bootstrap, which fills a legacy baseline's `NULL` checksum once after proving its ID, description, and prior checksum state.
- If the database contains a higher migration unknown to the current registry, the older application stops before writing to the newer schema.

## DatabaseManager Initialization Order

`DatabaseManager` remains the only business-runtime engine, Session, and database configuration entry point. API, Bot, Desktop, Docker, and Actions use the same migration package and initialization sequence when they first enter `DatabaseManager`:

```text
create engine / install SQLite PRAGMAs / create Session factory
  -> BEGIN IMMEDIATE and preflight any existing registry
  -> Base.metadata.create_all()
  -> existing _ensure_* compatibility and repair steps
  -> prove and stamp a fresh/known legacy baseline
  -> commit the serialized compatibility transaction
  -> bootstrap or upgrade schema_migrations metadata
  -> verify applied registry and checksums
  -> apply pending migrations in registry order
  -> mark DatabaseManager initialized
```

Migrations finish synchronously inside `DatabaseManager` initialization and never continue as a background task. SQLite also serializes the `create_all + _ensure_* + baseline` compatibility phase under one database-level write lock and transaction, preventing two fresh processes from racing before they enter the runner. The first backend path that needs `DatabaseManager` returns only after migration finishes. If any step fails, `DatabaseManager` remains uninitialized, the current transaction rolls back, and no applied row is recorded.

The general `/api/health` endpoint is not currently a database readiness probe, so a health response does not promise eager database initialization. This lazy boundary does not create a background migration: the first call that actually enters `DatabaseManager` still waits for the runner to succeed or fail completely.

## Transactions, Locking, and Concurrency

- SQLite initialization first uses `BEGIN IMMEDIATE` to serialize `create_all + _ensure_* + baseline`. Each formal migration then obtains its own database-level write lock and reuses the application's existing busy timeout contract.
- Each migration commits independently. Its DDL or DML and applied row share one transaction.
- The runner exclusively owns transaction control. An `upgrade` must not call `begin`, `commit`, `rollback`, or `close`, or access the underlying DBAPI transaction. Public SQLAlchemy controls are blocked, and a SQLite authorizer rejects transaction or savepoint opcodes issued through explicit SQL or the underlying DBAPI before the migration is rolled back.
- Later migrations do not run after the first failure.
- When two processes start together, the second process waits for the write lock and then reloads the applied registry. The same upgrade does not run twice.
- A busy timeout returns a stable migration error. An in-process `threading.Lock` is not used as a substitute for cross-process locking.

Errors contain only a stable category and failed migration ID. They do not log a complete `db_url`, absolute path, SQL parameters, or sensitive data.

## Fresh and Historical Databases

### Fresh Database

A database is recognized as fresh only when inspection under the initialization lock finds no user tables before `create_all()`. SQLAlchemy metadata then creates the current table layout, and the runner bootstraps the applied registry and records the baseline. Even when `create_all()` already created a target column, the corresponding migration must follow its contract and receive an applied record. A second startup verifies the registry without running the upgrade again.

### Historical Database

A historical database validates any existing registry under the initialization lock, runs the existing `_ensure_*` compatibility steps, and then enters the ordered runner. The explicitly supported release boundaries are:

- `v3.0.0`, `v3.4.0`, and `v3.20.0`: without a registry, the database must match the corresponding fixed release profile.
- `v3.21.0` and `v3.26.3`: the database must carry the known legacy baseline row; the checksum column may not exist yet.

Each pre-baseline profile records a fixed source tag and commit and fully validates that release's required tables, ordered columns, SQLite type affinity, primary keys, `NOT NULL`, defaults, unique keys and collations, foreign keys, and `WITHOUT ROWID` / `STRICT` options. Partial or expression unique indexes, explicit `ON CONFLICT` policies, and known later-release tables are also part of the fail-closed boundary. Profiles are checked newest first, so an incomplete newer database cannot fall back to an older profile. Compatibility repair must then prove the complete current ORM baseline and pass `PRAGMA foreign_key_check` before a baseline row is written. A partial lookalike, missing constraint, wrong affinity, incomplete profile, or unrelated SQLite database fails closed and rolls back the complete compatibility transaction. Extra custom tables provide no profile evidence and cannot replace required tables. An unrecognized old database is never treated as fresh or stamped automatically; stop writers, make a complete backup, and have a maintainer establish its source version and an explicit migration path.

The upgrade does not remove existing business tables, fields, or data. This phase deliberately retains `create_all + _ensure_*` as compatibility debt. Converting an existing ensure step into a formal migration requires a separate implementation slice.

## Status and Verification CLI

The CLI wraps the same runner and does not copy version decisions:

```bash
python -m src.migrations.cli status
python -m src.migrations.cli verify
```

The runner's `status` result can represent structured current and target versions plus applied, pending, unknown, and checksum mismatch state. `verify` uses the same registry to check ordering, unknown versions, and checksum drift.

Both commands use the same `get_config().get_db_url()` configuration source and the minimal engine builder shared with startup, but they do not create or register the business `DatabaseManager` singleton. SQLite is opened with URI `mode=ro`, and every connection enforces `PRAGMA query_only=ON`. Neither command calls `create_all`, `_ensure_*`, or `apply_pending`, and neither modifies schema, business data, registry rows, journal mode, or `user_version`.

| State | `status` | `verify` |
| --- | --- | --- |
| Fully applied | exit 0 with current state | exit 0 |
| Pending migration | exit 0 with the real pending list | nonzero with `pending_migrations` |
| Unknown / checksum mismatch / malformed registry | nonzero structured failure | nonzero structured failure |
| Missing database | nonzero `database_not_found`; no file or parent is created | same |
| Non-SQLite backend | nonzero `unsupported_backend`; no business connection is opened | same |

The CLI diagnoses only. The application still applies pending migrations synchronously when it first enters `DatabaseManager`. Output excludes complete database paths, URLs, SQL, parameters, and raw exceptions.

Development and CI smoke checks must point to an isolated temporary database:

```bash
tmp_dir="$(mktemp -d)"
DATABASE_PATH="$tmp_dir/stockpulse-migration-smoke.sqlite" python -c \
  'from src.storage import DatabaseManager; DatabaseManager.get_instance(); DatabaseManager.reset_instance()'
DATABASE_PATH="$tmp_dir/stockpulse-migration-smoke.sqlite" python -m src.migrations.cli status
DATABASE_PATH="$tmp_dir/stockpulse-migration-smoke.sqlite" python -m src.migrations.cli verify
```

The first command initializes only that temporary database; the following diagnostics must leave it unchanged. Do not run smoke commands against the default database, a Desktop user database, or a real deployment volume. The runner does not provide a downgrade command.

## Failures and Forward Recovery

The normal recovery path is to correct the problem and retry forward. Do not delete registry rows or run a destructive down migration:

1. Stop every process that uses the affected SQLite database.
2. Preserve the stable error category and failed migration ID without sharing sensitive paths or SQL parameters.
3. Back up the database, then correct lock contention, disk, permission, or data preconditions.
4. Restart with a fixed application release containing the same published registry. A failed migration has no applied row, so it runs again.
5. Run `status` and `verify`; confirm that current equals target and that there are no mismatches or unknown IDs.

For a checksum mismatch, do not edit the migration or manually alter registry rows. Restore a matching application and database pair, or upgrade with a release containing a new explicit migration. For an unknown higher migration ID, use an application version that recognizes it instead of forcing the older application to start.

## Backup, Rollback, and Disaster Recovery

The Migration Runner is not a backup system and does not create deployment backups automatically.

- Stop all writers before an upgrade. Prefer the SQLite Online Backup API or a tested volume snapshot.
- Make file-level copies only after the application fully exits, and keep the main database, `-wal`, and `-shm` files consistent. Never copy only the live `.db` file.
- Back up or snapshot the Docker `./data/` volume before upgrading. Fully exit Desktop first; back up the `data/` folder beside the executable on packaged Windows and the `data/` folder under Electron `userData` on packaged macOS.
- Restore a backup for database corruption or another disaster. A normal migration failure uses transaction rollback and a forward retry.
- After a code rollback, the older application can fail closed because the database contains an unknown higher migration. Restore a matching code and backup pair; never delete an applied row to simulate a downgrade.

After restoring, run SQLite integrity checks and migration `verify` in an isolated environment before reopening the service.

## Desktop, Docker, and GitHub Actions

### Desktop

The Windows and macOS PyInstaller builds explicitly include `src.migrations`, `src.migrations.registry`, `src.migrations.versions`, and the version `.py` sources required by source-bound checksums. They then run a `src.migrations.registry` import probe against the frozen backend. Electron remains responsible only for starting and supervising the Python backend. It does not duplicate the runner or schedule it in the background.

Fresh Desktop databases and databases retained from an older release follow the same sequence. A frozen-backend path that first enters `DatabaseManager` returns only after migration succeeds. On failure, that database-dependent path fails and uses the existing Desktop logging path. This does not imply that the general health endpoint eagerly initializes the database.

### Docker and Actions

The Docker image uses the same importable migration package as source runs, CLI, and Desktop. The first `DatabaseManager` initialization in a new image upgrades an old volume synchronously before that call returns. Database write locking serializes migrations when multiple containers point to one SQLite file, but an upgrade should still run with only one writer whenever possible.

The CI Docker smoke imports `src.migrations.registry`, calls `get_migrations()`, and asserts that the final entry equals `TARGET_VERSION`. Resource discovery does not depend on an absolute development-machine path.

## Adding a Migration

1. Add a stable ID higher than the current target under `src/migrations/versions/`.
2. Use a stable English description, and do not let business configuration change the schema shape.
3. Keep `upgrade` limited to this migration's DDL or DML. Do not begin, commit, roll back, close, or access the underlying DBAPI transaction.
4. Register it explicitly in strictly increasing order. Do not use directory auto-discovery.
5. Add fresh, historical, repeat, failure and recovery, checksum, and concurrency tests.
6. Pass the Desktop package probe, Docker import smoke, and complete backend gate before release.

Never edit the original migration after release. Every correction moves forward under a new ID.
