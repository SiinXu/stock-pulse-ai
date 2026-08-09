# 组合健康分（V2 后端合同）

本功能提供确定性的组合结构评分与可执行洞察。它仅引用 [#151](https://github.com/SiinXu/stock-pulse-ai/issues/151)，不会关闭该 Issue：可见的 Portfolio Health 页面、可观察的每日更新链路和趋势消费端仍未交付。

健康分是组合结构度量，不是投资建议。LLM 最多只能润色洞察文案，不能修改分数、分档、阈值、严重级别、标的或证据。

## HTTP 生命周期

| 方法 | 路径 | 合同 |
| --- | --- | --- |
| `GET` | `/api/v1/portfolio/health` | 只读获取某日已存结果，不 replay、不写库 |
| `POST` | `/api/v1/portfolio/health/refresh` | 显式计算；`persist=true` 只执行一次原子健康快照 upsert |

两者都接受 `account_id`、`as_of`、`cost_method=fifo|avg`。POST 另接受 `persist`；`persist=false` 是真正零写入的预览。

刷新只调用一次 `PortfolioService.preview_portfolio_snapshot()`，并把同一个不可变 mapping 传给 `PortfolioRiskMetricsService`。它不会物化组合 position/lot/daily cache。GET 无数据时返回 404；缺少迁移时返回脱敏的 `portfolio_health_migration_required` 503，仓储不会在请求期建表。

## 公式配置

所有值统一由共享 `Config`、环境加载器和系统配置注册表管理。数值必须有限且位于文档范围内；非法字符串、`NaN`、无穷值会被拒绝，不会静默忽略或 clamp。

| 维度 | 默认权重 | 环境变量 |
| --- | ---: | --- |
| 集中度 | 0.25 | `PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION` |
| 风险暴露 | 0.25 | `PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE` |
| 分散度 | 0.20 | `PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION` |
| 盈亏 | 0.15 | `PORTFOLIO_HEALTH_WEIGHT_PNL` |
| 现金比例 | 0.15 | `PORTFOLIO_HEALTH_WEIGHT_CASH_RATIO` |

有限、非负权重统一归一化一次，且总和必须大于零。洞察阈值为：

- `PORTFOLIO_HEALTH_CONCENTRATION_ALERT_PCT=35`
- `PORTFOLIO_HEALTH_VAR_ALERT_PCT=5`
- `PORTFOLIO_HEALTH_DIVERSIFICATION_ALERT=0.35`
- `PORTFOLIO_HEALTH_CASH_LOW_ALERT_PCT=2`
- `PORTFOLIO_HEALTH_CASH_HIGH_ALERT_PCT=50`
- `PORTFOLIO_HEALTH_PNL_LOSS_ALERT_PCT=-15`

现金低阈值必须严格小于高阈值。响应会记录最终配置值和配置哈希。

## 子分公式

每个可用维度产生 0–100 子分：

1. 集中度：最大单票权重 ≤15% 得 100，≥50% 得 0，中间线性插值。
2. 风险暴露：1 日历史 VaR ≤1% 得 100，≥8% 得 0，中间线性插值。
3. 分散度：上游 `[0, 1]` 分散度乘 100。
4. 未实现盈亏：≥10% 得 100，0% 得 70，≤-30% 得 0，中间分段线性。
5. 现金比例：5–25% 得 100，0% 与 ≥80% 得 0，理想区间之外线性变化。

所有来源指标和中间值都必须有限。只有上游 VaR 状态为 `ok` 才可评分；价格缺失/陈旧或 FX 陈旧时 PnL 不可用；FX 陈旧时现金维度不可用。

## 缺失数据不奖励不变量

缺失数据绝不能让主分或分档变得更健康。

诊断字段 `partial_score` 使用固定配置分母：

```text
partial_score = sum(可用维度子分 * 原配置权重)
coverage_ratio = sum(可用维度的原配置权重)
```

缺失维度按零贡献处理，可用权重不会重新归一化。只有五维全部可用（`coverage_ratio=1`）且来源质量没有 partial 原因时，才输出可比较的 `score` 和常规 `healthy|fair|caution|poor` 分档。否则：

- `status=partial` 或 `unavailable`
- `score=null`、`band=null`、`comparable=false`
- `partial_score` 仅作为不可跨日比较的诊断值
- 每个缺失维度都有显式 unavailable 洞察
- 未知维度绝不会生成 “within thresholds” 结论

纯现金组合按 partial 处理，并可评估 PnL/现金；不会误判为空组合。只有现金和市值都为零才是 empty。负权益明确返回 unavailable。

## 持久化与溯源

迁移 `202608090002_portfolio_health_snapshots` 是唯一 schema 所有者；运行时仓储不执行 DDL。每日唯一键为 `(account_key, snapshot_date, cost_method)`，单条 `INSERT ... ON CONFLICT DO UPDATE` 保证同键原子收敛，并带有限次 SQLite busy 重试。

存储 payload 与调用者收到的状态语义一致，包括 `persisted=true`。响应记录：

- 来源组合快照与风险结果哈希
- 最终配置哈希与公式版本
- UTC 计算时间
- 风险历史窗口/as-of 证据
- 有界的价格与 FX 溯源
- 覆盖率、有效权重、缺失维度和质量原因

严格 JSON 序列化与响应 schema 会拒绝非有限值。同日键仍是幂等当前快照，不是不可变修订历史或趋势 API。

## 仅适用于完整可比较结果的分档

| 分档 | 区间 |
| --- | --- |
| `healthy` | `[80, 100]` |
| `fair` | `[60, 80)` |
| `caution` | `[40, 60)` |
| `poor` | `[0, 40)` |

## 回滚

Revert 本功能。新增表可以保留为空闲表，或在保留所需数据后删除；现有组合账本不会被改写。
