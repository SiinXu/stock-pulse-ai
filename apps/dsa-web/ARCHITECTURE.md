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
