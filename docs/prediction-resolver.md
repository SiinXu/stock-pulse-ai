# 预测到期解析器（Prediction Horizon Resolver）

> English: [prediction-resolver_EN.md](prediction-resolver_EN.md)

实现 Issue [#1102](https://github.com/SiinXu/stock-pulse-ai/issues/1102) 与 [#1116](https://github.com/SiinXu/stock-pulse-ai/issues/1116)（Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)）。

当 `resolve_after` 到期时，**系统**认领预测、经服务端 data_provider 路径取实际行情、确定性打分并写回。用户无需点击核验。

## 产品规则

- 接入**既有**进程调度器或外部 cron CLI，不另造调度进程。
- Provider 失败 → `data_unavailable` / 重试，**永不**伪造 hit/miss。
- 不修改 Agent Soul charter 或 ToolSurface 拒绝项。
- 仅研究 / 质量运营定位。

## 配置

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `PREDICTION_RESOLVE_ENABLED` | `false` | 总开关 |
| `PREDICTION_RESOLVE_INTERVAL_SECONDS` | `60` | 轮询间隔（下限 30s） |
| `PREDICTION_RESOLVE_MAX_PER_TICK` | `50` | 每次 tick 最多认领 |
| `PREDICTION_RESOLVE_LEASE_SECONDS` | `120` | resolving 租约 TTL |
| `PREDICTION_RESOLVE_MAX_ATTEMPTS` | `5` | 硬性尝试次数上限 |
| `PREDICTION_RESOLVE_FETCH_CONCURRENCY` | `4` | actuals 拉取的全局 worker 上限 |
| `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` | `10` | 注入复盘队列 adapter 后的每 tick 转交预算；未注入时不执行复盘工作 |
| `PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_THRESHOLD` | `5` | 单次 tick 中触发熔断的失败拉取组数 |
| `PREDICTION_RESOLVE_PROVIDER_ERROR_CIRCUIT_COOLDOWN_SECONDS` | `60` | 熔断冷却秒数 |
| `PREDICTION_RESOLVE_CIRCUIT_OPEN_MAX_PER_TICK` | `5` | 熔断期间收缩后的每 tick 认领上限 |
| `PREDICTION_RESOLVE_RETRY_JITTER_RATIO` | `0.1` | 正向重试抖动比例（`0` 到 `1`） |

## 单进程部署

1. 运行时具备 A3 持久化、A4 `ActualsFetcher`、A5 `ClaimScorer`。
2. 设置 `PREDICTION_RESOLVE_ENABLED=true`。
3. 运行 `python main.py --schedule` 或已挂载 `RuntimeSchedulerService` 的 serve 路径。
4. 后台任务名：`prediction_resolver`。

## 多进程 / cron

应用 worker 保持开关关闭，由单一作业执行：

```bash
* * * * * cd /app && python -m src.services.prediction_resolver --json >> /var/log/prediction-resolver.log 2>&1
```

`--limit` 只能收窄 `PREDICTION_RESOLVE_MAX_PER_TICK`，不能超过或重新启用已配置的硬上限。

## 重叠保护与重试

- 进程内非阻塞锁跳过重叠 tick。
- 存储层租约 + 条件写回防止重复 outcome；租约过期后工作可能重试，但只有一个 outcome 能成功落库。
- **过期的 `resolving` 租约**会在下一次 tick 重新进入 due 扫描（崩溃恢复）。
- `data_unavailable` 使用带正向抖动的有界指数退避（outcome 中的 `next_attempt_at`），并在达到 `PREDICTION_RESOLVE_MAX_ATTEMPTS` 后标记 `retry_exhausted` 停止重试。
- 重试信息持久化在 A3 outcome 中；每次 tick 只会重新排队已到 `next_attempt_at` 的可重试记录，停牌/退市及已耗尽尝试的记录保持 `data_unavailable`。
- 实际行情窗口从预测的规范 `as_of` 字段开始；最终交易日的最高/最低价不会被误当成整个窗口的路径极值。

## 有界批处理行为

- 到期任务受 `PREDICTION_RESOLVE_MAX_PER_TICK` 限制，大积压会跨多个 tick 排空。
- 已认领记录按 `symbol`、`market`、预测 `as_of` 与 horizon 结束日合并；完全相同的窗口只拉取一次 actuals。
- 只有 actuals 拉取并发执行；claim 打分与 lease-token 条件写回在单次 tick 内保持串行，不会创建无界的打分或 LLM 线程池。
- 并发上限是全局的，因为 provider 选择与 fallback 封装在 `ActualsFetcher` 端口之后；provider 级节流由 fetcher 自身负责。
- 拉取错误突增会打开进程内熔断；冷却期间后续 tick 使用更小的认领上限，避免放大 provider 故障。
- miss/partial outcome 可转交给注入的有界复盘队列。队列使用独立且显式受限的 drain 线程池，miss 优先；resolver 主链不会执行复盘 LLM 调用。
- 每次 tick 的 summary/event 包含积压深度（有界探测）、最老到期延迟、解析率、拉取/错误/合并数量、延期量、熔断状态和复盘队列深度。

## 诊断 HTTP

已认证运营者可以在不写 SQL 的情况下查看当前**可认领**的到期工作：

```http
GET /api/v1/agent/prediction-resolver/diagnostics
```

鉴权与可选预测反馈 API 一致：`AuthMiddleware` 加上管理员会话 Cookie。当 `ADMIN_AUTH_ENABLED=true` 时，缺少或无效 Cookie 返回 **401** `unauthorized`（不是 403）。该路径不在鉴权豁免列表中。

响应是构造出的允许列表（`extra=forbid`）：

| 字段 | 含义 |
| --- | --- |
| `enabled` | 本 API 进程的 `PREDICTION_RESOLVE_ENABLED` |
| `interval_seconds` | 已配置的轮询间隔（下限 30 秒），即使本进程不是 worker |
| `this_process_worker_registered` | **本 API 进程**是否登记了 `prediction_resolver` 后台任务。这不是全局 worker 健康。默认 Compose `server` 与文档中的 cron 路径下该字段为 `false`。 |
| `observed_at` | 用作 due 探测 `as_of` 的 ISO-8601 UTC 时钟 |
| `claimable_due_count` | 与下一次 tick 相同的可认领探测长度，但 **不会** 执行 requeue 写操作 |
| `claimable_due_truncated` | 探测长度达到上限时为 `true` |
| `claimable_due_probe_limit` | 探测上限（`max(1000, max_per_tick + 1)`，硬顶 10000；存储层 `list_due` 仍硬顶 1000） |
| `oldest_due` | 最多 10 条允许字段，已按最老 `resolve_after` 排序：`prediction_id`、`symbol`、`market`、`status`（`pending` 或租约过期的 `resolving`）、`resolve_after`、`lag_seconds` |

该 GET 只读。它不会 tick、认领、重新排队、启动或构造 resolver worker。存储读取失败返回 **503**，不会伪装成空积压。开关关闭 / 空队列 / API 进程未挂 worker 时仍返回 **200** 并带上上述字段。

可认领集合是 pending 行加上已过期的 `resolving` 租约。到期的 `data_unavailable` 重试在 tick 重新排队之前 **不会** 被计入，因此 `claimable_due_count` 可能低于下一次 tick 的 `due_before`。`claimable_due_count` / `lag_seconds` 增大只是**提示**，不能证明 worker 卡住。熔断、重叠跳过和上次 tick 计数仍只在日志中；本接口不提供进程内 `last_tick`。

## Epic 剩余边界

- 预测查询列表 / 按 id 查询 HTTP API（剩余 #1102）
- p50/p95 解析延迟直方图、持久化当日命中率、最近拉取错误、Prometheus / OTel，以及可跨进程证明 cron 健康的 worker 心跳
- 交易日历 `resolve_after`（#1109）
- 复盘 lesson writer / adapter（#1103 / #1106）；resolver 只提供有界队列边界
