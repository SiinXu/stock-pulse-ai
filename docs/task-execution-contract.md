# Task Execution Contract

## Purpose

`src.task_execution` is the application-neutral contract for process-local task
execution. `AnalysisTaskQueue` is its current adapter. The adapter keeps the
existing single-process `ThreadPoolExecutor` deployment model; this contract does
not introduce an external queue, scheduler, worker service, or persistence layer.

API and other delivery adapters may project these types into their existing
payloads, but they must not define a second lifecycle or status enum.

## Port

```text
TaskExecutionPort
  submit(command) -> task_id
  get(task_id) -> TaskSnapshot
  cancel(task_id) -> TaskSnapshot
  retry(task_id) -> task_id
  subscribe(task_id) -> TaskEventStream
  subscribe_all() -> TaskEventStream
```

`TaskCommand`, `TaskSnapshot`, and `TaskEvent` are immutable, detached values.
Nested mappings and collections are deeply frozen at the contract boundary.
Mutable values returned through legacy `TaskInfo` accessors are deep copies.

`TaskSnapshot` contains only neutral lifecycle fields:

```text
id / kind / status / progress / result_ref / error_code /
trace_id / created_at / updated_at
```

The queue retains the existing rich `TaskInfo` object as a compatibility
projection for polling, Portfolio, AlphaSift, and other current callers.

## Lifecycle

The canonical enum order and wire values are:

```text
pending
processing
cancel_requested
completed
failed
cancelled
interrupted
```

Allowed transitions are:

| From | To | Meaning |
| --- | --- | --- |
| `pending` | `processing` | A worker atomically claims the command. |
| `pending` | `cancel_requested` | Cancellation wins before the worker claim. |
| `processing` | `cancel_requested` | The runner has been asked to stop cooperatively. |
| `pending` / `processing` / `cancel_requested` | `interrupted` | Queue shutdown fences process-local work. |
| `processing` | `completed` / `failed` | The runner result wins the lifecycle lock. |
| `cancel_requested` | `cancelled` | Cancellation won before a competing result. |

`completed`, `failed`, `cancelled`, and `interrupted` are terminal. The first
terminal transition under the queue lifecycle lock wins. A completion or failure
that arrives after `cancel_requested` resolves to `cancelled`; late progress and
run-flow events are rejected. Each task records and publishes at most one terminal
event.

A pending command cancelled before execution never invokes its runner. Runners can
poll `TaskRunContext.is_cancel_requested()`; it also returns true after
`cancelled` or `interrupted` so a late-running callable observes the stop fence.

## Results And Errors

Generic `TaskCommand` runners may return `None` successfully. Existing stock
analysis and legacy background wrappers retain their historical requirement that
`None` means failure by setting `none_is_success=False`.

When a mapping result contains `result_ref`, `query_id`, or `id`, the first present
value becomes `TaskSnapshot.result_ref`. Results are detached before the task is
made terminal; a result that cannot be copied fails the task rather than leaving a
partial `completed` state.

Public failure diagnostics use stable codes. Provider exception text remains in
the server-only diagnostic field and is sanitized before storage or logging.
`interrupted` snapshots expose `task_interrupted`; legacy HTTP/SSE payloads keep
their existing public fields and do not expose raw diagnostics.

Stable port errors include:

- `task_not_found`
- `task_idempotency_conflict`
- `task_retry_not_allowed`
- `task_retry_unsupported`
- `task_queue_shutdown`
- `task_stream_overflow`

## Idempotency, Dedupe, And Retry

`idempotency_key` identifies one submission request. Reusing a key with the same
fingerprint returns the existing task ID without publishing another event or
submitting another executor call. Reusing it with a different fingerprint raises
`TaskIdempotencyConflictError`.

`dedupe_key` is a separate in-flight ownership constraint. Stock-analysis wrappers
continue to use the canonical stock-code key, so equivalent code forms cannot run
concurrently. Batch staging, executor submission, events, idempotency ownership,
and dedupe ownership are rolled back together if any executor submission fails.

Only `failed`, `cancelled`, and `interrupted` tasks can be retried. A command must
provide an explicit `retry_factory`; legacy background callables are one-shot by
default. The factory runs outside the lifecycle lock. Concurrent callers share one
reservation and receive the same child task ID or the same failure category.

A retry gets a new task ID, trace ID, and idempotency key while retaining the
parent request fingerprint, metadata, kind, dedupe key, error policy, and retry
factory. An unrelated active dedupe owner still raises `DuplicateTaskError`.

## Event Streams

`subscribe(task_id)` atomically registers a task-scoped stream and enqueues a
`snapshot` event under the same lock. Unknown task IDs raise `TaskNotFoundError`.
A terminal snapshot is replayed once and then the stream reaches EOF.

`subscribe_all()` atomically registers a global stream and replays snapshots for
all active tasks. It is the adapter used by the existing `/tasks/stream` SSE route.

Every stream:

- belongs to the event loop that created it;
- owns a unique registration token and a bounded queue;
- remains open after a receive timeout;
- is weakly registered so an abandoned stream is not retained after its owning
  event loop closes, even when a caller omits `aclose()`;
- unregisters on `aclose()`, terminal task completion, overflow, a closed loop, or
  queue shutdown;
- preserves a task-scoped terminal event when that event encounters a full queue;
- reports global-stream overflow explicitly instead of presenting one task's
  terminal event as a normal end for the whole stream.

The legacy SSE adapter retains existing event names:

| Canonical event | Legacy SSE event |
| --- | --- |
| `created`, `snapshot` | `task_created` |
| `started` | `task_started` |
| `progress`, `cancel_requested` | `task_progress` |
| `completed` | `task_completed` |
| `failed`, `cancelled`, `interrupted` | `task_failed` |

The route continues to send `connected` and 30-second `heartbeat` events. Client
cancellation propagates after the stream is closed in `finally`.

## Process Boundary

The queue accepts work only while its process-local executor is active. Graceful
shutdown rejects new submissions and retries, marks every active task
`interrupted`, wakes retry waiters, closes event streams after queued terminal
events drain, cancels pending futures, and does not wait indefinitely for an
uncooperative runner.

This task does not add HTTP cancel/retry routes, an external broker, cross-process
task sharing, or durable recovery after an ungraceful process loss. Deployment
continues to require one Web process for a single task authority; broader startup
and Bot authority migration is handled separately.
