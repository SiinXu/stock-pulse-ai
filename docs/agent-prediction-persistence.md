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
| Non-parseable prose ≠ claim | Empty or non-verifiable claims are allowed; do not invent claims at write time |
| Provider failure never fabricates hit | Use `data_unavailable` and retry; never write a fake hit/miss |

## Schema location

| Path | Role |
| --- | --- |
| `src/migrations/versions/v202608120001_agent_prediction_schema.py` | Additive table, indexes, resolved immutability trigger, downgrade |
| `src/repositories/agent_prediction_tables.py` | SQLAlchemy table projection |
| `src/repositories/agent_prediction_repo.py` | Insert / due list / claim / resolve CAS |
| `src/schemas/agent_prediction.py` | Status constants and detached record types |
| `tests/repositories/test_agent_prediction_repo.py` | Real SQLite coverage including concurrent writes |

Migration id: `202608120001_agent_prediction_schema`.

## Table: `agent_predictions`

| Column | Notes |
| --- | --- |
| `prediction_id` | Primary key (`VARCHAR(128)`, aligned with A1 `PredictionRecord`) |
| `run_id` | Analysis / agent run linkage (`VARCHAR(128)`) |
| `symbol`, `market` | Instrument identity for history queries; **`market` is normalized to lowercase** on write |
| `horizon` | Horizon token or policy label |
| `resolve_after` | UTC-naive datetime used by due scans |
| `status` | See state machine below |
| `lease_owner`, `lease_token`, `lease_expires_at` | Resolver claim lease |
| `claims_json` | Typed claims array (JSON text) |
| `outcome_json` | Score / label payload after resolution attempts |
| `model_meta_json` | Optional provenance (mode, soul_version, skill ids) |
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

## Concurrency

- Insert uses primary-key uniqueness; collisions return the existing row without overwrite. CHECK / NOT NULL failures are **not** treated as collisions.
- Claim and resolve use conditional `UPDATE ... WHERE` and require `rowcount == 1`.
- Concurrent resolvers of the same id: exactly one applies; losers observe the winner’s terminal outcome.
- After `claim_for_resolve`, the worker **should always pass** `expected_lease_token` into `resolve` / `mark_data_unavailable` so only the lease holder can finish the transition. Omitting the token still enforces terminal CAS but does not bind the writer to a lease.

## Rollback

1. Stop prediction writers / resolvers.
2. Deploy code without the repository consumers if needed.
3. Either restore a pre-migration SQLite backup, or run the module `downgrade` helper (drops `agent_predictions` and its indexes/trigger). Do not delete `schema_migrations` rows by hand without a coordinated restore.

The ordered runner is forward-only at process startup; `downgrade` is an explicit operator path for this additive table.
