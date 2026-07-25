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
  Every older-application definition write includes the expected schema version
  in its atomic database predicate and reclassifies a CAS miss.
- A corrupt current-version definition is not forward-compatible data. It is
  disabled and quarantined with one interrupted occurrence so invalid financial
  work cannot run.
- Daily wall times enumerate both valid DST folds and skip a local date when the
  wall time does not exist. Trading-session classification uses the exchange's
  IANA timezone, independently of the schedule timezone.
- Queue coalescing requires equality of every result or side-effect input passed
  to `AnalysisService`, including request-context binding. An incompatible
  active stock task causes conflict waiting without consuming an execution
  attempt. A compatible external execution may be observed, but only execution
  IDs owned by the occurrence may be retried through the queue.
- Disabling does not cancel a canonical execution already in flight, but once
  that execution fails the occurrence is interrupted and cannot create another
  submission or retry side effect.
- `max_attempts` bounds accepted or compatible execution attempts. It does not
  count conflict probes that submit no work.

Natural-language planning, general workflow orchestration, a distributed lease,
multi-process execution recovery, and a second analysis pipeline remain out of
scope and require a separate decision.

## Consequences

- Definitions and occurrence evidence survive restarts without overstating the
  durability of in-memory execution.
- Older applications can inspect newer definitions safely while refusing to
  mutate or execute contracts they do not understand.
- Same-stock schedules serialize through the canonical queue; identical
  schedules share one compatible execution, while materially different analyses
  wait for their own execution instead of being reported as false successes.
- DST and cross-timezone behavior is deterministic but can produce two runs on a
  fall-back date and no run on a spring-forward date whose wall time is absent.
- Operators must run one scheduled-task owner for a database. Multi-owner or
  distributed execution would need leases, durable execution state, and another
  ADR.
