# Web responsive breakpoints and audit matrix

Supported viewport matrix for StockPulse Web (`apps/dsa-web`). Complements the
application shell established in PR #208 and tracks remaining page-level work
for issues **#146** and **#234**.

## Breakpoint matrix

| Tier | Width | Shell behavior | Tailwind anchors |
| --- | --- | --- | --- |
| Phone (narrow) | **320** | Mobile header + navigation Drawer; no desktop sidebar | default / `< sm` |
| Phone | 390–767 | Same shell as 320; more horizontal room for chips/filters | `sm` (640+) |
| Tablet | **768** | Still mobile shell (`lg` not yet); AdvancedFilterSheet uses Popover at ≥768 | `md` (768) |
| Tablet / small laptop | **1024** | Desktop sidebar (compact by default through 1279); Home stays single-column until `xl` | `lg` (1024), compact rail through 1279 |
| Desktop | 1280+ | Expanded or user-toggled sidebar; multi-column Home / Chat session rail | `xl` (1280) |

Audit and regression evidence should cover at least **320 / 768 / 1024**.

## Foundation already in place (do not re-solve)

- Shell mobile header, nav Drawer, compact/expanded desktop rail (`Shell.tsx`)
- Coarse-pointer targets (`min-h-11` / IconButton `navigation` = 44px)
- `Pagination` compact strip for 320px containers
- `DataTable` contained horizontal scroll (`overflow-x-auto`) with declared min widths
- `ResponsiveFilterPanel` / `AdvancedFilterSheet` mobile drawers and 768 breakpoint switch
- Home three-column core blocks only at `xl` (avoids clip at 1024 with compact rail)

## Systematic audit snapshot (main baseline, code + foundation E2E)

Method: static review of primary routes against the matrix; foundation E2E already
covers shell chrome at 320–1024. Full interactive page screenshots are follow-up.

| Surface | 320 | 768 | 1024 | Severity | Notes / batch |
| --- | --- | --- | --- | --- | --- |
| Shell chrome | OK | OK | OK | — | Foundation E2E; safe-area insets added in batch 1 |
| Login | OK | OK | OK | Low | Centered card `max-w-sm` |
| Home | Partial | Partial | Partial | Medium | Dense stacks OK; watchlist/tables still desktop-oriented |
| Research → Analysis workbench | Gap | Gap | Partial | High | Action rows `flex-nowrap` + overflow-x; process/report panes need mobile fallbacks |
| Research → Market / Discover / Backtest | Partial | Partial | Partial | Medium | Filter collapse patterns exist; result tables rely on horizontal scroll |
| Chat / Agent | Partial | Partial | Partial | Medium | Session rail only at `xl`; drawer path present below |
| Portfolio | Gap | Partial | Partial | High | Dense holdings tables; URL wizard OK; risk panels wide |
| Signals center | Gap | Partial | Partial | High | Multi-tab + tables; filter density; not in primary nav (IA #368) |
| Settings | Partial | Partial | OK | Medium | Section nav stacks; long forms need sticky save visibility checks |
| Stock details / report reading | Gap | Partial | Partial | High | Charts + tables; report process visualizations need mobile fallbacks |
| Approvals / Notifications / Events | Partial | Partial | OK | Low–Med | List patterns mostly single-column |

**Legend:** OK = no critical overflow expected; Partial = usable with known density/scroll debt; Gap = high risk of cramped actions or missing mobile fallback.

## Gap backlog (small batches)

### Batch 1 (this PR) — shell install + safe area

- [x] PWA manifest + shell-only service worker + install meta tags (Refs #234)
- [x] Safe-area padding for notched phones on shell header / main
- [x] Breakpoint matrix documented

### Batch 2 — dense tables and workbench (follow-up)

- [ ] Analysis workbench action chrome: wrap / stack below 768 instead of only horizontal scroll
- [ ] Report / process visualizations: mobile stacked fallback (Refs #146 AC)
- [ ] Portfolio and Signals: prefer card/list summaries under 768 where tables exceed two screens of horizontal scroll

### Batch 3 — interaction and coverage (follow-up)

- [ ] Expand Playwright viewport checks for primary routes at 320 / 768 / 1024 (document overflow + critical CTAs visible)
- [ ] Touch-target sweep on remaining page-local buttons outside shared primitives
- [ ] Optional bottom-nav exploration only if primary IA (#368) lands first

## Out of scope here

- Offline analysis data cache (see `docs/web-pwa.md`, #218 / #990)
- Push notifications
- Navigation IA redesign (#368)

## Related

- Issue #146 — responsive multi-device optimization
- Issue #234 — mobile experience + PWA
- `docs/web-ui-foundation.md` — shared control geometry
- `docs/web-pwa.md` — PWA cache boundary
