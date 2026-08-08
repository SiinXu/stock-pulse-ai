# Agent 规划引擎（plan-and-execute 前置步骤）

[中文](agent-planning-engine.md) | [English](agent-planning-engine_EN.md)

Issue [#199](https://github.com/SiinXu/stock-pulse-ai/issues/199)。为单 Agent 路径 `AgentExecutor` 提供可选的**规划前置步骤**：在既有 ReAct 循环之前产出结构化步骤列表（目标、预期工具、成功判据）。

## 与现有编排的关系（前置，不是替代）

| 组件 | 职责 |
| --- | --- |
| `AgentExecutor` + `run_agent_loop` | 既有单 Agent ReAct 工具循环（核心不变） |
| `AgentOrchestrator` | 多 Agent 分阶段流水线（本功能不改动） |
| 多策略审议 | `AGENT_MULTI_STRATEGY_DELIBERATION` 下的意见调解（不改动） |
| Deep Research 规划 | `research.py` 内查询拆解（独立路径） |
| **规划引擎（本文）** | **前置步骤**：可将计划注入 user message，再交给既有 ReAct 循环 |

结论：规划器是单 Agent 执行的**前缀**，不是第二套编排运行时。多 Agent 日常流水线仍走 orchestrator。

## 默认关闭

- 配置：`AGENT_PLANNING_ENABLED`（默认 `false`）
- 关闭时：`AgentExecutor.run` 与原先直接执行路径一致；`result.planning` 记录 `{enabled: false, applied: false}`
- 开启时：生成结构化计划，注入任务/用户消息，再跑同一套 ReAct 循环

## 如何启用

```bash
AGENT_MODE=true
AGENT_PLANNING_ENABLED=true
# 可选：
# AGENT_PLANNING_STRATEGY=auto   # auto | template | llm
# AGENT_PLANNING_MAX_STEPS=8
# AGENT_PLANNING_MAX_REPLANS=1
# AGENT_PLANNING_MAX_TOKENS=1500
# AGENT_PLANNING_TIMEOUT_S=30
```

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `AGENT_PLANNING_ENABLED` | `false` | 总开关 |
| `AGENT_PLANNING_STRATEGY` | `auto` | `template`=确定性工具阶段计划；`llm`=模型 JSON 计划；`auto`=有 adapter 则 llm 否则 template |
| `AGENT_PLANNING_MAX_STEPS` | `8` | 计划步数硬上限 |
| `AGENT_PLANNING_MAX_REPLANS` | `1` | 失败后额外规划次数 |
| `AGENT_PLANNING_MAX_TOKENS` | `1500` | 规划 LLM 请求 token 上限 |
| `AGENT_PLANNING_TIMEOUT_S` | `30` | 规划调用超时（秒） |

## 结构化计划 schema

```json
{
  "version": "agent-plan-v1",
  "goal": "Analyze stock and produce a decision dashboard",
  "max_steps": 8,
  "steps": [
    {
      "id": 1,
      "goal": "Fetch market quote and price history",
      "expected_tools": ["get_realtime_quote", "get_daily_history"],
      "success_criteria": "Realtime quote and/or daily history returned"
    }
  ]
}
```

轨迹元数据挂在 `AgentResult.planning` 上（**不会**写入 dashboard / 报告 JSON schema）。

## 失败与成本边界

- 计划结构不合法 → 在 `AGENT_PLANNING_MAX_REPLANS` 内重规划，否则**降级为直接执行**（不硬失败）
- LLM 规划失败 → 在剩余次数内可回退 template；否则直接执行
- 超过计划步数上限 → 拒绝/降级
- 规划过程中取消 → 直接路径，`fallback_reason=cancelled`

## 不改动的契约

- 最终报告 / dashboard schema
- `runner.py` 工具日志写入格式
- 多 Agent orchestrator 阶段
- 开关关闭时的默认生产行为

## Integration Point（配置注册表 UI）

运行时从 `src/agent/planning/config.py` 直接读取环境变量，从而不修改 `src/core/config_registry_parts/`（并行任务所有权）。若要在 Web Settings 展示开关，请在 agent 配置注册表中登记上表键名（留给配置注册表 owner 的 Integration Point）。

## 回滚

设置 `AGENT_PLANNING_ENABLED=false` 或删除该项。无需数据迁移；运行时即可回退，不必发版。
