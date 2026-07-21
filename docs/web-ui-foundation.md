# Web UI Foundation Contract

This document defines the shared interaction-control, surface, section, and
state contract for `apps/dsa-web`. Page and domain components should consume
these primitives and patterns instead of rebuilding size, focus, loading,
field-description, hit-target, boundary, empty-state, or alert behavior.

## Layer Boundary

- Foundation owns semantic tokens and shared control geometry.
- Primitives own native semantics, refs, disabled/loading states, focus, and
  coarse-pointer targets.
- Patterns may compose primitives but must not redefine their core geometry.
- Pages and domain components own business state and localized content only.

## Shared Primitives

| Primitive | Contract |
| --- | --- |
| `Button` | Requires an explicit intent, forwards the native button ref, and exposes semantic variant and size state. |
| `SelectionChip` | Provides a compact text-led selection command that grows for multi-line content without caller-owned geometry. |
| `IconButton` | Requires an accessible name, provides an optional tooltip, separates its visible icon surface from its coarse-pointer hit target, and owns the 44px `navigation` size used by shell and rail controls. |
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
| `AppliedFilterChips` | Presents applied filters as individually removable tokens with one clear-all command. |
| `useFilterQueryState` | Keeps applied filters in Router search params, preserves unrelated params, keeps drafts local, and restores both after Back/Forward navigation. |
| `DataTable` | Renders typed columns and native table semantics, controlled sorting, one task state, contained narrow-screen scrolling, and isolated row activation. |
| `AppPage` / `WorkspacePage` | Provide the full-width page canvas and optional main/rail workspace grid beneath the Shell's single `main`. |
| `PageHeader` / `Toolbar` | Provide one programmatically focusable H1 and one semantic command group without adding a decorative page surface. |
| `ResponsiveRail` | Keeps contextual content visible at wide desktop and exposes one labelled disclosure at narrower breakpoints. |
| `Tabs` / `TabPanel` | Implement same-page panel selection with associated tab/panel IDs and horizontal roving focus. |
| `SummaryStrip` | Presents continuous summary metrics as one labelled definition list rather than a card grid. |
| `WorkspaceNavigation` | Uses Router Links for sibling routes and a native compact select; route navigation never masquerades as Tabs. |
| `RouteFocusCoordinator` / `useRouteFocusTarget` | Coordinate ready H1 focus after PUSH/REPLACE and stable trigger restoration after POP without exposing history metadata to pages. |

Every caller-visible string, including `aria-label` and tooltip content, must
come from the existing i18n resources.

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

The Pattern renders one framed table surface. Empty rows use the required
`emptyState`; loading, error, and retrying use one explicit `status` and hide
the table so duplicate state blocks cannot appear. State content reuses
`StatePanel` roles, live regions, busy state, and actions. Callers cannot pass
`className`, `style`, or Surface attributes through `DataTable`; contextual
layout belongs on a wrapper and cell typography belongs inside the cell
renderer.

On narrow screens the native table remains a table inside a named, keyboard-
focusable horizontal scroll region. `content`, `wide`, and `extra-wide` are
stable minimum-width contracts; scrolling is contained within the Pattern and
must never increase document width. This preserves dense financial columns and
their headers instead of duplicating rows into a second card DOM.

An activatable row requires both `onRowActivate` and a localized
`getRowAriaLabel`. Click, Enter, and Space invoke the same command. Events from
nested `button`, link, input, label, select, textarea, summary,
`contenteditable`, focusable element, or interactive ARIA role are ignored, so
row navigation cannot fire together with an edit, menu, link, or form control.
Disabled rows leave the activation tab sequence and expose `aria-disabled`.

Optional controlled detail rows require both `isRowDetailVisible` and
`renderRowDetail`. `DataTable` owns the sibling row, full-column span, density,
semantic detail fill, stable optional ID, and accessible optional row label;
the caller owns business content and the command that controls visibility.
That command must expose `aria-expanded` and `aria-controls` when it targets a
stable detail-row ID.

Five embedded raw tables remain tracked by stable file/token/count inventory.
They are owned by `UIUX-HARNESS` and may be removed only when their concrete
shared-Pattern prerequisite is available:

| Current table source | Removal prerequisite |
| --- | --- |
| Stock history trend | Selected-row presentation and percentage/fixed-layout columns without caller geometry overrides. |
| Market Review report | Embedded unframed report-table mode without a nested Surface inside the report Card. |
| Run Flow node details | Embedded unframed compact mode for an overlay detail panel. |
| Settings AI overview matrix | Settings-border ownership and stable per-task row test IDs through `DataTable`. |
| Token Usage recent calls | Embedded `DataTable` inside the existing `Section` without a nested card, preserving the no-calls state. |

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
Left/Right/Home/End movement, and native Enter/Space activation. Sibling page
routes use `WorkspaceNavigation` instead: desktop renders real Router Links
with one `aria-current="page"`, while compact layouts render a labelled native
select that hands the selected item back to the caller. Route item IDs, not
translated labels or array indexes, provide stable focus markers.

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
application navigation descriptor preserves the nine approved flat routes;
Research, More, or another top-level destination requires a separate
information-architecture decision.

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
| `overlay` | Content above the document flow | Semantic overlay surface, one border, and the shared elevated shadow |

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

The canonical visible tiers are:

| Size | Height | Typical use |
| --- | ---: | --- |
| `compact` | 28px | Dense toolbars and low-frequency filters |
| `default` | 32px | Ordinary commands |
| `comfortable` | 36px | Forms and regular submissions |
| `primary` | 40px | The unique task CTA |
| `navigation` | 44px | Shell, rail, and overlay navigation controls |

`Button` defaults to `default`; `Input` defaults to `comfortable`; login inputs
resolve to `primary`. `IconButton` supports `compact`, `default`, and
`comfortable` visible squares plus the 44px `navigation` square. The
`navigation` tier is reserved for shell, rail, and overlay navigation controls
whose visible target must remain 44px; it is not a general replacement for the
smaller command tiers.

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

- Button style-map soft rounding and the 28/32/36/40px tiers.
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
  substitute. Five retained raw tables use stable file/token/count inventory
  and the concrete shared-Pattern prerequisites listed above.
- Every `glass-card` / `dashboard-card`, raw white-alpha
  background/border/ring utility, and undefined `bg-surface` alias; the
  production allowance list is empty.

The Button visual-override allowlist is empty. Retained state-surface
exceptions are limited to shared compatibility adapters plus the audited
report/task consumers; each records exact tokens, owner `UIUX-HARNESS`, and a
concrete `removeWhen` condition. No page-track `removeBy` entry remains.

## Component Playground

The production build includes an authenticated, intentionally hidden component
workbench at `/playground`. It is not part of `SidebarNav`. The route uses the
same `AuthProvider` boundary as the rest of the Web application, so a signed-out
request preserves the complete playground deep link through `/login?redirect=`.

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

The renderer waits for the real application authentication check to finish,
then installs its Axios mock before mounting the selected story. The mock is
limited to that iframe's JavaScript realm, uses synthetic fixtures only, and is
restored on unmount. It provides deterministic `ready`, `empty`, `error`, and
`slow` profiles; switching a profile or scenario rebuilds the iframe and its
in-memory state. Registered writes update in-memory fixtures, while every
unregistered request is rejected with `501 playground_mock_not_registered`.
Passthrough is prohibited. Request-log messages contain only method, path
without query or hash, status, duration, and a local request id; payloads,
headers, credentials, and response bodies must never cross the iframe boundary.

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
  `UI-QA01` added controlled detail rows for Stock Screening and retained only
  the five embedded-table prerequisites listed above.
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
