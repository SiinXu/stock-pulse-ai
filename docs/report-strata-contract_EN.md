# Report Strata Contract

[中文](report-strata-contract.md) | [English](report-strata-contract_EN.md)

## Purpose

Issue #616 requires analysis reports to present **fixed evidence strata** so fluent model prose is not read as verified investment fact. This is a presentation and payload contract. It does **not** replace the full exportable audit package tracked in #127.

## Six strata (product order)

1. **Verified facts** — statements with optional `source_id` and `as_of` when available  
2. **Missing data or source conflicts** — gaps that must not be folded into facts  
3. **Model inference** — judgment, forecasts, and narrative conclusions  
4. **Risks / counter-evidence**  
5. **Alignment with user framework** — uses the local personal framework slot from #465; when none is active, status is `not_configured` with an explicit summary  
6. **Non-investment-advice disclaimer** — always visible on user-facing formats

## Schema

- Domain model: `src/schemas/report_strata.py` (`report-strata-v1`)
- Additive field on analysis dashboard / report JSON: `dashboard.report_strata` (preferred) or top-level `report_strata`
- Historical reports may omit the field entirely and must still render
- `AnalysisReportSchema` remains `report-v1` at the outer report level; strata carry their own `schema_version`

## New analysis artifacts

Successful JSON parse paths call `attach_report_strata_to_dashboard`: existing LLM strata are normalized; otherwise an empty six-slot structure is written (framework not configured + disclaimer). New runs therefore always persist the six-slot payload; filled fact lines still depend on model/upstream data quality.

## Rendering

| Surface | Behavior |
| --- | --- |
| Markdown / brief / WeChat templates | When strata present, emit facts/gaps/inference/risks/framework without merging inference into facts; always print a single report-level disclaimer |
| Web full-report (`ReportSummary` → `ReportStrata`) | Same section order; disclaimer always shown even when strata are absent |
| API `ReportDetails.report_strata` | Projected when resolvable from `raw_result` / dashboard |

## Defaults

- Empty or missing framework → `framework_alignment.status = not_configured` plus localized “framework not configured” summary  
- Blank disclaimer on a present strata payload is filled with the language default  
- `ensure_report_strata()` builds a complete empty structure for **new** artifacts that need the slot filled deterministically  

## Fixtures

Offline fixtures live under `tests/fixtures/report_strata/`:

- `full_strata.json`  
- `empty_sources.json`  
- `source_conflicts.json`  
- `missing_timestamps.json`  
- `historical_without_strata.json`  
- `new_report_with_strata.json`  

## Out of scope

- Exportable audit zip / evidence package remainder (#127)  
- Multi-tenant ownership  
- Guarantees of trading accuracy or alpha  
- Forcing LLM extractor prompt rewrites beyond additive schema acceptance  
