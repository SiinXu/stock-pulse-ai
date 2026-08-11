# Portfolio Health Score (V2 backend contract)

This backend-only feature provides a deterministic portfolio structure score and actionable insights. It references [#151](https://github.com/SiinXu/stock-pulse-ai/issues/151) but does not close it: a visible Portfolio Health page, observable daily update path, and trend consumer remain unimplemented.

The score is a structural metric, not investment advice. An LLM may rewrite insight text only; it cannot change scores, bands, thresholds, severity, symbols, or evidence.

## HTTP lifecycle

| Method | Path | Contract |
| --- | --- | --- |
| `GET` | `/api/v1/portfolio/health` | Read one stored daily result; never replays or writes |
| `POST` | `/api/v1/portfolio/health/refresh` | Explicitly compute; `persist=true` performs one atomic health upsert |

Both accept `account_id`, `as_of`, and `cost_method=fifo|avg`. POST also accepts `persist`; `persist=false` is a true preview with zero writes.

Refresh calls `PortfolioService.preview_portfolio_snapshot()` once, then passes that exact immutable mapping to `PortfolioRiskMetricsService`. It does not materialize portfolio position/lot/daily caches. GET returns 404 when no stored result exists. If the migration is absent, storage access returns the sanitized `portfolio_health_migration_required` 503 and does not create tables at request time.

## Formula configuration

All values are owned by shared `Config`, environment loading, and the system configuration registry. Values must be finite and within their documented domains; malformed values, `NaN`, and infinity are rejected rather than ignored or clamped.

| Dimension | Default weight | Environment key |
| --- | ---: | --- |
| Concentration | 0.25 | `PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION` |
| Risk exposure | 0.25 | `PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE` |
| Diversification | 0.20 | `PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION` |
| PnL | 0.15 | `PORTFOLIO_HEALTH_WEIGHT_PNL` |
| Cash ratio | 0.15 | `PORTFOLIO_HEALTH_WEIGHT_CASH_RATIO` |

Finite non-negative weights are normalized once; they must have a positive sum. Insight thresholds use:

- `PORTFOLIO_HEALTH_CONCENTRATION_ALERT_PCT=35`
- `PORTFOLIO_HEALTH_VAR_ALERT_PCT=5`
- `PORTFOLIO_HEALTH_DIVERSIFICATION_ALERT=0.35`
- `PORTFOLIO_HEALTH_CASH_LOW_ALERT_PCT=2`
- `PORTFOLIO_HEALTH_CASH_HIGH_ALERT_PCT=50`
- `PORTFOLIO_HEALTH_PNL_LOSS_ALERT_PCT=-15`

The low-cash threshold must be strictly below the high-cash threshold. The response records the resolved values and a configuration hash.

## Dimension formulas

Each available dimension produces a 0–100 sub-score:

1. Concentration: top position weight ≤15% scores 100, ≥50% scores 0, linear between.
2. Risk exposure: one-day historical VaR ≤1% scores 100, ≥8% scores 0, linear between.
3. Diversification: upstream diversification in `[0, 1]` multiplied by 100.
4. Unrealized PnL: ≥10% scores 100; 0% scores 70; ≤-30% scores 0, piecewise linear between.
5. Cash ratio: 5–25% scores 100; 0% and ≥80% score 0, linear outside the ideal band.

Every source metric and intermediate must be finite. VaR is unavailable unless its upstream status is `ok`. PnL is unavailable for missing/stale prices or stale FX. Cash is unavailable for stale FX.

## Missing-data invariant

Missing data can never make the primary score or band healthier.

For diagnostics, `partial_score` uses the fixed configured denominator:

```text
partial_score = sum(available_dimension_score * configured_weight)
coverage_ratio = sum(configured_weight for available dimensions)
```

Missing dimensions contribute zero; available weights are not re-normalized. The comparable `score` and normal `healthy|fair|caution|poor` band are emitted only when all five dimensions are available (`coverage_ratio=1`) and source quality has no partial reason. Otherwise:

- `status=partial` or `unavailable`
- `score=null`, `band=null`, `comparable=false`
- `partial_score` may be present only as a non-comparable diagnostic
- each missing dimension gets an explicit unavailable insight
- no “within thresholds” claim is made for unknown dimensions

Cash-only portfolios are partial and can evaluate PnL/cash; they are not called empty. A genuinely zero cash/zero market-value portfolio is empty. Negative equity is explicitly unavailable.

## Persistence and provenance

Migration `202608090002_portfolio_health_snapshots` is the sole schema owner. Runtime repositories never execute DDL. The unique daily key is `(account_key, snapshot_date, cost_method)`, and one `INSERT ... ON CONFLICT DO UPDATE` provides atomic same-key convergence with bounded SQLite busy retries.

The stored payload is byte-semantically the same state returned to the caller, including `persisted=true`. It records:

- source snapshot and risk hashes
- resolved configuration hash and formula version
- UTC calculation timestamp
- risk history window/as-of evidence
- bounded price and FX provenance
- coverage, effective weights, unavailable dimensions, and quality reasons

Strict JSON serialization and response schemas reject non-finite values. The same-day key remains an idempotent current snapshot, not an immutable revision history or trend API.

## Bands for comparable results only

| Band | Range |
| --- | --- |
| `healthy` | `[80, 100]` |
| `fair` | `[60, 80)` |
| `caution` | `[40, 60)` |
| `poor` | `[0, 40)` |

## Rollback

Revert the feature. The additive table can remain inert, or be dropped after preserving any desired data. No existing portfolio ledger data is rewritten.
