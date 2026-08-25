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
| `provenance_source`, `actor_id` | Server-stamped write provenance (`system_resolve` on resolve / `data_unavailable`; NULL on historical and still-pending rows). Not the transport `source` field. |
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

`outcome_json` is the PredictionOutcome actuals payload. Resolve and `data_unavailable` writes call `lock_prediction_outcome_actuals()` so user-opinion keys (`feedback_value`, `note`, `user_feedback`, transport `source`, …) cannot enter that JSON. Decision-signal user feedback remains a sidecar table and uses `lock_opinion_payload()` so market-actuals keys cannot ride along. Mixed payloads are rejected, not stripped and stored as facts. Feedback `note`/`reason_code` and episode free-text (`user_feedback`, `extra` values, `remedy`) also reject Soul-boundary markers, oversize, and illegal C0 controls at the write boundary (`src/schemas/memory_write_guard.py`, #1124 DAG-2). Resolve and episode append stamp server-owned `provenance_source=system_resolve` on the row (not inside `outcome_json`). Client-supplied provenance keys are rejected (`src/schemas/memory_provenance.py`, #1124 DAG-3). Do not `UPDATE` historical `resolved` prediction rows or append-only episodes to backfill stamps.

### Optional user feedback (#1105)

Opinion is a separate sidecar, not a rewrite of resolver actuals:

| Surface | Key | Enum | HTTP |
| --- | --- | --- | --- |
| Analysis run | canonical `run_id` | `useful` / `partial` / `wrong` / `harmful` | `GET`/`PUT /api/v1/agent/runs/{run_id}/feedback` |
| Prediction | stored `prediction_id` | `agree_hit` / `agree_miss` / `disagree_score` / `context_note` | `GET`/`PUT /api/v1/agent/predictions/{prediction_id}/feedback` |

- Latest-row upsert in `agent_run_feedback` / `agent_prediction_feedback`. Optional bounded `note`. Transport `source` is `web`/`api`.
- Auth matches other admin APIs: `ADMIN_AUTH_ENABLED=true` requires a valid admin session cookie and returns 401 otherwise.
- Unknown `prediction_id` is 404. Unknown run identity is 404 unless a landed token exists on `agent_predictions.run_id` or pipeline `analysis_history.query_id` (`AnalysisRepository.get_by_query_id`). Episode-only `run_id` values are not parents.
- Prediction PUT requires `status=resolved`; unresolved parents return 409 and do not persist. GET on an existing parent with no sidecar row returns 200 and `feedback_value=null`.
- Identity keys are path-only. Request bodies may not include `run_id` / `prediction_id`.
- Writes reuse `lock_opinion_payload`, `reject_memory_write_text`, and `apply_server_provenance` (`provenance_source=user_feedback`, optional `actor_id=local_admin`). Client provenance keys are rejected and not persisted.
- Feedback never writes `agent_predictions.outcome_json`, never `UPDATE`s append-only `agent_episodes`, and never changes prediction `status` / `resolved_at`. Missing feedback does not keep a row `pending`. Episode merge is a later read-time join; the sidecar is the system of record.
- This is not decision-signal `useful|not_useful` feedback, not #1096 eval-fixture curator grades (`pass|fail|partial|harmful` via `python scripts/label_curator_grades.py --fixture path.json`), and not a prediction query/diagnostics API. Web professional reports now expose optional run feedback (`useful|partial|wrong|harmful` plus a 1000-character note) keyed by `report.meta.queryId`. Prediction-feedback UI is later.

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
