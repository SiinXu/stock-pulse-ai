# Prediction Extraction (Structured Decision → Claims)

**Status**: A2 extractor (Issue [#1108](https://github.com/SiinXu/stock-pulse-ai/issues/1108); parent Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107); depends on A1 contract [#1101](https://github.com/SiinXu/stock-pulse-ai/issues/1101))

**Chinese**: [prediction-extraction.md](prediction-extraction.md)

## Purpose

Turn **structured** decision / dashboard fields into a `PredictionRecord` draft after a successful finalize path. Later stages can persist, resolve horizons, and score claims without treating report prose as a fake verifiable forecast.

## Product rules

| Rule | Extractor behavior |
| --- | --- |
| Structured fields only | Claims come from exact enums (`decision_type`, `action`) or explicit claim objects |
| Prose ≠ claim | `analysis_summary`, `operation_advice` text, `trend_prediction` copy, outlook paragraphs are **never** regex-parsed into direction |
| Missing structure | Emit `status=no_verifiable_claim` + `no_verifiable_reason` (for example `prose_only`) |
| Fail closed on analysis | Extraction exceptions are logged; analysis / history save still succeeds |
| Research / quality-ops | Not a returns guarantee product surface |
| Default off | `PREDICTION_EXTRACT_ENABLED=false` |

## Module map

| Path | Role |
| --- | --- |
| `src/schemas/prediction_record.py` | A1 contract (strict `PredictionRecord` / claims) |
| `src/core/prediction_resolve_after.py` | Horizon → UTC `resolve_after` (trading sessions; fail closed) |
| `src/services/prediction_extractor.py` | Pure extractor + feature-flagged finalize helper |
| `src/core/stages/persistence.py` | Post-history-save hook (best-effort, flag-gated) |
| `src/agent/orchestrator_parts/dashboard.py` | Post-agent-finalize hook (best-effort, flag-gated) |
| `tests/services/test_prediction_extractor.py` | Unit coverage including prose anti-examples |

## What becomes a claim

| Source | Claim |
| --- | --- |
| `action` exact token `buy`/`add`/`hold`/`watch`/`reduce`/`sell` | `direction` (`up` / `sideways` / `down`) |
| else `decision_type` exact token `buy`/`hold`/`sell` | `direction` |
| Explicit `prediction_claims` / `claims` / `forecast.claims` list | Validated A1 claim objects only |
| Explicit `return_bucket` / `level_break` / `vol_regime` objects | Matching claim types |

`avoid` / `alert` actions do not invent a price direction. Multi-word free text and Chinese advice phrases are rejected as enums.

## What never becomes a claim

- Narrative fields: `analysis_summary`, `short_term_outlook`, `operation_advice`, `trend_prediction`, markdown bodies, etc.
- Invented defaults when enums are missing
- Fabricated hits when providers / calendars fail (`resolve_after` fails closed → `status=error` with claims retained, not a fake pending due time)


## Extraction semantics (review-converged)

| Topic | Behavior |
| --- | --- |
| Confidence | Structured `confidence` / `confidence_level` only; **never** invent `0.5` |
| Horizon | Explicit structured horizon preferred; otherwise system policy default `5d` recorded as `horizon_source=policy_default:5d` in notes (not a model claim) |
| Agent mode | Direction requires explicit `action` or typed `prediction_claims`; `decision_type` alone is ignored (often orchestrator-synthesized) |
| Analysis mode | Exact `decision_type` buy/hold/sell still accepted with structured confidence |
| Dual hooks | Agent finalize (`ctx.meta`) and history-save (`result.prediction_extraction`) may both attach drafts; A3 persistence must dedupe |

## Feature flag

| Key | Default | Effect |
| --- | --- | --- |
| `PREDICTION_EXTRACT_ENABLED` | `false` | When off, hooks are no-ops. When on, successful finalize/history-save paths attach an in-memory extraction draft |

Drafts are attached to:

- `AnalysisResult.prediction_extraction` (pipeline history path)
- `AgentContext.meta["prediction_extraction"]` (agent finalize path)

Durable `agent_prediction` storage is **out of scope** for A2 (persistence issue).

## Rollout

1. Leave the flag off in production until the persistence + resolver path is ready.
2. Enable in non-prod to inspect draft `PredictionRecord` shapes.
3. Disable at any time; analysis continues unchanged.

## Related docs

- [Prediction Contract (EN)](prediction-contract_EN.md)
- Epic product rules in issue #1107
