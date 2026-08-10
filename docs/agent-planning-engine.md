# Agent 类型化计划提案基础

**状态**：Issue [#199](https://github.com/SiinXu/stock-pulse-ai/issues/199) 的 proposal-only 基础切片

**English**: [agent-planning-engine_EN.md](agent-planning-engine_EN.md)

## 诚实边界

`src/agent/planning/` 只在离线调用方显式调用时生成和校验有界计划提案。它没有接入 `AgentExecutor`、Chat、Research、日常分析、多 Agent orchestrator、报告、诊断、持久化或 Web Settings。

它**不会**执行计划步骤、把工具结果绑定为 observation、根据 observation 重规划、执行共享总预算或提供审计轨迹。这些都是 #199 的剩余验收项。计划提案不得称为 plan→act→observe 引擎。

## 契约

- 调用方显式构造 `PlanningSettings`；没有 `AGENT_PLANNING_*` 环境变量或第二套配置 owner。
- **单一上限 owner。** 所有绝对上限只定义在 `src/agent/planning/config.py`，由 settings 校验、payload 校验、engine 与 prompt projection 共同导入；任何模块都不再重复书写字面量。
- 精确有限上限：最多 16 步、3 次重试、8,192 个 planner token、单次提案调用 60 秒。非法显式值抛出 `ValueError`，不 clamp、不静默回默认值。
- 公开函数 `validate_plan_payload` 的 `max_steps` 参数是*只能收紧*的调用方上限，不能放宽 16 步这一绝对权威。传入 `max_steps=17` 会被直接拒绝，因此任何调用方都无法把公开契约放宽到接受 17 步计划。
- schema version 必须严格为 `agent-plan-v1`；step id 必须从 1 开始、唯一且连续；goal、success criteria、工具名、available-tool 集合大小、输入 task 和 prompt projection 都有上限。
- 每个 expected tool 必须属于调用方提供的 available-tool 集合。空 registry 不授权任何工具；未知工具使提案无效。
- **通过校验即可投影。** 逐字段上限并不能约束整体 payload，因此校验同时拒绝渲染后会超过 20,000 字符的计划。已通过校验的计划一定可以投影，`format_plan_for_prompt` 不会在已接受的计划上失败。
- LLM 调用前后及接受前均检查取消信号，迟到响应不能应用。
- 剩余 deadline 会作为 transport `timeout` 传入 adapter 调用，因此 planner 调用是真正可中断的，而不是只在返回后事后判断；返回后的 deadline 检查作为第二道围栏保留。
- 在 JSON 校验前读取 provider usage，因此 invalid response 的已计费 token 仍被记录。metadata 只保留稳定错误码和异常类型，不返回原始异常或 planner 输出。
- **重试证据保持真实。** `replan_attempts` 在所有退出路径（含成功路径）上都记录真实发生的重试次数。当 `llm` 尝试失败、重试降级为 `template` 时，`requested_strategy` 仍为 `llm` 而 `strategy` 变为 `template`，使已计费 token 与记录的 model 可被正确归属。只有在确实允许并用尽重试预算时才报告 `max_replans_exceeded`，否则原因为 `planning_failed`。
- 规范化提案通过 SHA-256 `plan_id` 标识。
- prompt projection 标为 `NON_AUTHORITATIVE_PLAN_PROPOSAL`；生成字段只是 advisory data，不能添加工具、权限或指令，也不能覆盖原始 user/system 请求。
- **模型文本无法伪造 advisory 边界。** 生成的 goal 与 success criteria 若包含任意拼写形式的边界标记（大小写不敏感、容忍空格）会被拒绝，因此提案无法提前关闭 advisory 区块、让后续文本被当作权威指令。其余字符都位于 JSON 字符串内，引号、反斜杠与控制字符均被转义。`format_plan_for_prompt` 另外断言每个标记恰好出现一次。

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
