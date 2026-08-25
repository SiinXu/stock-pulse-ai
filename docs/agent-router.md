# Agent 深度路由规则库

**状态**：Issue [#1120](https://github.com/SiinXu/stock-pulse-ai/issues/1120) 第一至三切片（规则库 + 结构化事实投影 + `AgentOrchestrator.run()` 应用）。Chat、factory、native adapter、Analyze、API、CLI、Bot、MCP 仍**未接线**。

**English**: [agent-router_EN.md](agent-router_EN.md)

## 诚实边界

`src/agent/runtime/agent_router.py` 提供纯规则 `AgentRouter`：根据**已经规范化**的分类事实，确定性选择分析深度与 Chat 路径。`src/agent/runtime/agent_router_facts.py` 从结构化 StockScope / entry_kind / 标的数量 / 可选的显式 per-run 覆盖投影这些事实。`AgentOrchestrator.run()`（仪表盘分析）对**每一次 run** 投影事实并应用路由器。这些切片：

- **不会**解析原始 prompt / 用户消息、provider 载荷或工具结果。
- **不会**改写 Settings/env `AGENT_ORCHESTRATOR_MODE`、Soul、ToolSurface、factory / native adapter、Chat/API/OpenAPI/Web/Desktop/CLI/Bot/MCP。
- **不会**写入 episode / trace 公共元数据、EvolutionEvent 或 memory admission。
- **不会**调用或扩展 `prefer_route`；miss-rate 证据在通过校验后**零路由影响**（身份中立，直至 #1091 / #1106）。
- **不会**把进程级 Settings/env `AGENT_ORCHESTRATOR_MODE` 复制为 `user_mode_override`。
- **不会**把 `report_type` 或 `skills` / `selected_skill_ids` 映射为路由器 mode。
- **不会**关闭 #1120：Chat incremental 真正跳过 `_execute_pipeline`（AC3）与运行元数据可见决策（AC4）仍属后续切片。factory / Chat / Analyze / CLI / Bot / MCP 仍未接线。

仪表盘 `run()` 失败关闭：投影或路由被拒绝时返回 `AgentResult(success=False)` 与公开执行失败文案，**不会**回退到构造时 mode。构造时配置的 mode 与 mode-budget limits 在成功、拒绝和所有异常路径上由 `finally` 恢复。Chat 仍始终调用 `_execute_pipeline`，仍使用构造时 mode。

## 输入

只接受有界分类事实（`AgentRouterRequest` 或同名字段 mapping）。任何未知 mapping 键失败关闭（`reason_code=unknown_field`），**不得**丢弃后继续路由，也**不得**把键名或取值写入 `error` / `explain`。

| 字段 | 约束 |
| --- | --- |
| `intent_category` | `simple` \| `technical` \| `news` \| `risk` \| `compare` \| `analysis` \| `unknown` |
| `symbol_count` | 非负 **int**（拒绝 bool / float / 字符串 / 负数） |
| `need_news` / `need_risk` | 严格 `bool`（拒绝 `0`/`1`/`"true"`） |
| `entry_kind` | `run` \| `chat` |
| `is_follow_up` / `same_symbol` / `tool_suitable` | 可选严格 `bool`，缺省 `false` |
| `user_mode_override` | 可选。缺省 / `None` 表示未提供 |
| `miss_rate` | 可选。若出现：有限实数，闭区间 `[0.0, 1.0]`（拒绝 bool、NaN/Inf、字符串、越界） |

非法或缺失的**必填**事实、未知 mapping 键、自相矛盾的分类事实、非严格布尔、非法枚举、非法计数，以及出现但畸形的 miss-rate，一律失败关闭：返回 `accepted=false` 的类型化决策，**不会**静默改写成 `standard`，也**不会**丢弃未知键后继续路由。未知键的拒绝不得回显键名或取值。

## 输出

| 字段 | 值 |
| --- | --- |
| `accepted` | 是否得到可用路由 |
| `mode` | 接受时为 `quick` \| `standard` \| `full` \| `specialist`；拒绝时为 `None` |
| `chat_path` | 接受时为 `incremental_tool` \| `full_repipeline`；拒绝时为 `None` |
| `reason_code` | 固定原因码（见下） |
| `error` | 仅拒绝时的短英文说明；不回显原始输入 |
| `explain` | 白名单派生事实；不含 prompt、消息、密钥、provider/tool 载荷、原始 override 字符串或原始 miss-rate |

深度模式与 `src.agent.orchestrator.VALID_MODES` 以及 `BUDGET_MODES` 去掉 Chat 预算档对齐。`strategy` / `skill` 作为合法覆盖别名规范化为 `specialist`。`chat` 不是路由器 mode。

## 规则

显式**合法**覆盖始终获胜。显式**非法 / 空白**覆盖：`reason_code=invalid_override`，`mode is None`。

本切片对矛盾事实的唯一契约是**失败关闭**（`inconsistent_facts`），而不是一边保留矛盾标志一边按意图抬升地板：

- `intent_category=risk` 且 `need_risk=false` → 拒绝，不得路由到 `standard` 或任何 mode。
- `intent_category=news` 且 `need_news=false` → 拒绝，不得路由到 `quick` / 低于 standard。
- `simple` 只允许单标的且无 news/risk；否则拒绝。
- `entry_kind=run` 不得携带 Chat 专用标志（`is_follow_up` / `same_symbol` / `tool_suitable`）；否则拒绝。
- `same_symbol=true` 要求 `is_follow_up=true`；否则拒绝。

自洽之后、无覆盖时的深度地板：

1. `need_risk=true` 的 `risk` 意图、其它 `need_risk`、`compare` 意图或 `symbol_count >= 2` → 至少 `full`（`floor_need_risk` / `floor_compare` / `floor_multi_symbol`，优先级同此顺序）。
2. 否则 `need_news=true` 的 `news` 意图或其它 `need_news` → 至少 `standard`（`floor_need_news`）。
3. 否则明确的单标的 `simple` 且无 news/risk → 可以 `quick`（`quick_eligible`）。
4. 否则默认 dashboard RUN 为 `standard` + `full_repipeline`（`default_standard`）。**从不**默认 always-full。`specialist` 只来自合法显式覆盖，不发明 Skill/模型路由。

Chat 路径（与深度独立，但 `full` / `specialist` 覆盖会强制重跑）：

- `entry_kind=chat` 且同标的 follow-up、无 news/risk、意图适合工具 → 可以 `incremental_tool`。
- 合法 RUN（无 Chat 专用标志）以及不满足上一条的 Chat → `full_repipeline`。

Miss-rate：出现则先按 `[0.0, 1.0]` 有限数值校验；两个不同的合法 miss-rate 必须得到相同的 `mode` / `chat_path` / `reason_code`。`explain.miss_rate_applied` 本切片恒为 `false`。畸形 miss-rate **不得**被吞掉。

## 原因码

接受：`explicit_override`、`default_standard`、`quick_eligible`、`floor_need_risk`、`floor_compare`、`floor_multi_symbol`、`floor_need_news`。

拒绝：`invalid_override`、`invalid_intent`、`invalid_symbol_count`、`invalid_flag`、`invalid_entry_kind`、`invalid_miss_rate`、`invalid_request`、`unknown_field`、`inconsistent_facts`。

## 用法

```python
from src.agent.runtime.agent_router import AgentRouter, AgentRouterRequest

decision = AgentRouter().route(
    AgentRouterRequest(
        intent_category="simple",
        symbol_count=1,
        need_news=False,
        need_risk=False,
        entry_kind="run",
    )
)
assert decision.mode == "quick"
assert decision.chat_path == "full_repipeline"
```

## 结构化事实投影（第二切片）

`project_router_request(facts)` 把**已经结构化**的运行时事实投影为合法 `AgentRouterRequest`，或在调用 `route()` **之前**给出类型化拒绝。投影器不会把 `AgentRouter.route()` 当作副作用来调用。未知 mapping 键失败关闭，且不回显键名或取值。

| 字段 | 规则 |
| --- | --- |
| `entry_kind` | 必填。只允许 `run` 或 `chat`（`ExecutionMode.RESEARCH` 及其它值失败关闭）。 |
| `scope_mode` | 可选。`maintain` / `compare` / `switch`。未知值失败关闭。 |
| `allowed_stock_codes` / `symbol_codes` | 可选的已规范化非空字符串序列。`symbol_count` 在 `allowed` 非空时取其长度，否则取 `symbol_codes` 长度，再否则为 `0`。字符串不当作字符序列。 |
| `expected_stock_code` | 可选字符串。仅用于推导 Chat `maintain` 的 same-symbol。 |
| `user_mode_override` | 可选字符串，且仅当调用方**已经**持有显式 per-run 值。缺省 / `None` 表示未提供。**从不**读取 `AGENT_ORCHESTRATOR_MODE`。非法 / 空白值原样传给路由器拒绝，**不会**改写成 `standard`。 |
| `intent_category` | 可选。缺省时：`scope_mode=="compare"` 则为 `compare`，否则为 `unknown`。除非调用方已提供该枚举，否则**从不**发出 `simple`。 |
| `need_news` / `need_risk` / `tool_suitable` | 可选严格布尔。缺省为 `false`。不从新闻文本、risk-gate 配置或工具目录推断。 |
| Chat 标志 | 派生字段，不作为输入。Chat `maintain` → follow-up，且在 `expected_stock_code` 非空时 same-symbol。Chat `switch` → follow-up 且非 same-symbol。Chat `compare` / 缺省 scope → 非 incremental。RUN 的 `is_follow_up` / `same_symbol` / `tool_suitable` 恒为 false；若调用方传入 `tool_suitable=true` 则失败关闭。 |

`report_type`、`skills`、`selected_skill_ids`、prompt、`miss_rate` 以及进程级配置键都是未知 mapping 键。

默认组合路由（先投影再 `route()`，仅测试）：

- RUN、单标的、缺省意图（`unknown`）、无 news/risk、无覆盖 → `standard` + `full_repipeline`（`default_standard`）。不是 `quick`。
- RUN `scope_mode=compare` 或 `symbol_count>=2` → `full` + `full_repipeline`。
- Chat `maintain` + 同标的 + 缺省 `tool_suitable=false` → `full_repipeline`（incremental 不得触发）。

```python
from src.agent.runtime.agent_router import route
from src.agent.runtime.agent_router_facts import project_router_request

projection = project_router_request(
    {
        "entry_kind": "run",
        "symbol_codes": ["600519"],
    }
)
assert projection.accepted is True
decision = route(projection.request)
assert decision.mode == "standard"
assert decision.chat_path == "full_repipeline"
```

## 仪表盘 run 应用（第三切片）

`AgentOrchestrator.run()` 从已解析的 StockScope 构造有界事实（`entry_kind=run`、`scope_mode`、标的代码），外加可选的显式 context `user_mode_override`。不读取 env/Settings、`report_type` 或 skills。接受路由后仅在本次 pipeline 设置 `self.mode`（及对应 mode-budget limits）。

```python
from src.agent.orchestrator import AgentOrchestrator

orch = AgentOrchestrator(tool_registry=registry, llm_adapter=adapter, mode="quick")
result = orch.run("analyze", {"stock_code": "600519"})
assert orch.mode == "quick"  # 构造时 mode 已恢复
```

投影/路由拒绝时不调用 `_execute_pipeline`。Chat 行为不变。

## 剩余工作（#1120 保持开放）

已落地：第一切片规则库；第二切片结构化事实投影；第三切片仪表盘 `run()` 应用（失败关闭，构造时 mode 恢复）。

仍待后续：

- 将投影器 + 路由器接入 factory / native adapter / analysis 与 Chat 入口（每 run 决策，而不是进程级 mode）。
- Chat `incremental_tool` 必须真正避免 `_execute_pipeline`（AC3）。Chat 仍未接线，仍始终重新跑 pipeline。
- 将 secret-free 决策写入 run-local 元数据（AC4）；episode 持久化需避开与 #1511 冲突。
- 基于 miss-rate 的 outcome bias 归 #1091 / #1106，且须有样本阈值。

回滚：先回退 `run()` 应用，再删除本库模块、测试、changelog fragment 与本文档即可；无迁移、无配置键。
