# Prediction Extraction (Structured Decision → Claims)

**Status**: A2 extractor + A3 persist (Issues [#1108](https://github.com/SiinXu/stock-pulse-ai/issues/1108) / [#1101](https://github.com/SiinXu/stock-pulse-ai/issues/1101); parent Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107))

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
| `src/services/prediction_persist.py` | Persist verifiable pending drafts via `insert_pending` |
| `src/core/stages/persistence.py` | Post-history-save hook (best-effort, flag-gated) |
| `src/agent/orchestrator_parts/dashboard.py` | Post-agent-finalize hook (best-effort, flag-gated) |
| `tests/services/test_prediction_extractor.py` | Unit coverage including prose anti-examples |
| `tests/services/test_prediction_persist.py` | Agent/pipeline persist, dual-hook one-row identity, attached id equals stored PK, no overwrite after resolve |

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
| Provenance | Pipeline extraction reads the parser-preserved `AnalysisResult.prediction_source`; normalized display defaults such as `action=hold` are ignored |
| Horizon | Explicit structured horizon preferred; otherwise system policy default `5d` recorded as `horizon_source=policy_default:5d` in notes (not a model claim) |
| Agent mode | Direction requires explicit `action` or typed `prediction_claims`; `decision_type` alone is ignored (often orchestrator-synthesized) |
| Analysis mode | Exact `decision_type` buy/hold/sell still accepted with structured confidence |
| Mixed valid/invalid claims | The draft is `status=error` and is not scoreable; invalid declared claims are never silently dropped into a partial pending record |
| Dual hooks | Agent finalize and history-save share one canonical `run_id` (pipeline `query_id` threaded into agent context, else chat `session_id`). One user-visible analysis stores one pending row per symbol. Persist stamps `prediction_id_for_run(run_id, symbol)` onto the attached draft so `prediction_extraction.record.prediction_id` equals the stored primary key. |

## Feature flag

| Key | Default | Effect |
| --- | --- | --- |
| `PREDICTION_EXTRACT_ENABLED` | `false` | When off, hooks are no-ops. When on, successful finalize/history-save paths attach an in-memory extraction draft and persist verifiable pending rows to `agent_predictions` |

Drafts are attached to:

- `AnalysisResult.prediction_extraction` (pipeline history path)
- `AgentContext.meta["prediction_extraction"]` (agent finalize path)

Verifiable pending drafts are persisted through `AgentPredictionRepository.insert_pending`. The durable `prediction_id` is length-prefixed (`pred-{len(run_id)}:{run_id}:{symbol}`, or a hash when that encoding exceeds 128 characters) so hyphenated run/symbol pairs cannot collide. Re-finalizing the same run/symbol reuses the existing row (primary-key conflict, no overwrite, including after resolve). Persistence failures are logged and never fail analysis. Callers attach `prediction_extraction` after persist so the in-memory draft carries the stored key.

## Rollout

Safe operator order for the whole verification loop is in [Prediction verification safe rollout](prediction-verification-rollout_EN.md) (Issue #1115). Extraction is **step 2** of that sequence:

1. Leave every verification-loop flag at its default off.
2. Enable `PREDICTION_EXTRACT_ENABLED=true` and confirm analysis / history save still succeed (extraction failures never fail analysis).
3. Only then enable the resolver on exactly one scheduled worker **or** invoke `python -m src.services.prediction_resolver` explicitly.
4. Enable miss/partial-only postmortem with `AGENT_POSTMORTEM_SKIP_CLEAN_HITS=true`.
5. Enable gated adapters only after `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES`.
6. Auto-promote stays hard off.

Disable `PREDICTION_EXTRACT_ENABLED` at any time; analysis continues unchanged. Issue example `PREDICTION_VERIFY_ENABLED` is **not** an alias of this key.

## Related docs

- [Prediction Contract (EN)](prediction-contract_EN.md)
- [Prediction verification safe rollout](prediction-verification-rollout_EN.md)
- Epic product rules in issue #1107
