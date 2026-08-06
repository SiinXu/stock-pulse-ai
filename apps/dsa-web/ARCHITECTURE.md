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
  snapshot-to-risk projection, ledger query dispatch, and the refresh surfaces used after writes.
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
| Alerts rules / triggers / notifications | `hooks/useAlertWorkspaceQueries.ts` + `AlertsWorkspace` | No poll; no focus refetch; page-owned create/update/delete mutations; `retry: false` | Wave 1 |
| `SkillOutcomesPage` performance load | `hooks/useSkillOutcomesQuery.ts` | reloadToken-driven initial load; manual refresh stays page-owned; no focus/poll; `retry: false` | Wave 1 |

### Rollout rules for the next pages

1. Keep transport in `api/*` and UI loading/error presentation on existing surfaces; do not invent a
   parallel error channel or change i18n keys.
2. Prefer route-local query hooks under `hooks/` (or a feature-private subfolder) over page-inline
   `useEffect` triples for list/detail fetch and polling.
3. Match the previous polling cadence and focus/visibility refresh semantics before changing them.
4. Default `retry: false` unless the product contract explicitly wants automatic retries.
5. Migrate one page at a time. Leave Zustand/client state for selection, drafts, and presentation
   until a later dedicated slice.
6. Tests that render a Query consumer must wrap with a test `QueryClientProvider` (`retry: false`).

Suggested remaining migration order (issue #789): Home history lifecycle → Portfolio projection
session → Alerts rules list → Settings system-config loads → Chat/agent status surfaces that still
hand-roll polling. Defer pages owned by concurrent open PRs (see wave-1 plan).

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
