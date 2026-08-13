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

## Remaining epic boundaries

- Prediction query / diagnostics HTTP API (outcomes are on the store row + logs)
- Trading-calendar `resolve_after` policy (#1109)
- Postmortem lesson writer and adapter wiring (#1103 / #1106); this resolver provides only the bounded queue boundary


## Related

- Epic #1107, daily-brief background-task pattern, scheduled tasks docs.
