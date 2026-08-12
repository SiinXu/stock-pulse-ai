# Corporate Event Calendar

The Web route `/events` provides a read-only calendar projection of the
corporate-event alert contract owned by the alerts subsystem.

## Contract boundary

- The calendar reads `GET /api/v1/alerts/triggers` with
  `alert_type=corporate_event`.
- It does not define an event provider, event configuration, cache, fallback,
  or a second event API.
- It does not fetch market or event data. Provider governance remains in the
  alerts event source.
- Impact and provenance fields are displayed from the alert trigger's public
  `impact_context` / `event_context` projection.

This dependency means the event-alert contract from PR #957 must be available
before the calendar is deployed.

## Loading behavior

The client requests trigger pages at the server maximum page size and continues
until the server-reported total is reached. Reads are capped at 20 pages (2,000
records). If a later page fails or the cap is reached, the page displays a
localized partial-results warning and does not claim that an incomplete range is
empty.

Changing the date range or refreshing cancels the previous request. A request
generation guard prevents an older response from replacing newer filters.

## Scope

The page shows triggered corporate events within the selected date range and
can display their impact summary, affected watchlist/portfolio flags, status,
and source. It does not implement the future-event provider catalog or the
agent-generated bull/bear/watch preview still remaining in issue #153.


## Production discovery

The Event Calendar page header links to the corporate event alerts view (`/event-alerts`) so operators can open the alert list without typing the URL. Research navigation to `/events` is tracked separately.

## Rollback

Remove the `/events` route and its lazy page, or revert this change. The alerts
data contract and event evaluation path are unaffected.
