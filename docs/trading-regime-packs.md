# Trading-regime packs (Issue #1141)

Versioned per-market microstructure facts (sessions, halts / price limits,
short-selling norms, and settlement notes) that are auto-attached to market
guidelines when a market is detected.

This document is the topic contract for the packs. It is not live legal or
regulatory advice.

## Scope

Shipped packs live under `src/market/regime_pack_data/` and currently cover
`cn`, `hk`, `us`, and `crypto`. Loader and renderer: `src/market/regime_packs.py`.
Minimal wiring: `src/market/context.py` (`get_market_guidelines` and
`get_trading_regime_context_metadata`).

Authoritative session / holiday / timezone *computation* stays in
`src/core/trading_calendar.py`. Packs only carry descriptive constraint
language and reuse the same timezone identifiers.

## Contract

- Distinct shipped markets produce distinct constraint language.
- Pack version is queryable (`get_trading_regime_pack_version`,
  `list_trading_regime_pack_versions`, `get_trading_regime_context_metadata`)
  and is included in the rendered prompt section that every run attaches via
  `get_market_guidelines`.
- User-visible pack text states that the pack is versioned static reference
  material, **not** a live authoritative statement of law or exchange rules,
  and **not** live legal advice.
- Markets without a pack (for example `jp`, `kr`, `tw`) get an explicit
  no-pack section. They do not inherit US or A-share rules.
- Pack YAML is schema-validated on load. Missing required fields, unknown
  keys, wrong `schema_version`, or a missing packaged directory fail loudly
  with `RegimePackError` naming the file and field.
- Loaded pack objects and their localized maps are immutable.

## Disclaimer

Packs are a static snapshot keyed by `pack_version`. They must not be
presented as current legal counsel, a live rulebook, or a substitute for the
relevant exchange's published rules. When in doubt, the exchange calendar and
rulebook win.

## Out of scope

- Splitting `src/market/analyzer.py` (Issue #1085).
- Persisting pack version onto `AnalysisContextPack` / run-flow snapshot
  fields outside `src/market/context.py` (would require shared pipeline
  files).
