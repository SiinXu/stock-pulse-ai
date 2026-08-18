# SmartMoney Money Flow

Optional main-force / large-order capital-flow tracking for individual stocks.

- **Phase 1 (Issue #862 / PR #980):** provider capability, typed outcomes, default-off gate, analysis-context injection.
- **Phase 2 (Issue #989):** user-reachable stock footprint view + HTTP API with as-of/source labeling and honest degradation.

This document does not cover Dragon-Tiger seats, Northbound flow, observation pools, or push alerts.

## Feature flag

| Env | Config field | Default |
| --- | --- | --- |
| `SMARTMONEY_ENABLED` | `smartmoney_enabled` | `false` |

The composition layer (`src.services.smartmoney_flow_service` and the stock
pipeline) owns the gate. When disabled it does not call
`DataFetcherManager.get_money_flow`, so no provider network I/O occurs. Direct
manager calls execute the capability contract and never re-read the environment.

## Capability contract

Plugin capability (data-provider contract v1, additive):

| Capability | Method |
| --- | --- |
| `money_flow` | `get_money_flow(stock_code, days=5)` |

Providers that omit this capability continue to load and run. The manager
selects only providers that implement the exact versioned method signature and
returns a typed `MoneyFlowOutcome` for every direct call.

Outcome states are `available`, `partial`, `not_supported`, `fetch_failed`,
`empty`, `stale`, and `fallback`. Outcomes carry the requested window, provider
date and age, source chain, cache state, warnings, and an error code when
applicable. A stale or fallback observation is never projected as `available`.

See `docs/plugin-extension-contract.md` (Data Providers).

## Normalized snapshot

`src.data_provider.money_flow_types.MoneyFlowSnapshot` fields include:

- ratio fields for main / super-large / large / medium / small buckets
- absolute amount fields and 5d / 10d rollups only when both currency and scale
  are authoritatively calibrated
- **`source`** and **`bucket_definition`** (required calibration metadata)
- `unit` and `amount_scale` (both `unknown` for this AkShare endpoint)
- requested / observed coverage and completeness

Do **not** mix numeric values across sources without recalibration: order-size
buckets differ between Eastmoney, Tushare, and Tonghuashun.

## Data source research (this PR)

| Source | API / entry | Fields | Frequency | Reliability | Cost | Status |
| --- | --- | --- | --- | --- | --- | --- |
| AkShare (Eastmoney) | `stock_individual_fund_flow(stock, market)` | main / super-large / large / medium / small net amount + ratio | Daily | Free; rate-limited / ban risk | Free | **Implemented** |
| AkShare (Eastmoney rank) | `stock_individual_fund_flow_rank` | ranking board, not per-stock history | Daily | Free; full-board scrape | Free | Remaining |
| AkShare (THS) | `stock_fund_flow_individual` | alternate buckets (即时/3/5/10/20日) | Daily | Free; different calibration | Free | Remaining |
| efinance | Eastmoney wrappers | similar EM buckets | Daily | Free | Free | Remaining |
| Tushare Pro | `moneyflow` | buy/sell by size (Tushare buckets) | Daily | Stable with token | Points | Remaining |
| Tencent | quote-adjacent only | incomplete for main-force | — | Partial | Free | Not suitable as primary |
| HK / US | no free public main-force size-bucket equivalent with same semantics | — | — | — | — | Out of scope this PR |

### Bucket calibration notes

- **Eastmoney (this PR)**: `bucket_definition` =
  `eastmoney_em_order_size_buckets_v1:...`. “Main force” is Eastmoney’s
  super-large + large composite. AkShare's public endpoint documentation does
  not authoritatively state the absolute amount currency/scale, so this adapter
  exposes the documented percentage ratios and omits absolute amounts.
- **Tushare moneyflow**: different size thresholds; never sum or compare
  directly to Eastmoney values.
- **Tonghuashun rankings**: ranking-oriented windows (“即时”, “5日排行”); not
  a drop-in substitute for the Eastmoney day kline.

## Implemented path

1. `AkshareFetcher.get_money_flow` → `src.data_provider.money_flow_akshare`
2. `DataFetcherManager.get_money_flow` (typed outcome + bounded cache,
   provider circuit breaker, and multi-provider fallback)
3. Optional analysis injection when enabled:
   - `enhanced_context["money_flow"]`
   - `AnalysisContextPack.blocks["money_flow"]` with explicit quality status
     (labeled **资金流 / money flow** in report context overview)
4. User-reachable view (Issue #989):
   - `GET /api/v1/stocks/{stock_code}/money-flow?days=5`
   - `src.services.smartmoney_flow_service.build_money_flow_view`
   - Stock Details Web panel (`MoneyFlowPanel`) — loads independently of quote/history

AkShare calls use a process-owned deadline so timeout cancellation terminates
the worker. Timeout and transport failures receive one bounded retry. A manager
cache entry is scoped to symbol, market, effective CN session, requested window,
provider route, and calibration identity; stale cache use is explicit fallback.

## HTTP API (stock footprint view)

| Item | Value |
| --- | --- |
| Method / path | `GET /api/v1/stocks/{stock_code}/money-flow` |
| Query | `days` (1–20, default 5) |
| Gate | When `SMARTMONEY_ENABLED=false`, response is `status=disabled`, `enabled=false`, **no provider I/O** |
| Success body | `schema_version=money_flow_view/1.0`, `status`, `as_of`, `provider_date`, `source`, `source_chain`, `warnings`, optional `snapshot` (ratios / calibrated amounts only), `disclaimer` |
| Degradation | `not_supported` / `fetch_failed` / `empty` / `stale` / `fallback` / `partial` keep explicit `message` and never invent bucket numbers |

The response contract is strict across OpenAPI and the generated Web client:
status/cache/market values are enumerated, all numerics must be finite and within
the provider-domain bounds, and provider attempts/warnings have hard count and
text limits. Uncontracted diagnostics are not exposed. Invalid internal output
fails as a sanitized server error; it is not mislabeled as invalid user input.

Absolute amount fields are omitted unless the provider calibrates both currency
and scale. The Web panel therefore prioritizes **ratio** fields and shows unit /
amount_scale / bucket_definition for honesty.

## Web reachability

| Surface | Entry |
| --- | --- |
| Stock Details | `/stocks/{code}` → section `data-testid=stock-details-money-flow-section` |
| Settings | `SMARTMONEY_ENABLED` system switch (default off) |

## Remaining scope

- Dragon-Tiger list / seat-level institutional identification
- Northbound flow, block trades, margin supporting data
- Observation pool / screener ranking boards
- Push brief / portfolio anomaly alerts
- Tushare / efinance / THS providers and HK/US coverage

## Integration Point

`SMARTMONEY_ENABLED` is registered under system settings
(`src/core/config_registry_parts/system.py`). Runtime loads the env via
`src/config_parts/loading.py`. Analysis pipelines and the stock money-flow
view both honor the same gate.
