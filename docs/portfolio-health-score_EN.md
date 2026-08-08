# Daily Portfolio Health Score (V1)

Deterministic daily portfolio health score and actionable insights
([#151](https://github.com/SiinXu/stock-pulse-ai/issues/151)).

This document lists the full scoring formulas and weights so a third party can
recompute scores. **This is a structural portfolio metric, not investment advice.**

Web portfolio visualization is out of scope for this change.

## Scope

| In scope | Out of scope |
| --- | --- |
| Five rule-based sub-scores + explicit weights | Web UI |
| Rule insights (symbol + threshold) | Stress testing |
| Daily snapshot idempotent upsert | Notification push |
| Honest `partial` data quality | Recomputing VaR / correlation |
| Optional LLM polish of insight *text* only | LLM changing scores |

Inputs come only from existing modules:

1. `PortfolioService.get_portfolio_snapshot(..., include_realtime=False)`
2. `PortfolioRiskMetricsService.get_risk_metrics(...)` (call only; never modify)

## Endpoint

```http
GET /api/v1/portfolio/health
```

| Parameter | Default | Description |
| --- | --- | --- |
| `account_id` | all active accounts | Optional |
| `as_of` | today | Snapshot date |
| `cost_method` | `fifo` | Passed to portfolio snapshot |
| `persist` | `true` | Upsert daily snapshot (overwrite same day) |

Auth matches neighboring `/api/v1/portfolio/*` routes.

Hard contract fields on every response:

- `score_source`: always `"rules"`
- `llm_can_modify_score`: always `false`
- `disclaimer`: structural-metric notice

## Default weights

| Dimension | Weight | Optional env override |
| --- | --- | --- |
| `concentration` | 0.25 | `PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION` |
| `risk_exposure` | 0.25 | `PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE` |
| `diversification` | 0.20 | `PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION` |
| `pnl` | 0.15 | `PORTFOLIO_HEALTH_WEIGHT_PNL` |
| `cash_ratio` | 0.15 | `PORTFOLIO_HEALTH_WEIGHT_CASH_RATIO` |

Weights are normalized to sum to 1.0. When a dimension is unavailable, remaining
weights are re-normalized over available dimensions only.

## Sub-score formulas (0–100, higher is healthier)

### 1. concentration

Input: `concentration.top_weight_pct` from risk metrics.

- top ≤ 15% → 100  
- top ≥ 50% → 0  
- else linear between those anchors

### 2. risk_exposure

Input: 1-day historical VaR percent `var.var_pct` (positive loss points).

- VaR ≤ 1% → 100  
- VaR ≥ 8% → 0  
- else linear  

If VaR status is not `ok` or `var_pct` is null, the dimension is **unavailable**
(never silent zero “no risk”).

### 3. diversification

Input: `diversification_score` ∈ [0, 1] (equal-weight → 1.0).

`score = diversification_score * 100`

### 4. pnl

Input: unrealized PnL as percent of equity.

| unrealized PnL % | sub-score |
| --- | --- |
| ≥ 10 | 100 |
| 0 … 10 | 70 + 30 × (p / 10) |
| -30 … 0 | 70 × (1 − \|p\| / 30) |
| ≤ -30 | 0 |

Unavailable when prices are missing/stale or FX is stale.

### 5. cash_ratio

Input: cash / equity percent.

| cash % | sub-score |
| --- | --- |
| 5 … 25 | 100 (ideal band) |
| 0 … 5 | 100 × (c / 5) |
| 25 … 80 | 100 × (80 − c) / 55 |
| ≥ 80 or ≤ 0 | 0 |

Unavailable when `fx_stale`.

## Aggregate score and bands

\[
S = \sum_{i \in \mathrm{avail}} w'_i s_i,\quad
w'_i = w_i / \sum_{j \in \mathrm{avail}} w_j
\]

| Band | Range |
| --- | --- |
| `healthy` | [80, 100] |
| `fair` | [60, 80) |
| `caution` | [40, 60) |
| `poor` | [0, 40) |

## Status honesty

| status | Meaning |
| --- | --- |
| `ok` | All five dimensions scored |
| `partial` | At least one dimension missing or snapshot quality partial |
| `empty_portfolio` | No positive equity MV; `score` is null |
| `unavailable` | No scorable dimensions |

## Insights and LLM contract

Rule engine emits actionable items with symbol (when applicable), metric value,
and threshold. Optional LLM polish may rewrite `insights[].message` only.
Score, band, dimensions, and insight metric fields remain rule-owned.
Tests assert a malicious polisher cannot change the score.

## Daily snapshot idempotency

Table `portfolio_health_snapshots`, unique key:

`(account_key, snapshot_date, cost_method)`

Same-day recompute **overwrites**.

## Implementation map

| Component | Path |
| --- | --- |
| Service | `src/services/portfolio_health_service.py` |
| Repository | `src/repositories/portfolio_health_repo.py` |
| Endpoint | `api/v1/endpoints/portfolio_health.py` |
| Schema | `api/v1/schemas/portfolio_health.py` |
| Migration | `src/migrations/versions/v202608090001_portfolio_health_snapshots.py` |
| Service tests | `tests/services/test_portfolio_health_service.py` |
| API tests | `tests/api/test_portfolio_health_api.py` |

## Recomputation example

With top=20%, VaR=2%, div=0.9, pnl=5%, cash=15% and default weights:

\[
S \approx 88.57 \quad (\mathrm{band=healthy})
\]

See the Chinese doc for the expanded arithmetic.
