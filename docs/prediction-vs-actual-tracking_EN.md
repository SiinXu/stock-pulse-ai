# Prediction vs Actual Tracking — Ownership Map

**Status**: Living (integration note)
**Issues**: Planning [#449](https://github.com/SiinXu/stock-pulse-ai/issues/449); authoritative Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)

## Purpose

Issue #449 asked for a general **Prediction vs Actual** evaluation framework.
Epic **#1107** is the authoritative, in-flight delivery of that loop for agent
forecasts (structured claims → automatic horizon resolution → scored outcomes →
budgeted post-mortem → gated adaptation).

**Do not implement a second tracking store, scorer, or resolver under #449.**

## Acceptance coverage

| #449 acceptance | #1107 surface |
| --- | --- |
| Auto-log predictions with metadata | A1 contract, A2 extractor, A3 `agent_predictions` |
| Auto compare after horizon | A4 ActualsFetcher, A5 ClaimScorer, resolve_after calendar, A7/A8 resolver |
| Metrics calculated | ClaimScorer aggregates (`hit_rate`, calibration) + offline eval gate |
| Metrics displayed | Ops metrics [#1114](https://github.com/SiinXu/stock-pulse-ai/issues/1114); query/diagnostics residual of [#1102](https://github.com/SiinXu/stock-pulse-ai/issues/1102) |
| Self-improvement feedback | Post-mortem [#1103](https://github.com/SiinXu/stock-pulse-ai/issues/1103); adapters [#1106](https://github.com/SiinXu/stock-pulse-ai/issues/1106) / [#1091](https://github.com/SiinXu/stock-pulse-ai/issues/1091) |

## Related but separate product surfaces

- Daily brief historical accuracy review ([#466](https://github.com/SiinXu/stock-pulse-ai/issues/466))
- Skill opinion outcomes / Decision signal outcomes (different label spaces)
- Offline agent output eval (not ClaimScorer)

## Intentional non-goals of the claim verifier

- Continuous-price MAE/RMSE leaderboards
- Paper P/L “if the signal was followed” (portfolio/backtest surfaces)
- Runtime mutation of Agent Soul charter or ToolSurface denials

Chinese: [prediction-vs-actual-tracking.md](prediction-vs-actual-tracking.md)
