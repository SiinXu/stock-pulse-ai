# 多标的组合级分析

对**一组标的**做组合层面分析（而非逐个结论堆叠）的后端入口（[#128](https://github.com/SiinXu/stock-pulse-ai/issues/128)）。

服务将标的列表构造成与现有持仓快照**同构**的合成权重快照，并复用：

| 数据面 | 作用 |
| --- | --- |
| `PortfolioRiskMetricsService` | 相关性矩阵、历史 VaR、集中度 / 分散度 |
| `PortfolioHealthService` | 在相同快照 + 风险输入上的结构健康维度 |
| `PortfolioStressTestService` | 可选确定性压力测试叠加 |
| `WatchlistScoreService` | 基于**已有**分析的立场 / 评分分布（不触发新 LLM） |

不另造持仓账本或平行组合模型。

## 接口

```http
POST /api/v1/analysis/portfolio
```

`operation_id`: `analyzePortfolioLevel`

鉴权与邻近 `/api/v1/analysis/*`、`/api/v1/portfolio/*` 一致（启用时走全局管理会话）。

### 请求要点

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `stock_codes` | 必填 | `1..20` 个不重复代码；超限在校验阶段拒绝并给出上限提示 |
| `weights` | 等权 | 可选非负权重；键必须属于 `stock_codes` |
| `include_stress` | `true` | 是否对合成快照跑压力情景 |
| `sector_map` | 无 | 可选行业标签，用于共同风险聚类 |
| `high_correlation_threshold` | `0.70` | 高相关高亮阈值 |

### 硬约束：缺数降级

- 单标的无可用收盘价时写入 `degraded_symbols`，**不**导致整单失败。
- 其余标的继续计算并重定权重；整体 `status=partial`。
- 全部缺失时返回 `status=unavailable`（HTTP 200），而非 500。

规模上界：`MAX_SYMBOLS = 20`。

## 范围外（后续）

- Web「分析组合 / 自选」按钮与完整报告页
- CLI `--portfolio` 模式
- 组合级摘要通知模板
- 将 basket 健康结果写入账户日度健康存储

英文版见 [portfolio-level-analysis_EN.md](portfolio-level-analysis_EN.md)。
