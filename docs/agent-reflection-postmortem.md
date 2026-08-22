# Agent 复盘与预测后验（Reflection / Post-mortem）

本文档说明 **运行内反思契约**（Issue #1089）与 **已解析预测后验复盘**（Issue #1103），从属于 Epic #1107。

## 产品规则

- 仅研究 / 质量运营定位，不是收益保证。
- 复盘路径 **不得** 改写 Agent Soul 章程 / 版本 / 哈希。
- 复盘路径 **不得** 扩展或放宽 ToolSurface 拒绝项。
- 非结构化散文不得变成假的可验证声明。
- Provider / 真值取数失败记为 `data_unavailable`（可重试），永不伪造命中。
- LLM 预算耗尽必须显式记录 `budget_skipped` / `terminate_reason=budget`，语义对齐 Critic 的 `record_critic_budget_skip`，禁止静默降级。
- 若运行上下文带有 `ctx.meta["mode_budget_account"]`，反思 / 后验 LLM 调用会计入该 run 账户；跳过仍使用 `budget_skipped`，不得越过 `max_llm_turns`。生产 Chat/单 Agent 循环会把该账户挂到 executor 上，供运行结束规划反思读取。这些调用走 `llm_complete`，不经过 `run_agent_loop`，因此不会重复计次。运行结束反思不预留 Decision 轮次；循环内可选步骤批评会预留。

## 入口

- 运行内反思：`src/agent/evolution/reflection.py`
- 预测后验：`src/agent/evolution/postmortem.py`
- 共享教训类型：`src/agent/evolution/lessons.py`

## 配置项

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `AGENT_REFLECTION_ENABLED` | `false` | 启用运行内反思 |
| `AGENT_REFLECTION_LLM_BUDGET` | `1` | 单次反思 LLM 调用上限（0–64） |
| `AGENT_REFLECTION_MAX_REVISE` | `1` | 运行内修订次数上限 |
| `AGENT_POSTMORTEM_ENABLED` | `false` | 启用预测后验复盘 |
| `AGENT_POSTMORTEM_LLM_BUDGET` | `8` | 单批后验 LLM 调用上限 |
| `AGENT_POSTMORTEM_SKIP_CLEAN_HITS` | `true` | 干净命中跳过后验 LLM |

英文版细节与回滚说明见 [agent-reflection-postmortem_EN.md](./agent-reflection-postmortem_EN.md)。
