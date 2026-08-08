# SmartMoney Money Flow

Optional main-force / large-order capital-flow tracking for individual stocks
(Issue #862 Phase-1 backend).

## Feature flag

| Env | Config field | Default |
| --- | --- | --- |
| `SMARTMONEY_ENABLED` | `smartmoney_enabled` | `false` |

When disabled, `DataFetcherManager.get_money_flow` and
`src.services.smartmoney_flow_service` perform **no** provider network I/O.

## Capability contract

Plugin capability (data-provider contract v1, additive):

| Capability | Method |
| --- | --- |
| `money_flow` | `get_money_flow(stock_code, days=5)` |

Providers that omit this capability continue to load and run. The manager
selects only providers that implement the method and returns `None` when none
succeed.

See `docs/plugin-extension-contract.md` (Data Providers).

## Normalized snapshot

`data_provider.money_flow_types.MoneyFlowSnapshot` fields include:

- `main_net_inflow`, `super_large_net_inflow`, `large_net_inflow`,
  `medium_net_inflow`, `small_net_inflow` (and ratio counterparts when present)
- `main_net_inflow_5d` / `main_net_inflow_10d` when history is available
- **`source`** and **`bucket_definition`** (required calibration metadata)
- `unit` (currently `CNY` for Eastmoney A-share flow)

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
  super-large + large composite; absolute CNY thresholds are owned by the
  vendor and may change.
- **Tushare moneyflow**: different size thresholds; never sum or compare
  directly to Eastmoney values.
- **Tonghuashun rankings**: ranking-oriented windows (“即时”, “5日排行”); not
  a drop-in substitute for the Eastmoney day kline.

## Implemented path

1. `AkshareFetcher.get_money_flow` → `data_provider.money_flow_akshare`
2. `DataFetcherManager.get_money_flow` (gated + multi-provider fallback)
3. Optional analysis injection when enabled:
   - `enhanced_context["money_flow"]`
   - agent `initial_context["money_flow"]`
   - `AnalysisContextPack.blocks["money_flow"]` (only when enabled / data present)

## Remaining scope (not in this PR)

- Dragon-Tiger list / seat-level institutional identification
- Northbound flow, block trades, margin supporting data
- Observation pool / screener / Web UI (see T24 boundary)
- Push brief / portfolio anomaly alerts
- Tushare / efinance / THS providers and HK/US coverage
- Settings UI registry entry for `SMARTMONEY_ENABLED` (config works via env)

## Integration Point

After merge, Settings owners (if desired) can register
`SMARTMONEY_ENABLED` in `src/core/config_registry_parts/data_source.py` following
the `ENABLE_CHIP_DISTRIBUTION` pattern. Runtime already reads the env var via
`src/config_parts/loading.py`.
