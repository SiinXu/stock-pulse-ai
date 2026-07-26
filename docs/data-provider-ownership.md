# Data Provider Module Ownership

- Status: `Living`
- Last verified: 2026-07-26
- Related: [ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md),
  [ADR-006](adr/ADR-006-behavior-preserving-module-decomposition.md),
  Issue #622

## Purpose

Track ownership after the first ADR-006 extraction from
`data_provider/base.py`. This map tells contributors **where new code belongs**
and **how to land the next review-sized slice** without changing provider
priority, circuit, or fallback policy (ADR-005).

## Compatibility Facade

| Public path | Role |
| --- | --- |
| `data_provider.base` | Compatibility facade and current home of manager/fetcher orchestration, circuit helpers, chip helpers still mixed in, and re-exports of extracted pure helpers. |
| `data_provider` package (`__init__.py`) | Stable package exports for plugins and callers. |

Until a later retirement PR says otherwise, production and test code may keep
importing public names from `data_provider.base`. New **implementations** of
extracted responsibilities belong in the owner module below, then re-exported
from the facade when a public name must remain stable.

## Ownership Map (after first extraction)

| Module | Owns | Does not own |
| --- | --- | --- |
| `data_provider/symbol_normalization.py` | Pure symbol / market code helpers: `normalize_stock_code`, `canonical_stock_code`, `is_bse_code`, `is_st_stock`, `is_kc_cy_stock`, ETF prefix checks, and market tags (`_is_*_market`, `_market_tag`, `_is_etf_code`, `ETF_PREFIXES`) | Provider I/O, caching, circuit policy, dataframe column normalization |
| `data_provider/us_index_mapping.py` | US ticker / index identity helpers used by market classification | A-share / HK / JP / KR / TW suffix rules (those live with symbol normalization or `src.services.market_symbol_utils`) |
| `data_provider/realtime_types.py` | Shared realtime quote types and circuit-breaker data shapes | Manager failover order |
| `data_provider/daily_cache.py` | Layered daily cache keys and lookup helpers | Provider priority |
| `data_provider/plugin_registry.py` | Plugin provider registration and discovery seams | Built-in fetcher implementations |
| `data_provider/*_fetcher.py` | One remote/source adapter each (history, quote, or specialty data) | Cross-provider orchestration |
| `data_provider/fundamental_adapter.py`, `yfinance_fundamental_adapter.py` | Fundamental field adaptation for specific stacks | Daily OHLCV routing |
| `data_provider/base.py` (remainder) | `BaseFetcher` / `DataFetcherManager`, env-backed circuit/health knobs, exception summary helpers, chip metric helpers still co-located, capability routing, and facade re-exports | New pure symbol rules (add to `symbol_normalization.py` instead) |

### Extracted public names (slice 1)

Re-exported unchanged from `data_provider.base`:

- `normalize_stock_code`
- `canonical_stock_code`
- `is_bse_code`
- `is_st_stock`
- `is_kc_cy_stock`
- `ETF_PREFIXES`
- `_is_us_market`, `_is_hk_market`, `_is_jp_market`, `_is_kr_market`, `_is_tw_market`
- `_is_etf_code`, `_market_tag`

## How To Add The Next Extraction Slice

Follow ADR-006:

1. **Inventory** production imports, tests, and monkeypatch targets for the
   names you plan to move.
2. **Choose one cohesive responsibility** still living in `base.py` (examples:
   chip metric helpers; env reader + circuit defaults; exception unwrap/summary;
   non-manager pure utilities). Prefer pure functions with dense offline tests.
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
