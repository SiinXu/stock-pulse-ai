# 组合每日健康分（V1）

面向已持仓组合的**确定性**每日健康分与可执行洞察（[#151](https://github.com/SiinXu/stock-pulse-ai/issues/151)）。

本文档给出评分公式与权重，便于第三方复算。  
**这是组合结构度量，不是投资建议。**

Web 组合页可视化不在本范围（组合 Web 层由独立 PR 占用）。

## 范围

| 包含 | 不包含 |
| --- | --- |
| 五维规则子分 + 显式权重总分 | Web 展示 |
| 规则洞察（含标的与阈值） | 压力测试 |
| 日快照幂等 upsert | 通知推送 |
| `partial` 数据质量透传 | 重算 VaR / 相关矩阵 |
| 可选 LLM 仅润色洞察文案 | LLM 改分 |

输入全部来自已有模块：

1. `PortfolioService.get_portfolio_snapshot(..., include_realtime=False)`
2. `PortfolioRiskMetricsService.get_risk_metrics(...)`（只调用，不修改）

## 端点

```http
GET /api/v1/portfolio/health
```

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `account_id` | 全部活跃账户 | 可选 |
| `as_of` | 今天 | 快照日 |
| `cost_method` | `fifo` | 传给组合快照 |
| `persist` | `true` | 是否按日幂等写入快照（覆盖同日） |

鉴权与相邻 `/api/v1/portfolio/*` 一致。

响应中硬合同字段：

- `score_source`: 恒为 `"rules"`
- `llm_can_modify_score`: 恒为 `false`
- `disclaimer`: 结构度量声明

## 权重（默认）

| 维度 | 权重 | 环境变量覆盖（可选） |
| --- | --- | --- |
| `concentration` | 0.25 | `PORTFOLIO_HEALTH_WEIGHT_CONCENTRATION` |
| `risk_exposure` | 0.25 | `PORTFOLIO_HEALTH_WEIGHT_RISK_EXPOSURE` |
| `diversification` | 0.20 | `PORTFOLIO_HEALTH_WEIGHT_DIVERSIFICATION` |
| `pnl` | 0.15 | `PORTFOLIO_HEALTH_WEIGHT_PNL` |
| `cash_ratio` | 0.15 | `PORTFOLIO_HEALTH_WEIGHT_CASH_RATIO` |

权重在使用前归一化为和 1.0。  
若某维度因数据不足记为不可用，则在**剩余可用维度**上重新归一化后加权。

## 子分公式（均为 0–100，越高越健康）

### 1. concentration（集中度）

输入：风险指标 `concentration.top_weight_pct`（最大单一持仓市值权重 %）。

\[
s_{\mathrm{conc}} =
\begin{cases}
100 & w_{\mathrm{top}} \le 15 \\
0 & w_{\mathrm{top}} \ge 50 \\
100 \cdot \dfrac{50 - w_{\mathrm{top}}}{50 - 15} & \text{otherwise}
\end{cases}
\]

### 2. risk_exposure（风险暴露）

输入：历史法 1 日 VaR 百分点 `var.var_pct`（正损失）。

\[
s_{\mathrm{risk}} =
\begin{cases}
100 & \mathrm{VaR} \le 1 \\
0 & \mathrm{VaR} \ge 8 \\
100 \cdot \dfrac{8 - \mathrm{VaR}}{8 - 1} & \text{otherwise}
\end{cases}
\]

VaR 状态非 `ok` 或 `var_pct` 为 null 时，该维度 **unavailable**，**不会**用 0 冒充无风险。

### 3. diversification（分散度）

输入：`concentration.diversification_score`（∈ [0,1]，等权 → 1.0）。

\[
s_{\mathrm{div}} = 100 \cdot d
\]

### 4. pnl（盈亏）

输入：未实现盈亏占权益比例  
\(p = 100 \cdot \mathrm{unrealized\_pnl} / \mathrm{total\_equity}\)。

分段线性：

| \(p\) | 子分 |
| --- | --- |
| \(p \ge 10\) | 100 |
| \(0 \le p < 10\) | \(70 + 30 \cdot p / 10\) |
| \(-30 < p < 0\) | \(70 \cdot (1 - \|p\| / 30)\) |
| \(p \le -30\) | 0 |

价格缺失 / 汇率陈旧时该维度 **unavailable**。

### 5. cash_ratio（现金比例）

输入：\(c = 100 \cdot \mathrm{total\_cash} / \mathrm{total\_equity}\)。

| \(c\) | 子分 |
| --- | --- |
| \(5 \le c \le 25\) | 100（理想带） |
| \(0 \le c < 5\) | \(100 \cdot c / 5\) |
| \(25 < c < 80\) | \(100 \cdot (80 - c) / (80 - 25)\) |
| \(c \ge 80\) 或 \(c \le 0\) | 0 |

`fx_stale` 时该维度 **unavailable**。

## 总分与分档

对可用维度 \(i\)，有效权重 \(w'_i = w_i / \sum_{j \in \mathrm{avail}} w_j\)：

\[
S = \sum_{i \in \mathrm{avail}} w'_i \, s_i
\]

| 分档 | 分数区间 |
| --- | --- |
| `healthy` | \[80, 100\] |
| `fair` | \[60, 80) |
| `caution` | \[40, 60) |
| `poor` | \[0, 40) |

## 状态诚实约定

| status | 含义 |
| --- | --- |
| `ok` | 五维均已计分 |
| `partial` | 至少一维缺失或快照数据质量 partial；总分仅用可用维 |
| `empty_portfolio` | 无正市值权益持仓；`score` 为 null |
| `unavailable` | 无任何可用维 |

## 洞察

规则引擎生成，每条尽量包含：

- 具体标的（若适用）
- 指标当前值
- 阈值
- 可执行建议措辞

默认阈值（可用环境变量覆盖）：

| 洞察 | 默认阈值 | 环境变量 |
| --- | --- | --- |
| 单票集中度 | 35% | `PORTFOLIO_HEALTH_CONCENTRATION_ALERT_PCT`（回退 `PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT`） |
| VaR | 5% | `PORTFOLIO_HEALTH_VAR_ALERT_PCT` |
| 分散度 | 0.35 | `PORTFOLIO_HEALTH_DIVERSIFICATION_ALERT` |
| 现金过低 | 2% | `PORTFOLIO_HEALTH_CASH_LOW_ALERT_PCT` |
| 现金过高 | 50% | `PORTFOLIO_HEALTH_CASH_HIGH_ALERT_PCT` |
| 未实现亏损 | -15% | `PORTFOLIO_HEALTH_PNL_LOSS_ALERT_PCT` |

### LLM 合同

可选注入的 LLM 润色**只能**改 `insights[].message`。  
`score`、`band`、`dimensions`、`value`、`threshold`、`symbol`、`severity`、`code` 一律以规则结果为准。  
测试断言：即使提供恶意 polisher，分数与指标字段不变。

## 日快照幂等

表 `portfolio_health_snapshots`，唯一键：

`(account_key, snapshot_date, cost_method)`

- `account_key` = `str(account_id)` 或 `all`
- 同日重复计算 **覆盖** 而非追加

## 实现映射

| 组件 | 路径 |
| --- | --- |
| 服务 | `src/services/portfolio_health_service.py` |
| 仓储 | `src/repositories/portfolio_health_repo.py` |
| 端点 | `api/v1/endpoints/portfolio_health.py` |
| Schema | `api/v1/schemas/portfolio_health.py` |
| 迁移 | `src/migrations/versions/v202608090001_portfolio_health_snapshots.py` |
| 服务测试 | `tests/services/test_portfolio_health_service.py` |
| API 测试 | `tests/api/test_portfolio_health_api.py` |

## 复算示例

设：

- \(w_{\mathrm{top}}=20\), \(\mathrm{VaR}=2\), \(d=0.9\), \(p=5\), \(c=15\)
- 默认权重

则：

- \(s_{\mathrm{conc}} = 100 \cdot (50-20)/35 \approx 85.7143\)
- \(s_{\mathrm{risk}} = 100 \cdot (8-2)/7 \approx 85.7143\)
- \(s_{\mathrm{div}} = 90\)
- \(s_{\mathrm{pnl}} = 70 + 30 \cdot 5/10 = 85\)
- \(s_{\mathrm{cash}} = 100\)

\[
S \approx 0.25\cdot85.7143 + 0.25\cdot85.7143 + 0.20\cdot90 + 0.15\cdot85 + 0.15\cdot100
\approx 88.57
\]

分档：`healthy`。
