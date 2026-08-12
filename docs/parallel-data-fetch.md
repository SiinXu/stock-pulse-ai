# Parallel Dependency-Free Data Pulls

Issue #1126 adds an optional coordinator for **dependency-free** market-input
pulls inside a single stock analysis. Chinese operators can read this English
topic doc; configuration keys are bilingual in Settings help.

## What runs in parallel

Inside `analyze_stock`, these capability pulls do not depend on each other:

| Merge key | Provider key | Call site |
| --- | --- | --- |
| `realtime_quote` | `realtime` | `DataFetcherManager.get_realtime_quote` |
| `chip_distribution` | `chip` | `DataFetcherManager.get_chip_distribution` |
| `money_flow` | `money_flow` | `DataFetcherManager.get_money_flow` (only when SmartMoney is enabled) |
| `fundamental_context` | `fundamental` | `DataFetcherManager.get_fundamental_context` |

Trend analysis still runs **after** this wave because it may augment history
with the realtime quote. News / intelligence stages keep their existing order
relative to the fetch stage.

## Guardrails

| Control | Env | Default | Behavior |
| --- | --- | --- | --- |
| Enable | `ANALYSIS_PARALLEL_FETCH_ENABLED` | `true` | `false` forces serial declaration-order execution on the caller thread |
| Global cap | `ANALYSIS_PARALLEL_FETCH_MAX_CONCURRENT` | `3` | Max in-flight branches in one wave |
| Per-provider cap | `ANALYSIS_PARALLEL_FETCH_PER_PROVIDER_LIMIT` | `1` | Max in-flight branches sharing the same logical `provider_key` |
| Total budget | `ANALYSIS_PARALLEL_FETCH_BUDGET_SECONDS` | `0` | `0` disables coordinator budget; unstarted branches become `budget_skipped` |

Hard rule: parallelism **must not** open a side-channel around provider
governance. Every branch still uses the manager (fallback chain, process
cache, circuit breaker, validation, and each fetcher’s own rate limiter).

## Deterministic merge order

Results are always an ordered map following **task declaration order**, never
completion order:

1. `realtime_quote`
2. `chip_distribution`
3. `money_flow` (when present)
4. `fundamental_context`

Downstream stage IO and AgentContext seeding should iterate that order (or the
declared key list). Parallel and serial modes share this contract so
enable/disable does not reorder merged context keys.

## Failure isolation

Each branch returns a typed status:

| Status | Meaning |
| --- | --- |
| `ok` | Non-null value |
| `gap` | Branch returned no data (optional absence) |
| `error` | Exception isolated to the branch |
| `timeout` | Message classified as timeout |
| `budget_skipped` | Wave budget elapsed before the branch started |
| `skipped` | Placeholder before execution (should not remain after a finished wave) |

A failed or empty branch does **not** cancel siblings. Pipeline degradation
continues to use existing `fetch_degraded` / failed-fundamental context rules.

## ActualsFetcher compatibility

Prediction scoring (`ActualsFetcher`, issue #1110) keeps its own short-TTL
cache and in-flight coalesce for the same symbol/as-of key. This coordinator
only fans out **distinct** dependency-free capabilities; overlapping actuals
pulls should still go through the provider manager / ActualsFetcher path, not
a second raw HTTP client.

## Implementation map

| Piece | Path |
| --- | --- |
| Coordinator | `src/services/parallel_data_fetch.py` |
| Pipeline wiring | `src/core/stages/analysis_stock.py` (`_fetch_dependency_free_market_inputs`) |
| Config model | `analysis_parallel_fetch_*` on `Config` |
| Offline tests | `tests/services/test_parallel_data_fetch.py` |

## Rollback

Set `ANALYSIS_PARALLEL_FETCH_ENABLED=false` (or remove the feature flags and
rely on defaults after revert). Serial mode preserves the same call sites and
merge keys.
