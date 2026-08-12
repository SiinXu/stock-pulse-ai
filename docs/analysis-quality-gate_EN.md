# Analysis quality gate (pipeline)

**Status**: Runtime slice of issue [#887](https://github.com/SiinXu/stock-pulse-ai/issues/887)

**Chinese**: [analysis-quality-gate.md](analysis-quality-gate.md)

**Reuses**: offline agent-eval dimensions in [agent-eval-dimensions_EN.md](agent-eval-dimensions_EN.md) / `src/services/agent_eval_service.py` (especially `factuality` and `boundary_honesty`). This gate does **not** invent a second rubric.

## Purpose

After analysis produces a conclusion, the pipeline runs a deterministic quality gate so **factual claims cannot be published as verified facts unless they bind to input evidence**. The gate:

1. Projects pipeline evidence into `FinancialFact` records
2. Projects conclusion fact claims (structured `dashboard.claims` and numeric `report_strata.verified_facts`) into `FinancialClaim` records
3. Scores them with the same rule scorers used by the offline agent-eval suite
4. Records the verdict under `quality_gate_result` / `dashboard.quality_gate` (trace + raw_result)
5. Applies a configurable failure policy

## Failure policy

| `ANALYSIS_QUALITY_GATE_ON_FAILURE` | Behavior |
| --- | --- |
| `annotate` (**default**) | Demote ungrounded verified-fact lines into `model_inference` (opinion), keep analysis success |
| `intercept` | Set `success=false`, `error_code=quality_gate_intercept` |

Gate-internal exceptions **never pass silently**: they fail closed to `annotate` with `verdict=gate_error` and `fail_closed=true`, even when the configured policy is `intercept`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANALYSIS_QUALITY_GATE_ENABLED` | `true` | Master switch; disable only for diagnostics |
| `ANALYSIS_QUALITY_GATE_ON_FAILURE` | `annotate` | `annotate` or `intercept` |

## Trace shape

`AnalysisResult.quality_gate_result` (schema `analysis-quality-gate/v1`) includes:

- `verdict`: `pass` | `annotate` | `intercept` | `gate_error` | `skipped`
- `failure_policy`, `passed`, `rule_score`, `dimensions`, bounded `checks`
- `ungrounded_claim_ids` / `ungrounded_statements`
- `eval_hook`: dimension catalog + rule score (pipeline eval hook)
- `evaluation_id`, `evaluated_at`, `fail_closed`, `action_taken`

## Explicit non-goals

- Guaranteeing profitable advice
- Replacing human judgment
- Live LLM judges for subjective dimensions (`explanation_clarity`, `risk_framing_quality`)
- Replacing the offline agent-eval benchmark or analysis-quality panel fixtures

## How to test

```bash
python -m pytest tests/services/test_analysis_quality_gate.py -q
python -m pytest tests/services/test_agent_eval_service.py -q
```
