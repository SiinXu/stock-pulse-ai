# Agent prediction batch resolution (queues, leases, backpressure)

Research / quality-ops path for **structured forecast verification** under bulk load. This document covers Issue **#1104** (A8 of Epic **#1107**): how due predictions are claimed, coalesced, scored, and retried without double-scoring or provider stampedes.

This is **not** a returns guarantee. It never mutates Agent Soul charters or ToolSurface denials. Non-parseable prose must not enter this pipeline as a fake claim (owned by #1101 / #1108). Provider failure is always `data_unavailable` + retry — never a fabricated hit.

Chinese mirror: deferred until the epic localization pass (EN is the source of truth for this new subsystem).

## Status on main

Until A1–A7 land durable `PredictionRecord` storage, ActualsFetcher, ClaimScorer, and scheduler wiring, this package ships:

| Piece | Module | Role |
| --- | --- | --- |
| Work-item port | `src/services/prediction_resolution/contracts.py` | Minimal row + Protocols for store / fetch / score / post-mortem |
| Config caps | `src/services/prediction_resolution/config.py` | Env-backed concurrency and backpressure |
| Lease store | `src/services/prediction_resolution/lease_store.py` | In-memory exclusive claim (test + single-process) |
| Coalesce | `src/services/prediction_resolution/coalesce.py` | Group by `(symbol, market, as_of_date)` |
| Batch resolver | `src/services/prediction_resolution/batch_resolver.py` | One tick: claim → group → fetch → score → post-mortem budget |
| Metrics | `src/services/prediction_resolution/metrics.py` | due lag, queue depths, fetch/score counters |
| Post-mortem queue | `src/services/prediction_resolution/postmortem_queue.py` | Bounded in-process miss queue |

A durable SQL store (A3) should implement the same `PredictionWorkStore` port with `FOR UPDATE SKIP LOCKED` (or equivalent). Claim / complete semantics must stay identical so multi-worker deployments keep the single-score invariant.

Lease design reuses the crash-consistency idea from `AnalysisTaskQueue` claim + inflight checkpoint (`src/services/task_queue.py`): processing ownership is established before side effects; terminal outcomes clear ownership.

## Tick shape

```text
due_batch = claim_due(limit=K)                 # status → resolving + lease
group by (symbol, market, as_of_date)
fetch_actuals_once_per_group                   # fetch pool concurrency cap
score_all_predictions_in_group                 # complete only if lease held
enqueue_postmortem(misses_only)                # separate smaller budget
```

### Lease claim (anti double-score)

1. **Claim** transitions an eligible row to `resolving` under `(lease_owner, lease_expires_at)` **before** scoring side effects.
2. Only the lease owner may `complete_resolved` or `release_for_retry` / `mark_error`.
3. A second `complete_resolved` on an already `resolved` row returns `false` and must not increment `score_count`.
4. Expired leases are reclaimable by another worker; the previous owner’s complete is rejected.

Hard invariant: **under concurrency, the same prediction is never scored twice** (`score_count == 1` after resolve).

### Coalesce

Multiple due predictions that share the same symbol / market / as-of date produce **one** ActualsFetcher call per tick group. Coalesce savings are recorded as `fetch_coalesced_saved`.

### Backpressure

- `PREDICTION_RESOLVE_MAX_PER_TICK` caps claims per tick; excess due rows stay pending for later ticks.
- Provider error circuit: after `PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_THRESHOLD` fetch failures in the window, the next ticks claim at most `PREDICTION_RESOLVE_CIRCUIT_OPEN_MAX_PER_TICK` until cooldown elapses.
- Post-mortem enqueues are capped by `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` so large miss batches cannot unbounded-parallel LLM work.

### Retry

On `DataUnavailable` (or scorer `data_unavailable`):

- Release lease to operational status `data_unavailable_retry` with `next_attempt_at` from exponential backoff (`base * 2^(attempt-1)`, optional jitter, max cap).
- After `PREDICTION_RESOLVE_MAX_ATTEMPTS`, mark `error` — still **no** fabricated hit/miss.

A1 contract statuses (`pending` / `resolving` / `resolved` / `expired` / `error`) remain the durable vocabulary; `data_unavailable_retry` is the batch-layer operational wait state between attempts.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `PREDICTION_RESOLVE_ENABLED` | `false` | Scheduler gate (A7); batch API remains callable when injected |
| `PREDICTION_RESOLVE_MAX_PER_TICK` | `50` | Claim backpressure per tick |
| `PREDICTION_RESOLVE_FETCH_CONCURRENCY` | `4` | Parallel actuals groups |
| `PREDICTION_RESOLVE_POSTMORTEM_CONCURRENCY` | `1` | Documented LLM pool size (drain side) |
| `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` | `10` | Miss enqueue budget per tick |
| `PREDICTION_RESOLVE_LEASE_SECONDS` | `120` | Resolving lease TTL |
| `PREDICTION_RESOLVE_MAX_ATTEMPTS` | `5` | Bound for data_unavailable retries |
| `PREDICTION_RESOLVE_RETRY_BASE_SECONDS` | `30` | Backoff base |
| `PREDICTION_RESOLVE_RETRY_MAX_SECONDS` | `3600` | Backoff cap |
| `PREDICTION_RESOLVE_RETRY_JITTER_RATIO` | `0.1` | Extra delay fraction |
| `PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_THRESHOLD` | `5` | Errors before circuit open |
| `PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_COOLDOWN_SECONDS` | `60` | Circuit open duration |
| `PREDICTION_RESOLVE_CIRCUIT_OPEN_MAX_PER_TICK` | `5` | Shrink claim size while open |

Feature-flag registry ownership for the broader verification loop remains with Issue **#1115**.

## Observability

`PredictionResolveMetrics.snapshot()` exposes process-local counters:

- `last_due_count`, `last_due_lag_seconds` (oldest unresolved due)
- `last_queue_depths` (status histogram from the store)
- `last_postmortem_queue_depth`
- `fetch_calls`, `fetch_errors`, `fetch_coalesced_saved`
- `resolved`, `retried`, `errors`, `score_rejected_stale_lease`
- `deferred_by_backpressure`, `circuit_open_ticks`

Richer diagnostics panels are Issue **#1114**.

## Product rules (Epic #1107)

- System-driven: scheduler / background tick, not a user “verify” click.
- No runtime mutation of Agent Soul or ToolSurface denials.
- Research / quality-ops framing only.
- Unstructured prose is not a verifiable claim.
- Provider failure → `data_unavailable` / retry, never forged hit.

## Tests

```bash
python -m pytest tests/services/test_prediction_batch_resolver.py -q
```

Coverage includes concurrent multi-worker claim exclusivity, concurrent resolve of 100 synthetic due rows with `score_count == 1`, coalesced fetch counts, `max_per_tick` backpressure, provider failure retry without scorer invocation, post-mortem per-tick cap, and circuit breaker claim shrink.

## Related issues

- #1107 Epic — prediction verification & automatic evolution
- #1101 Prediction contracts
- #1102 Horizon resolver orchestration
- #1103 Post-mortem lessons
- #1104 **This document** — batch / parallel / leases
- #1110 ActualsFetcher
- #1111 ClaimScorer
- #1114 Observability
- #1115 Feature flags / config registry
