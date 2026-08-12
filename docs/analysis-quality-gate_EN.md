# Analysis quality gate (pipeline)

**Status**: Runtime slice of issue [#887](https://github.com/SiinXu/stock-pulse-ai/issues/887)

**Chinese**: [analysis-quality-gate.md](analysis-quality-gate.md)

**Reuses**: offline agent-eval dimensions in [agent-eval-dimensions_EN.md](agent-eval-dimensions_EN.md) / `src/services/agent_eval_service.py`. This gate does **not** invent a second rubric.

## Purpose

After analysis produces a conclusion, the pipeline runs a deterministic quality gate so **factual claims cannot be published as verified facts unless they bind to input evidence**. The gate:

1. Projects bounded quote, fundamental, and technical inputs into `FinancialFact` records; the public context overview supplies status/provenance only and is never treated as a value source
2. Projects conclusion fact claims (the analyzer's numeric `dashboard.data_perspective` fields, optional structured `dashboard.claims`, and numeric `report_strata.verified_facts`) into `FinancialClaim` records
3. Scores them with the same rule scorers used by the offline agent-eval suite
4. Records the verdict under `quality_gate_result` / `dashboard.quality_gate` (trace + raw_result)
5. Applies a configurable failure policy

## Failure path vs advisory path

| Path | Dimensions | Effect on publish |
| --- | --- | --- |
| **Failure** | `factuality` only | Drives `annotate` / `intercept` |
| **Advisory** | `boundary_honesty` | Recorded in `checks` / `eval_hook` only; never flips verdict or demotes strata |

Soft `data_quality.limitations` (for example a partial news window) do **not** mark data missing. Directional forbids are never enabled by default at runtime (offline cases may still opt in via their own rubric).

## Failure policy

| `ANALYSIS_QUALITY_GATE_ON_FAILURE` | Behavior |
| --- | --- |
| `annotate` (**default**) | Demote ungrounded verified-fact lines into `model_inference` and quarantine failed structured claims, while keeping analysis success |
| `intercept` | Set `success=false`, `error_code=quality_gate_intercept` |

Gate-internal exceptions **never pass silently**: they remove every unchecked structured claim and demote every verified-fact line before returning `verdict=gate_error` and `fail_closed=true`, even when the configured policy is `intercept`. If that enforcement cannot be applied, the exception propagates so the pipeline cannot publish an unchecked success.

Results that already have `success=false` are recorded as `skipped_failed_analysis`; the gate never reclassifies a provider or analysis failure as a successful quality verdict.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `ANALYSIS_QUALITY_GATE_ENABLED` | `true` | Master switch; disable only for diagnostics |
| `ANALYSIS_QUALITY_GATE_ON_FAILURE` | `annotate` | `annotate` or `intercept` |

## Trace shape

`AnalysisResult.quality_gate_result` (schema `analysis-quality-gate/v1`) includes:

- `verdict`: `pass` | `annotate` | `intercept` | `gate_error` | `skipped`
- `failure_policy`, `passed`, `rule_score`, `failure_rule_score`, `advisory_rule_score`
- `failure_dimensions` / `advisory_dimensions`, `failure_reason_codes`, bounded `checks`
- `ungrounded_claim_ids` / `ungrounded_statements`
- `eval_hook`: dimension catalog + failure/advisory scores (pipeline eval hook)
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
