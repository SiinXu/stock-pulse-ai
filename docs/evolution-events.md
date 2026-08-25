# EvolutionEvent Store

**Status**: first bounded slice for issue [#1113](https://github.com/SiinXu/stock-pulse-ai/issues/1113) under epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)

**Chinese**: [evolution-events_CN.md](evolution-events_CN.md)

This document describes the append-only `EvolutionEvent` persistence and typed query foundation. It is **not** the privileged-operation security audit trail, not episode storage, not curator-grade ingest, and not the prediction-resolver process logger named `EvolutionEventSink`.

This slice does **not** close #1113. Automatic adapter mutations are not yet emitted (acceptance criterion 1 remains open). Issues #1113, #1107, #1091, #1106, and #1093 stay open.

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

There is no public HTTP, OpenAPI, Web, Desktop, or CLI query in this slice. There is no configuration flag.

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

## Privacy

Snapshots and `reason_refs` are JSON-safe and size-bounded. The schema rejects secrets, full system prompts, raw provider payloads, Agent Soul charter text, and non-finite numbers. Snapshot keys are canonicalized from camelCase, hyphen, and dotted names (`accessToken`, `system-prompt`, `provider.payload`) before matching the forbidden set. Do not persist API keys, tokens, `system_prompt`, `provider_payload`, or equivalent keys.

## Future producer policy (not wired here)

Later slices may append `actor=system` rows when a real adapter or overlay mutation applies (`applied=True`). Identity stubs, flag-off paths, and insufficient samples must not invent rows.

**Event-write failures must be logged and must not alter prediction `status` / `outcome_json` or adapter return values.** Future producers should catch `AgentEvolutionEventRepository.append` failures, log a sanitized warning, and continue. They must not add update/delete APIs, must not change adapter return values, and must not write prediction rows from the event path. Repository `append` itself stays fail-closed.

This policy is documented now. This slice does not hook `calibrate_confidence`, `apply_forecast_outcome_calibration`, BaseAgent, planner, router, tool-rank, route-bias, experimental skill flags, or replace resolver `EvolutionEventSink`. There is no extra service wrapper because no producer is wired yet.

## Out of scope

- Live adapter / overlay event emission (later #1113 slice; depends on this store)
- Tool-rank / route-bias / experimental-flag mutations (#1091 / #1106 / #1093 leftovers)
- Public query API, OpenAPI, Web, Desktop, CLI
- Config-registry keys or README homepage changes
- Reuse of `security_audit_events`

## Rollback

Revert this change set. `downgrade` drops `agent_evolution_events` only. Existing prediction actuals and append-only episodes stay in place.
