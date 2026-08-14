# Portfolio-Level Multi-Symbol Analysis

Service and Web entry for analyzing a **list of symbols as one portfolio** ([#128](https://github.com/SiinXu/stock-pulse-ai/issues/128)).

This is not a stack of per-symbol conclusions. The service builds a synthetic
equal/custom-weight snapshot in the **existing portfolio holdings shape**, then
reuses:

| Data plane | Role |
| --- | --- |
| `PortfolioRiskMetricsService` | Correlation matrix, historical VaR, concentration / diversification |
| `PortfolioHealthService` | Structural dimension scores on the same snapshot + risk inputs |
| `PortfolioStressTestService` | Optional deterministic stress overlay |
| `WatchlistScoreService` | Stance / score distribution from **existing** analysis (no new LLM) |

No separate holdings ledger or parallel portfolio model is introduced.

## Endpoint

```http
POST /api/v1/analysis/portfolio
```

`operation_id`: `analyzePortfolioLevel`

Auth matches neighboring `/api/v1/analysis/*` and `/api/v1/portfolio/*` routes
(global admin session when enabled).

### Request (JSON)

| Field | Default | Notes |
| --- | --- | --- |
| `stock_codes` | required | `1..20` unique codes; overflow is rejected with a clear limit message |
| `weights` | equal weight | Optional non-negative map; must only use codes from `stock_codes`. Usable symbols missing from the map receive an equal unit baseline, then all usable weights are renormalized. |
| `as_of` | today | End date for stored closes / snapshot |
| `lookback_trading_days` | `252` | Passed to risk metrics (`60..1000`) |
| `confidence` | `0.95` | VaR confidence |
| `horizon_days` | `1` | VaR horizon |
| `include_stress` | `true` | When true, runs `scenario_id` on the synthetic snapshot |
| `scenario_id` | `market_down_10` | Built-in or configured stress scenario |
| `sector_map` | none | Optional labels for sector shared-risk clusters |
| `high_correlation_threshold` | `0.70` | Absolute correlation floor for highlights |
| `currency` | `CNY` | Synthetic snapshot response currency |

### Response highlights

- `status`: `ok` | `partial` | `unavailable`
- `correlation` / `correlation_highlights`
- `concentration` / `var`
- `shared_risk_exposures` (high-correlation clusters, optional sector groups, name concentration)
- `stance_distribution` (from existing watchlist scores / decision signals)
- `health` (projected portfolio health payload; often `partial` for baskets without cash/PnL)
- `stress` (optional)
- `degraded_symbols` + `annotations` when some names lack prices

## Size bound

`MAX_SYMBOLS = 20`. Requests with more codes fail validation before any analysis
runs. The error text states the limit and asks the caller to split the basket.

## Missing-data policy (hard requirement)

1. Latest stored daily closes are loaded per symbol (no provider hot path).
2. Symbols without a usable positive close are listed under `degraded_symbols`
   with `reason=price_unavailable`.
3. Remaining symbols keep the analysis running; weights are **rebased** over the
   usable set.
4. Overall `status` becomes `partial` when any symbol was excluded.
5. If **every** symbol is missing prices, `status=unavailable` is returned as a
   successful HTTP 200 payload — not a 500.

Single-symbol data gaps must never abort the whole basket.

## Weighting

- Default: equal weight across **usable** symbols.
- Custom weights: positive values only; degraded codes are dropped, then the
  remaining weights are renormalized to 1.0.

Cash is zero and holdings PnL is not modeled. For synthetic baskets, health marks
`cash_ratio` and `pnl` **unavailable** (they never score 0/neutral as if real).
Invalid `scenario_id` returns HTTP 400; unexpected stress runtime failures degrade
only the stress block.

## Web entry

Open `/portfolio?tab=insights&view=basket`. Enter up to 20 symbols and choose whether to include the deterministic stress block. The view preserves `ok / partial / unavailable` states and displays correlation, concentration, VaR, health, stance distribution, and degraded symbols. It does not launch new per-symbol LLM runs or write the synthetic basket to a real account ledger.

## Out of scope (follow-up)

- A standalone long-form portfolio report and persisted report history
- CLI `--portfolio` mode beyond the API
- Notification channel templates for portfolio-level summaries
- Persisting basket health rows into the account-keyed daily health store

## Related docs

- [Portfolio Risk Metrics](portfolio-risk-metrics_EN.md)
- [Portfolio Health Score](portfolio-health-score_EN.md)
- [Portfolio Stress Test](portfolio-stress-test_EN.md)
