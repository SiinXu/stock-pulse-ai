# Agent Reflection and Forecast Post-mortem

This document covers the **run-local reflection contract** (Issue #1089) and the
**resolved-forecast post-mortem** (Issue #1103) under Epic #1107.

## Product rules

- System-driven quality ops only — not a guaranteed-returns product.
- Reflection and post-mortem **never** rewrite Agent Soul charter/version/hash.
- Reflection and post-mortem **never** expand or relax ToolSurface denials.
- Non-parseable prose does not become a fake verifiable claim.
- Provider / actuals failure is `data_unavailable` (retry later), never a
  fabricated hit.
- LLM budget exhaustion is an **explicit** `budget_skipped` / `terminate_reason=budget`
  outcome, aligned with the Critic's `record_critic_budget_skip` fail-soft style.
  There is no silent “pretend success” degradation.

## Shared lesson taxonomy

`src/agent/evolution/lessons.py` owns the typed kinds used by both paths:

| Kind | Typical trigger |
| --- | --- |
| `evidence_gap` | Missing material evidence |
| `overclaim` | Prose treated as a checkable claim |
| `overconfidence` | High confidence miss |
| `tool_failure` | Tool error / denial treated as inventable data |
| `risk_omission` | Downside / invalidation omitted |
| `format_violation` | Schema-invalid structured output |
| `regime_shift` | Regime filters flipped after the forecast |
| `horizon_mismatch` | Claim horizon vs resolve calendar mismatch |
| `other` | Residual typed bucket (still not free prose) |

`ReflectionLesson` and `ReflectionResult` are the shared serialization shapes.
Optional `strategy_note` is a human-facing note only — never a Soul edit.

## Run-local reflection (#1089)

Entry: `src/agent/evolution/reflection.py` (`run_reflection_loop`, etc.).

1. Default **off** (`AGENT_REFLECTION_ENABLED=false`).
2. When enabled, emits typed lessons onto `ctx.meta["reflection_result"]`.
3. Optional LLM critique limited by `AGENT_REFLECTION_LLM_BUDGET` (default 1, max 64).
4. When `ctx.meta["mode_budget_account"]` is present, each reflection LLM call
   also consumes one run-account turn. The production Chat/single-agent loop
   persists that account on the executor so end-of-run planning reflection can
   find it. After optional reflection, the planning product path rewrites
   `AgentResult.budget_snapshot` (and `planning_metadata["mode_budget"]`) from
   that live account so diagnostics include the extra turn. A run-account skip
   uses the existing `budget_skipped` / `terminate_reason=budget` vocabulary and
   does not increment past `max_llm_turns`. These calls use `llm_complete`, not
   `run_agent_loop`, so they are not double-counted. End-of-run reflection does
   not reserve a Decision turn; optional in-loop step-critique enrichment does.
   The run LLM-turn cap is `AGENT_MODE_BUDGET_MAX_LLM_TURNS` (there is no
   `AGENT_MAX_RUN_LLM_CALLS` key).
5. Optional in-run revise limited by `AGENT_REFLECTION_MAX_REVISE` (default 1).
6. Soul / ToolSurface identity is snapshotted and re-asserted after the path.
7. An existing `ctx.meta["critic_trace"]` seeds typed lesson kinds
   (`evidence_gap`, `overconfidence`, `tool_failure`, `risk_omission`) so a
   Critic verdict produces lessons even when no reflection LLM runs. Seeding
   only adds kinds that are not already present; it never opens a second
   critic voice.

### Production call sites

`src.agent.evolution.multilevel.attach_end_of_run_reflection` is the single
attach point. All three Native call sites delegate to it, so there is no
parallel copy:

| Call site | Where | Trigger |
| --- | --- | --- |
| Planning product path (opt-in) | `src/agent/planning/product.py` | `AGENT_PLANNING_ENABLED=true` |
| Classic Native Single | `src/agent/executor_parts/run.py` | default `AGENT_ARCH=single` with planning off |
| Native Multi dashboard | `src/agent/orchestrator_parts/chat.py` `run()` | `AGENT_ARCH=multi` |

Contract shared by all three:

- Runs **after** the primary analysis/decision. A reflection failure never
  changes `success`, dashboard content, or Decision fields — the failure is
  recorded as `status=error` in metadata instead.
- The typed result is written to `AgentResult.planning_metadata["reflection_result"]`
  (no new result field) and, on Native Multi, mirrored onto
  `ctx.meta["reflection_result"]`. `OrchestratorResult.planning_metadata`
  carries it through `_public_agent_result`.
- Chat is excluded. `AgentOrchestrator.chat` never reaches the attach point, and
  `is_reflection_enabled` also rejects a projected `response_mode == "chat"`.
  There is no `AGENT_REFLECTION_IN_CHAT` env key.
- No `revise_fn` is passed on Native production paths. Critic revision remains
  the apply-within-run mechanism; `AGENT_REFLECTION_MAX_REVISE` stays a hard cap
  for explicit library callers.
- Input is a bounded, redacted projection: at most 64 tool rows, 12 opinions,
  10 risk flags, and a Critic trace reduced to `verdict` / `validation_status`
  plus 8 `reasons` / `missing_evidence` entries. System prompts, Soul charter
  text, raw completions and deep payloads are never sent.
- Nothing is persisted. No episode row, decision-memory admission, prediction
  actual, or Soul marker is written here — persistence stays with #1090.

### Observability

When agent observability is enabled the attach point emits two bounded events
of type `agent.reflect`: `reflect_start` (`llm_budget_total`) and `reflect_end`
(`terminate_reason`, `status`, `lesson_count`, `llm_budget_consumed`,
`llm_budget_remaining`). Lesson text, remedies and `strategy_note` never reach
observability. The disabled path emits nothing at all — there is no fake
successful `reflect_end`.

## Resolved-forecast post-mortem (#1103)

Library entry: `src/agent/evolution/postmortem.py` (`reflect_resolved_forecast`,
`run_postmortem_batch`). Production drain:
`src/services/prediction_resolver/postmortem_drain.py`.

1. Default **off** (`AGENT_POSTMORTEM_ENABLED=false`).
2. Input is an already-scored forecast. Persistence/actuals/scoring remain A1–A5.
3. Miss/partial produce typed lessons linked to `episode_id` / `prediction_id`.
4. Clean hits skip LLM when `AGENT_POSTMORTEM_SKIP_CLEAN_HITS=true` (default).
5. Batch LLM spend capped by `AGENT_POSTMORTEM_LLM_BUDGET` (default 8).
6. Budget exhaustion records `budget_skipped` (not silent success).
7. When a caller supplies a run `ctx` with `mode_budget_account`, post-mortem
   LLM calls charge that same account and refresh `ctx.meta["mode_budget"]`.
   Post-mortem is not an `AgentResult` path; callers that need a result snapshot
   must read the account or `ctx.meta["mode_budget"]`. Skip stays
   `budget_skipped`.
8. Production wire: `InMemoryPostmortemQueue` is injected when
   `AGENT_POSTMORTEM_ENABLED` is true. A **scheduled** drain also needs the
   resolver worker (`PREDICTION_RESOLVE_ENABLED`). The cron CLI
   (`python -m src.services.prediction_resolver`) drains after its tick even
   when that scheduler flag is off — an intentional operator gate. Drain runs
   after a non-overlap `tick()`, at most
   `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` jobs. Drain concurrency is
   hardcoded `2` (not an env key). The handler maps stored
   outcome/score/actuals (plus copied `run_id` / claims). It does not re-fetch
   market data or invent direction. Hits and `data_unavailable` are not
   enqueued. Lessons project through `record_reflection_lessons`: if
   `AGENT_EPISODE_LOG_ENABLED` and an episode exists for `run_id`, that
   `episode_id` is used; otherwise the process-local sidecar remains the record.
   A missing episode does not fail resolve. Drain/LLM/episode errors log and
   requeue; they do not roll back `resolved` rows or fabricate hits. Queue-depth
   HTTP remains out of scope (#1114 remainder).

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_REFLECTION_ENABLED` | `false` | Enable run-local reflection |
| `AGENT_REFLECTION_LLM_BUDGET` | `1` | Max LLM calls per reflection loop (0-64) |
| `AGENT_REFLECTION_MAX_REVISE` | `1` | Max in-run revise passes |
| `AGENT_POSTMORTEM_ENABLED` | `false` | Enable resolved-forecast post-mortem |
| `AGENT_POSTMORTEM_LLM_BUDGET` | `8` | Max LLM calls per resolution batch |
| `AGENT_POSTMORTEM_SKIP_CLEAN_HITS` | `true` | Skip post-mortem LLM on clean hits |
| `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` | `10` | Max postmortem jobs drained after a non-overlap tick |

Issue #1115 examples (`PREDICTION_POSTMORTEM_ENABLED`, `PREDICTION_POSTMORTEM_ON_HIT`, `PREDICTION_POSTMORTEM_CONCURRENCY`, `PREDICTION_POSTMORTEM_MAX_PER_TICK`) are **not aliases** of these keys. `PREDICTION_POSTMORTEM_CONCURRENCY` has no env surface; drain workers stay hardcoded `2`.

## Safe rollout

Operator order for the whole verification loop:

1. All verification-loop flags off.
2. Enable extraction and verify analysis remains healthy.
3. Enable the resolver on exactly one scheduled worker **or** invoke the cron CLI explicitly.
4. Enable miss/partial-only postmortem with `AGENT_POSTMORTEM_SKIP_CLEAN_HITS=true` (this step).
5. Enable gated adapters only after `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES`.
6. Auto-promote stays hard off.

Full mapping and deferrals: [Prediction verification safe rollout](prediction-verification-rollout_EN.md).

## Rollback

Set enable flags to `false` or remove them. No data migration required. Analysis continues.
