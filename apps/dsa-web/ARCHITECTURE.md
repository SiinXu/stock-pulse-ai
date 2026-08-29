# StockPulse Web Architecture Contract

This document defines ownership and dependency direction inside `apps/dsa-web/src`. It complements
the visual and interaction contracts in `DESIGN_GUIDE.md` and `docs/web-ui-foundation.md`; it does
not replace them. Runtime behavior, API contracts, accessibility, and repository `AGENTS.md` rules
remain authoritative.

## Goals

- Keep business and data contracts reusable without importing rendered UI.
- Keep shared UI primitives independent of feature, layout, and theme owners.
- Make page modules composition roots rather than reusable dependencies.
- Keep the component playground isolated behind its application-level route composition.
- Turn known debt into explicit, shrinking exceptions instead of implicit precedent.

The contract governs production TypeScript and TSX. Tests may cross production boundaries to
exercise integration paths, and generated, fixture, story, and test sources are excluded from the
production inventory.

## Ownership Layers

| Layer | Paths | Owns |
| --- | --- | --- |
| Application composition | `App.tsx`, `main.tsx` | Providers, router assembly, and top-level error/loading boundaries. |
| Pages | `pages/` | Route-level orchestration, business-state composition, and page-local presentation. |
| Feature UI | `components/<feature>/` | Reusable presentation and interaction for one feature domain. |
| Shared UI | `components/common/`, `components/layout/`, `components/routing/`, `components/theme/` | Design primitives and cross-feature visual or navigation patterns, each under its named owner. |
| Behavior and state | `hooks/`, `stores/`, `contexts/` | Reusable React behavior, client state, and neutral provider contracts. |
| Data and contracts | `api/`, `types/`, `utils/`, `i18n/`, `locales/` | Transport adapters, schemas, pure policy/helpers, and localization resources. |
| Component catalog | `playground/` | Component scenarios and manual inspection surfaces mounted only by application composition. |

`dev/` contains optional development integration shims. Assets contain static resources and do not
define application contracts.

## Dependency Direction

The normal composition direction is:

```text
App -> pages -> feature/shared UI -> behavior/state -> data/contracts
```

This is an ownership rule, not a requirement to pass every dependency through every layer.
Pages and components may import the lower-level modules they directly need. The following rules are
enforced by `src/components/__tests__/architectureImportGuard.test.ts`:

1. `App.tsx` owns page-route composition, and `main.tsx` may import `App.tsx` to mount the
   application. Pages, components, and lower layers must not import a page or either application
   composition module. Extract reusable UI or policy below the route layer instead.
2. A page must not import another page. Extract reusable UI to a feature component, and extract
   reusable behavior or policy to its owning lower layer.
3. Pages, components, and lower layers must not import the playground. `App.tsx` is the sole
   composition root allowed to mount its catalog routes.
4. `components/common/` must not import or re-export another UI owner's feature, layout, routing,
   or theme module. Consumers import those modules from their actual owner.
5. `api/`, `contexts/`, `hooks/`, `i18n/`, `locales/`, `stores/`, `types/`, and `utils/` must not
   import rendered UI under `components/`, route composition under `pages/`, or playground code.
   Move a shared contract to neutral ownership instead of making a lower layer depend on its UI.

Feature components may compose shared UI and lower layers. Layout, routing, and theme owners may
compose `components/common` primitives. Application composition may import pages and any provider
needed to assemble the application.

### Portfolio route-local workflows

`hooks/portfolio/` contains feature-private workflow Modules for the Portfolio route. They live
under the behavior/state layer but are not a shared cross-feature facade:

- `usePortfolioProjectionSession` owns account/cost scope acceptance, stale-response rejection,
  snapshot-to-risk projection (TanStack Query schedule), hand-rolled ledger query dispatch, and the
  refresh surfaces used after writes.
- `usePortfolioLedgerMutationWorkflow` owns operation identity for the five idempotent ledger
  writes, commit-before-refresh sequencing, paper-trade refresh-only retry, and CSV partial-result
  attempt rotation.

`PortfolioPage` remains the route composition root and presentation owner: it owns URL composition,
form validation, modal state, localized error presentation, tables, and all rendered structure.
The route-local workflows consume the existing Portfolio transport adapter and public Web types;
they do not redefine either contract.

## Module Entry Points

- A directory barrel may expose modules owned by that directory. It must not hide an upward or
  sideways dependency by re-exporting another owner's module.
- Prefer the narrowest stable owner import. Store consumers should import the owning store module;
  UI consumers may use a same-owner component barrel when it represents a deliberate public API.
- Do not add a new barrel solely to shorten import paths. A barrel is useful only when it defines a
  reviewed ownership boundary.
- Types and pure policy used by both UI and non-view code belong in `types/`, `utils/`, or a neutral
  context module, not in a component directory.

## Executable Inventory And Ratchets

`src/components/__tests__/productionSourceInventory.ts` is the shared test-only authority for
discovering production TypeScript, TSX, and CSS. Architecture, page/router, production-design, and
responsive-design guards use that inventory so exclusions cannot drift between tests.

The architecture guard parses static imports, re-exports, import types, dynamic imports, and
`require()` calls with the TypeScript AST. It resolves relative imports to the production inventory
and compares every violation with an exact allowance ledger. Each allowance records its owner and
removal condition. The current maximum is one; a new edge fails even if it resembles existing
debt.

The production design guard separately caps existing caller-specific exceptions:

| Allowance | Maximum |
| --- | ---: |
| Button visual overrides | 0 |
| State-surface visual overrides | 16 |
| Near-viewport panels | 1 |

These numbers are ceilings, not targets. When a violation is removed, delete its exact allowance
and lower the corresponding maximum in the same change. Do not replace one retired exception with
another or broaden an exact path/token entry into a directory-wide exclusion.

## Known Migration Ledger

The executable allowance list is authoritative. The current ledger contains these migration
groups:

| Current edge | Count | Removal path |
| --- | ---: | --- |
| `hooks/useSystemConfig.ts` imports Settings subcategory policy | 1 | Extract the cohesive policy in a dedicated Settings contract change. |

W2a introduced the guard with eight allowances. W2b resolved four by removing the foreign
layout/theme re-exports from `components/common/index.ts`; it also removed the unused stores facade
and analysis store. W2c resolved three more by moving the route-focus context and model-access
field-key contracts to neutral ownership. Runtime consumers now import these contracts from their
actual owners, leaving one deferred exception.

The Settings exception is intentionally deferred. It spans configuration schema grouping, route
selection, page navigation, and tests; moving it safely requires a focused behavioral slice rather
than a line-count-driven file split.

## TanStack Query Rollout Pattern (Pilot)

`@tanstack/react-query` is mounted once at the application root via `query/QueryProvider.tsx` in
`main.tsx`. The provider is **inert for non-consumers**: pages and hooks that never call
`useQuery` / `useMutation` keep their existing fetch style and are unaffected.

### Pilot consumer

| Surface | Ownership | Behavior parity notes |
| --- | --- | --- |
| `MarketReviewPage` history list | `hooks/useMarketReviewHistoryQuery.ts` | `useQuery` with `refetchInterval: 30_000`, `refetchOnWindowFocus: true`, `retry: false`. First fetch uses the store's non-silent load; later refetches use silent refresh. Errors still land on the existing store / `ApiErrorAlert` surfaces. |
| Market review trigger | `hooks/useMarketReviewRunner.ts` | `useMutation` for `triggerMarketReview`. Task-status polling stays custom (domain notices, 2s cadence, 120-attempt cap) so completion/timeout copy is unchanged. |

### Migration ledger (graduated pages)

| Surface | Ownership | Behavior parity notes | Status |
| --- | --- | --- | --- |
| `MarketReviewPage` history + trigger | `hooks/useMarketReviewHistoryQuery.ts`, `hooks/useMarketReviewRunner.ts` | See pilot consumer above | Pilot (#788) |
| `DecisionSignalsPage` list feed | `hooks/useDecisionSignalListQuery.ts` | No interval poll; no focus refetch (`refetchOnWindowFocus: false`); key includes filters/page/scope/watchlist readiness; list reducer remains error/loading owner; `retry: false` | Wave 1 |
| `DecisionSignalsPage` outcome stats | `hooks/useDecisionSignalOutcomeStatsQuery.ts` | Mount load only; no focus/poll; existing stats error surface; `retry: false` | Wave 1 |
| `DecisionSignalsPage` detail outcomes + feedback | `hooks/useDecisionSignalDetailQueries.ts` | Selection-gated; independent queries; no focus/poll; `retry: false` | Wave 1 |
| `DecisionSignalsPage` status mutation | `hooks/useDecisionSignalStatusMutation.ts` | Single-shot `useMutation`; synchronous in-flight ref (not `isPending` alone) stays held through page-owned list+stats reload; `retry: false`; latest/timeline/selection updates stay page-owned | #789 |
| Alerts rules / triggers / notifications | `hooks/useAlertWorkspaceQueries.ts` + `AlertsWorkspace` | No poll; no focus refetch; page-owned create/update/delete mutations; `retry: false` | Wave 1 |
| `SkillOutcomesPage` performance load | `hooks/useSkillOutcomesQuery.ts` | reloadToken-driven initial load; manual refresh stays page-owned; no focus/poll; `retry: false` | Wave 1 |
| `ApprovalsPage` workspace | `hooks/useApprovalsWorkspaceQuery.ts` | First run full load; later ticks poll proposals at **5s**; interval off when auth-blocked; no focus refetch; countdown timer stays local | Wave 1 |
| `StockDetailsPage` quote + history | `hooks/useStockDetailsQueries.ts` | Code/days key; no poll/focus; `retry: false` | Wave 1 |
| Analysis Workbench dashboard data refresh | `hooks/useDashboardDataRefreshQuery.ts` (via `useDashboardLifecycle`) | First run **per mount** (mount-scoped query key + cache miss) non-silent history + stock-bar + active tasks; initial-loader identity change re-runs non-silent path; later ticks silent at **30s**; explicit `visibilitychange` refetch (`refetchOnWindowFocus: false`); unmount removes schedule cache entry; SSE + 2s disconnected task poll stay custom; `retry: false` | Wave 2 (#789) |
| `HomePage` attention / Today's Focus / setup-status | `hooks/useHomePageQueries.ts` | Mount + manual refresh only; no poll; no window-focus refetch; Today's Focus key includes language; attention pack uses allSettled so one failed source does not wipe the pack; last-known signal totals stay marked stale; setup silent refresh stays onboarding-owned; unmount removes cache rows; `retry: false`; `staleTime: 0` | Wave 2 (#789) |
| Header notification bell preview + unread count | `hooks/useUnreadNotifications.ts` | **60s** poll (`pollMs` default 60000, `pageSize` 10, `enabled` true); query key includes `pageSize` only; `list({ pageSize })` + `unreadCount()` via `Promise.allSettled`; last-good per side from live cache after settlement; independent flags; hard error only when both fail; bounded `sourceStatuses` degradation; `retry: false`; `refetchOnWindowFocus: false`; `refetchIntervalInBackground: true`; `networkMode: 'always'` (previous effect always fetched while offline); `staleTime: 0` + unmount/disable/key-change silent cancel + `removeQueries` (no hidden remount or disable-period cache; not `gcTime: 0`); `refresh` void-facing (silent cancel then `refetchQueries` so an initial pending pair is replaced); `markAllSeen` keeps `markAllRead` success/failure/rethrow and, while disabled, updates only `markFailed` so it cannot resurrect the removed row; the disabled shape reports the empty preview with live `markFailed`. Two disclosed divergences from the previous `setInterval` scheduler, both unreachable from the sole consumer: a tick during an in-flight pair joins that fetch instead of starting a second pair, and a runtime `pollMs` change re-arms the interval without an immediate refetch. Cleanup is `removeQueries({ exact: true })`, correct for a **single owner** only — `Shell` mounts the bell on mutually exclusive desktop/mobile branches; a second concurrent owner of this key would need a refcounted discard. Notification Center page inbox is migrated on a disjoint `['notifications','center','list',…]` family (see below); this hook must not prefix-cancel or prefix-remove `['notifications']`. | #789 |
| Portfolio projection snapshot + risk | `hooks/portfolio/usePortfolioProjectionQueries.ts` + `usePortfolioProjectionSession` | Mount + filter-driven / refresh / silent FX follow-up snapshot-then-risk; `retry: false`; no poll; `refetchOnWindowFocus: false`; `staleTime: 0`; snapshot fail clears snapshot+risk and the page hard-error surface; silent `CancelledError` does not clear; risk fail keeps snapshot, sets `riskWarning`, and clears hard error; owner-based `isLoading`; exact-key cancel + `removeQueries` on unmount/account scope. Ledger events stay hand-rolled in the same session hook. | #789 |
| Notification Center page inbox list, cursor pagination, and mark-read refresh | `hooks/useNotificationCenterInbox.ts` | Imperative `fetchQuery` only (no live `useQuery` observer, no `useInfiniteQuery`, no `useMutation`); query key `['notifications', 'center', 'list', kind\|\|'all', unreadOnly ? 'unread' : 'all', 50, cursor ?? 'head']`; `retry: false`; no poll; `refetchOnWindowFocus: false`; `networkMode: 'always'`; `staleTime: 0`; request-id owner loading/error; concatenated `items` and latest `pageData` stay in React state (cache is transport-only); exact-key silent cancel (`silent: true, revert: false`) + `removeQueries`; same-key refresh cancel+remove then `fetchQuery`; unmount/filter change exact-removes live center keys; mark-read / mark-all-read stay imperative `notificationInboxApi` plus generation-fenced `load('refresh')` (no optimistic patch, no bell `setQueryData` / `invalidateQueries`); header bell `['notifications','unread-preview',10]` stays disjoint | #789 |
| Settings system-config GET load | `hooks/useSystemConfigLoadQuery.ts` + `useSystemConfig` | Imperative `fetchQuery` only (no live `useQuery` observer, no `useMutation`); query key `['settings','system-config','load']`; always `getConfig(true)`; `retry: false`; no poll; `refetchOnWindowFocus: false`; `networkMode: 'always'`; `staleTime: 0`; request-id + `serverSnapshotEpoch` latest-wins; silent `CancelledError` does not `setLoadError`; exact-key silent cancel (`silent: true, revert: false`) + `removeQueries`; overlapping `load()` cancel+remove then `fetchQuery`; unmount exact-removes the load key; save / 409 rebase / `refreshCommittedSnapshot` / `refreshAfterExternalSave` stay raw `systemConfigApi.getConfig(true)` (must not share the load key); section-local Settings loaders stay hand-rolled | #789 |
| Event Calendar page list | `hooks/useEventCalendarQuery.ts` + `EventCalendarWorkspace` | Imperative `fetchQuery` only (no live `useQuery` observer, no `useInfiniteQuery`, no `useMutation`); query key `['event-calendar','list',dateFrom,dateTo]`; transport `eventCalendarApi.getCalendar({dateFrom,dateTo},{signal})`; `retry: false`; no poll; `refetchOnWindowFocus: false`; `networkMode: 'always'`; `staleTime: 0`; request-id owner loading/error; React state for `data` (cache is transport-only); exact-key silent cancel (`silent: true, revert: false`) + `removeQueries`; date-range change and Refresh share `load()`; same-key refresh cancel+remove then `fetchQuery`; unmount/date-key change exact-removes live keys; silent `CancelledError` / abort does not `setError` or clear a newer generation's data; live-generation hard error clears only its own data; `includeImpact` stays client-side column state (not in key or API) | #789 |

### Rollout rules for the next pages

1. Keep transport in `api/*` and UI loading/error presentation on existing surfaces; do not invent a
   parallel error channel or change i18n keys.
2. Prefer route-local query hooks under `hooks/` (or a feature-private subfolder) over page-inline
   `useEffect` triples for list/detail fetch and polling.
3. Match the previous polling cadence and focus/visibility refresh semantics before changing them.
4. Default `retry: false` unless the product contract explicitly wants automatic retries.
5. Migrate one page at a time. Leave Zustand/client state for selection, drafts, and presentation
   until a later dedicated slice.
6. Every host that mounts a Query consumer must wrap a retry-free client. Unit
   tests use `QueryClientProvider` (`retry: false`). Standalone Playwright
   fixtures that mount `Shell` / `NotificationBell` (they do not inherit
   `main.tsx`) must wrap the production `QueryProvider` /
   `createAppQueryClient`. Playground stories rendered through `App` inherit
   the app-root provider; isolated playground unit renders still wrap a test
   client.

Suggested remaining migration order (issue #789): Screening → Chat/agent status → Backtest / calculators / report compare / token usage. Portfolio projection ledger events stay hand-rolled (HOLD). Settings section-local loaders still hand-rolled. Defer surfaces owned by concurrent open PRs.

## Change Checklist

Before adding or moving a module:

1. Name the owner by the behavior or contract it provides, not by its first consumer.
2. Check both imports and re-exports; a barrel does not change dependency direction.
3. Put shared types and pure policy below the UI that consumes them.
4. Add or update a focused guard fixture when changing an enforced rule.
5. Remove and lower allowances when debt is retired. New allowances require a concrete owner,
   removal condition, and review of why the dependency cannot be corrected in the same change.
6. Run lint, TypeScript build checking, the affected guard tests, and the production build.

Large files, by themselves, are not architecture violations. Split a module only when the new
boundary has cohesive ownership, reduces meaningful coupling, and can be verified independently.
