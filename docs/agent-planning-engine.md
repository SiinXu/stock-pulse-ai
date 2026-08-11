# Agent 规划：提案基础与执行闭环

**状态**：Issue [#199](https://github.com/SiinXu/stock-pulse-ai/issues/199) 的部分交付

**English**: [agent-planning-engine_EN.md](agent-planning-engine_EN.md)

## 诚实边界

`src/agent/planning/` 提供：

1. **提案基础** — 生成并校验有界 `AgentPlan`（`PlanningEngine`）。
2. **执行闭环** — 可选的 `execute_plan_loop`，在硬预算下运行 plan → act → observe → replan。

两条路径都**没有**接入 `AgentExecutor`、Chat、Research、日常分析、多 Agent orchestrator、报告、Web Settings 或产品配置。调用方必须显式调用 API。

单独的计划提案不得称为完整的生产规划引擎。执行闭环是首个真实执行切片；产品集成仍开放。

## 提案契约

- 调用方显式构造 `PlanningSettings`；没有 `AGENT_PLANNING_*` 环境变量或第二套配置 owner。
- **单一上限 owner。** 所有绝对上限只定义在 `src/agent/planning/config.py`，由 settings 校验、payload 校验、engine、prompt projection 与执行闭环共同导入。
- 精确有限提案上限：最多 16 步、3 次提案重试、8,192 个 planner token、单次提案 60 秒。非法显式值抛出 `ValueError`，不 clamp。
- `validate_plan_payload` 的 `max_steps` 只能收紧 16 步权威上限。
- schema version 必须为 `agent-plan-v1`；step id 从 1 开始、唯一且连续。
- 每个 expected tool 必须属于调用方提供的 available-tool 集合；空 registry 不授权任何工具。
- **通过校验即可投影**；已接受计划一定可投影进 20,000 字符预算。
- LLM 调用前后及接受前检查取消；usage 在 JSON 校验前采集（含 invalid 已计费）。
- prompt projection 标为 `NON_AUTHORITATIVE_PLAN_PROPOSAL`，不能添加工具/权限/指令。
- 单一投影字符串契约覆盖所有被投影字段（含工具名）。

## 执行闭环契约

`execute_plan_loop` 是 plan → act → observe → replan 入口。

- 调用方显式构造 `PlanExecutionSettings`（本切片无环境/Config owner）。
- 绝对执行上限：32 次工具调用、3 次 observation-driven replan、120 秒墙钟、500 字符 observation 摘要；settings 只能收紧。
- 每个步骤通过**调用方提供的 invoker** 调用 `expected_tools`（生产侧通常包装 `ToolSurface.execute_tool`）。闭环不绕过工具授权、capability 或 Tool Surface 安全契约。
- 工具结果必须包含精确布尔 `ok`。缺失或非布尔 `ok` 视为失败（`invalid_tool_result`）。闭环**永不 fail-open** 把失败或歧义结果当作整体成功。
- 空 `expected_tools` 为综合步骤，不发明工具调用即成功。
- 步骤失败且 `on_step_failure="terminate"`（或 replan 预算用尽）时，以稳定 `reason` / `error_code` 终止且 `success=False`。
- 步骤失败且允许 replan 时，带 `prior_observations` 调用 planner，把 replan 记入审计轨迹，并从新计划第一步重启；历史 observation 保留在 metadata。
- template replan 在构造下一提案时排除硬失败工具（非瞬时错误码）；授权集合仍只来自调用方 available-tools。
- 停止闭环的预算/围栏原因：`max_tool_calls_exceeded`、`execution_timeout`、`max_observation_replans_exceeded`、`cancelled`、`replan_failed`。
- 轨迹通道：通过既有 agent observability 发出 `plan_execution` / `plan_step` 阶段事件、工具起止事件与终态 decision 事件（诊断上下文激活时可持久化）。结构化 metadata 始终可通过 `PlanExecutionResult.to_metadata()` 供诊断与评测消费。
- 仅当（含 replan 后的）活动计划全部步骤成功完成时 `success=True`。replan 前的失败 observation 仍保留在列表中，不会单独把终态改写为成功——终态反映闭环是否完成，而不是“每一行 observation 都绿”。

### 执行示例

```python
from src.agent.planning import (
    PlanningEngine,
    PlanningSettings,
    PlanExecutionSettings,
    execute_plan_loop,
)

engine = PlanningEngine(PlanningSettings(enabled=True, strategy="template"))
outcome = engine.plan(
    "Analyze 600519",
    available_tools=["get_realtime_quote", "get_daily_history"],
    context={"stock_code": "600519"},
)
assert outcome.plan is not None

def invoker(name, arguments):
    return surface.execute_tool(name, arguments, context=access_ctx)

result = execute_plan_loop(
    plan=outcome.plan,
    tool_invoker=invoker,
    available_tools=["get_realtime_quote", "get_daily_history"],
    task="Analyze 600519",
    context={"stock_code": "600519"},
    settings=PlanExecutionSettings(max_total_tool_calls=8, max_observation_replans=1),
    planning_settings=PlanningSettings(enabled=True, strategy="template"),
)
print(result.success, result.status, result.to_metadata())
```

## 隐私与保留

库本身不持久化。observability emit 仅在 emit 边界 fail-open；执行结果永不把失败报成成功。调用方不得持久化私有 task、自由推理、凭据或原始 provider response。返回 metadata 仅限稳定 reason code、有界摘要、plan id 与 observation 状态行。

## #199 剩余范围

- RUN/CHAT/RESEARCH/daily 的 mode-aware 产品策略与跨模式共享工具授权/预算；
- 计划/动作/observation 的耐久审计持久化、tenant identity、脱敏/retention owner 与产品 UI；
- 规划侧统一的 UsageRecorder / 安全审计 / run diagnostics 配置 owner；
- 生产工作流内确定性的真实多步骤工具验收证据。

## 回滚

回退新增 planning 模块、测试与文档即可；没有 runtime 开关、迁移或生产集成需要回滚。
