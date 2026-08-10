# Plan: Portfolio allocation & rebalancing recommendations (V1)

**Status:** BLOCKED — waiting on risk metrics PR **#812** to merge  
**Issue:** [#237](https://github.com/SiinXu/stock-pulse-ai/issues/237)  
**Branch:** `feat/portfolio-rebalancing-v1`  
**Hard dependency:** [#812](https://github.com/SiinXu/stock-pulse-ai/pull/812) `feat: add portfolio risk metrics service` (must be **MERGED**; implement against its **merged** public surface, not a guessed API)

This document is the V1 implementation plan only. **No production service, API, or tests are implemented on this branch until #812 lands.**

---

## 1. Why blocked

Rebalancing recommendations consume portfolio **VaR**, **pairwise correlation**, and **concentration / diversification** metrics. Those are introduced by #812 as:

| Surface | Path / symbol |
| --- | --- |
| Service | `src/services/portfolio_risk_metrics_service.py` → `PortfolioRiskMetricsService.get_risk_metrics(...)` |
| HTTP | `GET /api/v1/portfolio/risk-metrics` (`operation_id=getPortfolioRiskMetrics`) |
| Schemas | `api/v1/schemas/portfolio_risk_metrics.py` |
| Docs | `docs/portfolio-risk-metrics.md` + `_EN.md` |

As of plan commit time, #812 is **OPEN** (`mergedAt: null`). Building against an unmerged head risks contract drift. Resume only after merge, then re-read the **merged** module and OpenAPI artifacts.

### #812 public contract to consume (preview from open PR head — verify post-merge)

**Inputs (re-use as-is):**

- Holdings / weights via `PortfolioService.get_portfolio_snapshot(..., include_realtime=False)` (no provider hot path).
- Risk block via `PortfolioRiskMetricsService.get_risk_metrics(...)` returning a dict matching `PortfolioRiskMetricsResponse`.

**Key response fields (do not invent alternatives):**

```text
status: ok | empty_portfolio | insufficient_history | partial
portfolio_value, positions_used, currency, as_of, account_id, cost_method
assumptions: {...}   # always present; rebalancing must extend/compose, not hide
var:
  status, var_pct, var_value, observation_count, confidence, horizon_days, ...
correlation:
  status, symbols[], matrix[][], observation_count, ...
concentration:
  status, hhi, effective_n, diversification_score, top_weight_pct,
  position_count, weights[{symbol, weight_pct}]
history: aligned_trading_days, ...
```

**Honesty rules inherited from #812:**

- Insufficient history → explicit status + null metrics (never silent zeros).
- Empty portfolio → `empty_portfolio` / no fabricated risk.
- Static current weights over lookback; √time multi-day VaR — disclosed in assumptions.

---

## 2. V1 scope (backend-only)

### In scope

1. **`src/services/portfolio_rebalancing_service.py`**
   - Risk-preference → **target allocation model** (risk-based, using #812 metrics).
   - **Drift detection** (current vs target weights / concentration caps).
   - **Concrete suggested adjustments** (trim / add weight deltas) with per-suggestion **rationale**, **assumptions**, and **“not investment advice”** framing.
   - **Explicit refusal** when data is insufficient or portfolio empty.

2. **ONE read-only API pair**
   - Endpoint module + response schemas (`response_model`).
   - Auth identical to neighboring `/api/v1/portfolio/*` routes (global admin session when enabled).
   - `api/v1/router.py` **append-only** include.
   - Regenerated `apps/dsa-web/openapi.json` + `apps/dsa-web/src/types/api.generated.ts`.

3. **Deterministic tests** (new files only)
   - Fixture portfolios → known-answer suggestions.
   - Insufficient-history / partial risk → refusal to recommend (no partial “fake” trades).
   - Empty portfolio.

4. **Bilingual docs** (formulas + assumptions + disclaimer) + append-only `docs/CHANGELOG.md` / INDEX.

### Out of scope (explicit fences)

| Fence | Owner / reason |
| --- | --- |
| Web / PortfolioPage UI | Open **#790** owns PortfolioPage; Web surface = **follow-up comment on #237** only |
| What-if scenario engine, tax/transaction-cost optimizer | Issue backlog; V1 may expose **estimated** simple turnover only if fully deterministic and disclosed |
| Market-regime agent integration (#220), stress testing (#210) | Separate issues |
| Edits to `portfolio_risk_metrics_service.py` / `portfolio_risk_service.py` | Consume; do not own |
| Live provider calls on hot path | Forbidden (match #812) |
| Shared file races | CHANGELOG, `.env.example`, `router.py` are **append-only** |

---

## 3. Proposed API (subject to post-#812 merge review)

```http
GET /api/v1/portfolio/rebalancing-recommendations
```

**Query parameters (draft):**

| Parameter | Default | Notes |
| --- | --- | --- |
| `account_id` | all active | Same as risk-metrics |
| `as_of` | today | Snapshot date |
| `cost_method` | `fifo` | Passed through |
| `risk_tolerance` | `moderate` | Enum: `conservative` \| `moderate` \| `aggressive` |
| `drift_threshold_pct` | `5.0` | Per-position absolute weight drift (percentage points) that triggers a suggestion |
| `confidence` / `horizon_days` / `lookback_trading_days` | #812 defaults | Forwarded into risk-metrics computation |

**Auth:** same as portfolio neighbors.

**`operation_id`:** `getPortfolioRebalancingRecommendations`

### Response shape (draft)

```jsonc
{
  "as_of": "YYYY-MM-DD",
  "account_id": null,
  "cost_method": "fifo",
  "currency": "CNY",
  "status": "ok | empty_portfolio | insufficient_data | refused",
  "status_message": "...",
  "disclaimer": "Research aid only — not investment advice. ...",
  "risk_tolerance": "moderate",
  "target_model": {
    "name": "risk_band_v1",
    "description": "...",
    "max_single_weight_pct": 25.0,
    "min_effective_n": 4.0,
    "max_hhi": 0.35,
    "target_var_pct_ceiling": 3.5,
    "notes": ["..."]
  },
  "current": {
    "portfolio_value": 0.0,
    "weights": [{"symbol": "AAPL", "weight_pct": 40.0}],
    "risk_status": "ok",
    "var_pct": 2.1,
    "hhi": 0.28,
    "effective_n": 3.6,
    "diversification_score": 0.7
  },
  "drift": {
    "max_abs_weight_drift_pct": 15.0,
    "breaches": [
      {
        "kind": "single_name_cap",
        "symbol": "AAPL",
        "current_pct": 40.0,
        "limit_pct": 25.0,
        "drift_pct": 15.0
      }
    ]
  },
  "suggestions": [
    {
      "action": "trim",
      "symbol": "AAPL",
      "from_weight_pct": 40.0,
      "to_weight_pct": 25.0,
      "delta_weight_pct": -15.0,
      "approx_notional": 15000.0,
      "rationale": "Single-name weight exceeds conservative/moderate band cap...",
      "assumptions": [
        "Static current market-value weights; no tax lot optimization.",
        "Targets are rule-based risk bands, not personal financial advice."
      ]
    }
  ],
  "assumptions": {
    "method": "risk_band_drift_v1",
    "uses_risk_metrics": true,
    "risk_metrics_source": "PortfolioRiskMetricsService",
    "provider_calls_on_hot_path": false,
    "tax_and_transaction_costs": "not_modeled_v1",
    "recommendation_honesty": "explicit_refusal_when_insufficient_data"
  },
  "risk_metrics_summary": {
    "status": "ok",
    "var_status": "ok",
    "correlation_status": "ok",
    "concentration_status": "ok"
  }
}
```

### Refusal contract (required)

| Condition | `status` | `suggestions` |
| --- | --- | --- |
| No equity holdings / zero MV | `empty_portfolio` | `[]` + clear message |
| Risk metrics `empty_portfolio` | `empty_portfolio` | `[]` |
| VaR or correlation `insufficient_history` when model requires them | `insufficient_data` | `[]` — **refuse**, do not invent trades |
| Risk metrics overall `partial` and required block missing | `insufficient_data` or `refused` | `[]` |
| No drift above threshold and concentration within band | `ok` | `[]` with message “within tolerance” |

Every non-empty suggestion **must** include `rationale` + `assumptions` + top-level `disclaimer`.

---

## 4. Target-allocation model (risk_band_v1)

Deterministic rule table (tunable constants; document in bilingual docs; optional env keys only if needed — prefer code constants for V1 to avoid config sprawl):

| `risk_tolerance` | max single weight | min effective N | max HHI | illustrative VaR ceiling (1d, 95%) |
| --- | --- | --- | --- | --- |
| `conservative` | 15% | 6.0 | 0.22 | 2.0% |
| `moderate` | 25% | 4.0 | 0.35 | 3.5% |
| `aggressive` | 40% | 2.5 | 0.50 | 6.0% |

**Drift / suggestion algorithm (V1):**

1. Load snapshot weights (equity only, cash excluded — same as #812).
2. Call `PortfolioRiskMetricsService.get_risk_metrics(...)` with forwarded params.
3. If refuse conditions → return empty suggestions + status.
4. Build breaches:
   - Single-name weight > band cap → suggest **trim** to cap (proportional residual redistributed to underweight names if multi-name; V1 may only emit trims + equal-rest residual note).
   - HHI / effective_n outside band → suggest diversifying trims on top contributors (using concentration weights + high pairwise correlation pairs from matrix when status is `ok`).
   - Optional: if `var_pct` above ceiling and concentration ok, prefer trims on highest-weight names with highest average correlation to peers (deterministic sort key: `(weight_pct, avg_corr, symbol)`).
5. Filter suggestions with `|delta_weight_pct| < drift_threshold_pct` unless hard cap breach.
6. Attach rationale strings that cite the **numeric breach** and **band rule** (no LLM in V1).

**What V1 does not do:**

- Optimize mean-variance frontiers.
- Estimate taxes, commissions, or market impact (state `not_modeled_v1`).
- Auto-execute trades or write portfolio ledger.

---

## 5. File plan (post-unblock)

```text
src/services/portfolio_rebalancing_service.py          # NEW
api/v1/endpoints/portfolio_rebalancing.py              # NEW
api/v1/schemas/portfolio_rebalancing.py                # NEW
api/v1/router.py                                       # APPEND include only
tests/services/test_portfolio_rebalancing_service.py   # NEW
tests/api/test_portfolio_rebalancing_api.py            # NEW
docs/portfolio-rebalancing.md                          # NEW (CN)
docs/portfolio-rebalancing_EN.md                       # NEW (EN)
docs/INDEX.md / docs/INDEX_EN.md                       # APPEND links
docs/CHANGELOG.md                                      # APPEND [Added] line
apps/dsa-web/openapi.json                              # regenerate
apps/dsa-web/src/types/api.generated.ts                # regenerate
```

Optional config: only if product requires runtime thresholds; otherwise constants + query params. If keys are added → update `.env.example` (append-only).

---

## 6. Test plan (deterministic known-answer)

| Case | Fixture | Expected |
| --- | --- | --- |
| Empty portfolio | snapshot with no positions | `status=empty_portfolio`, `suggestions=[]` |
| Insufficient history | mock risk metrics `var.status=insufficient_history` | `status=insufficient_data`, refuse |
| Single-name overload | one name 60% weight, moderate band | one trim suggestion to 25%, rationale cites cap |
| Within band | equal-weight 4 names, moderate | `suggestions=[]`, within-tolerance message |
| Correlation-aware trim order | fixed matrix + weights | deterministic order by documented sort key |

Mock `PortfolioRiskMetricsService` / portfolio snapshot at service boundary; API tests mirror #812 auth + `response_model` patterns.

Fast verify (mission):

```bash
python -m py_compile \
  src/services/portfolio_rebalancing_service.py \
  api/v1/endpoints/portfolio_rebalancing.py \
  api/v1/schemas/portfolio_rebalancing.py \
  api/v1/router.py

python -m pytest tests -k rebalanc -m "not network and not benchmark"
```

---

## 7. Recommendation honesty (non-negotiable)

- Top-level `disclaimer` always present (align with portfolio UI manual: research aid, **not investment advice**).
- Every suggestion: `rationale` + `assumptions[]`.
- Insufficient data → **refuse**, never fill with plausible-looking zeros or invented allocations.
- Document formulas, band table, and non-goals in bilingual docs.

---

## 8. Resume checklist (when #812 merges)

1. `git fetch --all --prune`; rebase/merge latest `origin/main` (with #812).
2. Confirm public API of `PortfolioRiskMetricsService` and OpenAPI path `/portfolio/risk-metrics` match this plan; update plan if merged surface drifted.
3. Implement service + API + tests + docs per sections 3–6.
4. Fast verify commands above; record exact pass counts.
5. Freshness pass vs `origin/main`; avoid #790 Web files; append-only shared files.
6. Open/ready PR title: `feat: add allocation and rebalancing recommendations`; `Refs #237`.
7. Comment on #237: Web Portfolio surface deferred (owned by #790); backend V1 landed / link PR.
8. HANDOFF with verification evidence.

---

## 9. Rollback

If implementation PR merges later: revert that PR (endpoint + service + docs + OpenAPI). No DB migration expected for V1.

---

## 10. HANDOFF (current)

```text
HANDOFF: needs-owner — waiting on #812
```

Blockers:

1. **#812 not merged** — cannot build against final risk-metrics API.
2. Implementation intentionally not started on this branch (plan-only DRAFT).

Unblock trigger: #812 state = MERGED; then reassign / resume on `feat/portfolio-rebalancing-v1`.
