# Agent 类型化计划提案基础

**状态**：Issue [#199](https://github.com/SiinXu/stock-pulse-ai/issues/199) 的 proposal-only 基础切片

**English**: [agent-planning-engine_EN.md](agent-planning-engine_EN.md)

## 诚实边界

`src/agent/planning/` 只在离线调用方显式调用时生成和校验有界计划提案。它没有接入 `AgentExecutor`、Chat、Research、日常分析、多 Agent orchestrator、报告、诊断、持久化或 Web Settings。

它**不会**执行计划步骤、把工具结果绑定为 observation、根据 observation 重规划、执行共享总预算或提供审计轨迹。这些都是 #199 的剩余验收项。计划提案不得称为 plan→act→observe 引擎。

## 契约

- 调用方显式构造 `PlanningSettings`；没有 `AGENT_PLANNING_*` 环境变量或第二套配置 owner。
- 精确有限上限：最多 16 步、3 次重试、8,192 个 planner token、单次提案调用 60 秒。非法显式值抛出 `ValueError`，不 clamp、不静默回默认值。
- schema version 必须严格为 `agent-plan-v1`；step id 必须从 1 开始、唯一且连续；goal、success criteria、工具名、输入 task 和 prompt projection 都有长度上限。
- 每个 expected tool 必须属于调用方提供的 available-tool 集合。空 registry 不授权任何工具；未知工具使提案无效。
- LLM 调用前后及接受前均检查取消信号，迟到响应不能应用。
- 在 JSON 校验前读取 provider usage，因此 invalid response 的已计费 token 仍被记录。metadata 只保留稳定错误码和异常类型，不返回原始异常或 planner 输出。
- 规范化提案通过 SHA-256 `plan_id` 标识。
- prompt projection 标为 `NON_AUTHORITATIVE_PLAN_PROPOSAL`；生成字段只是 advisory data，不能添加工具、权限或指令，也不能覆盖原始 user/system 请求。

## 显式示例

```python
from src.agent.planning import PlanningEngine, PlanningSettings

engine = PlanningEngine(
    PlanningSettings(enabled=True, strategy="template", max_plan_steps=4)
)
outcome = engine.plan(
    "Analyze 600519",
    available_tools=["get_realtime_quote", "get_daily_history"],
    context={"stock_code": "600519"},
)
assert outcome.plan is not None
print(outcome.to_metadata())
```

template strategy 不发网络请求；`llm` strategy 需要调用方显式提供 adapter，且仍只生成提案。

## 隐私与保留

本基础模块不持久化数据。调用方不得持久化私有 task、自由推理、凭据或原始 provider response。失败 metadata 仅限稳定 reason code、异常类型、有界 usage、模型名和已校验提案。

## #199 剩余范围

- RUN/CHAT/RESEARCH/daily 的 mode-aware 产品策略；
- 已授权步骤执行和 typed observation；
- observation-driven replan；
- planner/executor/tool 共用一个 deadline 与 token/cost/step 总预算；
- 接入 UsageRecorder、安全审计、run diagnostics、tenant identity、脱敏与 retention；
- 确定性的真实多步骤工具验收证据。

## 回滚

回退新增 planning 模块、测试与文档即可；没有 runtime 开关、迁移、持久化数据或生产集成需要回滚。
