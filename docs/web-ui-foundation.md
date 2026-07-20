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
| `IconButton` | Requires an accessible name, provides an optional tooltip, and separates its visible icon surface from its coarse-pointer hit target. |
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

Existing raw tables remain exact, expiring page-track migrations:

| Removal item | Execution owner | Current table sources |
| --- | --- | --- |
| `UI-R01` | `TRACK-UI1` | Market Review report table |
| `UI-R02` | `TRACK-UI1` | Stock history trend table |
| `UI-R03` | `TRACK-UI1` | Run Flow node-detail table |
| `UI-U01` | `TRACK-UI1` | Token Usage recent calls |
| `UI-A01` | `TRACK-UI2` | Alert rules, trigger history, and alert-event tables |
| `UI-BT01` | `TRACK-UI2` | Backtest results |
| `UI-P01` | `TRACK-UI2` | Portfolio positions |
| `UI-SCR01` | `TRACK-UI2` | Screening results and stock history data |
| `UI-S02` | `TRACK-UI3` | Settings AI overview matrix |

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

`Button` defaults to `default`; `Input` defaults to `comfortable`; login inputs
resolve to `primary`. `IconButton` supports `compact`, `default`, and
`comfortable` visible squares.

When any available pointer is coarse, including on hybrid touchscreen devices,
`Button` and `IconButton` use a transparent pseudo-element to provide at least a
44x44px effective target. `Input` uses a 44px focus frame whose empty area
forwards focus to the native input. The visible background is not enlarged to
44px.

## Caller Constraints

Button and IconButton callers must not use `className` to replace shared
height, width, padding, radius, flex-basis, or flex-growth geometry. Input and
Textarea callers must not replace shared height, padding, radius, or focus
geometry; Input layout width belongs on `fieldClassName`. Typography,
whitespace behavior, and contextual color adjustments remain valid when they
do not replace the primitive contract.

The AST-backed production design guard checks:

- Button style-map soft rounding and the 28/32/36/40px tiers.
- Legacy `xsm`/`sm`/`md`/`lg` Button sizes in both the shared style map and
  aliased or namespaced callers.
- `size="xl"` usage against an exact allowlist.
- Icon- or symbol-only shared `Button` callers that must use `IconButton`.
- Static and unresolved Button visual overrides, including `size-*` and
  arbitrary geometry properties, against exact call-site exceptions.
- Static Input, IconButton, and Textarea height, padding, radius, or icon-box
  overrides; Input wrapper width remains a Pattern/layout responsibility.
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
- New direct `pushState` or `replaceState` calls. Three existing filter-page
  calls remain exact line-level migration entries assigned to `TRACK-UI2`.
- Shared `DataTable` implementations outside its declared common owner, plus
  any new JSX / `createElement` raw table or page-local `role="table|grid"`
  substitute. Twelve existing raw tables remain exact line-level entries
  assigned to their page tracks and removal items.

Temporary override exceptions record both exact tokens and their removal work
item:

| Removal item | Execution owner | Temporary reason |
| --- | --- | --- |
| `UI-D01` | `TRACK-UI2` | Replace the multiline Decision Signals candidate Button with the shared filter/pressable pattern. |
| `UI-P01` | `TRACK-UI2` | Move Portfolio flex/full-width layout ownership into the account and form patterns. |
| `UI-R01` | `TRACK-UI1` | Remove Home and Market Review compatibility card classes during the report hierarchy migration. |
| `UI-R02` | `TRACK-UI1` | Remove report/history compatibility card classes during route-level reading and trend migration. |
| `UI-R03` | `TRACK-UI1` | Move TaskPanel layout and visual ownership into the route-level Run Flow workspace. |
| `UI-SCR01` | `TRACK-UI2` | Replace the Stock Screening loading-width shim with stable task-action layout. |

The sole temporary `size="xl"` caller is the NotFound recovery CTA; `UI-QA01`
must re-evaluate and remove that compatibility entry when legacy cleanup lands.

## Migration And Deletion

- `UI-F01A` establishes the primitives, removes business-named Button variants,
  removes Button icon sizing, and enables the production guards.
- `UI-F01B` migrated `xsm`/`sm`/`md`/`lg` call sites to canonical semantic size
  names and deleted those compatibility aliases from `ButtonSize` and
  `BUTTON_SIZE_STYLES`; the production guard prevents their reintroduction.
- `UI-F02` establishes `Surface`, `Section`, `StatePanel`, and `Alert`; maps
  `Card`, `SectionCard`, `EmptyState`, `InlineAlert`, `Loading`,
  `ApiErrorAlert`, `DashboardStateBlock`, `StatCard`, and
  `SettingsSectionCard` through compatibility adapters; and uses Token Usage
  as the first complete state consumer. Each domain work item replaces its
  compatibility calls with the authoritative API when it owns that page.
- `UI-F04A` establishes `FilterBar`, `AdvancedFilterSheet`,
  `AppliedFilterChips`, `FilterChip`, and `useFilterQueryState`. It does not
  migrate a business page: `TRACK-UI2` owns Decision Signals (`UI-D01`),
  Backtest (`UI-BT01`), and Stock Screening (`UI-SCR01`) and must delete each
  exact direct-history allowance in the same change that adopts the Router
  query contract.
- `UI-F04B` establishes the typed `DataTable`, state, sorting, row-event, and
  contained-scroll contracts. It does not migrate a business page. Each page
  track deletes its exact raw-table allowance in the same change that adopts
  the shared Pattern; the final migration deletes the legacy allowance list.
- Existing page-local textarea implementations migrate through their owning
  page work items (`UI-C01` and `UI-S02`, both `TRACK-UI3`) before duplicate
  raw controls are deleted.
- `UI-QA01` removes expired allowlist entries and deletes a compatibility
  adapter only after its final production consumer has migrated; it also
  verifies that no duplicate primitive, state, alert, or surface implementation
  remains.

Tests should assert role, accessible name, native state, semantic variant/size,
and behavior. Tailwind classes such as `h-11` or `rounded-full` are not product
contracts and must not be asserted by component or page tests.
