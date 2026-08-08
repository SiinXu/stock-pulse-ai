# Configurable technical indicator periods

Issue #172 makes trend-analysis indicator periods configurable via environment / Settings, including longer moving averages (120 / 250 day).

## Defaults (backward compatible)

| Setting | Default | Notes |
| --- | --- | --- |
| `INDICATOR_MA_PERIODS` | `5,10,20,60` | First four map to legacy `ma5` / `ma10` / `ma20` / `ma60` slots |
| `INDICATOR_MACD_FAST` | `12` | Must be &lt; slow |
| `INDICATOR_MACD_SLOW` | `26` | |
| `INDICATOR_MACD_SIGNAL` | `9` | DEA period |
| `INDICATOR_RSI_PERIODS` | `6,12,24` | First three map to `rsi_6` / `rsi_12` / `rsi_24` |

When these defaults are used and enough bars are available, computed MA / MACD / RSI values match the pre-configuration formulas.

## Validation

- Periods must be positive integers.
- MA periods: 1–500, 3–16 unique values for `INDICATOR_MA_PERIODS`.
- RSI periods: 1–250.
- MACD fast must be strictly less than slow.
- Invalid env values log a warning and fall back to defaults so the process still starts.
- Settings writes should reject invalid values via registry validation.

## Insufficient data

If `period > available bars` for a moving average:

- `ma_by_period[period]` is `None`
- Legacy float slots use `0.0` for that slot
- `risk_factors` includes a clear `MAn: insufficient data (need n bars, got m)` note
- **No silent substitution** of a shorter MA (the old MA60←MA20 fallback is removed)

## History window

Trend analysis lookback in the stock pipeline scales with the longest configured indicator period (`max(MA, MACD slow+signal, RSI)`), expanded to calendar days with the same ~1.8× + 10 day style as history loading.

`src/services/stock_daily_window_resolver.py` resolves **backtest evaluation** windows and does **not** need changes for indicator calculation.

## Out of scope / integration notes

- `data_provider` daily `ma5/ma10/ma20` columns remain hard-coded (owned by data-provider tasks).
- Agent tool `calculate_ma` still accepts per-call period strings; it is not rewired in this change (`src/agent/` frozen for this batch).
- Report templates still label slots as MA5/MA10/MA20; slot names are compatibility labels when periods change.

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
