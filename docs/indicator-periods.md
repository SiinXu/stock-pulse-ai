# 可配置技术指标周期

Issue #172 通过环境变量 / Settings 配置趋势分析所用的技术指标周期，并支持 120 / 250 等长周期均线。

## 默认值（向后兼容）

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `INDICATOR_MA_PERIODS` | `5,10,20,60` | 前四个映射到兼容字段 `ma5` / `ma10` / `ma20` / `ma60` |
| `INDICATOR_MACD_FAST` | `12` | 必须小于 slow |
| `INDICATOR_MACD_SLOW` | `26` | |
| `INDICATOR_MACD_SIGNAL` | `9` | DEA 周期 |
| `INDICATOR_RSI_PERIODS` | `6,12,24` | 前三个映射到 `rsi_6` / `rsi_12` / `rsi_24` |

使用默认值且 K 线充足时，MA / MACD / RSI 数值与配置化之前的公式结果一致。

## 校验

- 周期必须为正整数。
- 均线：1–500，`INDICATOR_MA_PERIODS` 需 3–16 个不重复值。
- RSI：1–250。
- MACD fast 必须严格小于 slow。
- 非法环境变量会打警告并回退默认值，保证进程可启动。
- Settings 写入路径应通过注册表校验拒绝非法值。

## 数据不足

当 `period > 可用 K 线数` 时：

- `ma_by_period[period]` 为 `None`
- 兼容 float 槽位为 `0.0`
- `risk_factors` 写入明确的 `MAn: insufficient data (...)` 说明
- **不会**用更短周期静默顶替（已移除旧的 MA60←MA20 行为）

## 历史取数窗口

个股流水线中的趋势分析取数窗口随最长配置周期放大（`max(均线, MACD slow+signal, RSI)`），再按约 1.8× 交易日 + 10 天换算为自然日。

`src/services/stock_daily_window_resolver.py` 用于**回测评估窗口**，与指标计算无关，本任务无需修改。

## 范围说明 / 集成点

- `data_provider` 日线 `ma5/ma10/ma20` 列仍为硬编码（数据源任务负责）。
- Agent 工具 `calculate_ma` 仍接受调用参数中的周期字符串；本批未改 `src/agent/`。
- 报告模板仍显示 MA5/MA10/MA20 等槽位名；自定义周期时槽位名是兼容标签。

## 示例

```bash
INDICATOR_MA_PERIODS=5,10,20,60,120,250
INDICATOR_MACD_FAST=8
INDICATOR_MACD_SLOW=17
INDICATOR_MACD_SIGNAL=5
INDICATOR_RSI_PERIODS=7,14,21
```
