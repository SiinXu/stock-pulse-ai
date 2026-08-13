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
3. Optional LLM critique limited by `AGENT_REFLECTION_LLM_BUDGET` (default 1).
4. Optional in-run revise limited by `AGENT_REFLECTION_MAX_REVISE` (default 1).
5. Soul / ToolSurface identity is snapshotted and re-asserted after the path.

## Resolved-forecast post-mortem (#1103)

Entry: `src/agent/evolution/postmortem.py` (`reflect_resolved_forecast`, `run_postmortem_batch`).

1. Default **off** (`AGENT_POSTMORTEM_ENABLED=false`).
2. Input is an already-scored forecast. Persistence/actuals/scoring remain A1–A5.
3. Miss/partial produce typed lessons linked to `episode_id` / `prediction_id`.
4. Clean hits skip LLM when `AGENT_POSTMORTEM_SKIP_CLEAN_HITS=true` (default).
5. Batch LLM spend capped by `AGENT_POSTMORTEM_LLM_BUDGET` (default 8).
6. Budget exhaustion records `budget_skipped` (not silent success).

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_REFLECTION_ENABLED` | `false` | Enable run-local reflection |
| `AGENT_REFLECTION_LLM_BUDGET` | `1` | Max LLM calls per reflection loop |
| `AGENT_REFLECTION_MAX_REVISE` | `1` | Max in-run revise passes |
| `AGENT_POSTMORTEM_ENABLED` | `false` | Enable resolved-forecast post-mortem |
| `AGENT_POSTMORTEM_LLM_BUDGET` | `8` | Max LLM calls per resolution batch |
| `AGENT_POSTMORTEM_SKIP_CLEAN_HITS` | `true` | Skip post-mortem LLM on clean hits |

## Rollback

Set enable flags to `false` or remove them. No data migration required.
