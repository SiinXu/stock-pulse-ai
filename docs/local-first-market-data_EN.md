# Local-first market data store

This document describes the **market-data** local-first modes built on the
existing layered daily cache (`data_provider/daily_cache.py`).

It is **not** the same switch as privacy egress mode (`LOCAL_ONLY_MODE` in
`docs/local-only-mode_EN.md`), which blocks non-loopback HTTP at the outbound
policy layer. Operators who need both offline bars and no cloud LLM should set
both knobs intentionally.

## Storage choice

| Choice | Reason |
| --- | --- |
| Reuse L1 process memory + L2 atomic JSON tables under `PROVIDER_DAILY_CACHE_DIR` | Already shipped for provider-manager daily cache; no new DB or package dependency |
| No SQLite/Redis introduction | Keeps desktop and zero-config installs lightweight and consistent with the existing cache layout |

Secrets never belong in this store: entries are OHLCV-style frames plus source name and timestamps only.

## Three modes (`PROVIDER_MARKET_DATA_MODE`)

| Mode | Value | Behavior |
| --- | --- | --- |
| Auto (default) | `auto` | Prefer **fresh** local data; on miss, upstream fetch is allowed and successful results update the local store. Equivalent to historical cache-as-accelerator behavior. |
| Local only | `local_only` | Use **only** the local store (including aged entries). On miss, raise `LocalDataMissingError` with a structured payload. **Never** invokes the network fetch callback. |
| Refresh | `refresh` | Always call upstream, then write the local store. Does not return a cache-only hit. |

Unset or invalid values resolve to `auto` so existing deployments keep working without configuration.

```env
# Default — no behavior change for current users
# PROVIDER_MARKET_DATA_MODE=auto

# Offline / privacy data path: serve bars only from local store
# PROVIDER_MARKET_DATA_MODE=local_only

# Force re-download and repopulate the local store
# PROVIDER_MARKET_DATA_MODE=refresh
```

TTL knobs (`PROVIDER_DAILY_CACHE_*`) still control **freshness** for `auto` and
stale-if-error fallback. In `local_only`, presence in the local store is enough
to serve data; `is_stale` on the result reflects age past the persistent TTL so
callers can show honesty about freshness without going online.

## Structured missing payload (`local_only`)

When local data cannot satisfy a request:

```json
{
  "symbol": "AAPL",
  "start_date": "2026-06-01",
  "end_date": "2026-07-01",
  "days": 20,
  "fields": ["daily_ohlcv", "volume"],
  "mode": "local_only",
  "reason": "no_local_entry"
}
```

| Field | Meaning |
| --- | --- |
| `symbol` | Normalized request symbol |
| `start_date` / `end_date` / `days` | Requested window (empty strings when not provided) |
| `fields` | Which logical datasets were required (default `daily_ohlcv`) |
| `mode` | Always `local_only` for this error path |
| `reason` | `no_local_entry` or `cache_disabled` |

Python exception: `data_provider.daily_cache.LocalDataMissingError` with
`.missing` / `.to_dict()`.

## Public API (data layer)

```python
from data_provider.daily_cache import (
    DailyCacheKey,
    DailyDataCache,
    LocalDataMissingError,
    MarketDataFetchMode,
)

cache = DailyDataCache.from_env()
key = DailyCacheKey(symbol="600519", start_date="", end_date="", days=30)

try:
    result = cache.resolve(
        key,
        network_fetch=lambda: upstream_get_daily(key),  # never called in local_only
        required_fields=("daily_ohlcv",),
    )
except LocalDataMissingError as exc:
    print(exc.to_dict())
```

Helpers:

- `lookup` / `store` / `use_stale` — unchanged accelerator contracts used by the manager today
- `lookup_local_store` — any local entry regardless of fresh TTL
- `resolve` — mode-aware orchestration for local-first workflows

## Integration with `DataFetcherManager`

This release delivers the store, modes, errors, tests, and configuration on
`daily_cache.py` (ownership for the parallel batch). Wiring into
`DataFetcherManager.get_daily_data` is a short post-merge integration:

1. After building `cache_key` / `daily_cache`, call `daily_cache.resolve(...)`
   with `network_fetch` wrapping the existing provider loop, **or**
2. Branch on `daily_cache.fetch_mode`:
   - `local_only` → `lookup_local_store` / raise `LocalDataMissingError`
   - `refresh` → skip fresh hit, always provider loop, then `store`
   - `auto` → keep the current lookup → provider → store / stale path

Until that wiring lands, setting `PROVIDER_MARKET_DATA_MODE` alone does not
change `get_daily_data` runtime paths; callers and tests can already use
`DailyDataCache.resolve` directly.

## Relation to `LOCAL_ONLY_MODE` (egress privacy)

| Knob | Layer | Effect |
| --- | --- | --- |
| `PROVIDER_MARKET_DATA_MODE=local_only` | Market data store | No upstream bar fetch via `resolve`; structured local miss |
| `LOCAL_ONLY_MODE=true` | Outbound HTTP policy | Blocks non-loopback destinations for all `safe_*` HTTP |

Use both for a full privacy offline profile (local bars + no cloud LLM/search).

## Remaining scope (not in this change)

- LLM / Ollama local model preference (see issue #159 remainder / T28)
- Web UI cache status badges
- Prefetch / cache warming from watchlists
- Changes to individual provider fetchers

## Verification

```bash
python -m pytest tests/data_provider/test_local_first_store.py tests/data_provider/test_daily_provider_cache.py -m "not network"
```

`local_only` tests assert the network callback is never invoked and additionally
block `socket.socket` construction on the miss path.
