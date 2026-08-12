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
(except diagnostic OHLC on `halted`). **Never** fabricates a hit-friendly price
on failure.

`retryable=True` for provider / timeout / unexpected failures so the resolver
can back off and try again on a later tick.

### Cache and coalesce

Cache key:

```text
actuals:{market}:{symbol}:{as_of}:{end}:{sorted_field_set}
```

- Process-local short TTL (default 60s)
- In-flight futures merge concurrent identical keys
- `fetch_many` unique-s by cache key before the provider pass

Retryable failures are **not** cached so the next tick can re-attempt.

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

## Rollback

Remove or stop calling `ActualsFetcher`; no schema migration or config flag is
required for this slice. Downstream resolvers should treat missing actuals as
`data_unavailable` regardless.
