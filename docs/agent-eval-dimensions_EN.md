# Financial Agent Output-Quality Evaluation Dimensions (Output-side V1)

**Status**: Output-quality slice of issue [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252); failure mining [#141](https://github.com/SiinXu/stock-pulse-ai/issues/141); harness slice of [#215](https://github.com/SiinXu/stock-pulse-ai/issues/215)

**Chinese**: [agent-eval-dimensions.md](agent-eval-dimensions.md)

**Integration**: the canonical offline runner in `tests/agent/benchmark` runs both runtime-structure checks and this single-output quality suite.

## Purpose

After changing prompts, tools, or models, answer with **offline-replayable** cases: did output quality improve or regress, and which failure modes dominate?

## Dimension table

| Dimension id | What it checks | Judge | Stability |
| --- | --- | --- | --- |
| `factuality` | Each numeric claim must exactly bind to a source fact by id, field path, value, unit, timestamp, and source id | **rule** | Prevents cross-field and percent/absolute borrowing |
| `tool_usage` | Required tools completed successfully with valid, authorized results; forbidden tools were not attempted | **rule** | Exact booleans only; a tool name alone never passes |
| `conclusion_consistency` | Evidence polarity must not contradict the final signal (e.g. all-bearish evidence vs `buy`) | **rule** | Stable; needs structured `evidence[].polarity\|sentiment` on the case |
| `boundary_honesty` | No overconfident advice when data is missing or tools failed | **rule** | Stable; context should mark `data_missing` / `failed_tools` |
| `language_format` | Required fields, forbidden phrases, object/JSON shape | **rule** | Stable |
| `explanation_clarity` | Subjective clarity of explanations | **llm** (optional external) | **Never mixed into the rule total**; offline default `skipped` unless the caller supplies `llm_judgements` |
| `risk_framing_quality` | Subjective risk-framing quality | **llm** (optional) | Same: separate `llm_score` only |

## Scoring

- **Rule score** = `passed / total` over all non-skipped rule checks.
- **LLM score** = only non-skipped `judge=llm` checks; reported separately from the rule score.
- **Failure mining** clusters by `(dimension, check_id)` with concrete case ids and sample details — not a single opaque total.
- Empty/malformed output, missing rubrics, non-finite numbers, and wrong types are explicit `invalid` failures; there are no vacuous passes.
- Candidate and baseline reports preserve separate rule/LLM deltas, per-dimension rule deltas, sample counts, suite hashes, and agent/config versions. `--strict-baseline` exits non-zero on regression.
- Reports are strict JSON (`NaN`/infinity forbidden), bounded to 64 cases and 500,000 characters, and disclose truncation/drop counts.

## Layout

| Path | Role |
| --- | --- |
| `src/services/agent_eval_service.py` | Evaluator + failure mining |
| `tests/fixtures/agent_eval/manifest.json` | Case catalog |
| `tests/fixtures/agent_eval/cases/*.json` | Context + expected properties + frozen `agent_output` |
| `tests/services/test_agent_eval_service.py` | Offline pytest (counterexample per rule) |

## How to run

```bash
python -c "
from src.services.agent_eval_service import AgentEvalService, format_failure_report
r = AgentEvalService().evaluate_suite()
print('rule_score', r.rule_score)
print(format_failure_report(r))
"

python -m pytest tests/services/test_agent_eval_service.py -q
python scripts/run_agent_benchmark.py --strict-baseline

# Compare a named candidate fixture catalog/config against the frozen baseline
python scripts/run_agent_benchmark.py --strict-baseline \
  --output-quality-candidate-root /path/to/candidate/catalog \
  --candidate-agent-version agent-v2 \
  --candidate-config-version config-v2 \
  --json-out /tmp/agent-eval.json
```

There is no environment switch or production runtime hook. Invocation is the opt-in boundary. Fixtures contain frozen, secret-free evidence only; raw private prompts, credentials, and tool payloads must not be stored in cases or reports.

## Explicit non-goals

- **No** automatic prompt / skill rewrite (#215 self-improvement remainder)
- **No** changes under `src/agent/`, backtest, or decision-signal outcome services
- **No** fabricating skill-level performance from global win rates (same honesty posture as `BacktestService.get_skill_summary()` returning `None`)
- **No** replacement of the V0 runtime benchmark or the analysis-quality panel

## Relation to T01 trajectory evaluation

| | T01 trajectory | This service (output quality) |
| --- | --- | --- |
| Object | Tool-call process efficiency | Output content quality |
| Code | Independent scorer | `agent_eval_service.py` |
| Runner | Canonical offline benchmark | Same runner, separate score bucket |
