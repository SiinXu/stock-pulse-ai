# ADR-004: Use One Process-Local Task Execution Authority

- Status: `Accepted (retrospective)`
- Decision date: 2026-07-20
- Recorded: 2026-07-21
- Decision owners: StockPulse maintainers
- References: [PR #90](https://github.com/SiinXu/stock-pulse-ai/pull/90), [PR #99](https://github.com/SiinXu/stock-pulse-ai/pull/99), [PR #103](https://github.com/SiinXu/stock-pulse-ai/pull/103), [`docs/task-execution-contract.md`](../task-execution-contract.md)

## Context

Task behavior had grown across the legacy `AnalysisTaskQueue` API, separate SSE
subscriber plumbing, delivery-layer status types, and a Bot-only `TaskService`.
Cancellation, retry, shutdown, idempotency, deduplication, and slow-consumer
behavior therefore did not share one application contract.

The deployed model was still one Python process using a `ThreadPoolExecutor`.
The work did not establish an external broker, durable task store, scheduler, or
multi-worker coordination mechanism.

## Decision

`src.task_execution` defines the application-neutral `TaskExecutionPort` and its
immutable command, snapshot, event, and stream values. `AnalysisTaskQueue` is the
single process-local adapter and lifecycle authority.

API, Web, Portfolio, AlphaSift, and Bot adapters may project that authority into
their existing payloads, but they must not define another lifecycle or task
status enum. The Bot `/analyze` path uses the same queue, task ID, normalized
stock dedupe key, error categories, and terminal state rules. The unused
parallel `TaskService` was removed rather than retained as a dead facade.

The authority keeps these boundaries:

- terminal state is first-wins, including cancellation and graceful interruption;
- idempotency identity and in-flight deduplication are separate concepts;
- event streams are bounded and tied to their owning event loop;
- shutdown marks active work `interrupted`, but runner cancellation remains
  cooperative;
- the queue is process-local and in-memory, not durable or multi-process.

The living [task execution contract](../task-execution-contract.md) remains
authoritative for transitions, retry reservations, SSE compatibility, overflow,
and shutdown mechanics.

## Consequences

- Delivery surfaces share one status and error vocabulary instead of drifting.
- Duplicate work, retry identity, cancellation races, and late completion are
  governed under one lock-protected lifecycle.
- Legacy polling and SSE names remain compatibility projections.
- One deployment process owns one in-memory authority. Multi-worker deployments
  would create divergent state and require a new ADR and implementation.
- There is no durable recovery after process loss; graceful shutdown can only
  classify known active work as `interrupted`.
