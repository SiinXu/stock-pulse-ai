# Information Quality Grading and Forced Conclusion

Issue reference: [#123](https://github.com/SiinXu/stock-pulse-ai/issues/123). Related quality-gate design: [#887](https://github.com/SiinXu/stock-pulse-ai/issues/887). Validation inputs come from the financial data validation layer ([#185](https://github.com/SiinXu/stock-pulse-ai/issues/185), `docs/data-validation-layer.md`).

## Boundary

Information quality grading **consumes** existing AnalysisContextPack `data_quality` artifacts:

- block statuses and limitations from `AnalysisContextBuilder`
- versioned `data_quality_evidence.v1` findings from `src/data_provider/data_validation.py`

It does **not** re-validate OHLCV, fundamentals, or indicators, and it does not invent a second scoring pipeline.

Public overview `blocks` are list-shaped (`[{key, status}, ...]`). Grading normalizes that list (or the pack mapping) before scoring and prefers a precomputed `info_quality` payload when block status inputs are absent, so it never invents core-block `"missing"` from an empty block list.

| Configuration | Default | Contract |
| --- | --- | --- |
| `INFO_QUALITY_GRADING_ENABLED` | `true` | Derive A/B/C grades and attach them to reports, DecisionSignal, and prompts. When disabled, grade metadata and grade-driven prompt rules are absent. |
| `FORCED_CONCLUSION_ENABLED` | `true` | Attach Pass / Fail / Watch conclusions and enable grade-driven action/Risk Manager constraints. When disabled, grades remain visible but cannot change the action. |

Both flags are loaded by the typed `Config` owner and registered under data-source Settings. They are independent: grading can remain visible without forced action changes, and a forced stance can remain visible without claiming a grade when grading is disabled.

## Grade contract (`info-quality-v1`)

Overall grade is the worst of:

1. Mapped AnalysisContextPack quality level (`good→A`, `usable→B`, `limited|poor→C`)
2. **Source reliability** — reject evidence, fetch_failed/missing core blocks, fallback/estimated
3. **Timeliness** — stale/partial core blocks or stale provenance
4. **Consistency** — cross-source divergence and related validation codes

The scorer is deterministic and fail-closed. Missing core status, unknown status values, malformed validation records, duplicate overview block keys, non-finite/out-of-range scores, or incomplete precomputed grade payloads cannot be promoted to a clean grade. A later public projection is merged with the precomputed builder grade using the worse result, so sanitization cannot improve risk.

| Grade | Meaning | Conclusion constraint |
| --- | --- | --- |
| `A` | Clean validation-backed inputs | Pass/Fail/Watch allowed as mapped from action |
| `B` | Acceptable with warnings | Pass allowed but marked uncertain |
| `C` | Weak / incomplete / rejected | Pass blocked → Watch with uncertainty; visible warning |

Payload path (report): `dashboard.info_quality`.

## Forced conclusion (`forced-conclusion-v1`)

| Stance | Mapped actions |
| --- | --- |
| `Pass` | `buy`, `add` |
| `Fail` | `sell`, `reduce`, `avoid` |
| `Watch` | `hold`, `watch`, `alert` (and any blocked Pass) |

Payload path (report): `dashboard.forced_conclusion`. DecisionSignal stores the same under `metadata.forced_conclusion` / `metadata.info_quality` and enriches `data_quality_summary`.

Hard rules:

1. **No evidence-free Pass** — all quote / daily / technical blocks must carry recognized evidence-backed statuses; otherwise Pass becomes Watch.
2. **Grade C Pass blocked** — actionable buy/add is rewritten to Watch with low confidence and a risk warning.
3. **Prompt constraints** — AnalysisContextPack prompt sections include grade lines and forbid inventing numbers absent from available evidence.

## Integration surfaces

| Surface | Behavior |
| --- | --- |
| Context pack build | `data_quality.metadata.info_quality` derived after validation-backed quality assembly |
| Pipeline (legacy + agent) | `apply_info_quality_constraints` after phase/market guardrails; agent path refreshes after Risk Manager |
| Risk Manager | Dashboard grade `C` injects high-severity evidence code `info_quality_grade_c` |
| Report templates | Decision card shows grade and forced stance |
| DecisionSignal | Metadata + data_quality_summary carry grade and stance |
| Trace | Dashboard fields and risk-gate evidence codes remain on analysis history / runtime facts |

## Compatibility and rollback

- Additive dashboard/metadata fields; historical reports without them remain valid.
- `FORCED_CONCLUSION_ENABLED=false` restores the prior unconstrained action while retaining the grade surface; `INFO_QUALITY_GRADING_ENABLED=false` removes grade metadata and grade-driven prompt rules without fabricating a neutral grade.
- Immediate rollback: `INFO_QUALITY_GRADING_ENABLED=false` and/or `FORCED_CONCLUSION_ENABLED=false`, or revert the introducing change.
