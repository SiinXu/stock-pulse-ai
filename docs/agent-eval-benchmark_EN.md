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
Boolean `timeout` / `guarded`, `duration`, and bounded guard metadata. The
benchmark supplies stable scenario task ID, source run ID, replay execution ID,
market and stock identity. Raw argument bodies are not returned; only a bounded
canonical SHA-256 fingerprint is retained.

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

Fingerprint history is isolated by `run_id` and `agent_id`. A duplicate is
classified only when its `dispatch_index` (preferred) or runner `step` is
strictly greater than the previous matching call. Same-step parallel calls,
calls without causal order, independent agents and independent runs are never
classified as post-success redundancy merely because their completions appear
later in a list.

### Validation, bounds and provenance

- String Booleans, blank tools, non-finite/negative/huge durations, unknown
  path labels, non-JSON arguments and oversized/deep arguments are rejected,
  counted and never silently coerced.
- Evaluation is capped at 64 runs / 2,000 accepted source calls; returned step
  detail is capped at 1,000 and the strict-JSON result at 500,000 characters.
  Source and output truncation are explicit.
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

Score drops are diagnostics for maintainers, not a required CI gate in V0. Scheduled workflow wiring under `.github/workflows/**` is intentionally a **follow-up** (owned by separate CI work).

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
