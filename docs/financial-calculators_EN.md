# Financial Calculators

The Web page at `/tools/calculators` provides compound growth, required periodic contribution, and time-to-goal calculations. It calls the deterministic `/api/v1/calculators/*` backend and does not read quotes, holdings, or LLM data.

## Calculation conventions

- `annual_rate` is a nominal annual decimal rate, so `0.07` means 7%. The periodic rate is `annual_rate / periods_per_year`; it is not an effective annual rate.
- Contributions occur at each period end (an ordinary annuity). A negative contribution represents a period-end withdrawal; principal and target amounts cannot be negative.
- Frequency is 1–365 periods per year. A fixed horizon is greater than 0 and at most 100 years, and `years × periods_per_year` must be an integer.
- Amounts are currency-neutral. Use one currency and unit throughout a calculation. Taxes, inflation, fees, and exchange rates are not modeled.

Compound future value is `P(1+r)^n + C((1+r)^n-1)/r`. When the periodic rate is zero, the calculator uses the linear form `P + Cn` to avoid division by zero.

## Precision, bounds, and responses

- A required contribution is rounded upward to two decimal places and forward-verified, so the amount displayed by the UI does not underfund the target because of display rounding.
- Time-to-goal is capped at 100 years independently of frequency. A longer result returns `status=unreachable` with a stable `reason_code`.
- Requests use strict, extra-field-forbidden schemas. Booleans masquerading as numbers, NaN, Infinity, and out-of-range money, rate, horizon, or frequency values are rejected.
- Compound growth returns at most 241 balance points. `series_total_points` reports the complete count, while `series_returned_points`, `series_sampled`, and `series_stride` describe sampling. Period zero and the final period are always retained.
- The UI localizes stable `reason_code` values instead of displaying backend English messages. Switching mode, resetting, or recalculating cancels and invalidates an older request.

Results are for education and planning only, not investment advice. Actual outcomes can differ because of volatility, taxes, fees, cash-flow timing, and precision rules.
