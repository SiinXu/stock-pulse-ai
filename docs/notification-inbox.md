# In-app notification center / inbox

Issue #181 / T20 adds a **read-side** notification center. It aggregates durable events into a browsable inbox with persistent read state. Outbound push channels (Feishu / WeCom / Telegram / …) are unchanged.

## Design

- **Shared durable event sources**: the inbox and header bell consume the same read model projected from existing analysis, alert, scheduled-run, decision-signal, daily-brief history, high-disagreement synthesis, and portfolio-health snapshot tables.
- **No push-side hooks**: does not call `NotificationService` or channel senders.
- **Does not evaluate alerts**: alert rules and workers stay in `alert_service` / `event_alerts` / `alert_worker`.
- **Read state only**: SQLite table `notification_inbox_read_state` stores `item_id` + `kind` + `read_at`.
- **Best-effort reads**: one unavailable source does not hide healthy sources. Responses include bounded `source_statuses`; the request fails with `503` only when no selected source can be read.
- **No fabricated occurrences**: when a class of events has no authoritative persisted row, the inbox returns zero items for that source (or marks the source temporarily unavailable on read failure). It never invents synthetic rows from ephemeral push text or in-memory scheduler state.

## Event sources covered

| Kind | Source | Notes |
| --- | --- | --- |
| `analysis_complete` | `analysis_history` | Completed analyses with deep link to research history; excludes specialized shapes such as `daily_brief` |
| `alert_triggered` | `alert_triggers` | Read-only via `AlertRepository` |
| `scheduled_task_result` | `scheduled_task_runs` (terminal statuses) | Read-only via `ScheduledTaskRepository` |
| `decision_signal` | decision signal rows | All retention-window statuses so a later status transition does not erase an occurrence |
| `daily_brief` | `analysis_history` (`report_type=daily_brief`) | Only durable history rows produced when daily-brief persistence succeeds |
| `high_disagreement` | `analysis_history.raw_result.dashboard.strategy_synthesis` | Only rows whose durable synthesis has `conflict_severity=high` |
| `portfolio_health` | `portfolio_health_snapshots` | Read-only via `PortfolioHealthRepository.list_recent_snapshots`; same-day upserts keep a day-stable occurrence id |

Analysis and alert timestamps are legacy process-local naive values and are converted from the server's local timezone to UTC at their source boundaries. Scheduled-run and decision-signal timestamps are stored as UTC-naive values and are labeled UTC. API timestamps are always offset-aware.

## Not included (data incomplete or out of scope)

- Live data-provider anomalies without a durable history row
- Daily brief text that was only pushed externally when `DAILY_BRIEF_PERSIST_HISTORY=false` or history write failed (source stays empty rather than inventing an occurrence)
- Outbound delivery attempt logs as primary inbox rows (those remain diagnostics)
- Cross-device OS / desktop notification fan-out (deferred; the Web inbox remains the shared durable read model)

## API

Prefix: `/api/v1/notification-inbox`

- `GET /items` — stable newest-first cursor list (`cursor`, `kind`, `unread_only`, `page_size`; legacy `page` remains compatible)
- `GET /unread-count`
- `POST /items/mark-read` — body `{ "item_ids": ["v1:analysis_complete:42:1786320000000000"] }`
- `POST /items/mark-all-read` — optional `{ "kind": "..." }`

Item IDs bind the source kind, durable source ID, and occurrence timestamp. Mark-read accepts at most 100 IDs, validates every ID against an authoritative current occurrence, and never persists unknown/orphan IDs. Mark-all-read fails closed if a selected source is unavailable.

Each source query is bounded to the inbox aggregation maximum before a deterministic global top-N merge. `page_size` is limited to 1-100. `next_cursor` and `has_more` expose reachable overflow rows without page-shift duplication when newer events arrive.

## Web

- Route: `/notifications`
- Page: `apps/dsa-web/src/pages/NotificationCenterPage.tsx`
- Components: `apps/dsa-web/src/components/notification-center/` (separate from Signal Center / Alerts detail views)
- Header bell “View all” links to `/notifications`
- The header bell uses the inbox list, unread-count, and mark-all-read endpoints. It does not maintain localStorage read timestamps or query alert/signal APIs separately.

## Operational bounds

The inbox read model uses a 90-day retention window and a newest-first aggregation cap of 500 occurrences. These are service bounds rather than notification-channel settings; the inbox does not add a second channel configuration surface. Tests and internal callers may inject smaller bounded values for deterministic projections.

Time-based read-marker retention runs on normal list/count lifecycle paths. Orphan cleanup runs only with a complete source window, so an unavailable source cannot cause valid markers to be deleted. Source event tables keep their own lifecycle.

## Boundary vs related tasks

- **T32** owns alert **detail** views under alerts components; this task owns the **aggregate inbox**.
- **T21** owns event calendar; do not share component paths.
- The inbox adds a newest-first repository read for scheduled occurrences; it does not modify `scheduled_task_service.py` or outbound notification modules.
