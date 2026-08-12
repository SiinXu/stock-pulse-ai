# Prediction `resolve_after` 交易日历策略

Issue **#1109**（Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107) Agent Evolution A6）。

本页说明预测验证链路如何把 horizon 换算为 UTC `resolve_after`，以及 A 股 / 港股 / 美股交易日、时区、节假日与半日市规则。实现入口：

- 模块：`src/core/prediction_resolve_after.py`
- 函数：`compute_resolve_after(market, created_at, horizon, as_of_policy=...)`
- 复用：`src/core/trading_calendar.py`（`MARKET_EXCHANGE` / `MARKET_TIMEZONE` / `get_effective_trading_date` / `exchange-calendars`）

**硬规则：不得用自然日近似交易日。** 日历不可用时 fail-closed，返回 `CalendarUnavailableError`（`calendar_approx` 恒为 `false`），由上游记 `data_unavailable` / 重试，永不伪造到期时间。

English: [prediction-resolve-after_EN.md](prediction-resolve-after_EN.md)

---

## 定位与边界

| 属于本模块 | 不属于本模块 |
| --- | --- |
| horizon → UTC `resolve_after` 换算 | `PredictionRecord` 落库（#1101 / #1112） |
| 按交易所 session 跳过周末/节假日 | Actuals 拉取与打分（#1110 / #1111） |
| 半日市使用真实 `session_close` | 调度 tick / 批量 resolver（#1116 / #1104） |
| 跨市场规则与文档 | 运行时改 Soul / ToolSurface |

产品规则（Epic #1107）：系统驱动验证；研究/质量运营定位；provider 失败只能是 `data_unavailable`/重试，永不伪造命中。

---

## API 契约

```python
from src.core.prediction_resolve_after import compute_resolve_after, AsOfPolicy

result = compute_resolve_after(
    market="cn",                          # 权威市场键：cn | hk | us | …
    created_at=created_at_utc,            # aware 优先；naive 视为 UTC
    horizon="5d",                         # Nd 交易 session，或正整数
    as_of_policy=AsOfPolicy.TRADING_DAY_CLOSE,
    stock_code="600519",                  # 可选：校验与 market 一致
    allow_cross_market=False,
)
# result.resolve_after  -> timezone-aware UTC datetime
# result.to_dict()      -> 可写入 model_meta / 诊断
```

### `as_of_policy`

| 策略 | 含义 |
| --- | --- |
| `trading_day_close`（默认） | 按交易所交易日推进 N 个 **session**，`resolve_after` = 目标 session 的 **收盘时刻**（UTC） |
| `explicit_timestamp` | horizon 为绝对时间（`datetime` / ISO 字符串 / `date`→当日 00:00 UTC）；不走 session 推进 |

### Horizon 语义（`trading_day_close`）

1. **锚点 session（anchor）**：对 `created_at` 调用 `get_effective_trading_date`——取**最近已完成**交易日 bar 日期（盘中取前一 session，收盘后取当日 session，非交易日取上一 session）。与分析日线/DecisionSignal outcome 的 completed-bar 语义对齐。
2. **目标 session**：`session_offset(anchor, N)`，即 anchor **之后**第 N 个交易所 session（`1d`/`5d`/`20d` 等）。
3. **`resolve_after`**：目标 session 的 `session_close`，转为 UTC 存储。

因此 `1d` **不是**「自然日 +1」，而是「下一根可交易日线收盘后才允许验证」。

不支持：`swing` / `long` / 散文 horizon；crypto 的 trading-day 策略（应使用 `explicit_timestamp`）。

---

## 市场、时区与交易所代码

| 市场键 | 交易所（exchange-calendars） | IANA 时区 | 常规收盘（本地，示意） |
| --- | --- | --- | --- |
| `cn` | `XSHG` | `Asia/Shanghai` | 15:00 |
| `hk` | `XHKG` | `Asia/Hong_Kong` | 16:00 |
| `us` | `XNYS` | `America/New_York` | 16:00（受夏令时影响，存 UTC 时安全） |

实现复用 `trading_calendar.MARKET_EXCHANGE` / `MARKET_TIMEZONE`，不另造日历表。日股/韩股/台股若已在日历模块注册，可按同一函数调用；本 issue 验收以 **A 股 / 港股 / 美股** 为主。

---

## 节假日、周末与半日市

| 场景 | 行为 |
| --- | --- |
| 周末 | `session_offset` 只落在交易所 session 上，不会落到周六/日 |
| 节假日（如 A 股国庆、美股 Thanksgiving、港股圣诞） | 闭市日不是 session；N 日推进自动跳过 |
| 半日市 / early close（如美股 7/3、港股 12/24） | 使用日历返回的真实 `session_close`，并在结果中标记 `is_early_close=true` |
| 夏令时（美股） | 本地收盘时刻经 `America/New_York` 转 UTC；结果 `tzinfo` 为 UTC |

**禁止**：`created_at + timedelta(days=N)`、business-day 近似、或在日历失败时写 `calendar_approx=true` 的自然日 fallback。

---

## 跨市场标的规则

1. **`market` 字段权威**：session 数学只使用 Prediction 上的 `market`，不用服务器本地时区推断市场。
2. **可选 `stock_code` 校验**：若代码解析出的市场与 `market` 不一致，默认抛 `CrossMarketMismatchError`。ADR/多地上市等需显式 `allow_cross_market=True`，并由调用方保证 `market` 选择正确。
3. **禁止混用日历**：港股代码不得用 `XSHG` 推进；美股不得用 A 股自然假日表。
4. **组合内多标的**：每条预测独立按自身 `market` 计算 `resolve_after`；到期扫描按各自 UTC 时间比较。
5. **裸码歧义**：6 位数字默认 A 股语义属于代码识别层（见 [market-support.md](market-support.md)）；resolve 层不二次猜测。

---

## 日历不可用时

| 条件 | 结果 |
| --- | --- |
| 未安装 `exchange-calendars` | `CalendarUnavailableError` / `calendar_unavailable` |
| 加载交易所失败 / session 越界 | `CalendarUnavailableError` 及对应 `error_code` |
| 不支持的 market / crypto + trading_day_close | `UnsupportedMarketError` |
| 非法 horizon | `InvalidHorizonError` |

上游（A1 契约写入、A3 持久化、A7 调度）应：

- 不写入伪造的 `resolve_after`；
- 将状态/诊断记为 `data_unavailable` 或延迟创建 pending 记录；
- 在日历恢复后重试计算。

Issue 原文曾提及「日历缺失时自然日近似 + `calendar_approx=true`」。本仓库 **明确拒绝** 该 fallback，与 Epic「永不伪造」一致。

---

## 与 DecisionSignal 过期的差异

| | Prediction `resolve_after`（本模块） | DecisionSignal `expires_at` |
| --- | --- | --- |
| 日线 horizon | **交易所 session** 计数 | 部分路径仍为自然日 TTL（历史兼容） |
| 目的 | 到点拉 actuals 并打分 | 信号卡片过期展示 |
| 日历失败 | fail-closed | 既有 fallback TTL |

后验评估里 DecisionSignal 的 outcome 已按 `StockDaily` 交易 bar 计数；本模块与之对齐的是 **session 语义**，不是其展示用 expires 自然日路径。

---

## 验证

```bash
python -m pytest tests/core/test_prediction_resolve_after.py -q
```

覆盖：CN 周末/国庆、HK 圣诞/半日市、US Thanksgiving/early close/跨时区与 DST、日历不可用 fail-closed、跨市场校验。

---

## 回滚

Revert 引入 `src/core/prediction_resolve_after.py` 与对应测试/文档的提交即可；无数据库迁移、无配置项、无用户数据回填。
