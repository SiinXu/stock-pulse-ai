# 预测抽取（结构化决策 → 声明）

**状态**：A2 抽取器 + A3 持久化（Issues [#1108](https://github.com/SiinXu/stock-pulse-ai/issues/1108) / [#1101](https://github.com/SiinXu/stock-pulse-ai/issues/1101)；父 Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)）

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
| `src/services/prediction_persist.py` | 通过 `insert_pending` 持久化可验证 pending 草稿 |
| `src/core/stages/persistence.py` | 历史保存后钩子（尽力而为、开关控制） |
| `src/agent/orchestrator_parts/dashboard.py` | Agent finalize 后钩子（尽力而为、开关控制） |
| `tests/services/test_prediction_extractor.py` | 单元覆盖，含散文反例 |
| `tests/services/test_prediction_persist.py` | Agent/流水线持久化、双入口一行身份、挂载 id 等于存库主键、resolve 后不覆盖 |

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
| 来源证明 | 流水线只读取解析器保留的 `AnalysisResult.prediction_source`；`action=hold` 等展示层归一化默认值不参与抽取 |
| 期限 | 优先显式结构化 horizon；否则系统策略默认 `5d`，在 notes 记 `horizon_source=policy_default:5d`（非模型声明） |
| Agent 模式 | 方向声明需要显式 `action` 或类型化 `prediction_claims`；单独的 `decision_type` 忽略（常被编排层合成） |
| 分析模式 | 在具备结构化置信度时仍接受精确 `decision_type` buy/hold/sell |
| 有效/无效声明混合 | 草稿标记为 `status=error` 且不可打分；不会静默丢弃无效声明后把残余子集作为 pending 记录 |
| 双入口 | Agent finalize 与历史保存共享同一个规范 `run_id`（流水线把 `query_id` 传入 agent 上下文，否则用 chat `session_id`）。一次用户可见分析每个 symbol 只存一行 pending。持久化把 `prediction_id_for_run(run_id, symbol)` 写回挂载草稿，使 `prediction_extraction.record.prediction_id` 等于存库主键。 |

## 特性开关

| 键 | 默认 | 效果 |
| --- | --- | --- |
| `PREDICTION_EXTRACT_ENABLED` | `false` | 关闭时钩子为空操作；开启时成功 finalize / 历史保存路径附加内存抽取草稿，并将可验证 pending 行写入 `agent_predictions` |

草稿挂载位置：

- `AnalysisResult.prediction_extraction`（流水线历史路径）
- `AgentContext.meta["prediction_extraction"]`（Agent finalize 路径）

可验证 pending 草稿通过 `AgentPredictionRepository.insert_pending` 持久化。稳定 `prediction_id` 使用长度前缀（`pred-{len(run_id)}:{run_id}:{symbol}`，超 128 字符时改为哈希），避免连字符拼接碰撞。同一 run/symbol 再次 finalize 复用已有行（主键冲突，不覆盖，含 resolve 之后）。持久化失败只记录日志，不中断分析。调用方在 persist 之后挂载 `prediction_extraction`，因此内存草稿携带存库主键。

## 放量

整条核验环路的安全运营顺序见 [预测核验安全放量](prediction-verification-rollout.md)（Issue #1115）。抽取是该顺序的 **第 2 步**：

1. 核验环路全部开关保持默认关闭。
2. 打开 `PREDICTION_EXTRACT_ENABLED=true`，并确认分析 / 历史保存仍然成功（抽取失败永不中断分析）。
3. 然后只在一个调度 worker 上打开解析器，**或**显式调用 `python -m src.services.prediction_resolver`。
4. 打开仅 miss/partial 的后验，并保持 `AGENT_POSTMORTEM_SKIP_CLEAN_HITS=true`。
5. 仅在达到 `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES` 后再打开门控适配器。
6. 自动晋升保持硬关闭。

随时关闭 `PREDICTION_EXTRACT_ENABLED`；分析路径不变。Issue 示例名 `PREDICTION_VERIFY_ENABLED` **不是**本键的别名。

## 相关文档

- [预测契约](prediction-contract.md)
- [预测核验安全放量](prediction-verification-rollout.md)
- Epic 产品规则见 issue #1107
