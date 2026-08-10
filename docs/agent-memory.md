# Principal-scoped layered Agent memory

**Status**: foundation + lifecycle for [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) and [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198)

**Chinese**: [agent-memory_CN.md](agent-memory_CN.md)

## What exists

| Module | Role |
| --- | --- |
| `src/agent/memory_layers.py` | Strict typed records and projection types |
| `src/agent/memory_retrieval.py` | Structured episodic + **outcome-pattern** retrieval; optional hashing-vector re-rank |
| `src/agent/memory_vector.py` | Dependency-free coarse ranking |
| `src/agent/memory_governance.py` | Consent, retention, principal delete/clear, access audit |
| `src/agent/memory_isolation.py` | Untrusted-data isolation for any future prompt path |

Existing `AgentMemory` / `BaseAgent` calibration behavior is unchanged. **No production prompt injection** is wired yet.

## Honest layer naming

The second layer is **outcome-pattern memory**, not free-text "semantic knowledge":

- **Episodic**: recent point-in-time analysis observations for one stock.
- **Outcome patterns**: provenance-linked *correct* outcomes grouped by `(signal, horizon)`.
- Optional **vector re-ranking** only reorders those structured entries (CJK-aware hashing BoW).

Payload keys use `outcome_patterns`. A deprecated `semantic` alias remains for one compatibility window.

## Projection contract

- Every record has a `principal_id`; cross-principal, duplicate ids, and unowned rows are rejected.
- Input capped at 200; output limits positive and capped at 3.
- Canonical signals; finite/ranged numerics; all-or-none outcome provenance; 5/20-day horizons.
- UTC timestamps parsed and bounded; point-in-time `as_of` filtering and expiry.
- Free-form prose cannot enter projected string fields.

## Data governance (minimize by default)

| Control | Default | Behavior |
| --- | --- | --- |
| `LAYERED_MEMORY_COLLECTION_ENABLED` | `false` | Global collection master switch |
| Per-principal consent | absent | Required for collect / list / project / export |
| `LAYERED_MEMORY_RETENTION_DAYS` | `90` | Stamps `expires_at` when missing; `expire_due` drops past rows |
| Principal delete / clear | — | `delete` / `clear`; revoke clears by default |
| `LAYERED_MEMORY_AUDIT_ENABLED` | `true` | Append-only access audit |
| `LAYERED_MEMORY_VECTOR_ENABLED` | `false` | Coarse re-rank only |
| `LAYERED_MEMORY_MAX_RECORDS_PER_PRINCIPAL` | `200` | Hard panel cap |

Policy via `LayeredMemoryPolicy.from_config(config)` (constructor injection).

## Injection protection

- Structured fields reject free-form instruction text.
- Prompt-facing render must use `isolate_layered_memory_for_prompt()`.
- Adversarial tests in `tests/agent/test_agent_memory_isolation.py`.

## Remaining scope

- Authoritative principal assignment across API/bot/CLI/scheduled runs; legacy migration.
- Durable DB-backed lifecycle store; user-facing UI controls.
- Security-reviewed production prompt consumption.
- Preference-profile layer under #150.

Issues #250 and #198 stay open until production ownership and UX land.

## Rollback

Revert modules/tests/docs/config fields and changelog line. Collection default-off; no production hook.
