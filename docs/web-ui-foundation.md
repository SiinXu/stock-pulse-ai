# Web UI Foundation Contract

This document defines the shared interaction-control, surface, section, and
state contract for `apps/dsa-web`. Page and domain components should consume
these primitives and patterns instead of rebuilding size, focus, loading,
field-description, hit-target, boundary, empty-state, or alert behavior.

## Layer Boundary

## Theme Contract v1

Authorable theme surface for Web (Issues #162 / #880):

| Layer | Owner | Notes |
| --- | --- | --- |
| 0 — Market paint | `index.css` + `data-price-direction` | `--price-red/green` (hue), `--price-up/down` (direction). Packs must not override. Default CN red-up. |
| 1 — Core semantic | Theme pack / `:root` / `.dark` | Bare HSL channels for Tailwind. Packs may recolor brand/surfaces only. |
| Legacy aliases | `index.css` | `--home-price-up/down` → Layer 0 hues during migration. |

Built-in packs: `classic` (default), `slate` (validation variant). Runtime attrs: `data-theme-pack`, `data-price-direction`. Guard: `themeContractGuard.test.ts` (baseline-only-decrease) plus the Phase 0 token-freeze ratchet below. Preference bridge: `MARKET_REVIEW_COLOR_SCHEME` ↔ `data-price-direction`.

Signed price / gain / loss paint on Portfolio, Backtest, Screening results, Market Structure, and Financial Calculators uses `changeSemantics` + `changeColorCssVar` (via `SignedChangeText`). Preference is the existing ThemeAppearance / `data-price-direction` bridge (`MARKET_REVIEW_COLOR_SCHEME`) — do not add a parallel preference hook. Do not map signed values onto `text-success` / `text-danger`. Zero, missing, non-finite, and unresolved-market values stay unpainted; never invent a `cn` market for an unknown code. Sign or wording remains the non-color cue. Backtest up/down movement badges use `trend-up` / `trend-down` so they follow `data-price-direction`.

### Theme token freeze (Phase 0 / #1300)

Phase 0 freezes the current Web custom-property contract. It does **not** delete page-scoped leftovers, unify value formats, or ship a second theme package. Those remain later T25/T40 work.

| Surface | Owner | Freeze rule |
| --- | --- | --- |
| Web runtime tokens | `apps/dsa-web/src/index.css` (`:root`, `.dark`, pack selectors, `data-price-direction`, `data-density`) | Unique defined names must match `THEME_DEFINED_TOKEN_NAMES`. New names fail CI. |
| Classification | `classifyThemeToken()` in `src/design/theme.ts` | Layer 0 / Layer 1 stay the public API. Page-scoped leftovers are `page-scoped-debt`, not Layer 1. Compat and `--home-price-*` aliases stay aliases. |
| Page prefixes | `--home-*`, `--settings-*`, `--chat-*`, `--backtest-*`, `--portfolio-*` | Frozen. Do not add names. Do not promote them to Layer 1 to green CI. `--login-*`, `--backtest-*`, `--portfolio-*`, `--chat-*`, `--settings-*`, `--home-action-*`, and `--home-prose-*` are collapsed to zero; `--home-title-accent` is also collapsed. Do not reintroduce those prefixes or the action/prose/title-accent leftovers. |
| Definitions outside `index.css` | production TS/TSX/CSS | Forbidden. Local `style` may override an inventoried token (see `Input` error ring); it may not invent a new name. |
| Undefined `var(--*)` | `THEME_UNGOVERNED_REFERENCE_DEBT` in `themeTokenFreezeGuard.test.ts` | Shrink-only. Includes `--home-border`, chart `--info`, Tailwind `--color-purple`, and optional `.input-surface` slots. Do not add those names to the defined inventory. The list stays in the `.test.ts` file because `./themeTokenFreeze.ts` is not path-filtered as `__tests__` by the production source inventory. |
| Desktop chrome | `apps/dsa-desktop/renderer/assistant.html` and `loading.html` | Isolated inventories in `DESKTOP_CHROME_DEFINED_TOKENS`. The embedded WebView still uses the Web contract. Do not copy desktop `--bg` / `--panel` into Web Layer 1. |

**How to add a token.** Prefer an existing Layer 1 name plus use-site opacity (`hsl(var(--primary) / 0.12)`). If a new public token is required: add it to `THEME_LAYER1_CSS_VARS` (or Layer 0 only for market paint), define it on `:root` and `.dark`, append it to `THEME_DEFINED_TOKEN_NAMES`, and keep charts / price-direction / desktop chrome on the existing owners. Domain geometry may use `--nav-*` / `--report-*` / `--input-surface-*`. Never add a page-prefixed name.

**How to read a failure**

| Code | Meaning |
| --- | --- |
| `new-defined-token` / `ungoverned-defined-token` | `index.css` grew a name that is missing from the inventory or has no class. Follow the addition workflow; do not invent a page token. |
| `stale-defined-token` | Inventory lists a name that left `index.css`. Remove it from the inventory in the same PR. |
| `page-scoped-growth` | A new `--home-*` / `--settings-*` / … name. Delete it or reuse Layer 1. |
| `outside-definition` | A custom property was defined outside `index.css`. |
| `new-ungoverned-reference` | `var(--missing)` / `hsl(var(--missing))` is not defined and not on the shrink-only debt list. |
| `stale-ungoverned-reference` | A recorded undefined reference is gone. Shrink `THEME_UNGOVERNED_REFERENCE_DEBT`. |
| `blessed-page-token` | A page-prefixed name was classified as Layer 1. Keep it as `page-scoped-debt` or `legacy-alias`. |
| `desktop-token-growth` / `stale-desktop-token` | Isolated desktop chrome tokens changed. Update `DESKTOP_CHROME_DEFINED_TOKENS` only for that surface. |

Guards: `themeContractGuard.test.ts` (price-direction / pack / Layer 0) and `themeTokenFreezeGuard.test.ts` (name-set ratchet and counterexamples).

**Phase 2 domain collapse — Login (#1300).** The `--login-*` family is deleted; `LoginPage` reads Layer 1 directly. `THEME_PAGE_SCOPED_TOKEN_CEILING` moved 107 → 100 and six `--login-*` entries left the shrink-only `TOKEN_FORMAT_DEBT` list (32 → 26). No `--auth-*` domain token was introduced.

| Deleted token | Replacement | Light | Dark |
| --- | --- | --- | --- |
| `--login-bg-main` | `bg-background` | exact | exact |
| `--login-bg-card` | `bg-card` | drops the 0.86 alpha (Δ ≈ 0.4% lightness) | exact |
| `--login-border-card` | `border-border` | card outline softens (contrast 1.42 → 1.19 against the card) | outline firms up (1.19 → 1.37) |
| `--login-text-primary` | `text-foreground` | exact | exact |
| `--login-text-secondary` | `text-secondary-text` | exact | exact |
| `--login-text-muted` | `text-muted-text` | drops the 0.9 alpha; contrast 3.01 → 3.55 (improves, still below the 4.5 AA floor) | exact |
| `--login-accent-soft` | `selection:bg-[hsl(var(--primary)/0.08)]` | exact | exact |

Contrast method: WCAG 2.x relative luminance on the 8-bit sRGB colours the browser actually paints, with alpha composited source-over onto the surface underneath. The `before` light values therefore use the composited card `rgb(254,254,254)` (`hsl(var(--neutral-white) / 0.86)` over `--background`), not pure white: muted text `rgb(147,149,141)`, outline `rgb(214,216,211)`. The `before` dark outline is `hsl(var(--neutral-white) / 0.06)` over `--card`, i.e. `rgb(43,43,41)` on `rgb(29,29,27)`. Every colour in this table was confirmed as a painted pixel in rendered light and dark captures of both builds.

The card-outline delta is deliberate: `--border` is already the card boundary for the app shell, Home panels, and the sidebar, so Login now follows theme packs instead of pinning its own greys. Because Login consumes Layer 1, `data-theme-pack="slate"` recolours it for the first time. Deltas are non-text decoration; every text mapping is exact or better.

**Phase 2 domain collapse — Backtest (#1300).** The `--backtest-*` family is deleted. Four unused definitions (`--backtest-border-light`, `--backtest-spinner-head`, `--backtest-spinner-track`, `--backtest-table-bg`) are removed with no replacement. The two live call sites in Backtest Workspace now inline the previous light/dark foreground alphas: `--backtest-border-dim` → `hsl(var(--foreground) / 0.05)` (`.dark` `0.06`) on `.backtest-metric-row` and `.backtest-summary`; `--backtest-border-subtle` → `hsl(var(--foreground) / 0.06)` (untinted `.dark` fallback `0.08`) on `.backtest-status-chip`. Success/danger/neutral chip colors and `.backtest-metric-footer` (`--border / 0.40`) are unchanged. `BacktestPage.tsx` still uses layout class names only. `THEME_PAGE_SCOPED_TOKEN_CEILING` moved 100 → 94; `TOKEN_FORMAT_DEBT` stays 26 because these six names were not on that list. No new page-scoped token was introduced. The leftover borders now use the existing Layer 1 `--foreground` semantic token and could follow theme packs that override `--foreground`. The current `slate` pack overrides `--border` and does not override `--foreground`, so it does not currently recolour these borders.

**Phase 2 domain collapse — Portfolio (#1300).** The last `--portfolio-*` token, `--portfolio-control-border`, is deleted in both `:root` and `.dark`. The one live call site — `:root:not(.dark) .portfolio-page .btn-secondary:not(:disabled)` — now inlines `hsl(var(--foreground) / 0.2)`, matching the Backtest leftover-border recipe. Disabled, hover-shadow, and focus behavior stay on the existing `.btn-secondary` rules. Dark had no `.portfolio-page .btn-secondary` override; its unused assignment equalled `--border` (`75 4% 20%`) and is removed rather than replaced. `THEME_PAGE_SCOPED_TOKEN_CEILING` moved 94 → 93; `TOKEN_FORMAT_DEBT` stays 26 because this name was a conforming `hsl-triplet` override, not format debt. `portfolio` remains in `THEME_PAGE_SCOPED_PREFIXES` as a permanent ban. No replacement page or domain token was introduced. The leftover outline uses Layer 1 `--foreground` and could follow packs that override `--foreground`; the current `slate` pack overrides `--border` and does not override `--foreground`, so it does not currently recolour this border.

**Phase 2 domain collapse — Chat (#1300).** The `--chat-*` family is deleted: ten avatar/bubble names defined in `:root` plus `.dark`, and seven `--chat-prose-*` names defined locally on the `.chat-prose` rule. The consumers now read Layer 1 with use-site alpha and keep the previous light values on the base rule: `.chat-avatar-user` `hsl(var(--primary) / 0.5)` / `hsl(var(--foreground))` / `hsl(var(--primary) / 0.3)`; `.chat-avatar-ai` `hsl(var(--primary) / 0.1)` / `hsl(var(--foreground) / 0.8)` / `hsl(var(--primary) / 0.2)`; `.chat-bubble-user` `hsl(var(--primary) / 0.1)` background and `hsl(var(--primary) / 0.2)` border; `.chat-bubble-ai` `hsl(var(--card) / 0.85)` background. The dark assignments that actually differed move to explicit `.dark .chat-avatar-user`, `.dark .chat-avatar-ai`, and a `background-color` on the existing `.dark .chat-bubble-ai` rule, so the same `.dark` ancestor condition still selects them. `--chat-bubble-user-bg` / `--chat-bubble-user-border` had identical light and dark values, so no dark override was added. `--chat-bubble-ai-border` had no consumer (`.chat-bubble-ai` sets `border: 0`) and is removed with no replacement. For prose, `--chat-prose-fg` becomes `hsl(var(--foreground) / 0.86)` at its three call sites, and the former `.dark .chat-prose { --chat-prose-fg }` override becomes an explicit `.dark` group over `.chat-prose`, `h1`–`h4`, and `strong`; the later `.dark .chat-prose h2` secondary-text rule still wins on source order, as before. `--chat-prose-border` / `--chat-prose-border-strong` were pure aliases of `--home-prose-border` / `--home-prose-border-strong` and at that slice referenced those names directly, matching the sibling `.prose` rules; the later Home-prose collapse inlines those leftovers to Layer 1. `THEME_PAGE_SCOPED_TOKEN_CEILING` moved 93 → 76; `TOKEN_FORMAT_DEBT` stays 26 because none of the 17 names were on that list, and the two `TOKEN_FORMAT_OVERRIDES` entries for the prose border aliases are removed because that guard requires every override key to still be defined. The `themeContractGuard` / `themeTokenFreezeGuard` non-vacuity floors move 200 → 190: they are lower bounds against a truncated inventory, and the four Phase 2 collapses have now taken the defined inventory from 210 to 196. `chat` remains in `THEME_PAGE_SCOPED_PREFIXES` as a permanent ban and no replacement page or domain token was introduced. Theme-pack behaviour is unchanged: the deleted names were already defined on `:root` in terms of `--primary` / `--card` / `--foreground` / `--background`, so Chat followed packs before and after. A rendered `data-theme-pack="slate"` comparison recolours the same eight elements (`chat-avatar-ai`, `chat-avatar-user`, `chat-bubble-ai`, `chat-bubble-user`, and the prose link / code / pre / blockquote) in both builds.

**Phase 2 domain collapse — Settings (#1300).** The `--settings-*` family is deleted: twenty names defined on `:root` plus `.dark`. Eight unused definitions (`--settings-accent-shadow`, `--settings-border-overlay`, `--settings-primary-border`, `--settings-secondary-bg`, `--settings-secondary-bg-hover`, `--settings-secondary-border`, `--settings-secondary-border-hover`, `--settings-surface-overlay`) are removed with no replacement. Live consumers now read Layer 1 plus use-site alpha: `--settings-surface` / `--settings-surface-strong` → `bg-card`; `--settings-surface-hover` → `bg-hover`; `--settings-surface-panel` → `bg-background`; `--settings-surface-overlay-soft` → `bg-muted`; `--settings-surface-overlay-muted` → `bg-[hsl(var(--background)/0.12)]`; `--settings-border` → `border-border`; `--settings-border-soft` → `border-border/60`; `--settings-border-strong` → `border-foreground/20` / `hover:border-foreground/20`; `--settings-skeleton-strong` → `bg-muted`; `--settings-skeleton-soft` → `bg-muted/50`. The Settings rest-only input override stays on `.settings-page .input-surface:not(:hover):not(:focus):not(:disabled)` and inlines `hsl(var(--border) / 0.72)` light and `hsl(var(--border) / 0.58)` dark. Hover, focus, error, and disabled remain on shared `.input-surface` / `Input` / `border-danger` / disabled opacity. Helper classes `.settings-surface-strong`, `.settings-surface-panel`, `.settings-surface-overlay-soft`, `.settings-surface-overlay-muted`, `.settings-border`, `.settings-border-strong`, `.settings-skeleton-strong`, and `.settings-skeleton-soft` are deleted; `.settings-accent-text` and `.settings-drag-active` stay because they already use Layer 1 `--primary`. `THEME_PAGE_SCOPED_TOKEN_CEILING` moved 76 → 56; `TOKEN_FORMAT_DEBT` moved 26 → 12 after dropping the fourteen Settings raw-`hsl()` rows. The `themeContractGuard` / `themeTokenFreezeGuard` non-vacuity floors move 190 → 170: the defined inventory is ~176 after deleting these twenty names. `settings` remains in `THEME_PAGE_SCOPED_PREFIXES` as a permanent ban and no replacement page or domain token was introduced. Because Settings now consumes Layer 1, `data-theme-pack="slate"` recolours its cards and borders for the first time. Layer 0 price paint and `--home-price-*` aliases are unchanged.

The light card-outline delta is deliberate and non-text: `--settings-border` was raw `hsl(80 7% 82% / 0.94)` over the card, while Layer 1 `--border` is `80 7% 92%`. Settings now follows the same outline as Login, the app shell, and Home panels instead of pinning a darker grey. Contrast method: WCAG 2.x relative luminance on the 8-bit sRGB colours the browser actually paints, with alpha composited source-over onto the surface underneath (same Login table).

| Pair | Light before | Light after | Dark before | Dark after |
| --- | --- | --- | --- | --- |
| Card fill vs page | exact white (`rgb(255,255,255)`; `neutral-white / 0.97` over `--background` already rounds to white) | exact (`bg-card`) | near-transparent wash `rgb(26,26,25)` | `bg-card` `rgb(29,29,27)` |
| Card outline vs card | 1.45 (`rgb(213,215,209)` on white) | 1.19 (`--border` `rgb(235,236,233)` on white) | 1.34 (`white / 0.1`) | 1.37 (`--border` `75 4% 20%`) |
| Hover fill | exact `rgb(243,243,241)` | exact (`--hover` is already `80 7% 95%`) | `white / 0.05` `rgb(37,37,36)` | `--hover` `rgb(42,42,39)` |
| Strong hover outline vs card | 1.90 | 1.54 (`foreground / 0.20`) | 1.90 | 1.90 |
| Input rest outline vs card | 1.24 (`80 7% 86% / 0.72`) | 1.13 (`--border / 0.72`) | 1.21 (`--border / 0.58`) | 1.19 |
| Foreground text vs card | 18.27 | 18.27 | 17.42 | 16.88 |
| Secondary text vs card | 5.86 | 5.86 | 8.98 | 8.71 |

Text stays well above WCAG AA. Outline/hover softening is decoration-only, matching Login’s card-outline table. After collapse, `data-theme-pack="slate"` recolours Settings borders (`--border` `210 10% 90%`, outline contrast 1.25 vs white) and hover (`210 12% 95%`) for the first time.

**Phase 2 domain collapse — Home-action (#1300).** The `--home-action-*` family is deleted: eight names defined on `:root` plus `.dark`. Four unused definitions (`--home-action-report-bg`, `--home-action-report-border`, `--home-action-report-text`, `--home-action-report-hover-bg`) are removed with no replacement. The one live call site — Chat jump-to-bottom `.chat-copy-btn` (`ChatPage.tsx` `showJumpToBottom`; the class name is historical) — now inlines Layer 1 `--primary` with use-site alpha: background `hsl(var(--primary) / 0.1)`, border `hsl(var(--primary) / 0.2)`, color `hsl(var(--primary))`. Light hover stays `0.18`; dark hover is an explicit `.dark .chat-copy-btn:hover` at `0.2` and must not be unified. `:active` transform, the grouped `:focus-visible` ring shared with `.session-item` / `.delete-btn` (`box-shadow: 0 0 0 3px hsl(var(--primary) / 0.16)`), and `min-height: 2.75rem` stay on the existing rules. Message copy/download stay on `IconButton` and do not use `.chat-copy-btn`. `THEME_PAGE_SCOPED_TOKEN_CEILING` moved 56 → 48; `TOKEN_FORMAT_DEBT` stays 12 because none of the eight names were on that list. The `themeContractGuard` / `themeTokenFreezeGuard` non-vacuity floors move 170 → 160: the defined inventory is 168 after deleting these eight names. `home` remains in `THEME_PAGE_SCOPED_PREFIXES` as a permanent ban and no replacement page or domain token was introduced. Theme-pack behaviour is unchanged: the deleted names already wrapped `--primary`, so the jump button followed packs before and after. Do not claim first-time slate recolour. Layer 0 price paint and `--home-price-up/down` aliases are unchanged. Remaining `--home-*` families (prose, cool, shadow, panel, surface) are out of this slice.

**Phase 2 domain collapse — Home-prose (#1300).** The `--home-prose-*` family is deleted: four names defined on `:root` plus `.dark` (`--home-prose-border`, `--home-prose-border-strong`, `--home-prose-blockquote-border`, `--home-prose-blockquote-bg`). Live call sites now inline Layer 1 with use-site alpha and keep the previous light values on the base rule: border `hsl(var(--foreground) / 0.1)`, strong `hsl(var(--foreground) / 0.16)`, blockquote border `hsl(var(--primary) / 0.28)`, blockquote background `hsl(var(--primary) / 0.06)`. Dark assignments that differed move to explicit `.dark` rules on the same selectors (`.12` / `.18` / `.3` / `.08`) and must not be unified. Consumers stay on existing classes: `.report-markdown-prose` `h1` / `pre` / `th, td` / `th` / `hr` / `blockquote`; shared `.prose` table `th, td` / `th`; `.chat-prose` `pre` / `th, td` / `hr`. `.chat-prose blockquote` already uses `--secondary-text` alpha and is unchanged. `THEME_PAGE_SCOPED_TOKEN_CEILING` moved 48 → 44; `TOKEN_FORMAT_DEBT` stays 12 because none of the four names were on that list. The `themeContractGuard` / `themeTokenFreezeGuard` non-vacuity floors stay at 160: the defined inventory is 164 after deleting these four names. `home` remains in `THEME_PAGE_SCOPED_PREFIXES` as a permanent ban and no replacement page or domain token was introduced. Theme-pack behaviour is unchanged: the deleted names already wrapped `--foreground` / `--primary`, so prose followed packs before and after. Do not claim first-time slate recolour. Layer 0 price paint and `--home-price-up/down` aliases are unchanged. Remaining `--home-*` families (cool, shadow, panel, surface) are out of this slice.

**Phase 2 leftover collapse — Home-title-accent (#1300).** `--home-title-accent` is deleted from `:root` and `.dark`. The historical class `.home-title-accent` stays and now inlines `color: hsl(var(--foreground));`. Light and dark were already the same Layer 1 wrap, so there is no `.dark` split. Do not write `color: var(--foreground)` (`--foreground` is an HSL triplet) and do not move the colour onto a Tailwind `text-foreground` class (that would edit TSX). `.home-title-accent` and `.label-uppercase` are equal-specificity single-class rules. `.home-title-accent` must stay earlier (`color: hsl(var(--foreground))`); later `.label-uppercase` still sets `color: var(--text-secondary-text)` and therefore wins computed eyebrow paint. Computed paint remains `--text-secondary-text`. Do not move the rule or raise specificity to make `--foreground` win — that would recolour the playground. `DashboardPanelHeader` keeps the class name and `accentEyebrow` default `false`; when the flag is true the eyebrow still mounts both classes. Production Home / watchlist / report / history / task call sites currently omit the flag, so those headers do not change colour; the live caller is playground `dashboard-panel-header`. `THEME_PAGE_SCOPED_TOKEN_CEILING` moved 44 → 43; `TOKEN_FORMAT_DEBT` stays 12 because this name was not on that list. The `themeContractGuard` / `themeTokenFreezeGuard` non-vacuity floors stay at 160: the defined inventory is 163 after deleting this name. `home` remains in `THEME_PAGE_SCOPED_PREFIXES` as a permanent ban and no replacement page or domain token was introduced. Theme-pack behaviour is unchanged: the deleted name already wrapped `--foreground`, and the current `slate` pack does not override `--foreground`. Do not claim first-time slate recolour. Layer 0 price paint and `--home-price-up/down` aliases are unchanged. Remaining `--home-*` families (cool, shadow, panel, surface, unused wrappers) are out of this slice.

**WAIT_FOR density integration.** Repeating the 18 structural spacing custom-property names as string literals in `themeTokenInventory.ts` is measured by `densityAdoptionRatchet` as `new-density-aware-file` (`../../design/themeTokenInventory.ts`, `densityTokenCount=18`, `fixedSpacingCount=0`). That is a catalog-string false positive, not theme-token consumer adoption. T24 does **not** change `densityAdoptionRatchet.ts` or weaken that scanner. The inventory composes those names from `DENSITY_STRUCTURAL_CSS_VARS` instead of repeating the literals. Density implementation/review should decide whether non-`density.ts` design catalogs belong in the consumer inventory; do not raise the density baseline or add a scanner bypass on this PR.


- Foundation owns semantic tokens and shared control geometry.
- Primitives own native semantics, refs, disabled/loading states, focus, and
  coarse-pointer targets.
- Patterns may compose primitives but must not redefine their core geometry.
- Pages and domain components own business state and localized content only.

## Shared Primitives

| Primitive | Contract |
| --- | --- |
| `Button` | Requires an explicit intent, forwards the native button ref, and exposes semantic variant and size state. |
| `Pressable` | Provides native button semantics, focus, disabled state, and a coarse-pointer hit target for compound rows or cards whose visual treatment remains caller-owned. |
| `SelectionChip` | Provides a compact text-led selection command that grows for multi-line content without caller-owned geometry. |
| `IconButton` | Requires an accessible name, provides an optional tooltip, separates its visible icon surface from its coarse-pointer hit target, and owns the 44px `navigation` size used by shell and rail controls. |
| `Spinner` | Provides one reduced-motion-safe loading glyph; it stays decorative inside an already labelled busy control and becomes a labelled status only when it owns the announcement. |
| `Progress` | Requires an accessible label, normalizes determinate values, exposes an indeterminate state, and limits indicator styling to semantic tones without page-owned width or animation markup. |
| `FileInput` | Provides the hidden native file control used with a visible shared `Button` or `IconButton` trigger; file validation and product copy remain caller-owned. |
| `Input` | Forwards the native input ref, owns label/hint/error wiring, and uses a focusable coarse-pointer frame around the visible input. |
| `Field` | Associates a label with one control, renders either an error or hint, and forwards its wrapper ref. |
| `Textarea` | Reuses `Field`, forwards the native textarea ref, and owns invalid/description semantics. |
| `Surface` | Forwards native sectioning-element attributes and refs while exposing one semantic `canvas` / `section` / `interactive` / `overlay` level. |
| `Alert` | Owns info/success/warning/danger presentation, `compact` / `default` density, live-region urgency, shared dismiss controls, and action placement. |

Shared patterns compose these primitives:

| Pattern | Contract |
| --- | --- |
| `Section` | Renders a visible heading and associates it with a semantic section; actions and content remain within one surface boundary. |
| `StatePanel` | Represents one typed task state and owns its live-region, busy, icon, density, description, and action semantics. |
| `FilterBar` | Owns the compact primary-filter form, Apply command, advanced-filter slot, and applied-filter summary slot. |
| `AdvancedFilterSheet` | Uses a non-modal dialog Popover at 768px and wider, a bottom Sheet below 768px, and one fixed reset/apply footer. |
| `ResponsiveFilterPanel` | Keeps basic filters visible, exposes advanced filters inline at desktop, and moves those advanced filters plus Apply into a Drawer below 1024px. |
| `AppliedFilterChips` | Presents applied filters as individually removable tokens with one clear-all command. |
| `useFilterQueryState` | Keeps applied filters in Router search params, preserves unrelated params, keeps drafts local, and restores both after Back/Forward navigation. |
| `DataTable` | Renders typed columns and native table semantics, framed or embedded presentation, controlled sorting/selection, fixed or automatic layout, one task state, contained scrolling, optional fixed-estimate row virtualization above a measured threshold, and isolated row activation. |
| `AppPage` / `WorkspacePage` | Provide the full-width page canvas and optional main/rail workspace grid beneath the Shell's single `main`. |
| `PageHeader` / `Toolbar` | Provide one programmatically focusable H1 and one semantic command group without adding a decorative page surface. |
| `ResponsiveRail` | Keeps contextual content visible at wide desktop and exposes one labelled disclosure at narrower breakpoints. |
| `Tabs` / `TabPanel` | Implement same-page panel selection with associated tab/panel IDs and horizontal roving focus. |
| `SummaryStrip` | Presents continuous summary metrics as one labelled definition list rather than a card grid. |
| `WorkspaceNavigation` | Uses Router Links for sibling routes and a native compact select; route navigation never masquerades as Tabs. |
| `RouteFocusCoordinator` / `useRouteFocusTarget` | Coordinate ready H1 focus after PUSH/REPLACE and stable trigger restoration after POP without exposing history metadata to pages. |

Every caller-visible string, including `aria-label` and tooltip content, must
come from the existing i18n resources.

### Shared-control adoption ratchet

Product TS/TSX must use the shared button primitives above instead of growing
new native `<button>` hosts or `role="button"` stand-ins. Native `input` /
`select` / `textarea` remain on the existing form-control guard
(`nativeFormControlAdoptionGuard.test.ts`). This task does **not** mass-migrate
current product buttons.

The scanner (`sharedControlAdoptionRatchet.ts`) walks the TypeScript AST — not a
raw substring count — so aliases (`const Tag = 'button'`), multiline JSX,
spread props, `createElement('button')`, and `document.createElement('button')`
count, while comments, type-only `'button'` literals, and selector strings such
as `'[role="button"]'` do not.

**Required owners.** `Button`, `IconButton`, `Pressable`, and `SelectionChip`
must keep a native button (`SHARED_CONTROL_REQUIRED_OWNERS`). Losing that
element is a regression.

**Compound owners.** DatePicker, Tabs, Select, DataTable sort headers, and the
other files in `SHARED_CONTROL_COMPOUND_OWNERS` may render native buttons
because they *are* the shared control. Count changes still require a baseline
edit.

**Measured baseline.** `apps/dsa-web/src/design/sharedControlAdoptionBaseline.json`
is snapshotted from the current production tree. Per-file `nativeButtonCount` /
`roleButtonCount` are shrink-only ceilings for business files. New unaudited
files fail as `new-bypass`. File moves with the same basename and counts fail as
`file-moved` until the JSON path is updated.

**Approved accessibility exemptions.** `SHARED_CONTROL_A11Y_EXEMPTIONS` is the
only production exception list. Current entries are the SVG scatter hit target
on Decision Signals and the native `details`/`summary` disclosure on the run-flow
timeline. Do **not** park leftover product-button debt here.

**Inventory exclusions** (documented in `SHARED_CONTROL_SCAN_EXCLUSIONS`): tests,
fixtures, generated files, vendor/`node_modules`, `src/dev/**`, playground, and
stories. Those trees are not shipped product UI.

| Code | Meaning |
| --- | --- |
| `missing-required-owner` / `lost-owner-file` | A shared control dropped its native button. Restore it. |
| `new-bypass` / `bypass-regression` | New or extra native/`role="button"` usage outside owners. Use `Button` / `IconButton` / `Pressable`, or add a reviewed a11y exemption. |
| `baseline-needs-tightening` / `lost-debt-file` | The tree improved. Update the JSON ceiling. |
| `file-moved` | Same basename and counts at a new path. Update the JSON path; do not treat the move as a free new bypass. |
| `stale-exemption` / `exemption-overflow` | Fix `SHARED_CONTROL_A11Y_EXEMPTIONS`. |

## Filter And Query Semantics

Applied filters are navigation state. A page supplies a typed
`FilterQueryCodec` that reads and normalizes its owned search-param keys and
writes only those keys. `useFilterQueryState` starts every write from the
current Router params, so report provenance, source context, and other
unrelated query state survive filter changes. Apply uses a new history entry by
default; Back and Forward therefore restore both the applied value and local
draft. Canonicalization-only callers may explicitly opt into replace
navigation.

The hook exposes separate applied and draft counts, dirty state, draft reset,
draft discard, applied reset, and direct applied-value updates for individual
chip removal. Filter controls must disable Apply when the draft is unchanged
or a request is in flight. Applying filters may explicitly clear pagination
keys, but the codec must not delete query keys owned by another route concern.

`AdvancedFilterSheet` uses the existing semantic Overlay foundation. At the
desktop breakpoint its non-modal dialog Popover moves focus to the first
control and restores the trigger when dismissed. Below that breakpoint it
uses `FilterSheet`, including the fixed header/body/footer, Escape, focus trap,
scroll lock, and trigger restoration contracts. Crossing the 768px breakpoint
while filters are open closes the old container and restores its trigger before
the other container can be opened. The caller owns all visible
and accessible strings; the Pattern owns no business copy or API request.
Both advanced-filter forms contain their submit event so a portalled form
composed inside `FilterBar` cannot also submit the outer primary-filter form.

`ResponsiveFilterPanel` remains the narrower PR #35 contract used by Decision
Signals. Basic filters stay visible at every width; advanced filters and Apply
stay inline from 1024px upward and move into one focus-managed Drawer below
that breakpoint. The mobile trigger reports the active-filter count, Apply is
blocked while unchanged or in flight, and a loading Apply cannot close the
Drawer early. New filter surfaces should prefer `FilterBar` plus
`AdvancedFilterSheet` unless they need this existing split-filter contract.

## Deep Link And URL State Semantics

`utils/deepLink.ts` is the neutral authority for links that move stock,
report, chat, portfolio, or decision-signal context between major views.
Callers use the typed `buildDeepLink()` target union instead of interpolating
query strings. `parseDeepLink()` accepts only same-origin stable routes,
canonicalizes stock codes and positive numeric identities, removes invalid
owned values, and preserves unrelated non-sensitive query parameters. The
shared route guard applies that normalization before a product page renders,
so every major route consumes the same validation and sensitive-key policy.

The current shareable state contract includes Analysis Workbench segment,
report, stock prefill, and Run Flow identity, Chat session/report context,
Portfolio account scope, stock-details period/range, Decision Signals stock,
signal, view, and filter context, and the existing page-owned filter codecs.
Research Discover and Research Backtest use one typed route-state codec across
their page initialization, the deep-link guard, and session continuity. The
codec removes malformed owned values before page effects can issue API calls,
replace-normalizes the URL, and preserves unrelated non-sensitive query and
hash state.
Stable view choices create history entries when Back/Forward should restore
them. Canonicalization, missing-resource fallback, and ordinary default-value
removal use Router replace navigation so they do not create dead history
entries. Discover keeps a deliberate exception: when explicit owned input
normalizes entirely to defaults, the canonical default-valued keys remain in
the URL as durable ownership markers. If any non-default owned value remains,
redundant defaults are still omitted. This conditional encoding keeps compact
URLs where possible without letting refresh, authentication, or a legacy
redirect mistake explicit intent for a bare route. A
valid but unavailable Portfolio account falls back to the first available
account (or all accounts) and displays the shared invalid-link warning.
Chat keeps validated stock/name/report identity in the URL until the prepared
follow-up is sent; refresh can therefore rebuild the unsent prompt and report
context. Sending, starting a new chat, or explicitly switching sessions removes
that pending context while retaining the stable session identity.

Credentials, authorization values, passwords, private keys, and secret-like
parameters never belong in a deep link. The route guard removes recognized
sensitive keys, including provider-prefixed API key and token names, before
state restoration and presents a localized warning when URL state is cleaned.
An invalid stock path is replaced with safe Home state before the stock page
can issue requests. Draft text, unsaved forms, notification payloads, and
other potentially sensitive state stay out of URLs. A valid stock prefill or
selected stock context may be represented, but draft stock text is not written
to the URL and a restored Workbench stock never auto-submits analysis. Legacy
Home analysis parameters are normalized into the Workbench before Home renders.

Electron currently consumes the same browser routes after loading its private
local Web origin. External custom-protocol registration and OS `open-url` or
second-instance URL forwarding are not part of the Web contract and require a
separate desktop-owned change.

## Session Continuity And Privacy

The Router URL remains the primary state owner. A tab-scoped continuity layer
stores only allowlisted, normalized route snapshots for Home, Chat, Portfolio,
Decision Signals, Research Market, Research Discover, Research Analysis,
Research Backtest, and stock details. On a fresh document
load, a bare major-route URL may replace itself once with the last snapshot for
that route, except bare Home, which always remains the attention hub instead of
restoring old analysis context. Explicit URL state always wins, and later in-app
navigation is not overridden by the initial restore guard.

An active Screening task keeps its opaque task ID for status recovery, but its
stored run parameters are only a fallback for a bare Discover URL. Any explicit
Discover-owned parameter selects the complete URL-owned run state, so stale
task parameters cannot rewrite a canonical or legacy-redirect deep link. Safe
custom strategy IDs remain URL-owned when absent from the current preset
catalog, including when that catalog is empty. The primary strategy selector
presents that retained value as the active custom option instead of an
unavailable-catalog placeholder. With an empty catalog, the selector remains
disabled only when there is no safe retained custom ID to present. Wholly
malformed owned input normalizes to explicit canonical defaults
instead of becoming bare, preserving the same precedence across refresh.

Research Analysis continuity includes the validated task/history Run Flow
identity owned by the Workbench URL. A same-stock return restores its active
detail overlay; carrying a different stock drops report and Run Flow identities
whose affinity cannot be proven. Home never receives that destination snapshot,
so its Sidebar link cannot loop back into Workbench. The current explicit route
also wins immediately over a stale snapshot, so clearing a destination filter
cannot be undone by its own Sidebar link.

Application navigation carries the current validated stock context into Chat,
Decision Signals, and Research Backtest. Destination-specific state such
as a Chat session, Portfolio account, Decision Signals tab/filter set, Research
Discover parameters, or Research Backtest range remains scoped to that
destination. Clearing a
route's URL-owned state overwrites its snapshot, so the persistence layer
cannot resurrect filters or selections the user intentionally removed.
Decision Signal details with a source report provide a one-click handoff to the
canonical Workbench history URL for the same stock.

Chat distinguishes an unconsumed report handoff from an active conversation
context. The first form preloads the follow-up draft. After that draft is sent,
the normalized stock, optional name, and report ID remain in the URL with
`context=active`, so shared navigation can carry the same identity without
recreating the consumed draft on refresh. An explicit in-chat stock switch
updates the URL to the new stock and drops the previous report identity.

Workflow continuity uses `sessionStorage`, not `localStorage`. This keeps route
snapshots, opaque Chat session IDs, Deep Research questions/results, and active
Screening task IDs within the current browser tab and browser session. Existing
Chat and Deep Research values written by older versions are migrated out of
`localStorage` on first read. Draft Chat text, unsaved forms, credentials,
authorization values, provider keys, and arbitrary query parameters are never
persisted by this layer.

Logout and authenticated-session expiry clear all StockPulse workflow traces
from both current `sessionStorage` and the known legacy `localStorage` keys,
abort and reset in-memory Chat state, and reset the shared analysis dashboard store.
Durable non-sensitive preferences such as UI language, theme, and sidebar
presentation remain intact. A completed logout replaces the active route with a
plain `/login`, without a redirect containing the prior workflow identity.
Browser history and explicitly shared deep-link URLs remain browser-owned and
are not rewritten retroactively.

## Selection Control Semantics

`SelectionChip` is the shared compact choice for text-led candidates whose
labels may wrap, such as a code followed by a long display name and market.
It remains a native non-submitting button, forwards its ref and native event
attributes, owns a 36px minimum visible height, and grows naturally when its
content needs another line. The coarse-pointer pseudo-element provides the
44x44px effective target without forcing every single-line choice to show a
44px background.

While `isLoading` is true, the primitive exposes `aria-busy`, prevents native
activation, and replaces the trailing state indicator with a spinner that
stops animating under reduced motion without changing the accessible name.
The primitive owns `aria-busy`; callers continue to own business-specific
progress messaging outside the control when additional context is required.

Callers omit `selected` for one-shot selection or navigation commands. When a
selection remains current after activation, callers supply `selected`; the
primitive then exposes `aria-pressed`, stable selected/unselected icon space,
and semantic selected styling. `SelectionChip` does not accept `className`,
`style`, `type`, caller-owned `aria-busy`, or caller-owned `aria-pressed`, so
its height, padding, rounding, width and state cannot drift by page.

The generic `label`, `description`, and `metadata` slots insert real text
separators before applying visual spacing and semantic text tones. This keeps
the accessible name readable when callers compose several data fragments;
CSS margin or flex gap must not be the only separation between spoken values.

This control is not an applied filter, status token, Tab, SegmentedControl
item, or icon tool. Applied values that activate removal continue to use
`FilterChip`; page sections and rows use their corresponding Pattern. The
multi-line Decision Signals candidate Button migrated to `SelectionChip`
under `UI-D01`; the page no longer owns a Button geometry allowance.

## DataTable Semantics

`DataTable<T>` is the shared authority for continuous business data. Callers
provide typed columns, stable row keys, localized caption and state copy, and
the already ordered row set. The Pattern does not fetch, paginate, infer a
business schema, or sort data internally. Optional sort controls emit the next
`columnId` / `ascending|descending` state; the caller owns local or server-side
ordering. Every sortable column supplies its own localized accessible label,
and the native column header exposes `aria-sort`.

The default `surface` frame renders one interactive table Surface. The explicit
`embedded` frame omits that Surface so a report Card, settings frame, overlay,
or Section remains the sole contextual Surface; its state path is likewise an
unframed canvas `StatePanel`. Empty rows use the required `emptyState`; loading,
error, and retrying use one explicit `status` and hide the table so duplicate
state blocks cannot appear. State content reuses `StatePanel` roles, live
regions, busy state, and actions. Callers cannot pass `className`, `style`, or
Surface attributes through `DataTable`; contextual layout belongs on a wrapper
and cell typography belongs inside the cell renderer. `default`, `subtle`, and
`inherit` separator tones cover shared tokens and a caller-owned contextual
frame without introducing domain-specific variants.

On narrow screens the native table remains a table inside a named, keyboard-
focusable horizontal scroll region. `container`, `narrow`, `content`, `wide`,
and `extra-wide` are stable minimum-width contracts; scrolling is contained
within the Pattern and must never increase document width. `fixed` layout owns
the native `colgroup` and normalizes a complete set of positive percentage
widths, while the default `auto` layout leaves sizing to table content. This
preserves dense financial columns and their headers instead of duplicating rows
into a second card DOM.

`DataTable` reuses the existing `useVirtualWindow` hook at this shared
boundary. Tables with fewer than 24 body rows stay fully mounted so browser
find, keyboard tab order, and assistive-technology row lists remain complete.
At or above that threshold the body is a fixed-estimate window: default rows
are 48px, compact rows are 36px, overscan is 6, and the scroll region is
capped at 480px with an opaque sticky header (`bg-card`, not the 3%
`bg-subtle-soft` wash). Top and bottom spacer rows preserve
scroll height so the first and last business rows remain reachable. Visible
rows keep their original `getRowKey` identity, `cell(row, index)` index, and
selection/activation handlers. The native table exposes `aria-rowcount` and
`aria-rowindex` while windowed. Pass `virtualization={false}` for
incompatible variable-height cells; controlled detail rows (`renderRowDetail`)
disable windowing automatically. Auto-window does not measure rendered
height, so any table whose cells wrap, stack, list, or exceed the 48px /
36px estimate must opt out even when the current page size is below 24.
DataTable does not implement `rowspan`. Current production fallbacks:
Screening results (detail rows), `RiskHeatmap`, the Portfolio risk
correlation matrix, Event Calendar, Screening Discovery, the stock-history
trend drawer, Portfolio position signal cells, Token Usage recent calls,
import failed-row reasons, Personal Performance reason lists, Event
Alerts, and the remaining wrapping or stacked production tables. Fixed-
height numeric tables such as stock candles and compound-growth series
stay on auto-window.

An activatable row requires both `onRowActivate` and a localized
`getRowAriaLabel`. Click, Enter, and Space invoke the same command. Events from
nested `button`, link, input, label, select, textarea, summary,
`contenteditable`, focusable element, or interactive ARIA role are ignored, so
row navigation cannot fire together with an edit, menu, link, or form control.
Disabled rows leave the activation tab sequence and expose `aria-disabled`.
Optional `isRowSelected` keeps controlled row selection, `aria-selected`, and
the selected visual treatment in the Pattern. `getRowTestId` provides a narrow
stable identity hook where product tests must address a business row; arbitrary
row attributes remain private to the implementation.

Optional controlled detail rows require both `isRowDetailVisible` and
`renderRowDetail`. `DataTable` owns the sibling row, full-column span, density,
semantic detail fill, stable optional ID, and accessible optional row label;
the caller owns business content and the command that controls visibility.
That command must expose `aria-expanded` and `aria-controls` when it targets a
stable detail-row ID.

Stock history trend, Market Review indices, Run Flow attempts, the Settings AI
overview matrix, and Token Usage recent calls now consume these shared
contracts. The production raw-table allowance inventory is empty; the guard
continues to reject any raw table outside the shared owner.

## Page And Router Semantics

The Shell already renders the application's sole `main` landmark, so
`AppPage` remains a full-width `div` and exposes its semantic Pattern and width
state through data attributes. It forwards native attributes and its ref.
`WorkspacePage` composes this canvas with one primary content region and an
optional contextual rail; neither component adds a Card or Surface boundary.

`PageHeader` renders the page's one H1, forwards the H1 ref, and owns
`tabIndex={-1}`. This lets the Router focus authority move focus after a
same-window transition without adding the heading to normal Tab order.
`Toolbar` owns `role="toolbar"` and command grouping but no glass/card visual.
Callers provide localized titles, descriptions, action labels, and toolbar
names.

`ResponsiveRail` is an `aside` named by its visible H2. At `xl` it is visible
and sticky within the workspace; below `xl` it becomes one native button
disclosure with caller-provided expand/collapse names. Its compact open state
is controlled or uncontrolled and never enters business URL state. The
disclosure retains the shared labelled Tooltip and 44px `navigation` target.
`SummaryStrip` is one labelled definition list with stable metric IDs and
semantic state tones; it does not create a row of nested cards.

`Tabs` and `TabPanel` are reserved for mutually exclusive content under one
page H1. They own tablist/tab/tabpanel association, disabled-item skipping,
Left/Right/Home/End movement, and native Enter/Space activation.
`SegmentedControl` defaults to the same tab semantics when it switches panels;
when it chooses one value without controlling a panel, callers select its
`single-select` contract, which exposes a radiogroup/radio relationship and
the same disabled-item and boundary-key navigation. Panel-controlling callers
may provide a stable ID so its triggers share the `TabPanel` ID contract.
Sibling page routes use
`WorkspaceNavigation` instead: desktop renders real Router Links with one
`aria-current="page"`, while compact layouts render a labelled native select
that hands the selected item back to the caller. Route item IDs, not translated
labels or array indexes, provide stable focus markers.

The owner-selected PR #35 page restoration keeps Settings, Portfolio, Signal
Center, and Backtest on the full-width `AppPage` canvas. Each exposes the shared
visible `PageHeader`. Signal Center provides four top-level shared `Tabs` /
`TabPanel` views and composes the existing decision-signal and alert surfaces
without creating a second page identity. Decision Signals selection identity is
`selectedSignalId` / `?signal=<id>`; list, latest, and timeline only supply
candidates and a display source, and a fixed Context Chip shows symbol, source,
and status. Closing the detail drawer leaves that chip visible and non-inert so
it can reopen the same id; feed refreshes restore or update by id and do not
overwrite a newer selection from another entry point. Its scope selector is a pressed-button
group, not another tablist, and is only rendered for the signal and rule views
that apply that scope to their requests. Portfolio renders one
page-level onboarding state when no account exists, and Backtest renders one
page-level loading, error, or empty state before results exist. Alert-rule
filters belong to the Card header at `sm` and wider and stack full-width below
`sm`; Decision Signals uses `ResponsiveFilterPanel` for its basic/advanced
split. Later account editing, manual signal creation, URL state, shared
`DataTable`, alert-rule editing, and notification-attempt filtering remain
available inside those restored structures.

Settings keeps regular configuration visible and editable in page flow; it
must never collapse those fields to a heading, summary, and Configure command.
This applies to Agent Behavior, Conversation, Reports, Alerts, Backtesting,
System & Security, task routing, reliability, raw advanced configuration,
scheduler, and event monitor settings. Their field groups use the shared
`Input`, `Select`, `Textarea`, and `TimePicker` controls directly in the active
section, alongside operational status and related page actions. Intelligent
Import keeps file/image selection and pasted text in a compact two-column
layout at large widths; its review commands, row removal, and sticky merge
action use the shared command primitives while preserving coarse-pointer
targets.

The shared `Modal` is reserved for discrete submission flows: adding or editing
one intelligence source, provider, or notification channel; authentication or
password changes; notification tests; and comparable single-entity forms. It
owns focus lifecycle, Escape handling, and the action footer for those flows,
but is not a blanket wrapper for regular configuration. Data Sources keeps its
quote/news configuration, source directories, status, and results inline.
Provider and notification-channel directories likewise remain inline for
scanning, with only an individual add/edit form opening a `Modal`. Readiness,
runtime status, version, import/backup, and result-oriented content stay in
page flow. Sensitive directory state exposes only configured or not configured,
never a credential or masked value. Settings field rows reserve one 240px
desktop control column, and every shared field control fills that same column;
`Input` and `Select` use the same control height. The sidebar profile consumes
`ThemeToggle`'s opt-in compact `Select` presentation so theme and language
choices use the same neutral option geometry. On desktop, both Profile menus
open to the right of their field; shared popup collision handling keeps them
inside the viewport and caps long option lists. Standalone ThemeToggle consumers
retain the default vertical menu.

`RouteFocusCoordinator` is mounted once inside the data Router. A page may
only call `useRouteFocusTarget({ routeId, headingRef, ready })`; it cannot pass
a navigation type, location key, history entry, or trigger key. Direct load,
refresh, and new-tab entry leave focus untouched. Cross-path PUSH and REPLACE
wait for a connected ready H1 before focusing it. Cross-path POP restores one
unique, rendered, focusable trigger for that history entry; duplicate,
missing, disabled, hidden, stale, or unsuccessfully focused triggers fail
closed to the ready H1. Same-path query/hash updates retain the active control;
an exact-URL PUSH with a new history key remains an independent H1 transition.
Same-path POP may restore a unique stable trigger but never falls back to the
H1. Blocked navigation retains its trigger until the Router proceeds or resets
the transition. Entries are bounded in memory and contain strings only, never
DOM refs, URL state, browser history state, `localStorage`, or `sessionStorage`.
When a responsive overlay trigger is transient, it may declare one
`data-route-focus-return-key` that names its persistent counterpart. The
coordinator validates the transient source and requires exactly one persistent
alias before storing that alias per `location.key`; an empty, missing, or
duplicate alias fails closed. Shell and navigation components only render the
stable markers and never copy route metadata or rewrite the persistent key.

Business code must use React Router navigation APIs rather than direct
`pushState` or `replaceState`. The production guard discovers calls through
direct, aliased, computed, or destructured method access. The production
allowance list is empty: same-page query canonicalization uses Router replace
navigation and preserves unrelated query parameters and hash state.

## Application Shell And Navigation

`Shell` owns the application's single `main` landmark and global navigation.
The global `main` retains the owner-selected framed/floating surface: one card
background, border, radius, shadow, and responsive outer gutter around page
content. Wide page content remains reachable through the `main` scroll
container instead of being clipped or widening the document. UI-N01 does not
replace or reinterpret the separately owned UI4 L-09 target. The typed
application navigation descriptor exposes five stable primary domains: Home,
Research, Portfolio, Agent, and Settings. Home temporarily owns one Signal
Center child until the global notification entry replaces it, while Research
owns a dedicated overview plus Market Review, Discover, Analysis Workbench, and
Backtest. In expanded desktop navigation and the mobile drawer, the Research
parent row navigates to `/research`; a separate trailing control expands or
collapses the four tool links without adding a duplicate Research Overview
child. Compact navigation keeps Research as a menu trigger and presents
Research Overview as the first item in the right-side hover or keyboard flyout,
followed by the four tools; Right Arrow enters the flyout and Left Arrow or
Escape restores its trigger. On `/research`, the expanded or mobile Research
parent link and the compact Research Overview item identify the current page.
On a child route, the visible active child is the sole `aria-current="page"`
link, while the Research branch retains visual active-section treatment.
Market Review remains a distinct page at `/research/market`.

Canonical Research paths are `/research`, `/research/market`,
`/research/discover`, `/research/analysis`, and `/research/backtest`. Analysis
Workbench owns the `launch`, `tasks`, and `history` segments as URL state on
that single route, and its history segment owns report comparison, full
Markdown, and Run Flow detail.
Run Flow uses the shared fullscreen `Modal` so graph inspection has a centered
workspace while retaining the URL-owned source identity, focus restoration,
and unavailable-state fallback. Its lane headers span their complete lanes,
nodes use the flat `Pressable` treatment, and the fixed-height event rail owns
its internal scroll without compressing the graph. A selected report exposes direct reanalysis
with the current Skill selection and a typed Chat handoff carrying the selected
stock/report identity as an unconsumed follow-up; accepted or duplicate
reanalysis switches to the task
segment. Home renders exactly Today's Focus, To-dos, and Signal summary before a
collapsed configurable area. Legacy Home analysis URLs with `recordId`, Run Flow,
stock, or analysis-workspace state use replace navigation into the corresponding
Workbench segment while preserving safe unrelated query and hash state. The
legacy `/screening` and `/backtest` URLs use the shared
replace-redirect contract and preserve query parameters and hash state. The
canonical Signal Center path is `/signals`; legacy `/decision-signals` and
`/alerts` paths map their query state into its feed, rules, history, or review
tab. Token
Usage remains in Settings as the `Usage & cost` section, with `/usage` using the
same compatibility contract while the destination-owned `section=usage` value
wins conflicts. Redirect destinations suppress tab-session restoration, and
all product paths plus Settings query keys come from the centralized route
contract.

The responsive contract has three states:

- Below 1024px, one shared navigation `IconButton`, the complete product name,
  and one directly reachable compact Profile trigger form the mobile header.
  Theme and language controls live inside the Profile dialog. Global navigation
  uses the Navigation `Drawer`; closing with Escape or the close control
  restores its opener. Only an unmodified primary same-window route activation
  closes the Drawer and delegates focus to the destination's ready H1;
  modifier, download, and new-context activation retain the current Drawer and
  native browser behavior. Each transient Drawer route declares the one stable
  mobile opener as its return target. `RouteFocusCoordinator` stores that target
  per history entry, so repeated Back/Forward restores the visible opener without
  Shell retaining or rewriting route metadata.
- From 1024px through 1279px, the global sidebar defaults to an 80px compact
  rail when the user has not chosen a state. A saved expanded or collapsed
  preference remains authoritative at this breakpoint, and the rail always
  provides the corresponding 44px toggle.
- At 1280px and wider, the global sidebar uses the same persisted preference,
  defaulting to its 240px expanded state. The expanded state always displays
  the complete product name.

If an open mobile Drawer crosses into the desktop breakpoint, the shell closes
it and moves focus to the current desktop route, or to the labelled desktop
sidebar when no route matches. A breakpoint change while the Drawer is closed
does not move focus. Desktop and mobile navigation instances use distinct,
stable route-focus marker prefixes so Router restoration never sees duplicate
targets. The profile surface uses dialog semantics, moves focus into its first
control, closes on Escape, and restores its trigger; crossing the desktop
breakpoint while Profile is open closes the old presentation and focuses the
visible Profile counterpart. It does not claim an incomplete menu keyboard
model. Compact navigation controls use the shared labelled Tooltip, route rows
and preference controls retain 44px targets without flex shrinking, and the
route list owns vertical scrolling so Profile and logout remain reachable at
short viewport heights. The framed `main` permits native horizontal and vertical
touch panning when page-owned content is wider than its viewport.

## Surface Hierarchy

| Level | Purpose | Visible boundary |
| --- | --- | --- |
| `canvas` | Page canvas or content already grouped by layout | Transparent, without border, radius, or shadow |
| `section` | A content grouping that needs slight tonal separation | Semantic surface color, without border or shadow |
| `interactive` | A selectable or independently interactive object | One necessary border; hover is opt-in; no default shadow |
| `overlay` | Content above the document flow | Semantic overlay surface, one border, and the shared elevated shadow (`shadow-elevation-overlay`) |

Pages must not add background, border, radius, ring, or shadow utilities to
`Surface`, `Section`, `StatePanel`, `Alert`, `EmptyState`, or
`DashboardStateBlock`. This includes arbitrary-property utilities and inline
`background`, `border`, `borderRadius`, or `boxShadow` styles. Layout-only
classes such as grid placement and maximum width remain valid. A normal page
should expose no more than two visible surface boundaries; headings, rows,
whitespace, and dividers group content inside a section.

There is no `glass` level or glass compatibility variant. The old
`glass-card` selector is an opaque card implementation, not a blur effect, and
must migrate to the existing hierarchy. A flat page or message workspace stays
`canvas`; a non-interactive content grouping uses `section`; and a structural
panel that owns actions or selection normally uses `interactive`. Layout-only
overflow remains caller-owned because clipping is not an invariant of any
level and can hide focus indicators or portalled content when applied
indiscriminately.

Nested fills and dividers use theme-aware foundation tokens instead of raw
white alpha:

| Legacy presentation | Semantic replacement |
| --- | --- |
| `glass-card` / `dashboard-card` | Choose `Surface level="canvas"`, `Surface level="section"`, or `Surface level="interactive"` from the content semantics; never add a fifth level. |
| `bg-white/N` | `bg-subtle-soft`, `bg-subtle`, or a state-specific semantic overlay token. |
| `border-white/N` / `ring-white/N` | `border-subtle` / `ring-subtle`. |
| `bg-surface` | Choose an existing Surface level or an existing token such as `bg-surface-1`, `bg-surface-2`, `bg-surface-3`, or `bg-subtle`; do not define the invalid alias. |

`UI-DEF-02` intentionally adds no new visual prop: `Surface` and these existing
tokens express the audited uses. The production allowance list is empty and
the guard rejects every `glass-card` / `dashboard-card`, raw white-alpha fill,
border/ring, and invalid `bg-surface` alias. The compatibility `glass-card`
selector has been deleted after its final consumers migrated.

`Card` remains a compatibility adapter while domain pages migrate. Its
`default` variant maps to the borderless `section` level; `bordered` and
`gradient` map to `interactive`. New production code should choose `Surface`
or `Section` directly instead of adding another `Card` variant.

## Surface Roles And Density Contract

This section is the **normative acceptance contract** for choosing and filling
Page, Drawer, Modal, full-page Wizard, and in-page rail surfaces. It codifies
the product rules from issues #877 (surface density) and #878 (action control
matrix). Visual tokens, glow/glass bans, and radius rules remain in
[`apps/dsa-web/DESIGN_GUIDE.md`](../apps/dsa-web/DESIGN_GUIDE.md). Overlay
focus, Escape, scroll lock, and z-index remain owned by the shared Overlay
primitives (`Modal`, `Drawer`, `ConfirmDialog`, `Sheet`, `Popover`)—this
section tightens **content policy**, not a second overlay stack.

**Enforcement model**

| Tag | Meaning |
| --- | --- |
| **Immediate** | Binding for all new production surfaces and any PR that adds or substantially reworks a surface. Reviewers may block on violation. |
| **Progressive** | Existing surfaces may still violate today. Owning domain PRs migrate when they touch that surface; no silent expansion of debt. |

Reviewers use the allow/deny lists and numeric limits below as pass/fail
criteria. Prefer words such as “must / must not / at most N” over aspirational
language.

### Surface role table

| Role | Allowed | Forbidden | Required chrome | Size / scroll limit | Compliance |
| --- | --- | --- | --- | --- | --- |
| **Page** | Owns the primary task for the route; durable URL state; durable multi-field configuration that the user scans and edits in place | Hosting a multi-step connect/import flow that belongs in a Wizard; dumping every Settings category’s fields into one scroll when section routing exists | Exactly one visible `PageHeader` H1 per route; optional `Toolbar`; task states via shared patterns | Full main canvas under Shell; at most two visible surface boundaries on a normal page (see Surface Hierarchy) | **Immediate** for new routes. **Progressive**: Settings multi-section long scrolls, Portfolio stacked write entry points, Discover long expansion, report strata fully open by default |
| **Drawer** (`variant="detail"`) | Single-object detail; short read; ≤ few actions (open full page, copy, simple status change); filter/history side panels that stay contextual | Multi-step wizards; long settings forms; nested tables whose primary job is horizontal exploration; entire settings categories | Visible title; object subtitle when an id/time/stock exists; primary action when the detail has one; **Open full page** (or equivalent deep link) when the object can grow beyond detail | Content height target **≤ ~1.5 viewports**. If content predictably exceeds that, use a Page or Wizard instead. Body scrolls inside the drawer; background scroll locked by the shared primitive | **Immediate** for new drawers. **Progressive**: signal/report drawers that host edit-scale content; any drawer that grew into a workflow without a full-page escape |
| **Drawer** (`variant="navigation"`) | Global product navigation only (Shell mobile nav) | Business detail, forms, or page-local tools | Product route list and close control; focus return to opener | Shell-owned width (`max-w-xs`); one global nav control on mobile | **Immediate** keep Shell as sole navigation drawer owner |
| **Modal** | Confirmations; short forms of **≤ 5–7 fields**; test-connection / single-entity add-edit (intelligence source, provider, channel, auth/password, notification test); comparable discrete submissions | Multi-step flows; entire settings categories; regular configuration that Settings keeps in page flow | Title; action footer owned by the shared `Modal`; danger confirms use `danger` / `ConfirmDialog` with consequence copy | Size tiers only: `compact` / `default` / `wide` / `fullscreen` as defined by the primitive. Scroll **only** the modal body; header/footer fixed; background locked. Prefer `compact`/`default` for ≤7 fields; `fullscreen` is reserved for graph-scale inspection such as Run Flow, not for long forms | **Immediate** for new modals. **Progressive**: Portfolio / Settings modals that exceed field limits; nested page+modal scroll without body-only scroll |
| **Full-page Wizard** | Multi-step flows; forms with **> 7 fields**; Integrations connect flows; portfolio import; first-run / agent onboarding | Hosting the same flow inside a Drawer or a short Modal | Step progress or explicit step labels; one primary forward action per step; cancel/back that restores a clear prior state | Full route or full main canvas; not an overlay series of pages | **Immediate** for new multi-step product flows. Existing: `FirstRunWizard`, `AgentOnboardingWizard`, settings wizard locales |
| **In-page panel / rail** | Context only: session list, outline, filters, secondary metrics | Equal weight to the main canvas; a third persistent column beside global nav + main + rail | Labelled region (`ResponsiveRail` H2 or equivalent); collapsible below its breakpoint | At wide desktop the rail may stay visible; narrower breakpoints use one labelled disclosure. Third surface must be overlay or bottom sheet, not a third persistent column | **Immediate** for new workspace layouts. **Progressive**: mid-width layouts that keep expanded global labels **and** page rail **and** dense main |

**Hard stacking rule:** do not open a product Drawer and a product Modal for the
same task at once. If a drawer action needs confirmation, use `ConfirmDialog`
or replace the drawer content—do not stack a second full form modal on top of a
workflow drawer without an explicit, reviewed exception.

**Overlay stack rule:** the shared foundation Overlay system remains the only
overlay stack. Page-local portal systems, one-off z-index ladders, and duplicate
focus traps are out of contract.

### Density and hierarchy rules

| ID | Rule | Compliance |
| --- | --- | --- |
| D1 | **One H1 per route.** Hierarchy is Title → section heading → field label. Do not introduce a second page-level H1 inside drawers, modals, or nested cards. | **Immediate** for new pages (matches `PageHeader` / route-focus contract). **Progressive** for any legacy dual-heading surfaces |
| D2 | **Secondary blocks default collapsed.** Advanced / governance / rarely edited groups and full report strata below the Decision Card start collapsed on first visit of that section/view. User expand state may be remembered later; first paint must not show every block open. | **Progressive** on Settings advanced groups, Discover strategy copy blocks, report strata; **Immediate** when a PR adds a new advanced block |
| D3 | **Card-in-card limit.** Nested bordered surfaces are allowed only when the inner piece is independently interactive (selectable row, activatable card). Prefer section spacing, dividers, and heading hierarchy over nested `interactive` boxes. | **Immediate** for new composition. Aligns with Surface Hierarchy “at most two visible surface boundaries” |
| D4 | **Help text is secondary.** Helper copy must not share equal visual weight with the control row (no competing primary emphasis in the same band). | **Immediate** for new fields; **Progressive** for dense Settings rows |
| D5 | **No per-page spacing invention.** Use the shared density token scale in `apps/dsa-web/src/index.css` (`--density-*`) and structural utilities (`density-gap-*`, `density-surface-pad-*`, `density-overlay-pad*`). Named inventory: `apps/dsa-web/src/design/density.ts`. Compact regions may set `data-density="compact"`. Do not redefine `--density-*` outside `index.css`. Density-aware shared components and pages are locked by the adoption ratchet below. | **Immediate** |

### Density adoption ratchet (D5 enforcement)

D5 is executable. The token inventory, parallel-definition ban, and Surface padding map remain in `apps/dsa-web/src/components/__tests__/densityContractGuard.test.ts`. The **adoption ratchet** (`densityAdoptionRatchet.test.ts`) then prevents density-aware files from reverting to fixed Tailwind / inline spacing.

**What “density-aware” means.** A production TS/TSX file is density-aware when the TypeScript AST (not a comment/type grep) contains a structural density utility (`density-gap-*`, `density-surface-pad-*`, `density-overlay-pad*`), a `var(--density-*)` / `--density-*` reference, or a `data-density` attribute. Overlay elevation (`shadow-elevation-*`) is a separate #878 contract and does **not** mark a file density-aware. The catalog `src/design/density.ts` and the playground are out of the consumer inventory.

**Required owners.** These shared components must stay density-aware: `Surface`, `PageHeader`, `Toolbar`, `Section`, `Modal`, `Drawer`, `Sheet`, `ConfirmDialog` (`DENSITY_REQUIRED_OWNERS`). Losing their density tokens is a regression, not a baseline edit.

**Measured baseline.** `apps/dsa-web/src/design/densityAdoptionBaseline.json` is snapshotted from the current production tree. For each density-aware file:

| Field | Direction | Meaning |
| --- | --- | --- |
| `densityTokenCount` | floor | Must not fall. Raise the baseline when a file gains density tokens. |
| `fixedSpacingCount` | ceiling | Remaining `gap-*` / `p-*` / `space-*` / spacing `style` after exemptions. Must not rise. Lower the baseline when debt shrinks. |

New density-aware files must be added to the JSON. This task does **not** mass-migrate product surfaces; leftover `gap-4` in a file that already uses one density token is recorded debt, not an exemption.

**Compact / comfortable.** Comfortable is the default `:root` scale. `[data-density="compact"]` retunes `--density-space-*` so structural utilities shrink. Fixed `p-4` / `gap-4` classes do not follow that switch. DataTable’s `compact` / `default` cell padding maps are the table’s own density contract and are listed as fixed-geometry exemptions. Virtualization spacer cells (`p-0` / `padding: 0`) are collapsed geometry, not density debt, and must stay compatible with the #1377 windowing contract.

**Fixed-geometry exemptions.** `DENSITY_FIXED_GEOMETRY_EXEMPTIONS` in `src/design/density.ts` is the only production exemption list. Each entry needs `file`, exact `token`, `count`, and a reason. Use it for device chrome and component-owned geometry (safe-area footer insets, DataTable cell density maps). Do **not** park leftover `p-4` debt here. Stale or overflowed entries fail CI.

**How to read a failure**

| Code | Meaning |
| --- | --- |
| `missing-required-owner` / `lost-density-aware-file` / `density-token-regression` | A density-aware file dropped tokens. Restore the utilities; do not lower the floor. |
| `fixed-spacing-regression` | New `gap-*` / `p-*` / spacing `style` on a density-aware file. Use a density utility, or a reviewed exemption if it is genuinely fixed geometry. |
| `baseline-needs-tightening` | The tree improved. Update `densityAdoptionBaseline.json` (raise token floors / lower spacing ceilings). |
| `new-density-aware-file` | A file started using density tokens. Add it to the baseline with the measured counts. |
| `stale-exemption` / `exemption-overflow` | Fix `DENSITY_FIXED_GEOMETRY_EXEMPTIONS` (`count` is shrink-only). |

The scanner follows aliases (`const STACK = 'gap-4'`), computed templates (`` `p-${size}` ``), and inline `style` padding/gap. Comments and type-only string literals are ignored. The production inventory walk may skip TypeScript parse when a conservative candidate filter proves a file cannot contain those tokens; the AST remains the authority, and the filter may over-parse but must not under-scan.

### Working-region breakpoints

Shell navigation breakpoints in Application Shell And Navigation remain
authoritative for sidebar width and mobile nav. The table below governs the
**page working region** (main canvas + optional page rail), complementary to
Shell rules:

| Viewport width | Working-region rule | Compliance |
| --- | --- | --- |
| **≥ 1280px** | Main canvas may pair with one optional collapsible context rail. Global sidebar expanded preference is independent but must not create three dense equal columns of content. | **Immediate** for new layouts |
| **~1024px (1024–1279px)** | At most **two** full-width competing surfaces in the working region: at most one of (expanded global nav labels **or** expanded page rail) may sit beside a dense main column. If both would clip core content, collapse the page rail to disclosure (or compact the nav per Shell defaults). | **Progressive** for Home / Analysis / Chat mid-width; **Immediate** when adding a new dual-rail layout |
| **< 768px** | Single column. Secondary content uses Drawer, sheet, or labelled disclosure. One global nav control (Shell). Page tools stay in the page header tool group, not a second global menu. | **Immediate** for new mobile layouts |

**Scroll rule:** prefer one primary vertical scroll owner per view. Multiple
independent `overflow-y` regions require a product reason (for example Run Flow
event rail + graph). Mid-width clipping of core content due to three full
columns is a contract defect (issue #877 I4).

### Async long-running tasks (409 / busy / queue / terminal)

For analysis, market review, portfolio analysis, screening, scheduler run-now,
and similar accepted background work, the shared **async task UX contract**
applies on top of StatePanel / Alert / Progress primitives:

- Document: [`async-task-ux-contract.md`](./async-task-ux-contract.md) (issue #885)
- Helpers: `apps/dsa-web/src/utils/asyncTaskUx.ts` (`resolveBusyRecoveryDecision`) and `apps/dsa-web/src/utils/busyRecoveryActions.ts`
- Progress copy: `formatTaskMessage` (`apps/dsa-web/src/utils/taskMessage.ts`)
- Never present a bare task id without a TaskPanel, RunFlow, or equivalent
  recoverable navigation path
- Busy/409 must disable double-submit **and** offer dismiss, attach/view-tasks,
  or reload so the launch control cannot deadlock

Error *class* taxonomy (auth, credential, network, …) remains the error-catalog
track; this foundation only requires the presentation patterns above for
async lifecycle states.

### Task state structure (Loading / Empty / Error / Partial)

Component APIs live in State And Alert Semantics. This table adds **structure
and CTA** requirements used in PR review:

| State | Structure requirements | CTA rules | Compliance |
| --- | --- | --- | --- |
| **Loading** | Block-level skeleton or shared `Progress` / `Spinner` path; labelled busy state (`aria-busy` / `role="status"` as owned by `StatePanel`) | No competing primary CTA that implies the task is ready | **Immediate** for new task regions. **Progressive**: pages still inventing local spinners |
| **Empty** | Shared empty pattern (`StatePanel` empty or `EmptyState` adapter): short plain-language copy; optional illustration; single clear next step | **Exactly one** primary CTA (text `Button`). Secondary links optional and quieter | **Immediate** for new empty states. **Progressive**: Discover / Today / Portfolio pilots |
| **Error** | Plain-language failure; reuse `StatePanel` error or `Alert` for refresh-over-stale; no raw stack traces in product UI | **Retry** when retry is meaningful; optional link to Integrations, security, or Settings when that is the fix path (see error-class issues) | **Immediate** for new error paths. **Progressive**: divergent per-page error layouts |
| **Partial / stale** | Keep last good content readable when possible; show a banner or `partial` state with as-of / completeness context | One action to refresh or complete missing setup; do not hide partial data behind a full-page empty | **Immediate** for new partial surfaces. **Progressive**: as-of banners on hubs |

Do not render a second loading card, empty card, or alert for the same task
identity. Refresh failure over existing results uses `Alert` while results stay
visible (existing foundation rule).

### Action control matrix (#878)

This matrix is the single documented rule for text buttons vs icon tools. It
extends Button Intent and IconButton primitive contracts; it does not add new
Button variants.

| Kind | Control | Live size | Examples | Forbidden patterns |
| --- | --- | --- | --- | --- |
| **Primary task** | Labeled `Button` (`primary` or one task-region primary). Optional leading icon inside the same Button | `primary` 32px, or `comfortable` 28px when it shares a header row | Save, Run analysis, Connect, Import, Apply filters | Icon-only for irreversible money/account destruction; multiple `primary` buttons in one task region |
| **Secondary task command** | Labeled `Button` (`secondary` / `outline`) | `comfortable` 28px (or `default` 24px when declared compact) | Cancel, Edit, View details when the label is the task | Styling secondary tools as a second primary |
| **Secondary chrome tool** | `IconButton` + accessible name + tooltip | `default` (`h-8` / 32px) | Refresh, Filter, More/overflow, Close, Collapse, History, Copy, Export | Full label `Button` rows that only wrap the toolbar; icon-only without accessible name |
| **Tertiary / inline** | Ghost `IconButton` or quiet text link | `compact` 28px when declared dense; otherwise `default` 32px | Inline dismiss affordances, low-emphasis row tools | Elevating tertiary tools to primary |
| **Destructive** | Labeled `Button` with `danger` / `danger-subtle`, or `ConfirmDialog` with consequence copy | same as primary/secondary labeled sizes | Delete account, remove channel | Icon-only destructive for irreversible actions unless a reviewed product pattern already confirms with a labeled dialog |

Shell/rail/overlay icon tools use `IconButton` `navigation` (44px visible) only.
Dense field-row help already uses `IconButton` `compact` (28px).

**No double frame (R2):** do not wrap each `IconButton` in its own bordered or
padded card. Allowed: a toolbar row with gap only; one shared segmented track
for a tool group; selected state on the group, not a per-icon default box.

**Header band layout (R4):**

```text
[ Title + meta .................... [icon tools] [optional primary Button] ]
[ optional secondary toolbar ]
[ content ]
```

Icon tools share one tool group on a single baseline. The primary CTA is
optically separate from the icon cluster (not mixed into the same chip row as
Refresh).

**Elevation usage (R3 / R5):** use Surface Hierarchy levels only. Nested content
inside a section must not add another card border unless independently
interactive. Overlays (`Modal` / `Drawer` / `Sheet` / `ConfirmDialog`) must read
above page section via the shared overlay surface, backdrop, and
`shadow-elevation-overlay` (not raw Tailwind `shadow-2xl` / `shadow-lg` ladders).
Menus and tooltips use `shadow-elevation-popper` when elevated. Only semantic
shadow tokens from `index.css`—no glow, glass, or decorative colored shadows
(DESIGN_GUIDE).

| Action-matrix rule | Compliance |
| --- | --- |
| Text vs IconButton classification | **Immediate** for new toolbars, drawer headers, and table row chrome. **Progressive**: existing pages still using labeled Refresh/Filter |
| No double frame around IconButton | **Immediate** for new chrome. **Progressive**: audited heavy wrappers |
| Header band separation of tools vs primary CTA | **Immediate** for new headers. **Progressive**: workbench / signals / settings headers |
| Overlay elevation via shared tokens | **Immediate** keep shared primitives; **Progressive** any custom elevated boxes |

### Mapping to existing code

| Existing surface | Contract stance |
| --- | --- |
| Shared `Drawer` / `Modal` / `ConfirmDialog` + `overlayZ` | **Keep** the system; tighten content policy only |
| Settings `section` / `view` routes | **Lean into** single active section content; do not paint every group when section routing exists |
| Portfolio multi-modal writes | Short modals only; long import → full-page wizard track |
| Signal / report drawers | Detail + link to full report / workbench; not full edit workflows |
| Foundation `StatePanel` / `EmptyState` / `Alert` | Extend adoption; stop page-local empty/error reinvention |
| `PageHeader` one H1 + route focus | Already foundational; surface contract restates as density D1 |
| DESIGN_GUIDE tokens / no glow / no glass | Unchanged; hierarchy comes from layout and Surface levels, not new colors |
| Shell breakpoints (1024 / 1280) | Unchanged; working-region table above is complementary content policy |

### Review checklist (executable)

A PR that introduces or reworks a surface fails this contract when any apply:

1. New multi-step or >7-field flow ships in a Drawer or short Modal without exception approval.
2. New Drawer content is expected to exceed ~1.5 viewports with no full-page escape.
3. New Modal scrolls the page behind or uses header/footer scroll instead of body-only scroll.
4. New route renders more than one H1, or adds nested bordered cards without independent interaction.
5. New empty/error/loading region omits the required structure or CTA rules above.
6. New toolbar uses labeled Buttons for recurrent chrome tools that the matrix assigns to `IconButton`, or wraps each icon in its own border frame.
7. New mid-width layout keeps three dense full columns that clip core content.
8. Any new glow, glass, or non-semantic shadow treatment (also a DESIGN_GUIDE failure).
9. A density-aware shared component or page replaces `density-*` utilities with fixed `p-*` / `gap-*` / spacing `style` without a `DENSITY_FIXED_GEOMETRY_EXEMPTIONS` entry.
10. A new production file (or extra occurrence in an existing file) introduces a native `<button>` or `role="button"` host outside the shared-control owners / a11y exemption list.

## State And Alert Semantics

`StatePanel.state` is typed as `loading`, `blocked`, `partial`, `empty`,
`error`, `retrying`, or `success`. Loading and retrying states expose
`role="status"`, polite announcements, and `aria-busy`; errors expose an
assertive alert. Persistent empty and blocked guidance is not a live region.
Callers choose the correct heading level and provide one relevant next action;
they cannot replace the component-owned role, live-region, or busy semantics.

`StatePanel` is borderless by default. A page-level task may opt into the
borderless `section` surface for stable tonal separation, but it must not show
a second loading card, empty card, or alert for the same task. Existing results
may remain visible during refresh; a refresh failure uses `Alert` while the
last successful result stays readable.

`Alert` uses `status` for non-urgent information and `alert` for danger or an
explicit urgent announcement. A dismissible Alert requires a dismiss label at
the type boundary and uses the shared `IconButton`; command actions remain
shared Buttons. Callers select semantic `compact` or `default` density instead
of overriding padding, radius, or shadow classes, and cannot replace the
component-owned role or live-region urgency.

## Button Intent

`Button.variant` is required. The primitive accepts only these business-neutral
intents:

- `primary`: the single highest-emphasis action in a task region.
- `secondary`: ordinary commands and lower-emphasis submissions.
- `outline`: an alternate selection or command with a visible boundary.
- `ghost`: quiet utility commands.
- `danger`: destructive confirmation.
- `danger-subtle`: lower-emphasis destructive commands.

Settings, Home, Chat, report, or other module names must not become primitive
variants. Icon-only actions use `IconButton`, not `Button` with an icon size.

## Visible Size And Hit Target

Named sizes are **not** shared pixel heights across primitives. Button
`compact` (20px) is not IconButton `compact` (28px). Chrome Refresh uses
IconButton `default` (`h-8` / 32px), not Button `primary` (also 32px).

**Button** visible map (`Button.tsx`; implicit default `comfortable`):

| Size | Height | Typical use |
| --- | ---: | --- |
| `compact` | 20px | Declared dense tables only |
| `default` | 24px | Ordinary compact labeled commands |
| `comfortable` | 28px | Forms, regular submissions, and the implicit default |
| `primary` | 32px | The unique task CTA |

**IconButton** visible map (`IconButton.tsx`; implicit default `default`):

| Size | Height | Typical use |
| --- | ---: | --- |
| `compact` | 28px | Declared dense tables and field-row help |
| `default` | 32px | Toolbar / row icon tools (Refresh, Export, Copy, Filter) |
| `comfortable` | 36px | Larger in-content icon commands when declared |
| `navigation` | 44px | Shell, rail, and overlay navigation controls |

`Button` defaults to `comfortable`; `Input` defaults to `comfortable`; login inputs
resolve to `primary`. `DatePicker` preserves its 44px default touch control and
offers an explicit 32px `compact` control for dense aligned toolbars such as
Backtest. The `navigation` tier is reserved for shell, rail, and overlay
navigation controls whose visible target must remain 44px; it is not a general
replacement for the smaller command tiers.

When any available pointer is coarse, including on hybrid touchscreen devices,
`Button` and `IconButton` use a transparent pseudo-element to provide at least a
44x44px effective target. `Input` uses a 44px focus frame whose empty area
forwards focus to the native input. The visible background is not enlarged to
44px.

## Caller Constraints

Button, IconButton, and SelectionChip callers must not use `className` to replace shared
height, width, padding, radius, flex-basis, or flex-growth geometry. Input and
Textarea callers must not replace shared height, padding, radius, or focus
geometry; Input layout width belongs on `fieldClassName`. Typography,
whitespace behavior, and contextual color adjustments remain valid when they
do not replace the primitive contract.

The AST-backed production design guard checks:

- Button style-map PR #35 rounding and the 20/24/28/32px tiers.
- IconButton style-map must stay `h-7`/`h-8`/`h-9`/`h-11` (28/32/36/44); unresolved `className` and `{...props}` fail closed (`IconButton:dynamic:…`); `size="primary"` is Button-only.
- Legacy `xsm`/`sm`/`md`/`lg`/`xl` Button sizes in both the shared style map
  and aliased or namespaced callers; no legacy-size allowlist remains.
- Icon- or symbol-only shared `Button` callers that must use `IconButton`.
- Static and unresolved Button visual overrides, including `size-*` and
  arbitrary geometry properties, against exact call-site exceptions.
- Static Input, IconButton, and Textarea height, padding, radius, or icon-box
  overrides; Input wrapper width remains a Pattern/layout responsibility.
- Static SelectionChip height, width, padding, radius, flex-basis, or
  flex-growth overrides, including aliased and namespaced common imports.
- Primary CTA gradient/shimmer rules already enforced by the repository.
- The complete `Surface` level style map, including borderless L0/L1,
  border-only L2, and shared-shadow Overlay invariants.
- Direct, aliased, and namespaced state-surface callers and compatibility
  adapter internals, rejecting caller-owned backgrounds, borders, radii, rings,
  shadows, named card classes, inline visual styles, arbitrary-property
  utilities, and dynamic visual overrides. Required adapter forwarding uses
  exact call-site exceptions with a deletion work item.
- Shared Filter/Query implementation names outside their declared
  `components/common` owners.
- Direct `pushState` or `replaceState` calls, including aliased, computed, and
  destructured access; the production allowance list is empty.
- Shared `DataTable` implementations outside its declared common owner, plus
  any new JSX / `createElement` raw table or page-local `role="table|grid"`
  substitute. The production raw-table allowance inventory is empty.
- Every `glass-card` / `dashboard-card`, raw white-alpha
  background/border/ring utility, and undefined `bg-surface` alias; the
  production allowance list is empty.

The Button visual-override allowlist is empty. Retained state-surface
exceptions are limited to shared compatibility adapters plus the audited
report/task consumers; each records exact tokens, owner `UIUX-HARNESS`, and a
concrete `removeWhen` condition. No page-track `removeBy` entry remains.

## Component Playground

Development builds include an authenticated, intentionally hidden component
workbench at `/playground`. It is not part of `SidebarNav`. The route uses the
same `AuthProvider` boundary as the rest of the Web application, so a signed-out
development request preserves the complete playground deep link through
`/login?redirect=`. Production composition omits the playground routes,
catalog, and scenario graph; unknown `/playground` URLs follow the normal
authenticated 404 path. The Axios mock adapter that powers deterministic
fixture profiles is a development-only dependency and is not resolved by the
production runtime bundle.

The catalog covers every exported visual component under `src/components`,
including shared primitives, layout patterns, and business components. Pages,
hooks, utilities, non-visual providers, and duplicate export aliases are out of
scope. When a visual component is added or removed, update the catalog and its
real-component scenario renderer together; the catalog completeness test must
remain exact. Stories may add local state wrappers but must not replace the
component with a visual approximation or introduce a generic props editor.

Each preview renders through the same-origin
`/playground/render/:componentId/:scenarioId` route in a dedicated iframe. This
keeps portals, focus traps, viewport media queries, drawers, modals, and
full-screen layouts inside the preview boundary. The selected `component`,
`scenario`, fixture `profile`, and `viewport` live in the parent URL query so a
refresh or shared link restores the same deterministic view. Invalid values are
replaced with the catalog default.

The renderer waits for the real application authentication check to finish.
In development it then installs its Axios mock before mounting the selected
story. That mock is limited to the iframe's JavaScript realm, uses synthetic
fixtures only, and is restored on unmount. It provides deterministic `ready`,
`empty`, `error`, and `slow` profiles; switching a profile or scenario rebuilds
the iframe and its in-memory state. Registered writes update in-memory
fixtures, while every unregistered request is rejected with
`501 playground_mock_not_registered`. Passthrough is prohibited. Request-log
messages contain only method, path without query or hash, status, duration, and
a local request id; payloads, headers, credentials, and response bodies must
never cross the iframe boundary. Production builds omit the playground catalog,
scenario graph, and mock adapter package.

## Migration And Deletion

- `UI-F01A` establishes the primitives, removes business-named Button variants,
  removes Button icon sizing, and enables the production guards.
- `UI-F01B` migrated `xsm`/`sm`/`md`/`lg` call sites to canonical semantic size
  names and deleted those compatibility aliases from `ButtonSize` and
  `BUTTON_SIZE_STYLES`; `UI-QA01` removed the final `xl` caller and alias. The
  production guard prevents every legacy size from being reintroduced.
- `UI-F02` establishes `Surface`, `Section`, `StatePanel`, and `Alert`; maps
  `Card`, `SectionCard`, `EmptyState`, `InlineAlert`, `Loading`,
  `ApiErrorAlert`, `DashboardStateBlock`, `StatCard`, and
  `SettingsSectionCard` through compatibility adapters; and uses Token Usage
  as the first complete state consumer. Each domain work item replaces its
  compatibility calls with the authoritative API when it owns that page.
- `UI-F04A` established `FilterBar`, `AdvancedFilterSheet`,
  `AppliedFilterChips`, `FilterChip`, and `useFilterQueryState`. Page tracks
  adopted the shared Patterns; `UI-QA01` moved the remaining Decision Signals,
  Backtest, and Stock Screening query writes to Router replace navigation and
  deleted the direct-history allowance list.
- `UI-F04B` established the typed `DataTable`, state, sorting, row-event, and
  contained-scroll contracts. Page tracks adopted the shared Pattern;
  `UI-QA01` added controlled detail rows for Stock Screening. The final debt
  cleanup added embedded framing, fixed percentage columns, controlled selected
  rows, contextual separators, and stable row test IDs, migrated the five
  retained tables, and deleted the raw-table allowance inventory.
- `UI-DEF-01` establishes `SelectionChip` from the explicit TRACK-UI2 deferred
  input. `UI-D01` subsequently migrated Decision Signals to the shared control
  and deleted its exact Button geometry allowance.
- `UI-DEF-02` established the four Surface levels and semantic subtle tokens as
  the complete replacement for glass/raw-white debt. `UI-QA01` completed the
  remaining business-page migration and changed its guard to a zero-debt rule.
- `UI-F05` establishes the page skeleton, same-page Tabs, sibling-route
  navigation, summary, responsive rail, and route-focus authority. It does not
  migrate business pages or the Shell. Page tracks adopt the public Patterns
  and `RouteFocusTarget` independently; `UI-N01` owns Shell/navigation layout.
- Existing page-local textarea implementations migrate through their owning
  page work items (`UI-C01` and `UI-S02`, both `TRACK-UI3`) before duplicate
  raw controls are deleted.
- `UI-QA01` removes expired allowlist entries and compatibility adapters only
  after their final production consumers migrate; retained compatibility APIs
  carry a concrete `UIUX-HARNESS` removal prerequisite.

Tests should assert role, accessible name, native state, semantic variant/size,
and behavior. Tailwind classes such as `h-11` or `rounded-full` are not product
contracts and must not be asserted by component or page tests.

## Responsive Breakpoints

Supported audit widths and page-level gap tracking live in [web-responsive-breakpoints.md](web-responsive-breakpoints.md). PWA install and shell-only caching live in [web-pwa.md](web-pwa.md).
