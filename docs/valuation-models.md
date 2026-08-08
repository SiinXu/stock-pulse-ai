# 估值模型（DCF 与相对估值）— Phase 1

StockPulse 可通过透明的 DCF 模型与同业相对估值（P/E、P/B）估算内在价值。本文描述
issue #238 的 **第一阶段**：后端估值服务 + 默认关闭的可选 Agent Tool。

报告模板投影、默认分析链路 Prompt 注入、以及 EV/EBITDA 相对估值属于后续阶段。

## 诚实性契约

每一条估值结果都会：

- 附带**显式假设**（增长、折现、永续增长、预测年限、现金流来源、同业集合）；
- 提供 DCF 股权价值的 **增长 × 折现敏感性区间**；
- 在关键输入缺失时返回 `insufficient_fundamentals`，**绝不编造**现金流基数、
  同业倍数或内在价格。

强制免责声明：结果仅供研究辅助，不构成投资建议。

## 默认与注册契约

Agent Tool `estimate_stock_valuation` **默认关闭**。

| 条件 | 行为 |
| --- | --- |
| `VALUATION_AGENT_TOOL_ENABLED=false`（默认） | 工厂返回 `None`，进程工具目录不包含该工具 |
| `VALUATION_AGENT_TOOL_ENABLED=true` | 进程重启后 `build_valuation_tool(config)` 完成注册 |
| Multi-agent Risk Agent | 仅在进程目录已注册时暴露该工具 |
| Single-agent / 全量目录 | 注册后与其他工具一同可用 |

启用开关后需要重启进程，以便重建缓存的工具注册表。关闭时默认分析、报告、通知、
Docker 与桌面端行为保持不变。

## 数据边界

基本面与行情**仅**通过现有 `DataFetcherManager` 接口消费
（`get_fundamental_context`、`get_realtime_quote`）。Phase 1 不新增 fetcher 文件，
也不绕过 provider 回退链路。

DCF 现金流优先级：

1. 盈利块中为正的 `operating_cash_flow`
2. 否则使用为正的 `net_profit_parent` 作为显式代理（来源写入 assumptions）
3. 否则 `insufficient_fundamentals`

增长默认取可用营收/净利同比中更保守者（带上限），否则使用文档化常量。调用方可覆盖
增长、折现、永续增长与预测年限。

## DCF 模型

两阶段结构：

1. 在高增长阶段按增长率为 `projection_years` 年投影自由现金流
2. 永续增长终值：`FCF_{n+1} / (r - g_term)`
3. 以折现率贴现投影现金流与终值
4. 在净债务不可得时，股权价值等于企业价值，并在假设中明确写明

敏感性表：增长偏移 `{-2pp, 0, +2pp}` × 折现偏移 `{-1pp, 0, +1pp}` 的股权价值网格，
并保证各情景的永续增长率严格低于该情景折现率。

## 相对估值

- 目标 P/E、P/B 来自基本面 / 行情
- 可选同业代码（逗号分隔）；对**正**倍数取中位数
- 隐含价格：`EPS × 同业 PE 中位`、`每股净资产 × 同业 PB 中位`
- 无同业或倍数缺失 → 相对估值段 `insufficient_fundamentals`（不编造同业）
- Phase 1 **不**估计 EV/EBITDA（跨市场尚无稳定 EBITDA 字段）

## 工具输入 / 输出

| 字段 | 契约 |
| --- | --- |
| `stock_code` | 必填；股票作用域；与其他行情工具相同的可移植代码 |
| `growth_rate` | 可选小数；省略则从基本面自动推导 |
| `discount_rate` | 可选小数；默认 `0.10` |
| `terminal_growth_rate` | 可选小数；默认 `0.03`；必须 `< discount_rate` |
| `projection_years` | 可选整数 `1..15`；默认 `5` |
| `peer_codes` | 可选逗号分隔同业代码 |

输出 schema：`valuation-estimate-v1`。

顶层包含 `status`（`ok` / `partial` / `insufficient_fundamentals`）、`dcf`、
`relative`、`fundamentals_snapshot` 与 `disclaimer`。各模型段内嵌 `assumptions`，
DCF 另含 `sensitivity`。

策略：只读、`market_data:read`、股票作用域、`enforce_contract=True`。

## 配置

```bash
# .env — 默认关闭
VALUATION_AGENT_TOOL_ENABLED=false
```

Web 设置 → Agent 中有同名开关。保存后需重启进程才能完成注册。

## 验证

```bash
python -m py_compile src/services/valuation_service.py src/agent/tools/valuation_tools.py
python -m pytest tests -k "valuation or dcf" -m "not network and not benchmark"
```

## 后续阶段（不在 Phase 1）

- 报告 / Prompt 投影估值块
- 跨市场 EBITDA 字段可用后的 EV/EBITDA
- Web 交互式敏感性 UI
- 超出通用 DCF / PE-PB 的市场专用模型包

## 回滚

1. 设置 `VALUATION_AGENT_TOOL_ENABLED=false`（或删除该变量）
2. 重启进程
3. 工具从注册表消失；分析主路径无行为变化
