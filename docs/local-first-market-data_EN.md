# Local-first daily market data

`DataFetcherManager.get_daily_data` is the runtime owner of the local-first
daily-data contract. It reuses the existing provider routing, priority,
plugin, health/circuit, diagnostics, and fallback behavior; the cache does not
introduce a second provider path.

This feature is separate from `LOCAL_ONLY_MODE` in
`docs/local-only-mode_EN.md`. `PROVIDER_MARKET_DATA_MODE` governs daily bars;
`LOCAL_ONLY_MODE` is the process-wide non-loopback HTTP policy. Enable both
when the complete process must be offline.

In `local_only`, the analysis pipeline also skips batch daily/realtime
prefetch and provider-backed stock-name decoration. Existing in-memory names,
static index names, and the local daily store remain available. This prevents
five-or-more-symbol batches from reaching a provider before the per-symbol
local resolver runs; it does not replace `LOCAL_ONLY_MODE` for unrelated
outbound features such as news, LLMs, or notifications.

## Modes

| `PROVIDER_MARKET_DATA_MODE` | Local read | Provider chain | Provider failure |
| --- | --- | --- | --- |
| `auto` (default) | Use a complete, fresh range | Once on miss, incomplete range/fields, or expiry | Return one complete stale candidate only while `PERSISTENT_TTL + STALE_IF_ERROR` remains valid; otherwise raise `DataFetchError` |
| `local_only` | Use a complete range within `LOCAL_ONLY_MAX_AGE` | Never constructed or called | Raise `LocalDataMissingError`; no provider availability callback or socket path is entered |
| `refresh` | Skipped | Exactly once | Raise the provider-chain error; never fall back to stale data |

Unset mode keeps the compatible `auto` default. Any non-empty value other than
`auto`, `local_only`, or `refresh` stops configuration loading with an
actionable `ValueError`; an offline typo can never become network-capable.

## Range and field coverage

The persistent identity is normalized symbol + adjustment identity + schema
identity. When TickFlow is active, its configured K-line adjustment is part of
that identity, so forward-, backward-, and unadjusted bars cannot reuse one
another across process restarts. Other providers use `provider_default`. The
persisted source name is part of the entry contract, and ranges from different
sources are never merged. The `days` hint is not storage identity: exact,
overlapping, and subset windows reuse one symbol table.

Successful requests record covered date intervals. Local reads verify that the
requested interval is covered, verify the requested columns, then sort,
deduplicate, and slice by date. A one-day rollover grace lets a warmed default
end date serve the following calendar day's overlapping window; the normal
freshness TTL still causes online `auto` to revalidate aged data.

Partial policy:

- `local_only` fails with only the missing columns and bounded missing ranges.
- `auto` calls the existing provider chain once for the full requested window,
  then merges a successful same-source result into the symbol table.
- `refresh` replaces or same-source-merges the successful requested window.

Example error payload:

```json
{
  "symbol": "600519",
  "start_date": "2026-07-01",
  "end_date": "2026-07-20",
  "days": 30,
  "fields": ["volume"],
  "missing_ranges": [
    {"start_date": "2026-07-01", "end_date": "2026-07-09"}
  ],
  "mode": "local_only",
  "reason": "missing_fields_and_ranges",
  "available_start_date": "2026-07-10",
  "available_end_date": "2026-07-20",
  "age_seconds": 12
}
```

Possible reasons include `cache_disabled`, `no_local_entry`,
`missing_fields`, `missing_ranges`, `missing_fields_and_ranges`,
`no_rows_in_covered_window`, and `local_entry_too_old`.

The typed error reaches the stock-history API as HTTP 409 with
`error=local_market_data_missing` and the payload in `details`. The analysis
endpoint declares this structured variant alongside duplicate-task HTTP 409
responses in OpenAPI. Synchronous and queued analysis expose the same stable
code/details, including after asynchronous task terminalization. Any missed
symbol makes either the embedded or standalone scheduled CLI path fail before
analysis notifications are assembled.

## Persistence, privacy, and retention

Schema v2 stores JSON records using an explicit allowlist:

`date`, `code`, `open`, `high`, `low`, `close`, `volume`, `amount`,
`pct_chg`, `ma5`, `ma10`, `ma20`, `volume_ratio`.

Unexpected columns are stripped before returning the persisted provider result
or writing disk. Configuration values, tokens, headers, URLs, and exception
text have no schema location and are never serialized. Writes use a temporary
file, `fsync`, and atomic replacement; same-manager concurrent callers share a
per-identity request guard so one warm-up performs one provider chain.

| Setting | Default | Policy |
| --- | ---: | --- |
| `PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS` | `7776000` (90 days) | Delete older files during lookup/write |
| `PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES` | `512` | Delete oldest entries first, with filename as deterministic tie-breaker |
| `PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS` | `2592000` (30 days) | A complete older entry is a structured offline miss |
| `PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS` | `1` | Calendar-day end rollover allowed for an otherwise covered range |

The existing memory/persistent TTL and stale-if-error settings keep their
freshness meanings. The cache directory remains
`data/provider_cache/daily` unless `PROVIDER_DAILY_CACHE_DIR` is set.

### Schema-v1 compatibility

Existing exact-request schema-v1 JSON tables are read as `provider_default` /
`normalized_daily_v1` coverage ranges, allowlisted on read, and can satisfy
matching/subset requests. When multiple compatible legacy files overlap, their
`stored_at` timestamps control merge order and the newest observation wins;
filenames only break equal-timestamp ties. Other adjustment/schema identities,
including active TickFlow adjustment identities, ignore legacy entries. The
next successful same-source write creates the schema-v2 symbol table.
Unsupported, corrupt, identity-mismatched, or incomplete entries never count
as hits.

Rollback is either reverting this change or unsetting/setting
`PROVIDER_MARKET_DATA_MODE=auto`. Reverting does not delete cache files;
schema-v1 readers ignore schema-v2 files, so operators may remove the configured
cache directory separately if reclaiming the footprint is desired.

## Verification

```bash
python -m pytest \
  tests/data_provider/test_local_first_manager.py \
  tests/data_provider/test_daily_provider_cache.py \
  tests/data_provider/test_local_first_store.py \
  tests/services/test_local_first_boundaries.py \
  tests/app/test_main_schedule_mode.py \
  tests/test_analysis_api_contract.py \
  -m "not network"
```

The manager suite asserts provider and socket call counts, persistence across
restart, concurrent callers, overlap/rollover/partial coverage, stale expiry,
refresh failure policy, schema-v1 reads, retention, corrupt entries, and
secret-shaped column stripping.
