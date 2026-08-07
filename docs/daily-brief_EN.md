# Daily Brief (historical accuracy review)

> 中文：[daily-brief.md](daily-brief.md)

Implements Issue [#466](https://github.com/SiinXu/stock-pulse-ai/issues/466): review the accuracy of prior predictions **before** presenting today's watchlist context, forming a prediction–verification loop.

## Scope

- **Default off** (`DAILY_BRIEF_ENABLED=false`). When enabled, a runtime-scheduler background task may fire **at most once per local calendar day**.
- Content sources:
  1. **Yesterday's analyses** from `AnalysisHistory` mapped to “yesterday” in the configured timezone (excludes `market_review` / `daily_brief` itself)
  2. **Today's watchlist** from `STOCK_LIST` (whether each code had a yesterday analysis)
  3. **Historical accuracy** from **existing stores only** (no new evaluation engine):
     - Decision-signal outcomes (`DecisionSignalOutcomeService` / persisted stats)
     - Backtest overall summary (`BacktestService.get_summary`)
     - Skill-opinion **performance** read API (`SkillOpinionPerformanceService.get_stats`)
- **Honesty rule**: when any source has insufficient completed samples, the brief **states that explicitly** and **never fabricates** hit-rate / accuracy percentages.
- Delivery: existing `NotificationService.send` (`route_type=report`) and `save_analysis_history`. **A single notification channel failure never aborts** generation or persistence.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `DAILY_BRIEF_ENABLED` | `false` | Master switch |
| `DAILY_BRIEF_SCHEDULE_TIME` | `08:30` | Local 24h `HH:MM` gate |
| `DAILY_BRIEF_TIMEZONE` | `Asia/Shanghai` | Schedule + “yesterday” mapping |
| `DAILY_BRIEF_MIN_SAMPLES` | `10` | Min completed samples before publishing a percentage |
| `DAILY_BRIEF_NOTIFY` | `true` | Dispatch via notification channels |
| `DAILY_BRIEF_PERSIST_HISTORY` | `true` | Persist as analysis history (`report_type=daily_brief`) |
| `DAILY_BRIEF_SAVE_REPORT_FILE` | `true` | Write Markdown report file |

## Scheduling

- Same pattern as the Event Monitor: background task name `daily_brief`, poll interval 60s (scheduler floor 30s).
- After `DAILY_BRIEF_SCHEDULE_TIME` on each local day, at most one successful generation; in-memory + history-table de-duplication.
- Registered from both the CLI `--schedule` path and `RuntimeSchedulerService` when the flag is on.

## Template and history

- Template: `templates/daily_brief.j2`
- History code: `DAILY_BRIEF`, `report_type=daily_brief`

## Relation to the reserved daily-digest flag

`NOTIFICATION_DAILY_DIGEST_ENABLED` remains a P4 **reserved** noise-control flag and does **not** send digests. This feature uses independent `DAILY_BRIEF_*` keys.

## Related

- [Notifications](notifications.md)
- [Decision signals](decision-signals.md)
- [Skill-opinion outcomes](skill-opinion-outcome-evaluation.md)
- [Scheduled tasks](scheduled-tasks.md)
