# In-app notification center / inbox

Issue #181 / T20 adds a **read-side** notification center. It aggregates durable events into a browsable inbox with persistent read state. Outbound push channels (Feishu / WeCom / Telegram / …) are unchanged.

## Design (plan A)

- **Independent consumer**: project items from existing tables at list time.
- **No push-side hooks**: does not call `NotificationService` or channel senders.
- **Does not evaluate alerts**: alert rules and workers stay in `alert_service` / `event_alerts` / `alert_worker`.
- **Read state only**: SQLite table `notification_inbox_read_state` stores `item_id` + `kind` + `read_at`.

## Event sources covered

| Kind | Source | Notes |
| --- | --- | --- |
| `analysis_complete` | `analysis_history` | Completed analyses with deep link to research history |
| `alert_triggered` | `alert_triggers` | Read-only via `AlertRepository` |
| `scheduled_task_result` | `scheduled_task_runs` (terminal statuses) | Read-only via `ScheduledTaskRepository` |
| `decision_signal` | decision signal rows | Active signals for catch-up with the header bell |

## Not included (data incomplete or out of scope)

- Live data-provider anomalies without a durable history row
- Daily brief text when not persisted as analysis/history
- Outbound delivery attempt logs as primary inbox rows (those remain diagnostics)

## API

Prefix: `/api/v1/notification-inbox`

- `GET /items` — paginated list (`kind`, `unread_only`)
- `GET /unread-count`
- `POST /items/mark-read` — body `{ "item_ids": ["analysis_complete:1"] }`
- `POST /items/mark-all-read` — optional `{ "kind": "..." }`

## Web

- Route: `/notifications`
- Page: `apps/dsa-web/src/pages/NotificationCenterPage.tsx`
- Components: `apps/dsa-web/src/components/notification-center/` (separate from Signal Center / Alerts detail views)
- Header bell “View all” links to `/notifications`

## Configuration

Optional. Defaults keep the feature on with conservative retention.

```bash
# NOTIFICATION_INBOX_RETENTION_DAYS=90
# NOTIFICATION_INBOX_MAX_ITEMS=500
```

Retention cleanup removes stale/orphan **read markers** only. Source event tables keep their own lifecycle.

## Boundary vs related tasks

- **T32** owns alert **detail** views under alerts components; this task owns the **aggregate inbox**.
- **T21** owns event calendar; do not share component paths.
- Do not modify `scheduled_task_service.py` or outbound notification modules.
