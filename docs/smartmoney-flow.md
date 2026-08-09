# SmartMoney Money Flow

Optional main-force / large-order capital-flow tracking for individual stocks.
This is the Issue #862 Phase-1 backend foundation; it does not add a Web UI,
alerts, screening, or agent-core behavior.

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

`data_provider.money_flow_types.MoneyFlowSnapshot` fields include:

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

1. `AkshareFetcher.get_money_flow` → `data_provider.money_flow_akshare`
2. `DataFetcherManager.get_money_flow` (typed outcome + bounded cache,
   provider circuit breaker, and multi-provider fallback)
3. Optional analysis injection when enabled:
   - `enhanced_context["money_flow"]`
   - `AnalysisContextPack.blocks["money_flow"]` with explicit quality status

AkShare calls use a process-owned deadline so timeout cancellation terminates
the worker. Timeout and transport failures receive one bounded retry. A manager
cache entry is scoped to symbol, market, effective CN session, requested window,
provider route, and calibration identity; stale cache use is explicit fallback.

## Remaining scope (not in this PR)

- Dragon-Tiger list / seat-level institutional identification
- Northbound flow, block trades, margin supporting data
- Observation pool / screener / Web UI (see T24 boundary)
- Push brief / portfolio anomaly alerts
- Tushare / efinance / THS providers and HK/US coverage
- Settings UI registry entry for `SMARTMONEY_ENABLED` (config works via env)
- Agent-core injection (kept out of this market-data lane)

## Integration Point

After merge, Settings owners (if desired) can register
`SMARTMONEY_ENABLED` in `src/core/config_registry_parts/data_source.py` following
the `ENABLE_CHIP_DISTRIBUTION` pattern. Runtime already reads the env var via
`src/config_parts/loading.py`.
