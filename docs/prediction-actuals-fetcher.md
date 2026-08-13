# Prediction ActualsFetcher

- Status: `Living`
- Issue: [#1110](https://github.com/SiinXu/stock-pulse-ai/issues/1110)
- Epic: [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)
- Owner modules:
  - `src/services/actuals_fetcher.py`
  - `src/schemas/prediction_actuals.py`
  - `tests/services/test_actuals_fetcher.py`

## Purpose

Horizon resolution for agent prediction scoring must pull **real** market OHLC
(and optional volume / return) through the server `data_provider` path. This
service is the single actuals boundary for the forecast track:

- Callers: `PredictionResolver` / Claim scoring (downstream of this PR)
- Non-callers: free-form Agent tools must not invent prices for verification

## Contract

### Input

| Field | Meaning |
| --- | --- |
| `symbol` | Stock / instrument code |
| `market` | Optional market hint (`cn` / `hk` / `us` / …); inferred when omitted |
| `as_of` | Anchor trade date (inclusive) |
| `end` | Optional window end (defaults to `as_of`) |
| `field_set` | Projection: `ohlc`, `return`, `volume` (default all three) |

### Output (`ActualsSnapshot`)

| Status | Scoreable? | Meaning |
| --- | --- | --- |
| `ok` | yes | Finite projected fields from provider data |
| `empty` | no | Empty frame or no bar on/before `as_of` |
| `halted` | no | Conservative zero-volume flat session heuristic |
| `delisted` | no | Explicit delisting marker only (never guessed from gaps) |
| `provider_down` | no | Provider chain exhausted / circuit / source unavailable |
| `data_unavailable` | no | Timeout, local-missing, non-finite reject, invalid input |

All non-`ok` statuses set `data_unavailable=True` and leave price fields unset
(except diagnostic OHLC on `halted`; even then `return_pct=None`). **Never** fabricates a hit-friendly price
on failure.

`retryable=True` for provider / timeout / unexpected failures so the resolver
can back off and try again on a later tick.

For a forward window (`end > as_of`), `ok` requires a real bar dated exactly
`end`. A stale earlier bar is never substituted as a zero-return horizon
actual. A missing end bar is `data_unavailable/no_bar_for_end` and retryable;
an end date later than the fetcher's current UTC date is
`data_unavailable/end_not_reached` without a provider call. A halted end bar is
non-scoreable rather than a sideways return.

Requested projections are complete-or-unavailable: `ohlc` requires complete,
positive and internally consistent OHLC bars; `volume` requires finite,
non-negative values; all returned numerics must be finite. The snapshot domain
type independently rejects price bars/returns on provider-failure statuses.

### Cache and coalesce

Cache key:

```text
actuals:{market}:{symbol}:{as_of}:{end}:{sorted_field_set}
```

- Process-local short TTL (default 60s)
- In-flight futures merge concurrent identical keys
- `fetch_many` unique-s by cache key before the provider pass and isolates malformed requests so one bad symbol/window does not abort its neighbors

All typed results, including retryable failures, use the short TTL. For failures
this TTL is a retry cooldown: the shared timeout helper returns promptly but
cannot kill its provider worker, so immediate retries would create overlapping
calls. After TTL expiry the next tick can re-attempt.

## Governance boundaries

| Must | Must not |
| --- | --- |
| Call `DataFetcherManager.get_daily_data` | Bypass manager with ad-hoc HTTP |
| Inherit provider fallback / circuit / validation | Fabricate OHLC on failure |
| Bound outer timeout via `call_with_timeout` | Mark hit/miss itself (ClaimScorer owns scoring) |
| Reject non-finite numerics | Mutate Agent Soul / ToolSurface |

## Usage

```python
from src.services.actuals_fetcher import ActualsFetcher

fetcher = ActualsFetcher()
snap = fetcher.fetch(
    symbol="600519",
    market="cn",
    as_of="2026-04-10",
    end="2026-04-13",
)
if snap.ok:
    print(snap.return_pct, snap.as_of_bar, snap.end_bar)
elif snap.data_unavailable:
    # resolver: record data_unavailable / schedule retry — do not score hit
    print(snap.status, snap.reason, snap.retryable)
```

Batch / tick coalesce:

```python
results = fetcher.fetch_many(
    [
        {"symbol": "600519", "market": "cn", "as_of": "2026-04-10"},
        {"symbol": "600519", "market": "cn", "as_of": "2026-04-10"},
        {"symbol": "AAPL", "market": "us", "as_of": "2026-04-10"},
    ]
)
# identical keys share one provider call within the process
```

## Tests

```bash
python -m pytest tests/services/test_actuals_fetcher.py -q
```

Mandatory counterexamples:

1. Provider raises `DataFetchError` → `provider_down`, all prices `None`
2. Same key twice (or concurrent) → one `get_daily_data` call
3. Non-finite close → `data_unavailable` / `non_finite_values`, not `ok`
4. Missing horizon-end bar / halted end session → non-scoreable, never stale `0%`
5. Real `DataFetcherManager` fallback reaches the backup provider
6. Timeout/retry cooldown starts only one provider call inside the TTL

## Rollback

Remove or stop calling `ActualsFetcher`; no schema migration or config flag is
required for this slice. Downstream resolvers should treat missing actuals as
`data_unavailable` regardless.
