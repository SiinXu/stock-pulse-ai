# Paper-trading decision process quality (Issue #1134)

中文版见 [paper-decision-quality_CN.md](paper-decision-quality_CN.md)。

## Purpose

Score **simulated paper trades on process discipline**, not realized return:

| Dimension | What it checks |
| --- | --- |
| `analysis_support` | Linked DecisionSignal / analysis plan, action alignment, reason, plan quality |
| `risk_gate_compliance` | Invalidation or stop-loss, confidence, data quality / gaps, trade vs signal action |
| `position_discipline` | Size / concentration vs `PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT`, smaller size when data quality is weak |

**Not scored:** win rate, average return, hit/miss, calibration. Those remain owned by DecisionSignal post-hoc calibration and the personal performance outcome surface ([#987](https://github.com/SiinXu/stock-pulse-ai/issues/987)).

## Division of labor (personal performance domain)

| Owner | Issue | Owns |
| --- | --- | --- |
| Process quality (this feature) | #1134 | Process scores for paper trades; composable API for a personal-performance **process** panel |
| Outcome / calibration | #987 | Win rate, realized return, style calibration dashboard |

Both may appear under a personal performance view. This API never redefines outcome semantics and labels every payload with `score_kind: "process"`.

## Formula

- `formula_version`: `paper-decision-quality-v2`
- Default weights: analysis 0.40, risk-gate 0.35, position 0.25
- Unavailable dimensions are dropped and remaining weights re-normalized
- Score range: 0–100
- Every dimension emits machine `code` + human-readable `message` reasons
- Evidence block records linked signal id/action, size inputs, equity basis, signal candidate count / ambiguity, and any ignored return field names present on the input
- **Position discipline uses the resulting same-symbol position weight from a read-only trade-date snapshot**, not just the current trade notional and not the account’s latest equity. Evidence fields include `equity_basis=trade_date_snapshot`, `position_basis=trade_date_position`, and `equity_as_of`.

## API

```http
GET /api/v1/portfolio/accounts/{account_id}/paper-decision-quality
```

Query:

- `date_from` / `date_to` (optional trade date filters)
- `limit` (1–200, default 50)

The response distinguishes the scored page (`sample_size`) from all matching trades (`total_trade_count`) and sets `truncated=true` when `limit` omits trades. Account aggregation therefore describes only the disclosed scored sample.

Requires a **paper** account (`account_type=paper` via the #370 sidecar). Real accounts return `400 paper_account_required`.

Signal linkage: DecisionSignals for the same stock code with `created_at` within 7 calendar days before the trade date (inclusive). For a trade recorded on that same day, the trade creation time is the strict upper bound, so a later signal cannot justify an earlier trade. Action-aligned candidates are preferred. When more than one eligible candidate remains, no signal is fabricated: signal-dependent dimensions are unsupported and evidence sets `signal_linkage_status=ambiguous`, `signal_linkage_ambiguous=true`, and `signal_candidate_count`.

## Service entry points

| Path | Role |
| --- | --- |
| `src/services/paper_decision_quality_service.py` | Scorer + account aggregation |
| `score_paper_decision_context(context)` | Pure fixture / offline entry (no I/O) |
| `src/api/v1/endpoints/paper_decision_quality.py` | HTTP surface |

## Tests

```bash
python -m pytest tests/services/test_paper_decision_quality_service.py -q
```

Acceptance fixtures: two decisions with the **same** fabricated PnL but different discipline produce different process scores; flipping only PnL fields does not change the score.

## Non-goals

- No automatic rebalancing or trade blocking
- No marketing claim of guaranteed returns
- No replacement of public signal scorecard (#379) or portfolio health (#151)
- No schema migration; trades are not rewritten with score columns
