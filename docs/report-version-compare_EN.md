# Report version comparison

[中文](report-version-compare.md) | [English](report-version-compare_EN.md)

Issue #188 / T18: users can select any two analysis history runs for the same symbol and review field differences plus configuration fingerprint differences side by side.

## Scope

- Version picker: `GET /api/v1/report-version-compare/runs?stock_code=...`
- Compare: `GET /api/v1/report-version-compare/compare?stock_code=...&base_run_id=...&target_run_id=...`
- Web page: `/research/report-compare`
- Does **not** implement the T17 comparison engine (`compare_analyses` in `src/services/history_comparison_service.py`)

## Status contract

| status | Meaning |
| --- | --- |
| `ok` | T17 returned an AnalysisDelta with `has_baseline=true` |
| `engine_pending` | T17 is not wired yet; side-by-side fields and config fingerprint diffs still render. **Not “no change”** |
| `no_baseline` | T17 returned `has_baseline=false`. **Not “no change”** |
| `incomparable` | Runs cannot be compared (for example, different symbols) |

## Severity grading (presentation layer)

- **major**: conclusion action reversal (e.g. buy/add ↔ sell/reduce/avoid)
- **moderate**: non-reversal action change, large score moves, model differences
- **minor**: small score tweaks or summary text drift
- **none**: field unchanged

Configuration fingerprint differences are shown in a dedicated panel so config-driven deltas are not misread as market moves.

## Integration Point (after T17 merges)

T17 delivers in `src/services/history_comparison_service.py`:

```python
def compare_analyses(stock_code: str, base_run_id: str, target_run_id: str) -> AnalysisDelta: ...
```

T18 already auto-discovers that function via `resolve_compare_analyses()` in `src/services/report_version_compare_adapter.py`. Endpoint signatures do not need to change. Integrators only need T17 merged and importable.

Tests may inject fixtures with `ReportVersionCompareService(compare_fn=...)`.

## Optional navigation wiring

This task does not modify `SidebarNav` or `ResearchOverviewPage` (frozen / contested in the batch). After merge, research overview can add:

```tsx
{
  key: 'report-compare',
  titleKey: /* new i18n key */,
  descriptionKey: /* new i18n key */,
  to: APP_ROUTE_PATHS.researchReportCompare,
  icon: GitCompareArrows,
}
```

## Related files

- `src/services/report_version_compare_service.py`
- `src/services/report_version_compare_adapter.py`
- `api/v1/endpoints/report_version_compare.py`
- `apps/dsa-web/src/pages/ReportVersionComparePage.tsx`
- `apps/dsa-web/src/components/report-version-compare/`
