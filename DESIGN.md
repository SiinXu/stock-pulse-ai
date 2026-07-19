---
version: 0.1.0
name: StockPulse
description: Agent-facing visual contract for the StockPulse web product.
status: target-with-known-implementation-gaps
source:
  figma_file: IVD11Gvk1jT4LkAjwg12yF
  figma_name: Coinstax Web3 Crypto Dashboard UI Kit
  role: visual-reference-only
colors:
  canvas:
    light: "#F7F8F7"
    dark: "#151514"
  surface:
    light: "#FFFFFF"
  text:
    light: "#151514"
    dark: "#FFFFFF"
  text_muted:
    light: "#878980"
    dark: "#9B9D95"
  border:
    light: "#EAEBE8"
    dark: "#343531"
  border_subtle:
    light: "#F0F0EF"
    dark: "#1F201D"
  brand:
    light: "#41B83D"
    dark: "#96DB94"
  success:
    light_text: "#41B83D"
    light_base: "#F0FAF0"
    light_border: "#DDF9DC"
    dark_text: "#96DB94"
    dark_base: "#1A3A18"
    dark_border: "#275624"
  error:
    light_text: "#E9415D"
    light_base: "#FEECEF"
    light_border: "#FDD8DE"
    dark_text: "#F8778D"
    dark_base: "#3D161D"
    dark_border: "#74202E"
typography:
  family: Geist
  weights:
    regular: 400
    medium: 500
    semibold: 600
shape:
  control_radius: 12px
  round_radius: 9999px
density:
  control_compact: 32px
  control_default: 36px
  control_prominent: 40px
  touch_target_min: 44px
  card_padding_dense: 12px
  card_padding_default: 16px
  card_padding_primary: 20px
---

# StockPulse Design System

This file is the compact visual contract for coding agents working on StockPulse. It describes the
approved target, not a claim that every current screen already conforms.

The Figma file is a **visual reference** for color, density, hierarchy, surface treatment, and
light/dark symmetry. It is not a product specification. Do not copy its Web3 information
architecture, wallet flows, crypto terminology, component APIs, or business behavior.

## 1. Authority and scope

Use these sources in this order:

1. Product semantics, `AGENTS.md`, API contracts, accessibility, and financial-domain rules.
2. This `DESIGN.md` for the target visual language and approved color values.
3. `apps/dsa-web/DESIGN_GUIDE.md` for detailed implementation and delivery guardrails.
4. `apps/dsa-web/src/index.css` and public components for the current executable state.

If the target in this file and the current CSS differ, do not silently mix the two. For a scoped
visual migration, update the semantic definitions in `src/index.css` first, then migrate public
components and pages. Outside such a task, keep the existing runtime token and report the gap.

The 63 linked Figma nodes are references, not 63 automatically approved implementation tasks.

## 2. Color system

### 2.1 Figma variable mapping

The following values were read from the Figma variables used by the supplied nodes. Keep their
values, but translate their names into StockPulse semantics before use.

| Figma variable | Exact value | StockPulse semantic target |
|---|---:|---|
| `Light Mode/Base` | `#F7F8F7` | canvas / app background |
| `Dark Mode/Base` | `#151514` | dark canvas / app background |
| `Light Mode/Text` | `#151514` | primary foreground |
| `Dark Mode/Text` | `#FFFFFF` | dark primary foreground |
| `Light Mode/Body Text + Icon` | `#878980` | muted text and secondary icon |
| `Dark Mode/Body Text + Icon` | `#9B9D95` | dark muted text and secondary icon |
| `Light Mode/Border` | `#EAEBE8` | standard border |
| `Dark Mode/Border` | `#343531` | dark standard border |
| `Light Mode/Light Border` | `#F0F0EF` | subtle separator |
| `Dark Mode/Light Border` | `#1F201D` | dark subtle separator |
| `White` | `#FFFFFF` | light card/popover surface; inverse text |
| `Black` | `#090A05` | high-contrast decorative/inverse black only |
| `State/Success/Light Text` | `#41B83D` | success foreground |
| `State/Success/Light Base` | `#F0FAF0` | success surface |
| `State/Success/Light Border` | `#DDF9DC` | success border |
| `State/Success/Dark Text` | `#96DB94` | dark success foreground |
| `State/Success/Dark Base` | `#1A3A18` | dark success surface |
| `State/Success/Dark Border` | `#275624` | dark success border |
| `State/Error/Light Text` | `#E9415D` | error foreground |
| `State/Error/Light Base` | `#FEECEF` | error surface |
| `State/Error/Light Border` | `#FDD8DE` | error border |
| `State/Error/Dark Text` | `#F8778D` | dark error foreground |
| `State/Error/Dark Base` | `#3D161D` | dark error surface |
| `State/Error/Dark Border` | `#74202E` | dark error border |

Reference nodes used for validation include the light Dashboard `363:9423`, dark Dashboard
`383:4434`, light Settings Profile `348:5293`, dark Settings Profile `399:7566`, and state-bearing
Portfolio/Calculator screens. The supplied `2432:9617` node is only an unbound raw rectangle with
fill `#6BF86A`; it is **not a Figma variable and must not become a StockPulse token**.

### 2.2 Semantic code tokens

Components consume semantic tokens, never Figma names or raw values. Prefer the current project
aliases below; introduce missing state aliases only in an approved token-foundation change.

| Role | Current CSS token | Required behavior |
|---|---|---|
| App canvas | `--background` | Figma Base for the active theme |
| Primary text | `--foreground` | Figma Text for the active theme |
| Card/popover | `--card`, `--popover` | distinct surface; do not hardcode white |
| Muted text/icon | `--muted-text`, `--muted-foreground` | use the theme's Body Text + Icon value |
| Standard border | `--border`, `--input` | use the theme's Border value |
| Subtle separator | semantic border alias | use the theme's Light Border value |
| Brand emphasis | `--primary`, `--ring` | `#41B83D` light / `#96DB94` dark |
| Success | `--success`, `--color-success` | separate semantic role even when equal to brand |
| Error | `--danger`, `--destructive` | use the error family, not market movement colors |
| Warning | `--warning`, `--color-warning` | StockPulse extension; the supplied nodes expose no warning variable |

In JSX/TSX, use project classes such as `bg-background`, `text-foreground`, `text-muted-text`,
`border-border`, `bg-card`, and `ring-primary`. Never write `bg-[#...]`, `text-[#...]`, inline hex,
or Figma variable names in a component.

Brand and state tokens may share a value while remaining different contracts. Never make
`--success` an alias of `--primary`, because either role may evolve independently.

### 2.3 Financial color semantics

StockPulse follows Chinese-market movement semantics:

| Meaning | Light | Dark | Existing token |
|---|---:|---:|---|
| Price up | `#F34949` | `#F45252` | `--home-price-up` |
| Price down | `#00D668` | `#00E06C` | `--home-price-down` |

These colors are product semantics, not decorations. Never derive them from brand, success, or
error tokens. Never reverse them to match the Web3 reference. Always pair color with a sign, arrow,
label, or accessible text so that color is not the only signal.

### 2.4 Known token gaps

The current production CSS is close to the approved Figma palette but not identical. Known gaps
include the standard light border, dark muted text, light success foreground, and light/dark error
foregrounds. The opaque success/error base and border triplets are also not yet complete semantic
families in `src/index.css`.

Do not fix these piecemeal inside page components. A token-alignment PR should update `:root` and
`.dark`, preserve compatibility aliases, add state-family tokens, and validate contrast plus visual
regressions across light and dark modes.

## 3. Typography and content scale

Use Geist through the existing project font stack.

| Role | Size | Weight | Guidance |
|---|---:|---:|---|
| Display | 32px | 600 | rare landing/empty-state headline; not a normal page title |
| Page H1 | 28px | 600 | one per page; 24px on narrow screens |
| Section H2 | 24px | 600 | major workspace section only |
| Section H3 | 20px | 600 | card group or subsection |
| Card title | 16–18px | 600 | 16px is the default |
| Emphasized body/value | 16px | 500–600 | actions, totals, important summary text |
| Default body/control | 14px | 400–500 | normal content, controls, and tables |
| Secondary metadata | 12px | 400–500 | timestamps, provenance, compact supporting text |
| Primary KPI | 28–32px | 600 | one dominant value per summary card, with an explicit unit |

Use tabular numerals for comparable financial values where supported. Do not use 18–20px body text
or 32px headings as defaults. Do not shrink essential labels to force a layout to fit. Truncate only
when the full value remains available through an accessible detail view or tooltip.

## 4. Layout and density

Use a stable application shell, clear page title, primary workspace, and secondary detail areas.
StockPulse is a data-dense financial tool: compact does not mean cramped, and accessible does not
mean every visible control must be 44px tall.

### 4.1 Density scale

| Element | Compact desktop | Default desktop | Touch/narrow-screen behavior |
|---|---:|---:|---|
| Button height | 28–32px | 36px | 40–44px visible height when it is a primary touch action |
| Icon button visual box | 32px | 36px | retain a 44px hit target through container/hit-area sizing |
| Input/select height | 32px | 36px | 44px where coarse pointer use is expected |
| Page horizontal padding | 16px | 20–24px | 12–16px |
| Card padding | 12px dense | 16px | 12–16px |
| Card/grid gap | 12px | 16px | 12px |
| Section gap | 20px | 24px | 16–20px |

Rules:

- Do not apply `min-h-11`, 44px height, or `p-6` to every desktop control and panel.
- Preserve a 44px touch target where needed without forcing every icon or compact table action to
  look 44px large.
- Use the 8px spacing rhythm with 4px half-steps for dense controls; avoid unrelated magic values.
- A page gets one primary action. Secondary actions should not compete through equal size or weight.
- Toolbars should normally fit on one row at desktop width; move lower-priority actions into a
  clearly labeled overflow menu before increasing the toolbar height.

### 4.2 Page grid

- Desktop: use a 12-column grid with 16px gaps. Medium layouts may use 8 columns. Mobile stacks to
  one deliberate reading order.
- Summary cards must align by row and content baseline, but should not receive arbitrary fixed
  heights that create large empty areas.
- Give the main analytical workspace more width than filters, history, provenance, or helper panels.
- Use `minmax(0, 1fr)` and explicit minimums for responsive grids; avoid overflow caused by long
  symbols, model names, currencies, or localized copy.
- At 390px and 320px widths, collapse secondary rails and move contextual detail into drawers or
  deliberate stacked sections. Do not create horizontal page scrolling.
- Empty, loading, error, partial-data, and stale-data states are first-class layouts, not afterthoughts.

### 4.3 Card composition

Cards are for grouping related information, not for decorating every block.

- Default card: 16px outer radius, 1px border, 16px padding, no decorative gradient.
- Dense card/table group: 12px padding. Use 20px only for a deliberate primary summary or form;
  `24px` is exceptional, not the default.
- Nested panels use a smaller radius and quieter surface. Do not exceed two visible surface levels.
- Card header: 16–18px title, optional 12px metadata, and at most one compact trailing action.
- Metric card: label → primary value → unit/change/provenance. Do not enlarge every number equally.
- A static card has no hover lift, pointer cursor, or focus treatment.
- A clickable card must be one semantic link/button, expose an accessible name, and implement the
  complete interactive state contract in section 7.1.
- Avoid grids where every card has the same visual weight. Use one primary analysis region and
  quieter supporting cards so the page has a clear reading order.

### 4.4 Responsive component contract

The web app uses Tailwind CSS v4. Components must adapt through three different signals. These
signals are related, but they are not interchangeable:

1. **Viewport breakpoints** (`sm:`, `md:`, `lg:`, `xl:`) control page composition and shell layout.
2. **Container queries** (`@container`, `@sm:`, `@md:`, and related variants) control reusable
   component layout based on the space the component actually receives.
3. **Pointer capability** (`pointer-coarse:`, `pointer-fine:`) controls hit target and interaction
   density without assuming that screen width equals input type.

Tailwind is mobile-first: unprefixed utilities are the base behavior, and breakpoint-prefixed
utilities apply at that minimum width and above. The current default breakpoints are `sm` 640px,
`md` 768px, `lg` 1024px, `xl` 1280px, and `2xl` 1536px.

#### Viewport responsibilities

- Base / below `sm`: one-column reading order, mobile sheets, wrapped or overflowed toolbars, and
  no hidden primary actions.
- `sm` / `md`: allow paired fields, two-column compact cards, and shorter desktop-style controls
  when space and input capability permit.
- `lg`: enable the persistent sidebar and multi-region workspaces.
- `xl` / `2xl`: increase column count or analytical width; do not scale every font, button, and
  padding value upward just because more space exists.

#### Container responsibilities

Use container queries for components that can appear in the main page, a narrow column, a modal,
or a drawer. Examples include metric groups, card headers, toolbars, filter forms, chart legends,
and action rows.

```tsx
<section className="@container">
  <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2 @3xl:grid-cols-4">
    {/* cards */}
  </div>
</section>
```

Do not use a viewport `md:` rule inside a reusable component when the intended behavior depends on
the component's own width. A 1440px viewport can still contain a 360px drawer.

#### Responsive control sizing

A semantic `size` prop expresses importance/density; responsive variants adapt that size to input
context. Do not create unrelated component APIs such as `mobileSize`, `tabletSize`, and
`desktopSize` on every control.

```tsx
const controlSizes = {
  compact: 'h-8 px-3 text-xs pointer-coarse:min-h-11',
  default: 'h-9 px-3.5 text-sm pointer-coarse:min-h-11',
  prominent: 'h-10 px-4 text-sm pointer-coarse:min-h-11',
} as const;
```

The example describes the contract, not permission to duplicate the map in each component. Keep
complete Tailwind class strings in shared component maps so the compiler can discover them; do not
build utility names dynamically from arbitrary values.

- Width normally follows content. Use `w-full` only for narrow stacked layouts, forms where the
  field owns a column, or explicitly full-width primary mobile actions.
- Height may become more compact on fine-pointer desktop, but text, icons, and focus rings remain
  readable. Do not use tiny 28px controls as the general desktop default.
- Layout may reflow before controls shrink. Preserve label clarity before saving a few pixels.
- Charts and complex visuals respond to their parent width; avoid fixed canvas dimensions.
- Validate at 320px, 390px, 768px, 1024px, and 1440px, including at least one coarse-pointer mode.

## 5. Elevation and depth

Use surfaces, 1px borders, and restrained shadows to establish hierarchy. Avoid neon glow,
cyan/purple bloom, heavy glass blur, or decorative gradients that reduce financial readability.

- Base canvas: no shadow.
- Cards: subtle border and soft shadow only when separation is otherwise insufficient.
- Popovers/modals: stronger elevation than cards, plus a clear overlay and focus trap.
- Selected state: border/ring and background change; never rely on glow alone.
- Hover elevation, if used at all, is limited to a 1px visual lift or a subtle border/shadow change.
  Content must not jump or reflow.

## 6. Shape

- Controls and buttons use the shared 12px radius (`--radius` / `rounded-lg`).
- Cards may use the shared card radius; keep it consistent within one hierarchy.
- `9999px` is reserved for dots, avatars, circular icon buttons, and intentional compact badges.
- Do not turn normal buttons, inputs, tabs, or filter controls into pills by default.

## 7. Components

### 7.1 Required interactive states

Every interactive element—button, link, nav item, clickable card, table row action, tab, segmented
control, icon control, and menu item—must define the following states. A hover style alone is
incomplete.

| State | Required visual and behavioral response |
|---|---|
| Default | clear affordance, readable label, stable dimensions |
| Hover | subtle background/border/text change; no information available only on hover |
| Focus-visible | persistent 2px semantic focus ring with sufficient contrast; never remove outline without replacement |
| Active/pressed | immediate pressed feedback through tone or at most 1px movement; no layout shift |
| Selected/current | persistent state distinct from hover; use `aria-current`, `aria-selected`, or `aria-pressed` |
| Disabled | 45–60% visual emphasis, no hover/active animation, semantic `disabled`/`aria-disabled` |
| Loading | stable width, progress indicator, `aria-busy`, duplicate submission prevented |
| Error | nearby explanation and recovery action; do not encode the problem only in red |

Interaction timing:

- Color, border, and opacity: 120–160ms.
- Panel/drawer movement: 180–240ms.
- Avoid `transition-all`; name the properties being animated.
- Respect `prefers-reduced-motion`. Keyboard and coarse-pointer users must receive equivalent state
  information without depending on hover.

### 7.2 Buttons

- Primary CTA: inverse neutral, black-on-light or white-on-dark, using semantic foreground/background.
- Brand green: focus, selection, links, indicators, and deliberate secondary emphasis—not every CTA.
- Secondary/outline: card or transparent surface with standard border.
- Destructive: the error family, with an explicit destructive label.
- Every icon-only button needs an accessible name and a visible focus state.
- Default desktop button is 36px high with 14px text and 12–16px horizontal padding. Use 32px for
  compact table/toolbar actions, 40px for prominent actions, and 44px visible controls only where
  touch context warrants it.
- Ordinary buttons use the shared 12px radius. Pills are reserved for compact filters, badges, and
  intentional segmented selections—not all buttons.
- Keep one-line labels. If localized text does not fit, allow sensible width growth or move the
  action; do not increase every button height.
- Do not bypass the public `Button` merely to create a new size or state. Add a deliberate shared
  variant when a real semantic gap exists.

### 7.3 Cards and panels

- Use `--card`, `--card-foreground`, and `--border`.
- A card must group related content; do not wrap every row in a card.
- Charts, totals, units, timestamps, and data provenance should have a stable visual hierarchy.
- Card hover/focus behavior follows section 4.3; a static information card must not pretend to be
  clickable.

### 7.4 Forms and settings

- Labels stay visible; placeholders are examples, not labels.
- Show validation near the affected field and preserve the user's entered value.
- Secret values are masked and never echoed into diagnostics or screenshots.
- Save, conflict, restart-required, inherited, and connection states need text plus visual status.

### 7.5 Tables and financial data

- Align numeric columns right and text columns left.
- Keep units and currencies explicit; never infer them from color or column position.
- Distinguish zero, unavailable, stale, estimated, and loading values.
- Sorting, filtering, pagination, and row actions must remain keyboard reachable.

### 7.6 Routes, dialogs, drawers, and overlays

Choose the interaction container by user intent, not by which component is easiest to import.

| Container | Use when | Do not use when | Target size |
|---|---|---|---|
| Route/page | it is a primary task, shareable destination, or multi-step workspace | the user only needs a quick contextual inspection | uses the main content grid |
| Drawer | inspecting/editing contextual detail while preserving the current page | the task is the new primary destination or needs several nested steps | 360px compact, 480px default, 640px wide; max 90vw |
| Modal | a short blocking decision, focused form, or bounded action | displaying long reports, tables, history, or general navigation | 400px compact, 520px default, 640px wide; max 85dvh |
| ConfirmDialog | confirming destructive, irreversible, or materially costly action | ordinary acknowledgement, success message, or long form | 360–420px |
| Popover/menu | short transient choices anchored to a trigger | complex forms or content requiring deep link/back behavior | content-sized with viewport collision handling |
| Inline disclosure | local optional detail that does not interrupt the task | content that must be independently shareable | bounded by its parent |

Overlay rules:

- Use the shared `Modal`, `Drawer`, and `ConfirmDialog` primitives and centralized overlay z-index.
- Modal is centered from `sm` upward; a short mobile modal may become a bottom sheet. A desktop side
  drawer becomes a full-width mobile sheet, preserving the same task and focus order.
- Drawer width is a named size, not a page-level arbitrary `max-w-*` value. Default content padding
  is 16px compact / 20px normal; 24px is reserved for unusually spacious editorial content.
- Only a `ConfirmDialog` may intentionally appear over an existing modal/drawer. Do not nest general
  modals, drawers, or popovers that contain another complex form.
- Trap focus, close on Escape where safe, restore focus to the trigger, lock background scroll, and
  prevent background interaction.
- Backdrop click may close a read-only overlay. It must not discard unsaved input or interrupt a
  submission without confirmation.
- A destructive confirmation names the affected object, consequence, and irreversible scope.
- Long-lived or shareable drawer selection belongs in the URL so reload and Back/Forward restore the
  state. Ephemeral confirmation state does not belong in the URL.

### 7.7 Page navigation

- Use router links for navigation and buttons for actions. Do not make a card-shaped `div` navigate.
- Keep the application shell stable during route changes. Do not flash a full-page blank state.
- Navigation items define default, hover, focus-visible, active/current, and pending states. Active
  is persistent and must not look identical to hover.
- If route content takes longer than roughly 150ms, show a restrained progress/skeleton state in the
  destination region while preserving the shell and current layout dimensions.
- After intentional page navigation, move focus to the page heading or main landmark when helpful.
  Back/Forward restores URL-driven selection and appropriate scroll/focus context.
- Use a modal only for a blocking subtask. Opening a normal page inside a modal or drawer breaks
  linking, refresh, browser history, and accessibility expectations.
- Warn before navigation only when the current view has unsaved or actively submitting work.

## 8. Do and don't

| Do | Don't |
|---|---|
| Map approved Figma values to semantic project tokens | Paste Figma variable names into JSX/CSS modules |
| Reuse public components and existing token aliases | Create page-local parallel design systems |
| Keep brand, success, error, and price movement separate | Reuse one green/red variable for unrelated meanings |
| Validate both themes and narrow widths | Approve a desktop light screenshot as complete evidence |
| Use state text, icon, and color together | Communicate financial state with color alone |
| Record an intentional design-reference deviation | Copy Web3 behavior because it exists in the reference |
| Ask when a semantic token is missing | Invent a new raw color in a component |
| Give every control a complete state set | Stop at a decorative hover style |
| Separate visible control size from touch hit area | Make every desktop control 44px tall |
| Use routes for primary/shareable tasks | Put normal page navigation inside a modal |
| Use named modal/drawer sizes | Pass arbitrary width and padding from each page |
| Make clickable cards semantic links/buttons | Add cursor/hover to static cards |

## 9. Accessibility and interaction

- Meet WCAG 2.2 AA contrast for normal text, controls, focus indicators, and meaningful chart marks.
- Preserve visible `:focus-visible` treatment using the brand ring.
- Support keyboard operation, screen-reader names, reduced motion, zoom, and text resizing.
- Use latest-request-wins behavior for replaceable async views; prevent stale responses from
  overwriting the active selection.
- Loading indicators must describe what is loading. Errors must state what failed and what the user
  can do next.
- Motion should explain state change, remain brief, and respect `prefers-reduced-motion`.

## 10. Current implementation gaps

This section records known mismatches so agents do not treat existing inconsistency as the desired
pattern. It is not authorization to repair unrelated pages in one broad change.

- `components/common/Button.tsx` currently makes every size pill-shaped and uses `transition-all`.
  Its primary inverse color and focus ring are directionally correct, but shape and transition
  behavior do not match sections 6 and 7.1.
- `components/common/Card.tsx` defaults to 20px padding and offers 24px as a normal large option;
  card utilities also apply a uniform 16px radius. Pages need a clearer dense/default/primary
  hierarchy instead of applying the same visual weight everywhere.
- `components/common/Drawer.tsx` defaults to `max-w-2xl` and 24px content padding. Named drawer sizes
  and compact/default padding are not yet encoded in its API.
- Modal, Drawer, and ConfirmDialog already provide focus management, Escape handling, scroll lock,
  and focus restoration. The remaining gap is consistent product-level selection, sizing, nesting,
  and URL behavior—not replacement with page-local overlays.
- Sidebar navigation has hover and active styles, but focus-visible and route-pending treatment are
  not consistently defined across all navigation actions.
- Many page-specific controls still choose `min-h-11`, arbitrary layout classes, or local state
  styling instead of a shared density and interaction contract.
- The app uses Tailwind CSS v4.1.18 and many viewport breakpoint utilities, but reusable components
  rarely use container queries. Page-local `sm:/md:/lg:` rules therefore do not reliably adapt a
  component placed in a sidebar, modal, drawer, or narrow grid column.

Close these gaps in foundation-first slices: state/density tokens → public components → shell and
navigation → representative page → remaining pages. Do not start with page-by-page CSS patches.

## 11. Agent workflow

Before editing UI:

1. Read `AGENTS.md`, this file, `apps/dsa-web/DESIGN_GUIDE.md`, and the affected public components.
2. Classify the task as token foundation, public component, shell, page visual, interaction, or IA.
3. Confirm whether the current CSS already has the required semantic token.
4. Reuse the existing component/API contract; do not change behavior in a visual-only task.
5. Treat Figma code, screenshots, and node metadata as reference evidence, never final production code.
6. For every changed interactive element, enumerate default, hover, focus-visible, active, selected,
   disabled, loading, and error states before implementation.
7. For every overlay or navigation change, justify Route vs Drawer vs Modal vs ConfirmDialog using
   section 7.6.

Before handing off:

- Run lint, tests, build, and proportional Playwright coverage for the affected surface.
- Capture light/dark and desktop/mobile evidence for user-visible UI changes.
- Scan changed components for raw colors, magic dimensions, glow, and accidental Web3 language.
- Confirm red-up/green-down semantics and non-color indicators remain correct.
- Document adopted and rejected reference details in the PR body.
- Verify control height, card padding, overlay width, keyboard focus, and Back/Forward behavior at
  desktop and 390px/320px widths.

## 12. Figma reference boundary

Approved from the supplied Figma file:

- exact named color-variable values listed in section 2.1;
- neutral warm canvas, high-contrast text, quiet borders, and light/dark symmetry;
- restrained data-dashboard density, cards, tables, settings, portfolio, and empty-state patterns.

Not approved by reference alone:

- the raw `#6BF86A` rectangle or any other unbound fill;
- wallet, transfer, exchange, DEX, crypto-address, or token-market product capabilities;
- routes, navigation labels, copy, data models, API contracts, component props, or interactions;
- raw generated Tailwind, absolute positioning, image assets, shadows, spacing, or arbitrary radii;
- Western green-up/red-down market conventions.

When a Figma detail conflicts with StockPulse product semantics, accessibility, or existing behavior,
preserve the product contract and record the visual deviation.
