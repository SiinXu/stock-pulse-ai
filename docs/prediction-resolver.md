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
| `PREDICTION_RESOLVE_MAX_ATTEMPTS` | `5` | 诊断用尝试计数 |

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

## 重叠保护

- 进程内非阻塞锁跳过重叠 tick。
- 存储层租约 + 条件写回防止跨进程双写。
