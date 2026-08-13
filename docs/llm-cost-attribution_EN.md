# LLM cost attribution and routing telemetry

Refs #166, #248. Aligns metering with per-mode Agent budgets (#1213).

## One measurement, two consumers

| Consumer | Surface | How cost is read |
| --- | --- | --- |
| Usage page / API | `llm_usage` + `/api/v1/usage/*` | nullable `estimated_cost_usd` + `cost_status` |
| Mode budget gate | `estimate_usage_cost_usd()` | float; unpriced → `0.0` |

Shared implementation: `src/llm/cost.py`.

Config: `LLM_USAGE_ATTRIBUTION_ENABLED` (default true), `LLM_COST_PRICING_PATH`.
