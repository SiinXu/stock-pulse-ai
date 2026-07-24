# 09 Backtest

The backtest UI evaluates **historical AI advice** after the fact. It is not a full quantitative backtesting suite.

## Steps

1. Open the backtest page (nav label depends on version).
2. Optionally limit symbols or analysis date range.
3. Run backtest.
4. Review result rows and summary metrics.
5. Drill into per-symbol performance when available.

## Metric meanings

| Concept | Meaning |
| --- | --- |
| Direction accuracy | Whether direction matched the advice |
| Win rate | Wins among decisive outcomes |
| Simulated return | Rule-based execution reference |
| Stop / take-profit hit rate | Whether planned levels were touched |

## Notes

- Very recent records may still be inside a cool-down window.
- When results are empty, read the on-page diagnostics (sample size, date filters, and similar).

Previous: [08 Reading reports](08-reading-reports_EN.md) · Next: [10 Settings](10-settings_EN.md)
