# Prediction Horizon Resolver

> 中文：[prediction-resolver.md](prediction-resolver.md)

Implements Issues [#1102](https://github.com/SiinXu/stock-pulse-ai/issues/1102) and [#1116](https://github.com/SiinXu/stock-pulse-ai/issues/1116) under Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107).

When `resolve_after` is reached, the **system** claims the prediction, pulls actuals through the server data path, scores claims deterministically, and writes the outcome. Users never need to press a verify button.

## Product rules

- System-driven via the **existing** process scheduler or external cron CLI — no second scheduler.
- Provider failure → `data_unavailable` / retry; **never** fabricate hit/miss.
- Does not mutate Agent Soul charter or ToolSurface denials.
- Research / quality-ops framing only.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `PREDICTION_RESOLVE_ENABLED` | `false` | Master switch |
| `PREDICTION_RESOLVE_INTERVAL_SECONDS` | `60` | Background poll interval (floor 30s) |
| `PREDICTION_RESOLVE_MAX_PER_TICK` | `50` | Max claims per tick |
| `PREDICTION_RESOLVE_LEASE_SECONDS` | `120` | Resolving lease TTL |
| `PREDICTION_RESOLVE_MAX_ATTEMPTS` | `5` | Hard attempt ceiling |
| `PREDICTION_RESOLVE_FETCH_CONCURRENCY` | `4` | Global actuals-fetch worker cap |
| `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` | `10` | Hand-off budget when a postmortem queue adapter is injected; otherwise no postmortem work runs |
| `PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_THRESHOLD` | `5` | Failed fetch groups in one tick before circuit open |
| `PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_COOLDOWN_SECONDS` | `60` | Open-circuit cooldown |
| `PREDICTION_RESOLVE_CIRCUIT_OPEN_MAX_PER_TICK` | `5` | Reduced claim cap while the circuit is open |
| `PREDICTION_RESOLVE_RETRY_JITTER_RATIO` | `0.1` | Positive retry jitter ratio (`0` to `1`) |

## Single-process deploy

1. Ensure A3 store (`agent_predictions`), A4 `ActualsFetcher`, and A5 `ClaimScorer` are available.
2. Set `PREDICTION_RESOLVE_ENABLED=true`.
3. Run `python main.py --schedule` or API/Web/Desktop serve with `RuntimeSchedulerService`.
4. Background task name: `prediction_resolver`.

## Multi-process / cron

Keep the flag off on app workers and run one job:

```bash
* * * * * cd /app && python -m src.services.prediction_resolver --json >> /var/log/prediction-resolver.log 2>&1
```

```bash
python -m src.services.prediction_resolver --limit 20 --worker-id cron-1 --json
```

`--limit` can only narrow `PREDICTION_RESOLVE_MAX_PER_TICK`; it cannot exceed or re-enable the configured hard cap.

Exit codes: `0` ok (including empty/overlap), `1` deps missing, `2` unexpected failure.

## Overlap protection and retry

- Process-local non-blocking lock skips concurrent ticks.
- Store leases + conditional writes prevent duplicate outcomes. Work may be retried after lease expiry, but only one outcome can be applied.
- **Expired `resolving` leases are re-scanned** on the next tick (crash recovery).
- `data_unavailable` uses bounded exponential backoff with positive jitter (`next_attempt_at` in outcome) and stops after `PREDICTION_RESOLVE_MAX_ATTEMPTS` (`retry_exhausted`).
- Retry metadata is durable in the A3 outcome. Each tick requeues only retryable rows whose `next_attempt_at` has elapsed; halted/delisted and exhausted rows remain `data_unavailable`.
- The actuals window starts at the prediction's canonical `as_of` field. A final-session high/low is never treated as the full-window path extreme.

## Bounded batch behavior

- Due work is capped by `PREDICTION_RESOLVE_MAX_PER_TICK`, so large backlogs drain across multiple ticks.
- Claimed rows are coalesced by `symbol`, `market`, prediction `as_of`, and horizon end. One actuals fetch serves every prediction in an identical window.
- Only actuals fetches run concurrently. Claim scoring and lease-token conditional write-back remain serial within a tick; the resolver never creates an unbounded scoring or LLM pool.
- Fetch concurrency is global because `ActualsFetcher` owns provider selection and fallback behind one port. Provider-specific throttling remains the fetcher's responsibility.
- A fetch-error spike opens a process-local circuit. During cooldown, subsequent ticks use the smaller open-circuit claim cap instead of amplifying a provider outage.
- Miss/partial outcomes can be handed to an injected bounded postmortem queue. The queue has its own explicitly capped drain pool; misses receive higher priority. No postmortem LLM call runs in the resolver path.
- Every tick summary/event includes backlog depth (bounded probe), oldest due lag, resolve rate, fetch calls/errors/coalescing, deferred count, circuit state, and postmortem queue depth.

## Diagnostics HTTP

Authenticated operators can inspect currently **claimable** due work without SQL:

```http
GET /api/v1/agent/prediction-resolver/diagnostics
```

Auth matches the optional prediction-feedback APIs: `AuthMiddleware` plus the admin session cookie. When `ADMIN_AUTH_ENABLED=true`, a missing or invalid cookie returns **401** `unauthorized` (not 403). The path is not auth-exempt.

The response is a constructed allowlist (`extra=forbid`):

| Field | Meaning |
| --- | --- |
| `enabled` | This API process's `PREDICTION_RESOLVE_ENABLED` |
| `interval_seconds` | Configured poll interval (floor 30s), even when this process is not the worker |
| `this_process_worker_registered` | Whether **this API process** registered the `prediction_resolver` background task. It is not global worker health. Default Compose `server` and documented cron leave this `false`. |
| `observed_at` | ISO-8601 UTC clock used as `as_of` for the due probe |
| `claimable_due_count` | Length of the same claimable-due probe the next tick uses, **without** requeue writes |
| `claimable_due_truncated` | `true` when the probe length reached its bound |
| `claimable_due_probe_limit` | Probe cap (`max(1000, max_per_tick + 1)`, hard ceiling 10000; store `list_due` still caps at 1000) |
| `oldest_due` | Up to 10 allowlisted rows, already oldest `resolve_after` first: `prediction_id`, `symbol`, `market`, `status` (`pending` or expired-lease `resolving`), `resolve_after`, `lag_seconds` |
| `claimable_due_lag_seconds` | Nested `extra=forbid` object: nearest-rank `p50` / `p95` / `max` lag seconds over **all** rows in this claimable-due probe (not only `oldest_due`). Each value is JSON `null` when `claimable_due_count` is 0 — lag is undefined on an empty queue, not zero. Quantiles are over the probe window; reuse `claimable_due_truncated`. Missing `resolve_after` uses the same rule as `oldest_due` (`0.0`). When count ≥ 1, `max` equals `oldest_due[0].lag_seconds`. |
| `resolved_utc_day_start` | Inclusive ISO-8601 UTC start of the civil UTC day that contains `observed_at` |
| `resolved_utc_day_end` | Exclusive ISO-8601 UTC end of that civil day (`[start, end)`) |
| `resolved_utc_day_counts` | Store-backed durable mix: `hit`, `miss`, `partial`, exhausted `unavailable`, and `unlabeled`. An empty day is all zeros. |

The GET is read-only. It never ticks, claims, requeues, starts, or constructs a resolver worker. If either the claimable-due probe or the UTC-day aggregate fails, the GET returns **503** and omits the due snapshot, the UTC-day fields, and the lag quantiles. It does not fake zeros. Disabled / empty / API-without-worker states return **200** with the fields above (counts may be non-zero if another worker, such as cron, already resolved rows; lag fields are `null` when due count is 0).

`hit` / `miss` / `partial` count `status=resolved` rows whose `resolved_at` is in the UTC day and whose `outcome_json.label` is that token. `unavailable` counts `status=data_unavailable` rows whose `updated_at` is in the window and `outcome_json.retry_exhausted` is true; retryable unavailable is **not** a result. `unlabeled` counts resolved rows in the window whose label is missing or not in `{hit,miss,partial}`. Counts use SQL `json_extract` only and never return outcome payloads, claims, notes, or prediction ids of resolved rows. The response does not include `today_resolve_counts` or process-local `last_tick`.

Claimable due is pending rows plus expired `resolving` leases. Ready `data_unavailable` retries are **not** counted until a tick requeues them, so `claimable_due_count` can be lower than the next tick's `due_before`. Growing `claimable_due_count` plus **zero** UTC-day results is a hint the worker is not completing; growing `unavailable` hints at provider or circuit issues; `hit+miss+partial` increasing while due shrinks is a hint the worker is making progress. This is still not a fused `stuck` boolean. Circuit-open, overlap-skip, and last-tick counters remain log-only.

## Remaining epic boundaries

- Prediction query list / get-by-id HTTP API (remaining #1102)
- Fetch-error recency HTTP, postmortem-queue depth HTTP, Prometheus / OTel, and a durable worker heartbeat
- Trading-calendar `resolve_after` policy (#1109)
- Adapter wiring / `adapter_updates_total` (#1106). Worker/CLI already drains the injected postmortem queue after a non-overlap tick (#1499); this HTTP surface still does not expose process-local queue depth.


## Related

- Epic #1107, daily-brief background-task pattern, scheduled tasks docs.
