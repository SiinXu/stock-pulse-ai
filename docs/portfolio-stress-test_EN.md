# Portfolio Stress Test (Deterministic Shocks)

The portfolio stress-test API provides read-only deterministic factor shocks
for [#158](https://github.com/SiinXu/stock-pulse-ai/issues/158), with related
portfolio-risk context from [#210](https://github.com/SiinXu/stock-pulse-ai/issues/210).
Historical replay, Monte Carlo simulation, full instrument revaluation, and Web
visualization remain out of scope.

## API

```http
GET  /api/v1/portfolio/stress-test/scenarios
GET  /api/v1/portfolio/stress-test?scenario_id=market_down_10
POST /api/v1/portfolio/stress-test
```

`GET /stress-test` supports ready presets. The sector preset is explicitly a
parameterized template and must use `POST` with both `target_sector` and a
caller-supplied `sector_map`; the service does not fabricate classifications.
`POST` requires exactly one of `scenario_id` and `custom_shocks`.

Shocks are a discriminated union:

- `market`, `sector`, and `fx` require `value_pct` in `[-100, 100]`.
- `rate` requires `value_bp` in `[-1000, 1000]`.
- Extra fields, wrong units, non-finite values, more than 16 shocks, and a
  composed position return below `-100%` are rejected.
- Beta and sector maps contain at most 256 entries. Beta values are finite and
  bounded to `[-5, 5]`.

## Built-in scenarios

| id | Meaning | Availability |
| --- | --- | --- |
| `market_down_10` | Broad market −10% | Ready |
| `market_down_20` | Broad market −20% | Ready |
| `sector_down_30` | Caller-selected sector −30% | POST parameters required |
| `fx_up_5` / `fx_down_5` | Instrument currency ±5% versus response base | Ready |
| `rate_up_100bp` | Rates +100bp through the disclosed equity sensitivity | Ready |

## Valuation and formulas

The service uses `PortfolioService.preview_portfolio_snapshot()`. This replays
the canonical holdings snapshot without market-provider calls and without
writing derived position, lot, or snapshot rows.

Each position remains separate by account, even when symbols repeat. Its
`market_value_base` is first converted from that account's base currency into
the response base currency. Portfolio totals, weights, PnL, concentration, and
rankings use only these converted values:

\[
w_i = \frac{V_i^{response}}{\sum_j V_j^{response}},\qquad
PnL = \sum_i V_i^{response}\frac{r_i}{100}
\]

The converted position sum is reconciled to the authoritative snapshot
`total_market_value`; a material mismatch makes the result `partial`.

Market transmission is `r_i = beta_i × market_shock`. Missing beta uses `1.0`
and is labeled `partial`. Sector transmission applies only to caller-classified
matching positions. Rate transmission is
`r_i = -sensitivity × (basis_points / 100)`, with a default sensitivity of 2
percentage points per +100bp.

FX shock direction is the instrument/trade currency return versus the response
base currency. It applies when `position.currency` differs from the response
base. `valuation_currency` is the account base and is not used to decide FX
exposure.

## Data quality and provenance

The response includes:

- snapshot hash/version and calculation timestamp;
- scenario source/version/hash and formula version;
- per-position account, instrument/account/response currencies, conversion
  rate/source/as-of/staleness, and price source/provider/date/staleness;
- beta and classification source/as-of when relevant;
- excluded held positions whose price is unavailable or valuation is not
  positive; and
- snapshot limitations, quality, FX staleness, and reconciliation delta.

`top_losers` contains strictly negative PnL rows and `top_winners` strictly
positive rows. Zero-PnL rows appear in neither list; ordering is deterministic.

| Status | Meaning |
| --- | --- |
| `ok` | Complete deterministic result for the supplied inputs |
| `partial` | Result exists but defaults, stale/incomplete data, exclusions, or reconciliation limits apply |
| `unavailable` | Held positions exist, but none can be valued |
| `empty_portfolio` | No held positions exist |

## Scenario catalog configuration

`PORTFOLIO_STRESS_SCENARIOS_PATH` is an optional local YAML catalog path
(maximum 1,024 characters). It is exposed through the shared Config loader and
configuration registry. The catalog is limited to 256 KiB, 64 scenarios, 16
shocks per scenario, 32 YAML alias markers, and nesting depth 8. YAML uses safe
loading and scenario IDs override built-ins.

Reload is atomic: an invalid later file keeps the last validated catalog for
that path. If no valid catalog has loaded, the API returns a sanitized `503`
without exposing the configured filesystem path. An unset path uses built-ins.

## Deliberate limitations

- Deterministic instantaneous shocks only; no historical path replay.
- Linear factor additivity; no nonlinear, liquidity, or correlation effects.
- Missing market beta falls back to unit beta with an explicit label.
- Rate sensitivity is uniform unless the caller supplies a bounded override.
- No market data provider calls occur on the stress-test hot path.
