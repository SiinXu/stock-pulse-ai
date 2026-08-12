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
| `PREDICTION_RESOLVE_MAX_ATTEMPTS` | `5` | Attempt counter for diagnostics |

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

Exit codes: `0` ok (including empty/overlap), `1` deps missing, `2` unexpected failure.

## Overlap protection and retry

- Process-local non-blocking lock skips concurrent ticks.
- Store leases + conditional resolve prevent cross-process double-scoring.
- **Expired `resolving` leases are re-scanned** on the next tick (crash recovery).
- `data_unavailable` uses bounded exponential backoff (`next_attempt_at` in outcome) and stops after `PREDICTION_RESOLVE_MAX_ATTEMPTS` (`retry_exhausted`).
- Retry metadata is durable in the A3 outcome. Each tick requeues only retryable rows whose `next_attempt_at` has elapsed; halted/delisted and exhausted rows remain `data_unavailable`.
- The actuals window starts at the prediction's canonical `as_of` field. A final-session high/low is never treated as the full-window path extreme.

## Scope boundaries (this PR)

Implemented here:

- `PredictionResolver.tick` orchestration, scheduler wiring, CLI entrypoint
- Process lock, lease reclaim, attempt ceiling, basic backoff
- `max_per_tick` as the per-tick claim cap

**Not** in this PR (later epic children):

- Parallel batch coalesce / global multi-worker rate-limit pools (#1104)
- Prediction query / diagnostics HTTP API (outcomes are on the store row + logs)
- Trading-calendar `resolve_after` policy (#1109)
- Post-mortem / adapter wiring (#1103 / #1106)


## Related

- Epic #1107, daily-brief background-task pattern, scheduled tasks docs.
