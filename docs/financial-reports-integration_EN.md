# Financial reports in fundamental analysis (Issue #235)

## Scope

- **A-shares first**: extends the existing `DataFetcherManager.get_fundamental_context` → `AkshareFundamentalAdapter` path. **No** parallel fundamental pipeline.
- HK/US stay on `YfinanceFundamentalAdapter`; only additive honesty metadata (`sufficiency`, `data_recency`) is layered on the existing summary fields.
- One provider failing is fail-open and never halts technical / news / main analysis.

## Data flow

1. `get_fundamental_context(code)` (manager cache / timeout / retry unchanged)
2. A-share bundle: `stock_financial_abstract` (plus indicator candidates) → multi-period parse
3. If abstract lacks multi-period history, OCF, or balance-sheet fields, best-effort:
   - Income: `stock_profit_sheet_by_report_em` (`SH600519` form)
   - Balance: `stock_balance_sheet_by_report_em`
   - Cash flow: `stock_cash_flow_sheet_by_report_em`
   - THS endpoints as fallbacks
4. `src/services/financial_reports_service.py` normalizes periods, metrics, sufficiency
5. Writes `earnings.data.financial_report` (legacy keys preserved)
6. Analysis prompt (`analyzer_parts/analysis.py`) and report rendering (`notification_parts/rendering.py`) consume the payload

## `financial_report` contract (additive)

| Field | Meaning |
|------|------|
| `report_date` / `revenue` / `net_profit_parent` / `operating_cash_flow` / `roe` / `currency` | Existing summary (compat) |
| `periods[]` | Multi-period fact rows (newest first) |
| `statements` | income / balance / cash_flow / abstract coverage |
| `metrics.*` | `{value, formula, basis}`; `value` may be `null` |
| `sufficiency` | `rich` \| `partial` \| `insufficient` + `message` / `missing_fields` |
| `data_recency` | Report period is not real-time |

## Derived metric formulas (single source of truth)

Documented in `src/services/financial_reports_service.py` module docstring:

- **YoY**: `(latest - prior_year_same) / abs(prior_year_same) * 100` (same month-day preferred; **never** use QoQ as YoY)
- **Gross margin**: `gross_profit / revenue * 100` (or provider passthrough)
- **Net margin**: `net_profit_parent / revenue * 100`
- **OCF / net profit**: `operating_cash_flow / net_profit_parent`
- **Debt / assets**: `total_liabilities / total_assets * 100`

## Honesty

- Missing / partial statements → `sufficiency.level` is `partial` or `insufficient`, message includes **insufficient fundamentals**.
- Never silent zeros; N/A must be described as missing.
- Prompts keep statement facts separate from `fundamental_analysis` inference.

## Configuration

Reuses existing keys only:

- `ENABLE_FUNDAMENTAL_PIPELINE`
- `FUNDAMENTAL_STAGE_TIMEOUT_SECONDS` / `FUNDAMENTAL_FETCH_TIMEOUT_SECONDS`
- `FUNDAMENTAL_RETRY_MAX` / `FUNDAMENTAL_CACHE_TTL_SECONDS` / `FUNDAMENTAL_CACHE_MAX_ENTRIES`

No new environment variables.

## Tests

- `tests/services/test_financial_reports_service.py`
- `tests/data_provider/test_financial_statements_adapter.py`
- `tests/notification/test_financial_report_rendering.py`
- Fixtures: `tests/fixtures/financial_reports/`
