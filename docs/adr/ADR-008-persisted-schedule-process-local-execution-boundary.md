# ADR-008: Separate Persisted Schedules From Process-Local Execution

- Status: `Accepted`
- Decision date: 2026-07-24
- Decision owners: StockPulse maintainers
- Amends: [ADR-004](ADR-004-process-local-task-execution-authority.md)
- References: [Issue #441](https://github.com/SiinXu/stock-pulse-ai/issues/441), [`docs/scheduled-tasks.md`](../scheduled-tasks.md), [`docs/task-execution-contract.md`](../task-execution-contract.md)

## Context

Personal daily schedules must survive application restarts, expose occurrence
history, and prevent repeated dispatch of one due slot. The existing
`AnalysisTaskQueue` deliberately owns execution only inside one process, so
making schedule definitions durable must not turn their aggregate status into a
second task lifecycle or imply distributed exactly-once execution.

Schedule wall times and exchange trading dates are separate concerns. IANA
timezone transitions can produce two or zero UTC instants for one local wall
time, and a user-selected schedule timezone can represent a different calendar
date from the stock's exchange timezone. Persisted definitions also need a
forward-compatibility boundary so an older application does not rewrite a
newer definition that it cannot interpret.

## Decision

`scheduled_tasks` is the durable, versioned definition source of truth and
`scheduled_task_runs` is a durable occurrence/audit projection. One runtime
owner atomically claims each supported due slot and submits stock analysis
through the existing `AnalysisTaskQueue -> AnalysisService` path. Canonical task
status, cancellation, retry identity, and side effects remain owned by
`AnalysisTaskQueue` under ADR-004.

The boundary has these rules:

- `(task_id, scheduled_for)` is the occurrence fence. A supported claim advances
  `next_run_at` and inserts its occurrence in one transaction.
- An unknown definition schema is returned as an opaque API projection. It is
  never parsed, executed, enabled, disabled, or rewritten by the older
  application. A due unknown slot receives one `interrupted` occurrence without
  changing any definition field, and subsequent polls exclude that fenced slot.
  When a newer application understands that schema again, it advances an exact
  schema/generation-matched unsupported fence to the next future occurrence; it
  never replays the fenced slot.
  Every older-application definition write includes the expected schema version
  in its atomic database predicate and reclassifies a CAS miss.
- A corrupt current-version definition is not forward-compatible data. It is
  disabled and quarantined with one interrupted occurrence so invalid financial
  work cannot run. Structurally invalid schema-version or execution-generation
  values cannot be copied into a truthful occurrence snapshot, so that narrow
  corruption path atomically disables the definition without a new run and
  replaces the generation under the same writer lock with an exact value above
  every valid persisted run snapshot for that task. Existing active runs are
  interrupted before any later dispatch or retry; a definition at the SQLite
  integer ceiling can still be disabled without incrementing, but remains
  non-enableable until operator repair.
- Daily wall times select the earliest valid instant on a fall-back date, so a
  definition runs at most once per schedule-local date. A local date is skipped
  when its wall time does not exist. Trading-session classification uses the
  exchange's IANA timezone, independently of the schedule timezone.
- Every occurrence snapshots the understood schema and an internal execution
  generation. Normal enable/disable transitions advance that generation, and
  structural-corruption quarantine installs a new exact generation fence, so an
  old conflict or retry wait cannot resume after either transition.
- Initial submission and retry first persist a tokenized `dispatching`
  reservation. Queue admission then runs inside a SQLite `BEGIN IMMEDIATE`
  writer window that rechecks schema, generation, enablement, reservation, and
  run state before storing the accepted execution identity. Concurrent
  definition writers therefore commit either before admission or after the
  identity is durable. An uncertain database finalization leaves the reservation
  fail-closed for interruption instead of replaying a possible side effect.
- Queue coalescing requires equality of every result or side-effect input passed
  to `AnalysisService`, including request-context binding. An incompatible
  active stock task causes conflict waiting without consuming an execution
  attempt. A compatible external execution may be observed, but only execution
  IDs owned by the occurrence may be retried through the queue.
- Disabling does not cancel a canonical execution already in flight, but once
  that execution fails the occurrence is interrupted and cannot create another
  submission or retry side effect.
- `max_attempts` bounds accepted or compatible execution attempts. It does not
  count conflict probes or queue admission failures that submit no work. Queue
  admission failures use a separate bounded counter.
- A completed canonical analysis remains a successful occurrence even when
  notification delivery is failed or degraded. The run stores only a bounded,
  sanitized notification status and channel projection; durable channel replay
  requires a separate outbox design and never replays the whole analysis.

Natural-language planning, general workflow orchestration, a distributed lease,
multi-process execution recovery, and a second analysis pipeline remain out of
scope and require a separate decision.

Process-local task-queue restart recovery (ADR-004 amendment) restores or
interrupts canonical `AnalysisTaskQueue` executions from SQLite checkpoints
before schedule reconciliation. It does not change occurrence fencing: a
recovered execution keeps the same execution id so a `RUNNING` occurrence waits
instead of being finished as `scheduled_task_execution_state_lost`, and a
non-resumable interrupted execution follows the existing terminal reconcile path
without replaying the same `(task_id, scheduled_for)` slot.

## Consequences

- Definitions and occurrence evidence survive restarts without overstating the
  durability of in-memory execution.
- Older applications can inspect newer definitions safely while refusing to
  mutate or execute contracts they do not understand.
- Same-stock schedules serialize through the canonical queue; identical
  schedules share one compatible execution, while materially different analyses
  wait for their own execution instead of being reported as false successes.
- DST and cross-timezone behavior is deterministic: a fall-back date produces
  at most one run at its earliest valid instant, while a spring-forward date has
  no run when its wall time is absent.
- Operators must run one scheduled-task owner for a database. Multi-owner or
  distributed execution would need leases, durable execution state, and another
  ADR.
