# 预测 vs 实际跟踪 — 归属说明

**状态**：Living（整合说明）
**议题**：规划 [#449](https://github.com/SiinXu/stock-pulse-ai/issues/449)；权威 Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)

## 目的

#449 提出通用的「预测 vs 实际」评估框架。**#1107** 是 Agent 可验证预测闭环的权威交付路径（结构化 claims → 到期自动解析 → 打分 → 复盘 → 门控适配）。

**禁止在 #449 下再实现第二套跟踪存储 / 打分器 / 解析器。**

## 验收覆盖

| #449 验收 | #1107 面 |
| --- | --- |
| 自动记录预测与元数据 | A1 契约、A2 抽取、A3 `agent_predictions` |
| 到期后自动对比 | A4 ActualsFetcher、A5 ClaimScorer、交易日历、A7/A8 resolver |
| 指标计算 | ClaimScorer 聚合 + offline评估门禁 |
| 指标展示 | 运维指标 [#1114](https://github.com/SiinXu/stock-pulse-ai/issues/1114)；查询/诊断残留 [#1102](https://github.com/SiinXu/stock-pulse-ai/issues/1102) |
| 自改进反馈 | 复盘 [#1103](https://github.com/SiinXu/stock-pulse-ai/issues/1103)；适配器 [#1106](https://github.com/SiinXu/stock-pulse-ai/issues/1106) / [#1091](https://github.com/SiinXu/stock-pulse-ai/issues/1091) |

英文主文档：[prediction-vs-actual-tracking_EN.md](prediction-vs-actual-tracking_EN.md)
