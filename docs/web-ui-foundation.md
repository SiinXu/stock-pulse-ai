# Web UI Foundation Contract

This document defines the shared interaction-control contract for
`apps/dsa-web`. Page and domain components should consume these primitives
instead of rebuilding size, focus, loading, field-description, or hit-target
behavior.

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

Every caller-visible string, including `aria-label` and tooltip content, must
come from the existing i18n resources.

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

Callers must not use `className` to replace shared height, width, padding,
radius, flex-basis, or flex-growth geometry. Typography, whitespace behavior,
and contextual color adjustments remain valid when they do not replace the
primitive contract.

The AST-backed production design guard checks:

- Button style-map soft rounding and the 28/32/36/40px tiers.
- `size="xl"` usage against an exact allowlist.
- Icon- or symbol-only shared `Button` callers that must use `IconButton`.
- Static and unresolved caller-side visual overrides, including `size-*` and
  arbitrary geometry properties, against exact call-site exceptions.
- Primary CTA gradient/shimmer rules already enforced by the repository.

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
- `UI-F01B` migrates `xsm`/`sm`/`md`/`lg` call sites to canonical semantic size
  names, then deletes those compatibility aliases from `ButtonSize` and
  `BUTTON_SIZE_STYLES`.
- Existing page-local textarea implementations migrate through their owning
  page work items (`UI-C01` and `UI-S02`) before duplicate raw controls are
  deleted.
- `UI-QA01` removes expired allowlist entries and verifies that no duplicate
  primitive implementation remains.

Tests should assert role, accessible name, native state, semantic variant/size,
and behavior. Tailwind classes such as `h-11` or `rounded-full` are not product
contracts and must not be asserted by component or page tests.
