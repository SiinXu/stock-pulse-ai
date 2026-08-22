# Offline Financial Agent Evaluation Benchmark (V0)

**Status**: V0 offline phase for issue [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252)  
**Complements**: evaluation harness tracker [#215](https://github.com/SiinXu/stock-pulse-ai/issues/215); Phase A analysis panel [#617](https://github.com/SiinXu/stock-pulse-ai/issues/617) / [analysis-quality-panel.md](analysis-quality-panel.md)  
**Chinese**: [agent-eval-benchmark.md](agent-eval-benchmark.md)

## Purpose

Score **recorded agent runs** (not free-form LLM prose) on three measurable families:

| Family | What it checks |
| --- | --- |
| `financial_task_correctness` | Terminal success, decision signal, required dashboard fields, stock identity |
| `tool_usage_discipline` | Required/forbidden tools, stock-code scope, success/failure policy, call-count bounds |
| `uncertainty_honesty` | Risk warning, allowed confidence levels, gap language / non-trivial `data_limitations` |

All cases are **offline**: frozen `tests/fixtures/agent_runtime/**` transcripts, `ReplayLLMAdapter`, and deterministic local tool handlers. No network. No live LLM.

## Layout

| Path | Role |
| --- | --- |
| `tests/fixtures/agent_runtime/benchmark/manifest.json` | Scenario catalog (3–6 cases) |
| `tests/fixtures/agent_runtime/benchmark/scenarios/*.json` | Rubrics + `source_case` pointers into existing AR-01 fixtures |
| `tests/agent/benchmark/loader.py` | Manifest / baseline paths |
| `tests/agent/benchmark/metrics.py` | Deterministic check functions |
| `tests/agent/benchmark/runner.py` | Replay + score + report helpers |
| `tests/agent/benchmark/baselines/v0.json` | Committed baseline scores |
| `tests/agent/benchmark/test_offline_benchmark.py` | pytest entry (`@pytest.mark.benchmark`) |
| `scripts/run_agent_benchmark.py` | CLI runner (markdown + full JSON, including trajectory evaluations) |

Scenarios **reference** existing agent_runtime fixtures; they do **not** re-freeze or edit AR-01 baselines. The main AR-01 `manifest.json` is intentionally untouched.

## How to run

```bash
# Preferred local / maintainer path
python scripts/run_agent_benchmark.py

# Optional artifacts
python scripts/run_agent_benchmark.py \
  --json-out /tmp/agent-eval.json \
  --md-out /tmp/agent-eval.md

# pytest entry (excluded from the blocking offline gate)
python -m pytest -m benchmark tests/agent/benchmark -q
```

The blocking backend gate uses `pytest -m "not network and not benchmark"`, so this suite is **non-blocking** by design (V0).

A focused unmarked test in `tests/agent/test_agent_trajectory_eval.py` feeds a real `observe_case` tool log into `evaluate_agent_trajectory` and asserts `sample_size > 0` with a non-null `tool_selection_precision`, so that producer join stays visible to the blocking offline gate. The rest of the panel remains behind the `benchmark` marker.

The CLI itself is the explicit opt-in boundary. There is no runtime
`AGENT_TRAJECTORY_EVAL_ENABLED` setting: the production analysis path does not
invoke this evaluator, so advertising an environment gate would be inert and
would create a second configuration owner.

## Trajectory evaluation contract

Every `scenario_details[]` item in the full `--json-out` artifact contains a
versioned `trajectory_evaluation`. The committed baseline remains the compact
score-only view and is not expanded or rewritten by this addition.

The evaluator consumes the runner's already-redacted `tool_calls` fields:
`step`, `tool`, `arguments`, exact Boolean `success` / `cached`, optional exact
Boolean `timeout` / `guarded`, `duration`, and bounded guard metadata. Extra
redacted runner-log fields (for example `result_preview`) are projected away;
they do not reject an otherwise valid call and are not counted in
`rejected_call_count`. The benchmark supplies stable scenario task ID, source
run ID, replay execution ID, market and stock identity. Raw argument bodies
are not returned; only a bounded canonical SHA-256 fingerprint is retained.

| Metric | Deterministic meaning |
| --- | --- |
| `tool_selection_precision` | Calls whose tool is in the scenario's `required_tools`, divided by accepted calls |
| `tool_selection_recall` | Distinct required tools observed, divided by distinct required tools |
| `tool_selection_f1` | Harmonic mean of the two selection metrics |
| `tool_call_success_rate` | Successful accepted calls divided by accepted calls; never labeled selection quality |
| `productive_step_rate` | Successful, non-redundant calls divided by accepted calls |
| `redundancy_rate` / `retry_rate` | Causally later same-tool/same-argument calls after success / failure |
| `cache_hit_rate` | Accepted calls marked `cached=true` divided by accepted calls |
| `task_completion_rate` | Runs with an explicit successful terminal result divided by runs with a known result |

Selection metrics are `null` when a scenario has no expected-tool annotation.
A wrong-but-successful tool can increase call success but cannot increase
selection precision, recall or F1. Repeated failed retries have zero productive
step rate.

### Causality and ownership

Fingerprint history is isolated by `run_id` and `agent_id`. Causality is not
derived from list position. For each `(agent_id, tool, argument fingerprint)`
scope the evaluator first aggregates, over the whole run, the earliest observed
causal position and the earliest **successful** causal position, where position
is `dispatch_index` (preferred) or the runner `step`. A call is then:

- **redundant** when an identical call already succeeded at a strictly earlier
  position;
- **retry** when a strictly earlier identical attempt exists but none of those
  earlier attempts succeeded;
- **neither** otherwise.

Because the aggregate depends only on the multiset of `(position, success)`
pairs, the completion order of same-position (parallel) results can never move
a later dependent call between `retry` and `redundant`. Same-step parallel
calls, calls without a causal position, independent agents and independent runs
are never classified as post-success redundancy merely because their
completions appear later in a list.

### Evaluation identity

`evaluation_id` is a SHA-256 over the complete normalized result: rubric
fingerprint, path label, `as_of`, schema/engine/rubric versions, run
provenance, every evaluated step field (position, duration, cache state,
failure class, causal classification, timestamps), the full metric set, and the
rejection/truncation evidence. Any input difference that moves a metric or a
step field — including duration or `cached` state alone — therefore moves
`evaluation_id`. Output-side step truncation is a deterministic function of that
payload, so identical identities always serialize identically.

### Validation, bounds and provenance

- String Booleans, blank tools, non-finite/negative/huge durations, unknown
  path labels, non-JSON arguments and oversized/deep arguments are rejected,
  counted and never silently coerced.
- Evaluation is capped at 64 runs / 2,000 accepted source calls; returned step
  detail is capped at 1,000 and the strict-JSON result at 500,000 characters.
  Source and output truncation are explicit.
- Oversized sources are clipped, never fatal. An input far beyond the accepted
  call cap still returns a bounded result with `source_truncated=true`. The
  aggregate `rejected_call_count` saturates at 128,000 and sets
  `rejected_call_count_saturated=true` so the report never understates the
  rejection silently; per-run provenance keeps the exact unsaturated count.
- Each result carries deterministic evaluation/rubric fingerprints, input and
  engine schema versions, run/execution/task/agent/call IDs, stock/market where
  available, rejected counts, and capture/output truncation state.
- The current frozen fixtures do not record dispatch timestamps, token/tool
  budgets or per-child-agent identity. Those dimensions remain unavailable and
  are not inferred. Runner/core files are unchanged.

## Interpreting scores

- **Score** = `checks_passed / checks_total` across all scenarios and families.
- A scenario with `failed_checks` lists exact check ids and details.
- Baseline comparison prints **delta** and **DROP** flags when a score falls.

### V0 policy

| Event | Behaviour |
| --- | --- |
| Infrastructure / fixture load failure | Runner exits non-zero |
| Metric check failure on current HEAD | Shown in report; e2e pytest currently expects a perfect panel so regressions fail the optional `@benchmark` suite |
| Score drop vs committed baseline | **Visible** in the markdown report; default CLI exit code stays 0 |
| Hard-fail on drop | Only with `--strict-baseline` (opt-in) |

Score drops remain diagnostics unless `--strict-baseline` is used. Issue [#1092](https://github.com/SiinXu/stock-pulse-ai/issues/1092) adds a **blocking** CI job `agent-eval-gate` that runs `python scripts/run_agent_benchmark.py --strict-baseline` and enforces the offline prediction-verification suite with regression threshold **0.0** (deterministic frozen fixtures; do not relax the threshold to keep CI green). Anti-tests inject degradation and assert the gate fails.

## Refreshing the baseline

After an **intentional** runtime or fixture change that correctly changes scores:

```bash
python scripts/run_agent_benchmark.py --write-baseline
```

Commit `tests/agent/benchmark/baselines/v0.json` with an English changelog note explaining why the baseline moved. Do not rewrite the baseline to hide accidental regressions.

## Adding a scenario

1. Prefer reusing an existing offline fixture under `tests/fixtures/agent_runtime/` (financial or contract).
2. Add `tests/fixtures/agent_runtime/benchmark/scenarios/<id>.json` with:
   - `source_case` relative to `tests/fixtures/agent_runtime/`
   - `evaluation` object containing all three metric families
3. Register the case in `benchmark/manifest.json`.
4. Keep the panel small (prefer ≤6 scenarios in V0).
5. Run the runner twice and confirm identical JSON output.
6. If scores intentionally change, refresh the baseline as above.

## What this does **not** claim

- Market returns, ranking quality, or alpha
- Live vendor accuracy or network SLA
- Subjective prose quality as a merge gate
- Full agent self-improvement loops ([#215](https://github.com/SiinXu/stock-pulse-ai/issues/215))
- Live/runtime trajectory collection or oracle-grade selection labels beyond each scenario rubric ([#269](https://github.com/SiinXu/stock-pulse-ai/issues/269))
- Replacing the analysis-quality panel ([#617](https://github.com/SiinXu/stock-pulse-ai/issues/617)) — that scores **report** fixtures; this scores **agent run** behaviour

## Relation to other work

| Issue / surface | Relationship |
| --- | --- |
| #252 | This offline V0 slice |
| #269 | Trajectory metrics are integrated here; live tracking and richer labels remain open |
| #215 | Broader harness / feedback / self-improvement — out of scope |
| #617 / analysis quality panel | Complementary: report trust vs agent-run discipline |
| AR-01 agent_runtime fixtures | Read-only source transcripts for replay |
| Output-quality eval service | [agent-eval-dimensions_EN.md](agent-eval-dimensions_EN.md) scores single output artifacts (`agent_eval_service`) and is invoked by this canonical runner in a separate score bucket |
| CI merge queue / workflow ownership | Do not wire scheduled jobs into `.github/workflows/**` in this PR |


## Prediction verification offline suite (#1092 / #1107)

Integrated into the same runner as `prediction_verification_evaluation`:

| Path | Role |
| --- | --- |
| `tests/fixtures/prediction_eval/` | Frozen integrity fixtures (success, provider failure, missing data, overclaim, seeded miss lessons, tool discipline) |
| `src/services/prediction_eval_service.py` | Deterministic integrity + trajectory replay via owned `evaluate_agent_trajectory` |
| `tests/agent/benchmark/baselines/prediction_v0.json` | Committed baseline (threshold 0.0) |

Provider failure fixtures must resolve to `data_unavailable` and never a fabricated hit.

The committed prediction baseline freezes the exact case IDs and per-case check counts in addition to finite scores. Missing/extra cases, removed checks, malformed totals, NaN/Infinity, schema/engine drift, or any threshold other than `0.0` fail closed. When A5 `ClaimScorer` is installed, the same typed A1 fixtures are scored through it; an installed-but-broken scorer fails the gate instead of being silently skipped.
