# EvolutionEvent Store

**Status**: first bounded slice for issue [#1113](https://github.com/SiinXu/stock-pulse-ai/issues/1113) under epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)

**Chinese**: [evolution-events_CN.md](evolution-events_CN.md)

This document describes the append-only `EvolutionEvent` persistence, typed repository query, and authenticated HTTP list. It is **not** the privileged-operation security audit trail, not episode storage, not curator-grade ingest, and not the prediction-resolver process logger named `EvolutionEventSink`.

This slice does **not** close #1113. Calibrate-apply emission is on main (`adapter.calibrate`, Refs #1106). Tool-rank, route-bias, experimental-flag producers, and Web UI remain open. Issues #1113, #1107, #1091, #1106, and #1093 stay open.

## Purpose

Persist inspectable records of automatic evolution so later producers can answer: what changed, why, and what the before/after snapshots were.

| Field | Contract |
| --- | --- |
| `event_id` | Immutable unique id generated at append time |
| `occurred_at` | Timezone-aware UTC timestamp (stored as UTC-naive datetime) |
| `event_type` | Nonempty exact type string (`adapter.confidence_calibration`, later mutation kinds) |
| `actor` | Allowlist: `system` \| `user` \| `operator` |
| `reason_refs` | Structured `{prediction_ids, run_ids}` only. Empty lists are allowed: the store does not invent correlation ids. Later automatic producers must fill known ids; absence is not a fabricated mutation. |
| `before` / `after` | JSON-safe bounded snapshot objects. `before` must differ from `after` after bounding. Identical or both-empty snapshots are rejected because this log audits actual mutations, not no-ops. |

## Modules

| Path | Role |
| --- | --- |
| `src/schemas/evolution_event.py` | Strict create/query contracts and payload bounds |
| `src/repositories/agent_evolution_event_tables.py` | SQLAlchemy table projection |
| `src/repositories/agent_evolution_event_repo.py` | Append and inclusive UTC time/type query only |
| `src/migrations/versions/v202608250003_agent_evolution_event_schema.py` | Table, indexes, append-only UPDATE/DELETE triggers |
| `src/services/evolution_event_query.py` | Thin read-only wrapper around `list_events` for HTTP |
| `src/api/v1/endpoints/evolution_events.py` | Authenticated `GET /api/v1/agent/evolution-events` |
| `src/api/v1/schemas/evolution_events.py` | HTTP `{items, limit, returned}` list response |

There is no configuration flag. There is still no Web, Desktop, or CLI query. The HTTP list does not append events.

## Append-only database boundary

`agent_evolution_events` is created only by the ordered migration runner (after `202608250002_agent_curator_grade_schema`). SQLite triggers abort `UPDATE` and `DELETE` of historical rows. Downgrade drops this table, its indexes, and its triggers only. Episodes, predictions, curator grades, security-audit events, and resolver process logs are untouched.

## Query

`AgentEvolutionEventRepository.list_events`:

- Inclusive UTC `occurred_from` / `occurred_to` (timezone-aware required; `from > to` fails closed)
- Optional **exact** `event_type`. Only `event_type=None` omits the filter. Blank or whitespace fails closed so a malformed filter cannot silently broaden results.
- Bounded `limit` (default 100, maximum 200)
- Deterministic order: `occurred_at ASC`, then `id ASC`
- No matching rows return an empty list, not an error

Naive timestamps and invalid limits are rejected.

## HTTP list

`GET /api/v1/agent/evolution-events` is the public read path. It uses the same window, exact-type, and limit contract as the repository:

- Required timezone-aware `occurred_from` and `occurred_to` (inclusive). Naive timestamps and `from > to` return `400 validation_error`.
- Optional exact `event_type`. Omitting the parameter skips the filter. Blank or whitespace returns `400` so a malformed filter cannot silently list every row.
- Optional `limit` (default 100, maximum 200). `0` or `201` return `400`.
- Extra query keys are rejected (`422`).
- Empty windows return `200` with `items: []`. Response shape is `{items, limit, returned}` with no total count.
- Authentication matches other agent reads (`AdminSessionCookie`). When `ADMIN_AUTH_ENABLED=true`, missing or invalid session returns `401`. When auth is off, local reads are allowed. This path is not in `EXEMPT_PATHS` and is not the security-audit 403-when-auth-disabled rule.
- The route is GET-only. It does not call `append`.

## Privacy

Snapshots and `reason_refs` are JSON-safe and size-bounded. The schema rejects secrets, full system prompts, raw provider payloads, Agent Soul charter text, and non-finite numbers. Snapshot keys are canonicalized from camelCase, hyphen, and dotted names (`accessToken`, `system-prompt`, `provider.payload`) before matching the forbidden set. Do not persist API keys, tokens, `system_prompt`, `provider_payload`, or equivalent keys.

## Producer policy

Gated confidence calibration appends one `actor=system` `adapter.calibrate` row when a factor actually applies (Refs #1106). Identity stubs, flag-off paths, and insufficient samples must not invent rows. Episode forget/consolidate already write metadata-only events in the same delete transaction.

**Event-write failures must be logged and must not alter prediction `status` / `outcome_json` or adapter return values.** Producers catch append failures, log a sanitized warning, and continue. They must not add update/delete APIs, must not change adapter return values, and must not write prediction rows from the event path. Repository `append` itself stays fail-closed. The HTTP list is read-only and does not emit.

Tool-rank, route-bias, experimental skill flags, and Web UI remain later leftovers. This HTTP slice does not replace resolver `EvolutionEventSink`.

## Out of scope

- Tool-rank / route-bias / experimental-flag mutations (#1091 / #1106 / #1093 leftovers)
- Web, Desktop, or CLI query UI
- Config-registry keys or README homepage changes
- Reuse of `security_audit_events`
- POST / PATCH / DELETE EvolutionEvent HTTP

## Rollback

Revert the HTTP-list change set. No migration. Existing `agent_evolution_events` rows stay in place.
