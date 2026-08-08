# Analysis Delta Comparison (Service Contract)

English technical note for Issue #148 / T17. Web comparison UI is owned by a follow-up task (T18) and is **not** covered here.

## Purpose

When the same stock is analyzed more than once, callers need a **deterministic** answer to “what changed since run A?” without re-reading the full report. The comparison lives in `src/services/history_comparison_service.py` and is pure data-structure diff — not an LLM rewrite of the delta.

## Public API

```python
from src.services.history_comparison_service import (
    compare_analyses,
    get_latest_delta,
    AnalysisDelta,
)

# Arbitrary two runs (run_id == AnalysisHistory.query_id)
delta = compare_analyses(stock_code, base_run_id, target_run_id)

# Convenience: two most recent history rows for the stock
delta = get_latest_delta(stock_code)
```

### `AnalysisDelta` fields

| Field | Meaning |
| --- | --- |
| `has_baseline` | `True` only when both runs exist and yield comparable snapshots |
| `baseline_status` | `ok` / `missing_history` / `missing_base` / `missing_target` / `incomparable_structure` |
| `baseline_reason` | Human-readable reason when `has_baseline` is `False` |
| `base_run_id` / `target_run_id` | Compared `query_id` values |
| `stock_code` | Normalized stock code |
| `has_material_changes` | `True` when any change bucket is non-empty |
| `conclusion_changes` | Action / confidence / sniper levels |
| `score_changes` | Sentiment score and dimension scores (e.g. `dimension.trend_score`) |
| `evidence_changes` | Added/removed key points, catalysts, verified facts, data sources |
| `risk_changes` | Added/removed risk alerts, risk warnings, strata counter-evidence |

Use `delta.to_dict()` for JSON-friendly serialization.

## No baseline vs no change

These must never be confused:

| Situation | `has_baseline` | `baseline_status` | Change buckets |
| --- | --- | --- | --- |
| First analysis / only one history row / empty history | `False` | `missing_history` | empty |
| Requested base or target run id not found | `False` | `missing_base` / `missing_target` | empty |
| Snapshot cannot be projected | `False` | `incomparable_structure` | empty |
| Two valid runs with identical comparable fields | `True` | `ok` | empty (`has_material_changes=False`) |
| Two valid runs with differences | `True` | `ok` | non-empty |

## Comparable fields (current history surface)

Persisted on `analysis_history` or inside `raw_result` / `dashboard`:

**Comparable today**

- Conclusion: `operation_advice`, structured `action` / `action_label`, `confidence_level`, sniper `ideal_buy` / `stop_loss` / `take_profit` (columns preferred, then dashboard)
- Scores: `sentiment_score`; `dashboard.data_perspective.trend_status.trend_score` (and other `*_score` keys when present)
- Evidence: `key_points`, `dashboard.intelligence.positive_catalysts`, `report_strata.verified_facts`, `data_sources`
- Risks: `dashboard.intelligence.risk_alerts`, `risk_warning`, `report_strata.risks_counter_evidence`

**Not comparable without schema work (out of T17 scope)**

- Free-form narrative sections (`trend_analysis`, full markdown body)
- Fields not persisted on history rows (runtime-only context that never entered `raw_result`)
- Cross-language semantic equality of free text beyond exact token match after split/normalize

## Numeric rules

- Only **finite** numbers participate in numeric deltas (`math.isfinite`).
- `None`, empty strings, NaN, ±Infinity → no forged numeric delta; the field is reported as non-comparable (`direction=unavailable`) when one side has a present non-finite value.

## Integration notes (T18 and report layer)

- This module does **not** render markdown, templates, or Web UI.
- Consumers (report top section, Web version compare, notifications) should call `compare_analyses` / `get_latest_delta` and format the structured delta themselves.
- Do not invent a parallel comparison implementation in agent or renderer code.

## Rollback

Revert the PR that introduced the service methods. No database migration is required.
