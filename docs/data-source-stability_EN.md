# Data-source Priority, Health, and Degradation

This guide explains how StockPulse chooses market-data providers, changes order after observed failures, and degrades when live sources are unavailable. It is written for operators configuring local, Docker, CI, or long-running server deployments.

> Chinese version: [Data-source stability and failure handling](data-source-stability.md).

For model routing and LLM failures, see [LLM routing and degradation order](LLM_CONFIG_GUIDE_EN.md#routing-and-degradation-order). Configuration changes use the [transactional hot-reload and one-step rollback contract](LLM_CONFIG_GUIDE_EN.md#transactional-hot-reload-and-one-step-rollback).

## The Three Priority Systems

StockPulse has separate priority systems. Changing one does not silently rewrite the others.

| Path | Configuration authority | Ordering rule |
| --- | --- | --- |
| Non-U.S. daily bars and general provider fallback | Fetcher numeric `priority`, including `EFINANCE_PRIORITY`, `AKSHARE_PRIORITY`, `TICKFLOW_PRIORITY`, `PYTDX_PRIORITY`, `BAOSTOCK_PRIORITY`, `YFINANCE_PRIORITY`, and `LONGBRIDGE_PRIORITY` | Lower numeric values are attempted earlier after market and capability filtering. A successfully initialized Tushare provider is forced to priority `-1`, ahead of the default free-provider group. U.S. daily bars use the dedicated named routes below instead of numeric priority. |
| A-share realtime quotes | `REALTIME_SOURCE_PRIORITY` | Provider aliases are attempted from left to right. This list is independent of daily numeric priorities and daily adaptive ordering. |
| AlphaSift screening snapshots | `SNAPSHOT_SOURCE_PRIORITY` or its token-aware default | When no explicit value is set, Tushare is prepended only when `TUSHARE_TOKEN` is available; the remaining chain uses Sina, Efinance, AkShare EM, and EastMoney Datacenter. |

When `TUSHARE_TOKEN` is set and `REALTIME_SOURCE_PRIORITY` is not explicitly set, StockPulse prepends `tushare` to the default realtime list. An explicit list always wins.

## Daily-provider Decision Order

`DataFetcherManager.get_daily_data()` applies the following order:

1. Return a fresh process-memory or persistent daily-cache entry when one is available.
2. Normalize the symbol and determine its market.
3. Remove providers that do not declare support for that market or are unavailable for the requested capability.
4. Apply dedicated market routes. U.S. indexes prefer YFinance; configured Longbridge credentials can make Longbridge primary for U.S. stocks. Hong Kong daily bars remain in the filtered numeric-priority chain.
5. For non-U.S. routes, start from numeric static priority and apply bounded adaptive ordering only to eligible equal-priority peers.
6. Skip a provider whose per-market daily circuit is in cooldown, and try the next eligible provider after an exception, empty result, or unusable response.
7. After every eligible provider fails, use an eligible stale daily-cache entry. If no stale entry is eligible, raise the existing data-fetch error.

The default A-share group contains Efinance and Tencent at priority 0, AkShare at 1, the credential-gated TickFlow provider and always-initialized Pytdx provider at 2, Baostock at 3, and YFinance at 4. Tushare, TickFlow, Longbridge, Finnhub, and Alpha Vantage are instantiated only when their required credentials are configured; Pytdx does not require credentials. Treat numeric values as non-U.S. static boundaries, not a guarantee that every provider supports every symbol or data type.

## Market-aware Routes

| Market or feature | Primary behavior | Fallback and degradation |
| --- | --- | --- |
| A-share daily bars | A configured and initialized Tushare provider is preferred; otherwise the filtered numeric-priority chain is used | Continue through free providers, then use eligible stale daily cache |
| A-share realtime quote | Left-to-right `REALTIME_SOURCE_PRIORITY`; default is `tencent,akshare_sina,efinance,akshare_em` | Continue through the list; provider-run diagnostics record the failed and successful source |
| U.S. index daily bars | YFinance, then configured Finnhub | Stale daily cache after eligible providers fail |
| U.S. stock daily bars | Longbridge, Finnhub, Alpha Vantage, then YFinance when Longbridge is configured and available; otherwise Finnhub, Alpha Vantage, then YFinance | Any available but non-preferred Longbridge route is last; unsupported or unavailable providers are skipped; stale daily cache is last |
| Hong Kong daily bars | The market filter retains HK-capable providers in numeric-priority order: configured and initialized Tushare (`-1`), AkShare (`1`), YFinance (`4`), then optional Longbridge (`5`) | `LONGBRIDGE_PRIORITY` can change Longbridge's HK daily position, but credentials alone do not promote it |
| Hong Kong and U.S. realtime quote | Configured and available Longbridge is preferred for the supported non-A-share quote route | YFinance or AkShare remains the market-specific fallback |
| Japan, Korea, and Taiwan daily bars | Market capability filtering retains supported providers, primarily YFinance for current coverage | Market-specific intelligence fields may be `not_supported` even when daily bars succeed |
| AlphaSift hotspot refresh | DSA EastMoney provider by default | Fall back to the last-good hotspot cache; without cache, return a stable empty state with a readable error code |

Provider success for one market does not prove support for another. Daily health is isolated by `daily_data:<market>:<provider>`, so an A-share outage does not directly lower the same provider's U.S. health.

## Health Score and Circuit State

The daily-provider health window is process-local and bounded. Defaults require no configuration:

| Key | Default | Effect |
| --- | ---: | --- |
| `PROVIDER_CIRCUIT_BREAKER_ENABLED` | `true` | Skip daily providers in cooldown after repeated exceptions; health observations continue when disabled |
| `PROVIDER_CIRCUIT_FAILURE_THRESHOLD` | `3` | Consecutive failures needed to open a circuit |
| `PROVIDER_CIRCUIT_COOLDOWN_SECONDS` | `300` | Cooldown before one half-open recovery probe |
| `PROVIDER_HEALTH_WINDOW_SIZE` | `20` | Recent bounded outcome and latency samples per market/provider key |
| `PROVIDER_ADAPTIVE_PRIORITY_ENABLED` | `true` | Allow eligible equal-priority daily providers to reorder |
| `PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES` | `3` | Samples required for each provider before it can join adaptive ordering |

The 0-100 health score is:

```text
70 * recent_success_rate
+ 20 * (1 / (1 + average_latency_ms / 1000))
+ 10 * max(0, 1 - consecutive_failures / failure_threshold)
```

When no latency has been observed, the latency factor is `1`. The snapshot also includes `error_rate`, sample counts, average latency, consecutive exceptions, circuit state, remaining cooldown, and last success/failure times.

An empty table or `None` is a quality failure in the recent health window. In the normal closed state it does not increment the consecutive-exception counter or open the circuit, so a provider can be retried on a later request. An empty half-open probe does not prove recovery and returns the provider to cooldown. Only a successful half-open probe closes the circuit.

Health and circuit state do not persist across process restarts.

## Adaptive-ordering Boundaries

Adaptive daily ordering is deliberately constrained:

1. Market-support and request-capability filters run first.
2. Numeric static priority is a hard boundary. Providers with different priority values never exchange positions.
3. A provider must be `closed` and meet `PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES`.
4. An `open`, `half_open`, or under-sampled provider stays at its static position and splits the list into separate contiguous ranking segments.
5. Eligible peers are ordered by health score, then success rate, then lower average latency, then original static order.
6. Setting `PROVIDER_ADAPTIVE_PRIORITY_ENABLED=false` immediately restores static ordering; health sampling and circuit control remain active.

This prevents a learned order from crossing explicit operator choices, market routes, or recovery probes. It also means a high score does not promote a priority-2 provider ahead of a priority-0 provider.

## Cache and Stale Degradation

Daily data uses two provider-manager cache layers in addition to the Pipeline's existing `stock_daily` database cache:

| Layer | Default fresh lifetime | Notes |
| --- | ---: | --- |
| L1 process memory | 60 seconds | Bounded to 256 entries by default |
| L2 local JSON table | 3,600 seconds | Defaults to `data/provider_cache/daily`; same-directory temporary write plus atomic replacement |
| Stale-if-error window | 86,400 additional seconds | Used only after every eligible provider fails; the newer eligible L1/L2 stale candidate wins |

```env
PROVIDER_DAILY_CACHE_ENABLED=true
PROVIDER_DAILY_CACHE_DIR=data/provider_cache/daily
PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS=60
PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS=3600
PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS=86400
PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES=256
```

Set an individual TTL or stale window to `0` to disable that behavior, or set `PROVIDER_DAILY_CACHE_ENABLED=false` to disable this provider-manager cache. Stale data is marked with `is_stale=true`, its age, layer, and source; it must not be presented as a live quote.

## Data Provider Plugins

`DataProvider` and `DataProviderRegistration` are now the stable plugin
contract. Built-in sources also register through the unified X2 registry while
retaining their existing runtime names, credential gates, construction order,
and instance priorities. With no plugin loaded, market filtering, fixed routes,
circuit behavior, cache semantics, adaptive ordering, and diagnostics therefore
remain unchanged.

A plugin declares a stable `provider_id`, factory, markets, and capabilities
through the same registry exposed by `DataFetcherManager.plugin_registry`. The
factory runs inside the plugin load transaction; a factory failure, invalid
implementation, ID collision, or runtime-name collision fails only that plugin.
Unloading removes the exact owned provider. Numeric plugin priority affects only
routes already governed by priority. U.S. index, U.S. stock,
Longbridge-preferred, and realtime built-in chains retain their fixed order and
try eligible plugins only as tail fallbacks.
Unload does not rewrite unexpired daily-cache entries or process-local health
observations; they keep their existing TTL, stale, and reset semantics.

This batch exposes programmatic registration. External-directory startup
scanning remains deferred to X2b behind GATE-P3 and is not automatically wired.
See the [plugin extension contract](plugin-extension-contract.md#data-providers)
for fields, capability identifiers, and an example.

## Recommended Profiles

### Zero-cost local profile

This profile uses the built-in free chain and keeps cache/circuit protection enabled:

```env
REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em
ENABLE_EASTMONEY_PATCH=true

PROVIDER_CIRCUIT_BREAKER_ENABLED=true
PROVIDER_ADAPTIVE_PRIORITY_ENABLED=true
PROVIDER_DAILY_CACHE_ENABLED=true
```

It requires no market-data token, but free upstreams can rate-limit, change response shapes, or return partial coverage. Keep multiple sources enabled rather than forcing one free source to handle every request.

### Production A-share profile

```env
TUSHARE_TOKEN=your_tushare_token
TICKFLOW_API_KEY=your_tickflow_key

REALTIME_SOURCE_PRIORITY=tickflow,tushare,tencent,akshare_sina,efinance,akshare_em
SNAPSHOT_SOURCE_PRIORITY=tushare,sina,efinance,akshare_em,em_datacenter

PROVIDER_CIRCUIT_BREAKER_ENABLED=true
PROVIDER_CIRCUIT_FAILURE_THRESHOLD=3
PROVIDER_CIRCUIT_COOLDOWN_SECONDS=300
PROVIDER_HEALTH_WINDOW_SIZE=20
PROVIDER_ADAPTIVE_PRIORITY_ENABLED=true
PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES=3
```

Tushare improves daily and snapshot stability. TickFlow can improve A-share daily bars, realtime quotes, and market review, subject to account permissions. Keep the free chain as fallback; do not make a credentialed provider the only source.

### Production Hong Kong and U.S. profile

```env
LONGBRIDGE_OAUTH_CLIENT_ID=your_client_id
LONGBRIDGE_OAUTH_TOKEN_CACHE_B64=your_token_cache_base64

FINNHUB_API_KEY=your_finnhub_key
ALPHAVANTAGE_API_KEY=your_alphavantage_key
```

Configured Longbridge credentials make it preferred for supported non-A-share realtime quotes and for U.S. stock daily bars. Hong Kong daily placement still follows numeric priority. YFinance remains the broad baseline; Finnhub and Alpha Vantage participate only when configured. U.S. indexes still prefer YFinance because Longbridge does not provide that index route.

## Troubleshooting

| Symptom | Check | Action |
| --- | --- | --- |
| Repeated `429`, connection reset, or remote disconnect | Provider-run diagnostics and `provider_health` logs; whether one free provider receives most calls | Keep cache enabled, retain multiple fallbacks, wait for cooldown, and add a token-based provider for sustained workloads. Do not disable the circuit merely to retry a rate-limited provider faster. |
| Provider order differs from the `.env` list | Whether the request is daily data or realtime; daily static priorities and adaptive logs | `REALTIME_SOURCE_PRIORITY` controls only realtime quotes. For daily data, inspect numeric priorities and `provider_priority event=adaptive_reorder`; disable adaptive ordering temporarily to compare with static order. |
| A configured provider is skipped | Credential completeness, market/capability support, circuit state, and minimum samples | Correct credentials or symbol/market selection. An open provider is retried by a half-open probe after cooldown; unsupported providers cannot be promoted by lowering priority. |
| Daily bars work but flow, boards, or institutional fields are missing | [Market support boundaries](market-support.md) and the field's `status`/quality metadata | Treat `not_supported` or `partial` as a capability boundary, not proof that the daily provider failed. Do not substitute A-share-only data for another market. |
| All live providers fail but a result is returned | `DataFrame.attrs["provider_cache"]` and task `ProviderRun` diagnostics | Confirm `is_stale=true`, `stale_seconds`, and source. Use the result as degraded evidence and lower confidence; set the stale window to `0` if policy forbids stale use. |
| No provider is attempted | Normalized symbol, market classification, optional credentials, and capability filters | Add a provider that actually supports the market. Changing priority cannot make an unsupported provider eligible. |
| AlphaSift returns partial screening or stale hotspots | `source_errors`, warnings, snapshot/daily health, and hotspot cache metadata | Add Tushare for snapshot stability, retain the DSA daily context, and retry hotspot refresh after the upstream recovers. |

## Diagnostics and Reset

```python
report = manager.get_daily_provider_health_report("cn")
manager.log_daily_provider_health_report("cn")
DataFetcherManager.reset_daily_source_health()

manager.get_daily_cache_stats()
manager.invalidate_daily_cache("600519")
```

The health report schema is `provider_daily_health_v1`. `provider_count=0` means the current process has no observation for that market; it does not mean all providers are permanently unavailable. Resetting health removes learned ordering and circuit state, so use it for diagnostics or controlled recovery rather than as a rate-limit bypass.

## Operator Boundaries

- A single provider failure is fail-open where another eligible source or stale entry exists.
- Market and capability support remain hard boundaries.
- Adaptive ordering is process-local and does not rewrite `.env` priorities.
- Provider errors and health logs are sanitized and must not contain tokens or raw credentials.
- This guide defines backend behavior. Settings-screen operation paths are maintained separately from these semantics.

## Related Documentation

- [LLM configuration, degradation, and hot reload](LLM_CONFIG_GUIDE_EN.md#routing-and-degradation-order)
- [Market support boundaries](market-support.md)
- [AlphaSift integration](alphasift-integration.md) (Chinese)
- [ADR-005: provider fallback and circuit control](adr/ADR-005-provider-fallback-and-circuit-control.md)
- [FAQ: data-source and rate-limit symptoms](FAQ_EN.md)
