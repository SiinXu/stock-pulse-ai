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
| `Alert` | Owns info/success/warning/danger presentation, live-region urgency, shared dismiss controls, and action placement. |

Shared patterns compose these primitives:

| Pattern | Contract |
| --- | --- |
| `Section` | Renders a visible heading and associates it with a semantic section; actions and content remain within one surface boundary. |
| `StatePanel` | Represents one typed task state and owns its live-region, busy, icon, density, description, and action semantics. |

Every caller-visible string, including `aria-label` and tooltip content, must
come from the existing i18n resources.

## Surface Hierarchy

| Level | Purpose | Visible boundary |
| --- | --- | --- |
| `canvas` | Page canvas or content already grouped by layout | Transparent, without border, radius, or shadow |
| `section` | A content grouping that needs slight tonal separation | Semantic surface color, without border or shadow |
| `interactive` | A selectable or independently interactive object | One necessary border; hover is opt-in; no default shadow |
| `overlay` | Content above the document flow | Semantic overlay surface, one border, and the shared elevated shadow |

Pages must not add background, border, radius, ring, or shadow utilities to
`Surface`, `Section`, `StatePanel`, `Alert`, `EmptyState`, or
`DashboardStateBlock`. Layout-only classes such as grid placement and maximum
width remain valid. A normal page should expose no more than two visible
surface boundaries; headings, rows, whitespace, and dividers group content
inside a section.

`Card` remains a compatibility adapter while domain pages migrate. Its
`default` variant maps to the borderless `section` level; `bordered` and
`gradient` map to `interactive`. New production code should choose `Surface`
or `Section` directly instead of adding another `Card` variant.

## State And Alert Semantics

`StatePanel.state` is typed as `loading`, `blocked`, `partial`, `empty`,
`error`, `retrying`, or `success`. Loading and retrying states expose
`role="status"`, polite announcements, and `aria-busy`; errors expose an
assertive alert. Persistent empty and blocked guidance is not a live region.
Callers choose the correct heading level and provide one relevant next action.

`StatePanel` is borderless by default. A page-level task may opt into the
borderless `section` surface for stable tonal separation, but it must not show
a second loading card, empty card, or alert for the same task. Existing results
may remain visible during refresh; a refresh failure uses `Alert` while the
last successful result stays readable.

`Alert` uses `status` for non-urgent information and `alert` for danger or an
explicit urgent announcement. A dismissible Alert requires a dismiss label at
the type boundary and uses the shared `IconButton`; command actions remain
shared Buttons.

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
- Direct, aliased, and namespaced state-surface callers, rejecting caller-owned
  backgrounds, borders, radii, rings, shadows, named card classes, and dynamic
  visual overrides.

Temporary override exceptions record both exact tokens and their removal work
item:

| Owner | Temporary reason |
| --- | --- |
| `UI-D01` | Replace the multiline Decision Signals candidate Button with the shared filter/pressable pattern. |
| `UI-P01` | Move Portfolio flex/full-width layout ownership into the account and form patterns. |
| `UI-SCR01` | Replace the Stock Screening loading-width shim with stable task-action layout. |

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
- Existing page-local textarea implementations migrate through their owning
  page work items (`UI-C01` and `UI-S02`) before duplicate raw controls are
  deleted.
- `UI-QA01` removes expired allowlist entries and deletes a compatibility
  adapter only after its final production consumer has migrated; it also
  verifies that no duplicate primitive, state, alert, or surface implementation
  remains.

Tests should assert role, accessible name, native state, semantic variant/size,
and behavior. Tailwind classes such as `h-11` or `rounded-full` are not product
contracts and must not be asserted by component or page tests.
