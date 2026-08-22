# Principal-scoped layered Agent memory

**Status**: layered foundation + lifecycle (no production layered-memory hook). Durable store/UX: [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118). Provenance/anti-poisoning: [#1124](https://github.com/SiinXu/stock-pulse-ai/issues/1124).

**Chinese**: [agent-memory_CN.md](agent-memory_CN.md)

## What exists

| Module | Role |
| --- | --- |
| `src/agent/memory_layers.py` | Strict typed records and projection types |
| `src/agent/memory_retrieval.py` | Structured episodic + **outcome-pattern** retrieval; optional hashing-vector re-rank |
| `src/agent/memory_vector.py` | Dependency-free coarse ranking |
| `src/agent/memory_governance.py` | Consent, retention, principal delete/clear, access audit |
| `src/agent/memory_isolation.py` | Untrusted-data isolation for any future prompt path |

Existing `AgentMemory` / `BaseAgent` calibration behavior is unchanged. Layered `PrincipalMemoryLifecycle` has **no production prompt hook**. Historical Decision Reflection is a separate production inject path (below). Optional `AGENT_MEMORY_ENABLED` calibration inject is default-off and is not wrapped by `isolate_untrusted_memory_body` (see [Threat notes](#threat-notes)).

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
- Prompt-facing render must use `isolate_layered_memory_for_prompt()` (or the shared
  `isolate_untrusted_memory_body()` helper for non-bundle text).
- Adversarial tests in `tests/agent/test_agent_memory_isolation.py`.

### Decision Memory reflection (#118)

Same-stock Historical Decision Reflection is a **separate production path** over
`DecisionSignal` + outcome stores (not `PrincipalMemoryLifecycle`). It still
must:

1. **Admit** only size-capped structured completed outcomes with `signal_id`
   provenance (`admit_decision_memory`); free-form signal reason text is excluded.
   Same-stock hit-rate and listed calls use the same lookback admitted set. Every
   renderer re-runs admission (the dataclass `admitted` flag is not authority),
   rejects non-finite numerics, and enforces the configured bounds and action enums.
2. **Isolate** the prompt block via `isolate_untrusted_memory_body` so history is
   non-authoritative data.
3. Remain **toggleable** (`DECISION_MEMORY_ENABLED` / per-request `use_memory`).

See `docs/decision-signals.md` §历史决策记忆注入.

<a id="threat-notes"></a>
## Threat notes (#1124)

Short Agent-safety baseline for shared/long-term memory. This is a scope map, not an exploit guide and not a memory product.

| Threat | Current contract | Gap |
| --- | --- | --- |
| **Poisoning** | Production decision-memory admits only size-capped structured completed outcomes with `signal_id` and wraps the prompt block as untrusted data. Layered projected fields reject free-form prose. | User notes and free-form feedback are opinions, not market facts. Optional `AGENT_MEMORY_ENABLED` calibration inject is default-off and currently unisolated. |
| **Actuals vs opinion** | System market actuals live on `decision_signal_outcomes` and `agent_predictions.outcome_json` (resolved rows are immutable). User feedback is a sidecar opinion table. DAG-1 locks fact versus opinion write keys in `src/schemas/memory_fact_opinion.py`: mixed payloads are **rejected** at prediction resolve, decision-signal outcome/feedback upsert, and `PUT /api/v1/decision-signals/{signal_id}/feedback`. Feedback cannot mutate PredictionOutcome actuals. | Transport channel `source` (`web` / `api`) is **not** provenance. Server-stamped `source` ∈ `system_resolve` / `user_feedback` / `operator` plus optional session `actor_id` are still required on persisted memory writes (DAG-3). |
| **Soul spoof** | Soul/persona composition rejects Soul-boundary markers. Feedback notes are size-capped and secret-redacted. | User-writable memory text does not yet reject Soul-boundary markers or marker-injected payloads. |
| **Tenant / actor** | Product is single-administrator (`AUTH-05`). Foundation `principal_id` rejection is in-process only. | Foundation principal tests are not production isolation. Optional `actor_id` is an admin/session identifier, not multi-tenant authorization. Cross-user isolation remains [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230) / [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118). |

Write-path illegal, oversized, or marker-injected payloads must be **rejected**, not truncated and stored as facts. Decision-memory **admission** stays fail-closed (nothing admitted → no inject); analysis **build** failure stays fail-open (skip inject, continue analysis). See [security baseline current gaps](security-baseline.md#current-gaps).

## Remaining scope

- Authoritative principal assignment across API/bot/CLI/scheduled runs; legacy migration.
- Durable DB-backed lifecycle store and user-facing UI controls: [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118) (absorbs closed [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) and [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198)).
- Security-reviewed production prompt consumption.
- Preference-profile layer: [#1117](https://github.com/SiinXu/stock-pulse-ai/issues/1117) (absorbs closed [#150](https://github.com/SiinXu/stock-pulse-ai/issues/150)).
- Memory provenance, fact/opinion isolation, and anti-poisoning baseline: [#1124](https://github.com/SiinXu/stock-pulse-ai/issues/1124). DAG-1 (this lock + tests) has landed. Remaining: DAG-2 Soul/oversize reject; DAG-3 server-stamped provenance. Do not fold in #1118 store/UX, #1119 forgetting, or #1105 product feedback APIs.

Do not reopen #250, #198, or #150.

## Rollback

Revert modules/tests/docs/config fields and changelog line. Collection default-off; no production hook.

## Related: error-pattern encyclopedia

Human-editable error-pattern cards clustered from reflection/post-mortem lessons: [agent-error-pattern-encyclopedia_EN.md](agent-error-pattern-encyclopedia_EN.md) (Issue #1138). Lessons are input; the encyclopedia is the aggregation layer. This is distinct from the outcome-pattern memory layer on this page.
