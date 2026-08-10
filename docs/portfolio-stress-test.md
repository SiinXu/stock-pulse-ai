# 组合压力测试（确定性冲击）

组合压力测试 API 为 [#158](https://github.com/SiinXu/stock-pulse-ai/issues/158)
提供只读的确定性因子冲击，并关联 [#210](https://github.com/SiinXu/stock-pulse-ai/issues/210)
的组合风险语义。历史路径重放、Monte Carlo、完整工具重估和 Web 可视化不在本轮范围内。

## API 与输入契约

```http
GET  /api/v1/portfolio/stress-test/scenarios
GET  /api/v1/portfolio/stress-test?scenario_id=market_down_10
POST /api/v1/portfolio/stress-test
```

`POST` 必须在 `scenario_id` 与 `custom_shocks` 中二选一。行业情景是参数化模板，
只能通过 `POST` 同时提供 `target_sector` 和调用方的 `sector_map`；服务不会虚构行业分类。
market/sector/FX 百分比冲击限制为 `[-100, 100]`，rate 冲击限制为
`[-1000, 1000]` bp；错误单位、额外字段、非有限数字、超量 map/冲击以及组合后低于
`-100%` 的回报都会被拒绝。快照超过 512 个持仓行时，也会在构造响应前返回稳定的客户端错误。

## 估值语义

服务调用 `PortfolioService.preview_portfolio_snapshot()`，复用规范持仓回放，但不调用
市场数据提供方，也不写入派生 position/lot/snapshot 行。同一股票在不同账户中的持仓保持分离。

每个 `market_value_base` 先从账户本位币转换为响应本位币，再计算总额、权重、PnL、
集中度和排序；转换后持仓合计加上已知的排除价值，会与快照的权威
`total_market_value` 对账。价格不可用的持仓保留“价值未知”计数，不把占位零当成真实估值。

FX 冲击表示工具/交易币种相对响应本位币的升贬值，依据 `position.currency` 判断风险敞口；
`valuation_currency` 是账户本位币，不能用于判断 FX 敞口。

## 质量与可复现性

响应披露快照 hash/版本、计算时间、情景来源/版本/hash、公式版本、价格来源，以及分开的
“工具币种→账户本位币”估值汇率和“账户本位币→响应本位币”汇总汇率来源/日期/陈旧状态。
价格不可用或估值非正的已持有头寸会显示在 `excluded_positions` 中，并披露已知排除价值和
未知价值计数，不会伪装成空组合。调用方只提供 beta/行业标量时没有观测日期，因此对应
`*_as_of` 保持空值；identity、zero 和 1:1 fallback 汇率也不会用请求日期伪造来源日期。

- `ok`：输入和数据足以计算完整结果。
- `partial`：使用单位 beta，或存在陈旧/缺失/排除/对账限制。
- `unavailable`：存在持仓，但没有任何可估值头寸。
- `empty_portfolio`：确实没有持仓。

`top_losers` 只包含负 PnL，`top_winners` 只包含正 PnL；零 PnL 不进入任一列表。

## YAML 情景目录

`PORTFOLIO_STRESS_SCENARIOS_PATH` 通过共享 Config 和配置注册表加载，路径最多 1,024 字符。
目录限制为 256 KiB、64 个情景、每个情景 16 个冲击、32 个 YAML alias 标记、嵌套深度 8，
并使用 safe loader。Config 构造时会先验证并原子预热目录；后续文件无效时继续使用同一路径
最后一次验证成功的目录。若该路径从未成功加载，API 返回不泄露文件路径的 `503`。
未配置时只使用内置情景。

更多公式和内置情景表见英文版：[portfolio-stress-test_EN.md](portfolio-stress-test_EN.md)。
