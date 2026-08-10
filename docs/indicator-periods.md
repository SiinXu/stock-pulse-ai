# 可配置技术指标周期

本变更为 Issue #172 建立全局配置基础：通过环境变量 / Settings 配置趋势分析所用的技术指标周期，并支持 120 / 250 等长周期均线。

## 默认值（向后兼容）

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `INDICATOR_MA_PERIODS` | `5,10,20,60` | 动态输出按真实配置周期标记 |
| `INDICATOR_MACD_FAST` | `12` | 必须小于 slow |
| `INDICATOR_MACD_SLOW` | `26` | |
| `INDICATOR_MACD_SIGNAL` | `9` | DEA 周期 |
| `INDICATOR_RSI_PERIODS` | `6,12,24` | 动态输出按真实配置周期标记 |

使用默认值且 K 线充足时，MA / MACD / RSI 数值与配置化之前的公式结果一致。

## 校验

- 周期必须为正整数。
- 均线：1–500，`INDICATOR_MA_PERIODS` 需 3–16 个不重复值。
- RSI：1–250，需 1–8 个不重复值。
- MACD：1–200。
- MACD fast 必须严格小于 slow。
- 只有缺失或空值使用默认值；显式格式错误、重复、越界或 fast/slow 倒置会在启动、导入/运行时构造与 Settings 保存路径中按同一规则拒绝。

## 数据不足

当 `period > 可用 K 线数` 时：

- `ma_by_period[period]` 为 `None`
- 对应动态读数的 `value` 为 `null`、`available` 为 `false`，并携带原因、K 线数与截止日期
- `ma60` 等精确兼容字段在自身周期不可用时为 `None`
- `risk_factors` 写入明确的 `MAn: insufficient data (...)` 说明
- **不会**用更短周期静默顶替（已移除旧的 MA60←MA20 行为）

## 历史取数窗口

经典个股流水线与 Agent 工具的趋势分析取数窗口都会随最长配置周期放大（`max(均线, MACD slow+signal, RSI)`），再按约 1.8× 交易日 + 10 天换算为自然日。断点续传会同时检查目标交易日与所需 K 线覆盖，数据库仅有近期数据时会先回补，再计算 MA250 等长周期指标。

`src/services/stock_daily_window_resolver.py` 用于**回测评估窗口**，与指标计算无关，本任务无需修改。

## 兼容与范围

- `data_provider` 日线 `ma5/ma10/ma20` 列仍为硬编码（数据源任务负责）。
- `ma5` / `ma10` / `ma20` / `ma60` 与 `rsi_6` / `rsi_12` / `rsi_24` 始终表示各自真实周期，不按自定义列表位置改名。
- Prompt、报告、通知、API 载荷与 Agent 趋势工具同时携带动态类型化快照，包含真实标签、可用状态、来源、K 线数与截止日期。
- 本变更只实现全局 Settings 优先级（`默认值 < 全局 Settings`）。策略 YAML 覆盖仍由 Issue #172 后续完成，本变更不宣称关闭该 Issue。

## 示例

```bash
INDICATOR_MA_PERIODS=5,10,20,60,120,250
INDICATOR_MACD_FAST=8
INDICATOR_MACD_SLOW=17
INDICATOR_MACD_SIGNAL=5
INDICATOR_RSI_PERIODS=7,14,21
```
