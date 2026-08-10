# Portfolio Risk Metrics (V0)

Backend-only risk metrics for held portfolios ([#239](https://github.com/SiinXu/stock-pulse-ai/issues/239)).

This page documents formulas, assumptions, and honesty rules for
`GET /api/v1/portfolio/risk-metrics`. A Web Portfolio surface is intentionally
out of scope for V0 (PortfolioPage is owned by a separate refactor track).

## Scope

| Included | Not included (follow-up) |
| --- | --- |
| Historical VaR (empirical) | Parametric / Monte Carlo VaR |
| Pairwise Pearson correlation of returns | Sector risk contribution charts |
| Concentration HHI + diversification score | Stress testing (#210) integration |
| Read-only API from **stored** daily bars | Live provider calls on the hot path |
| Explicit insufficient-history status | Report embedding / notifications |

This module **complements** the existing portfolio risk report
(`GET /api/v1/portfolio/risk`: concentration alerts, drawdown, stop-loss,
decision-signal risk). It does not replace that endpoint.

## Endpoint

```http
GET /api/v1/portfolio/risk-metrics
```

Query parameters:

| Parameter | Default | Notes |
| --- | --- | --- |
| `account_id` | all active accounts | Optional |
| `as_of` | today | Snapshot / history end date |
| `cost_method` | `fifo` | Passed to portfolio snapshot |
| `confidence` | `0.95` | Exclusive range `(0.5, 1.0)` |
| `horizon_days` | `1` | `1..30`; multi-day uses √time scaling |
| `lookback_trading_days` | `252` | Requested close count (`60..1000`) |

Auth matches neighboring `/api/v1/portfolio/*` routes (global admin session when enabled).

## Data inputs (no provider hot path)

1. **Holdings / weights** — `PortfolioService.get_portfolio_snapshot(..., include_realtime=False)`.
2. **Daily closes** — `StockRepository.get_range` over already-stored `stock_daily` rows.

Cash is excluded from weights. Weights are market-value shares of equity positions
(`market_value_base`), rebased to sum to 1.0.

## Formulas and assumptions

### Simple returns

For each symbol on consecutive common trading dates \(t-1, t\):

\[
r_{i,t} = \frac{P_{i,t}}{P_{i,t-1}} - 1
\]

Dates are **inner-joined** across all held symbols so every observation uses the same calendar.

### Portfolio returns (static current weights)

\[
R_t = \sum_i w_i \, r_{i,t}
\]

Weights \(w_i\) are **current** snapshot weights held fixed over the lookback
window (not daily rebalanced historical weights). This is an intentional V0
simplification disclosed in the response `assumptions` block.

### Historical VaR

At confidence \(c\) (default \(0.95\)):

1. Take the empirical left-tail quantile of \(\{R_t\}\) at \(\alpha = 1 - c\)
   (NumPy linear percentile interpolation).
2. One-day VaR as a **positive loss fraction**:
   \(\mathrm{VaR}_{1d} = \max(0, -Q_\alpha(R))\).
3. Percent points: \(\mathrm{var\_pct} = 100 \cdot \mathrm{VaR}_{h}\).
4. Currency loss: \(\mathrm{var\_value} = \mathrm{VaR}_{h} \cdot V\), where \(V\) is
   current equity market value.

**Horizon scaling (when `horizon_days` > 1):**

\[
\mathrm{VaR}_{h} = \mathrm{VaR}_{1d} \cdot \sqrt{h}
\]

This uses an **i.i.d. returns / independent days** assumption. It is **not** a
full multi-day historical simulation. V0 documents the assumption instead of
hiding it.

**Distribution assumption:** empirical historical distribution only. Historical
VaR does **not** assume normality.

### Minimum history

| Metric | Minimum aligned return observations |
| --- | --- |
| Historical VaR | 60 |
| Correlation | 30 |

If history is short, the API returns `status: insufficient_history` (or a
per-block status) with **`var_pct` / `var_value` = null** — never silent zeros
that look like “zero risk.”

### Correlation

Pearson correlation of aligned simple returns between every symbol pair.
Diagonal is `1.0`. If a series has zero variance, the off-diagonal cell is
`null` (not forced to 0).

### Concentration and diversification

With weights \(w_i\) (fractions summing to 1) and \(n\) positions:

\[
\mathrm{HHI} = \sum_i w_i^2, \quad
N_{\mathrm{eff}} = \frac{1}{\mathrm{HHI}}
\]

\[
\mathrm{diversification\_score} =
\begin{cases}
0 & n \le 1 \\
\dfrac{1 - \mathrm{HHI}}{1 - 1/n} & n > 1
\end{cases}
\]

Equal-weight portfolios score `1.0`. A single 100% position scores `0.0`.
`top_weight_pct` is \(\max_i w_i \times 100\).

## Response honesty statuses

| Overall / block status | Meaning |
| --- | --- |
| `ok` | Metric computed |
| `empty_portfolio` | No positive market-value equity holdings |
| `insufficient_history` | Aligned history below the documented minimum |
| `unavailable` | Not applicable (e.g. empty portfolio, or correlation with &lt; 2 symbols) |
| `partial` | Some blocks ok, others not |

The `assumptions` object is always present and states method, lookback,
horizon scaling, cash exclusion, and `provider_calls_on_hot_path: false`.

## Implementation map

| Piece | Path |
| --- | --- |
| Service | `src/services/portfolio_risk_metrics_service.py` |
| Endpoint | `api/v1/endpoints/portfolio_risk_metrics.py` |
| Schemas | `api/v1/schemas/portfolio_risk_metrics.py` |
| Service tests | `tests/services/test_portfolio_risk_metrics_service.py` |
| API tests | `tests/api/test_portfolio_risk_metrics_api.py` |
| Web client | `apps/dsa-web/src/api/portfolioRiskMetrics.ts` |
| Web panel | `apps/dsa-web/src/components/portfolio-risk/PortfolioRiskMetricsPanel.tsx` |

## Web V1 surface

The Portfolio page mounts a risk-metrics panel that consumes this endpoint only:

- Historical VaR card (null when block status is not `ok`)
- Correlation matrix with explicit missing cells
- Concentration / diversification card (HHI, effective N, score, top weights)
- Always-visible `assumptions` block
- Honest top-level `empty_portfolio` / `insufficient_history` / `partial` banners

Report embedding, parametric VaR, and stress-test integration remain out of scope.

## Follow-ups (not V0 / not Web V1)

- Parametric VaR, risk contribution, sector breakdown.
- Integration with stress testing (#210) and allocation (#237).
- Report and notification surfaces for risk metrics.
