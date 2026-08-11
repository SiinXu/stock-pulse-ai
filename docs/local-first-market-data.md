# 本地优先日线行情

`DataFetcherManager.get_daily_data` 是本地优先日线契约的运行时唯一编排入口。它继续复用既有 provider 的市场路由、优先级、插件、健康度/熔断、诊断和逐源回退；缓存不会建立第二条 provider 调用链。

此功能与 `docs/local-only-mode.md` 中的 `LOCAL_ONLY_MODE` 相互独立：`PROVIDER_MARKET_DATA_MODE` 管理日线数据，`LOCAL_ONLY_MODE` 是进程级非回环 HTTP 出站策略。需要整个进程离线时应同时启用两者。

在 `local_only` 模式下，分析流水线也会跳过批量日线/实时行情预取及依赖 provider 的股票名称补全；已有内存名称、静态指数名称与本地日线存储仍可使用。因此，包含至少五个标的的批次不会在逐标的本地解析前触达 provider。新闻、LLM 或通知等其他出站能力仍须依靠 `LOCAL_ONLY_MODE` 约束。

## 三种模式

| `PROVIDER_MARKET_DATA_MODE` | 本地读取 | Provider 链 | Provider 失败 |
| --- | --- | --- | --- |
| `auto`（默认） | 使用字段和区间完整的新鲜数据 | 未命中、字段/区间不完整或过期时调用一次 | 仅在 `PERSISTENT_TTL + STALE_IF_ERROR` 有效期内返回一个完整 stale 候选，否则抛出 `DataFetchError` |
| `local_only` | 仅使用未超过 `LOCAL_ONLY_MAX_AGE` 的完整区间 | 绝不构造或调用 | 抛出 `LocalDataMissingError`；不会进入 provider 可用性探测或 socket 路径 |
| `refresh` | 跳过 | 严格调用一次 | 抛出 provider 链错误，不使用 stale 数据 |

未设置时保持兼容的 `auto` 默认值。任何非空且不属于 `auto`、`local_only`、`refresh` 的值都会在配置加载时给出可操作的 `ValueError`；离线配置拼写错误不会静默变成可联网模式。

## 区间与字段覆盖

持久化身份由规范化代码、复权身份和 schema 身份组成。TickFlow 生效时，其配置的 K 线复权方式属于该身份，因此前复权、后复权与不复权数据在进程重启后也不会交叉复用；其他 provider 使用 `provider_default`。来源名属于条目契约，不同来源的数据不会合并。`days` 只是请求提示，不再属于存储身份；精确、重叠和子区间请求复用同一标的表。

成功请求会记录已覆盖的日期区间。本地读取先验证请求区间和所需列，再按日期排序、去重和切片。一天的 rollover 宽限允许已预热的默认结束日期服务下一日的重叠窗口；`auto` 的新鲜 TTL 仍会让已老化数据在线复验。

部分覆盖策略：

- `local_only` 失败，并只报告实际缺失列和有界缺失区间；
- `auto` 对完整请求窗口调用既有 provider 链一次，成功后与同来源标的表合并；
- `refresh` 对成功窗口执行替换或同来源合并。

错误载荷示例：

```json
{
  "symbol": "600519",
  "start_date": "2026-07-01",
  "end_date": "2026-07-20",
  "days": 30,
  "fields": ["volume"],
  "missing_ranges": [
    {"start_date": "2026-07-01", "end_date": "2026-07-09"}
  ],
  "mode": "local_only",
  "reason": "missing_fields_and_ranges",
  "available_start_date": "2026-07-10",
  "available_end_date": "2026-07-20",
  "age_seconds": 12
}
```

原因可能为 `cache_disabled`、`no_local_entry`、`missing_fields`、`missing_ranges`、`missing_fields_and_ranges`、`no_rows_in_covered_window` 或 `local_entry_too_old`。

股票历史 API 使用 HTTP 409 返回该类型错误，稳定错误码为 `local_market_data_missing`，结构化载荷位于 `details`；分析接口的 OpenAPI 会同时声明该结构化 409 与重复任务 409。同步/异步分析在任务终态化之后仍暴露相同错误码和详情。任何标的缺失时，嵌入式或独立定时 CLI 路径都会在组装分析通知前失败。

## 持久化、隐私与保留策略

Schema v2 仅允许保存以下列：

`date`、`code`、`open`、`high`、`low`、`close`、`volume`、`amount`、`pct_chg`、`ma5`、`ma10`、`ma20`、`volume_ratio`。

provider 结果中的其他列会在返回持久化结果和写盘前剔除。配置值、令牌、请求头、URL 和异常文本在 schema 中没有位置，不会被序列化。写入采用临时文件、`fsync` 和原子替换；同一 manager 内的并发请求共享按身份划分的请求锁，因此一次预热只执行一轮 provider 链。

| 设置 | 默认值 | 策略 |
| --- | ---: | --- |
| `PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS` | `7776000`（90 天） | 读写时删除更老文件 |
| `PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES` | `512` | 最老条目优先删除，同时间戳按文件名确定顺序 |
| `PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS` | `2592000`（30 天） | 更老的完整条目也视为结构化离线缺失 |
| `PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS` | `1` | 对其他部分已覆盖的请求允许一天自然日结束时间滚动 |

既有内存/持久化 TTL 与 stale-if-error 配置继续表达新鲜度。缓存目录默认仍为 `data/provider_cache/daily`，可通过 `PROVIDER_DAILY_CACHE_DIR` 覆盖。

### Schema-v1 兼容

既有按精确请求保存的 schema-v1 JSON 会作为 `provider_default` / `normalized_daily_v1` 的独立覆盖区间读取，并在读取时执行字段白名单；匹配或子区间请求仍可命中。多个兼容旧文件重叠时按 `stored_at` 合并，较新的观测值胜出，文件名只用于相同时间戳的确定性决胜。其他复权/schema 身份（包括 TickFlow 生效的复权身份）会忽略旧条目。下一次同来源成功写入会生成 schema-v2 标的表。不支持、损坏、身份不匹配或不完整的条目都不会算作成功命中。

回滚方式为回退本变更，或取消设置/设为 `PROVIDER_MARKET_DATA_MODE=auto`。回退不会删除缓存文件；schema-v1 读取器会忽略 schema-v2 文件，如需回收空间可另行删除已配置的缓存目录。

## 验证

```bash
python -m pytest \
  tests/data_provider/test_local_first_manager.py \
  tests/data_provider/test_daily_provider_cache.py \
  tests/data_provider/test_local_first_store.py \
  tests/services/test_local_first_boundaries.py \
  tests/app/test_main_schedule_mode.py \
  tests/test_analysis_api_contract.py \
  -m "not network"
```

manager 测试会断言 provider/socket 调用次数、重启后读取、并发调用、重叠/rollover/部分覆盖、stale 过期、refresh 失败策略、schema-v1 读取、保留清理、损坏条目，以及敏感形态额外列不会被持久化。
