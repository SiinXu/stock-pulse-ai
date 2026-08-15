# Navigation Information Architecture — Target Proposal

**Status**: Phase 2 B0/B1 follow-up keeps both core workspaces visible (Today · Research · Agent · Signals · Portfolio · Settings). Contextual and administrator-only routes remain outside the primary sidebar. Historical A–D options are retained below for context.
**Issue**: [#368](https://github.com/SiinXu/stock-pulse-ai/issues/368)  
**Design input**: [#873](https://github.com/SiinXu/stock-pulse-ai/issues/873)  
**Companion PR**: mechanical label / redirect / palette hygiene only for the audit baseline; chrome batches land separately

This document records the **current-state audit** and **target IA options** so the maintainer can pick a direction. Speculative route restructuring is intentionally out of scope for the mechanical PR.

> Chinese twin: [navigation-ia-proposal_zh.md](navigation-ia-proposal_zh.md)

---

## 1. Current-state audit (as of mechanical PR baseline)

### 1.1 Canonical routes (shell)

| Path | Page / surface | Primary nav? | Notes |
| --- | --- | --- | --- |
| `/` | Home | Yes | Attention hub; still carries workspaces via query |
| `/research` | Research overview | Yes (group root) | Cards to Research tools |
| `/research/market` | Market review | Yes (Research child) | |
| `/research/discover` | Discover (screening) | Yes (Research child) | |
| `/research/analysis` | Analysis Workbench | Yes (Research child) | Segments: launch / tasks / history |
| `/research/backtest` | Backtest | Yes (Research child) | |
| `/research/skill-outcomes` | Skill outcomes | Yes (Research child) | Low-frequency research tool |
| `/portfolio` | Portfolio / holdings | Yes | |
| `/chat` | Agent chat | Yes | Path kept for deep-link compatibility; label is Agent |
| `/settings` | Settings | Yes | Usage nested as section |
| `/signals` | Signal Center | Yes | Single instance for signals + alerts + review |
| `/approvals` | Human approvals | **No** (Home / palette) | Admin auth gated |
| `/stocks/:stockCode` | Stock workspace | **No** (content page) | |
| `/login` | Login | Standalone | `?redirect=` deep-link preserve |
| `/playground` (+ render) | Component playground | Standalone / not product nav | Dev surface |

### 1.2 Legacy redirects (compatibility surface — do not rename canonical paths)

| Legacy path | Canonical target | Query mapping |
| --- | --- | --- |
| `/decision-signals` | `/signals` | Decision-signals → Signal Center state map |
| `/alerts` | `/signals` | Alerts view → Signal Center tab/history map |
| `/screening` | `/research/discover` | Preserve query/hash |
| `/backtest` | `/research/backtest` | Preserve query/hash |
| `/usage` | `/settings?section=usage` | Section override + preserve remainder |

**Invariant**: never rename a public route path in place; add redirects only.

### 1.3 Orphans

| Kind | Path / entry | Assessment |
| --- | --- | --- |
| Reachable, unlinked in sidebar | `/approvals`, `/notifications`, `/stocks/:code`, `/event-alerts`, `/portfolio/performance`, `/research/report-compare` | **Intentional** (Home / bell / owning workspace / content context) |
| Linked but dead | — | None found in product nav or command palette after mechanical hygiene |
| Dead page modules without routes | `AlertsPage` re-export shell | Routed via `/signals` + legacy redirect only |
| Deep-link allowlist gap (fixed in mechanical PR) | `/research/skill-outcomes` | Was rejected as `unsupported_route`; now allowed |

### 1.4 Primary nav (target after #873 B0/B1)

Order: **Today (`layout.nav.home`) → Research (group) → Agent → Signals → Portfolio → Settings**.

Research children order: **Market review → Discover → Analysis Workbench → Backtest → Calculators → Skill outcomes**.

Agent is a primary workspace. Approvals remains a command-palette secondary page with a Home entry because administrator authentication governs access. Sidebar + Cmd+K pages share `listCommandPalettePages` / `APPLICATION_NAVIGATION_ITEMS` in `navigation.ts`; path constants remain `routes.ts` only.

Labels for Research children use the `layout.nav.*` key namespace (mechanical alignment).

### 1.5 Mechanical fixes shipped with the audit PR

| Fix | Evidence |
| --- | --- |
| Research child labels use `layout.nav.marketReview` / `layout.nav.analysis` (not page-title keys) | `navigation.ts`, `ResearchOverviewPage.tsx`, i18n ×10 |
| Command palette indexes Home, Research, Analysis Workbench, Approvals with the same nav labels | `CommandPalette.tsx` + tests |
| Command palette action “Start analysis” stays an action; Workbench is a page entry | Palette actions vs pages split |
| Deep-link parser allows `/research/skill-outcomes` | `deepLink.ts` + test |
| Route inventory regression test for nav vs legacy map | `routing/__tests__/routeInventory.test.ts` |

No speculative domain regrouping (e.g. moving Signal Center under Home, Settings subtree redesign, mobile bottom bar) is implemented here.

---

## 2. Target architecture options — DECISION NEEDED

Issue #368 describes a task-oriented target IA that already partially matches the shipped six-domain shell. Remaining decisions are about **depth**, **where Signals/Approvals live**, and **how far Home/Agent/Settings should expand**.

### Option A — Stabilize the visible core shell (current)

**Shape**: keep six primary domains with Agent and Signals visible; Approvals remains available through Home/palette; no contextual detail route becomes a top-level domain.

| Pros | Cons |
| --- | --- |
| Matches current code, UI manual, and tests | Approvals remain easy to miss for non-admin users |
| Lowest migration cost and deep-link risk | Home still denser than the “three-block” target |
| Aligns with “no new top-level domains” rule | Skill outcomes stays a Research child without a Discover/sentiment split |

**When to choose**: ship incremental Home/Signal empty states and workbench polish without another nav re-org.

### Option B — Full #368 domain map (Home + Signal Center secondary + Research + Portfolio + Agent + Settings)

**Shape**: issue target (attention hub Home; single Signal Center; Research Market/Discover/Workbench/Backtest; Portfolio holdings+risk; Agent chat/process/personas; Settings system/plugins/notifications/usage/API).

| Pros | Cons |
| --- | --- |
| Task-oriented; external review already favored this map | Requires multi-PR content redesign (Home blocks, Settings IA, Agent sub-surfaces) |
| Clear frequency layering | High conflict risk with concurrent page-split PRs |
| Mobile bottom bar story is defined | Bottom bar is a PWA/mobile project of its own |

**When to choose**: maintainer accepts a sequenced epic with binding constraints from #368, **after** mechanical hygiene lands.

### Option C — Promote Signal Center (or Approvals) into primary nav

**Shape**: add Signal Center (and optionally Approvals) as top-level or Home children.

| Pros | Cons |
| --- | --- |
| Improves discoverability without cmd+k/bell literacy | Breaks “signals do not occupy bottom bar / single secondary instance” intent |
| Matches some power-user muscle memory from early 10-item nav | Re-widens top-level IA; contradicts issue principle of frequency layering |

**When to choose**: only if analytics show Signals entry failure rates that palette/bell cannot fix.

### Option D — Collapse Research children further

**Shape**: fewer Research children (e.g. hide Skill outcomes behind Overview only; merge Discover into Analysis launch).

| Pros | Cons |
| --- | --- |
| Shorter sidebar on small screens | Hides real tools; skill-outcomes already low frequency but linked for evaluators |
| | Conflicts with overview cards and existing deep links |

**When to choose**: after measuring Research flyout noise; not a default.

---

## 3. Binding constraints (from #368 — remain binding if Option B is chosen)

1. Home default: Today’s Focus + To-dos + Signal summary; other blocks collapsed by default.  
2. Exactly one Signal Center instance; context filters via URL/session.  
3. Analysis is one workbench with three segments (not parallel secondary pages).  
4. Secondary empty states with a primary action.  
5. Desktop-only capabilities must not leave dead Web/PWA entries.  
6. cmd+k indexes secondary pages and key actions (partially addressed mechanically).  
7. Bell is first entry for signals/alerts/approvals deep links.  
8. Portfolio header reserves multi-portfolio switcher placeholder.  
9. #161 splits: import into analysis vs recognize holdings from screenshot.

Paper trading stays a portfolio type; plugin marketplace stays under Settings until thresholds in #368 are met.

---

## 4. Migration mapping (reference only — not executed here)

| Current | Target under Option B |
| --- | --- |
| Home flat density | Slim attention hub + configurable area |
| `/signals` (+ legacy decision-signals/alerts) | Signal Center secondary under Home domain (same path preferred) |
| `/chat` | Agent · Chat (path may stay `/chat`) |
| `/portfolio` | Portfolio · Holdings & watchlist |
| `/research/*` | Research tools as today, content hierarchy refined |
| `/usage` → settings usage | Settings · Usage & cost |
| Market review / history | Research · Market / Workbench history segment |

---

## 5. Maintainer decision checklist

Please comment on #368 with one of:

- **A** — Stabilize current shell; only content/empty-state PRs next  
- **B** — Full #368 map as sequenced epic (list first child issue)  
- **C** — Promote Signals and/or Approvals into primary nav  
- **D** — Collapse Research children (specify which)  
- **Custom** — describe deltas  

Until a choice is recorded, implementers must **not** restructure routes or primary domains beyond mechanical label/redirect/palette hygiene.
