# Financial Agent Output-Quality Evaluation Dimensions (Output-side V1)

**Status**: Output-quality slice of issue [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252); failure mining [#141](https://github.com/SiinXu/stock-pulse-ai/issues/141); harness slice of [#215](https://github.com/SiinXu/stock-pulse-ai/issues/215)  
**Chinese**: [agent-eval-dimensions.md](agent-eval-dimensions.md)  
**Complements**: the existing **runtime-structure** benchmark [agent-eval-benchmark_EN.md](agent-eval-benchmark_EN.md) (`tests/agent/benchmark`), which scores tool-call discipline on frozen agent transcripts. This table and `src/services/agent_eval_service.py` score **single output artifacts**. Metric intent is aligned; code is not shared.

## Purpose

After changing prompts, tools, or models, answer with **offline-replayable** cases: did output quality improve or regress, and which failure modes dominate?

## Dimension table

| Dimension id | What it checks | Judge | Stability |
| --- | --- | --- | --- |
| `factuality` | Market / filing-style numbers in the output must be grounded in the input context (no invented figures) | **rule** | Byte-stable for a fixed case; number tokens normalized (commas, trailing zeros, `%`) |
| `tool_usage` | Required tools called / forbidden tools absent (from output-side `tool_calls`) | **rule** | Stable; vs T01 trajectory: this dimension is set membership, not step/latency efficiency |
| `conclusion_consistency` | Evidence polarity must not contradict the final signal (e.g. all-bearish evidence vs `buy`) | **rule** | Stable; needs structured `evidence[].polarity\|sentiment` on the case |
| `boundary_honesty` | No overconfident advice when data is missing or tools failed | **rule** | Stable; context should mark `data_missing` / `failed_tools` |
| `language_format` | Required fields, forbidden phrases, object/JSON shape | **rule** | Stable |
| `explanation_clarity` | Subjective clarity of explanations | **llm** (optional external) | **Never mixed into the rule total**; offline default `skipped` unless the caller supplies `llm_judgements` |
| `risk_framing_quality` | Subjective risk-framing quality | **llm** (optional) | Same: separate `llm_score` only |

## Scoring

- **Rule score** = `passed / total` over all non-skipped rule checks.
- **LLM score** = only non-skipped `judge=llm` checks; reported separately from the rule score.
- **Failure mining** clusters by `(dimension, check_id)` with concrete case ids and sample details — not a single opaque total.

## Layout

| Path | Role |
| --- | --- |
| `src/services/agent_eval_service.py` | Evaluator + failure mining |
| `tests/fixtures/agent_eval/manifest.json` | Case catalog |
| `tests/fixtures/agent_eval/cases/*.json` | Context + expected properties + frozen `agent_output` |
| `tests/services/test_agent_eval_service.py` | Offline pytest (counterexample per rule) |

## Switch

```bash
# Default off; when off, evaluate_suite returns enabled=False with zero production impact
AGENT_EVAL_ENABLED=false
```

## How to run

```bash
AGENT_EVAL_ENABLED=true python -c "
from src.services.agent_eval_service import AgentEvalService, format_failure_report
r = AgentEvalService().evaluate_suite()
print('rule_score', r.rule_score)
print(format_failure_report(r))
"

python -m pytest tests/services/test_agent_eval_service.py -q
```

## Explicit non-goals

- **No** automatic prompt / skill rewrite (#215 self-improvement remainder)
- **No** changes under `src/agent/`, runner, backtest, or decision-signal outcome services
- **No** fabricating skill-level performance from global win rates (same honesty posture as `BacktestService.get_skill_summary()` returning `None`)
- **No** replacement of the V0 runtime benchmark or the analysis-quality panel

## Relation to T01 trajectory evaluation

| | T01 trajectory | This service (output quality) |
| --- | --- | --- |
| Object | Tool-call process efficiency | Output content quality |
| Code | Independent (not shared here) | `agent_eval_service.py` |
| Runner | Must not modify | Must not modify |
