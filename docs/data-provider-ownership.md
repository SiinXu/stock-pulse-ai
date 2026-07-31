# Data Provider Module Ownership

- Status: `Living`
- Last verified: 2026-07-30
- Related: [ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md),
  [ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md),
  Issue #622

## Purpose

Track ownership after the sequential ADR-006 extractions from
`data_provider/base.py`. This map tells contributors **where new code belongs**
and **how to land the next review-sized slice** without changing provider
priority, circuit, or fallback policy (ADR-005).

## Compatibility Facade

| Public path | Role |
| --- | --- |
| `data_provider.base` | Compatibility facade and current home of manager/fetcher workflows, circuit helpers, chip helpers still mixed in, re-exports of extracted pure helpers, and rebound capability-catalog descriptors. |
| `data_provider` package (`__init__.py`) | Stable package exports for plugins and callers. |

Until a later retirement PR says otherwise, production and test code may keep
importing public names from `data_provider.base`. Prefer patching
`data_provider.base.<name>` in tests that target the public surface. Slice 1
facade attributes and Slice 2 inventory constants preserve object identity with
their owner module for each import; Slice 2 descriptor functions are cloned
against facade globals to preserve established patch seams. Reloading either
the facade or the private owner runs the same assembly callback, so both reload
orders converge on one current inventory and descriptor set. New
**implementations** of extracted responsibilities belong in the owner module
below, then re-exported from the facade when a public name must remain stable.

## Ownership Map (after second extraction)

| Module | Owns | Does not own |
| --- | --- | --- |
| `data_provider/symbol_normalization.py` | Pure symbol / market code helpers: `normalize_stock_code`, `canonical_stock_code`, `is_bse_code`, `is_st_stock`, `is_kc_cy_stock`, ETF prefix checks, and market tags (`_is_*_market`, `_market_tag`, `_is_etf_code`, `ETF_PREFIXES`) | Provider I/O, caching, circuit policy, dataframe column normalization |
| `data_provider/us_index_mapping.py` | US ticker / index identity helpers used by market classification | A-share / HK / JP / KR / TW suffix rules (those live with symbol normalization or `src.services.market_symbol_utils`) |
| `data_provider/realtime_types.py` | Shared realtime quote types and circuit-breaker data shapes | Manager failover order |
| `data_provider/daily_cache.py` | Layered daily cache keys and lookup helpers | Provider priority |
| `data_provider/plugin_registry.py` | Plugin provider registration and discovery seams | Built-in fetcher implementations |
| `data_provider/_capability_catalog.py` | Built-in capability inventory and the mechanics that apply manager-owned ordering inputs, maintain indexes, synchronize plugin providers, filter by capability/market/availability, and look up fetchers | Priority values or policy, daily/realtime/fundamental execution, cache, health, circuit, fallback, or plugin routing policy |
| `data_provider/*_fetcher.py` | One remote/source adapter each (history, quote, or specialty data) | Cross-provider orchestration |
| `data_provider/fundamental_adapter.py`, `yfinance_fundamental_adapter.py` | Fundamental field adaptation for specific stacks | Daily OHLCV routing |
| `data_provider/base.py` (remainder) | `BaseFetcher` / `DataFetcherManager`, manager-owned priority/circuit/fallback/plugin policy and state, daily/realtime/fundamental/cache/health workflows, env-backed circuit/health knobs, exception summary helpers, chip metric helpers still co-located, and facade bindings/re-exports | New pure symbol rules (add to `symbol_normalization.py` instead) or capability-catalog mechanics |

The private catalog receives and mutates only manager-owned state through
`DataFetcherManager` descriptors. It does not introduce an independent policy
object, configuration source, priority table, circuit, fallback loop, or plugin
route. The manager therefore remains the authoritative ADR-005 / ADR-007 policy
owner while the cohesive catalog mechanics gain Locality.

### Extracted facade names

Slice 1 re-exports these pure helpers unchanged from `data_provider.base`:

- `normalize_stock_code`
- `canonical_stock_code`
- `is_bse_code`
- `is_st_stock`
- `is_kc_cy_stock`
- `ETF_PREFIXES`
- `_is_us_market`, `_is_hk_market`, `_is_jp_market`, `_is_kr_market`, `_is_tw_market`
- `_is_etf_code`, `_market_tag`

Slice 2 rebinds these `DataFetcherManager` descriptors from the private
capability catalog while preserving their `data_provider.base` module,
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

## How To Add The Next Extraction Slice

Follow ADR-006:

1. **Inventory** production imports, tests, and monkeypatch targets for the
   names you plan to move.
2. **Choose one cohesive responsibility** still living in `base.py` (examples:
   chip metric helpers; env reader + circuit defaults; exception unwrap/summary;
   non-manager pure utilities). Do not duplicate capability-catalog mechanics.
   Prefer pure functions with dense offline tests.
3. **Move bodies** into a focused `data_provider/<slice>.py` module.
4. **Re-export** the same names from `data_provider.base` in the same PR.
   Do **not** migrate callers in the structural slice.
5. **State** “no intentional behavior change” in the PR body.
6. **Verify** at least:
   ```bash
   python -m pytest -m "not network" tests/data_provider -q
   python -m py_compile data_provider/*.py
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
- Migrating all `data_provider.base` importers off the facade

## Related Docs

- [Architecture overview](architecture-overview.md)
- [Data-source stability](data-source-stability.md) / [EN](data-source-stability_EN.md)
- [Data provider plugin authoring](data-provider-plugin-authoring.md)
- Market / analysis-context-pack top-level shims remain separate ADR-006 facades under `src/`; their import ban is tracked by Issue #623 and is outside this package map.
