# In-app notification center / inbox

Issue #181 / T20 adds a **read-side** notification center. It aggregates durable events into a browsable inbox with persistent read state. Outbound push channels (Feishu / WeCom / Telegram / …) are unchanged.

## Design

- **Shared durable event sources**: the inbox and header bell consume the same read model projected from existing analysis, alert, scheduled-run, and decision-signal tables.
- **No push-side hooks**: does not call `NotificationService` or channel senders.
- **Does not evaluate alerts**: alert rules and workers stay in `alert_service` / `event_alerts` / `alert_worker`.
- **Read state only**: SQLite table `notification_inbox_read_state` stores `item_id` + `kind` + `read_at`.
- **Best-effort reads**: one unavailable source does not hide healthy sources. Responses include bounded `source_statuses`; the request fails with `503` only when no selected source can be read.

## Event sources covered

| Kind | Source | Notes |
| --- | --- | --- |
| `analysis_complete` | `analysis_history` | Completed analyses with deep link to research history |
| `alert_triggered` | `alert_triggers` | Read-only via `AlertRepository` |
| `scheduled_task_result` | `scheduled_task_runs` (terminal statuses) | Read-only via `ScheduledTaskRepository` |
| `decision_signal` | decision signal rows | All retention-window statuses so a later status transition does not erase an occurrence |

Analysis and alert timestamps are legacy process-local naive values and are converted from the server's local timezone to UTC at their source boundaries. Scheduled-run and decision-signal timestamps are stored as UTC-naive values and are labeled UTC. API timestamps are always offset-aware.

## Not included (data incomplete or out of scope)

- Live data-provider anomalies without a durable history row
- Daily brief text when not persisted as analysis/history
- Outbound delivery attempt logs as primary inbox rows (those remain diagnostics)

## API

Prefix: `/api/v1/notification-inbox`

- `GET /items` — stable newest-first cursor list (`cursor`, `kind`, `unread_only`, `page_size`; legacy `page` remains compatible)
- `GET /unread-count`
- `POST /items/mark-read` — body `{ "item_ids": ["v1:analysis_complete:42:1786320000000000"] }`
- `POST /items/mark-all-read` — optional `{ "kind": "..." }`

Item IDs bind the source kind, durable source ID, and occurrence timestamp. Mark-read accepts at most 100 IDs, validates every ID against an authoritative current occurrence, and never persists unknown/orphan IDs. Mark-all-read fails closed if a selected source is unavailable.

Each source query is bounded to the configured aggregation maximum before a deterministic global top-N merge. `page_size` is limited to 1-100. `next_cursor` and `has_more` expose reachable overflow rows without page-shift duplication when newer events arrive.

## Web

- Route: `/notifications`
- Page: `apps/dsa-web/src/pages/NotificationCenterPage.tsx`
- Components: `apps/dsa-web/src/components/notification-center/` (separate from Signal Center / Alerts detail views)
- Header bell “View all” links to `/notifications`
- The header bell uses the inbox list, unread-count, and mark-all-read endpoints. It does not maintain localStorage read timestamps or query alert/signal APIs separately.

## Configuration

Optional. Defaults keep the feature on with conservative retention.

```bash
# NOTIFICATION_INBOX_RETENTION_DAYS=90
# NOTIFICATION_INBOX_MAX_ITEMS=500
```

`NOTIFICATION_INBOX_RETENTION_DAYS` is clamped to 1-3650 and `NOTIFICATION_INBOX_MAX_ITEMS` to 10-5000. A non-integer value logs the key name without its raw value and uses the documented default. No setting disables the inbox.

Time-based read-marker retention runs on normal list/count lifecycle paths. Orphan cleanup runs only with a complete source window, so an unavailable source cannot cause valid markers to be deleted. Source event tables keep their own lifecycle.

## Boundary vs related tasks

- **T32** owns alert **detail** views under alerts components; this task owns the **aggregate inbox**.
- **T21** owns event calendar; do not share component paths.
- The inbox adds a newest-first repository read for scheduled occurrences; it does not modify `scheduled_task_service.py` or outbound notification modules.
