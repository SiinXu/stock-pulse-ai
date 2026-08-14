# Home dashboard layout

The Home page mounts an independent **customizable dashboard board** for four key widgets:

| Widget id | Content |
| --- | --- |
| `watchlist` | Watchlist groups (existing Home section, including AI scores when available) |
| `portfolio_health` | Read-only stored daily portfolio health snapshot |
| `alerts` | Triggered-alert count with a deep link to Alerts |
| `recent_reports` | Recent stock analysis reports |

Zero-config first-run / readiness panels and **Today's Focus** stay outside this board and are not reordered by layout preferences.

## Preference model

- Storage key: `dsa.home.dashboardLayout.v1` in browser `localStorage` (per browser profile).
- Schema version `1` with a monotonically increasing `revision`.
- Every known widget id appears exactly once with a `visible` flag.
- Safe bounds:
  - Unknown ids are dropped; missing ids are appended with default visibility.
  - At least one widget must stay visible.
  - Reorder payloads must list every known id exactly once.

## Concurrency

Mutations use the same revision-CAS convention as watchlist groups on the client: each write supplies the expected revision, advances revision on success, and fails closed with a reload on conflict (including multi-tab `storage` events). A short action lease prevents overlapping writes in one tab.

## Interaction and accessibility

- **Desktop**: drag starts only from a grip handle while Customize mode is on; the same handle supports Arrow Up / Arrow Down.
- **Mobile**: grip handles stay hidden; explicit move-up / move-down buttons reorder without drag.
- Show/hide toggles respect the minimum-visible bound; the last visible widget cannot be hidden.
- Live-region announcements cover reorder, show/hide, and reset success.
- Empty board state (should only appear after corrupt storage is recovered incorrectly) offers Reset to default.

## Integration boundary

`HomeDashboardLayout` is a container plus the preference store. Home only passes widget nodes and existing attention data; it does not re-implement drag or storage. Portfolio health uses `GET /api/v1/portfolio/health` read-only (404 → empty snapshot UI).

## Rollback

Remove the Home board mount and the layout preference key. Older clients ignore `dsa.home.dashboardLayout.v1`. No backend migration is required.
