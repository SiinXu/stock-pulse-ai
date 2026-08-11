# Configurable technical indicator periods

This global-settings foundation for issue #172 makes trend-analysis indicator periods configurable through environment variables and Settings, including longer moving averages such as 120 and 250 days.

## Defaults (backward compatible)

| Setting | Default | Notes |
| --- | --- | --- |
| `INDICATOR_MA_PERIODS` | `5,10,20,60` | Dynamic output uses exact configured MA labels |
| `INDICATOR_MACD_FAST` | `12` | Must be &lt; slow |
| `INDICATOR_MACD_SLOW` | `26` | |
| `INDICATOR_MACD_SIGNAL` | `9` | DEA period |
| `INDICATOR_RSI_PERIODS` | `6,12,24` | Dynamic output uses exact configured RSI labels |

When these defaults are used and enough bars are available, computed MA / MACD / RSI values match the pre-configuration formulas.

## Validation

- Periods must be positive integers.
- MA periods: 1–500, 3–16 unique values for `INDICATOR_MA_PERIODS`.
- RSI periods: 1–250, 1–8 unique values.
- MACD periods: 1–200.
- MACD fast must be strictly less than slow.
- Only absent or blank values use defaults. Explicit malformed, duplicate, out-of-range, or inverted values are rejected at startup, import/runtime construction, and Settings save.

## Insufficient data

If `period > available bars` for a moving average:

- `ma_by_period[period]` is `None`
- The matching dynamic reading has `value: null`, `available: false`, a reason, bar count, and as-of date
- Exact legacy fields such as `ma60` are `None` when their own period is unavailable
- `risk_factors` includes a clear `MAn: insufficient data (need n bars, got m)` note
- **No silent substitution** of a shorter MA (the old MA60←MA20 fallback is removed)

## History window

Trend analysis lookback in both the classic pipeline and Agent tool scales with the longest configured indicator period (`max(MA, MACD slow+signal, RSI)`), expanded to calendar days with the same ~1.8× + 10 day style as history loading. Resumability checks both the target date and required bar coverage, so a database containing only recent bars is backfilled before a long indicator such as MA250 is evaluated.

`src/services/stock_daily_window_resolver.py` resolves **backtest evaluation** windows and does **not** need changes for indicator calculation.

## Compatibility and scope

- `data_provider` daily `ma5/ma10/ma20` columns remain hard-coded (owned by data-provider tasks).
- Legacy fields `ma5` / `ma10` / `ma20` / `ma60` and `rsi_6` / `rsi_12` / `rsi_24` always retain those exact periods. They are never positional aliases for custom periods.
- Prompts, reports, notifications, API payloads, and the Agent trend tool also carry the dynamic typed snapshot with exact labels, availability, source, bar count, and as-of date.
- This change establishes global Settings precedence (`defaults < global Settings`). Strategy-YAML overrides remain future work for issue #172; this change does not claim to close the issue.

## Examples

```bash
# Long-horizon MAs for trend context
INDICATOR_MA_PERIODS=5,10,20,60,120,250

# Faster MACD
INDICATOR_MACD_FAST=8
INDICATOR_MACD_SLOW=17
INDICATOR_MACD_SIGNAL=5

# Classic RSI 14 as medium term
INDICATOR_RSI_PERIODS=7,14,21
```
