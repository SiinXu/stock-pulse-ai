# 预测核验环路 — 安全放量

> English: [prediction-verification-rollout_EN.md](prediction-verification-rollout_EN.md)

运营向说明：落地后的核验 / 复盘开关如何按安全顺序打开（Issue [#1115](https://github.com/SiinXu/stock-pulse-ai/issues/1115)，Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107)）。

本页只记录 **默认值与安全开启顺序**。它 **并不** 关闭 #1115 的全部验收项（见 [Issue 剩余缺口](#issue-剩余缺口)）。

仅研究 / 质量运营定位，不是收益保证产品面。

## 安全放量顺序

按此顺序操作，不要提前打开适配器或晋升。

1. **全部开关关闭。** 使用落地默认值：抽取关闭、解析器调度关闭、后验关闭、在线适配器关闭。分析、历史保存与通知走既有路径。
2. **打开抽取并确认分析仍然健康。** 设置 `PREDICTION_EXTRACT_ENABLED=true`。跑一次正常分析 / Agent finalize。抽取异常只记日志，**永不**让分析或历史保存失败。只有健康检查通过后，再查看挂载草稿 / `agent_predictions` pending 行。
3. **只在一个调度 worker 上打开解析器，或显式调用 cron CLI。** 二选一：
   - 在 **一个** 已运行既有调度器的进程上设置 `PREDICTION_RESOLVE_ENABLED=true`（`python main.py --schedule`，或会注册 `RuntimeSchedulerService` 的 API/Web/Desktop serve），后台任务名 `prediction_resolver`；**或者**
   - 应用 worker 保持 `PREDICTION_RESOLVE_ENABLED=false`，运行 `python -m src.services.prediction_resolver`（可选 `--limit`、`--worker-id`、`--json`）。
   手动 CLI 调用是 **有意的运营闸门**：即使调度开关关闭，CLI 也会执行一次 `tick()`。不要在每个应用副本上都注册后台 worker。
4. **打开仅 miss/partial 的后验，并保持 skip-clean-hits。** 设置 `AGENT_POSTMORTEM_ENABLED=true`，保留 `AGENT_POSTMORTEM_SKIP_CLEAN_HITS=true`（默认）。命中不会入队。排空发生在非重叠 resolver tick 之后，受 `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK`（默认 `10`）限制。
5. **仅在样本达到阈值后再打开门控适配器。** 只有 `AgentMemory` / 已解析预测样本能满足 `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES`（默认 `30`）时，才设置 `AGENT_ONLINE_ADAPTERS_ENABLED=true`。低于阈值时适配器保持恒等（`applied=false`，`reason=insufficient_samples`）。
6. **自动晋升保持硬关闭。** 没有环境变量可以打开 skill 自动晋升。沙箱 `PromotionReceipt.auto_promote` 硬编码为 `false`，直到存在评估闸门。

要停止 **新的** 核验工作且不破坏分析：把 enable 开关改回 `false`（或删除）。已写入的 `agent_predictions` pending 行会留在库中；分析路径不依赖它们。

## Issue 示例名不是别名

Issue #1115 列出的是示例名（`e.g.`）。这些字符串 **不是** 已注册配置键，也 **不得** 当作落地键的别名、回退或环境变量同义词。在 `.env` 里写示例名不会生效。

| Issue #1115 示例 | 落地键或表面 | 落地默认 | 说明 |
| --- | --- | --- | --- |
| `PREDICTION_VERIFY_ENABLED` | `PREDICTION_EXTRACT_ENABLED` **与** `PREDICTION_RESOLVE_ENABLED` | 均为 `false` | 核验是两把开关。示例名不是二者的父别名。 |
| `PREDICTION_RESOLVER_INTERVAL_SEC` | `PREDICTION_RESOLVE_INTERVAL_SECONDS` | `60`（调度下限 `30`） | 拼写不同；不是别名。 |
| `PREDICTION_RESOLVER_BATCH_LIMIT` | `PREDICTION_RESOLVE_MAX_PER_TICK` | `50` | 拼写不同；不是别名。 |
| `PREDICTION_FETCH_CONCURRENCY` | `PREDICTION_RESOLVE_FETCH_CONCURRENCY` | `4` | 拼写不同；不是别名。 |
| `PREDICTION_POSTMORTEM_ENABLED` | `AGENT_POSTMORTEM_ENABLED` | `false` | 前缀不同；不是别名。 |
| `PREDICTION_POSTMORTEM_ON_HIT` | `AGENT_POSTMORTEM_SKIP_CLEAN_HITS` | `true` | 相对 “命中也复盘” **语义相反**。默认跳过干净命中；命中不会入队。 |
| `PREDICTION_POSTMORTEM_CONCURRENCY` | *（无）* | 硬编码 `2` | Drain worker 数在代码内（`_DEFAULT_DRAIN_WORKERS`）。没有环境变量。 |
| `PREDICTION_POSTMORTEM_MAX_PER_TICK` | `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` | `10` | 前缀不同；不是别名。 |
| `PREDICTION_FLAT_EPSILON_PCT` | `ClaimScoreConfig.sideways_epsilon`（构造参数别名 `flat_epsilon`） | `0.001`（0.1%） | 打分器本地 / 非环境变量。没有 `PREDICTION_FLAT_EPSILON_PCT` 注册键。 |
| `EVOLUTION_MIN_SAMPLES` | `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES` | `30` | 拼写不同；不是别名。 |
| `EVOLUTION_AUTO_PROMOTE_SKILLS` | *（无）* | 硬编码 `false` | `PromotionReceipt.auto_promote` 与沙箱 `auto_promote_to_production` 保持 false。没有环境变量。 |

落地键走既有 `Config` / 配置注册表路径。示例名不会。

## 当前延期与边界

这些是 **当前产品事实**，不是运营可调的放量旋钮：

| 边界 | 当前行为 |
| --- | --- |
| 后验并发 | `drain_postmortem_queue` 硬编码 `2`（`_DEFAULT_DRAIN_WORKERS`）。调度与 CLI 不传 `max_workers`。没有 `PREDICTION_POSTMORTEM_CONCURRENCY` 环境变量。 |
| Flat epsilon | 仅 `ClaimScoreConfig` 本地（`sideways_epsilon`，可选构造别名 `flat_epsilon`）。不是环境变量。 |
| 自动晋升 | `PromotionReceipt` 与沙箱策略硬 `false`，直到存在评估闸门。不要臆造 `EVOLUTION_AUTO_PROMOTE_SKILLS=true`。 |
| 手动 resolver CLI | `python -m src.services.prediction_resolver` 是有意的运营闸门。它会读取上限配置（租约、批次、拉取并发、熔断、后验预算）并执行一次 tick，**即使** `PREDICTION_RESOLVE_ENABLED` 为 false。调度开关只负责注册后台 worker。 |
| 调度 vs CLI 后验注入 | 队列注入只看 `AGENT_POSTMORTEM_ENABLED`。**调度** 排空还需要 resolver worker（`PREDICTION_RESOLVE_ENABLED`）。CLI 排空不要求该调度开关。 |
| 关闭开关 | 抽取关闭 → 钩子空操作。解析器调度关闭 → 不注册 `prediction_resolver` 后台任务（CLI 仍可用）。后验关闭 → 不注入 / 不排空队列。适配器关闭 → 恒等。上述情况下分析路径均继续。 |

## 相关文档

- [预测抽取](prediction-extraction.md)
- [预测到期解析器](prediction-resolver.md)
- [Agent 复盘与预测后验](agent-reflection-postmortem.md)
- [确定性预测声明打分器](prediction-claim-scorer.md)
- [主体隔离的分层 Agent 记忆](agent-memory_CN.md)（门控适配器）
- [Agent / 策略模拟沙箱](agent-sandbox.md)（硬 `auto_promote=false`；目前仅英文）
- 环境变量清单：[environment-variables.md](environment-variables.md)

## Issue 剩余缺口

本说明切片 **并不** 使 Issue #1115 验收全部关闭：

- 已记录的默认值与本安全放量顺序 — 本页。
- 开关从单一配置解析路径读取 — **仅落地键**。示例名有意保持未注册。
- 关闭开关会停止新工作且不破坏分析 — 对上文落地 enable 键成立；运营必须使用这些键，而不是 issue 示例名。
- 可用环境变量调节的后验并发、可用环境变量调节的 flat epsilon，以及评估闸门之后的自动晋升，仍属 **延期**。
