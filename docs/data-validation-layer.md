# Financial Data Validation Layer

Issue: #185 · Module: `data_provider/data_validation.py` · Manager wiring: `data_provider/manager_parts/data_validation_wiring.py`

## Purpose

Validate OHLCV bars, realtime quotes, and key fundamental metrics **before** they flow into analysis, LLM prompts, and reports. Validation runs at the `DataFetcherManager` unified exit (manager layer), not inside individual fetchers.

## Policy

| Mode | Env | Behavior |
| --- | --- | --- |
| Enabled (default) | `DATA_VALIDATION_ENABLED=true` (default) | Run validators; **warn-only** |
| Disabled | `DATA_VALIDATION_ENABLED=false` | No validation; behavior identical to pre-layer |
| Strict (opt-in) | `DATA_VALIDATION_STRICT=true` | `REJECT` findings raise `DataValidationRejected` (daily/fundamental) or force quote `None` so existing failover applies |

**Never silent drop.** Issues are structured reason codes attached to diagnostics (`DataFrame.attrs["data_validation"]` for daily frames; `data_validation` key on fundamental dicts) and logged.

## Reason codes

| Code | Typical severity | Meaning |
| --- | --- | --- |
| `dv_price_missing` | reject | Close/price missing |
| `dv_price_non_finite` | reject | NaN / ±Infinity in a price field |
| `dv_price_non_positive` | reject | Zero or negative price |
| `dv_high_below_low` | reject | high &lt; low |
| `dv_close_out_of_range` | reject | close outside [low, high] |
| `dv_open_out_of_range` | warn | open outside [low, high] |
| `dv_pct_chg_inconsistent` | warn | pct_chg vs (close − pre_close) / pre_close |
| `dv_volume_negative` | reject | Negative volume |
| `dv_volume_non_finite` | reject | Non-finite volume |
| `dv_volume_unit_suspect` | warn | amount/volume ≈ 100 × close (likely 手 vs 股) |
| `dv_amount_negative` | reject | Negative amount |
| `dv_date_out_of_order` | warn | Dates / report periods reverse |
| `dv_date_duplicate` | warn | Duplicate date / period |
| `dv_fund_pe_non_finite` | reject | PE is NaN / ±Infinity |
| `dv_fund_pe_extreme` | reject | \|PE\| ≥ 50 000 |
| `dv_fund_pe_negative` | warn | Negative PE (often legitimate) |
| `dv_fund_pb_non_finite` | reject | PB is NaN / ±Infinity |
| `dv_fund_pb_extreme` | reject | \|PB\| ≥ 10 000 |
| `dv_empty_payload` | reject/warn | Empty or unsupported payload |

## Dirty-data inventory and handling

This inventory is a first-class deliverable of #185. Each row is covered by an offline unit test.

| # | Dirty form | Where it appears | Severity | Handling |
| --- | --- | --- | --- | --- |
| 1 | Price `None` / missing close | Daily bar, quote | reject | Strict: raise / quote→None; default: log + annotate |
| 2 | Price `0` or negative | Daily bar, quote | reject | Same |
| 3 | Price `NaN` / `±Infinity` | Daily bar, quote, PE/PB | reject | Same |
| 4 | `pct_chg` inconsistent with price vs pre_close / prior close | Daily bar, quote | warn | Always pass-through; log + annotate |
| 5 | `high < low` | Daily bar, quote | reject | Strict blocks; default annotate |
| 6 | `close` outside `[low, high]` | Daily bar, quote | reject | Strict blocks; default annotate |
| 7 | Negative volume / amount | Daily bar, quote | reject | Strict blocks; default annotate |
| 8 | Volume unit mismatch (手 vs 股) — amount/volume ~100× close | Daily bar, quote (historical TickFlow-class bug) | warn | Pass-through; log + annotate (no auto-rescale) |
| 9 | Duplicate bar dates / earnings periods | Daily frame, fundamentals | warn | Pass-through; log + annotate |
| 10 | Date / period reverse order | Daily frame, fundamentals | warn | Pass-through; log + annotate |
| 11 | Extreme PE/PB magnitudes | Quote valuation, fundamental valuation block | reject | Strict blocks; default annotate |
| 12 | Negative PE | Quote / fundamentals | warn | Pass-through (loss-making issuers are valid) |

### Explicit non-goals (false-positive protection)

- Missing PE/PB on ETFs or partial offshore coverage → **no issue**
- Mild pct_chg rounding within ±0.51 percentage points → **no issue**
- Negative PE alone → **warn only**, never reject
- Empty realtime quote (`None`) from upstream failover → validation is skipped at the wiring layer when the result is already `None`

## Integration point

Wiring is installed when the manager daily-source-health facade binds (owned by T11 under `manager_parts/`). No change to `data_provider/base.py` (owned by T10 in the parallel batch).

Methods wrapped:

1. `DataFetcherManager.get_daily_data`
2. `DataFetcherManager.get_realtime_quote`
3. `DataFetcherManager.get_fundamental_context`

Public pure API for tests and diagnostics:

```python
from data_provider.data_validation import (
    validate_daily_frame,
    validate_realtime_quote,
    validate_fundamental_context,
    validate_and_annotate,
    ValidationResult,
    REASON_CODES,
)
```

## Related modules (do not conflate)

| Module | Role |
| --- | --- |
| `data_provider/symbol_normalization.py` | Code normalization only |
| `data_provider/retry_policy.py` | Retry / timeout policy |
| `src/services/decision_signal_data_quality.py` | Decision-signal quality labels (signal layer) |
| Web `marketFormat` finite guards (PR #939) | UI formatting of non-finite numbers |

## Rollback

1. Set `DATA_VALIDATION_ENABLED=false`, or
2. Revert the PR that introduced this layer.
