# 模拟盘决策过程质量分（Issue #1134）

English: [paper-decision-quality.md](paper-decision-quality.md)

## 目的

对**模拟盘成交**按过程纪律打分，而不是按实现收益：

| 维度 | 检查内容 |
| --- | --- |
| `analysis_support` | 是否关联 DecisionSignal / 分析计划、动作对齐、理由、计划完整度 |
| `risk_gate_compliance` | 失效条件或止损、置信度、数据质量/缺口、是否逆风险门动作下单 |
| `position_discipline` | 仓位/集中度相对 `PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT`；数据质量差时应控仓 |

**不评分：** 胜率、平均收益、命中/偏离、校准。这些仍由 DecisionSignal 后验校准与个人表现收益面（[#987](https://github.com/SiinXu/stock-pulse-ai/issues/987)）负责。

## 与个人表现视图的分工

| 归属 | Issue | 职责 |
| --- | --- | --- |
| 过程质量（本能力） | #1134 | 模拟盘过程分；个人表现视图中的**过程**面板可组合调用 |
| 结果 / 校准 | #987 | 胜率、实现收益、风格校准看板 |

两者可同属个人表现域。本 API 从不重定义结果语义，并固定标记 `score_kind: "process"`。

## 公式与 API

- `formula_version`: `paper-decision-quality-v2`
- 权重：分析 0.40、风险门 0.35、仓位 0.25
- **仓位占比按成交日权益**（回放到该日的组合快照），不用当前权益
- 信号关联：同代码 7 日内优先动作对齐；多候选时 `signal_linkage_ambiguous=true`
- 端点：`GET /api/v1/portfolio/accounts/{account_id}/paper-decision-quality`
- 仅 `paper` 账户；真实账户返回 `400 paper_account_required`；账户不存在返回 `404 account_not_found`

## 非目标

- 不自动调仓、不拦截下单
- 不做收益保证宣传
- 不替代公开信号计分卡（#379）或组合健康分（#151）
