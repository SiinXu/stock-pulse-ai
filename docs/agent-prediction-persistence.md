# Agent Prediction Persistence

**Status**: A3 persistence schema (Issue [#1112](https://github.com/SiinXu/stock-pulse-ai/issues/1112); parent Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107))

**English**: this document. Contract-only schema lives under Issue #1101.

## Purpose

Durable storage for structured forecast verification:

- Efficient due scans: `(status, resolve_after)`
- Symbol history: `(symbol, market, created_at)`
- Run linkage: `run_id`
- One-shot resolve transitions under concurrency

This slice is **schema + repository CAS** only. It does not extract claims, fetch actuals, score hits/misses, or mutate Agent Soul / ToolSurface.

## Product rules (Epic #1107)

| Rule | Persistence implication |
| --- | --- |
| System-driven loop | Rows carry `status` / `resolve_after` / leases for background resolvers |
| No Soul / ToolSurface mutation | Store `model_meta_json` as provenance only |
| Research / quality-ops framing | No guaranteed-return product surface |
| Non-parseable prose ≠ claim | Empty claims are accepted only as `no_verifiable_claim` with an explicit reason; do not invent claims at write time |
| Provider failure never fabricates hit | Use `data_unavailable` and retry; never write a fake hit/miss |

## Schema location

| Path | Role |
| --- | --- |
| `src/migrations/versions/v202608130001_agent_prediction_schema.py` | Additive table, indexes, resolved immutability trigger, downgrade |
| `src/repositories/agent_prediction_tables.py` | SQLAlchemy table projection |
| `src/repositories/agent_prediction_repo.py` | Insert / due list / claim / resolve CAS |
| `src/schemas/agent_prediction.py` | Status constants and detached record types |
| `tests/repositories/test_agent_prediction_repo.py` | Real SQLite coverage including concurrent writes |

Migration id: `202608130001_agent_prediction_schema`.

## Table: `agent_predictions`

| Column | Notes |
| --- | --- |
| `prediction_id` | Primary key (`VARCHAR(128)`, aligned with A1 `PredictionRecord`) |
| `run_id` | Analysis / agent run linkage (`VARCHAR(128)`) |
| `symbol`, `market` | Instrument identity for history queries; **`market` is normalized to lowercase** on write |
| `as_of` | A1 forecast base date used by ActualsFetcher/resolver grouping |
| `horizon` | A1 horizon token (`1d`, `3d`, `5d`, `10d`, or `20d`) |
| `resolve_after` | UTC-naive datetime used by due scans |
| `status` | See state machine below |
| `lease_owner`, `lease_token`, `lease_expires_at` | Resolver claim lease |
| `claims_json` | Typed claims array (JSON text) |
| `outcome_json` | Score / label payload after resolution attempts |
| `model_meta_json` | Optional provenance (mode, soul_version, skill ids) |
| `source_decision_id`, `no_verifiable_reason`, `notes` | A1 decision linkage, explicit non-verifiable reason, and bounded research notes |
| `attempts` | Claim/resolve attempt counter |
| `created_at`, `updated_at`, `resolved_at` | Timestamps |

### Indexes

- `ix_agent_prediction_status_resolve_after` — due scans
- `ix_agent_prediction_symbol_market_created` — per-instrument history
- `ix_agent_prediction_run_id` — run linkage
- `ix_agent_prediction_lease_expires_at` — expired lease reclaim

### State machine

```text
pending ──claim──► resolving ──success──► resolved (terminal, immutable)
                      │
                      └──provider fail──► data_unavailable ──requeue──► pending
```

Also accepted in the CHECK constraint for forward compatibility with the A1 contract: `expired`, `error`, `no_verifiable_claim`.

`resolved` rows cannot be updated (SQLite trigger + repository CAS `WHERE status IN ('pending','resolving')`).

### Fact versus opinion (#1124 DAG-1)

`outcome_json` is the PredictionOutcome actuals payload. Resolve and `data_unavailable` writes call `lock_prediction_outcome_actuals()` so user-opinion keys (`feedback_value`, `note`, `user_feedback`, transport `source`, …) cannot enter that JSON. Decision-signal user feedback remains a sidecar table and uses `lock_opinion_payload()` so market-actuals keys cannot ride along. Mixed payloads are rejected, not stripped and stored as facts. Feedback `note`/`reason_code` and episode free-text (`user_feedback`, `extra` values, `remedy`) also reject Soul-boundary markers, oversize, and illegal C0 controls at the write boundary (`src/schemas/memory_write_guard.py`, #1124 DAG-2). This slice does not add #1105 product feedback APIs or server-stamped provenance.

## Concurrency

- Insert validates the real A1 `PredictionClaim`, horizon, status/claim invariants, model metadata, `as_of`, and provenance before using primary-key uniqueness; collisions return the existing row without overwrite. CHECK / NOT NULL failures are **not** treated as collisions, and malformed JSON is never read as empty claims.
- Claim and resolve use conditional `UPDATE ... WHERE` and require `rowcount == 1`. Future rows cannot be claimed.
- Concurrent resolvers of the same id: exactly one applies; losers observe the winner’s terminal outcome.
- After `claim_for_resolve`, only the unexpired lease holder can call `resolve` or `mark_data_unavailable`; `mark_data_unavailable` always requires the token. A direct tokenless resolve is accepted only while the row is still `pending`.
- Provider-failure diagnostics cannot override the canonical `data_unavailable` label or add score/hit/miss fields. `requeue_pending` clears the stale unavailable outcome before a later claim.

## Rollback

1. Stop prediction writers / resolvers.
2. Deploy code without the repository consumers if needed.
3. Either restore a pre-migration SQLite backup, or run the module `downgrade` helper (drops `agent_predictions` and its indexes/trigger). Do not delete `schema_migrations` rows by hand without a coordinated restore.

The ordered runner is forward-only at process startup; `downgrade` is an explicit operator path for this additive table.
