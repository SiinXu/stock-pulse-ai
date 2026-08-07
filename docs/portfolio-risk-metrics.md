# 组合风险指标（V0）

面向已持仓组合的后端风险指标（[#239](https://github.com/SiinXu/stock-pulse-ai/issues/239)）。

本文档说明 `GET /api/v1/portfolio/risk-metrics` 的公式、假设与财务诚实规则。
Web 组合页可视化不在 V0 范围（PortfolioPage 由独立重构 PR 占用）。

## 范围

| 包含 | 不包含（后续） |
| --- | --- |
| 历史法 VaR（经验分布） | 参数法 / 蒙特卡洛 VaR |
| 收益两两 Pearson 相关矩阵 | 行业风险贡献图 |
| 集中度 HHI + 分散化得分 | 压力测试（#210）集成 |
| 仅用**已落库**日线的只读 API | 热路径实时拉行情 |
| 明确的「历史不足」状态 | 报告嵌入 / 通知 |

本模块**补充**既有组合风险报告
（`GET /api/v1/portfolio/risk`：集中度告警、回撤、止损邻近、决策信号风险），
不替换该端点。

## 端点

```http
GET /api/v1/portfolio/risk-metrics
```

查询参数：

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `account_id` | 全部活跃账户 | 可选 |
| `as_of` | 今天 | 快照 / 历史截止日 |
| `cost_method` | `fifo` | 传给组合快照 |
| `confidence` | `0.95` | 开区间 `(0.5, 1.0)` |
| `horizon_days` | `1` | `1..30`；多日用 √时间缩放 |
| `lookback_trading_days` | `252` | 请求的收盘价天数（`60..1000`） |

鉴权与相邻 `/api/v1/portfolio/*` 一致（启用时走全局管理员会话）。

## 数据输入（热路径不调 Provider）

1. **持仓 / 权重** — `PortfolioService.get_portfolio_snapshot(..., include_realtime=False)`。
2. **日线收盘** — `StockRepository.get_range` 读取已存储的 `stock_daily`。

现金不参与权重。权重为权益仓位的市值占比（`market_value_base`），归一化后和为 1.0。

## 公式与假设

### 简单收益率

对每个标的，在相邻共同交易日 \(t-1, t\) 上：

\[
r_{i,t} = \frac{P_{i,t}}{P_{i,t-1}} - 1
\]

日期在**全部持仓标的之间做内连接**，保证每个观测日使用同一日历。

### 组合收益（静态当前权重）

\[
R_t = \sum_i w_i \, r_{i,t}
\]

权重 \(w_i\) 取**当前**快照权重，并在回看窗口内保持不变（非逐日历史再平衡）。
这是 V0 有意简化，并在响应 `assumptions` 中披露。

### 历史法 VaR

置信水平 \(c\)（默认 \(0.95\)）：

1. 对 \(\{R_t\}\) 取经验左尾分位 \(\alpha = 1 - c\)（NumPy 线性分位插值）。
2. 一日 VaR 为**正的损失比例**：
   \(\mathrm{VaR}_{1d} = \max(0, -Q_\alpha(R))\)。
3. 百分点：\(\mathrm{var\_pct} = 100 \cdot \mathrm{VaR}_{h}\)。
4. 币种损失：\(\mathrm{var\_value} = \mathrm{VaR}_{h} \cdot V\)，\(V\) 为当前权益市值。

**持有期缩放（`horizon_days` > 1）：**

\[
\mathrm{VaR}_{h} = \mathrm{VaR}_{1d} \cdot \sqrt{h}
\]

假设收益**独立同分布 / 日收益独立**。这不是完整多日历史模拟；V0 明确披露该假设。

**分布假设：** 仅经验历史分布。历史法 VaR **不**假设正态。

### 最少历史长度

| 指标 | 最少对齐收益观测数 |
| --- | --- |
| 历史法 VaR | 60 |
| 相关矩阵 | 30 |

历史不足时，API 返回 `status: insufficient_history`（或分块状态），且
**`var_pct` / `var_value` 为 null**，绝不静默填 0 伪装成「无风险」。

### 相关矩阵

对齐简单收益的 Pearson 相关。对角线为 `1.0`。若某序列方差为 0，非对角元为
`null`（不强制写成 0）。

### 集中度与分散化

权重 \(w_i\)（分数，和为 1），持仓数 \(n\)：

\[
\mathrm{HHI} = \sum_i w_i^2, \quad
N_{\mathrm{eff}} = \frac{1}{\mathrm{HHI}}
\]

\[
\mathrm{diversification\_score} =
\begin{cases}
0 & n \le 1 \\
\dfrac{1 - \mathrm{HHI}}{1 - 1/n} & n > 1
\end{cases}
\]

等权组合得分为 `1.0`；单一 100% 仓位为 `0.0`。
`top_weight_pct` 为 \(\max_i w_i \times 100\)。

## 状态诚实约定

| 整体 / 分块 status | 含义 |
| --- | --- |
| `ok` | 指标已计算 |
| `empty_portfolio` | 无正市值权益持仓 |
| `insufficient_history` | 对齐历史低于文档最低要求 |
| `unavailable` | 不适用（如空组合，或相关矩阵持仓 &lt; 2） |
| `partial` | 部分块成功、部分失败 |

`assumptions` 始终返回，包含方法、回看窗口、持有期缩放、是否排除现金，以及
`provider_calls_on_hot_path: false`。

## 实现映射

| 组件 | 路径 |
| --- | --- |
| 服务 | `src/services/portfolio_risk_metrics_service.py` |
| 端点 | `api/v1/endpoints/portfolio_risk_metrics.py` |
| Schema | `api/v1/schemas/portfolio_risk_metrics.py` |
| 服务测试 | `tests/services/test_portfolio_risk_metrics_service.py` |
| API 测试 | `tests/api/test_portfolio_risk_metrics_api.py` |

## 后续（非 V0）

- Web 组合页可视化（在 #239 留言跟进；受 PortfolioPage 所有权约束）。
- 参数法 VaR、风险贡献、行业拆分。
- 与压力测试（#210）、资产配置（#237）集成。
