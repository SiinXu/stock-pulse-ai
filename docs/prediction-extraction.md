# 预测抽取（结构化决策 → 声明）

**状态**：A2 抽取器（Issue [#1108](https://github.com/SiinXu/stock-pulse-ai/issues/1108)；父 Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)；依赖 A1 契约 [#1101](https://github.com/SiinXu/stock-pulse-ai/issues/1101)）

**English**: [prediction-extraction_EN.md](prediction-extraction_EN.md)

## 目的

在成功的 finalize 路径上，把**结构化**决策 / 仪表盘字段映射为 `PredictionRecord` 草稿。后续阶段可持久化、按 horizon 核验并打分，而不会把报告散文当成假的可验证预测。

## 产品规则

| 规则 | 抽取器行为 |
| --- | --- |
| 仅结构化字段 | 声明只来自精确枚举（`decision_type`、`action`）或显式 claim 对象 |
| 散文 ≠ 声明 | `analysis_summary`、`operation_advice` 文本、`trend_prediction` 文案、展望段落**永不**被正则解析成方向 |
| 缺少结构 | 输出 `status=no_verifiable_claim` + `no_verifiable_reason`（例如 `prose_only`） |
| 分析失败闭环 | 抽取异常只记日志；分析 / 历史保存仍成功 |
| 研究 / 质量运营 | 不是收益保证产品面 |
| 默认关闭 | `PREDICTION_EXTRACT_ENABLED=false` |

## 模块映射

| 路径 | 职责 |
| --- | --- |
| `src/schemas/prediction_record.py` | A1 契约（严格 `PredictionRecord` / claims） |
| `src/core/prediction_resolve_after.py` | Horizon → UTC `resolve_after`（交易日；失败封闭） |
| `src/services/prediction_extractor.py` | 纯抽取器 + 特性开关 finalize 辅助 |
| `src/core/stages/persistence.py` | 历史保存后钩子（尽力而为、开关控制） |
| `src/agent/orchestrator_parts/dashboard.py` | Agent finalize 后钩子（尽力而为、开关控制） |
| `tests/services/test_prediction_extractor.py` | 单元覆盖，含散文反例 |

## 会变成声明的来源

| 来源 | 声明 |
| --- | --- |
| `action` 精确 token `buy`/`add`/`hold`/`watch`/`reduce`/`sell` | `direction`（`up` / `sideways` / `down`） |
| 否则 `decision_type` 精确 token `buy`/`hold`/`sell` | `direction` |
| 显式 `prediction_claims` / `claims` / `forecast.claims` 列表 | 仅通过 A1 校验的 claim 对象 |
| 显式 `return_bucket` / `level_break` / `vol_regime` 对象 | 对应 claim 类型 |

`avoid` / `alert` 不会臆造价格方向。多词自由文本与中文建议短语不会被当作枚举。

## 绝不会变成声明的内容

- 叙述字段：`analysis_summary`、`short_term_outlook`、`operation_advice`、`trend_prediction`、Markdown 正文等
- 枚举缺失时的默认方向
- 行情 / 日历失败时的伪造命中（`resolve_after` 失败封闭 → 保留 claims 但 `status=error`，不伪造 pending 到期时间）


## 抽取语义（评审收敛）

| 主题 | 行为 |
| --- | --- |
| 置信度 | 仅结构化 `confidence` / `confidence_level`；**永不**发明 `0.5` |
| 期限 | 优先显式结构化 horizon；否则系统策略默认 `5d`，在 notes 记 `horizon_source=policy_default:5d`（非模型声明） |
| Agent 模式 | 方向声明需要显式 `action` 或类型化 `prediction_claims`；单独的 `decision_type` 忽略（常被编排层合成） |
| 分析模式 | 在具备结构化置信度时仍接受精确 `decision_type` buy/hold/sell |
| 双入口 | Agent finalize（`ctx.meta`）与历史保存（`result.prediction_extraction`）都可能挂草稿；A3 持久化必须去重 |

## 特性开关

| 键 | 默认 | 效果 |
| --- | --- | --- |
| `PREDICTION_EXTRACT_ENABLED` | `false` | 关闭时钩子为空操作；开启时成功 finalize / 历史保存路径附加内存抽取草稿 |

草稿挂载位置：

- `AnalysisResult.prediction_extraction`（流水线历史路径）
- `AgentContext.meta["prediction_extraction"]`（Agent finalize 路径）

耐久 `agent_prediction` 存储**不在** A2 范围（持久化 issue）。

## 相关文档

- [预测契约](prediction-contract.md)
- Epic 产品规则见 issue #1107
