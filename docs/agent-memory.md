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

Existing `AgentMemory` / `BaseAgent` numeric calibration behavior is unchanged. Layered `PrincipalMemoryLifecycle` has **no production prompt hook**. Historical Decision Reflection is a separate production inject path (below). Optional `AGENT_MEMORY_ENABLED` history inject is default-off; when enabled, `BaseAgent._build_memory_context` wraps history lines with `isolate_untrusted_memory_body` and canonicalizes `signal` to `buy|hold|sell` (see [Threat notes](#threat-notes)).

## Online evolution adapters (gated, default off)

Library-only slice in `src/agent/evolution/adapters.py`. Production `BaseAgent` calibration is unchanged and must not be double-multiplied.

| Control | Default | Behavior |
| --- | --- | --- |
| `AGENT_ONLINE_ADAPTERS_ENABLED` | `false` | Master gate. When false, adapters are identity: raw confidence, input tool order, the same route, and no `adapter_influence` key on `AgentContext.meta`. |
| `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES` | `30` | Minimum `AgentMemory` samples before confidence calibration applies. Below threshold: factor `1.0`, `applied=false`. |

Issue #1115 example `EVOLUTION_MIN_SAMPLES` is **not** an alias of `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES`. Enable this adapter gate only as **step 5** of the [prediction verification safe rollout](prediction-verification-rollout_EN.md), after extraction, a single resolver worker or explicit CLI, and miss/partial-only postmortem. Auto-promote stays hard off; there is no `EVOLUTION_AUTO_PROMOTE_SKILLS` env key.

When enabled and samples meet the adapter threshold, `calibrate_confidence` applies the stored `CalibrationResult.calibration_factor` from `AgentMemory.get_calibration` (and only when `calibrated` is true). AgentMemory already clamps `historical_accuracy / avg_confidence` to `0.5..1.5`, including a real `historical_accuracy=0.0`; the adapter must not re-derive that ratio with truthy fallbacks such as `accuracy or 0.5`. Confidence is then clamped to `[0,1]`. Sample source is existing `AGENT_MEMORY_ENABLED` / `AgentMemory`; this slice does not add a second store. Tool-effectiveness and route-preference are explicit identity stubs: they do not unlock denied ToolSurface tools and do not write `AGENT_ORCHESTRATOR_MODE`. Influence is recorded only on run-local `AgentContext.meta["adapter_influence"]` (not episodes).

### Forecast-outcome overlay (gated, default off)

When adapters are on, `apply_forecast_outcome_calibration` in `src/agent/evolution/outcome_ingest.py` may pull resolved `agent_predictions` for the current symbol/market through existing `list_by_symbol_market` (`limit <= 500`) and feed scored `hit` / `partial` / `miss` rows that have a finite confidence in `[0, 1]` into the gated adapter. Numeric accuracy uses `OUTCOME_NUMERIC_SCORE` (`hit=1.0`, `partial=0.5`, `miss=0.0`).

- Flag off or missing `stock_code`: identity, and the overlay does not query the store. When adapters are off, `adapter_influence` is not written.
- `N < AGENT_ONLINE_ADAPTERS_MIN_SAMPLES`: identity (`applied=false`, `reason=insufficient_samples`).
- `N >=` threshold: forecast stats only. This slice does **not** blend `AgentMemory` / backtest stats with live forecast outcomes.
- `data_unavailable`, unlabeled rows, invalid confidence, forward-return sidecar buckets (`1d_up` / …), and store failures are not samples and never fabricate hits.
- Influence remains `AgentContext.meta["adapter_influence"]` only. `BaseAgent`, Soul, ToolSurface, episodes, prediction HTTP, and tool/route stubs are unchanged.

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
| **Poisoning** | Production decision-memory admits only size-capped structured completed outcomes with `signal_id` and wraps the prompt block as untrusted data. Layered projected fields reject free-form prose. Optional default-off `AGENT_MEMORY_ENABLED` BaseAgent history inject wraps data lines with `isolate_untrusted_memory_body` and stores a canonical `buy` / `hold` / `sell` signal (`normalize_decision_signal`); `operation_advice` prose is never copied into `signal`. Expected storage lookup failures (`RuntimeError`, `SQLAlchemyError`) skip inject instead of emitting unattested rows. Unexpected mapping errors are not swallowed. Numeric calibration is unchanged. | User notes and free-form feedback are opinions, not market facts. Prompt isolation still truncates on inject (analysis build stays fail-open). |
| **Actuals vs opinion** | System market actuals live on `decision_signal_outcomes` and `agent_predictions.outcome_json` (resolved rows are immutable). User feedback is a sidecar opinion table. DAG-1 locks fact versus opinion write keys in `src/schemas/memory_fact_opinion.py`: mixed payloads are **rejected** at prediction resolve, decision-signal outcome/feedback upsert, and `PUT /api/v1/decision-signals/{signal_id}/feedback`. Feedback cannot mutate PredictionOutcome actuals. Transport channel `source` (`web` / `api`) is **not** provenance. DAG-3 stamps server-owned `provenance_source` ∈ `system_resolve` / `user_feedback` / `operator` plus optional session `actor_id` (`local_admin` on feedback writes) in `src/schemas/memory_provenance.py`. Client-supplied provenance keys are **rejected**. Historical prediction/episode rows stay NULL; existing feedback rows may backfill `user_feedback`. | Optional `actor_id` is an admin/session identifier under `AUTH-05`, not multi-tenant authorization. Durable store / principal assignment remains [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118) / [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230). |
| **Soul spoof** | Soul/persona composition rejects Soul-boundary markers. User-writable memory text (`PUT .../feedback` `note`/`reason_code`, repository upsert, episode `user_feedback` / `extra` / `remedy`) **rejects** Soul-boundary markers, oversize, and illegal C0 controls; payloads are not stripped or truncated and stored. Existing caps remain: feedback note 1000, reason_code 64, episode strings 256 / remedy 300. Secret redaction is unchanged and is not a substitute for reject-on-write. | Prompt isolation still truncates on inject (analysis build stays fail-open). That is not the write contract. |
| **Tenant / actor** | Product is single-administrator (`AUTH-05`). Foundation `principal_id` rejection is in-process only. | Foundation principal tests are not production isolation. Optional `actor_id` is an admin/session identifier, not multi-tenant authorization. Cross-user isolation remains [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230) / [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118). |

Write-path illegal, oversized, or marker-injected payloads must be **rejected**, not truncated and stored as facts. Decision-memory **admission** stays fail-closed (nothing admitted → no inject); analysis **build** failure stays fail-open (skip inject, continue analysis). See [security baseline current gaps](security-baseline.md#current-gaps).

## Remaining scope

- Authoritative principal assignment across API/bot/CLI/scheduled runs; legacy migration.
- Durable DB-backed lifecycle store and user-facing UI controls: [#1118](https://github.com/SiinXu/stock-pulse-ai/issues/1118) (absorbs closed [#250](https://github.com/SiinXu/stock-pulse-ai/issues/250) and [#198](https://github.com/SiinXu/stock-pulse-ai/issues/198)).
- Security-reviewed production prompt consumption.
- Preference-profile layer: [#1117](https://github.com/SiinXu/stock-pulse-ai/issues/1117) (absorbs closed [#150](https://github.com/SiinXu/stock-pulse-ai/issues/150)).
- Memory provenance, fact/opinion isolation, and anti-poisoning baseline: [#1124](https://github.com/SiinXu/stock-pulse-ai/issues/1124). DAG-0 threat notes, DAG-1 fact/opinion lock, DAG-2 Soul/oversize write reject (`src/schemas/memory_write_guard.py`), and DAG-3 server-stamped provenance (`src/schemas/memory_provenance.py`) have landed. DAG-4 isolates default-off AgentMemory prompt inject (`src/agent/agents/base_agent.py` / `src/agent/memory.py`) as untrusted data with canonical `buy` / `hold` / `sell` signals. Do not fold in #1118 store/UX, #1119 forgetting, or #1105 product feedback APIs. Keep the issue open until maintainers confirm every acceptance item.

Do not reopen #250, #198, or #150.

## Rollback

Revert modules/tests/docs/config fields and changelog line. Collection default-off; no production hook.

## Related: error-pattern encyclopedia

Human-editable error-pattern cards clustered from reflection/post-mortem lessons: [agent-error-pattern-encyclopedia_EN.md](agent-error-pattern-encyclopedia_EN.md) (Issue #1138). Lessons are input; the encyclopedia is the aggregation layer. This is distinct from the outcome-pattern memory layer on this page.
