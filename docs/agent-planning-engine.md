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
- **单一投影字符串契约，覆盖所有被投影字段。** `src/agent/planning/types.py` 中的 `unprojectable_reason` 是唯一权威，统一约束 plan goal、每个 step goal、每个 success criteria、每个 expected tool 名称，以及它们所来源的 available-tool 名称。字符串在以下任一情况下被拒绝：(a) 含有任意拼写形式的边界标记；(b) 含有未配对的 surrogate 码点。该匹配器在 `config.py` 中由渲染器实际输出的标记推导得到，因此不会与其漂移。
- **模型文本无法伪造 advisory 边界。** 由于上述规则同时覆盖工具名与散文字段，提案无法提前关闭 advisory 区块、让后续文本被当作权威指令——精确的 `[/NON_AUTHORITATIVE_PLAN_PROPOSAL]` 与容忍空格的变体（如 `[ / non_authoritative_plan_proposal ]`）都会被拒绝。其余字符都位于 JSON 字符串内，引号、反斜杠与控制字符均被转义。`format_plan_for_prompt` 复用同一匹配器并断言每个标记恰好出现一次，作为手工构造 `AgentPlan` 时的纵深防御。
- **planner 可控文本不会抛出编码错误。** `plan_id` 对 UTF-8 字节做哈希，因此单个 surrogate（可经 `json.loads` 以 `"\ud800"` 形式存活）原本会让 `plan_id`、`to_metadata()` 与 `prepare_run_with_planning` 抛出 `UnicodeEncodeError`，而不是给出降级结果。校验会以稳定原因拒绝这类字符串；engine 另在入口拦截不可编码的 task（`invalid_task`）以及不可编码或含标记的工具 registry（`invalid_tools`），因此公开封装始终降级并原样返回调用方输入。`to_canonical_json` 会把残余 surrogate 转义为 `\uXXXX`，使手工构造的计划也能得到 `plan_id`，同时保持可读的非 ASCII 文本不变——因此所有已接受计划的 id 均不变。
- adapter 上报的 metadata 标识符被限制为 `[A-Za-z0-9._:/-]{1,128}`，否则归约为 `unknown`。该规则同时覆盖 `planning_model` 与 `exception_type`。

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
