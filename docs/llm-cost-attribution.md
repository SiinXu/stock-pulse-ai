# LLM 成本归因与路由遥测

Refs #166, #248。与每模式 Agent 预算（#1213）对齐计量口径。

## 一套计量，两处消费

| 消费方 | 表面 | 成本读取 |
| --- | --- | --- |
| Usage 页 / API | `llm_usage` + `/api/v1/usage/*` | nullable `estimated_cost_usd` + `cost_status` |
| 模式预算门 | `estimate_usage_cost_usd()` | float；未计价 → `0.0` |

共享实现：`src/llm/cost.py`。

配置：`LLM_USAGE_ATTRIBUTION_ENABLED`（默认 true）、`LLM_COST_PRICING_PATH`。

