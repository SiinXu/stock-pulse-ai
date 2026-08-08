# Portfolio Stress Test (Deterministic Shocks)

Backend-only portfolio stress testing ([#158](https://github.com/SiinXu/stock-pulse-ai/issues/158); related [#210](https://github.com/SiinXu/stock-pulse-ai/issues/210)).

This page documents the **deterministic factor-shock** engine, assumptions, and
honesty rules. A Web Portfolio surface is intentionally out of scope for this
delivery (Portfolio Web work is owned by a separate track).

## Scope

| Included | Not included (remaining) |
| --- | --- |
| Declarative built-in scenarios (YAML-overridable) | Historical extreme-window path replay |
| Deterministic market / sector / FX / rate shocks | Monte Carlo or full revaluation paths |
| Explicit unit-beta and rate-sensitivity labels | Calibrated multi-factor risk models |
| `partial` when beta/sector data is missing | Web UI charts |
| Concentration block reused from risk-metrics helpers | Agent / report embedding |

**Simulation method this delivery:** `deterministic_factor_shock` only.
`historical_replay_available` is always `false` in the API payload.

## Endpoints

```http
GET  /api/v1/portfolio/stress-test/scenarios
GET  /api/v1/portfolio/stress-test?scenario_id=market_down_10
POST /api/v1/portfolio/stress-test
```

Auth matches neighboring `/api/v1/portfolio/*` routes.

### Query / body parameters (run)

| Parameter | Notes |
| --- | --- |
| `scenario_id` | Built-in or YAML scenario id (GET required; POST optional if `custom_shocks`) |
| `target_sector` | Required for sector scenarios |
| `account_id` / `as_of` / `cost_method` | Same snapshot contract as risk-metrics |
| `betas` (POST) | Optional per-symbol market beta |
| `sector_map` (POST) | Optional per-symbol sector labels |
| `custom_shocks` (POST) | Optional list of `{factor, value_pct|value_bp}` |
| `rate_sensitivity_pct_per_100bp` | Default `2.0` (simplified) |

## Built-in scenarios

| id | Shock |
| --- | --- |
| `market_down_10` | Market −10% |
| `market_down_20` | Market −20% |
| `sector_down_30` | Named sector −30% (needs `target_sector`) |
| `fx_up_5` / `fx_down_5` | FX ±5% on non-base currency holdings |
| `rate_up_100bp` | Rates +100bp via equity sensitivity assumption |

Optional env: `PORTFOLIO_STRESS_SCENARIOS_PATH` pointing at a YAML file that
lists additional scenarios or overrides by `id`. **Unset = built-ins only.**

## Transmission formulas

### Market

\[
r_i = \beta_i \cdot s_{\mathrm{market}}
\]

If \(\beta_i\) is not provided, \(\beta_i = 1\) and the response status becomes
`partial` with `missing_data` containing `beta` and
`simplified_assumptions` containing `unit_beta_default`.

### Sector

\[
r_i =
\begin{cases}
s_{\mathrm{sector}} & \mathrm{sector}(i)=\mathrm{target} \\
0 & \text{otherwise}
\end{cases}
\]

Names without sector classification do **not** receive a fabricated sector hit;
they contribute `sector` to `missing_data` and overall `partial` when relevant.

### FX

Applied only when `valuation_currency` differs from the portfolio base currency.

### Rate

\[
r_i = -\,k \cdot \frac{\Delta \mathrm{bp}}{100}
\]

Default \(k = 2.0\) percent points per +100bp for every equity name
(`uniform_equity_rate_sensitivity`). This is **not** bond duration or a
calibrated equity rate beta.

### Portfolio PnL

\[
\mathrm{PnL} = \sum_i V_i \cdot \frac{r_i}{100},\quad
\mathrm{PnL\%} = 100 \cdot \frac{\mathrm{PnL}}{\sum_i V_i}
\]

Multiple shocks in one scenario are **linearly additive** (documented
simplification; no second-order correlation or liquidity effects).

## Honesty statuses

| status | Meaning |
| --- | --- |
| `ok` | Shock applied with sufficient classification / beta inputs |
| `empty_portfolio` | No positive market-value equity holdings |
| `partial` | Result computed but uses defaults or incomplete sector map |

Never invent beta/sector data to look complete. Prefer `partial` + `missing_data`.

## Concentration

Position weights feed `compute_concentration_metrics` from
`portfolio_risk_metrics_service` (read-only reuse). The risk-metrics service
file is **not** modified.

## Implementation map

| Piece | Path |
| --- | --- |
| Scenario catalog | `src/services/portfolio_stress_scenarios.py` |
| Service | `src/services/portfolio_stress_test_service.py` |
| Endpoint | `api/v1/endpoints/portfolio_stress_test.py` |
| Schemas | `api/v1/schemas/portfolio_stress_test.py` |
| Service tests | `tests/services/test_portfolio_stress_test_service.py` |
| API tests | `tests/api/test_portfolio_stress_test_api.py` |

## Assumption checklist (delivery note)

1. Instantaneous, one-shot factor shocks (not multi-day paths).
2. Linear additivity across factors.
3. Missing market beta → unit beta with `partial`.
4. Uniform equity rate sensitivity default.
5. FX only on currency mismatch vs base.
6. No provider calls on the hot path.
7. Historical extreme-window replay **not** implemented.
