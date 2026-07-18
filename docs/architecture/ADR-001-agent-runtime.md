# ADR-001: Agent Runtime 架构 — Native 永久默认 + vendor-neutral Runtime Contract + 实验性 PydanticAI Adapter

- 状态:`Accepted`(维护者 2026-07-17 批准,含 D2 degraded 行为裁决;AR-PY-01 编码解除阻断)
- 日期:2026-07-17
- 决策者:Maintainer(SiinXu);起草:Runtime Tech Lead
- 代码 baseline:`main@fa7a6ee1`(行号取证于 `e58d71f2`,已核实 `e58d71f2..fa7a6ee1` 不涉及 Runtime 证据文件)
- 关联文档:
  - `docs/architecture/pydanticai-runtime-development-plan.md`(状态 `Approved`,分阶段执行计划)
  - `docs/stockpulse-agent-runtime-framework-comparison.md`(框架对比结论)
  - `docs/stockpulse-work-tracker.md`(AR 工作追踪)
  - `docs/agent-stream-events.md`(SSE 事件契约,9 种事件,additive 演进)

## 1. Context(背景与问题)

StockPulse 的 Agent 执行层(`src/agent/`)当前是纯 Native 实现:`build_agent_executor()`(`src/agent/factory.py:306`)按 `agent_arch` 装配 Single(`AgentExecutor`)或 Multi(`AgentOrchestrator`),共享 `LLMToolAdapter`(`src/agent/llm_adapter.py:341-345`)与 ToolRegistry。存在以下结构性缺口:

1. **无统一执行生命周期抽象**:`AgentExecution`/`ExecutionHandle`/`AgentRuntime` 等符号不存在;执行状态散落在同步调用栈与线程/queue 桥接中,无状态机、无 terminal precedence。
2. **无真实取消**:浏览器"停止"只 `abort()` 断开 fetch(`apps/dsa-web/src/stores/agentChatStore.ts:282-289`);后端 SSE finally 块仅等待、不终止执行线程(`api/v1/endpoints/agent.py:546-561`)。取消后模型请求与工具仍在消耗预算并可能产生副作用。
3. **工具边界有校验、无会话**:`tool_surface.py` 有参数校验、scope guard、超时与审计,但缺少 per-execution 冻结工具会话、permission 强制(`src/agent/tools/registry.py:43` 仅声明)、cancellation token 与迟到结果 fence。
4. **无 vendor 抽象层**:任何外部 Agent 框架(如 PydanticAI)若直接接入,将被迫与 `runner.py`/`orchestrator.py` 内部实现耦合,且可能形成第二套模型配置、会话与 usage 权威。

同时,PR #11 已合入 AR-01 replay characterization suite(`tests/test_agent_runtime_compatibility.py` + `tests/agent_runtime_replay.py` + 36 个 fixture),把现有行为(含两个 degraded `success=true` 行为)冻结为可回归验证的基线,为架构改造提供了安全网。

评估 PydanticAI(2026-07-17 观测:v2.12.0,Python >= 3.10,MIT)的动机:类型化 output、成熟的 tool/agent 循环与流式抽象可能降低 Native 循环的长期维护成本。但收益未经证实,必须以隔离 POC + conformance 证据裁决,且 `Native Only` 是合法终局。

## 2. Decision(决策)

### D1:三层架构 — Native 永久默认 + Runtime Contract + 实验性 Adapter

采用如下分层,作为 Agent Runtime 演进的唯一路线:

```text
API / Web / Desktop / Bot(公共契约,不变)
  -> StockPulse 业务层:Architecture 选择(single/multi/research)、Prompt/Skill、
     任务模型路由、报告 Schema、Conversation、Usage、Provider trace
      -> Runtime Contract(vendor-neutral):AgentExecution / ExecutionContext /
         ExecutionHandle / AgentRuntime protocol / 状态机 / typed events
          -> Native Runtime Adapter(默认、永久保留)
          -> PydanticAI Runtime Adapter(实验性、可选依赖、可整体移除)
```

约束:

- Runtime Contract 是纯 StockPulse 资产,**不出现任何 PydanticAI 类型**;Native Adapter 是首个也是永久默认实现。
- PydanticAI Adapter 是实验性、可选依赖、可整体删除的资产;删除它不回滚 Contract/BoundToolSession/生命周期带来的架构收益。
- `AGENT_ARCH` 语义不变:仍是业务 Architecture 选择器(single/multi),**不是** Runtime Adapter 选择器。Runtime 选择不向用户暴露(最多 internal-only 注入点)。
- 状态机:`created/running/succeeded/failed/cancelled/timed_out`;terminal 不可变;并发 terminal precedence 先到先终,后到丢弃并审计。
- 工具访问唯一通道为 BoundToolSession(执行期冻结、fail-closed:未知工具、越权 scope、超预算、超时、取消一律拒绝并审计,不静默降级)。

### D2:两个 degraded `success=true` 行为的裁决(已批准:冻结为兼容契约)

以下两个行为已被 replay fixture 冻结,维护者 2026-07-17 批准裁决为**正式兼容契约**(而非缺陷):

1. **预算不足/超时合成 degraded dashboard 且 `success=true`**:`src/agent/orchestrator.py:187-229` `_build_budget_skip_result()` 从已完成阶段合成内容并打 partial 标记(`:208-211`),`:216` 在合成内容非空时返回 `success=True`,同时 `error` 字段保留原因(`:219-222`);超时路径 `_build_timeout_result`(`:145-185`)语义相同。
2. **Decision 阶段解析失败按 Technical/Intel 合成报告且 `success=true`**:`src/agent/orchestrator.py:925-954` `_resolve_dashboard_payload()` 在最终输出不可解析时强制合成(`:941-942`),`:956-1015` 从 base opinion 推导结论,主循环 `:637-657` 最终 `success=bool(content)`。

裁决理由:

- 结果元数据已含可辨识信号:partial 标记文案 + `error` 字段 + `pipeline_budget_skipped`/`pipeline_timeout` 事件(`docs/agent-stream-events.md`),消费方可以区分完整成功与降级成功。
- 现有 Web/Bot/通知客户端依赖 `success=true` 走正常渲染路径;改为 `success=False` 属破坏性变更,需要全客户端兼容层,与本期"零公开契约变更"目标冲突。
- 该语义符合仓库稳定性护栏("单一数据源/阶段失败不应拖垮整个分析流程")。

约束与演进路径:

- 冻结期间,任何 Runtime Adapter(含 PydanticAI POC)必须逐字节复现该语义;conformance 双跑以现状为基线。
- 未来若判定需要修正(如引入显式 `degraded: true` 顶层字段或改变 `success` 语义),必须走独立 ADR + versioned fixture(新增 fixture 版本,不删除、不放宽现有 36 个),并提供客户端兼容层。
- AR-PY-03 引入真实取消后,degraded 合成仅允许发生在"未取消"路径;取消路径终态必须是 `cancelled`,不得产出伪成功。

### D3:所有权边界(不可让渡清单)

StockPulse 永久拥有(任何外部框架不得复制或替代):

- Single/Multi/Research Architecture 与金融阶段拓扑(technical/intel/risk/decision/portfolio/skill)。
- Provider Catalog、Connection、Available Models Catalog 与任务模型路由(`src/agent/litellm_route_resolution.py:70-100`);**不存在自由文本模型字符串直通路径**,任何 Adapter 不得接受第二套 provider/model 配置。
- Prompt/Skill 选择、模型 fallback 顺序(`models_to_try`)、报告 Schema。
- Execution 生命周期、状态机、取消、typed events 与 terminal precedence。
- Tool policy、scope、permissions、deadline、预算、审计与脱敏。
- Conversation(`src/agent/conversation.py`)、Provider trace(`src/agent/provider_trace.py`、`executor.py:722-803`)、Usage(`runner.py:458-459`)、错误契约与持久化。
- API/SSE/Web/Desktop/Bot 公共兼容契约。

PydanticAI 只允许拥有:单个 Execution/Stage 内部的模型调用与工具循环实现、`RunContext` 内部映射、经 BoundToolSession 包装的工具桥接、typed output 内部解析,以及映射回 StockPulse 权威契约的临时运行状态。其 message history/usage 仅作运行态,单向映射回 StockPulse 权威,不落库。

第一阶段禁区(任何 PR 不得触碰):PydanticAI 接管 Multi 拓扑;第二套模型配置;第二套 Conversation;向其暴露数据库/Config/原始 ToolRegistry/完整 `.env`;默认开放 MCP/Web/Shell/文件系统/代码执行工具;Pydantic Graph/durable execution/持久 Job/数据库迁移;修改设置页或公开 API;删除或弱化 Native、Native tests、replay fixture。

### D4:依赖与版本策略

- `pydantic-ai` 为**可选依赖**,精确 pin(以 AR-PY-04 合入当日最新稳定版为准;2026-07-17 观测为 2.12.0),不进入默认 `requirements.txt` 与 Desktop 默认打包清单;缺少依赖时 Native 正常启动(惰性 import + 明确错误)。
- 版本升级走独立 PR,伴随 conformance 全量重跑。
- 模型接入方式(方案 A:PydanticAI LiteLLM Model;方案 B:自定义 Model 包装 `LLMToolAdapter`)**不预选**,由隔离 Spike 按开发计划第 6.3 节标准打分,维护者裁决(官方 LiteLLM Model 文档页 2026-07-17 访问 404,为 Evidence gap G1)。

## 3. Consequences(后果)

正面:

- Native 三条路径获得统一生命周期、真实取消与 fail-closed 工具边界——**即使 PydanticAI 最终不被采用,这些收益仍然保留**。
- 外部框架评估被约束在 Contract 之后的隔离 Adapter 内,不污染业务层与公共契约。
- 36 个 replay fixture + conformance 双跑使每一步改造均可逐字节回归。

负面/成本:

- 新增 Contract 层与包装层带来一次性抽象成本与每次调用的轻微开销(以 replay 套件运行时间做回归观测)。
- PydanticAI POC 期间需维护可选依赖矩阵(装/不装两态均需测试)。
- 裁决"冻结 degraded 行为"意味着短期内不修正 `success` 语义的历史包袱,依赖元数据信号辨识降级。

回滚:

- 每阶段 PR 独立可 revert;PydanticAI 资产(adapter + 可选依赖清单 + 注入点)整体删除即回到 Native Only。
- 本 ADR 若被拒绝:维持现状,开发计划终止,replay 套件继续作为行为基线服务日常回归。

## 4. Alternatives considered(备选方案)

| 备选 | 描述 | 拒绝理由 |
| --- | --- | --- |
| A1 维持现状 | 不引入 Contract,不评估外部框架 | 生命周期/取消/工具会话缺口继续存在;"停止"语义对用户失真;每次外部框架评估都要重新入侵核心文件 |
| A2 直接迁移到 PydanticAI | 以 PydanticAI 替换 Native 循环为默认路径 | 无 conformance 证据;违反"Native 永久默认";一旦框架演进破坏契约无退路;金融阶段拓扑与降级语义移交第三方抽象,风险不可控 |
| A3 仅做 Native 生命周期改造,不设 vendor Contract | 修 runner/orchestrator 但不抽象 Runtime | 下次评估任何框架仍需再次开膛;Contract 的边际成本低(AR-PY-01 一个 PR),且是隔离 POC 的前提 |
| A4 采用其他框架优先(LangGraph/AutoGen/CrewAI 等) | 以其他框架做第一优先 POC | 见 `docs/stockpulse-agent-runtime-framework-comparison.md`:PydanticAI 与现有 Pydantic/typed-schema 栈同源、依赖面较小、Model 抽象公开可子类化,为当前第一优先 Python POC;其余框架保留为后续候选,Contract 对其同样适用 |

## 5. Compliance & verification(合规与验证)

- 编码前置:本 ADR `Accepted` + D2 裁决获维护者批准(开发计划第 4.2 节 B1/B2)。
- 每阶段硬验收:36 个 replay fixture 零删除、零放宽、零修改通过;公开 API/SSE/数据库契约零变更(AR-PY-06 获批前)。
- 静态守卫:PydanticAI 代码路径不得 import `system_config_service`/`provider_catalog` 或直接读取 Connection 配置。
- 全局停止条件与风险登记见开发计划第 12 章;任一停止条件满足即回到 `Native Only` 并把结论写回本 ADR。

## 6. Decision log

| 日期 | 状态 | 说明 |
| --- | --- | --- |
| 2026-07-17 | Proposed | 初稿随 AR-PY-00 送审;D2 为建议裁决,待维护者批准 |
| 2026-07-17 | Accepted | 维护者批准审批点 1(架构)与审批点 2(D2 冻结为兼容契约);AR-PY-01 解除阻断 |
