# Data Provider Module Ownership

- Status: `Living`
- Last verified: 2026-08-21
- Related: [ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md),
  [ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md),
  Issue #622

## Purpose

Track ownership after the sequential ADR-006 extractions from
`src/data_provider/base.py`. This map tells contributors **where new code belongs**
and **how to land the next review-sized slice** without changing provider
priority, circuit, or fallback policy (ADR-005).

## Canonical Facade

| Public path | Role |
| --- | --- |
| `src.data_provider.base` | Canonical facade and current home of manager/fetcher workflows still mixed in, re-exports of extracted pure helpers/errors/chip helpers, and rebound capability-catalog / health / daily-cache / realtime field-trust / money-flow cache descriptors. |
| `src.data_provider` package (`__init__.py`) | Stable package exports for plugins and callers. |

Production and test code import public names from `src.data_provider.base`.
Prefer patching `src.data_provider.base.<name>` in tests that target the public surface. Slice 1
facade attributes and Slice 2 inventory constants preserve object identity with
their owner module for each import; Slice 2 descriptor functions are cloned
against facade globals to preserve established patch seams. Reloading either
the facade or the private owner runs the same assembly callback, so both reload
orders converge on one current inventory and descriptor set. New
**implementations** of extracted responsibilities belong in the owner module
below, then re-exported from the facade when a public name must remain stable.

## Ownership Map (after money-flow cache extraction)

| Module | Owns | Does not own |
| --- | --- | --- |
| `src/data_provider/symbol_normalization.py` | Pure symbol / market code helpers: `normalize_stock_code`, `canonical_stock_code`, `is_bse_code`, `is_st_stock`, `is_kc_cy_stock`, ETF prefix checks, and market tags (`_is_*_market`, `_market_tag`, `_is_etf_code`, `ETF_PREFIXES`) | Provider I/O, caching, circuit policy, dataframe column normalization |
| `src/data_provider/errors.py` | Typed provider failures (`DataFetchError`, `RateLimitError`, `DataSourceUnavailableError`, `CircuitOpenError`) and exception summary helpers (`unwrap_exception`, `summarize_exception`) | Provider I/O, routing, cache policy |
| `src/data_provider/chip_helpers.py` | Pure chip metric coercion and meaningful-distribution checks | Provider I/O and chip fetch orchestration |
| `src/data_provider/us_index_mapping.py` | US ticker / index identity helpers used by market classification | A-share / HK / JP / KR / TW suffix rules (those live with symbol normalization or `src.services.market_symbol_utils`) |
| `src/data_provider/realtime_types.py` | Shared realtime quote types and circuit-breaker data shapes | Manager failover order |
| `src/data_provider/daily_cache.py` | Layered daily cache keys and lookup helpers | Provider priority |
| `src/data_provider/manager_parts/daily_cache_methods.py` | Manager-owned daily cache orchestration rebound onto `DataFetcherManager` (cache resolve, candidate validation, stock-name cache helpers) | Layered cache storage implementation (owned by `daily_cache.py`) |
| `src/data_provider/manager_parts/daily_source_health.py` | Daily health/circuit/adaptive-priority methods rebound onto `DataFetcherManager` | Daily fetch execution loops |
| `src/data_provider/manager_parts/realtime_field_trust_methods.py` | Manager-owned realtime quote attempt and field-trust bookkeeping rebound onto `DataFetcherManager` | Realtime routing policy, fallback order, and `get_realtime_quote` |
| `src/data_provider/manager_parts/money_flow_cache_methods.py` | Manager-owned money-flow cache lookup, store, invalidate, and stats rebound onto `DataFetcherManager` | `get_money_flow` routing, circuit policy, TTL/size class attributes, cache/circuit instance state, and hit/miss increments |
| `src/data_provider/plugin_registry.py` | Plugin provider registration and discovery seams | Built-in fetcher implementations |
| `src/data_provider/_capability_catalog.py` | Built-in capability inventory and the mechanics that apply manager-owned ordering inputs, maintain indexes, synchronize plugin providers, filter by capability/market/availability, and look up fetchers | Priority values or policy, daily/realtime/fundamental execution, cache, health, circuit, fallback, or plugin routing policy |
| `src/data_provider/*_fetcher.py` | One remote/source adapter each (history, quote, or specialty data) | Cross-provider orchestration |
| `src/data_provider/akshare_fetcher.py` | Compatibility facade for the AkShare provider: public class, constants, re-exports, and ADR-006 method rebinding / timeout clone seams | New capability-domain bodies (add under `akshare_parts/`) |
| `src/data_provider/akshare_parts/` | AkShare implementation ownership by capability domain: `symbols`, `timeout_client`, `parse_tencent`, `realtime_errors`, `history`, `realtime_quotes`, `market_boards`, `enhanced`, `realtime_cache`, plus `facade_bind` helpers | Cross-provider manager policy (ADR-005) |
| `src/data_provider/fundamental_adapter.py`, `yfinance_fundamental_adapter.py` | Fundamental field adaptation for specific stacks | Daily OHLCV routing |
| `src/data_provider/base.py` (remainder) | `BaseFetcher` / `DataFetcherManager`, manager-owned priority/fallback/plugin policy and state, daily/realtime/fundamental workflows still co-located, facade bindings/re-exports | New pure symbol rules, typed errors, chip helpers, capability-catalog mechanics, or extracted health/daily-cache/field-trust/money-flow-cache descriptors |

The private catalog receives and mutates only manager-owned state through
`DataFetcherManager` descriptors. It does not introduce an independent policy
object, configuration source, priority table, circuit, fallback loop, or plugin
route. The manager therefore remains the authoritative ADR-005 / ADR-007 policy
owner while the cohesive catalog mechanics gain Locality.

### Extracted facade names

Slice 1 re-exports these pure helpers unchanged from `src.data_provider.base`:

- `normalize_stock_code`
- `canonical_stock_code`
- `is_bse_code`
- `is_st_stock`
- `is_kc_cy_stock`
- `ETF_PREFIXES`
- `_is_us_market`, `_is_hk_market`, `_is_jp_market`, `_is_kr_market`, `_is_tw_market`
- `_is_etf_code`, `_market_tag`

Slice 3 re-exports typed failures and pure helpers unchanged from
`src.data_provider.base`:

- `DataFetchError`, `RateLimitError`, `DataSourceUnavailableError`, `CircuitOpenError`
- `unwrap_exception`, `summarize_exception`
- `_coerce_chip_metric`, `_is_meaningful_chip_distribution`

Slice 2 rebinds these `DataFetcherManager` descriptors from the private
capability catalog while preserving their `src.data_provider.base` module,
qualname, signature, class-dictionary position, globals, and patch behavior:

- `plugin_registry`, `available_fetchers`, `add_fetcher`
- `_assign_fetcher_static_order_locked`, `_provider_priority`,
  `_sort_fetchers_locked`, `_remove_registered_fetcher_locked`
- `_sync_registered_data_providers`, `_get_fetchers_snapshot`,
  `_refresh_fetcher_indexes_locked`
- `_provider_plugin_registration`, `_provider_supports_capability`,
  `_get_fetchers_for_capability`, `_get_fetcher_by_name`
- `_call_availability_probe`, `_is_fetcher_available`
- `_filter_daily_fetchers_for_market`, `_filter_fetchers_by_capability`
- `_register_builtin_data_provider`

For each facade import or reload, the catalog owns the same freshly assembled
objects exposed as manager inventory constants:
`_DAILY_MARKET_FETCHER_SUPPORT`, `_BUILTIN_DATA_PROVIDER_IDS`,
`_BUILTIN_DATA_PROVIDER_PLUGIN_ID`, and `_DAILY_MARKETS`.

Slice 4 rebinds daily health/circuit descriptors from
`manager_parts/daily_source_health.py` (see that module's
`EXPECTED_DAILY_SOURCE_HEALTH_METHOD_NAMES`).

Slice 5 rebinds daily-cache orchestration descriptors from
`manager_parts/daily_cache_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `_get_daily_data_cache`, `is_market_data_local_only`, `_daily_adjustment_identity`
- `_daily_cache_key`, `_record_daily_cache_result`, `_validate_daily_candidate`
- `get_daily_cache_stats`, `invalidate_daily_cache`
- `_get_cached_stock_name`, `_cache_stock_name`

Slice 6 rebinds realtime field-trust descriptors from
`manager_parts/realtime_field_trust_methods.py` (see that module's
`EXPECTED_REALTIME_FIELD_TRUST_METHOD_NAMES`).

Slice 7 rebinds money-flow cache descriptors from
`manager_parts/money_flow_cache_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `_money_flow_cache_lookup`, `_money_flow_cache_store`
- `invalidate_money_flow_cache`, `get_money_flow_cache_stats`

`get_money_flow`, `_money_flow_timestamp`, TTL/size class attributes,
cache/circuit instance state, and hit/miss increments stay on the facade.

## How To Add The Next Extraction Slice

Follow ADR-006:

1. **Inventory** production imports, tests, and monkeypatch targets for the
   names you plan to move.
2. **Choose one cohesive responsibility** still living in `base.py` (examples:
   chip metric helpers; env reader + circuit defaults; exception unwrap/summary;
   non-manager pure utilities). Do not duplicate capability-catalog mechanics.
   Prefer pure functions with dense offline tests.
3. **Move bodies** into a focused `src/data_provider/<slice>.py` module.
4. **Re-export** the same names from `src.data_provider.base` in the same PR.
   Do **not** migrate callers in the structural slice.
5. **State** “no intentional behavior change” in the PR body.
6. **Verify** at least:
   ```bash
   python -m pytest -m "not network" tests/data_provider -q
   python -m py_compile src/data_provider/*.py
   ```
7. **Update this ownership map** so the table matches the tree.
8. If broad-exception handlers move, classify or regenerate fingerprints through
   repository tooling (do not hand-edit baselines casually).

Do **not** change ADR-005 policy (priority order, circuit thresholds semantics,
or fallback behavior) in the same PR as a pure move.

## Out Of Scope Here

- Provider priority / circuit / fallback policy changes
- Fetcher rewrites
- Plugin provider API redesign
- Migrating all `src.data_provider.base` importers off the facade

## Related Docs

- [Architecture overview](architecture-overview.md)
- [Data-source stability](data-source-stability.md) / [EN](data-source-stability_EN.md)
- [Data provider plugin authoring](data-provider-plugin-authoring.md)
- Market / analysis-context-pack top-level shims remain separate ADR-006 facades under `src/`; their import ban is tracked by Issue #623 and is outside this package map.
