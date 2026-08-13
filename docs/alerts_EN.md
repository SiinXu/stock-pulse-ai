# Real-Time Alert Center (English Companion)

This document is the English companion for [alerts.md](alerts.md). The Chinese document remains the full phase history for Issue #1202 (P0–P8). This companion focuses on **Issue #241 Backend V0** (smart event-driven alerts with context).

## Baseline (shared with Chinese doc)

- Worker: `src/services/alert_worker.py`
- Rule evaluation: `src/services/alert_service.py` + `src/agent/events.py`
- Gates: `AGENT_EVENT_MONITOR_ENABLED`, `AGENT_EVENT_MONITOR_INTERVAL_MINUTES`
- Legacy JSON: `AGENT_EVENT_ALERT_RULES_JSON` (price_cross / price_change_percent / volume_spike only)
- Delivery: `NotificationService.send_with_results(..., route_type="alert")`
- Channel failure never stops the rest of the worker cycle or the main analysis pipeline

## P9 / Issue #241 Backend V0 — Context-aware corporate event alerts

### Goals

- Detect important corporate events already stored as managed intelligence
- Explain **what happened**, **why it matters**, and **affected holdings/watchlist**
- Deliver via the existing alert notification route with an enriched template
- Stay on the existing alert rule model (do not replace price/tech/portfolio/market rules)

### Data-source rule (hard)

The alert hot path **must not** open new blocking market/news provider calls. Evaluation and context assembly only read:

- `intelligence_items` (already ingested)
- portfolio snapshot with `include_realtime=False`
- recent `analysis_history` rows

### Config

| Key | Default | Meaning |
| --- | --- | --- |
| `AGENT_EVENT_IMPACT_CONTEXT_ENABLED` | `true` | Attach `impact_context` to triggered diagnostics and notification body |

Corporate event rules themselves are opt-in via Alert API rule creation (not legacy JSON).

### `corporate_event` rule contract

| Field | Value |
| --- | --- |
| `alert_type` | `corporate_event` |
| `target_scope` | `single_symbol`, `watchlist`, or `portfolio_holdings` |
| `parameters.event_categories` | subset of `earnings`, `shareholder`, `mna`, `regulatory`, `analyst` (default: all) |
| `parameters.lookback_hours` | integer `1..168`, default `24` |
| `parameters.min_items` | integer `1..50`, default `1` |

Evaluation:

1. Load symbol-scoped intelligence items and filter by lookback hours.
2. Classify title/summary with bilingual keyword lexicons.
3. Trigger when match count ≥ `min_items`.
4. No managed items → `skipped`; lookup errors → `failed` / `evaluation_error`.
5. `data_source=intelligence_items`; `observed_value` = match count; `threshold` = `min_items`.
6. On trigger, write `diagnostics.event_context`.

### Impact context

When impact enrichment is enabled and a rule truly triggers, the worker best-effort builds `diagnostics.impact_context`:

- `what_happened` / `why_it_matters` / `event_category`
- `affected.in_watchlist` / `affected.in_portfolio` / optional `weight_pct`
- `related_analysis` short excerpt
- `degraded=true` if any managed lookup fails (notification still sends)

Notification content appends a public impact excerpt after the existing phase and decision-signal excerpts. Missing context degrades gracefully to the original reason string.

### Implementation map

- `src/services/event_alerts.py`
- `src/services/alert_service.py`
- `src/services/alert_worker.py`
- Config registry + `.env.example`

### Out of scope for V0

- Web form / `apps/dsa-web/src/api/alerts.ts` (follow-up; integrations OpenAPI slice ownership)
- Live news fetch on the alert path
- Push vs digest mode
- LLM-generated impact write-ups
- New tables or migrations


### Web follow-up (issue #241)

- The dedicated `/event-alerts` view uses the server-side `alert_type=corporate_event` filter and an opaque continuation cursor, so corporate events cannot be hidden behind the first page of general trigger history.
- `GET /api/v1/alerts/triggers` exposes typed, bounded `impact_context` / `event_context` projections. Account identifiers, quantities, market values, raw matched items, and raw corporate-event diagnostics are not returned.
- The backend derives impact grade from rule `severity` with `rule_severity` provenance. Missing rule metadata yields `unclassified`; the Web client does not infer grade from event category.
- The Web create/edit form round-trips `event_categories`, `lookback_hours`, and `min_items`.

See the Chinese [alerts.md](alerts.md) for full P0–P8 contracts, storage, cooldown, and Market Light details.

## Event-triggered deep analysis and contextual actions (issues #129 / #152)

### Master switches (all default off / safe)

| Key | Default | Meaning |
| --- | --- | --- |
| `EVENT_TRIGGERED_ANALYSIS_ENABLED` | `false` | Master switch for enqueueing deep analysis after opted-in alert triggers |
| `EVENT_TRIGGER_COOLDOWN_MINUTES` | `180` | Per rule+symbol debounce window |
| `EVENT_TRIGGER_DEFAULT_PIPELINE` | `standard` | Maps to task-queue report type (`standard`/`detailed` → `detailed`, `simple` → `simple`) |
| `EVENT_TRIGGER_MAX_PER_HOUR` | `5` | Process-local hourly budget (`0` disables) |
| `EVENT_TRIGGER_MAX_PER_DAY` | `20` | Process-local daily budget (`0` disables) |

Rules must also set `notification_policy.auto_analysis=true`. Eligible alert types:
`corporate_event`, `volume_spike`, `price_change_percent`.

Analysis is enqueued through `AnalysisSubmissionService` (async task queue). The alert
hot path never runs a full analysis inline.
Only tasks accepted by the queue consume debounce and hourly/daily budget slots;
duplicate, empty, and failed enqueue attempts release their provisional reservations.
Rule values, NL-compiled numeric values, and persisted trigger values reject `NaN`,
`+Inf`, and `-Inf`.

### Contextual suggested actions

On real triggers the worker attaches a bounded `suggested_action` (and optional
`auto_analysis` status) to diagnostics. Public API projection follows the #957 event
alert surface: no raw portfolio quantities/account IDs; deep links are in-app paths
plus optional http(s) source URLs only.
When the impact conclusion is absent, the Web UI explicitly shows “Not evaluated”
and never presents the missing state as a pass.

Quiet hours for alert **delivery** continue to use `NOTIFICATION_QUIET_HOURS` /
`NOTIFICATION_TIMEZONE` on the notification alert route.

### NL rule compiler (C5 / #1133)

`POST /api/v1/alerts/rules/compile-nl` compiles whitelist-bounded natural-language
phrases into Alert create payloads. Outcomes: `success` | `need_clarification` |
`rejected`. No arbitrary code execution. Corporate-event compiles always include
`event_categories`, `lookback_hours`, and `min_items` to prevent field-loss regressions.
