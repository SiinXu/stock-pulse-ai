# Analysis Delta Comparison (Service Contract)

English technical note for Issue #148 / T17. Web comparison UI is owned by a follow-up task (T18) and is **not** covered here.

## Purpose

When the same stock is analyzed more than once, callers need a **deterministic** answer to “what changed since history version A?” without re-reading the full report. The comparison lives in `src/services/history_comparison_service.py` and is a pure data-structure diff — not an LLM rewrite of the delta.

## Public API

```python
from src.services.history_comparison_service import (
    compare_analyses,
    get_latest_delta,
    AnalysisDelta,
)

# Arbitrary two persisted versions (record id == AnalysisHistory.id)
delta = compare_analyses(stock_code, base_record_id, target_record_id)

# Convenience: two most recent rows for one stock/report shape
delta = get_latest_delta(stock_code, report_type="simple")
```

### `AnalysisDelta` fields

| Field | Meaning |
| --- | --- |
| `has_baseline` | `True` only when both records exist and yield comparable snapshots |
| `baseline_status` | `ok` / `missing_history` / `missing_base` / `missing_target` / `incomparable_structure` |
| `baseline_reason` | Human-readable reason when `has_baseline` is `False` |
| `base_record_id` / `target_record_id` | Unique compared `AnalysisHistory.id` primary keys |
| `base_query_id` / `target_query_id` | Non-unique correlation metadata; these values may be equal |
| `stock_code` | Normalized stock code |
| `report_type` | Shared persisted report type for the compared records |
| `has_material_changes` | `True` when any change bucket is non-empty |
| `conclusion_changes` | Action / confidence / sniper levels |
| `score_changes` | Sentiment score and dimension scores (e.g. `dimension.trend_score`) |
| `evidence_changes` | Added/removed key points, catalysts, verified facts, data sources |
| `risk_changes` | Added/removed risk alerts, risk warnings, strata counter-evidence |

Use `delta.to_dict()` for strict-JSON serialization. `json.dumps(delta.to_dict(), allow_nan=False)` is supported.

## Identity, ordering, and snapshot contract

| Concern | Contract |
| --- | --- |
| Version identity | `AnalysisHistory.id`; it is the unique primary key used by `compare_analyses` |
| Correlation metadata | `query_id`; it can repeat for batches, retries, and recovered persistence and is never called a run/version id |
| Latest ordering | `created_at DESC, id DESC`; the primary key deterministically breaks timestamp ties |
| Latest read | One storage query filtered by `stock_code` and explicit `report_type`, ordered as above, with `LIMIT 2` |
| Concurrent insert/delete | `get_latest_delta` compares the two row values returned by that query directly; it does not re-resolve them by `query_id` |
| Baseline age | No age cutoff. A prior row remains eligible regardless of whether it is older than 365 days |

Comparing a record id with itself is a valid exact comparison: `has_baseline=True`, `baseline_status=ok`, and no material changes. A row deleted before an explicit primary-key lookup yields `missing_base` or `missing_target`; a deletion after the latest-pair query does not change the already-selected snapshot.

## No baseline vs no change

These must never be confused:

| Situation | `has_baseline` | `baseline_status` | Change buckets |
| --- | --- | --- | --- |
| First analysis / only one matching history row / empty history | `False` | `missing_history` | empty |
| Requested base or target record id not found | `False` | `missing_base` / `missing_target` | empty |
| Snapshot cannot be projected | `False` | `incomparable_structure` | empty |
| Two valid records with identical comparable fields | `True` | `ok` | empty (`has_material_changes=False`) |
| Two valid records with differences | `True` | `ok` | non-empty |

## Report-type boundary

Latest comparison is **within one explicit persisted report type**. `get_latest_delta` requires `report_type` and filters storage before selecting two rows, so a newer `full`, `brief`, `market_review`, or other shape cannot become the baseline/target for a `simple` request. Explicit `compare_analyses` accepts exact record ids but returns `incomparable_structure` when the two records have different or missing report types. This service does not claim projection compatibility across report shapes.

## Comparable fields (current history surface)

Persisted on `analysis_history` or inside `raw_result` / `dashboard`:

**Comparable today**

- Conclusion: `operation_advice`, structured `action` / `action_label`, `confidence_level`, sniper `ideal_buy` / `stop_loss` / `take_profit` (columns preferred, then dashboard)
- Scores: `sentiment_score`; dashboard trend, volume, momentum, and fundamental scores from their documented `data_perspective` locations when present
- Evidence: `key_points`, `dashboard.intelligence.positive_catalysts`, `report_strata.verified_facts`, `data_sources`
- Risks: `dashboard.intelligence.risk_alerts`, `risk_warning`, `report_strata.risks_counter_evidence`

**Not comparable without schema work (out of T17 scope)**

- Free-form narrative sections (`trend_analysis`, full markdown body)
- Fields not persisted on history rows (runtime-only context that never entered `raw_result`)
- Cross-language semantic equality of free text beyond exact token match after split/normalize

## Numeric and strict-JSON rules

- Only **finite** numbers participate in numeric deltas (`math.isfinite`).
- Integer, float, and numeric-string zero are preserved. A real `5 → 0` change is a finite decrease.
- Missing, invalid, NaN, and ±Infinity inputs never appear as NaN/Infinity in public output. An unavailable side is serialized as `null`, `comparable=false`, `direction=unavailable`, plus `unavailability.base` / `unavailability.target` with stable reasons: `missing_value`, `invalid_number`, or `non_finite_number`.
- Every conclusion and score change is strict-JSON safe; evidence/risk values are strings.

## Deterministic payload bounds

Evidence/risk list changes are sorted and deduplicated. Each public `added`, `removed`, and `unchanged` list contains at most 100 items, and each item contains at most 512 characters (long items include a stable SHA-256 suffix). `added_total`, `removed_total`, `unchanged_total`, and `output_truncated` disclose omitted output details instead of silently hiding them. The latest storage selection remains fixed at two rows.

## Integration notes (T18 and report layer)

- This module does **not** render markdown, templates, or Web UI.
- Consumers (report top section, Web version compare, notifications) should call `compare_analyses` / `get_latest_delta` with primary-key record ids or an explicit report type and format the structured delta themselves.
- Do not invent a parallel comparison implementation in agent or renderer code.

## Rollback

Revert the PR that introduced the service methods. No database migration is required.
