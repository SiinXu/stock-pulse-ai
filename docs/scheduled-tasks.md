# Scheduled Tasks

## Two schedulers (read this first)

StockPulse currently has **two independent schedule tracks**. They share the
process-local analysis queue when work is admitted, but they are **not** one
unified scheduler UI or migration wizard.

| Track | Config / API | What it runs | Settings surface | Home surface |
| --- | --- | --- | --- | --- |
| **Legacy day-batch** | `SCHEDULE_ENABLED`, `SCHEDULE_TIME` / `SCHEDULE_TIMES`, plus `STOCK_LIST` | Whole watchlist analysis at fixed daily times | **Legacy day-batch schedule** card (`SchedulerSettingsCard`) | Not listed as versioned “today” rows |
| **Versioned scheduled tasks** | `POST/GET /api/v1/scheduled-tasks`, SQLite definitions | Per-definition stock analysis or research (`schema_version` 1/2) | **Saved schedule definitions** panel | **Versioned scheduled tasks today** card |

Both tracks may be enabled at once. That can produce overlapping analysis load
(the queue may coalesce identical execution contracts, but it does not merge
unrelated jobs). Prefer enabling only the track you intend to use.

**Process ownership** is deployment-role based (`--serve`, `--schedule`, Compose
`analyzer` vs `server`, Desktop `--serve-only`). The internal
`DSA_SCHEDULED_TASK_OWNER` handoff makes those roles explicit; it is **not** a
second operator-facing switch. The legacy status card reports only legacy
day-batch next/last times — it does not expose a live “this process owns
versioned tasks” indicator.

There is no English twin of this document yet (`docs/scheduled-tasks_EN.md`);
this file is the single source for both tracks.

## Scope

The scheduled-task model stores deterministic daily stock-analysis and bounded
research tasks and runs them through the existing process-local
`AnalysisTaskQueue ->
AnalysisService` boundary. It does not add a natural-language scheduler,
workflow engine, worker service, second analysis pipeline, or natural-language planning UI. Settings exposes a minimal list with enable/disable for
persisted definitions. Home exposes a read-only projection of today's occurrences.

Schema version 1 supports one configurable stock analysis per definition.
Schema version 2 adds the predefined `research_brief` and `risk_check` types.
Both versions use the same task table, occurrence claim, run statuses, retry
limits, history, notification projection, and runtime ownership contract.

## Definition Contract

`POST /api/v1/scheduled-tasks` continues to accept the schema-v1 stock-analysis
shape:

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

Research definitions use schema version 2 and a deliberately smaller payload:

```json
{
  "schema_version": 2,
  "name": "AAPL downside review",
  "task_type": "risk_check",
  "schedule": {
    "kind": "daily",
    "time": "09:30",
    "timezone": "America/New_York",
    "calendar_market": "us",
    "non_trading_day_policy": "skip"
  },
  "payload": {
    "stock_code": "AAPL",
    "notify": true
  },
  "enabled": true,
  "max_attempts": 2
}
```

- `stock_analysis` requires schema version `1`; `research_brief` and
  `risk_check` require schema version `2`. Version and task type cannot be
  mixed.
- `research_brief` always submits the canonical brief report contract.
  `risk_check` submits the canonical detailed report contract with the
  `persona_tail_risk` entry from the effective canonical Agent skill catalog.
  A configured custom skill with that same stable ID follows the existing
  catalog override rule; this schedule contract does not pin the bundled file.
  Research payloads cannot supply arbitrary prompts, report modes, skills,
  credentials, or provider configuration.
- `kind` must be `daily`; `time` uses 24-hour `HH:MM` in the supplied IANA
  timezone.
- `calendar_market` is one of `cn`, `hk`, `us`, `jp`, `kr`, or `tw` and must
  match the normalized stock code's market.
- `non_trading_day_policy=skip` records a terminal skipped occurrence without
  dispatching analysis only when the market is confidently classified as
  closed. If classification is unavailable, the occurrence is interrupted and
  no analysis is dispatched. `run` dispatches without consulting the calendar.
- `max_attempts` is bounded from 1 through 3. The default is one attempt.
- Unknown definition or payload fields are rejected; arbitrary commands,
  prompts, credentials, and provider configuration are not persisted here.
- Omitted fields use the documented defaults. Explicit scalar values must use
  their declared JSON types: string booleans or integers are not coerced, and
  unknown fields at the definition, schedule, or payload boundary return 422.

Times are stored as UTC-naive values under the repository's SQLite convention
and returned by the API as UTC timestamps. The IANA timezone remains part of
the definition, so daylight-saving changes are applied when calculating each
next occurrence. During a fall-back fold, the earliest valid UTC instant is the
only occurrence for that schedule-local date. If it has passed, the next local
date is selected rather than running the second fold. If the configured wall
time does not exist during a spring-forward gap, that local date is skipped
rather than silently shifted.

## API

All routes use the existing `/api/v1` authentication policy:

| Method | Route | Behavior |
| --- | --- | --- |
| `POST` | `/scheduled-tasks` | Create a supported schema-v1 or schema-v2 definition. |
| `GET` | `/scheduled-tasks` | List definitions, optionally filtered by `enabled`. |
| `GET` | `/scheduled-tasks/today?timezone=<IANA>` | List past and upcoming occurrences on today's date in the requested display timezone. |
| `GET` | `/scheduled-tasks/{task_id}/status` | Return the definition and latest run. |
| `POST` | `/scheduled-tasks/{task_id}/enable` | Enable and calculate the next future occurrence. |
| `POST` | `/scheduled-tasks/{task_id}/disable` | Disable and clear `next_run_at`. |
| `GET` | `/scheduled-tasks/{task_id}/runs` | List durable occurrence records. |

Enable and disable are idempotent. Disabling prevents later occurrences but
does not cancel an analysis that was already submitted to the canonical task
queue. A conflict-waiting occurrence that has not submitted or adopted a
compatible execution is interrupted instead of dispatching after disable. An
already submitted execution may finish and still record success, but a failure
after disable is interrupted instead of creating a retry or resubmission.
Each normal enable/disable transition advances an internal execution
generation. At SQLite's terminal generation ceiling, disable still clears the
occurrence without incrementing the generation, while re-enable is rejected. A
disable followed by re-enable therefore cannot revive an occurrence that was
already waiting to dispatch or retry under the older definition state.

The `today` projection combines durable runs with enabled definitions whose
next occurrence is later on the same local calendar date. Its range uses local
midnight boundaries, so daylight-saving transition dates correctly span 23 or
25 UTC hours. Completed and disabled definitions remain visible through their
durable run, while disabled definitions with no run are not projected. The
projection is read-only and does not claim, execute, retry, or mutate a task.
Each item is isolated: an occurrence whose definition was concurrently deleted,
or a corrupt definition or run, is omitted without making the rest of the Home
card unavailable.

Responses use a `compatibility` discriminator. Schema-v1 and schema-v2
definitions return `supported` and the complete definition. An unknown future schema returns
`unsupported_schema` plus only `id`, `schema_version`, `name`, enablement,
timing, and timestamps; schedule and payload fields are not parsed or exposed.
This opaque projection also applies to the `today` route. Status and run-history
reads remain available, while enable/disable returns
`409 scheduled_task_schema_unsupported` without changing any definition field.

The database mutation is authoritative. If the immediate best-effort runtime
reconciliation fails after a create, enable, or disable commit, the API still
returns the committed result and logs `scheduled_task_runtime_reconcile_deferred`;
the owner loop retries discovery on its next polling interval.


## Web UI (minimal)

The product surface is intentionally small:

| Surface | Behavior |
| --- | --- |
| Settings → System & Security → Scheduling → Legacy day-batch | Configures `SCHEDULE_*` + shows legacy status only. Copy labels it as legacy and warns when both tracks appear enabled. |
| Settings → System & Security → Scheduling → Saved definitions | Lists versioned definitions, shows next run when known, and enable/disable supported definitions. Unsupported future schemas are visible but not mutable. |
| Home → Configurable area → Versioned scheduled tasks today | Read-only today projection from `GET /scheduled-tasks/today` (versioned track only). Empty state links to Settings management. |

| Settings → System & Security → Scheduling | Create supported definitions (`stock_analysis` / `research_brief` / `risk_check`), list persisted definitions, show next run and latest run status when the status API returns them, and enable/disable supported definitions. Unsupported future schemas are visible but not mutable. |
| Home → Configurable area → Scheduled tasks today | Read-only today projection from `GET /scheduled-tasks/today`. Empty state links to Settings management. |

Defaults and framing:

- Create uses the existing `POST /scheduled-tasks` contract only. There is still no edit/delete definition form, natural-language planner, multi-tenant ownership, or distributed scheduler in this UI.
- Latest status is loaded via `GET /scheduled-tasks/{id}/status` after list refresh (fail-soft per item). Full run-history browsing stays API-only for now.
- Execution remains process-local through `AnalysisTaskQueue` / ADR-008.
- Research brief and risk-check schedules are research-only aids, not investment advice.
- Daily stock-list scheduler env (`SCHEDULE_*`) remains the separate **legacy** system-config card on the same Settings view; it is not the versioned definitions list.

## Occurrence And Execution Semantics

Each due slot is claimed by atomically advancing the definition's
`next_run_at`. `scheduled_task_runs` has a unique `(task_id, scheduled_for)`
constraint, so repeated polls cannot claim or dispatch the same occurrence.
After downtime, the service claims at most one overdue occurrence and advances
directly to the next future daily time; it does not replay an unbounded backlog.
Every persisted definition is validated through its matching schema-v1 or
schema-v2 contract before it is mutated, claimed, or reconciled. An unsupported future definition
is never parsed or rewritten. Its due slot receives one `interrupted` occurrence
as a fence, and the due query excludes that same slot on later polls. When code
that supports the schema returns, it atomically advances this exact
schema/generation fence to the next future daily occurrence without replaying
the old slot. A corrupt supported definition is atomically disabled and records
one `interrupted` quarantine occurrence. If the schema version or execution
generation itself is not an exact positive integer, it cannot form a truthful
run snapshot: the definition is atomically disabled without an occurrence and
its generation is moved, under the same SQLite writer lock, above every valid
persisted run snapshot for that task. If the signed SQLite generation ceiling
is reached, disabling still clears the next occurrence without incrementing the
generation, while re-enabling remains rejected until operator repair.
Enablement, supported
claims, and supported-definition quarantine writes
all compare the expected schema version in the same database statement; a CAS
miss is re-read and reclassified before any later action.

Each occurrence snapshots both the understood schema version and execution
generation. Initial submission and every retry first persist a tokenized
`dispatching` reservation. The service then acquires SQLite's writer lock with
`BEGIN IMMEDIATE`, reloads the definition and run, rechecks schema, generation,
enablement, token, and status, and admits queue work before storing the accepted
execution identity in that same writer window. A concurrent disable or schema
writer therefore commits either before queue admission, which prevents the
side effect, or after the execution ID is durable. If database finalization is
uncertain after queue acceptance, the reservation is interrupted on recovery
and is not blindly replayed.

The run statuses are:

| Status | Meaning |
| --- | --- |
| `dispatching` | A tokenized queue-admission reservation exists but its canonical task ID is not yet durable. |
| `running` | The canonical analysis task is pending or processing. |
| `retry_wait` | A failed compatible execution is waiting for retry, or an incompatible active stock task is waiting for a new submission probe after 30 seconds. |
| `succeeded` | The canonical analysis completed; available result references are stored. |
| `failed` | The compatible execution-attempt bound or separate queue-admission failure bound ended. |
| `skipped` | The selected market was closed and policy was `skip`. |
| `interrupted` | Execution identity, definition validity, or required calendar classification was unavailable; no blind dispatch occurs. |

Analysis submission reuses the canonical task queue's stock deduplication. If
an active task has the same canonical stock and complete execution contract, the
occurrence observes it instead of creating duplicate analysis and notification
side effects. The contract covers normalized report type, analysis phase,
force-refresh, notification, ordered skills, skill-selection strictness, report
language, decision-memory override, portfolio context, query source, and
whether contextual reply targets are bound. `detailed` and `full` normalize to
the same report mode; `None` and an explicit empty or disabled value remain
distinct where execution distinguishes them.

An incompatible active task moves the occurrence to `retry_wait` without adding
an execution ID or consuming `max_attempts`; after the fixed 30-second interval,
the queue is probed again. This serializes legitimate same-stock schedules while
ensuring one active analysis at a time. Compatible accepted or coalesced
executions consume attempts. If a non-owned compatible execution fails and
attempts remain, the occurrence submits again rather than retrying someone
else's task. Only a task ID created by the occurrence can use the queue's retry
operation. `execution_task_ids` remains append-only audit history, with the last
ID representing the execution currently being observed.

If the required effective-catalog risk-check skill is unavailable during
admission, no fallback analysis is submitted. The occurrence uses the existing
queue-admission failure counter, waits 30 seconds between probes, and becomes
`failed` after three admission failures without consuming an analysis attempt.
Queue metadata also marks this selection strict, so if the catalog entry
disappears before the Analyzer or Agent resolves it, execution fails and follows
the normal bounded execution retry path instead of silently activating default
skills. Once admitted, all other execution failure and retry behavior is
identical to schema-v1 stock analysis.

`attempt_count` increases only when a newly accepted or exactly compatible
coalesced execution ID is durable. Queue shutdown, executor rejection, and
other admission failures do not consume analysis attempts; they increment the
separate `dispatch_failure_count` and retry after 30 seconds, stopping after
three admission failures. Incompatible duplicate probes consume neither
counter. A missing process-local retry source is interrupted immediately
because repeating that lookup cannot recover its execution state.

Successful runs expose `notification_status`, `notification_channels`, and
`notification_failed_channels`. `notify=false` records `not_requested`.
Requested delivery records `ok`, `degraded`, `failed`, `skipped`,
`not_configured`, or `unknown` from the canonical analysis diagnostic result.
Only bounded sanitized status/channel evidence is stored; diagnostic messages
and arbitrary result details are not copied into the schedule record. Delivery
failure does not change the occurrence from `succeeded`, consume another
analysis attempt, or replay the analysis. Durable per-channel replay is outside
this phase and requires an outbox contract.

The execution authority is process-local, as documented in
[`task-execution-contract.md`](task-execution-contract.md) and
[ADR-008](adr/ADR-008-persisted-schedule-process-local-execution-boundary.md).
The durable
occurrence claim prevents duplicate polling, but it does not claim distributed
exactly-once execution. If a process exits after queue submission and before
the task ID is stored, the durable dispatch reservation becomes `interrupted`
and fails closed instead of blindly repeating a possibly completed side effect.
The same rule applies to retry admission. Multi-worker scheduling requires a
separate architecture decision and is out of scope.

## Trading Calendar Behavior

For `skip`, the scheduler calls the strict
`src.core.trading_calendar.classify_market_session` boundary for the
occurrence instant converted to the selected market's exchange timezone, not
the user-selected schedule timezone. `OPEN` dispatches, `CLOSED` records `skipped`, and
`UNKNOWN` records `interrupted` with
`scheduled_task_calendar_unavailable`; financial work is never dispatched when
classification is unavailable. The legacy `is_market_open` helper remains
fail-open for its existing callers, so this stricter behavior is isolated to
persisted scheduled tasks.

## Runtime Ownership

No new scheduler loop is introduced:

- Direct `uvicorn server:app` and normal `python main.py --serve` runtimes own
  one `scheduled_tasks` background callback in `RuntimeSchedulerService`. The
  owner loop starts without querying scheduled-task persistence and retries
  transient database discovery failures on later polling intervals. It remains
  available while legacy `SCHEDULE_ENABLED` is false; the existing system
  scheduler status still reports only the legacy setting.
- `python main.py --schedule` and the Docker image's default analyzer command
  attach the same callback to the existing standalone `Scheduler`.
- `python main.py --serve --schedule` keeps the existing API-owned schedule
  handoff and therefore has one owner.
- Generic `python main.py --serve-only` is a persisted-task non-owner. In the
  provided Docker Compose topology, the `analyzer` service executes persisted
  tasks and the `server` service provides CRUD/status APIs. Starting only
  `server` stores definitions but does not execute them; start `analyzer` for
  scheduled execution.
- Desktop starts the same `--serve-only` entrypoint with
  `DSA_DESKTOP_MODE=true`; that backend owns persisted tasks while continuing
  to suppress the legacy environment-driven daily job at startup. Saving the
  existing `SCHEDULE_ENABLED` settings may still start or rebuild that legacy
  job later, preserving the prior Web/Desktop configuration contract. The
  internal `DSA_SCHEDULED_TASK_OWNER` handoff keeps these deployment roles
  explicit; it is not a second operator-facing scheduling switch.

Do not run multiple analyzer processes against the same task database. SQLite
claiming prevents duplicate due-slot rows, but canonical execution state and
retry ownership remain process-local.

## Persistence And Rollback

Migration `202607240002_scheduled_task_schema` already supplies
`scheduled_tasks` and `scheduled_task_runs`, including internal definition
snapshots, execution generation, dispatch reservations, admission-failure
counts, and notification outcomes. Schema-v2 research tasks reuse those tables;
this feature adds no database migration or configuration.

The normal code rollback is to revert the research-task feature. The preceding
schema-v1 application keeps stock-analysis definitions working and exposes
schema-v2 definitions as opaque unsupported records without mutating or
executing them. If the older application observes a due schema-v2 slot, it
records only the terminal unsupported-schema fence and leaves the definition
unchanged. Re-deploying schema-v2 code detects that exact fence, advances the
definition to its next future daily occurrence, and never replays the old
possibly stale slot. No database restore, manual enable toggle, or destructive
table operation is required for this rollback.
