# 组合再平衡与风险调整仓位区间

对应 Issue [#237](https://github.com/SiinXu/stock-pulse-ai/issues/237)、[#126](https://github.com/SiinXu/stock-pulse-ai/issues/126) 的后端 V1。

本能力输出**确定性、可解释**的再平衡建议与单票仓位权重区间，**不会**自动下单、改写账本或替代个人判断。

**仅供研究参考，不构成投资建议。**

完整公式、风险带表、拒绝条件与配置项见英文文档：[portfolio-rebalancing_EN.md](portfolio-rebalancing_EN.md)。

## HTTP

`GET /api/v1/portfolio/rebalancing-recommendations`

`operation_id=getPortfolioRebalancingRecommendations`

只读；消费组合快照 + `PortfolioRiskMetricsService`；热路径不调用行情 Provider。

## 硬性约束

- 顶层始终带 `disclaimer`。
- 每条建议含 `rationale`、`assumptions`，且 `is_suggestion_only=true`、`auto_execute=false`。
- 空仓 / 历史不足 → 明确 `status` 并拒绝生成虚构调仓。
- 非有限数值（NaN/Inf）拒绝。
- 跨币种权重一律使用快照中的 `market_value_base`（由 `PortfolioService` 完成汇率归一）。

## 风险带（摘要）

| 风险偏好 | 单票上限 | 最小有效 N | 最大 HHI | 示意 1 日 VaR 上限 |
| --- | ---: | ---: | ---: | ---: |
| conservative | 15% | 6.0 | 0.22 | 2.0% |
| moderate | 25% | 4.0 | 0.35 | 3.5% |
| aggressive | 40% | 2.5 | 0.50 | 6.0% |

有效单票上限 = `min(风险带上限, PORTFOLIO_MAX_SINGLE_NAME_WEIGHT×100)`。

## Agent

`PortfolioAgent` 注入确定性基座；`post_process` 以服务结果覆盖自由生成的 `rebalance_suggestions`，LLM 仅可润色叙述。

## 回滚

还原实现 PR 即可；无数据库迁移。
