# Event Calendar (V0)

Upcoming-event calendar scoped to watchlist and holdings
([#153](https://github.com/SiinXu/stock-pulse-ai/issues/153) / T21).

## Scope

| Included | Out of scope (V0) |
| --- | --- |
| Event model + date certainty (`confirmed` / `scheduled` / `estimated`) | Full-market event firehose |
| Watchlist + holdings symbols only | Edits to `event_alerts.py` |
| Independent akshare fetch (no provider capability-table expansion) | Full US/HK calendars |
| Impact preview via `build_impact_context` | LLM inventing events |
| Web view at `/events` | Sidebar nav wiring (see Integration Point) |

## Toggle

```bash
EVENT_CALENDAR_ENABLED=false   # default: zero extra fetch
EVENT_CALENDAR_ENABLED=true    # opt-in before any akshare calendar call
```

When unset or `false`, the API returns `enabled=false`, `fetch_attempted=false`,
and an empty event list.

## Endpoint

```http
GET /api/v1/event-calendar
```

| Parameter | Default | Notes |
| --- | --- | --- |
| `date_from` | today | Range start |
| `date_to` | today + 90d | Range end |
| `symbols` | watchlist ∪ holdings | Intersected with managed scope only |
| `event_types` | all | `earnings,ex_dividend,unlock,index_rebalance,macro` |
| `include_impact` | true | Attach `build_impact_context` preview |
| `report_language` | zh | `zh` / `en` |

## Certainty

| Value | Meaning |
| --- | --- |
| `confirmed` | Fixed announced date (ex-date, unlock batch) |
| `scheduled` | Appointment date (earnings appointment) — **can still move** |
| `estimated` | Lowest confidence inference |

UI must show the certainty badge and `fetched_at` so appointment dates are never
mistaken for fixed dates.

## Impact preview

- Reuses `build_impact_context` / `why_it_matters` from
  `src/services/event_alerts.py` (read-only; that file is not modified).
- Does not call an LLM to invent events; leaves `why_it_matters` empty when
  assessment is unavailable.

## Market coverage

| Market | Earnings | Ex-dividend | Unlock | Index rebalance | Macro |
| --- | --- | --- | --- | --- | --- |
| CN A-share | akshare `stock_yysj_em` (appointment/actual) | akshare `stock_fhps_em` | akshare unlock queue | not covered (V0) | not covered (V0) |
| HK | not covered (V0) | not covered (V0) | not covered (V0) | not covered (V0) | not covered (V0) |
| US | not covered (V0) | not covered (V0) | not covered (V0) | not covered (V0) | not covered (V0) |

**Do not assume US/HK calendars are as complete as A-share.**

## Web

- Route: `/events` (`APP_ROUTE_PATHS.eventCalendar`)
- Components: `apps/dsa-web/src/components/event-calendar/`
  (separate from `alerts` / `notifications`)

## Integration Point

`SidebarNav.tsx` is frozen in this batch. After merge, add one nav entry:

```tsx
{ to: APP_ROUTE_PATHS.eventCalendar, labelKey: 'layout.nav.eventCalendar' }
```

Until then, open `/events` directly.

## Rollback

Set `EVENT_CALENDAR_ENABLED=false` or revert this change.
