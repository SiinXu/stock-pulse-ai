# 分析质量门（管线）

**状态**：Issue [#887](https://github.com/SiinXu/stock-pulse-ai/issues/887) 的运行时切片

**English**：[analysis-quality-gate_EN.md](analysis-quality-gate_EN.md)

**复用**：离线 agent-eval 维度 [agent-eval-dimensions.md](agent-eval-dimensions.md) / `src/services/agent_eval_service.py`。本质量门**不另立**评分标准。

## 目的

分析产出结论后，管线运行确定性质量门：**事实性陈述必须能绑定到输入证据**，否则不得作为已核实事实发布。门会：

1. 将有界的行情、基本面与技术指标输入投影为 `FinancialFact`；公开 context overview 只提供状态与来源信息，绝不作为数值证据
2. 将结论中的事实声明（分析器真实产出的 `dashboard.data_perspective` 数值字段、可选结构化 `dashboard.claims` 与含数值的 `report_strata.verified_facts`）投影为 `FinancialClaim`
3. 使用与离线 agent-eval 相同的规则评分器打分
4. 把判定写入 `quality_gate_result` / `dashboard.quality_gate`（trace 与 raw_result）
5. 按可配置策略处理失败

## 失败路径 vs 顾问路径

| 路径 | 维度 | 对发布的影响 |
| --- | --- | --- |
| **失败路径** | 仅 `factuality` | 驱动 `annotate` / `intercept` |
| **顾问路径** | `boundary_honesty` | 只写入 `checks` / `eval_hook`；不改变 verdict、不 demote strata |

软性 `data_quality.limitations`（例如新闻窗口 partial）**不会**被当成 data missing。运行时默认不启用 directional forbid（离线 case 仍可在自有 rubric 中显式开启）。

## 失败策略

| `ANALYSIS_QUALITY_GATE_ON_FAILURE` | 行为 |
| --- | --- |
| `annotate`（**默认**） | 将未绑定的 verified_facts 降级为 `model_inference`，并隔离失败的结构化声明；分析仍成功 |
| `intercept` | `success=false`，`error_code=quality_gate_intercept` |

门自身异常**不得静默放行**：返回 `verdict=gate_error`、`fail_closed=true` 前，会移除所有未经核验的结构化声明并降级所有 verified_facts。若连该处置也无法完成，异常会继续向上抛出，防止管线发布未经检查的成功结果。

对于已经是 `success=false` 的分析结果，质量门记录 `skipped_failed_analysis`，不会把 provider 或分析失败重新判定为质量检查成功。

## 配置

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `ANALYSIS_QUALITY_GATE_ENABLED` | `true` | 总开关；仅排障时关闭 |
| `ANALYSIS_QUALITY_GATE_ON_FAILURE` | `annotate` | `annotate` 或 `intercept` |

## Trace 形状

`AnalysisResult.quality_gate_result`（schema `analysis-quality-gate/v1`）包含：

- `verdict`：`pass` | `annotate` | `intercept` | `gate_error` | `skipped`
- `failure_policy`、`passed`、`rule_score`、`failure_rule_score`、`advisory_rule_score`
- `failure_dimensions` / `advisory_dimensions`、`failure_reason_codes`、有界 `checks`
- `ungrounded_claim_ids` / `ungrounded_statements`
- `eval_hook`：维度目录 + 失败/顾问分（管线内评测钩子）
- `evaluation_id`、`evaluated_at`、`fail_closed`、`action_taken`

## 明确非目标

- 保证盈利建议
- 替代人类判断
- 对主观维度（`explanation_clarity`、`risk_framing_quality`）做在线 LLM 评判
- 替代离线 agent-eval 基准或 analysis-quality 面板夹具

## 如何测试

```bash
python -m pytest tests/services/test_analysis_quality_gate.py -q
python -m pytest tests/services/test_agent_eval_service.py -q
```
