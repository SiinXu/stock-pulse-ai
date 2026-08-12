# 预测契约（结构化预测记录）

**状态**：仅 A1 契约（Issue [#1101](https://github.com/SiinXu/stock-pulse-ai/issues/1101)；父 Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)）

**English**: [prediction-contract_EN.md](prediction-contract_EN.md)

## 目的

Agent 自进化需要**可核验的预测**，而不是自由文本叙事。本文定义严格的 `PredictionRecord` schema，供后续按 horizon 取数、打分与复盘使用，并禁止把非结构化散文伪造成可验证声明。

本切片**只含类型与校验**，不负责：从散文抽取 claims、持久化、拉取行情 actuals、调度、打分，也不修改 Soul / ToolSurface。

## 产品规则（来自 Epic #1107）

| 规则 | 契约含义 |
| --- | --- |
| 后续系统驱动闭环 | schema 携带 `status` / `resolve_after` 供调度；契约本身不要求用户点「验证」 |
| 禁止运行时改 Soul / ToolSurface | `model_meta.soul_version` 仅为溯源 |
| 仅研究 / 质量运营定位 | 文档与 `notes` 不得声称收益保证 |
| 不可解析散文 ≠ claim | 使用 `status=no_verifiable_claim` + `no_verifiable_reason`，且 `claims` 必须为空 |
| 永不伪造命中 | 打分不在本切片；契约拒绝非有限数值，并拒绝 prose 充当 claim |

## 代码位置

| 路径 | 职责 |
| --- | --- |
| `src/schemas/prediction_record.py` | 严格 Pydantic 模型、构造器与校验 |
| `tests/schemas/test_prediction_record.py` | 成功 / 失败 / 边界单测 |

Schema 版本常量：`prediction-record-v1`（`PREDICTION_RECORD_SCHEMA_VERSION`）。

## 记录字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `schema_version` | 是 | 字面量 `prediction-record-v1` |
| `prediction_id` | 是 | 预测记录稳定 id |
| `run_id` | 是 | 关联分析 / Agent run，供后续 reflection |
| `symbol` | 是 | 标的代码（禁止空白字符） |
| `market` | 否 | 市场标签（如 `CN` / `HK` / `US`） |
| `created_at` | 是 | 带时区 datetime（规范为 UTC） |
| `as_of` | 是 | 预测锚定的交易日 |
| `horizon` | 是 | `1d` / `3d` / `5d` / `10d` / `20d` 之一 |
| `resolve_after` | 是 | 最早可解析时间（UTC 感知） |
| `claims` | 条件 | 类型化可机检声明（见下） |
| `status` | 是 | `pending` \| `resolving` \| `resolved` \| `expired` \| `error` \| `no_verifiable_claim` |
| `source_decision_id` | 否 | 上游决策 / dashboard 标识 |
| `model_meta` | 否 | `mode`、`soul_version`、`skill_ids`、`model_version`、`config_version`、`model_id` |
| `no_verifiable_reason` | 不可验证时 | `unparseable_output` \| `prose_only` \| `missing_structured_fields` \| `empty_decision` \| `unsupported_shape` |
| `notes` | 否 | 仅研究备注；**永不参与打分** |

### 状态与 claims

| 状态 | claims | 说明 |
| --- | --- | --- |
| `pending` / `resolving` / `resolved` | **至少一个**类型化 claim | 可进入后续核验流水线 |
| `no_verifiable_claim` | **必须为空** | 必须带 `no_verifiable_reason`；跳过打分 |
| `error` / `expired` | 可为空 | 故障 / 过期路径，不得发明 claim |

推荐构造器：无法从结构化字段抽出 claim 时，使用 `build_no_verifiable_claim_record(...)`。

## Claim 类型

只有**类型化** claim 可进入核验流水线。每条 claim 含 `claim_id`、`type`、`confidence` ∈ [0, 1] 与匹配的 `payload`。

| `type` | payload | 后续机检意图 |
| --- | --- | --- |
| `direction` | `direction`: `up` \| `down` \| `sideways` | 相对 `as_of` 收盘价的收益方向 |
| `return_bucket` | 有限 `low_pct` &lt; `high_pct`，可选 `bucket_id` | 简单收益率区间（幅度桶） |
| `level_break` | `side`、有限 `level`、`reference` | 突破绝对价或相对收盘涨跌幅 |
| `vol_regime` | `regime`: `low` \| `normal` \| `high` \| `elevated` | 实现波动率分档 |
| `custom` | `metric`、`operator`、机检 `expected` | 仅显式算子比较 |

### 拒绝项

- 未知额外字段（`extra=forbid`）
- 任意 float 上的 NaN / ±Infinity（`allow_inf_nan=False`）
- 置信度超出 `[0, 1]`
- 无时区的 `created_at` / `resolve_after`
- 将自由散文写入 `custom.expected`（仅允许短机检 token 或有限数字）
- `no_verifiable_claim` 仍携带 claims（伪造可验证性）
- `pending` 且 claims 为空（应改用 `no_verifiable_claim`）

`notes` 可供运营阅读；A2 抽取器不得将其提升为 `claims`。

## 本切片之外（#1107 后续）

| 阶段 | 职责 |
| --- | --- |
| A2 | 从结构化决策 / dashboard 字段抽取（禁止对 markdown 散文硬编 claims） |
| A3 | 持久化与索引 `(status, resolve_after)`、`(symbol, created_at)` |
| A4 | Actuals 拉取；失败为 `data_unavailable` / 重试，永不伪造价格 |
| A5–A8 | 打分、日历、调度、批量合并 |
| A9–A10 | 复盘 lessons、评测门 / adapters |

## 相关但不可复用的面

- 分析 dashboard 上的自由文本 `trend_prediction`（仅展示叙事）
- Skill opinion outcomes（单 skill 信号评估，身份独立）
- Decision signal outcomes（DecisionSignal 动作窗口，生命周期独立）
- 离线 agent-output eval facts（仅评测 harness）
