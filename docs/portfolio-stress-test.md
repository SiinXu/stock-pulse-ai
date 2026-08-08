# 组合压力测试（确定性冲击）

后端只读的组合情景压力测试（[#158](https://github.com/SiinXu/stock-pulse-ai/issues/158)；相关 [#210](https://github.com/SiinXu/stock-pulse-ai/issues/210)）。

本文说明**确定性因子冲击**引擎、假设与诚实状态规则。本交付**不包含** Web 展示。

## 范围

| 本轮包含 | 剩余范围 |
| --- | --- |
| 声明式内置情景（可 YAML 覆盖） | 历史极端区间路径重放 |
| 确定性 market / sector / FX / rate 冲击 | Monte Carlo / 全路径重估 |
| 单位 beta、利率敏感度等简化标注 | 校准多因子模型 |
| 缺 beta/行业时 `partial` | Web UI |
| 复用 risk-metrics 集中度纯函数 | Agent / 报告嵌入 |

**本轮模拟方法：** 仅 `deterministic_factor_shock`。响应中 `historical_replay_available` 恒为 `false`。

## 端点

```http
GET  /api/v1/portfolio/stress-test/scenarios
GET  /api/v1/portfolio/stress-test?scenario_id=market_down_10
POST /api/v1/portfolio/stress-test
```

认证与相邻 `/api/v1/portfolio/*` 一致。

详细公式、内置情景表与假设清单见英文版：[`portfolio-stress-test_EN.md`](portfolio-stress-test_EN.md)。

## 实现映射

| 组件 | 路径 |
| --- | --- |
| 情景目录 | `src/services/portfolio_stress_scenarios.py` |
| 服务 | `src/services/portfolio_stress_test_service.py` |
| 端点 | `api/v1/endpoints/portfolio_stress_test.py` |
| Schema | `api/v1/schemas/portfolio_stress_test.py` |
| 服务测试 | `tests/services/test_portfolio_stress_test_service.py` |
| API 测试 | `tests/api/test_portfolio_stress_test_api.py` |
