# Scheduled Tasks

## Scope

The scheduled-task skeleton stores deterministic daily stock-analysis tasks and
runs them through the existing process-local `AnalysisTaskQueue ->
AnalysisService` boundary. It does not add a natural-language scheduler,
workflow engine, worker service, second analysis pipeline, or scheduling UI.

Schema version 1 supports one stock analysis per definition. A later task type
must reuse the task definition, occurrence claim, run-status, retry, and runtime
ownership contracts below rather than introducing another scheduler.

## Definition Contract

`POST /api/v1/scheduled-tasks` accepts this shape:

```json
{
  "schema_version": 1,
  "name": "US close analysis",
  "task_type": "stock_analysis",
  "schedule": {
    "kind": "daily",
    "time": "16:30",
    "timezone": "America/New_York",
    "calendar_market": "us",
    "non_trading_day_policy": "skip"
  },
  "payload": {
    "stock_code": "AAPL",
    "report_type": "brief",
    "notify": true
  },
  "enabled": true,
  "max_attempts": 2
}
```

- `schema_version` must be `1`.
- `kind` must be `daily`; `time` uses 24-hour `HH:MM` in the supplied IANA
  timezone.
- `calendar_market` is one of `cn`, `hk`, `us`, `jp`, `kr`, or `tw` and must
  match the normalized stock code's market.
- `non_trading_day_policy=skip` records a terminal skipped occurrence without
  dispatching analysis. `run` dispatches on both trading and non-trading days.
- `max_attempts` is bounded from 1 through 3. The default is one attempt.
- Unknown definition or payload fields are rejected; arbitrary commands,
  prompts, credentials, and provider configuration are not persisted here.

Times are stored as UTC-naive values under the repository's SQLite convention
and returned by the API as UTC timestamps. The IANA timezone remains part of
the definition, so daylight-saving changes are applied when calculating each
next occurrence.

## API

All routes use the existing `/api/v1` authentication policy:

| Method | Route | Behavior |
| --- | --- | --- |
| `POST` | `/scheduled-tasks` | Create a schema-v1 definition. |
| `GET` | `/scheduled-tasks` | List definitions, optionally filtered by `enabled`. |
| `GET` | `/scheduled-tasks/{task_id}/status` | Return the definition and latest run. |
| `POST` | `/scheduled-tasks/{task_id}/enable` | Enable and calculate the next future occurrence. |
| `POST` | `/scheduled-tasks/{task_id}/disable` | Disable and clear `next_run_at`. |
| `GET` | `/scheduled-tasks/{task_id}/runs` | List durable occurrence records. |

Enable and disable are idempotent. Disabling prevents later occurrences but
does not cancel an analysis that was already submitted to the canonical task
queue.

## Occurrence And Execution Semantics

Each due slot is claimed by atomically advancing the definition's
`next_run_at`. `scheduled_task_runs` has a unique `(task_id, scheduled_for)`
constraint, so repeated polls cannot claim or dispatch the same occurrence.
After downtime, the service claims at most one overdue occurrence and advances
directly to the next future daily time; it does not replay an unbounded backlog.

The run statuses are:

| Status | Meaning |
| --- | --- |
| `dispatching` | The occurrence is claimed but its canonical task ID is not yet durable. |
| `running` | The canonical analysis task is pending or processing. |
| `retry_wait` | An owned failed analysis is waiting for the fixed 30-second retry boundary. |
| `succeeded` | The canonical analysis completed; available result references are stored. |
| `failed` | The bounded attempts ended or a non-owned coalesced analysis failed. |
| `skipped` | The selected market was closed and policy was `skip`. |
| `interrupted` | Execution identity was lost across the process boundary; no blind redispatch occurs. |

Analysis submission reuses the canonical task queue's stock deduplication. If
the same stock is already running, the occurrence observes that task instead of
creating duplicate analysis and notification side effects. Only a task ID
created by the occurrence can be retried. A retry receives a new canonical task
ID and is included in the same scheduled run record.

The execution authority is process-local, as documented in
[`task-execution-contract.md`](task-execution-contract.md). The durable
occurrence claim prevents duplicate polling, but it does not claim distributed
exactly-once execution. If a process exits after queue submission and before
the task ID is stored, the run becomes `interrupted` and fails closed instead
of blindly repeating a possibly completed side effect. Multi-worker scheduling
requires a separate architecture decision and is out of scope.

## Trading Calendar Behavior

The scheduler calls the existing `src.core.trading_calendar.is_market_open`
boundary for the occurrence's local date. That boundary intentionally fails
open when `exchange-calendars` is unavailable or cannot classify the date, so a
`skip` definition runs in that degradation case rather than being silently
dropped. The locked application requirements include `exchange-calendars`; an
operator who requires strict holiday skipping should treat calendar import or
range warnings as an environment fault.

## Runtime Ownership

No new scheduler loop is introduced:

- Direct `uvicorn server:app` and Web/API/Desktop runtimes attach one
  `scheduled_tasks` background callback to `RuntimeSchedulerService`. Persisted
  tasks can keep that shared loop active while legacy `SCHEDULE_ENABLED` remains
  false; the existing system scheduler status still reports the legacy setting.
- `python main.py --schedule` and the Docker image's default analyzer command
  attach the same callback to the existing standalone `Scheduler`.
- `python main.py --serve --schedule` keeps the existing API-owned schedule
  handoff and therefore has one owner.
- `python main.py --serve-only` deliberately suppresses schedule ownership. In
  the provided Docker Compose topology, the `analyzer` service executes
  persisted tasks and the `server` service provides CRUD/status APIs. Starting
  only `server` stores definitions but does not execute them; start `analyzer`
  for scheduled execution.

Do not run multiple analyzer processes against the same task database. SQLite
claiming prevents duplicate due-slot rows, but canonical execution state and
retry ownership remain process-local.

## Persistence And Rollback

Migration `202607240001_scheduled_task_schema` adds `scheduled_tasks` and
`scheduled_task_runs`. It is additive and preserves existing configuration,
global schedule behavior, analysis history, and task-queue API fields.

The normal code rollback is to revert the feature PR. An older application will
fail closed when it sees the unknown higher migration, so production rollback
must restore a matching pre-upgrade database backup as described in
[`database-migrations_EN.md`](database-migrations_EN.md). If the data is known
to be disposable, a maintainer may remove both new tables and the corresponding
registry state only as a planned maintenance operation; the application does
not provide a destructive down migration.
