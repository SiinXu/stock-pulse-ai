# Agent 复盘与预测后验（Reflection / Post-mortem）

本文档说明 **运行内反思契约**（Issue #1089）与 **已解析预测后验复盘**（Issue #1103），从属于 Epic #1107。

## 产品规则

- 仅研究 / 质量运营定位，不是收益保证。
- 复盘路径 **不得** 改写 Agent Soul 章程 / 版本 / 哈希。
- 复盘路径 **不得** 扩展或放宽 ToolSurface 拒绝项。
- 非结构化散文不得变成假的可验证声明。
- Provider / 真值取数失败记为 `data_unavailable`（可重试），永不伪造命中。
- LLM 预算耗尽必须显式记录 `budget_skipped` / `terminate_reason=budget`，语义对齐 Critic 的 `record_critic_budget_skip`，禁止静默降级。
- 若运行上下文带有 `ctx.meta["mode_budget_account"]`，反思 / 后验 LLM 调用会计入该 run 账户；跳过仍使用 `budget_skipped`，不得越过 `max_llm_turns`。生产 Chat/单 Agent 循环会把该账户挂到 executor 上，供运行结束规划反思读取。规划产品路径会在反思后把 `AgentResult.budget_snapshot` 重写为该账户的最终快照。后验没有 `AgentResult`，诊断看 `ctx.meta["mode_budget"]`。这些调用走 `llm_complete`，不经过 `run_agent_loop`，因此不会重复计次。运行结束反思不预留 Decision 轮次；循环内可选步骤批评会预留。运行级 LLM 轮次上限是 `AGENT_MODE_BUDGET_MAX_LLM_TURNS`（没有 `AGENT_MAX_RUN_LLM_CALLS` 键）。

## 入口

- 运行内反思：`src/agent/evolution/reflection.py`
- 预测后验：`src/agent/evolution/postmortem.py`
- 生产排空：`src/services/prediction_resolver/postmortem_drain.py`
- 共享教训类型：`src/agent/evolution/lessons.py`

## 生产接线（调度 / CLI）

默认关闭。`AGENT_POSTMORTEM_ENABLED=true` 时才会注入已有的 `InMemoryPostmortemQueue`。**调度**排空还需要 resolver worker（`PREDICTION_RESOLVE_ENABLED`）。cron CLI（`python -m src.services.prediction_resolver`）在调度开关关闭时仍会在 tick 后排空——这是有意的运营闸门。排空发生在非重叠 `tick()` 之后，受 `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` 限制；drain 并发硬编码为 `2`（不是环境变量）。

处理器只映射已经写入的 outcome / score / actuals（含入队时拷贝的 `run_id` 与 claims），不重新拉行情，也不从价格编造方向。命中与 `data_unavailable` 不会入队。教训经 `record_reflection_lessons` 投影：若 `AGENT_EPISODE_LOG_ENABLED` 且能按 `run_id` 找到 episode，则带上该 `episode_id`；否则保留进程内 sidecar。找不到 episode 不会让 resolve 失败。排空 / LLM / episode 错误只记录并按队列策略重入队，**不会**回滚已 `resolved` 行，也不会伪造 hit。本切片不向 diagnostics HTTP 暴露队列深度。

## 配置项

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `AGENT_REFLECTION_ENABLED` | `false` | 启用运行内反思 |
| `AGENT_REFLECTION_LLM_BUDGET` | `1` | 单次反思 LLM 调用上限（0–64） |
| `AGENT_REFLECTION_MAX_REVISE` | `1` | 运行内修订次数上限 |
| `AGENT_POSTMORTEM_ENABLED` | `false` | 启用预测后验复盘 |
| `AGENT_POSTMORTEM_LLM_BUDGET` | `8` | 单批后验 LLM 调用上限 |
| `AGENT_POSTMORTEM_SKIP_CLEAN_HITS` | `true` | 干净命中跳过后验 LLM |
| `PREDICTION_RESOLVE_POSTMORTEM_MAX_PER_TICK` | `10` | 非重叠 tick 后最多排空的后验任务数 |

Issue #1115 示例名（`PREDICTION_POSTMORTEM_ENABLED`、`PREDICTION_POSTMORTEM_ON_HIT`、`PREDICTION_POSTMORTEM_CONCURRENCY`、`PREDICTION_POSTMORTEM_MAX_PER_TICK`）**不是**上表键的别名。`PREDICTION_POSTMORTEM_CONCURRENCY` 没有环境变量；drain worker 数硬编码为 `2`。

## 安全放量

整条核验环路的运营顺序：

1. 核验环路全部开关关闭。
2. 打开抽取并确认分析仍然健康。
3. 只在一个调度 worker 上打开解析器，**或**显式调用 cron CLI。
4. 打开仅 miss/partial 的后验，并保持 `AGENT_POSTMORTEM_SKIP_CLEAN_HITS=true`（本步）。
5. 仅在达到 `AGENT_ONLINE_ADAPTERS_MIN_SAMPLES` 后再打开门控适配器。
6. 自动晋升保持硬关闭。

完整映射与延期边界见 [预测核验安全放量](prediction-verification-rollout.md)。

英文版细节与回滚说明见 [agent-reflection-postmortem_EN.md](./agent-reflection-postmortem_EN.md)。
