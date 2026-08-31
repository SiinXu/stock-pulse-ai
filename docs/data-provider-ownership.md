# Data Provider Module Ownership

- Status: `Living`
- Last verified: 2026-08-30
- Related: [ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md),
  [ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md),
  Issue #622, Issue #1292

## Purpose

Track ownership after the sequential ADR-006 extractions from
`src/data_provider/base.py`. This map tells contributors **where new code belongs**
and **how to land the next review-sized slice** without changing provider
priority, circuit, or fallback policy (ADR-005).

## Canonical Facade

| Public path | Role |
| --- | --- |
| `src.data_provider.base` | Canonical facade and current home of manager/fetcher workflows still mixed in, re-exports of extracted pure helpers/errors/chip helpers, and rebound capability-catalog / health / daily-cache / daily-execution / realtime field-trust / realtime quote orchestration / chip-distribution orchestration / stock-name lookup / money-flow cache / money-flow orchestration / fundamental cache / fundamental loaders / fundamental-config accessor / CN fundamental sub-blocks / fundamental payload helpers / rankings / market-overview / belong-board descriptors. |
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

## Process manager identity (pipeline and agent tools)

`resolve_process_data_fetcher_manager()` on the composition root
(`src/application_services.py`) is the single resolver for the analysis
pipeline and agent data/market tools. It prefers the installed
`ApplicationServices.data_fetcher_manager` when auto-bind owns one, then the
`src.agent.tools.data_tools` fallback singleton. `active_fetcher_manager()`
and `reset_fetcher_manager()` still observe or clear **only** that fallback
singleton. Ad-hoc `DataFetcherManager()` constructors elsewhere stay out of
this identity.

## Ownership Map (after fundamental timeout/retry worker extraction)

| Module | Owns | Does not own |
| --- | --- | --- |
| `src/data_provider/symbol_normalization.py` | Pure symbol / market code helpers: `normalize_stock_code`, `canonical_stock_code`, `is_bse_code`, `is_st_stock`, `is_kc_cy_stock`, ETF prefix checks, and market tags (`_is_*_market`, `_market_tag`, `_is_etf_code`, `ETF_PREFIXES`) | Provider I/O, caching, circuit policy, dataframe column normalization |
| `src/data_provider/errors.py` | Typed provider failures (`DataFetchError`, `RateLimitError`, `DataSourceUnavailableError`, `CircuitOpenError`) and exception summary helpers (`unwrap_exception`, `summarize_exception`) | Provider I/O, routing, cache policy |
| `src/data_provider/chip_helpers.py` | Pure chip metric coercion and meaningful-distribution checks | Provider I/O and chip fetch orchestration |
| `src/data_provider/us_index_mapping.py` | US ticker / index identity helpers used by market classification | A-share / HK / JP / KR / TW suffix rules (those live with symbol normalization or `src.services.market_symbol_utils`) |
| `src/data_provider/realtime_types.py` | Shared realtime quote types and circuit-breaker data shapes | Manager failover order |
| `src/data_provider/pull_coalesce.py` | Process-local short-TTL + in-flight coalesce helper keyed by provider, normalized symbol, as_of, and capability (wait timeout is per-caller, not a key axis) | Daily L1/L2 persistence, fallback order, circuit policy, snapshot keep-last-good caches, new env keys |
| `src/data_provider/daily_cache.py` | Layered daily cache keys and lookup helpers | Provider priority |
| `src/data_provider/manager_parts/daily_cache_methods.py` | Manager-owned daily cache orchestration rebound onto `DataFetcherManager` (cache resolve, candidate validation, stock-name cache helpers) | Layered cache storage implementation (owned by `daily_cache.py`) |
| `src/data_provider/manager_parts/daily_source_health.py` | Daily health/circuit/adaptive-priority methods rebound onto `DataFetcherManager`, plus the realtime `get_realtime_quote` and chip `get_chip_distribution` call locks that now enter `pull_coalesce` | Daily fetch execution loops, coalesce key policy |
| `src/data_provider/manager_parts/daily_provider_execution.py` | Manager-owned daily execution rebound onto `DataFetcherManager`: `get_daily_data` cache-resolve entry, `_call_daily_data_provider`, and `_get_daily_data_from_providers` fallback loop | Health/circuit state machine (`daily_source_health`), layered cache storage (`daily_cache.py`), cache helpers (`daily_cache_methods`), capability inventory, realtime routing |
| `src/data_provider/manager_parts/realtime_field_trust_methods.py` | Manager-owned realtime quote attempt and field-trust bookkeeping rebound onto `DataFetcherManager` | Realtime routing policy, fallback order, and `get_realtime_quote` |
| `src/data_provider/manager_parts/realtime_quote_methods.py` | Manager-owned realtime quote orchestration rebound onto `DataFetcherManager`: timestamp parse/enrich, plugin realtime fallback, `get_realtime_quote` routing, quote supplement helpers, and Longbridge preference | Field-trust attempt bookkeeping (`realtime_field_trust_methods`), `prefetch_realtime_quotes`, Local Only / outbound HTTP policy, chip / money-flow / stock-name / fundamental / rankings workflows |
| `src/data_provider/manager_parts/chip_distribution_methods.py` | Manager-owned chip-distribution orchestration rebound onto `DataFetcherManager`: `get_chip_distribution` routing, provider priority, fallback/error behavior, and chip-circuit success/failure/inconclusive accounting | Pure chip metric helpers (`chip_helpers.py`), `pull_coalesce` chip call locks (`daily_source_health`), stock-name lookup (`stock_name_methods`), rankings / loader/cache / prefetch, BaseFetcher methods |
| `src/data_provider/manager_parts/stock_name_methods.py` | Manager-owned single-code stock-name lookup plus bulk/prefetch rebound onto `DataFetcherManager`: `get_stock_name` cache/static/index precedence, the market-data Local Only short circuit, the optional realtime probe, provider capability ordering with the US-capable allow-list, the all-sources-failed fallback, `prefetch_stock_names`, and `batch_get_stock_names` | Stock-name memory cache helpers (`daily_cache_methods`), `STOCK_NAME_MAP` / `is_meaningful_stock_name` / `get_index_stock_name` facade seams, realtime quote orchestration, rankings, loader/cache, BaseFetcher methods |
| `src/data_provider/manager_parts/money_flow_cache_methods.py` | Manager-owned money-flow cache lookup, store, invalidate, and stats rebound onto `DataFetcherManager` | `get_money_flow` routing and hit/miss accounting (`money_flow_methods`), circuit policy, TTL/size class attributes, and cache/circuit instance state |
| `src/data_provider/manager_parts/money_flow_methods.py` | Manager-owned money-flow orchestration rebound onto `DataFetcherManager`: `_money_flow_timestamp`, `get_money_flow` routing, circuit failure/success, `source_chain`, `fallback_to`, the stale-cache return path, and hit/miss accounting | Cache lookup/store/invalidate/stats (`money_flow_cache_methods`), TTL/size class attributes, cache/circuit instance state including hit/miss counters, fundamental loaders, daily/realtime/Local Only behavior, and other rankings |
| `src/data_provider/manager_parts/fundamental_cache_methods.py` | Manager-owned fundamental aggregation cache key, prune, and in-flight get-or-load rebound onto `DataFetcherManager` (instance-local; key is symbol + market + budget + as_of). TTL/max-entries resolve from injected `config` or manager `_get_fundamental_config()` | CN/offshore aggregation loaders (`fundamental_loader_methods`), `FUNDAMENTAL_CACHE_TTL_SECONDS` env default, `_should_cache_fundamental_context` (`fundamental_payload_methods`), the 5s realtime/chip `pull_coalesce` singleton, daily L1/L2, and TW institutional inflight |
| `src/data_provider/manager_parts/fundamental_loader_methods.py` | Manager-owned fundamental CN/offshore loaders rebound onto `DataFetcherManager`: `_build_offshore_fundamental_context` and `get_fundamental_context` (market dispatch, nested `_load` closures, TW fail-open institution) | Cache key/prune/in-flight (`fundamental_cache_methods`), `_get_fundamental_config` (rebound from `fundamental_context_methods`, not inlined here), payload helpers (`fundamental_payload_methods`), timeout/retry workers, failed/validation-rejected builders (`fundamental_outcome_methods`), CN sub-block public APIs (`fundamental_cn_context_methods`), chip / stock-name / rankings / prefetch |
| `src/data_provider/manager_parts/fundamental_context_methods.py` | Manager-owned `_get_fundamental_config` accessor rebound onto `DataFetcherManager`. Resolves process Config per call through `get_application_services().config` (default root still `get_config()` identity; injected `ApplicationServices.config` is authoritative). This is a behavior-adjacent #1540 conversion, not a pure #1067 mechanical extract. | Constructor/instance Config cache, CN/offshore loaders, CN sub-blocks (`fundamental_cn_context_methods` call this accessor), cache TTL helpers, chip / realtime / retry callers (they keep `self._get_fundamental_config()`), other `get_config()` sites on `base.py` |
| `src/data_provider/manager_parts/fundamental_cn_context_methods.py` | Manager-owned CN fundamental sub-blocks rebound onto `DataFetcherManager`: `get_capital_flow_context`, `get_dragon_tiger_context`, and `get_board_context`. Each block converts its former `get_config()` site to `self._get_fundamental_config()`. `get_board_context` still calls rebound `_get_sector_rankings_with_meta` | Payload helpers (`fundamental_payload_methods`), failed/rejected builders (`fundamental_outcome_methods`), timeout/retry workers, CN/offshore loaders, `_get_fundamental_config` body, rankings orchestration, concept-rankings TTL/lock/dict class attributes, TickFlow, prefetch |
| `src/data_provider/manager_parts/fundamental_payload_methods.py` | Manager-owned fundamental payload helpers rebound onto `DataFetcherManager`: `_normalize_source_chain`, `_block_status`, `_build_fundamental_block`, `_has_meaningful_payload`, `_infer_block_status`, `_should_cache_fundamental_context`, and `_build_market_not_supported`. `_has_meaningful_payload` still looks up rebound `_try_scalar_isna` from facade globals | Failed/rejected builders (`fundamental_outcome_methods`), timeout/retry workers (`fundamental_timeout_methods`), TickFlow lifecycle, prefetch, `_get_fundamental_config`, CN/offshore loaders, CN sub-blocks, belong-board `_try_scalar_isna` body |
| `src/data_provider/manager_parts/fundamental_timeout_methods.py` | Manager-owned timeout/retry workers rebound onto `DataFetcherManager`: `_run_with_timeout` (daemon `Thread`, non-blocking `BoundedSemaphore` slot) and `_run_with_retry` (budgeted attempts via rebound `_get_fundamental_config().fundamental_retry_max`). `_run_with_retry` still calls rebound `self._run_with_timeout` | Slot construction (`_fundamental_timeout_slots` / `_fundamental_timeout_worker_limit` on `__init__`), failed/rejected builders (`fundamental_outcome_methods`), TickFlow lifecycle, prefetch, `_init_default_fetchers`, remaining `get_config()` sites, CN/offshore loaders, CN sub-blocks |
| `src/data_provider/manager_parts/fundamental_outcome_methods.py` | Manager-owned failed/validation-rejected fundamental outcome builders rebound onto `DataFetcherManager`: `build_failed_fundamental_context` and `build_validation_rejected_fundamental_context`. Cloned bodies still resolve facade `_market_tag` / `sanitize_diagnostic_text` and rebound `self._build_fundamental_block` | TickFlow lifecycle (`tickflow_lifecycle_methods`), prefetch, `_init_default_fetchers`, timeout slot construction, remaining `get_config()` sites, payload helpers, timeout/retry workers, CN/offshore loaders, CN sub-blocks |
| `src/data_provider/manager_parts/rankings_methods.py` | Manager-owned rankings orchestration rebound onto `DataFetcherManager`: sector ranking aggregation with meta, concept-rankings cache read/write, hot-stock and limit-up pool routing | `BaseFetcher` provider methods of the same names, market-overview routing (`get_main_indices`, `get_market_stats` — Slice 16), concept-rankings TTL/lock/dict class attributes, `get_board_context` (Slice 19), and capability inventory |
| `src/data_provider/manager_parts/tickflow_lifecycle_methods.py` | Manager-owned TickFlow lifecycle rebound onto `DataFetcherManager`: `_get_tickflow_fetcher` (create/replace/registry reuse; converts the former `get_config()` site to `self._get_fundamental_config()`) and `close` (best-effort TickFlow release). Facade `__del__` stays a live FunctionDef and still calls rebound `self.close()` | Prefetch (`prefetch_realtime_quotes` / `prefetch_daily_klines`), `_init_default_fetchers`, timeout slot construction, remaining `get_config()` sites, market-overview routing (`get_main_indices` / `get_market_stats` still call rebound `_get_tickflow_fetcher`), capability inventory |
| `src/data_provider/manager_parts/market_overview_methods.py` | Manager-owned market-overview routing rebound onto `DataFetcherManager`: TickFlow-first `get_main_indices` and `get_market_stats` capability fallback | `BaseFetcher` provider methods of the same names, TickFlow lifecycle (`tickflow_lifecycle_methods`: `_get_tickflow_fetcher`, `close`), capability inventory, rankings, CN sub-blocks, payload helpers, belong-board routing, prefetch, and timeout workers |
| `src/data_provider/manager_parts/belong_board_methods.py` | Manager-owned belong-board missing-value and normalization helpers plus `get_belong_boards` routing, capability probing, and provider fallback rebound onto `DataFetcherManager` | Fundamental payload helpers that only *call* `_try_scalar_isna` (`fundamental_payload_methods`), stock-name bulk/prefetch, CN sub-blocks, timeout workers, TickFlow lifecycle |
| `src/data_provider/plugin_registry.py` | Plugin provider registration and discovery seams | Built-in fetcher implementations |
| `src/data_provider/_capability_catalog.py` | Built-in capability inventory and the mechanics that apply manager-owned ordering inputs, maintain indexes, synchronize plugin providers, filter by capability/market/availability, and look up fetchers | Priority values or policy, daily/realtime/fundamental execution, cache, health, circuit, fallback, or plugin routing policy |
| `src/data_provider/*_fetcher.py` | One remote/source adapter each (history, quote, or specialty data) | Cross-provider orchestration |
| `src/data_provider/akshare_fetcher.py` | Compatibility facade for the AkShare provider: public class, constants, re-exports, and ADR-006 method rebinding / timeout clone seams | New capability-domain bodies (add under `akshare_parts/`) |
| `src/data_provider/akshare_parts/` | AkShare implementation ownership by capability domain: `symbols`, `timeout_client`, `parse_tencent`, `realtime_errors`, `history`, `realtime_quotes`, `market_boards`, `enhanced`, `realtime_cache`, plus `facade_bind` helpers | Cross-provider manager policy (ADR-005) |
| `src/data_provider/efinance_fetcher.py` | Compatibility facade for the efinance provider: public class, constants, module-level code/timeout helpers, and ADR-006 method rebinding | New capability-domain bodies (add under `efinance_parts/`) |
| `src/data_provider/efinance_parts/` | efinance implementation ownership by capability domain: `etf` (ETF history fetch and ETF realtime quote), `realtime` (stock realtime quote), `market_boards` (main indices, market stats, sector rankings), plus `facade_bind` helpers | Stock-path history/info bodies, per-symbol `get_belong_board`, module-level code and timeout helpers, and cross-provider manager policy (ADR-005) |
| `src/data_provider/tickflow_fetcher.py` | Compatibility facade for the TickFlow provider: public class, constants, capability probing, client access, and ADR-006 method rebinding | New capability-domain bodies (add under `tickflow_parts/`) |
| `src/data_provider/tickflow_parts/` | TickFlow implementation ownership by capability domain: `market_boards` (main indices, market stats, sector rankings), plus `facade_bind` helpers | Daily/realtime fetch bodies, prefetch paths, capability probing, client access, and cross-provider manager policy (ADR-005) |
| `src/data_provider/yfinance_fetcher.py` | Compatibility facade for the yfinance provider: public class, constants, symbol conversion, HTTP guard, and ADR-006 method rebinding | New capability-domain bodies (add under `yfinance_parts/`) |
| `src/data_provider/yfinance_parts/` | yfinance implementation ownership by capability domain: `main_indices` (regional main-index quotes and the shared ticker fetch), plus `facade_bind` re-export | Realtime quote routing, Stooq/US-index fallbacks, daily fetch/normalize bodies, and cross-provider manager policy (ADR-005) |
| `src/data_provider/tushare_fetcher.py` | Compatibility facade for the Tushare provider: public class, HTTP-client / URL / symbol re-exports, and ADR-006 method rebinding / HTTP-client clone seams | New capability-domain bodies (add under `tushare_parts/`) |
| `src/data_provider/tushare_parts/` | Tushare implementation ownership by capability domain: `client` (HTTP client, URL resolve, rate-limit wrappers), `symbols` (ETF/US classifiers and ts_code conversion), `history` (`_fetch_raw_data` / `_normalize_data`), `stock_identity` (`get_stock_name` / `get_stock_list`), plus `facade_bind` helpers | Cross-provider manager policy (ADR-005); Tushare realtime / market-boards / chip remain on the facade |
| `src/data_provider/fundamental_adapter.py`, `yfinance_fundamental_adapter.py` | Fundamental field adaptation for specific stacks | Daily OHLCV routing |
| `src/data_provider/base.py` (remainder) | `BaseFetcher` / `DataFetcherManager`, manager-owned priority/plugin policy and state, facade `__del__`, timeout slot construction (`_fundamental_timeout_slots`), concept-rankings TTL/lock/dict class attributes, money-flow TTL/size class attributes plus cache/circuit instance state, `_SUPPLEMENT_FIELDS`, facade bindings/re-exports | `_get_fundamental_config` (rebound from `fundamental_context_methods`), CN sub-blocks (rebound from `fundamental_cn_context_methods`), payload helpers (rebound from `fundamental_payload_methods`), timeout/retry workers (rebound from `fundamental_timeout_methods`), failed/rejected builders (rebound from `fundamental_outcome_methods`), TickFlow lifecycle (rebound from `tickflow_lifecycle_methods`), new pure symbol rules, typed errors, chip helpers, capability-catalog mechanics, or extracted health/daily-cache/daily-execution/field-trust/realtime-quote/chip-distribution/money-flow-cache/money-flow-orchestration/fundamental-cache/fundamental-loader/rankings/market-overview/belong-board/stock-name descriptors |

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

TTL/size class attributes, cache/circuit instance state, and hit/miss
counter state stay on the facade. `get_money_flow` routing and hit/miss
accounting travel with Slice 11 along with `_money_flow_timestamp`.

Slice 8 rebinds belong-board missing-value and normalization descriptors from
`manager_parts/belong_board_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `_try_scalar_isna`, `_is_missing_board_value`, `_normalize_belong_boards`

`get_belong_boards` routing, capability probing, and provider fallback travel
with Slice 17. `_has_meaningful_payload` stays on the facade and still
calls the rebound `_try_scalar_isna` through `DataFetcherManager`.

Slice 9 rebinds daily provider execution descriptors from
`manager_parts/daily_provider_execution.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `_call_daily_data_provider`, `get_daily_data`, `_get_daily_data_from_providers`

Health/circuit (`daily_source_health`) and daily-cache helpers remain separate
owners. `prefetch_daily_klines` stays on the facade and still calls rebound
`get_daily_data`.

Slice 10 rebinds realtime quote orchestration descriptors from
`manager_parts/realtime_quote_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `_utc_now_iso`, `_parse_realtime_timestamp`, `_enrich_realtime_quote`
- `_try_plugin_realtime_quote`, `get_realtime_quote`
- `_quote_needs_supplement`, `_merge_quote_fields`
- `_longbridge_preferred`, `_supplement_from_longbridge`

Field-trust (`realtime_field_trust_methods`) remains a separate owner.
`prefetch_realtime_quotes`, `_SUPPLEMENT_FIELDS`, stock-name, and
fundamental stay on the facade. Chip-distribution routing travels with
Slice 13 and rankings with Slice 15. `get_realtime_quote` is rebound
after field-trust and then wrapped by `install_facade_validation_wrappers`.
Import the facade (`src.data_provider.base` / `src.data_provider`), not
`manager_parts.realtime_quote_methods`.

Slice 11 rebinds money-flow orchestration descriptors from
`manager_parts/money_flow_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `_money_flow_timestamp`, `get_money_flow`

Cache helpers (`money_flow_cache_methods`) remain a separate owner.
TTL/size class attributes, cache/circuit instance state, and hit/miss
counter state stay on the facade. Routing and hit/miss accounting travel
with `get_money_flow`. Import the facade
(`src.data_provider.base` / `src.data_provider`), not
`manager_parts.money_flow_methods`.

Slice 12 rebinds fundamental CN/offshore loader descriptors from
`manager_parts/fundamental_loader_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `_build_offshore_fundamental_context`, `get_fundamental_context`

Cache helpers (`fundamental_cache_methods`) remain a separate owner.
`_get_fundamental_config` is rebound from `fundamental_context_methods`
(#1540), not inlined in the loader. Payload helpers, timeout/retry workers,
`_should_cache_fundamental_context`, failed/validation-rejected builders,
and CN sub-block public APIs travel with Slice 19. Nested `_load` closures
stay nested inside the moved methods. `get_fundamental_context` is rebound
after fundamental cache and then wrapped by `install_facade_validation_wrappers`.
Import the facade (`src.data_provider.base` / `src.data_provider`), not
`manager_parts.fundamental_loader_methods`.

Slice 13 rebinds chip-distribution orchestration descriptors from
`manager_parts/chip_distribution_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `get_chip_distribution`

Pure chip metric helpers (`chip_helpers.py`) and the chip `pull_coalesce`
call lock (`daily_source_health`) remain separate owners. Loader/cache
and prefetch stay on the facade. Rankings travel with Slice 15. Import
the facade (`src.data_provider.base` / `src.data_provider`), not
`manager_parts.chip_distribution_methods`.

Slice 14 rebinds stock-name lookup descriptors from
`manager_parts/stock_name_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `get_stock_name`

Stock-name memory cache helpers (`_get_cached_stock_name` /
`_cache_stock_name`, owned by `daily_cache_methods`) remain a separate
owner. The static `STOCK_NAME_MAP`, `is_meaningful_stock_name`, and
`get_index_stock_name` module-level seams stay on the facade, so
`src.data_provider.base.get_index_stock_name` remains the patch target.
Bulk/prefetch entry points (`prefetch_stock_names`,
`batch_get_stock_names`) travel with Slice 18. Loader/cache stay on the
facade. Rankings travel with Slice 15. The in-body
`from .akshare_fetcher import _is_us_code` seam resolves through the
facade package because rebound descriptors keep
`src.data_provider.base` globals. Import the facade
(`src.data_provider.base` / `src.data_provider`), not
`manager_parts.stock_name_methods`.

Slice 15 rebinds rankings orchestration descriptors from
`manager_parts/rankings_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `_get_sector_rankings_with_meta`, `get_sector_rankings`
- `_copy_ranking_rows`, `clear_concept_rankings_cache_for_tests`
- `get_concept_rankings`, `get_hot_stocks`, `get_limit_up_pool`

`BaseFetcher` provider methods of the same names stay on `BaseFetcher`.
Market-overview routing (`get_main_indices`, `get_market_stats`) travels
with Slice 16. Concept-rankings TTL/lock/dict class attributes stay on the
facade. `get_board_context` travels with Slice 19 and still calls rebound
`_get_sector_rankings_with_meta`. `_copy_ranking_rows` remains a
`staticmethod` and `clear_concept_rankings_cache_for_tests` remains a
`classmethod`. Import the facade (`src.data_provider.base` /
`src.data_provider`), not `manager_parts.rankings_methods`.

Slice 16 rebinds market-overview routing descriptors from
`manager_parts/market_overview_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch behavior:

- `get_main_indices`, `get_market_stats`

`BaseFetcher` provider methods of the same names stay on `BaseFetcher`
(`Optional[...]` returns; `get_market_stats` has no `purpose` kw-only).
TickFlow lifecycle (`_get_tickflow_fetcher`, `close`), capability inventory,
payload helpers, prefetch, and timeout workers stay on the facade. CN
sub-blocks travel with Slice 19. Belong-board routing travels with Slice 17. `purpose` is log metadata
only and is not forwarded to providers. Import the facade
(`src.data_provider.base` / `src.data_provider`), not
`manager_parts.market_overview_methods`.

Issue #1540 (behavior-adjacent leftover after Slice 16, not a pure #1067
mechanical extract) rebinds `_get_fundamental_config` from
`manager_parts/fundamental_context_methods.py`. The body is
`get_application_services().config`, so the default composition root keeps
`src.config.get_config` identity while an injected
`ApplicationServices.config` is authoritative. Public patch target remains
`src.data_provider.base.DataFetcherManager._get_fundamental_config`.
Slice 16 leftover on the facade: stock-name bulk/prefetch, CN sub-blocks,
payload helpers, timeout workers, TickFlow lifecycle, and the remaining
`base.py` `get_config()` sites.

Slice 17 rebinds belong-board routing from
`manager_parts/belong_board_methods.py` (extending the Slice 8 owner)
while preserving `src.data_provider.base` module, qualname, signature,
globals, and patch behavior:

- `get_belong_boards`

Missing-value and normalization helpers already rebound in Slice 8 stay
in this owner. Routing calls `self._normalize_belong_boards`. Capability
`"belong_boards"` plus `hasattr(..., "get_belong_board")` probe order,
empty non-CN returns, empty-payload failed `provider_run`, and
`except Exception` fallback are unchanged. `get_belong_boards` is not a
validation-wrapped exit. Import the facade
(`src.data_provider.base` / `src.data_provider`), not
`manager_parts.belong_board_methods`.

Slice 17 leftover on the facade: stock-name bulk/prefetch, CN sub-blocks,
payload helpers, timeout workers, TickFlow lifecycle, and the remaining
`base.py` `get_config()` sites.

Slice 18 rebinds stock-name bulk/prefetch from
`manager_parts/stock_name_methods.py` (extending the Slice 14 owner)
while preserving `src.data_provider.base` module, qualname, signature,
globals, and patch behavior:

- `prefetch_stock_names`, `batch_get_stock_names`

Single-code `get_stock_name` already rebound in Slice 14 stays in this
owner. `prefetch_stock_names` either no-ops on empty/local-only, delegates
to `batch_get_stock_names` when `use_bulk=True`, or sequentially calls
`get_stock_name(..., allow_realtime=False)`. Bulk lookup still seeds from
raw codes, serializes via `_ensure_concurrency_guards` plus the cache lock,
capability-fences `stock_list` providers, rejects cross-market rows,
logs `data_provider_bulk_stock_name_lookup_failed` then continues, and
falls back to `get_stock_name`. Neither method is a validation-wrapped
exit. Import the facade (`src.data_provider.base` / `src.data_provider`),
not `manager_parts.stock_name_methods`.

Slice 18 leftover on the facade: CN sub-blocks traveled with Slice 19.
Remaining on the facade after Slice 18: payload helpers, timeout workers,
TickFlow lifecycle, `prefetch_realtime_quotes` / `prefetch_daily_klines`,
and the remaining `base.py` `get_config()` sites.

Slice 19 rebinds CN fundamental sub-blocks from
`manager_parts/fundamental_cn_context_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, globals, and patch
behavior:

- `get_capital_flow_context`, `get_dragon_tiger_context`, `get_board_context`

Each method converts its former `from src.config import get_config` /
`config = get_config()` site to `config = self._get_fundamental_config()`
in the same PR so the new owner has zero bare `get_config()` sites.
Fallback remains CN / ETF `not_supported`, timeout `failed`,
`_run_with_retry` plus adapter / rebound `_get_sector_rankings_with_meta`,
and fail-open block builders. None of the three methods is a
validation-wrapped exit. Payload helpers, `_run_with_retry` /
`_run_with_timeout`, TickFlow, prefetch, and rankings stay on the facade
or their existing owners. Import the facade (`src.data_provider.base` /
`src.data_provider`), not `manager_parts.fundamental_cn_context_methods`.

Slice 19 leftover on the facade: payload helpers traveled with Slice 20.
Remaining on the facade after Slice 19: timeout workers, TickFlow
lifecycle, `prefetch_realtime_quotes` / `prefetch_daily_klines`,
failed/rejected builders, and the remaining `base.py` `get_config()`
sites (TickFlow, `_init_default_fetchers`, `prefetch_realtime_quotes`).

Slice 20 rebinds fundamental payload helpers from
`manager_parts/fundamental_payload_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, descriptor kind,
globals, and patch behavior:

- `_normalize_source_chain`, `_block_status`, `_build_fundamental_block`
- `_has_meaningful_payload`, `_infer_block_status`
- `_should_cache_fundamental_context`, `_build_market_not_supported`

Bodies stay behavior-preserving. `_has_meaningful_payload` still calls
`DataFetcherManager._try_scalar_isna(..., "fundamental_payload")` and
recurses through `DataFetcherManager._has_meaningful_payload` via facade
globals so `patch.object(DataFetcherManager, "_try_scalar_isna")` keeps
working. `_build_market_not_supported` still calls rebound
`self._build_fundamental_block`. ETF markets keep top-level and
valuation status `"partial"`; other markets stay `"not_supported"`. None
of the seven names is a validation-wrapped exit. The new owner has zero
`get_config()` sites and does not import the facade. Import the facade
(`src.data_provider.base` / `src.data_provider`), not
`manager_parts.fundamental_payload_methods`.

Slice 20 leftover on the facade: failed/rejected builders
(`build_failed_fundamental_context`,
`build_validation_rejected_fundamental_context`), timeout workers
(`_run_with_timeout` / `_run_with_retry`), TickFlow lifecycle
(`_get_tickflow_fetcher`, `close`, `__del__`),
`prefetch_realtime_quotes` / `prefetch_daily_klines`,
`_init_default_fetchers`, and the remaining `base.py` `get_config()`
sites (TickFlow, `_init_default_fetchers`, `prefetch_realtime_quotes`).

Slice 21 rebinds timeout/retry workers from
`manager_parts/fundamental_timeout_methods.py` while preserving their
`src.data_provider.base` module, qualname, signature, descriptor kind,
globals, and patch behavior:

- `_run_with_timeout`, `_run_with_retry`

Bodies stay behavior-preserving. `_run_with_timeout` still uses facade
`Thread` / `time` and instance `_fundamental_timeout_slots` (constructed
in `__init__`, not moved). `_run_with_retry` still calls rebound
`self._get_fundamental_config()` and `self._run_with_timeout`. Neither
name is a validation-wrapped exit. The new owner has zero `get_config()`
sites and does not import the facade. Import the facade
(`src.data_provider.base` / `src.data_provider`), not
`manager_parts.fundamental_timeout_methods`.

Slice 21 leftover on the facade: failed/rejected builders
(`build_failed_fundamental_context`,
`build_validation_rejected_fundamental_context`), TickFlow lifecycle
(`_get_tickflow_fetcher`, `close`, `__del__`),
`prefetch_realtime_quotes` / `prefetch_daily_klines`,
`_init_default_fetchers`, timeout slot construction, and the remaining
`base.py` `get_config()` sites (TickFlow, `_init_default_fetchers`,
`prefetch_realtime_quotes`).

Slice 22 rebinds failed/validation-rejected fundamental outcome builders
from `manager_parts/fundamental_outcome_methods.py` while preserving
their `src.data_provider.base` module, qualname, signature, descriptor
kind, globals, and patch behavior:

- `build_failed_fundamental_context`
- `build_validation_rejected_fundamental_context`

Bodies stay behavior-preserving. Failed payloads still report status
`failed` with `fundamental_pipeline` source-chain result `failed`.
Validation-rejected payloads still sanitize reason codes through facade
`sanitize_diagnostic_text`, copy evidence dicts, and do not claim
provider `failed`. Both still call rebound
`self._build_fundamental_block` and facade `_market_tag`. Neither name
is a validation-wrapped exit. The new owner has zero `get_config()`
sites and does not import the facade. Import the facade
(`src.data_provider.base` / `src.data_provider`), not
`manager_parts.fundamental_outcome_methods`.

Slice 22 leftover on the facade: TickFlow lifecycle
(`_get_tickflow_fetcher`, `close`, `__del__`),
`prefetch_realtime_quotes` / `prefetch_daily_klines`,
`_init_default_fetchers`, timeout slot construction, and the remaining
`base.py` `get_config()` sites (TickFlow, `_init_default_fetchers`,
`prefetch_realtime_quotes`).

Slice 23 rebinds TickFlow lifecycle from
`manager_parts/tickflow_lifecycle_methods.py` while preserving
their `src.data_provider.base` module, qualname, signature, descriptor
kind, globals, and patch behavior:

- `_get_tickflow_fetcher`
- `close`

Bodies stay behavior-preserving. Empty or missing `tickflow_api_key`
still closes a stale fetcher, clears handles, and returns `None`.
Registry `self._get_fetcher_by_name("TickFlowFetcher")` still wins
when present. Same-key reuse keeps `current_fetcher`. Key change still
closes the previous fetcher then constructs `TickFlowFetcher` with the
same getattr defaults. Construct failure still warns
`tickflow_fetcher_initialization_failed`, clears handles, and returns
`None`. `close` still clears handles under the lock then best-effort
releases the previous fetcher. The moved `_get_tickflow_fetcher` site
converts its former `get_config()` call to
`self._get_fundamental_config()`. Facade `__del__` stays a live
FunctionDef and still calls rebound `self.close()`, swallowing
`Exception`. Neither moved name is a validation-wrapped exit. The new
owner has zero `get_config()` sites and does not import the facade.
Market-overview routing still calls rebound
`self._get_tickflow_fetcher()`. Import the facade
(`src.data_provider.base` / `src.data_provider`), not
`manager_parts.tickflow_lifecycle_methods`.

Slice 23 leftover on the facade: `__del__`,
`prefetch_realtime_quotes` / `prefetch_daily_klines`,
`_init_default_fetchers`, timeout slot construction, and the remaining
`base.py` `get_config()` sites (`_init_default_fetchers`,
`prefetch_realtime_quotes`).

Tushare client / symbols / history / stock-identity (Issue #1068) rebinds
`_init_api` / `_build_api_client` / `_check_rate_limit` /
`_call_api_with_rate_limit`, `_detect_exchange_hint` /
`_convert_stock_code` / `_convert_hk_stock_code_for_tushare`,
`_fetch_raw_data` / `_normalize_data`, and `get_stock_name` /
`get_stock_list` from `tushare_parts/` while preserving
`src.data_provider.tushare_fetcher` module, qualname, shared
`_stock_name_cache` identity, and patch seams (`safe_post`,
`requests.post`, `get_config`, `_check_rate_limit`, converters, `_api.*`).
Import the facade (`src.data_provider.tushare_fetcher` /
`src.data_provider`), not `tushare_parts`. Realtime, market-boards, and
chip stay on the Tushare facade.

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
