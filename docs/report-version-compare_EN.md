# Report version comparison

[中文](report-version-compare.md) | [English](report-version-compare_EN.md)

Issue #188 / T18: users can select two runs for the same symbol from analysis history, or enter from Stock Details, and review typed report and configuration differences side by side. Issue #188 remains open for structured risk/catalyst diffing and explicit behavior when optional multi-agent sections are absent.

## Scope

- Version picker: `GET /api/v1/report-version-compare/runs?stock_code=...`
- Compare: `GET /api/v1/report-version-compare/compare?stock_code=...&base_run_id=...&target_run_id=...`
- Web page: `/research/report-compare`
- Reuses the merged T17 comparison engine (`compare_analyses` in `src/services/history_comparison_service.py`); T18 does not duplicate comparison logic
- Uses unique `AnalysisHistory.id` values as version identity. `query_id` is correlation metadata and may repeat.
- Excludes `market_review` before count/pagination unless that report type is explicitly requested

## Status contract

| status | Meaning |
| --- | --- |
| `ok` | T17 returned an AnalysisDelta with `has_baseline=true` |
| `engine_pending` | The merged engine is unavailable at runtime; side-by-side fields and config provenance still render. **Not “no change”** |
| `no_baseline` | T17 returned `has_baseline=false`. **Not “no change”** |
| `incomparable` | Runs cannot be compared (for example, different symbols) |

## Severity grading (presentation layer)

- **major**: conclusion action reversal (e.g. buy/add ↔ sell/reduce/avoid)
- **moderate**: non-reversal action change, large score moves, model differences
- **minor**: small score tweaks or summary text drift
- **none**: field unchanged

Configuration fingerprint differences are shown in a dedicated panel so config-driven deltas are not misread as market moves. A fingerprint is emitted only when the persisted run contains the required model, report, provider route, model route, profile, and configuration-version provenance. Incomplete provenance is shown as `unknown`, never as identical.

## Identity and typed delta contract

T17 delivers in `src/services/history_comparison_service.py`:

```python
def compare_analyses(stock_code: str, base_record_id: int, target_record_id: int) -> AnalysisDelta: ...
```

The HTTP API keeps `base_run_id` / `target_run_id` parameter names for compatibility, but their values are primary history IDs and are passed to T17 as integers. The public projection preserves baseline status/reason, primary IDs, trace query IDs, stock/report identity, material-change status, typed scalar changes, and typed evidence/risk list changes. Persisted scores outside the finite 0–100 contract become `null`; complete responses serialize with strict JSON.

Tests may inject fixtures with `ReportVersionCompareService(compare_fn=...)`.

## Web recovery and history depth

- The picker loads 50 stable, descending records per page and exposes **Load more versions** until the server-reported total is reached.
- Draft stock input and loaded stock identity are separate. Editing the draft invalidates old selections and results.
- Retry is operation-owned: list failures repeat the list request; compare failures repeat the same compare inputs without reloading versions or clearing selections.

## Navigation and prefill

- Analysis Workbench History shows **Compare** after two records for the same stock are selected, then carries the stock code plus baseline and target history primary keys to the comparison page.
- Stock Details provides a **Report version compare** action that carries the canonical stock code to the comparison page.
- The page accepts `stock`, `baseRunId`, and `targetRunId` query parameters. `stock` triggers version loading; when both run IDs are distinct positive safe integers, comparison starts automatically after the list loads.
- Invalid or missing run IDs do not start comparison. Users can still choose runs manually from the loaded picker.

## Related files

- `src/services/report_version_compare_service.py`
- `src/services/report_version_compare_adapter.py`
- `api/v1/endpoints/report_version_compare.py`
- `apps/dsa-web/src/pages/ReportVersionComparePage.tsx`
- `apps/dsa-web/src/components/report-version-compare/`
