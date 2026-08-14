# Portfolio Rebalancing & Risk-Adjusted Position Bands

Deterministic service and Web V1 for issues [#237](https://github.com/SiinXu/stock-pulse-ai/issues/237) and [#126](https://github.com/SiinXu/stock-pulse-ai/issues/126).

This feature produces **deterministic, explainable suggestions** for portfolio rebalancing and single-name weight bands. It does **not** execute trades, write the ledger, or replace personal judgment.

**Research aid only — not investment advice.**

## HTTP surface

| Method | Path | Contract |
| --- | --- | --- |
| `GET` | `/api/v1/portfolio/rebalancing-recommendations` | Read-only. Consumes portfolio snapshot + risk metrics. Never calls market-data providers. |

Query parameters:

| Parameter | Default | Notes |
| --- | --- | --- |
| `account_id` | all active | Same as risk-metrics |
| `as_of` | today | Snapshot date |
| `cost_method` | `fifo` | `fifo` or `avg` |
| `risk_tolerance` | `moderate` | `conservative` \| `moderate` \| `aggressive` |
| `drift_threshold_pct` | `5.0` | Minimum absolute weight drift (pp) to emit a suggestion |
| `confidence` / `horizon_days` / `lookback_trading_days` | risk-metrics defaults | Forwarded into `PortfolioRiskMetricsService` |

`operation_id`: `getPortfolioRebalancingRecommendations`

## Honesty rules

- Top-level `disclaimer` is always present.
- Every suggestion includes `rationale`, `assumptions[]`, `is_suggestion_only=true`, `auto_execute=false`.
- Empty portfolio → `status=empty_portfolio`, `suggestions=[]`.
- Insufficient VaR/history or missing concentration → `status=insufficient_data`, **refuse** (no invented trades).
- Non-finite inputs (`NaN` / `Inf`) are rejected.
- Cross-currency holdings use `market_value_base` from the portfolio snapshot (already FX-normalized by `PortfolioService`). Local currencies are never mixed raw.

## Risk-band model (`risk_band_v1`)

| `risk_tolerance` | Max single weight | Min effective N | Max HHI | Illustrative 1d VaR ceiling |
| --- | ---: | ---: | ---: | ---: |
| `conservative` | 15% | 6.0 | 0.22 | 2.0% |
| `moderate` | 25% | 4.0 | 0.35 | 3.5% |
| `aggressive` | 40% | 2.5 | 0.50 | 6.0% |

Effective single-name cap = `min(band_cap, PORTFOLIO_MAX_SINGLE_NAME_WEIGHT * 100)`.

### Drift / suggestion algorithm (V1)

1. Load equity weights from snapshot `market_value_base` (cash excluded).
2. Call `PortfolioRiskMetricsService.get_risk_metrics(...)` with forwarded params.
3. Refuse when empty / insufficient history / concentration unavailable.
4. Build breaches: single-name cap, HHI ceiling, effective-N floor, optional VaR ceiling.
5. Emit **trim** suggestions with numeric rationale. Sort candidates by `(weight_pct desc, avg_corr desc, symbol asc)`.
6. Filter with `|delta| < drift_threshold_pct` unless a hard single-name cap breach.
7. Attach per-holding **position bands** (low/mid/high target weight %) for risk-adjusted sizing (#126).

V1 does **not**: optimize mean-variance frontiers; model taxes/commissions/impact; auto-execute trades; invent add targets without an investable universe.

## Portfolio-aware position bands (#126)

For each held name (and via `suggest_position_for_symbol` for a single code):

- Target midpoint = `effective_cap * signal_fraction` where signal fractions are deterministic (`buy` 0.85, `hold` 0.55, `sell` 0.15, …).
- Band half-width is a deterministic function of the midpoint/cap.
- Action relative to current weight: `add` / `reduce` / `hold` / `exit`.
- Without portfolio data, mode is `stock_only_fallback` (still explainable).

Optional environment keys (defaults work without configuration):

| Key | Default | Description |
| --- | --- | --- |
| `PORTFOLIO_AWARE_SIZING_ENABLED` | `true` | Enable portfolio-aware bands |
| `PORTFOLIO_MAX_SINGLE_NAME_WEIGHT` | `0.15` | Soft global single-name cap (fraction) |

## Agent integration

`PortfolioAgent` injects the service payload as a **Deterministic Rebalancing Base**. When present, `post_process` overwrites free-form LLM `rebalance_suggestions` with the base, and stores `deterministic_rebalancing` for downstream consumers. The model may polish narrative text only.

## Web entry

Open `/portfolio?tab=insights&view=rebalance`. Select `conservative`, `moderate`, or `aggressive` risk tolerance and set the drift threshold. The view shows the current risk summary, target model, limitations, and each add/reduce/hold/exit suggestion. `insufficient_data` remains an explicit refusal; no action writes the ledger or executes a trade.

## Non-goals / fences

- Complete multi-goal planning beyond the shipped risk-tolerance and drift controls.
- What-if tax/cost optimizers.

## Rollback

Revert the implementation PR (service + endpoint + schemas + agent wiring + docs + OpenAPI). No DB migration.
