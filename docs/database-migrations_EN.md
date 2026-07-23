# Database Migrations

[Chinese](database-migrations.md) | [English](database-migrations_EN.md)

StockPulse uses an in-repository Python Migration Runner to manage SQLite schema evolution. The first phase does not introduce Alembic and does not replace the existing `Base.metadata.create_all()` or startup `_ensure_*` compatibility logic all at once; instead it converts startup DDL into formal migrations one slice at a time.

The current production registry target is `202607190005_intelligence_item_unique_index`. `202607160001_migration_runner_registry` establishes additive metadata required by the ordered registry; `202607190001`–`202607190005` convert the startup `_ensure_*` steps that previously backfilled the `llm_usage` telemetry columns, the `decision_signals` `decision_profile` column/indexes/backfill, the `portfolio_idempotency_records` scope columns/unique-index/normalization/guard-trigger, the `intelligence_items` legacy scope-value normalization, and the `intelligence_items` rebuild from legacy url uniqueness to the scoped composite unique key into formal migrations that repair legacy databases idempotently and are no-ops on fresh databases. Startup no longer runs any business schema DDL compatibility step.

Data model versioning has two orthogonal layers in this repository: the **DB schema layer** is managed by the ordered migration runner described below (table/column/index shape evolution), and the **serialized domain artifact layer** is managed by embedded version tags (the internal contract of persisted or cross-module payloads); see "Serialized Artifact Versioning" at the end.

## Core Contract

Each migration has these stable properties:

| Property | Contract |
| --- | --- |
| `id` | Globally unique, strictly increasing, and immutable after release |
| `description` | Stable English diagnostic text |
| `checksum` | Deterministic SHA-256 of the complete normalized migration module source |
| `upgrade` | Synchronous upgrade callable accepting a restricted `MigrationExecution` SQL capability and returning `None` |

`src.migrations.registry` is the only source of truth for execution order. The runner does not use filesystem traversal order and does not infer upgrade functions from filenames. Repeated imports must produce the same IDs, order, and checksums.

Production migrations use `Migration.from_source_file()` so the checksum covers the complete module containing the real `upgrade`, helper functions, and constants. Normalization changes only CRLF/CR physical line endings to LF; every other character, including semantic whitespace inside strings and the final file newline, remains covered. Absolute paths never enter the hash. A released migration must never be edited, reordered, or deleted. Add a migration with a higher ID whenever schema or data behavior must change. Editing an applied migration causes checksum verification to fail and the application to fail closed.

Production migrations are reviewed, trusted code shipped with the repository. They are not user scripts, plugins, or remote payloads. The runner gives `upgrade` only `execute` and `exec_driver_sql`; it does not expose a full SQLAlchemy `Connection`, engine, raw cursor, underlying DBAPI handle, `executescript`, or transaction-control methods. `execute` accepts only the exact `TextClause` produced by `sqlalchemy.text()`. The runner snapshots its plain SQL string once and executes it through its own driver path, so an arbitrary SQLAlchemy executable, a `str` subclass, an execution callback attached to a `TextClause` instance, or a concurrent mutation cannot receive the real `Connection` or replace the validated statement. The capability is valid only during the synchronous `upgrade` call. When the callable returns or raises, the runner first rejects new and queued calls, waits for statements already inside the driver path to finish and materialize, and then revokes the connection lease. A retained facade therefore cannot continue executing outside the runner transaction, even when the caller supplied a `Connection` that remains open. Query results are materialized into cursor-independent tuples and dictionaries while the lease is held. Statement execution or materialization failures and forbidden capability requests are irreversibly latched; even if migration code catches the corresponding exception, the runner refuses the applied row and rolls back. Published version modules may retain historical `Connection` type annotations to preserve their source checksum, but the runtime object is still the restricted capability. Migration registration recursively checks `inspect.unwrap` wrappers, `functools.partial` targets, and callable objects, rejecting coroutine, generator, and async-generator functions as well as wrapper cycles. A `contextmanager` or `asynccontextmanager` therefore cannot hide a lazy upgrade. The source-bound AST guard, transaction-control SQL preflight, random savepoint, and transaction-state checks remain defense in depth; the runner does not overwrite a caller-installed SQLite authorizer. These boundaries isolate common mistakes and regressions in trusted code; they are not a Python security sandbox and cannot make untrusted migration code safe to execute. Every new migration still requires source review and complete tests; never load upgrade code dynamically from configuration, a database, or the network.

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
  -> remaining _ensure_* compatibility and repair steps
  -> stamp a fresh/known legacy baseline
  -> apply pending migrations in registry order within the same transaction
  -> prove the fresh/known legacy baseline (schema shape and foreign keys)
  -> commit the serialized initialization transaction
  -> mark DatabaseManager initialized
```

Migrations finish synchronously inside `DatabaseManager` initialization and never continue as a background task. SQLite serializes the whole `create_all + baseline stamp + pending migrations + baseline proof` phase under one database-level write lock and transaction, preventing two fresh processes from racing to create tables and keeping the entire initialization atomic across the registry, schema, and baseline proof. Startup applies the ordered migrations inside that same write lock, so the baseline proof observes the fully repaired schema. Startup no longer runs any business schema DDL compatibility step: every `CREATE`/`ALTER`/`DROP` during initialization occurs only inside `metadata.create_all` (the fresh baseline) or while a registered migration's `upgrade` callable is actually executing. A regression test captures those statements and rejects stray schema DDL outside create_all and registered callables, including startup ensures re-introduced in outer runner orchestration, savepoint handling, bootstrap inspection, or applied-row writes. The first backend path that needs `DatabaseManager` returns only after migration finishes. If any initialization step fails, `DatabaseManager` remains uninitialized; `create_all`, applied rows, and every DDL/DML statement in that transaction roll back together, leaving no half-migrated state.

The general `/api/health` endpoint is not currently a database readiness probe, so a health response does not promise eager database initialization. This lazy boundary does not create a background migration: the first call that actually enters `DatabaseManager` still waits for the runner to succeed or fail completely.

## Transactions, Locking, and Concurrency

- SQLite initialization uses one `BEGIN IMMEDIATE` to serialize `create_all + _ensure_* + baseline stamp + pending migrations + baseline proof` and reuses the application's existing busy timeout contract; startup applies the ordered migrations inside that write lock instead of taking a separate lock per migration.
- On the startup path every pending migration's DDL or DML and applied row live inside the initialization transaction and commit or roll back once with it. The `apply_pending` engine entry point (reused by standalone diagnostics and tooling) still takes its own database-level write lock and commits per migration; both paths share the same guard, savepoint, and applied-row write logic.
- An `upgrade` must execute synchronously and return `None`. Registration rejects known lazy functions and wrapper cycles. Any non-`None` runtime return fails closed with `migration_upgrade_invalid_return`. The runner first closes a natively closeable coroutine or generator and then rolls back the current transaction, so DDL or DML performed before the invalid return and the applied row are not committed.
- The runner exclusively owns transaction control. An `upgrade` receives only the restricted SQL capability, whose public surface exposes no full `Connection`, engine, raw cursor, underlying DBAPI handle, `executescript`, `begin`, `commit`, `rollback`, savepoint, `close`, or `execution_options`. `execute` rejects arbitrary executables and sends one validated snapshot from an exact `TextClause` through the runner-owned driver path, preventing a SQLAlchemy statement callback or concurrent mutation from receiving the underlying connection or replacing that statement. When `upgrade` returns or raises, the runner publishes the revoked state first, rejects new calls and queued calls that have not obtained the connection, and waits for in-flight statements to finish inside the same transaction before writing the applied row. Any in-flight statement failure is latched as a migration failure. Forbidden attributes, arbitrary executables, non-builtin SQL strings, and helper-indirected transaction requests are likewise latched as capability violations, so catching their exceptions and returning `None` cannot produce a commit. DDL/DML previously executed through the capability rolls back with the applied row, and reusing a retained facade produces no additional database change. Explicit SQL `BEGIN`, `COMMIT`, `END`, `ROLLBACK`, `SAVEPOINT`, and `RELEASE`, including forms preceded by comments, empty statements, or a BOM, is rejected before entering the real Connection. The random savepoint and transaction-state checks continue to verify runner ownership, while an existing caller-installed SQLite authorizer remains unchanged.
- Later migrations do not run after the first failure.
- When two processes start together, the second process waits for the write lock and then reloads the applied registry. The same upgrade does not run twice.
- A busy timeout returns a stable migration error. An in-process `threading.Lock` is not used as a substitute for cross-process locking.

Errors contain only a stable category and failed migration ID. They do not log a complete `db_url`, absolute path, SQL parameters, or sensitive data.

## Fresh and Historical Databases

### Fresh Database

A database is recognized as fresh only when inspection under the initialization lock finds no user tables before `create_all()`. SQLAlchemy metadata then creates the current table layout, and the runner bootstraps the applied registry and records the baseline. Even when `create_all()` already created a target column, the corresponding migration must follow its contract and receive an applied record. A second startup verifies the registry without running the upgrade again.

### Historical Database

A historical database validates any existing registry under the initialization lock, runs the existing `_ensure_*` compatibility steps, applies the ordered runner within the same transaction, and then proves the baseline. The explicitly supported release boundaries are:

- `v3.0.0`, `v3.4.0`, and `v3.20.0`: without a registry, the database must match the corresponding fixed release profile.
- `v3.21.0` and `v3.26.3`: the database must carry the known legacy baseline row; the checksum column may not exist yet.

Each pre-baseline profile records a fixed source tag and commit and fully validates that release's required tables, ordered columns, SQLite type affinity, primary keys, `NOT NULL`, defaults, unique keys and collations, foreign keys, and `WITHOUT ROWID` / `STRICT` options. Partial or expression unique indexes, explicit `ON CONFLICT` policies, and known later-release tables are also part of the fail-closed boundary. Profiles are checked newest first, so an incomplete newer database cannot fall back to an older profile. Compatibility repair must then prove the complete current ORM baseline and pass `PRAGMA foreign_key_check` before a baseline row is written. A partial lookalike, missing constraint, wrong affinity, incomplete profile, or unrelated SQLite database fails closed and rolls back the complete compatibility transaction. Extra custom tables provide no profile evidence and cannot replace required tables. An unrecognized old database is never treated as fresh or stamped automatically; stop writers, make a complete backup, and have a maintainer establish its source version and an explicit migration path.

The upgrade does not remove existing business tables, fields, or data. The `llm_usage`, `decision_signals`, `portfolio_idempotency_records`, and `intelligence_items` startup compatibility steps are now the formal migrations `202607190001`–`202607190005`; startup no longer runs any business schema DDL compatibility step, keeping only `create_all` (fresh baseline table creation) and the baseline record stamp, and every other schema change must ship as a new dedicated migration.

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

Failures through the supported execution capability roll back completely and can be retried forward after correcting the migration or its preconditions. Never insert an applied row manually. In-process Python cannot sandbox malicious code: if trusted migration code deliberately uses reflection, reopens the database, or writes outside the capability, that is an unsupported code violation. Stop writers, compare against the pre-upgrade backup, and either restore it or publish a forward migration that explicitly proves and repairs the state.

For a checksum mismatch, do not edit the migration or manually alter registry rows. Restore a matching application and database pair, or upgrade with a release containing a new explicit migration. For an unknown higher migration ID, use an application version that recognizes it instead of forcing the older application to start.

## Backup, Rollback, and Disaster Recovery

The Migration Runner is not a backup system and does not create deployment backups automatically.

- Stop all writers before an upgrade. Prefer the SQLite Online Backup API or a tested volume snapshot.
- Make file-level copies only after the application fully exits, and keep the main database, `-wal`, and `-shm` files consistent. Never copy only the live `.db` file.
- Back up or snapshot the Docker `./data/` volume before upgrading. Fully exit Desktop first; back up the `data/` folder beside the executable on packaged Windows and the `data/` folder under Electron `userData` on packaged macOS.
- Restore a backup for database corruption, code that writes outside the capability, or another disaster. A normal failure inside the supported execution capability uses transaction rollback and a forward retry.
- After a code rollback, the older application can fail closed because the database contains an unknown higher migration. Restore a matching code and backup pair; never delete an applied row to simulate a downgrade.

After restoring, run SQLite integrity checks and migration `verify` in an isolated environment before reopening the service.

## Desktop, Docker, and GitHub Actions

### Desktop

The Windows and macOS PyInstaller builds explicitly include `src.migrations`, `src.migrations.registry`, `src.migrations.versions`, and the version `.py` sources required by source-bound checksums. They then run a `src.migrations.registry` import probe against the frozen backend. Electron remains responsible only for starting and supervising the Python backend. It does not duplicate the runner or schedule it in the background.

Fresh Desktop databases and databases retained from an older release follow the same sequence. A frozen-backend path that first enters `DatabaseManager` returns only after migration succeeds. On failure, that database-dependent path fails and uses the existing Desktop logging path. This does not imply that the general health endpoint eagerly initializes the database.

### Docker and Actions

The Docker image uses the same importable migration package as source runs, CLI, and Desktop. The first `DatabaseManager` initialization in a new image upgrades an old volume synchronously before that call returns. Database write locking serializes migrations when multiple containers point to one SQLite file, but an upgrade should still run with only one writer whenever possible.

In addition to importing `src.migrations.registry`, calling `get_migrations()`, and asserting that the final entry equals `TARGET_VERSION`, the CI Docker smoke mounts a supported legacy SQLite fixture as the image's `/app/data` volume. It uses the image's default entrypoint to initialize the real `DatabaseManager` as the dropped-privilege `dsa` user (UID 1000), verifies business canaries, applied checksums, and the target version, and then starts a second container against the same volume to prove idempotency. This covers container permissions, the volume path, startup migration, migration resource discovery, and restart recovery without depending on an absolute development-machine path or touching a default or real user database.

## Adding a Migration

1. Add a stable ID higher than the current target under `src/migrations/versions/`.
2. Use a stable English description, and do not let business configuration change the schema shape.
3. Use a synchronous, non-generator `upgrade` callable that accepts `MigrationExecution` and explicitly or implicitly returns `None`. Pass only a `TextClause` created directly by `sqlalchemy.text()` to `execute`, or use `exec_driver_sql`, plus safe result reads for this migration's parameterized DDL or DML. Do not pass custom executables, seek a full Connection, raw handle, cursor, or transaction control, and make sure the source-bound guard passes. Do not treat the capability or guard as a sandbox for untrusted migrations.
4. Register it explicitly in strictly increasing order. Do not use directory auto-discovery.
5. Add fresh, historical, repeat, failure and recovery, checksum, and concurrency tests.
6. Pass the Desktop package probe, Docker legacy-volume startup and restart smoke, and complete backend gate before release.

Never edit the original migration after release. Every correction moves forward under a new ID.

## Serialized Artifact Versioning

The ordered migration registry above governs the **DB schema layer**. In addition, the repository embeds explicit version tags in a set of **serialized domain artifacts** (Pydantic / dataclass payloads that are persisted or passed across modules) so that historical payloads stay interpretable after the models evolve. This layer is orthogonal to DB migrations: DB migrations govern table/column/index shape, while serialized versions govern the internal contract of a payload.

### Current version-tag inventory

| Artifact | Version constant | Current value | Field | Persistence surface |
| --- | --- | --- | --- | --- |
| `AnalysisContextPack` | `PACK_VERSION` | `1.0` | `pack_version` (`Literal["1.0"]`) | `analysis_history.context_snapshot`, prompt summary, overview |
| `MarketThemeContext` | `MARKET_THEME_SCHEMA_VERSION` | `market-theme-v1` | `schema_version` | market structure snapshot |
| `StockMarketPosition` | `STOCK_MARKET_POSITION_SCHEMA_VERSION` | `stock-market-position-v1` | `schema_version` | market structure snapshot |
| `MarketStructureContext` | `MARKET_STRUCTURE_SCHEMA_VERSION` | `market-structure-v1` | `schema_version` | market structure snapshot, prompt section |
| Canonical decision scale | `CANONICAL_DECISION_SCALE_VERSION` | `decision-scale-v1` | `scale_version` (`score_band_metadata`) | DecisionSignal / report scoring convention |
| Runtime event | `RUNTIME_EVENT_SCHEMA_VERSION` | `1` | `schema_version` | Agent runtime events |
| Provider usage | `PROVIDER_USAGE_SCHEMA_VERSION` (+ `PROVIDER_USAGE_SCHEMA_NAME`) | `2026-06-10` (`provider_usage_v1`) | `provider_usage_schema_version` | `llm_usage.provider_usage_schema_version` column |

The inventory is bound to the actual constants by the guard test `tests/test_data_model_versioning_guard.py`; any constant drift or dropping a version field during serialization is caught.

### Backward / forward compatibility rules

- **Add fields within a version.** Adding an optional field with a safe default does not bump the version constant. A consumer reading an older payload that lacks the field falls back to the default, and historical reads are unaffected.
- **Bump the version only for breaking changes.** Renaming, removing, retyping, or changing the meaning of a field is a breaking change and must bump the version constant to a new value (for example `market-structure-v2`) while keeping read handling for the old value. Released version values are never reused or recycled.
- **Producers always emit the current version tag.** Serialization must carry the version field; it must never be dropped during a dump (the guard test covers this regression).
- **Consumers degrade gracefully on an unrecognized version.** Skip the block, return empty, or fall back to defaults; never hard-fail a historical read because its version does not match. Existing behavior: `src/market_structure_prompt.py` and `src/utils/data_processing.py` skip on a `schema_version` mismatch, and `AnalysisContextPack.pack_version` rejects unknown values via `Literal`.
- **Never rewrite historical payloads in place.** Interpret historical records by their embedded version rather than bulk "upgrading" them. If the persistence surface (column/table) itself must change shape, use a DB migration above; the in-payload version and DB migrations have separate responsibilities.

### Bumping a serialized version

1. Raise the corresponding version constant to a new value and keep a read/degrade branch for the old value.
2. Update this inventory table and the guard test `tests/test_data_model_versioning_guard.py`.
3. If the artifact's persisted column/table shape changes at the same time, add a higher-ID DB migration as well (see "Adding a Migration" above).
4. Go through the normal source review and complete backend gate.

### Artifacts not yet versioned (follow-up)

`Report` (`src/schemas/report_schema.py`), `RunFlowSnapshot` (`src/schemas/run_flow.py`), and `DecisionSignalPresentation` (`src/schemas/decision_signal_presentation.py`) do not yet embed an explicit version field. They can adopt the "add fields within a version / bump only for breaking changes" pattern above the next time their persisted shape changes, at low cost — which is exactly the low-migration-cost evolution this strategy is meant to guarantee.
