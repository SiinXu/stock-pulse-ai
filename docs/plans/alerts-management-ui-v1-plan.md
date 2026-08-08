# Plan: Alerts management Web UI (V1 / W15-08)

**Status:** BLOCKED — waiting on context-aware alert evaluation PR **#820** to merge  
**Issue:** [#241](https://github.com/SiinXu/stock-pulse-ai/issues/241)  
**Branch:** `feat/alerts-management-ui-v1`  
**PR title:** `feat: add the alerts management interface`  
**Hard dependency:** [#820](https://github.com/SiinXu/stock-pulse-ai/pull/820) `feat: add context-aware event-driven alert evaluation` (must be **MERGED**; implement against its **merged** public surface via OpenAPI / generated types + live trigger payloads, not a guessed API)

This document is the V1 implementation plan only. **No production Web UI, types, i18n, or tests are implemented on this branch until #820 lands.**

---

## 1. Why blocked

Issue #241’s Web surface needs:

1. **`corporate_event` alert type** (rule create/edit/filter) with `event_categories`, `lookback_hours`, `min_items`
2. **Impact / context cards** on trigger history: what fired, why it matters, impacted holdings/watchlist
3. Honest **notification-channel dispatch** status from existing attempt records

Those evaluation + diagnostics contracts are introduced by **#820** (backend V0). As of plan commit time:

| PR | Role | State |
| --- | --- | --- |
| **#820** | Hard dependency — `corporate_event` + `diagnostics.impact_context` / `event_context` | **OPEN** (`mergedAt: null`) |
| **#787** | Soft fence — owns `apps/dsa-web/src/api/alerts.ts` + tests | **OPEN** |
| **#822** | Soft fence — owns `AlertsWorkspace.tsx` TanStack Query migration | **OPEN** (draft) |

Building UI against an unmerged #820 head risks contract drift. Resume only after merge, then re-read the **merged** service, docs (`docs/alerts.md` / `docs/alerts_EN.md`), worker diagnostics ordering, and regenerate/consume OpenAPI artifacts if the schema surface changed.

---

## 2. Existing surface inventory (EXTEND — do not rebuild)

Main already has a full Alert Center under Signal Center. **Reuse and extend these modules.**

| Path | Role today | V1 action |
| --- | --- | --- |
| `apps/dsa-web/src/pages/AlertsPage.tsx` | Thin page shell → workspace | Keep |
| `apps/dsa-web/src/components/alerts/AlertsWorkspace.tsx` | Rules / history / notifications tabs, CRUD, filters, empty/loading/error | Extend carefully (soft conflict with #822) |
| `apps/dsa-web/src/components/alerts/AlertRuleForm.tsx` | Full rule form by scope/type | **Extend** for `corporate_event` params |
| `apps/dsa-web/src/components/alerts/AlertRuleList.tsx` | Rule table + enable/disable/edit/delete/test | Extend type labels/filter only if needed |
| `apps/dsa-web/src/components/alerts/AlertTriggerHistory.tsx` | Trigger table (status, phase/quality, target, observed, reason) | **Extend** with impact/context cards or expandable row |
| `apps/dsa-web/src/api/alerts.ts` | Manual snake/camel client | Prefer **not** to own while #787 open; if parameter mapping must change, coordinate or land after #787 |
| `apps/dsa-web/src/types/alerts.ts` | Hand types for rules/triggers/notifications | Extend `AlertType` + parameters + typed impact helpers |
| `apps/dsa-web/src/locales/alerts.ts` | Labels via `createUiLanguageRecord` | Append keys for corporate event + impact cards |
| `apps/dsa-web/src/i18n/translations/*` (×10 languages) | Flat UI string catalog | Append-only sync for new keys |
| Component tests under `components/alerts/__tests__/` | Form / list / history | Extend + add impact-card coverage |

### Already present (do not reimplement)

- Rules list/CRUD, dry-run test, enable/disable, pagination
- Trigger history with market phase + analysis data-quality badges
- Notification history with channel labels + success filter (includes `__dispatch__` / `__context__`)
- Empty / loading table states via `DataTable` `status` + `emptyState`
- i18n scaffolding for alert labels (zh/en base + language record pattern)

### Gaps relative to #241 Web acceptance

- No `corporate_event` in `AlertType` union or form/filter options
- No rendering of `diagnostics.impact_context` / `event_context` (what / why / affected holdings)
- Trigger `diagnostics` is still a **string** (JSON) on the API schema; impact is **not** a first-class field like `market_phase_summary` (verify post-#820 merge whether that stays true)
- Channel honesty: notification tab exists, but trigger-detail linkage (“which channels this firing went to”) may need clearer UX from dispatch attempt rows
- Tests do not cover corporate-event form validation or impact-card empty/degraded states

---

## 3. #820 contract to consume (preview from open PR head — verify post-merge)

### Rule: `corporate_event`

| Field | Value |
| --- | --- |
| `alert_type` | `corporate_event` |
| `target_scope` | `single_symbol` \| `watchlist` \| `portfolio_holdings` |
| `parameters.event_categories` | subset of `earnings`, `shareholder`, `mna`, `regulatory`, `analyst` (default all) |
| `parameters.lookback_hours` | int `1..168`, default `24` |
| `parameters.min_items` | int `1..50`, default `1` |

Evaluation (backend): managed `intelligence_items` only; `data_source=intelligence_items`; `observed_value` = match count; `threshold` = `min_items`.

### Diagnostics payload (worker)

On trigger, diagnostics object (serialized to string on list API today) includes:

```text
event_context:
  what_happened, why_it_matters, event_category, event_categories,
  matched_count, source_item_id, source_name, source_url, matched_items[]

impact_context:   # when AGENT_EVENT_IMPACT_CONTEXT_ENABLED (default true)
  degraded: bool
  what_happened, why_it_matters, event_category
  affected: { symbol, in_watchlist, in_portfolio, portfolio_accounts[],
              quantity, weight_pct, market_value_base,
              watchlist_error?, portfolio_error? }
  related_analysis?: string
  matched_count?, source_item_id?, source_name?, source_url?, event_categories?
```

Worker keeps compact keys (`impact_context`, `event_context`, …) first so sanitization truncation does not drop them.

**UI honesty rules:**

- If `impact_context.degraded === true` or affected lookup errors present → show partial-context badge, never invent holdings membership
- If diagnostics missing / unparseable → fall back to `reason` / existing phase columns; do not fabricate impact cards
- Channel status only from real `AlertNotificationItem` rows (`success`, `channel`, `error_code`, `retryable`) — never claim delivery without a successful attempt record

### Config (read-only awareness)

| Key | Default | UI note |
| --- | --- | --- |
| `AGENT_EVENT_IMPACT_CONTEXT_ENABLED` | `true` | No settings form in V1; UI degrades when context absent |

---

## 4. V1 scope (Web only)

### In scope

1. **Extend `AlertRuleForm` + type filter options**
   - Add `corporate_event` to symbol/watchlist/portfolio_holdings type pickers
   - Fields: multi-select categories, lookback hours, min items (with validation matching backend bounds)
   - Ensure create/update payload parameters round-trip (client parameter mapping may require a careful #787 coordination or post-#787 follow-up)

2. **Trigger history context / impact cards**
   - New presentational component(s) under `components/alerts/` (e.g. `AlertImpactContextCard`) used from history row expansion or detail panel
   - Parse diagnostics JSON safely; prefer `impact_context`, fall back to `event_context`, then reason string
   - Show: what happened, why it matters, event category, watchlist/portfolio membership + weight when present, related analysis excerpt, degraded note

3. **Notification-channel honesty**
   - Keep notifications tab; improve trigger-scoped view or inline badges from dispatch attempts for the selected trigger
   - Labels already include known channels; unknown channels stay raw codes

4. **Empty / loading / error**
   - Reuse `DataTable` / `InlineAlert` / `ApiErrorAlert` patterns already in workspace
   - Impact card empty: “No impact context for this trigger” (i18n), not a spinner forever

5. **Component tests**
   - Form: corporate_event defaults + validation bounds
   - Impact card: full context, degraded, missing diagnostics
   - Notification honesty: success vs failed attempt rendering

6. **i18n ×10 + sync**
   - Append keys via existing `locales/alerts.ts` + `createUiLanguageRecord` / translation catalog sync scripts used by the repo
   - Run project i18n check scripts after append

7. **CHANGELOG append-only** under `[Unreleased]` flat format

### Out of scope (explicit fences)

| Fence | Owner / reason |
| --- | --- |
| Backend evaluation / worker / `event_alerts.py` | **#820** — consume only |
| Regenerating OpenAPI as primary work | Only if merged #820 actually changes schema; prefer generated types when present |
| Owning rewrite of `apps/dsa-web/src/api/alerts.ts` while **#787** open | Soft fence; minimize or sequence after integrations slice |
| Large rewrite of `AlertsWorkspace` data-fetch architecture | Soft fence **#822** (TanStack rollout) — prefer leaf components |
| Digest mode, LLM impact write-ups, live news fetch | Out of #241 V0/V1 Web |
| New notification channels | Backend/plugins |
| Settings page for `AGENT_EVENT_IMPACT_CONTEXT_ENABLED` | Not required for V1 |

### Shared append-only

- `docs/CHANGELOG.md`
- i18n catalogs ×10 (+ sync)
- Do not touch unrelated open-PR surfaces

---

## 5. Proposed component / type shape (draft)

### Types (`types/alerts.ts`)

```ts
// AlertType union adds: 'corporate_event'

export type CorporateEventCategory =
  | 'earnings'
  | 'shareholder'
  | 'mna'
  | 'regulatory'
  | 'analyst';

// AlertRuleParameters adds:
//   eventCategories?: CorporateEventCategory[];
//   lookbackHours?: number;
//   minItems?: number;

export type AlertImpactContext = {
  degraded?: boolean;
  whatHappened?: string | null;
  whyItMatters?: string | null;
  eventCategory?: string | null;
  eventCategories?: string[];
  matchedCount?: number;
  sourceItemId?: string | number | null;
  sourceName?: string | null;
  sourceUrl?: string | null;
  affected?: {
    symbol?: string | null;
    inWatchlist?: boolean;
    inPortfolio?: boolean;
    portfolioAccounts?: unknown[];
    quantity?: number | null;
    weightPct?: number | null;
    marketValueBase?: number | null;
    watchlistError?: string | null;
    portfolioError?: string | null;
  };
  relatedAnalysis?: string | null;
};
```

Helper: `parseAlertDiagnostics(diagnostics?: string | null): { impactContext?: AlertImpactContext; eventContext?: ... }` — resilient to non-JSON / partial payloads.

### UI placement

- **Form:** parameter section when `alertType === 'corporate_event'` (mirror existing type-specific sections in `AlertRuleForm`)
- **History:** keep table columns; add detail region or expandable row for impact card when row selected (workspace already has `selectedTriggerId`)
- **Notifications:** when a trigger is selected, filter or highlight attempts for that `triggerId` if API supports it (already has `triggerId` query)

### Client parameter mapping risk

`toSnakeRulePayload` in `api/alerts.ts` currently allow-lists parameter keys and would **drop** `event_categories` / `lookback_hours` / `min_items`. Resume checklist must either:

1. Land after #787 and extend the generated/manual mapping once, or  
2. Land a minimal append to `alerts.ts` with explicit coordination note if #787 still open and mapping is blocking.

Do **not** invent a second alerts client.

---

## 6. Verification plan (when unblocked)

Fast verify (wave instruction):

```bash
cd apps/dsa-web
npm run lint
npm run test -- src/components/alerts
# i18n sync / check scripts used by the repo, e.g.:
node scripts/check-ui-i18n-resources.mjs
# and any high-risk i18n audit if keys touch listed surfaces
```

Also:

```bash
# exact counts for delivery notes
git diff --stat origin/main...HEAD
git diff --name-only origin/main...HEAD | wc -l
```

PR body must include:

- DOM evidence path or component-test screenshots alternative
- **Screenshot-limitation note** if interactive browser capture unavailable (AGENTS.md / PR template)
- Refs #241; dependency note for #820 (merged SHA)
- Rollback: revert PR

---

## 7. Resume checklist (post-#820 merge)

1. `git fetch --all --prune`; confirm working tree clean; rebase/ff onto latest `origin/main`.
2. Confirm **#820 `mergedAt` is non-null**; record merge commit SHA.
3. Re-read merged:
   - `src/services/event_alerts.py`
   - `src/services/alert_worker.py` diagnostics ordering
   - `docs/alerts_EN.md` / `docs/alerts.md` P9 section
   - `api/v1/schemas/alerts.py` (any new first-class fields?)
   - `apps/dsa-web/openapi.json` / `src/types/api.generated.ts` if regenerated on main
4. Re-check open PR ownership:
   - `api/alerts.ts` → #787 status
   - `AlertsWorkspace.tsx` → #822 status
5. Implement minimal extend path (form → history impact card → notifications honesty → tests → i18n ×10 → CHANGELOG).
6. Fast verify + freshness pass vs `origin/main`.
7. Undraft PR; update body with verification, visual evidence / limitation note, risks, rollback.
8. Comment on **#241** with Web V1 status and residual follow-ups.

---

## 8. Risks

| Risk | Mitigation |
| --- | --- |
| #820 diagnostics remain string-only | Safe JSON parse helper; degrade to reason text |
| #787 concurrent rewrite of alerts client | Fence client edits; sequence after merge if needed |
| #822 refactors workspace data loading | Prefer leaf components (`AlertRuleForm`, history/impact cards) |
| Keyword classification false positives (backend) | UI shows source title/URL honestly; no extra confidence chrome |
| Shared CHANGELOG / i18n conflicts | Append-only; re-pull before final push |

---

## 9. Rollback

- Close/revert this PR (plan-only until unblocked; after implementation: full revert)
- No backend or DB migration owned by this branch
- Existing alert center remains functional without corporate-event UI

---

## 10. HANDOFF (lifecycle pause)

| Field | Value |
| --- | --- |
| Wave | W15-08 · V3 |
| State | **PAUSED / DRAFT** |
| Reason | Hard dependency **#820** not merged |
| Branch | `feat/alerts-management-ui-v1` |
| Plan | `docs/plans/alerts-management-ui-v1-plan.md` |
| Issue | #241 |
| Soft fences | #787 (`api/alerts.ts`), #822 (`AlertsWorkspace.tsx`) |
| Next human/agent action | Wait for #820 merge → run resume checklist §7 |
