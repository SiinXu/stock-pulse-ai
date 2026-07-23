# StockPulse PydanticAI Runtime Adapter 分阶段开发计划

> **历史文档，已停止执行。** RF-07 于 2026-07-18 裁决 `Native Only`，
> 该裁决于 2026-07-19 完整实施。本文仅保留 POC 的历史背景与证据，
> 不是当前开发指令；不得据此恢复已删除的 Adapter、依赖、注入点或 CI。

## 1. 文档状态、baseline、适用范围与非目标

- 状态:`Historical / Superseded`（曾于 2026-07-17 批准，现由 ADR-001 的
  `Native Only` 实施结论取代）
- 版本:v0.3
- 日期:2026-07-19（标记历史状态；原计划内容保持为审计记录）
- 作者角色:Principal Architect / Runtime Tech Lead
- 代码 baseline:`main@fa7a6ee1`(`Merge pull request #10 ... login-modern-redesign`)
  - 本工作区远端命名:`mine` = `SiinXu/stock-pulse-ai`(StockPulse 权威主线);规划 prompt 中的 "origin/main" 在本工作区语境下即 `mine/main`
  - 规划 prompt 引用的 `b8ac3a0a` 仅为 2026-07-17 拟稿时的参考快照;文中行号取证于 `e58d71f2`,已核实 `e58d71f2..fa7a6ee1` 仅涉及 `apps/dsa-web/` 与 `docs/CHANGELOG.md`,不影响任何 Runtime 证据文件与行号
- 适用范围:Agent Runtime 架构演进(Runtime Contract、Native Adapter、BoundToolSession、生命周期/取消、PydanticAI 隔离 POC、conformance/benchmark 与条件产品化)
- 非目标:
  - 不将 StockPulse 整体迁移到 PydanticAI
  - 不改变 Single/Multi/Research 业务 Architecture 的归属
  - 不新增用户可见配置、API、数据库表或设置页(AR-PY-06 获批前)
  - 本文档本身不修改任何生产代码、依赖、配置或测试

原计划目标架构（历史记录，不代表当前可执行架构）:

```text
StockPulse Native Architecture
  -> StockPulse Runtime Contract
      -> Native Runtime Adapter(默认、永久保留)
      -> PydanticAI Runtime Adapter(实验性、可移除)
```

## 2. 背景、当前痛点与为什么现在评估 PydanticAI

### 2.1 背景

StockPulse 拥有一套完整的 Native Agent 实现:Single(`AgentExecutor`)、Multi(`AgentOrchestrator`,金融阶段拓扑)与 Research(`ResearchAgent`)。模型调用统一经 LiteLLM 路由解析,工具经 Tool Surface 校验执行,输出经报告 Schema 与 SSE 事件契约向 API/Web/Desktop/Bot 交付。PR #11(`0d070596`)合入了 36 个 replay fixture 与兼容测试,冻结了现有行为基线。

### 2.2 当前痛点(以代码为证,见第 3 章)

1. 没有统一的执行生命周期抽象:`AgentExecution`/`ExecutionHandle`/`AgentRuntime` 均不存在,执行状态散落在同步调用栈与线程/queue 桥接中。
2. 没有真实取消:Web 停止按钮只 abort 浏览器侧 fetch(`agentChatStore.ts:282-289`),后端线程继续运行至自然结束(`api/v1/endpoints/agent.py:546-561` 仅等待 5s 后放手)。
3. 工具边界不完整:Tool Surface 有校验/scope/timeout/审计/脱敏,但没有 per-execution 冻结会话、principal/permission 强制与 cancellation token(`src/agent/tools/registry.py:43` permissions 仅声明)。
4. 手写工具循环与 JSON 解析承担了大量维护成本,typed output 验证、结构化流式输出等能力需要持续自研。
5. 事件契约无版本号与 sequence(`src/agent/stream_events.py:13-22`),难以支撑多 Runtime 等价性验证。

### 2.3 为什么现在评估 PydanticAI

- PR #11 的 replay 安全网已就位,首次具备"以相同输入验证两个 Runtime 等价"的能力,评估窗口成熟。
- PydanticAI(访问日期 2026-07-17,详见第 16 章)提供 typed output、Toolset 抽象、流式 partial validation 与多 agent 模式,与 StockPulse 自研方向重叠度高,值得用隔离 POC 验证"外包工具循环"是否降低维护成本。
- 同时,评估必须允许 `Native Only` 结论:若无收益或维护/打包成本高于 Native,停止并保持 Native Only 是合法且体面的终局。

## 3. 当前代码事实与行号证据

以下事实基于 `main@e58d71f2` 逐条核实。任何 Runtime 改造 PR 都必须重新核对本章行号。

### 3.1 依赖与符号现状

| # | 事实 | 证据 |
| --- | --- | --- |
| F1 | 仓库无 `pydantic-ai` 依赖与生产代码 | `requirements.txt`、`pyproject.toml`、`src/`、`api/` 全量检索无 `pydantic_ai`/`pydantic-ai` |
| F2 | 不存在 `AgentExecution`、`ExecutionHandle`、`BoundToolSession`、`AgentRuntime` 符号 | `src/`、`api/` 全量检索无命中 |
| F3 | `tests/agent/runtime/` 目录不存在 | `tests/` 目录树核实;fixture 位于 `tests/fixtures/agent_runtime/` |

### 3.2 Factory 与业务 Architecture

- `src/agent/factory.py:306` `build_agent_executor()` 是唯一装配入口;`:330` 读取 `arch = getattr(config, "agent_arch", "single")`;`:347-354` `arch == "multi"` 时构建 `AgentOrchestrator`,否则 `:356-361` 返回 `AgentExecutor`。
- 这是**业务 Architecture 选择器,不是 Runtime Adapter 选择器**:两个分支共享同一 `LLMToolAdapter`(`:345`)与 ToolRegistry(`:334`),没有任何 vendor 抽象层。
- Single/Multi/Research 是 StockPulse 业务资产:
  - Single:`src/agent/executor.py:509-525`(`AgentExecutor.__init__` 持有 `max_steps`/`timeout_seconds`),`:805-857` 委托共享循环。
  - Multi:`src/agent/orchestrator.py:64-66`(`VALID_MODES = ("quick", "standard", "full", "specialist")`,`NON_CRITICAL_BASE_STAGES = {"intel", "risk"}`),`:126-143` 按 stage(technical/intel/risk/decision/portfolio/skill)定义超时。
  - Research:`src/agent/research.py:37-70`(`ResearchAgent`,独立 token 预算,默认 30000,`:34`)。

### 3.3 Native 循环、预算与降级语义

- 工具循环:`src/agent/runner.py:317-353` `run_agent_loop()` 声明 `max_steps`、`max_wall_clock_seconds`、`tool_call_timeout_seconds`;`:392-409` 步循环内检查剩余预算,低于 `_MIN_STEP_BUDGET_S = 8.0`(`:369`)触发预算护栏结果。
- 阶段编排:`src/agent/orchestrator.py:470-489` pipeline 超时路径(发 `pipeline_timeout` 事件后调 `_build_timeout_result`);`:491-523` 预算不足路径(发 `pipeline_budget_skipped` 事件后调 `_build_budget_skip_result`);`:608-628` 非关键阶段失败仅记降级(`_record_degraded_stage`,`:799-813` 写入 `ctx.meta["degraded_stages"]`),关键阶段(technical/decision)失败返回 `success=False`。

### 3.4 两个已冻结、需 ADR 裁决的 degraded `success=true` 行为

这两个行为已被 PR #11 的 replay fixture 冻结为现状基线。在 ADR-001 明确"正式兼容契约 vs 历史缺陷"之前,**PydanticAI POC 不得自行改变它们**,conformance 比对必须按现状复现:

1. **预算不足合成 degraded dashboard 且 `success=true`**:
   `src/agent/orchestrator.py:187-229` `_build_budget_skip_result()` 调用 `_resolve_final_output()`(`:206`)从已完成阶段合成 dashboard,打上 partial 标记("多 Agent 预算不足,以下结论基于已完成阶段自动降级生成",`:208-211`),最终 `:216` 返回 `success=bool(content) if (not parse_dashboard or dashboard is not None) else False`——即合成内容非空时 `success=True`,同时 `error` 字段仍写入预算不足原因(`:219-222`)。超时路径 `_build_timeout_result`(`:145-185`,`:175`)语义相同。
2. **Decision 阶段无法解析时按 Technical/Intel 合成报告且 `success=true`**:
   `src/agent/orchestrator.py:886-923` `_resolve_final_output()` 依次尝试解析 dashboard;`:925-954` `_resolve_dashboard_payload()` 在 `final_dashboard`/`final_raw` 均不可用时,`:941-942` 以空 payload 调 `_normalize_dashboard_payload({}, ctx)` 强制合成;`:956-1015` 从 base opinion(technical/intel)推导 `decision_type`/`confidence`/`analysis_summary`;主循环 `:637-657` 最终 `success=bool(content)` 返回。

### 3.5 模型调用链(单一权威)

- `src/agent/llm_adapter.py:341-345` `LLMToolAdapter` 是统一 LiteLLM 工具调用适配器;`:94-95` `LLMResponse` 携带 `reasoning_content` 与 `provider_blocks`(如 Claude thinking/redacted_thinking);`:102-108` thinking payload 按模型白名单注入(`_AUTO_THINKING_MODELS`/`_OPT_IN_THINKING_MODELS`)。
- `src/agent/litellm_route_resolution.py:70-100` `resolve_agent_litellm_route(config)` 产出 `primary_model` 与 `models_to_try`(fallback 顺序)——模型解析、fallback 与 wire model 归 StockPulse 所有。
- `src/llm/provider_catalog.py:25` 起 `_PROVIDERS` 定义 Provider 元数据;Available Models 由 Connection 运行时提供;`src/services/system_config_service.py:73,77` `build_connection_contract_values()`/`validate_connection_contract_values()` 是配置入口。
- **不存在自由文本模型字符串直通路径**:所有模型必须经配置解析与路由验证。任何 Runtime Adapter 不得接受第二套 provider/model 字符串配置。

### 3.6 Tool Surface 现状(有边界,非沙箱)

- 已有:参数校验(`src/agent/tool_surface.py:102-125`)、scope 契约与 stock scope guard(`:114-165`)、超时执行(`:169-188`,ThreadPoolExecutor)、结果字节截断(`:214-217`、`:394-405`)、审计(`:226-232` `build_tool_audit`)、脱敏(`src/agent/tools/execution.py:354-375` `redact_diagnostic_value`、`:235-250` `_redact_structured_secrets`)。
- 缺失(AR-PY-02 目标):per-execution 冻结工具会话、principal/permission grant 强制(`src/agent/tools/registry.py:43` 仅声明)、cancellation token、幂等/重试策略、迟到结果 fence、总工具预算。

### 3.7 API/SSE 执行与"停止"的真实语义

- `api/v1/endpoints/agent.py:460` 创建 `asyncio.Queue`;`:475` 执行线程经 `run_coroutine_threadsafe` 推送事件;`:528` `loop.run_in_executor(None, run_sync)` 在线程池执行阻塞调用;`:526-545` SSE `event_generator` 消费 queue;`:546-561` finally 块仅 `asyncio.wait_for(fut, timeout=5.0)` 等待、不杀线程,`CancelledError` 静默。
- Web 侧:`apps/dsa-web/src/api/agent.ts:90-102` fetch + AbortSignal;`apps/dsa-web/src/stores/agentChatStore.ts:282-289` `stopStream()` 仅 `abortController.abort()`。
- 结论:**浏览器停止只断开传输,不能证明后端工作已终止**。`tests/test_agent_sse_cleanup.py:55-80` 冻结的是清理告警语义,不是取消语义。

### 3.8 Conversation / Provider trace / Usage / 报告归属

- 会话:`src/agent/conversation.py:26-30` `add_message()` 落库,`:37-40` `get_history()` 读取。
- Provider trace:`src/agent/provider_trace.py:28-46`(thinking block 类型、`must_roundtrip`);`src/agent/executor.py:722-803` `_persist_provider_trace()` 经 `db.save_agent_provider_turn()` 持久化。
- Usage:`src/agent/runner.py:41-43` 导入 usage 持久化,`:458-459` 每次 LLM 调用后 `_persist_usage(..., call_type="agent")`。
- 以上均由 StockPulse 拥有;PydanticAI 的 message history/usage 只能作为内部运行态,单向映射回上述权威。

### 3.9 无持久 Agent Job

- `src/`、`api/` 中无 job/resume/checkpoint 机制;执行状态仅存活于进程内线程与调用栈。**不能承诺跨进程重启 resume**;本计划不引入持久 Job(见第 5 章禁区)。

### 3.10 Replay 安全网(PR #11)

- `tests/agent_runtime_replay.py:92-150` `ReplayLLMAdapter` 注入替换 `LLMToolAdapter`,严格按序消费录制转录,超出即 `AssertionError`(`:117-119`),并校验 `allowed_stage`(`:131-135`)。
- `tests/fixtures/agent_runtime/manifest.json:1-42`:36 个 fixture = 24 financial(A/HK/US 各 8:`single_run`/`single_chat`/`quick`/`standard`/`full`/`specialist` 6 模式 + 2 partial/degraded)+ 12 contract(modelref/fallback/toolscope/timeout/cancelrace/malformed 6 profile × 2)。
- `tests/agent/test_agent_runtime_compatibility.py` 断言输出、工具调用序列与 factory 契约。这是**现有行为基线**,不代表 Runtime Contract、生命周期或 PydanticAI Adapter 已实现。
- 事件契约:`docs/agent-stream-events.md:41-54` 冻结 9 种事件(`stage_start`/`stage_done`/`thinking`/`tool_start`/`tool_done`/`generating`/`pipeline_timeout`/`pipeline_budget_skipped`/`done`/`error`),additive 演进;`src/agent/stream_events.py:13-22` 事件为无版本、无 sequence 的 dict。
- CI:`.github/workflows/ci.yml:54-90` `backend-gate` 执行 `./scripts/ci_gate.sh` 四阶段(syntax/flake8/deterministic/offline-tests,`:84-90`);replay 兼容测试包含在 offline-tests(`pytest -m "not network"`,`scripts/ci_gate.sh:25-34`)中;`web-gate`(`:220-246`)与 `web-e2e`(`:294-307`,`npm run test:smoke`)按前端改动触发。

## 4. 已批准决策、未决问题与阻断项

### 4.1 文档漂移(重要事实)

规划 prompt 列为"必须完整阅读"的 9 份仓库资料中,截至 `e58d71f2` **仅 2 份存在**:`AGENTS.md`、`docs/agent-stream-events.md`。以下 7 份在主线、全部远端分支与本机全部工作区均不存在:

- `docs/stockpulse-agent-runtime-framework-comparison.md`
- `docs/stockpulse-ar01-agent-runtime-adr-prompt.md`
- `docs/stockpulse-ar02a-native-execution-lifecycle-implementation-prompt.md`
- `docs/stockpulse-document-governance.md`
- `docs/stockpulse-domain-decisions.md`
- `docs/stockpulse-product-overview.md`
- `docs/stockpulse-work-tracker.md`
- `docs/architecture/ADR-001-agent-runtime.md`(`docs/architecture/` 目前仅含 `api_spec.json`)

处理决定(已与用户确认):如实记录为文档漂移/Evidence gap,并把"创建或迁入这些治理文档"列入 AR-PY-00 的阻断项。prompt 中"更新框架对比文档的 Vercel Harness 旧结论"与"更新 Work Tracker 旧 baseline 与 AR-07 描述"两条指令,在文档不存在的现实下转化为:**创建或迁入时即以 PydanticAI 为第一优先 Python POC、以 `e58d71f2` 后的最新主线为 baseline 建立正确结论**,不再产生需要修正的旧结论。

### 4.2 阻断项(编码前必须关闭)

| ID | 阻断项 | 状态 |
| --- | --- | --- |
| B1 | `docs/architecture/ADR-001-agent-runtime.md` 不存在,更未 `Accepted` | **已关闭**:ADR-001 于 2026-07-17 创建并获维护者 `Accepted` |
| B2 | 两个 degraded `success=true` 行为未获 ADR 裁决(第 3.4 节) | **已关闭**:维护者 2026-07-17 批准 ADR-001 D2(冻结为兼容契约) |
| B3 | 本计划状态为 `Proposed`,未获维护者批准 | **已关闭**:维护者 2026-07-17 批准("按照本计划开始开发"),状态更新为 `Approved` |
| B4 | 治理文档漂移(第 4.1 节) | AR-PY-00 内创建/迁入 |

### 4.3 已确认决策(本次规划过程)

- baseline 使用执行时最新主线 `e58d71f2`(非 prompt 快照 `b8ac3a0a`)。
- 规划分支 `codex/pydanticai-runtime-development-plan` 从最新主线创建;本文档是该分支唯一产物。
- 文档语言:中文正文 + 英文术语;GitHub 协作内容(Issue/PR 标题正文等)按 `AGENTS.md` 使用英文。

### 4.4 未决问题(留给人工审批,见第 14 章)

ADR 裁决、方案 A/B 选择、POC 首路径、benchmark 预算、产品化与否、Runtime 是否向用户暴露。

## 5. 目标架构与所有权边界

### 5.1 分层

```text
API / Web / Desktop / Bot(公共契约,不变)
  -> StockPulse 业务层:Architecture 选择(single/multi/research)、Prompt/Skill、
     任务模型路由、报告 Schema、Conversation、Usage、Provider trace
      -> Runtime Contract(vendor-neutral):AgentExecution / ExecutionContext /
         ExecutionHandle / AgentRuntime protocol / 状态机 / typed events
          -> Native Runtime Adapter(默认、永久保留)
          -> PydanticAI Runtime Adapter(实验性、可选依赖、可整体移除)
              -> BoundToolSession(唯一工具桥,fail-closed)
              -> 已解析执行期模型信息(方案 A 或 B,见第 6 章)
```

### 5.2 StockPulse 继续拥有(不可让渡)

- Single/Multi/Research Architecture 与金融阶段拓扑(technical/intel/risk/decision/portfolio/skill)。
- Provider Catalog、Connection、Available Models Catalog 与任务模型路由(`litellm_route_resolution.py`)。
- Prompt/Skill 选择、模型 fallback 顺序、报告 Schema。
- Execution 生命周期、状态机、取消、事件与 terminal precedence。
- Tool policy、scope、permissions、deadline、预算、审计与脱敏。
- Conversation、Provider trace、Usage、错误契约、历史记录与报告持久化。
- API/SSE/Web/Desktop/Bot 公共兼容契约。

### 5.3 PydanticAI 只允许拥有

- 单个 Execution/Stage 内部的模型调用与工具循环实现。
- `RunContext` 对冻结 Execution 依赖的内部映射。
- 经 BoundToolSession 包装后的工具描述与调用桥接。
- Pydantic typed output 的内部解析与验证。
- 映射回 StockPulse typed events、usage 与 terminal result 的临时运行状态。

### 5.4 第一阶段禁区(任何 PR 不得触碰)

- PydanticAI 接管 Multi Agent 金融阶段拓扑。
- PydanticAI provider/model string 形成第二套用户模型配置。
- PydanticAI message history 成为第二套业务 Conversation。
- 向 PydanticAI 暴露数据库、Config、原始 ToolRegistry、ToolSurface handler 或完整 `.env`。
- 默认开放 MCP、Web、Shell、文件系统、代码执行或第三方内建工具。
- 引入 Pydantic Graph、durable execution、持久 Job 或数据库迁移。
- 修改 Web 设置页、公开 API 或让用户选择实验 Runtime。
- 删除或弱化 Native Runtime、Native tests 或 replay fixture。

## 6. 方案 A/B 模型接入 Spike(不预选)

外部核对(2026-07-17)显示 PydanticAI 官方 LiteLLM Model 文档页当时不可达(404,Evidence gap,见第 16 章),因此**必须先跑隔离 Spike,不得凭假设选型**。

### 6.1 方案 A:PydanticAI LiteLLM Model

StockPulse 先经 `resolve_agent_litellm_route()` 完成 Connection/任务路由/fallback 解析,把**已解析的执行期模型信息**(wire model、api_base、key、超时)传给 PydanticAI 的 LiteLLM Model。

Spike 必须验证:

- 不重新读取用户 provider/model 配置(静态守卫:PydanticAI 代码路径不 import `system_config_service`/`provider_catalog`)。
- 不改变现有 LiteLLM wire model、fallback、thinking payload(`llm_adapter.py:102-108`)、timeout 与 provider trace。
- 不重复注册成本、usage 或 fallback(禁用 PydanticAI `FallbackModel`,fallback 仍由 StockPulse `models_to_try` 驱动)。

### 6.2 方案 B:自定义 PydanticAI Model Adapter

以自定义 `Model` 子类包装现有 `LLMToolAdapter`(`llm_adapter.py:341`)或更低层的已解析调用接口。

Spike 必须验证:

- tool call、reasoning/provider blocks(`LLMResponse.reasoning_content`/`provider_blocks`)、usage、错误能否无损映射。
- 是否比方案 A 更稳定,而不制造过厚的双向适配层。
- PydanticAI 版本升级时,`Model` 抽象作为公开接口的稳定性与私有接口依赖的维护成本。

### 6.3 选择标准(Spike 结束后按证据打分,维护者裁决)

| 维度 | 衡量方式 |
| --- | --- |
| Provider/Model 配置一致性 | 静态守卫 + contract fixture(modelref/fallback profile)零漂移 |
| Tool call 与 structured output 保真 | replay contract fixture 对比;malformed profile 行为一致 |
| Streaming/usage/fallback/timeout/cancel/错误映射 | 12 个 contract fixture + 取消竞态测试全绿 |
| 测试替身可控性 | 能否以 deterministic fake model 驱动(不依赖网络) |
| 依赖耦合、升级成本、Desktop 打包 | 依赖树 diff、PyInstaller 冻结试验、版本 pin 策略评估 |

两方案在任一硬性维度 fail-closed 失败即淘汰;全部通过时按维护成本与保真度加权,推荐值见第 14 章审批点 3。

## 7. AR-PY-00 ~ AR-PY-06 分阶段计划

每阶段:目标 / 前置 / 预计文件(均为"预计新增或修改",非当前事实)/ 测试 / 验收 / 风险 / 回滚 / 禁止越界。测试命令详见第 10 章。

### AR-PY-00:决策与基线收敛(docs-only)

- 目标:
  - 起草并送审 `docs/architecture/ADR-001-agent-runtime.md`(决策:Native 永久默认 + vendor-neutral Contract + PydanticAI 实验 Adapter;PydanticAI 为第一优先 Python POC)。
  - 对两个 degraded `success=true` 行为(第 3.4 节)给出裁决建议并送审。
  - 创建或迁入第 4.1 节缺失的治理文档(framework comparison、work tracker 等),以最新主线为 baseline,不引入旧结论。
  - 记录 PydanticAI 版本、许可证、Python/Desktop/Docker 支持与 Evidence gap(以合入当日重新核对官方资料,更新第 16 章)。
- 前置:本计划获批。
- 预计文件:`docs/architecture/ADR-001-agent-runtime.md`(新)、`docs/stockpulse-agent-runtime-framework-comparison.md`(新建或迁入)、`docs/stockpulse-work-tracker.md`(新建或迁入)、本文档状态位更新。
- 测试:`python scripts/check_ai_assets.py`、`git diff --check`、文档验证命令(第 10.3 节)。
- 验收/退出条件:ADR 与两项 degraded 裁决获维护者批准。**未批准则停止,不进入任何编码阶段。**
- 风险:裁决久拖导致后续阶段全部阻塞——按期升级给维护者,不得绕过。
- 回滚:revert 文档 PR 即可,无代码影响。
- 禁止越界:任何生产代码、依赖、目录骨架、feature flag、配置字段。

### AR-PY-01:Runtime Contract + Native Adapter(vendor-neutral)

- 目标:定义纯 StockPulse 的 Contract 并让 Native 三条路径接入,**不出现任何 PydanticAI 类型**。
  - `AgentExecution` / `ExecutionContext`(冻结输入:architecture、已解析模型路由、工具白名单、预算、deadline)。
  - `ExecutionHandle`(状态查询 + `request_cancel()`)。
  - `AgentRuntime` protocol(Native 为首个实现)。
  - 状态机:`created/running/succeeded/failed/cancelled/timed_out`;terminal 不可变;并发 terminal precedence(先到先终,后到丢弃并审计)。
  - Native Single/Multi/Research Adapter:包装 `build_agent_executor()` 现有产物,不重写内部逻辑。
  - 现有同步入口与 callback/SSE 兼容层原样保留(`api/v1/endpoints/agent.py` 不改公开行为)。
- 前置:AR-PY-00 批准。
- 预计文件:`src/agent/runtime/__init__.py`、`src/agent/runtime/contract.py`、`src/agent/runtime/native_adapter.py`(均为新增);`src/agent/factory.py` 增加薄装配入口(不改变默认行为);新增 `tests/agent/runtime/` 契约测试。
- 测试:第 10.1 节全量;replay 兼容套件必须零修改通过。
- 验收:Native 默认输出、工具调用序列、provider/model attribution、usage、错误与 36 个 replay 结果逐字节不变;新状态机契约测试全绿。
- 风险:Contract 过度设计或包装层泄漏语义——以"包装不重写"为审查红线。
- 回滚:revert PR;Contract 无外部消费方,不影响公开契约。
- 禁止越界:PydanticAI 依赖/类型、API/UI 改造、事件格式变更。

### AR-PY-02:BoundToolSession 与统一 Tool Bridge

- 目标:任何 Runtime 只能经执行期冻结的工具会话调用金融能力。
  - 会话身份:execution/stage/attempt identity。
  - 冻结 allowed tool names;principal、permission grants 与 stock/portfolio/account scope(把 `registry.py:43` 的声明变为强制)。
  - deadline、cancellation token、结果大小与总工具预算(复用 `tool_surface.py` 既有 timeout/truncation,收敛为会话级预算)。
  - idempotency/retry policy 与 audit context(挂接 `build_tool_audit`)。
  - 工具描述的中立导出(供未来映射到 PydanticAI Tool/Toolset schema),**不泄露原始 handler**。
  - 输入/输出验证、异常脱敏(复用 `execution.py` redaction)、并行调用与迟到结果 fence。
- 前置:AR-PY-01 合入。
- 预计文件:`src/agent/runtime/tool_session.py`(新)、`src/agent/tool_surface.py`(接线改造)、`tests/agent/runtime/test_tool_session.py`(新)。
- 测试:第 10.1 节全量 + 新增 fail-closed 用例。
- 验收:未知工具、越权 scope、超预算、超时与取消**全部 fail-closed**(拒绝并审计,不静默降级);Native 经会话执行后 replay 结果不变。
- 风险:会话包装引入每次调用开销——以 replay 套件运行时间做粗粒度回归观测。
- 回滚:revert PR;Native 可直接回退到 ToolSurface 直连。
- 禁止越界:外部 Runtime、用户配置、新工具能力。

### AR-PY-03:Lifecycle、typed events、usage 与真实取消

- 目标:在外部 Runtime POC 前关闭生命周期缺口。
  - versioned internal events(含 execution/stage/attempt/sequence),现有 9 种 SSE 事件(`docs/agent-stream-events.md:41-54`)由**单一 SSE compatibility adapter** 从内部事件降级映射,公开契约 additive 不破坏。
  - `cancel_requested`(意图)与最终 `cancelled`(结果)分离。
  - cooperative cancellation 贯穿:模型调用、串行工具、并行工具、stage boundary(`orchestrator.py:470-523` 的预算/超时检查点扩展为取消检查点)。
  - 取消/超时后的 late message、provider trace、report 与副作用阻断(late-write fence:terminal 后到达的写入丢弃并审计)。
  - 统一 UsageRecorder(收敛 `runner.py:458-459` 的直接持久化)与稳定错误分类。
  - 进程内 registry 仅在必要时新增,含容量上限、terminal TTL 与"不可跨进程恢复"的明示语义;若现有 queue 桥接已足够则**不新增**。
- 前置:AR-PY-02 合入。
- 预计文件:`src/agent/runtime/events.py`、`src/agent/runtime/lifecycle.py`(新);`src/agent/runner.py`、`src/agent/orchestrator.py`、`api/v1/endpoints/agent.py` 接线;`tests/agent/runtime/test_lifecycle.py`(新)。
- 测试:第 10.1 节全量 + Barrier/Event 构造的取消竞态用例(禁止 sleep 竞态,见第 10.2 节)。
- 验收:停止后不产生伪成功、不重复副作用、不被迟到结果覆盖终态;`test_agent_sse_cleanup.py`、`test_agent_stream_events.py` 零修改通过;SSE 对外表现不变。
- 风险:取消语义改变两个 degraded 行为的观测面——degraded 合成仅允许发生在"未取消"路径,取消路径终态必须是 `cancelled`。
- 回滚:revert PR;SSE adapter 与旧 callback 并存期间可逐个入口回退。
- 禁止越界:PydanticAI 产品化、公开事件契约破坏性变更、持久 Job。

### AR-PY-04:PydanticAI 隔离 POC

- 目标:在 Contract 之后新增实验 Adapter,不进入默认产品路径。
  - 可选依赖策略:锁定精确版本或窄兼容范围(推荐 `pydantic-ai==2.12.x` 系列,以合入当日最新稳定版为准;见第 14 章审批点 3);缺少依赖时 Native 正常启动运行(import 惰性 + 明确错误)。
  - `PydanticAIRuntimeAdapter` 只依赖 StockPulse Contract(AR-PY-01)与 BoundToolSession(AR-PY-02)。
  - 方案 A/B Spike(第 6 章)先行,产出选择记录后再实现选定方案。
  - `RunContext` 只承载冻结 Execution 依赖;BoundToolSession -> PydanticAI Tool/Toolset 单一桥接点;typed output -> 现有报告/Agent 结果 Schema 单一映射点;event/usage/error -> StockPulse contract 单一适配点。
  - Internal-only 注入点(测试构造/内部工厂参数),**不新增用户设置与环境变量开关文档**。
  - 第一版只做**一条最小代表性路径**(推荐 Single Agent run,见第 14 章审批点 4),不同时迁移 Single/Multi/Research 与所有 API。
- 前置:AR-PY-03 合入;方案 A/B 由维护者依 Spike 证据裁决。
- 预计文件:`src/agent/runtime/pydantic_ai_adapter.py`(新,惰性 import);可选依赖清单文件(如 `requirements-pydanticai.txt`,具体形式在 PR 中与维护者确认);`tests/agent/runtime/test_pydantic_ai_adapter.py`(新,含依赖缺失路径)。
- 测试:第 10.1 节全量 + 依赖缺失/版本不兼容用例;PydanticAI 路径用 deterministic fake model 驱动。
- 验收:未安装可选依赖时全套件绿;安装后 POC 路径能以 fake model 跑通并产出 StockPulse 契约结果;不触碰任何禁区(第 5.4 节)。
- 风险:PydanticAI 版本演进破坏 Adapter——版本 pin + 升级走独立 PR。
- 回滚:revert PR 或直接删除 adapter 文件与可选依赖清单;Native 路径零依赖。
- 禁止越界:默认启用、设置页、Multi/Research 迁移、MCP/内建工具、Graph/durable execution。

### AR-PY-05:Conformance、Benchmark 与决策门禁

- 目标:以相同输入产出 Native vs PydanticAI 的可比证据,支撑"继续/停止"裁决。
  - 36 个 replay fixture 在 Native 与候选 Adapter 上运行(统一 conformance 门禁,fixture 双跑)。
  - 合同测试覆盖:factory、routing、tool scope、timeout、cancel race、malformed output、fallback。
  - 样本覆盖:A/H/US 市场 × single/chat/quick/standard/full/specialist × partial/degraded。
  - 在线可选 benchmark(相同模型、Prompt、Tool descriptor、fixture、预算与停止条件),与离线 CI 分离。
  - 指标:内容质量、schema 成功率、工具调用正确率、取消延迟、p50/p95 延迟、token/cost、provider attribution、错误率。
  - 打包证据:Source、Docker、macOS/Windows Desktop 的安装、启动、运行、取消与卸载/回滚检查。
- 前置:AR-PY-04 合入。
- 预计文件:`tests/agent/runtime/test_conformance.py`(新,参数化 runtime)、`scripts/bench_agent_runtime.py`(新,可选在线)、benchmark 报告(PR 附件/Actions artifact,不入库)。
- 测试:第 10.1 节全量 + conformance 双跑。
- 验收(硬门禁,不得放宽):
  - replay/conformance 100% 通过,或每个有意差异都有版本化决策与新 fixture。
  - 无 secret、Prompt、reasoning、完整工具结果或原始异常泄漏(secret scan 覆盖日志/SSE/异常/artifact)。
  - 无第二套 Provider/Model/Conversation/Usage 权威。
  - 无取消后 late success、重复写入或重复副作用。
  - 性能阈值不预设:先测 Native baseline,再由维护者批准可接受预算(见第 14 章审批点 5)。
  - **无收益或维护/打包成本明显高于 Native 时,结论必须允许 `Native Only`。**
- 回滚:conformance 与 benchmark 均为叠加测试资产,revert 即可。
- 禁止越界:为通过门禁而删除 fixture、放宽断言或 mock 掉真实风险层。

### AR-PY-06:有限产品化(条件阶段)

仅当 AR-PY-05 通过**且**维护者再次批准后才进入详细计划;当前只冻结边界:

- 初始状态只能是 Experimental;Native 始终默认且可独立运行。
- Runtime fallback 默认关闭;仅当尚未输出、未调用工具、未创建外部 Session、未发生副作用时,才允许策略化 fallback。
- Source/Docker 先开放;Desktop 必须完成全平台真实打包与取消验证后再开放。
- 若确需用户配置:必须进入现有配置注册表、API Schema、统一设置事务、409 语义、帮助文案与删除引用保护;**不得新增第二个模型配置入口**。
- 回滚:关闭注入点 + 卸载可选依赖即回到 Native Only;文档与配置注册表条目随 PR revert。

## 8. 每阶段文件影响矩阵

"新"= 预计新增;"改"= 预计修改;均为计划,非当前事实。

| 文件/区域 | 00 | 01 | 02 | 03 | 04 | 05 | 06 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `docs/architecture/ADR-001-agent-runtime.md` | 新 | - | - | - | - | 改(结论) | 改 |
| `docs/stockpulse-*`(治理文档) | 新/迁入 | - | - | - | - | - | 改 |
| `src/agent/runtime/contract.py` 等 Contract | - | 新 | - | 改 | - | - | - |
| `src/agent/runtime/native_adapter.py` | - | 新 | 改 | 改 | - | - | - |
| `src/agent/runtime/tool_session.py` | - | - | 新 | 改 | - | - | - |
| `src/agent/runtime/events.py` / `lifecycle.py` | - | - | - | 新 | - | - | - |
| `src/agent/factory.py` | - | 改(薄) | - | - | - | - | 改 |
| `src/agent/runner.py` / `orchestrator.py` | - | - | 改(接线) | 改 | - | - | - |
| `src/agent/tool_surface.py` | - | - | 改 | 改 | - | - | - |
| `api/v1/endpoints/agent.py` | - | - | - | 改(SSE adapter) | - | - | 改 |
| `src/agent/runtime/pydantic_ai_adapter.py` | - | - | - | - | 新 | 改 | 改 |
| 可选依赖清单(形式待定) | - | - | - | - | 新 | 改 | 改 |
| `tests/agent/runtime/` | - | 新 | 增 | 增 | 增 | 增 | 增 |
| `tests/fixtures/agent_runtime/` | - | 只读 | 只读 | 只读 | 只读 | 只读(或版本化新增) | 只读 |
| `scripts/bench_agent_runtime.py` | - | - | - | - | - | 新 | - |
| Web/Desktop/Bot/数据库 | - | - | - | - | - | - | 视批准 |

不变式:`tests/fixtures/agent_runtime/` 全程只读;删除或放宽即违反门禁(第 7 章 AR-PY-05)。

## 9. PR 拆分、依赖关系与可并行边界

### 9.1 推荐 PR 序列

| PR | 阶段 | 主题 | 允许范围 | 明确禁止 |
| --- | --- | --- | --- | --- |
| PR-AR0 | AR-PY-00 | ADR/文档收敛 | ADR、治理文档、Tracker、本计划状态位 | 生产代码、依赖 |
| PR-AR1 | AR-PY-01 | Runtime Contract + Native Adapter | vendor-neutral contract、Native parity、tests | PydanticAI、API/UI 改造 |
| PR-AR2 | AR-PY-02 | BoundToolSession | 工具边界、权限、审计、tests | 外部 Runtime、用户配置 |
| PR-AR3 | AR-PY-03 | Lifecycle/cancel/events | 状态机、取消、late-write fence、SSE adapter、tests | PydanticAI 产品化 |
| PR-AR4 | AR-PY-04 前段 | PydanticAI model integration Spike | 隔离实验分支、Spike 测试报告(artifact) | 默认启用、设置页 |
| PR-AR5 | AR-PY-04 后段 | PydanticAI Adapter POC | 最小路径 Adapter、可选依赖、conformance 接入 | Multi/Research 全量迁移 |
| PR-AR6 | AR-PY-05/06 | Packaging/benchmark decision | 可选依赖策略、Docker/Desktop 证据、ADR 更新 | 未经批准公开 |

每个 PR:单一语义目标;可独立回滚;先测试后扩大接入面;不以代码量为完成证据;不通过删 fixture、放宽断言或 mock 真实风险层过 CI。

### 9.2 依赖图

```text
AR-PY-00 ADR Accepted
  -> AR-PY-01 Runtime Contract + Native parity
      -> AR-PY-02 BoundToolSession
          -> AR-PY-03 Lifecycle/cancel/events
              -> AR-PY-04 PydanticAI isolated POC(PR-AR4 Spike -> PR-AR5 POC)
                  -> AR-PY-05 Conformance/benchmark
                      -> [HITL: Native Only | Continue Experimental]
                          -> AR-PY-06 Conditional productization
```

### 9.3 可并行边界

- 可并行:AR-PY-00 的治理文档撰写与 AR-PY-01 的 Contract 草案设计(仅设计,不合入);AR-PY-04 的方案 A/B Spike 与 AR-PY-05 的 benchmark 脚手架设计;外部资料核对随时可并行。
- 必须串行:PR-AR1 -> PR-AR2 -> PR-AR3 -> PR-AR5(共享 `src/agent/runtime/`、`runner.py`、`orchestrator.py`、`tool_surface.py` 核心文件)。**PydanticAI POC 不得与 Runtime Contract、BoundToolSession 或取消语义并行抢占同一核心文件。**
- 门禁串行:每个阶段合入前,上一阶段 PR 必须已合入且 replay 套件绿。

## 10. 测试与验证计划

### 10.1 每个编码阶段的最低命令集(当前真实存在的路径)

```bash
python -m pytest tests/agent/test_agent_runtime_compatibility.py -q
python -m pytest tests/test_agent_executor.py tests/test_multi_agent.py -q
python -m pytest tests/test_agent_tool_surface.py -q
python -m pytest tests/test_agent_chat_api.py tests/test_agent_stream_events.py tests/test_agent_sse_cleanup.py -q
python -m pytest -m "not network"
./scripts/ci_gate.sh
python scripts/check_ai_assets.py
git diff --check
```

`tests/agent/runtime/` 目录当前不存在;自 AR-PY-01 实际创建后,各阶段命令集追加 `python -m pytest tests/agent/runtime -q`。在该目录存在之前,不得把它写成可执行事实。

### 10.2 测试设计强制要求

- Deterministic fake model/tool:关键路径一律确定性替身,禁止用 sleep 构造关键竞态。
- 竞态用 `threading.Barrier`/`Event`/受控 Future 覆盖 timeout/cancel/late-write(取消发出与工具完成的先后由同步原语精确编排)。
- 可选依赖缺失与版本不兼容测试:未装 `pydantic-ai` 时 import 路径、工厂路径、错误信息均有断言。
- 静态/契约守卫:PydanticAI 代码路径不得 import `system_config_service`、`provider_catalog` 或直接读取 Connection 配置(防止 Provider Catalog/task routing 被复制)。
- Secret scan:日志、SSE 输出、异常与 benchmark artifact 均过脱敏断言(复用 `execution.py:354-375` 语义)。
- Docker/Desktop 未验证时在 PR 中明确列为风险,不得写成通过。
- 真实 Provider/network 测试进入 `-m network` 与 `network-smoke` 观测链路,不进入阻断门禁。

### 10.3 docs-only 阶段(含本文档)的验证命令

```bash
rg -n "PydanticAI|AR-PY-|Runtime Contract|BoundToolSession" docs/architecture/pydanticai-runtime-development-plan.md
rg -n "b8ac3a0a|origin/main|baseline" docs/architecture/pydanticai-runtime-development-plan.md
rg -n '[ \t]+$' docs/architecture/pydanticai-runtime-development-plan.md
awk '/^```/{n++} END{print n; exit(n%2)}' docs/architecture/pydanticai-runtime-development-plan.md
git diff --check
git status --short
```

### 10.4 Conformance / Benchmark / 打包 / 安全验证矩阵

| 验证面 | 载体 | 阶段 | 阻断性 |
| --- | --- | --- | --- |
| Replay 等价(36 fixture 双跑) | `tests/agent/runtime/test_conformance.py`(预计) | 01 起持续,05 双跑 | 阻断 |
| 合同测试(factory/routing/scope/timeout/cancel race/malformed/fallback) | contract fixture + 新增用例 | 02-05 | 阻断 |
| 取消/late-write fence | Barrier/Event 竞态用例 | 03 起 | 阻断 |
| 可选依赖缺失/版本不兼容 | 依赖开关用例 | 04 起 | 阻断 |
| Secret scan | 日志/SSE/异常/artifact 断言 | 全程 | 阻断 |
| 在线 benchmark(质量/延迟/成本) | `scripts/bench_agent_runtime.py`(预计,可选) | 05 | 观测(结论供裁决) |
| Docker 构建与导入 smoke | 现有 `docker-build` job | 全程 | 阻断(既有) |
| Desktop 冻结(macOS/Windows)安装/启动/取消/卸载 | 手工 + Release 工作流证据 | 05-06 | 06 开放 Desktop 前阻断 |

## 11. 配置、API、数据库、Web、Desktop 与 Bot 兼容性说明

- 配置:AR-PY-00~05 不新增任何配置字段与 `.env` 语义;`AGENT_ARCH` 语义不变(仍是业务 Architecture 选择)。AR-PY-06 若获批新增配置,必须走现有配置注册表、API Schema、统一设置事务、409 语义、帮助文案与删除引用保护,并同步 `.env.example` 与文档(遵循 `AGENTS.md`)。
- API:公开端点、请求/响应 Schema、SSE 事件(9 种,additive)全程不变;AR-PY-03 的 SSE compatibility adapter 只改内部实现,`tests/test_agent_chat_api.py`/`test_agent_stream_events.py`/`test_agent_sse_cleanup.py` 零修改通过是硬验收。
- 数据库:全程无迁移、无新表;Conversation/Provider trace/Usage 持久化路径不变(`conversation.py:26-30`、`executor.py:722-803`、`runner.py:458-459`)。
- Web:`apps/dsa-web` 全程零改动;停止按钮行为的真实化(后端真取消)对 Web 是透明增强,不改前端契约。
- Desktop:AR-PY-04 起可选依赖不得进入默认打包清单;PyInstaller hidden imports 与体积影响在 AR-PY-05 出证据;Desktop 开放是 AR-PY-06 的显式审批项。
- Bot:入口经由同一 factory/Contract,行为随 Native 保持;POC 路径不覆盖 Bot 场景(明确记为未验证面)。

## 12. 风险登记、停止条件与回滚策略

Owner 角色:RTL = Runtime Tech Lead(实施 Agent),MNT = Maintainer。

| # | 风险 | Owner | 触发信号 | 缓解 | 验证 | 停止条件 |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | PydanticAI 版本快速演进,public/private API 边界移动 | RTL | 升级后测试红/弃用告警 | 精确 pin;升级走独立 PR;只依赖公开契约 | 依赖不兼容测试 | 一个小版本内两次破坏性变更且无迁移路径 -> Native Only |
| R2 | LiteLLM 被双重包装,fallback/usage/trace 重复 | RTL | usage 双计;trace 出现双 provider 记录 | fallback 只由 `models_to_try` 驱动;禁用 PydanticAI FallbackModel/retry | contract fixture(fallback/modelref)双跑 | 无法关闭内部重试/回退 -> 方案淘汰 |
| R3 | Pydantic structured output 与现有宽松 JSON repair/degraded fallback 语义差异 | RTL | conformance 差异集中在 malformed/partial 样本 | typed output 失败时映射回现有降级语义,不提前收紧 | malformed/partial fixture | 差异不可映射且 ADR 不接受 -> Native Only |
| R4 | PydanticAI tool schema 与 ToolDefinition 表达能力不一致 | RTL | 工具参数/描述在桥接中丢失 | BoundToolSession 中立描述层;丢失字段显式报错 | toolscope fixture + schema diff 用例 | 关键金融工具无法无损表达 -> 方案淘汰 |
| R5 | PydanticAI message history 与业务 Conversation 重复 | RTL | 出现第二份会话持久化 | history 仅作运行态,由宿主注入/丢弃 | 静态守卫 + DB 写入断言 | 无法阻止其持久化 -> Native Only |
| R6 | cooperative cancellation 无法中断底层 SDK/线程 | RTL | 取消后模型请求仍在计费/占线程 | deadline + fence 兜底;取消延迟入 benchmark 指标 | cancel race 竞态用例 | 取消延迟超出维护者预算且无解 -> Native Only |
| R7 | 并行工具取消后的迟到结果、副作用与线程泄漏 | RTL | fence 审计出现 late-write;线程数攀升 | late-write fence(AR-PY-03);会话级并行预算 | Barrier 竞态用例 + 线程数断言 | 副作用不可阻断 -> 停止 POC |
| R8 | 依赖体积、PyInstaller hidden imports、多平台冻结与升级风险 | RTL | Desktop 构建失败/体积激增 | 可选依赖不进默认打包;AR-PY-05 出打包证据 | Docker/Desktop 打包检查 | Desktop 无法冻结且无隔离方案 -> Desktop 不开放 |
| R9 | 两套错误/事件/usage/配置来源漂移 | RTL | 同一失败在两 Runtime 呈现不同错误类别 | 单一适配点 + 稳定错误分类(AR-PY-03) | conformance 错误映射断言 | 分类无法收敛 -> Native Only |
| R10 | Multi Agent 双重编排与不可预测 token 成本 | MNT | POC 越界触碰 Multi 拓扑;token 成本异常 | 第 5.4 节禁区;POC 限单一路径 | PR 审查 + usage 对比 | 出现双编排设计 -> 关闭重做 |
| R11 | 外部 telemetry/tracing/durable execution 数据泄漏 | MNT | 依赖树出现外发 SDK;网络出站异常 | 不启用 Logfire/durable extras;secret scan | 依赖树 diff + 出站审计 | 无法禁用外发 -> 方案淘汰 |

全局停止条件(任一满足即停,保持 Native Only,写入 ADR 结论):

1. AR-PY-05 硬门禁任一项不可修复地失败。
2. 维护者判定收益不足或维护/打包成本明显高于 Native。
3. 连续两个阶段出现契约漂移、补丁堆叠或验证证据失真(对应 `AGENTS.md` §8.1 低质量 PR 判据)。

全局回滚策略:每个 PR 独立可 revert;PydanticAI 资产(adapter 文件 + 可选依赖清单 + 注入点)整体删除后,Contract/BoundToolSession/生命周期改造仍独立成立并继续服务 Native——**回滚 PydanticAI 不回滚架构收益**。

## 13. Definition of Ready / Definition of Done

### DoR(任一编码阶段启动前)

- ADR-001 状态为 `Accepted`,且两个 degraded 行为有版本化裁决。
- 本计划状态为 `Approved`(已于 2026-07-17 由维护者批准)。
- 上一阶段 PR 已合入,replay 套件在最新主线绿。
- 阶段任务有明确 Issue(英文标题)与验收清单。

### DoD(每个阶段/PR)

- 第 10.1 节命令全绿;replay fixture 零删除、零放宽。
- 交付说明包含:改了什么 / 为什么 / 验证情况 / 未验证项 / 风险点 / 回滚方式(`AGENTS.md` §9)。
- PR body 与实际 diff、验证结果、兼容风险一致;无禁区触碰。
- 文档与 `docs/CHANGELOG.md`(如涉及用户可见变化)同步;本计划各阶段默认不产生用户可见变化。

## 14. 人工审批点(每项含推荐默认值)

| # | 审批点 | 推荐默认值 | 备选 | 证据 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 1 | AR-01 ADR 是否 Accepted | 接受"Native 永久默认 + Contract + 实验 Adapter"架构 | 拒绝(维持现状,计划终止) | 第 3 章代码事实;replay 安全网就绪 | 决定后续全部阶段是否存在 |
| 2 | 两个 degraded `success=true` 行为 | **保留为冻结兼容契约**,在结果元数据中已有 partial 标记与 error 字段,消费方可辨识;未来若修正走独立 versioned fixture | 判为缺陷,立即修正(破坏现有客户端对 success 的解读,需要兼容层) | `orchestrator.py:216`/`:657`;partial 标记 `:167-172`/`:207-213` | 影响 conformance 基线与所有客户端 |
| 3 | PydanticAI 版本策略与方案 A/B | 精确 pin(以合入日最新稳定版,2026-07-17 观测为 2.12.0);A/B 由 Spike 证据决定,**倾向先验证方案 A**(官方维护面更小),LiteLLM Model 文档缺失(Evidence gap)时 B 为回退 | 宽版本范围(升级风险大);无证据直接选 B(违反本计划) | 第 6 章选择标准;第 16 章 Evidence gap | 决定维护成本与升级路径 |
| 4 | POC 首个路径:Single run 还是 Chat | **Single Agent run**(无会话/SSE 交互面,fixture `single_run` 现成,验证面最小) | Single chat(多一层 Conversation 注入与流式面) | manifest 中 single_run fixture;chat 依赖 conversation 注入 | 决定 PR-AR5 范围 |
| 5 | Benchmark 性能/成本/质量容忍预算 | 先跑 Native baseline 报告,维护者据此设定预算;计划不预写阈值 | 直接沿用行业经验值(无本地依据,拒绝) | AR-PY-05 baseline 报告 | 决定 AR-PY-05 通过线 |
| 6 | POC 后 Native Only 还是 Experimental 产品化 | 默认 **Native Only**,除非 AR-PY-05 全部硬门禁通过且展示明确收益(维护成本下降或能力增量) | Experimental 产品化(进入 AR-PY-06) | conformance + benchmark + 打包证据 | 决定 AR-PY-06 是否展开 |
| 7 | 是否/何时向用户暴露 Runtime 选择 | **不暴露**;最多 Internal-only 注入点;若未来暴露必须走配置注册表全链路 | 暴露为高级设置(增加支持面与误用风险) | 第 11 章配置兼容性约束 | 决定支持面与文档义务 |

## 15. 推荐 Issue 标题、PR 标题与实施顺序

GitHub 协作内容按 `AGENTS.md` 一律英文,标题格式 `<type>: <change summary>`,不带工具/agent 前缀。

| 顺序 | Issue 标题(建议) | PR 标题(建议) |
| --- | --- | --- |
| 0 | `Converge agent runtime ADR and governance docs` | `docs: add agent runtime ADR and governance baseline` |
| 1 | `Introduce vendor-neutral agent runtime contract with native adapter` | `refactor: introduce agent runtime contract with native adapter parity` |
| 2 | `Enforce bound tool sessions for agent tool access` | `feat: enforce bound tool session for agent tool access` |
| 3 | `Close agent execution lifecycle and cancellation gaps` | `feat: add agent execution lifecycle events and cooperative cancellation` |
| 4 | `Spike: PydanticAI model integration options A/B` | `test: add isolated PydanticAI model integration spike` |
| 5 | `Add experimental PydanticAI runtime adapter POC` | `feat: add experimental PydanticAI runtime adapter behind internal seam` |
| 6 | `Decide PydanticAI productization from conformance and packaging evidence` | `docs: record PydanticAI runtime benchmark results and decision` |

本文档自身的合入建议:`docs: add PydanticAI runtime development plan`(docs-only,`Docs only, tests not run`,但已执行第 10.3 节文档验证)。

实施顺序即依赖图(第 9.2 节);每步之间设 HITL 审批(第 14 章)。

## 16. Evidence gaps 与需要 Spike 回答的问题

外部资料访问日期:2026-07-17;来源:`ai.pydantic.dev`(当日重定向至 `pydantic.dev/docs/ai`)与 PyPI `pydantic-ai` 项目页。合入 AR-PY-00 时必须重新核对并更新本章。

### 16.1 官方已确认(访问当日)

- 版本:2.12.0(2026-07-17 发布);Python >= 3.10;MIT 许可;存在 `pydantic-ai-slim` 变体与大量可选 extras(含 dbos/temporal/prefect/xai 等)。
- Agent 契约:`Agent(model, deps_type, output_type, instructions, ...)`;`run`/`run_sync`/`run_stream`;`RunContext[Deps]` 依赖注入;`ctx.usage`/`UsageLimits`。
- Tool 契约:`@agent.tool`/`@agent.tool_plain`;`FunctionToolset`/`AbstractToolset`(`get_tools`/`call_tool`);FilteredToolset 等组合器。
- Model 层:`Model` 抽象公开可子类化(方案 B 的前提成立);`FallbackModel`/`ConcurrencyLimitedModel` 存在(本计划禁用其 fallback)。
- Streaming:`StreamedRunResult`,`stream_text`/`stream_output`(partial validation),事件如 `PartStartEvent`/`FinalResultEvent`;`result.cancel()` 可中断流式生成并标记 interrupted。
- Message history:`ModelMessage` 列表可由宿主序列化存储与注入(满足"运行态不落库"要求)。
- Multi-agent:官方分层为 delegation -> programmatic hand-off -> graph -> deep agents;全部**不进入**第一期。

### 16.2 Evidence gaps(全部转为 Spike/验收项)

| # | Gap | 转化 |
| --- | --- | --- |
| G1 | LiteLLM Model 官方文档页访问当日 404,extras 中未见 litellm 专项说明 | 方案 A Spike 第一项:确认 LiteLLM Model 的存在形态、配置面与版本要求;若官方无承诺,方案 A 降级为候选、方案 B 升为主案 |
| G2 | 取消语义:`cancel()` 之外,能否中止进行中的模型 HTTP 请求与并行工具无官方承诺 | AR-PY-04 Spike 实测取消延迟与线程行为;结果计入 R6 风险与 benchmark 指标 |
| G3 | durable execution 文档当日 404;dbos/temporal/prefect extras 语义未核 | 明确列为第一期禁区,不做 Spike;仅在 AR-PY-06 之后按需重评 |
| G4 | usage 数据的序列化/持久化格式未明确 | AR-PY-04 在适配点断言 usage 字段完备性,映射到统一 UsageRecorder |
| G5 | 依赖树体积、httpx/pydantic 版本下限、PyInstaller 冻结支持无官方说明 | AR-PY-05 打包证据项:真实构建 Docker 与 macOS/Windows Desktop 并记录体积/hidden imports |
| G6 | 官方站点信息架构迁移中(多处 301/302/404),链接稳定性差 | AR-PY-00 重新核对全部引用并固化访问日期与快照式引用 |

### 16.3 需要 Spike 回答的问题清单

1. 方案 A 是否能在不读取用户配置的前提下,完整复用 StockPulse 已解析的 wire model/timeout/thinking payload?
2. 方案 B 的自定义 `Model` 需要实现的最小接口面是什么?其在 2.x 内的稳定性?
3. `reasoning_content`/`provider_blocks`(含 Claude thinking roundtrip,`provider_trace.py:28-46` 的 `must_roundtrip`)能否经 PydanticAI 消息模型无损往返?
4. 取消发出后,进行中的模型请求与并行工具的真实终止时点与线程归还行为?
5. malformed output 场景下,typed output 失败路径能否映射回现有 degraded 合成语义而不提前 fail?
6. 未安装可选依赖时的 import 面与错误信息是否可控?

---

本计划曾于 2026-07-17 获批，并已完成 POC 与证据收集。RF-07 后续裁决为
`Native Only`，2026-07-19 已删除实验 Adapter、可选依赖、注入点和专用 CI。
任何未来框架评估必须新建 ADR，并从当前 Native Contract 重新接入。
