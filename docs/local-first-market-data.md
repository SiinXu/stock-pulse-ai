# 本地优先行情存储

本文说明基于既有分层日线缓存（`data_provider/daily_cache.py`）的**行情数据**本地优先模式。

它与隐私出站开关 `LOCAL_ONLY_MODE`（见 `docs/local-only-mode.md`）**不是同一配置**：后者在出站策略层拦截非回环 HTTP。需要「离线 K 线 + 不上云 LLM」时，应有意识地同时配置两个开关。

## 存储选型

| 选择 | 理由 |
| --- | --- |
| 复用 L1 进程内存 + L2 原子 JSON 表（`PROVIDER_DAILY_CACHE_DIR`） | 已在 provider manager 日线缓存中落地；不引入新数据库或依赖 |
| 不新增 SQLite/Redis | 保持桌面与低门槛安装路径一致 |

该存储只保存 OHLCV 类帧、来源名与时间戳，**不**写入密钥。

## 三档模式（`PROVIDER_MARKET_DATA_MODE`）

| 模式 | 取值 | 行为 |
| --- | --- | --- |
| 自动（默认） | `auto` | 优先**新鲜**本地数据；未命中允许回源，成功结果写回本地。与历史「加速缓存」行为等价。 |
| 仅本地 | `local_only` | **只**用本地库（含已过期新鲜窗口的条目）。缺失时抛出带结构化载荷的 `LocalDataMissingError`。**绝不**调用网络回调。 |
| 强制刷新 | `refresh` | 始终回源并更新本地；不返回纯缓存命中。 |

未设置或非法值回退为 `auto`，保证现有部署零配置兼容。

```env
# 默认 —— 对现有用户无行为变化
# PROVIDER_MARKET_DATA_MODE=auto

# 离线 / 隐私数据路径：只从本地库提供日线
# PROVIDER_MARKET_DATA_MODE=local_only

# 强制回源并回填本地库
# PROVIDER_MARKET_DATA_MODE=refresh
```

`PROVIDER_DAILY_CACHE_*` 的 TTL 仍控制 `auto` 的新鲜度与 stale-if-error。在 `local_only` 下，本地有条目即可服务；结果上的 `is_stale` 表示是否超过持久化 TTL，便于诚实展示新鲜度而不上网。

## 结构化缺失（`local_only`）

本地无法满足请求时：

```json
{
  "symbol": "AAPL",
  "start_date": "2026-06-01",
  "end_date": "2026-07-01",
  "days": 20,
  "fields": ["daily_ohlcv", "volume"],
  "mode": "local_only",
  "reason": "no_local_entry"
}
```

| 字段 | 含义 |
| --- | --- |
| `symbol` | 请求标的（规范化后） |
| `start_date` / `end_date` / `days` | 请求窗口（未提供时为空字符串） |
| `fields` | 所需逻辑字段（默认 `daily_ohlcv`） |
| `mode` | 本错误路径恒为 `local_only` |
| `reason` | `no_local_entry` 或 `cache_disabled` |

Python 异常：`data_provider.daily_cache.LocalDataMissingError`（`.missing` / `.to_dict()`）。

## 数据层公共 API

```python
from data_provider.daily_cache import (
    DailyCacheKey,
    DailyDataCache,
    LocalDataMissingError,
    MarketDataFetchMode,
)

cache = DailyDataCache.from_env()
key = DailyCacheKey(symbol="600519", start_date="", end_date="", days=30)

try:
    result = cache.resolve(
        key,
        network_fetch=lambda: upstream_get_daily(key),  # local_only 下永不调用
        required_fields=("daily_ohlcv",),
    )
except LocalDataMissingError as exc:
    print(exc.to_dict())
```

辅助方法：

- `lookup` / `store` / `use_stale` —— manager 现用的加速缓存契约，保持不变
- `lookup_local_store` —— 忽略新鲜 TTL，返回任意本地条目
- `resolve` —— 按模式编排的本地优先解析

## 与 `DataFetcherManager` 的接线

本变更在 `daily_cache.py` 交付存储、模式、错误、测试与配置（并行批次所有权）。接入 `DataFetcherManager.get_daily_data` 属于合并后的短接线：

1. 构建 `cache_key` / `daily_cache` 后调用 `daily_cache.resolve(...)`，`network_fetch` 包装既有 provider 链；或
2. 按 `daily_cache.fetch_mode` 分支：
   - `local_only` → `lookup_local_store` / 抛 `LocalDataMissingError`
   - `refresh` → 跳过新鲜命中，始终走 provider，再 `store`
   - `auto` → 保持现有 lookup → provider → store / stale 路径

在接线落地前，仅设置 `PROVIDER_MARKET_DATA_MODE` **不会**改变 `get_daily_data` 运行时路径；调用方与测试可直接使用 `DailyDataCache.resolve`。

## 与 `LOCAL_ONLY_MODE`（出站隐私）的关系

| 开关 | 层级 | 效果 |
| --- | --- | --- |
| `PROVIDER_MARKET_DATA_MODE=local_only` | 行情本地库 | `resolve` 不回源；结构化本地缺失 |
| `LOCAL_ONLY_MODE=true` | 出站 HTTP 策略 | 拦截所有非回环目标 |

完整隐私离线配置建议两者同时开启。

## 剩余范围（本变更不做）

- LLM / Ollama 本地模型偏好（#159 剩余 / T28）
- Web 缓存状态展示
- 自选股预取 / cache warming
- 各 fetcher 抓取实现改动

## 验证

```bash
python -m pytest tests/data_provider/test_local_first_store.py tests/data_provider/test_daily_provider_cache.py -m "not network"
```

`local_only` 测试断言网络回调永不被调用，并在缺失路径上禁止构造 `socket.socket`。
