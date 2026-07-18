# StockPulse Agent Runtime 合并后问题修复计划

## 1. 文档状态、基线与用途

- 状态：`Accepted`（维护者已批准 RF-00～RF-07 顺序；RF-00～RF-05 已合入主线，RF-06～RF-07 待执行）
- 版本：v0.1
- 日期：2026-07-18
- 审计基线：`main@309268760699cd9a833e702b6b8b0b1a8545376a`
- 合并来源：[PR #18](https://github.com/SiinXu/stock-pulse-ai/pull/18)
- 上位架构决策：`docs/architecture/ADR-001-agent-runtime.md`（`Accepted`）
- 原始开发计划：`docs/architecture/pydanticai-runtime-development-plan.md`（`Approved`）
- 用途：记录 PR #18 合入后的真实实现状态，并把未达到原计划验收条件的部分拆成可独立验证、独立回滚的小 PR。

本计划不撤销已批准的目标架构和 degraded 行为裁决，也不把当前 Native 路径判定为不可用。它只修复实现与原计划之间的差距：运行中控制柄、统一工具权威、完整取消与 late-write fence、真实 PydanticAI 模型桥、可选依赖 CI 和 conformance 证据。

## 2. 目标与非目标

### 2.1 目标

```text
StockPulse Native Architecture
  -> vendor-neutral Runtime Contract
      -> Native Runtime Adapter（永久默认）
      -> PydanticAI Runtime Adapter（实验性、可整体删除）
```

修复完成后必须满足：

1. 调用方能在执行运行期间持有 `ExecutionHandle`，查询状态、消费事件、请求取消并等待终态。
2. Native 与任何实验 Runtime 共享唯一的 `BoundToolSession` 工具安全边界。
3. Single、Multi、Research 和 Chat/SSE 使用一致的生命周期、终态分类、取消优先级和持久化 fence。
4. PydanticAI Single RUN 的真实模型桥能无损传递 Prompt、工具 schema、工具历史、timeout、usage、provider attribution 和错误。
5. 未安装与已安装 PydanticAI 两种环境均由 CI 显式验证，安装态不得以 skip 代替 pass。
6. Conformance 只对已批准能力矩阵声明等价；未支持能力必须明确拒绝，不得伪装降级成功。
7. 任一阶段无法满足硬门禁时，允许停止在 `Native Only`，且不回滚已经证明对 Native 有价值的独立架构改进。

### 2.2 非目标

- 不把 StockPulse 整体迁移到 PydanticAI。
- 不让 PydanticAI 接管 Single/Multi/Research 业务拓扑、Provider Catalog、Connection、任务模型路由、Prompt/Skill、报告、Conversation、Usage 或 Provider trace 权威。
- 不在本轮增加 Runtime 用户设置、环境变量开关、公开 API、数据库表或持久 Agent Job。
- 不在 PydanticAI Single RUN 合格前扩展 CHAT、Multi、Research、MCP、Graph 或 durable execution。
- 不在 Runtime 修复 PR 中修改许可证；当前双许可证状态另走治理审查。
- 不删除、放宽或重录既有 36 个 replay fixture 来迁就实现。

## 3. 当前实现状态

| 阶段 | 当前事实 | 真实状态 |
| --- | --- | --- |
| AR-01 | 36 个 replay fixture 与 Native 兼容测试已在 PR #11 合入 | `Done` |
| AR-PY-00 | ADR、开发计划和 tracker 已合入且架构方向获批准 | `Done` |
| AR-PY-01 | Contract、状态机和 Native wrapper 已存在，但 `execute()` 结束后才返回 terminal handle；Context 输入不完整且只浅层冻结 | `Partial` |
| AR-PY-02 | `BoundToolSession` 有 allowlist、权限、预算、deadline、审计和 late-result fence；Native 仍走 legacy direct path | `Partial` |
| AR-PY-03 | typed events、UsageRecorder、部分 runner/orchestrator 取消检查点和 Chat SSE 断连取消已接入；未形成全入口统一生命周期和持久化 fence | `Partial` |
| AR-PY-04 | 可选依赖、实验 Adapter 和 PydanticAI toolset bridge 已存在；真实 StockPulse-backed 工具循环、Prompt 等价和 timeout/cancel 未完成 | `Experimental / Incomplete` |
| AR-PY-05 | 仅有 5 个简化 fake conformance tests；无 replay 支持矩阵、benchmark 和可选依赖 CI | `Not started` |
| AR-PY-06 | Native 仍默认，实验 Runtime 未向用户公开 | `Blocked` |

当前默认安装不包含 `pydantic-ai-slim`，生产代码也没有调用 `build_agent_runtime()` 或选择 `PydanticAIRuntimeAdapter`。因此 PydanticAI 缺陷目前是休眠的实验路径问题，不是默认 Native 立即故障；但在下列问题关闭前不得启用或宣传该路径。

## 4. 问题登记

| ID | 严重度 | 问题 | 代码证据 | 影响 | 修复阶段 |
| --- | --- | --- | --- | --- | --- |
| AR-RF-01 | P0 | `ExecutionHandle` 不是运行中控制柄 | `src/agent/runtime/contract.py:234-253`；Native/PydanticAI `execute()` 均同步完成后返回 | 调用方无法用 Handle 取消、等待或观察运行中状态 | RF-02 |
| AR-RF-02 | P1 | `ExecutionContext` 不是完整、深层冻结的执行快照 | `src/agent/runtime/contract.py:71-94` 只做 `MappingProxyType(dict(...))`，嵌套 dict/list 仍可变 | 路由、scope、预算等运行输入可能在执行中漂移 | RF-02 |
| AR-RF-03 | P0 | Native 与外部 Runtime 存在两套工具权威 | `src/agent/runtime/tool_session.py:6-21` 明确保留 Native direct path | permissions、scope、deadline、预算和 late-result 行为无法跨 Runtime 等价 | RF-03 |
| AR-RF-04 | P0 | StockPulse-backed PydanticAI Model 不向 LLM 发送工具 schema | `src/agent/runtime/pydantic_ai_adapter.py:126-130` 固定调用 `call_with_tools(..., [])` | 真实模型永远不会产生合法工具调用 | RF-05 |
| AR-RF-05 | P0 | ToolCall/ToolReturn 历史在模型桥中丢失 | `src/agent/runtime/pydantic_ai_adapter.py:74-100` 只转换文本 part | 即使补上传工具 schema，下一轮模型也看不到工具结果 | RF-05 |
| AR-RF-06 | P1 | PydanticAI Prompt 与金融行为未证明等价 | `src/agent/runtime/pydantic_ai_adapter.py:224-265` 直接 `Agent(...).run_sync(context.prompt)` | system/skill/context、dashboard 约束、fallback、thinking 和 provider trace 可能漂移 | RF-05 |
| AR-RF-07 | P0 | 取消、timeout 与 late-write fence 未统一 | PydanticAI `execute()` 不消费 `timeout_seconds`/cancel；Native lifecycle 主要由 `api/v1/endpoints/agent.py:478-588` 的 Chat SSE 持有 | Run/Research/工具/持久化仍可能在取消后继续完成或写入 | RF-04、RF-05 |
| AR-RF-08 | P0 | Conformance 证据只覆盖简化 fake | `tests/agent/runtime/test_conformance.py:35-119` | 无法证明 routing、fallback、toolscope、timeout、cancelrace、malformed 或 partial/degraded 等价 | RF-06 |
| AR-RF-09 | P0 | 默认 CI 静默跳过 PydanticAI 核心测试 | `.github/requirements-ci.txt` 不安装可选依赖；两个测试模块使用 `pytest.importorskip("pydantic_ai")` | `backend-gate` 绿色不代表实验 Adapter 被执行 | RF-01 |
| AR-RF-10 | P1 | PydanticAI usage 字段与存储摘要列不匹配 | Adapter 写 `input_tokens/output_tokens`；`src/storage.py:4098-4100` 读取 `prompt_tokens/completion_tokens` | 未来启用时 Usage 页面输入/输出 token 统计为 0 | RF-05 |
| AR-RF-11 | P2 | CHAT 在 Single RUN conformance 前提前进入 Adapter | `src/agent/runtime/pydantic_ai_adapter.py:190-199` 支持 RUN/CHAT | 扩大了 Conversation、SSE、trace、重试和取消验证面 | RF-00、RF-05 |
| AR-RF-12 | P2 | 治理文档与合并后事实漂移 | `docs/stockpulse-work-tracker.md` 仍写“实现完成，待合入”，并引用不存在的 Spike 报告 | 后续任务会错误判断前置阶段已完成 | RF-00 |
| AR-RF-13 | Governance | Runtime 与许可证治理耦合 | PR #18 同时包含 Runtime 00～05 和全仓许可证提交 | 运行时回滚与许可证裁决无法独立进行 | 独立治理任务 |

## 5. 修复原则与不变式

1. **Forward-fix 优先**：Native 默认路径、replay 安全网和已证明有效的生命周期资产继续保留；不因实验 Adapter 缺陷默认整体回滚 PR #18。
2. **逐 PR 串行**：每个 PR 只有一个主要语义；上一阶段合入且门禁绿色后才能开始下一核心阶段。
3. **Native 先行**：Contract、工具边界和生命周期先在 Native 完成，再修 PydanticAI。
4. **一个权威源**：模型路由、工具策略、Conversation、Usage、Provider trace、错误和持久化只能由 StockPulse 拥有。
5. **能力显式化**：Runtime 不支持某模式时返回稳定的 `unsupported_capability`，不得静默 fallback 或输出伪成功。
6. **取消不等于强杀**：底层 SDK/线程无法中断时必须标记 cooperative；仍应记录实际计费 usage，但禁止写 success message、success trace、报告或重复副作用。
7. **fixture 不动**：既有 36 fixture 全程只读；有意行为变化走独立 ADR 和版本化新增 fixture。
8. **许可证隔离**：任何 Runtime 修复 PR 不修改 `LICENSE`、`LICENSE.AGPL`、README license 说明或全仓 SPDX header。

## 6. 分阶段修复计划

### RF-00：真实状态、冻结边界与任务登记

**目标**

- 保留已批准开发计划和 ADR，不重新争论目标架构。
- 将 tracker 更新为第 3 章的真实阶段状态。
- 登记 AR-RF-01～13、负责人、依赖、停止条件和 PR 顺序。
- 将 PydanticAI 标记为 internal experimental / not operational。
- 在 RF-06 裁决前冻结 PydanticAI CHAT、Multi、Research 和产品入口扩展。

**允许范围**

- `docs/architecture/pydanticai-runtime-recovery-plan.md`
- `docs/stockpulse-work-tracker.md`
- 必要时更新 `docs/architecture/ADR-001-agent-runtime.md` 的实施状态附注，但不改变已批准决策。

**验证**

```bash
python scripts/check_ai_assets.py
rg -n "AR-RF-|RF-0|Partial|Not started|Experimental" docs/architecture/pydanticai-runtime-recovery-plan.md docs/stockpulse-work-tracker.md
rg -n '[ \t]+$' docs/architecture/pydanticai-runtime-recovery-plan.md docs/stockpulse-work-tracker.md
git diff --check
```

**退出条件**

- tracker 不再包含“待合入”等与 `main@30926876` 冲突的状态。
- 所有后续 PR 都有单一范围、验收条件和回滚方式。
- 维护者批准 RF-01～RF-07 顺序。

**回滚**

- revert docs-only PR；无运行时影响。

### RF-01：PydanticAI optional-dependency CI 矩阵

**目标**

建立两个独立、显式的 CI 环境：

```text
native-no-pydantic
pydanticai-installed
```

**实现要求**

- Native job 不安装 `requirements-pydanticai.txt`，验证默认启动、factory、API 和 Docker 导入均不依赖 PydanticAI。
- PydanticAI job 同时安装 `.github/requirements-ci.txt` 与 `requirements-pydanticai.txt`。
- cache key 纳入两个 requirements 文件。
- 安装态 job 首先强制 `import pydantic_ai` 并打印受控版本信息；缺失即失败。
- 安装态运行 `tests/agent/runtime/test_pydantic_ai_adapter.py`、`test_tool_session.py`、`test_conformance.py`。
- 安装态出现 module-level skip 必须失败；不能用 `importorskip` 隐藏安装或导入错误。
- 默认 Docker/Desktop 继续不包含实验依赖；可选扩展包验证留到 RF-06。

**预计文件**

- `.github/workflows/ci.yml`
- `.github/requirements-ci.txt`（仅在确有必要时）
- `tests/agent/runtime/` 中的依赖状态守卫

**退出条件**

- 未安装态和安装态均有独立绿色证据。
- PR 页面能明确区分“Native 正常”和“PydanticAI tests 实际执行”。

**回滚**

- revert CI PR，不影响生产代码。

### RF-02：Live Runtime Contract 与深层冻结 Context

**目标**

将当前完成结果包装器改造成运行中控制柄，同时保留现有同步入口兼容性。

**目标接口**

```text
AgentRuntime.start(context) -> ExecutionHandle
ExecutionHandle.state
ExecutionHandle.events / subscribe
ExecutionHandle.request_cancel()
ExecutionHandle.wait(timeout=None)
ExecutionHandle.result
ExecutionHandle.error
ExecutionHandle.close()
```

原 `execute(context)` 可保留为兼容 helper，但只能实现为 `start(context)` 后等待终态，不能继续作为核心生命周期协议。

**实现要求**

- 明确 worker thread / asyncio task 的创建者、终止、join/wait、close 和异常传播规则。
- Handle 在 `RUNNING` 时可返回给调用方。
- terminal first-wins 与 dropped transition 审计保持不变。
- `ExecutionContext` 深层快照化，调用方后续修改嵌套 dict/list 不影响执行。
- 将以下字段从松散 `request_context` 提升为正式、只读契约：
  - architecture / mode
  - resolved model route 与 fallback 顺序
  - allowed tools
  - principal / permission grants / stock、portfolio、account scope
  - token、tool、time budgets
  - deadline
  - Runtime capabilities
- PydanticAI 类型不得进入 Contract。

**验证**

- Contract 状态、并发 terminal、异常传播、cancel-before-start、cancel-while-running、wait timeout、close 幂等测试。
- 嵌套 mapping/list/set 调用方修改测试。
- Native Single/Multi/Research wrapper parity。
- 36 个 Native replay fixture 零修改通过。

**退出条件**

- 测试能在 worker 被 controlled Future 阻塞时拿到 `RUNNING` handle 并发出取消。
- 所有旧同步入口仍保持既有公开结果和异常语义。

**回滚**

- revert Contract PR；旧同步执行路径仍可独立运行。

### RF-03：Native 统一接入 BoundToolSession

**目标**

消除 Native direct ToolRegistry 权威，使所有 Runtime 都经过同一工具会话：

```text
Runtime
  -> BoundToolSession
      -> ToolSurface
          -> ToolRegistry handler
```

**实现要求**

- Native runner 不再直接接收可绕过会话门禁的原始工具执行权威。
- 如 replay 兼容需要 mapper，只允许一个明确迁移点，且 mapper 不得跳过 session gate。
- 补齐并冻结：schema、permissions、stock/portfolio/account scope、deadline、每次和会话总预算、结果大小、审计、idempotency/retry policy、cancel 和 late-result fence。
- 将当前表示“相对持续时间”的 `deadline_seconds` 改为无歧义名称或绝对 deadline 契约。
- terminal 时关闭 session；迟到结果只能审计，不能进入下一轮模型或持久化成功结果。
- side-effect 工具必须显式分类；无法保证幂等或取消安全时不得向实验 Runtime 暴露。

**验证**

- Native 全部工具调用序列、参数、结果和 audit parity。
- 未知工具、缺权限、scope 越界、预算耗尽、deadline、取消、结果过大全部 fail-closed。
- Barrier/Event 驱动的单工具和并行工具 late-result 测试。
- 36 个 Native replay fixture 零修改通过。

**退出条件**

- 生产运行路径中不存在绕过 `BoundToolSession` 的第二套工具分发权威。
- Native 性能退化有测量结果并获接受，不以主观判断放行。

**回滚**

- revert 本 PR；Contract 保留，Native 临时回到旧 ToolSurface 路径。

### RF-04：统一生命周期、取消与持久化 fence

**目标**

让 Single、Multi、Research、Chat API/SSE 使用同一个 `ExecutionLifecycle`，并关闭终态后的用户可见写入。

**优先级**

```text
cancel_requested / client disconnect
  > deadline / timeout
      > degraded success
          > normal success
```

实际 provider usage 是计费与审计事实：即使取消后 LLM 才返回，只要 usage 有效仍应记录；但它不得驱动 success、assistant message、provider trace success 或报告写入。

**实现要求**

- `ExecutionLifecycle` 由所有入口持有，不再只由 Chat SSE 单独创建。
- cancellation checkpoint 覆盖：LLM 前后、串行工具、并行工具、stage boundary、最终合成和持久化提交前。
- 为 Conversation assistant、Provider trace、报告和其他用户可见副作用增加 execution/attempt write fence。
- 保留 Chat 用户已发送消息；取消不写“失败”助手占位，也不写 partial success。
- typed internal event 只允许经单一 SSE compatibility mapper 对外降级。
- terminal 后 event、tool result、assistant/result write 全部丢弃并审计。
- 明确 cooperative cancellation 不能保证已经开始的 SDK 请求停止计费。
- SSE 的 300 秒 transport timeout 与 Runtime deadline 使用一致、可解释的映射。

**验证**

- cancel 与 success、timeout、tool completion、DB write 的竞争测试。
- 取消后无 assistant success、provider trace success、报告或 late SSE event。
- 有效 late usage 仍只记录一次。
- 无 sleep 驱动的关键竞态断言。
- `test_agent_chat_api.py`、`test_agent_stream_events.py`、`test_agent_sse_cleanup.py` 与 36 replay fixture 零修改通过。

**退出条件**

- 所有入口使用同一终态分类和 fence。
- 无法取消的 side effect 有明确禁止暴露或幂等补偿策略。

**回滚**

- revert lifecycle PR；RF-02 Contract 和 RF-03 工具边界仍独立保留。

### RF-05：PydanticAI Single RUN 真实模型桥

**目标**

只完成一条可证明的 Single RUN 路径。现有 PydanticAI CHAT 在本阶段改为显式 unsupported；CHAT 只有在 RF-06 后另行审批才能恢复。

**实现要求**

1. 从 PydanticAI `model_request_parameters` 读取当前请求的工具定义并无损映射为 `LLMToolAdapter.call_with_tools()` schema，禁止固定空数组。
2. 将 StockPulse `LLMResponse.tool_calls` 映射为 PydanticAI `ToolCallPart`。
3. 将 PydanticAI ToolCall、ToolReturn、RetryPrompt、assistant text 正确映射回 StockPulse messages；下一轮模型必须看到工具结果。
4. reasoning content、provider blocks、provider/model attribution 和 must-roundtrip trace 不得静默丢失；无法无损表达时 fail closed 并触发停止条件。
5. 复用 StockPulse 已解析的 system prompt、Skill prompt、股票/市场 context、response/dashboard 约束、模型 route、fallback 和 thinking payload，不在 Adapter 内建立第二套业务规则。
6. 将 execution deadline/remaining timeout 传入模型调用和工具 session。
7. 所有工具仍经 RF-03 的 `BoundToolSession`。
8. usage 映射到 StockPulse 权威字段：`input_tokens -> prompt_tokens`、`output_tokens -> completion_tokens`，并保留 total/provider 原始遥测。
9. 错误映射经 StockPulse sanitizer 和稳定错误分类，不泄漏 Prompt、密钥、provider payload 或原始异常。

**关键测试**

测试必须穿过真实模型桥，而不是只让 PydanticAI fake Model 直接生成 ToolCall：

```text
PydanticAI Agent
  -> StockPulse-backed fake LLMToolAdapter
      -> 断言收到真实工具 schema / prompt / timeout
      -> 返回 StockPulse tool call
  -> BoundToolSession 执行
  -> ToolReturn 回到下一轮 StockPulse-backed model request
  -> 最终 Decision Dashboard
```

还需覆盖无工具文本、工具拒绝、malformed output、fallback、provider error、cancel、timeout、usage 和 reasoning/provider block round-trip。

**退出条件**

- A/HK/US Single RUN 支持子集 conformance 全绿。
- 未安装 PydanticAI 时 Native 全量仍绿。
- Adapter 没有第二套模型配置、Conversation、Usage 或工具权威。
- 真实工具闭环、Prompt snapshot 或 provider trace 任一无法收敛时，停止 POC 并选择 `Native Only`。

**回滚**

- 删除/revert PydanticAI adapter、toolset、可选依赖和内部注入点；RF-02～04 的 Native 架构收益保留。

### RF-06：Conformance、benchmark 与打包证据

**目标**

以明确能力矩阵验证 Native 与 PydanticAI，而不是为了“36 双跑”扩大 POC 范围。

**第一阶段支持矩阵**

- 双跑：A/HK/US `single_run` normal/partial 及与 Single RUN 相关的 modelref、fallback、toolscope、timeout、cancelrace、malformed fixtures。
- 明确拒绝：CHAT、Multi、Research 及未批准模式必须返回稳定 `unsupported_capability`。
- 不得为了满足 fixture 数量提前实现 CHAT/Multi/Research。

只有维护者批准扩大能力矩阵后，才增加其他 fixture 的双跑。最终报告必须同时列出“等价通过”“明确不支持”“有意差异”三类，不得把 unsupported 计作 pass。

**验证指标**

- schema/报告成功率
- 工具 schema、调用顺序、参数和结果正确率
- provider/model/fallback attribution
- usage 与成本
- error classification
- cancel latency、late write 和重复副作用
- p50/p95 latency
- 依赖树、Docker、macOS/Windows Desktop 安装/启动/卸载与体积
- secret、Prompt、reasoning、完整工具结果和原始异常泄漏扫描

**CI/测试要求**

- 同 fixture、同 Prompt snapshot、同 tool descriptor、同预算和停止条件。
- 离线 conformance 阻断；真实 provider benchmark 独立为 network/Actions artifact，不读取开发者 ambient credentials。
- 每个有意差异必须先有 ADR 决策和版本化新增 fixture。

**退出条件**

- 已批准支持矩阵 100% 通过。
- 无第二套权威、late success、重复 usage/trace 或打包阻断。
- 形成 `Native Only` 或 `Continue Experimental` 决策报告。

**回滚**

- conformance/benchmark 为叠加测试资产，可独立 revert；不影响 Native 生产代码。

### RF-07：产品化裁决

默认决策是 `Native Only`。只有 RF-06 全部硬门禁通过且有明确收益时，维护者才可批准 `Continue Experimental`。

即使继续 Experimental：

- Native 永久默认并可零 PydanticAI 依赖运行。
- Runtime fallback 默认关闭。
- 不立即新增用户设置；公开入口另立配置/API/Web/Desktop 全链路计划。
- PydanticAI 资产必须继续支持整体删除。
- Source/Docker 可先于 Desktop；Desktop 需独立完成多平台真实打包证据。

## 7. PR 序列与依赖

| 顺序 | 阶段 | 建议英文 PR 标题 | 主要范围 | 明确禁止 |
| --- | --- | --- | --- | --- |
| 0 | RF-00 | `docs: record agent runtime recovery baseline` | recovery plan、tracker、实施状态 | 生产代码、CI、依赖、许可证 |
| 1 | RF-01 | `ci: add the optional PydanticAI runtime test matrix` | CI、依赖安装态守卫 | Runtime 行为修复 |
| 2 | RF-02 | `refactor: make agent execution handles live and awaitable` | Contract、Native wrapper、契约测试 | PydanticAI、工具接线、API 改造 |
| 3 | RF-03 | `refactor: route native agent tools through bound sessions` | Tool session、runner/tool surface 接线 | PydanticAI 功能扩展、UI |
| 4 | RF-04 | `fix: unify agent cancellation and late-write fencing` | lifecycle、events、入口、持久化 fence | PydanticAI 产品化 |
| 5 | RF-05 | `fix: complete the PydanticAI single-run model bridge` | Single RUN Adapter、tool/model bridge、usage | CHAT、Multi、Research、设置页 |
| 6 | RF-06 | `test: enforce cross-runtime conformance and packaging gates` | fixtures 支持矩阵、benchmark、packaging | 放宽 fixture、扩大产品入口 |
| 7 | RF-07 | `docs: record the PydanticAI runtime adoption decision` | 决策报告、ADR/tracker 状态 | 自动产品化 |

依赖关系：

```text
RF-00
  -> RF-01
      -> RF-02
          -> RF-03
              -> RF-04
                  -> RF-05
                      -> RF-06
                          -> RF-07
```

RF-01 可以在 RF-00 获批后立即执行；RF-02～05 共享核心文件，必须严格串行。RF-06 的 benchmark 脚手架可以提前设计，但不得合入或宣称通过，直到 RF-05 完成。

## 8. 验证门禁

### 8.1 每个编码阶段最低命令集

```bash
python -m pytest tests/test_agent_runtime_compatibility.py -q
python -m pytest tests/agent/runtime -q
python -m pytest tests/test_agent_executor.py tests/test_multi_agent.py -q
python -m pytest tests/test_agent_tool_surface.py -q
python -m pytest tests/test_agent_chat_api.py tests/test_agent_stream_events.py tests/test_agent_sse_cleanup.py -q
python -m pytest -m "not network"
./scripts/ci_gate.sh
python scripts/check_ai_assets.py
git diff --check
```

### 8.2 PydanticAI 阶段附加门禁

```text
环境 A：不安装 requirements-pydanticai.txt
  -> Native 全套 + import isolation

环境 B：安装 requirements-pydanticai.txt
  -> 强制 import/version assertion
  -> Adapter/tool bridge/conformance tests
  -> 禁止 skip
```

### 8.3 竞态与安全要求

- timeout/cancel/late-write 使用 Barrier、Event 或 controlled Future，不用 sleep 决定先后。
- 测试不得 mock 掉被审查的真实风险层；模型桥测试必须进入 StockPulse-backed model request。
- 日志、异常、SSE、benchmark artifact 经过脱敏与 secret scan。
- PR body 必须区分“已验证”“未验证”“明确不支持”，不能以 CI 绿色替代语义证据。

## 9. 风险与停止条件

| 风险 | 触发信号 | 缓解 | 停止条件 |
| --- | --- | --- | --- |
| Contract 改造破坏 Native 行为 | replay 输出、工具序列或错误语义变化 | 保留同步 compatibility helper；逐入口 parity | 无法在单一兼容层保持 replay -> 停止并重设 Contract |
| Native 统一工具边界产生双重执行或性能回退 | 工具调用重复、audit 重复、耗时显著上升 | 单一 migration mapper；基准对比 | 无法消除第二权威或关键工具无法表达 -> 停止 RF-03 |
| cooperative cancel 无法阻止副作用 | terminal 后仍有不可幂等外部写入 | 工具分类、幂等 key、禁止暴露高风险工具 | 副作用不可 fence/补偿 -> PydanticAI 不得使用该工具 |
| PydanticAI Model API 升级不稳定 | pin 升级即破坏 tool/message round-trip | 精确 pin、只用公开 API、独立升级 PR | 两次连续小版本破坏且无薄适配方案 -> Native Only |
| Prompt/trace 无法无损映射 | reasoning/provider blocks 或 must-roundtrip 丢失 | StockPulse 继续持有 provider trace；fail closed | 关键 provider 无法 round-trip -> Native Only |
| Conformance 为通过而扩大范围 | 提前加入 CHAT/Multi/Research 或弱化 fixture | 能力矩阵 + unsupported contract | 再次出现同类证据失真 -> 关闭重做 |
| 打包成本高于收益 | Desktop 构建失败、体积/启动时间明显恶化 | 可选扩展包、Source/Docker 优先 | 维护者判定收益不足 -> Native Only |

全局停止条件：

1. 任一核心安全契约只能通过第二套 fallback、静默降级或绕过真实风险层实现。
2. Native replay 无法保持且没有获批的版本化行为变更。
3. PydanticAI 真实工具闭环、Prompt snapshot、provider trace 或取消 fence 无法收敛。
4. optional dependency、Docker/Desktop 或升级成本明显高于可证明收益。
5. 连续两个阶段出现同类契约漂移、补丁堆叠或验证证据失真。

触发停止条件后：停止 PydanticAI 后续工作，删除实验 Adapter/依赖/注入点，保留经 Native 证明的 Contract、BoundToolSession、生命周期和测试资产，并将 ADR 结论更新为 `Native Only`。

## 10. Definition of Ready / Definition of Done

### 10.1 DoR

- 上一阶段已合入且远端阻断 CI 绿色。
- 阶段 Issue/PR 只有一个主要语义和明确反例。
- 受影响文件、权威源、兼容入口和回滚点已列出。
- 未安装/已安装依赖状态和能力支持矩阵已明确。
- 涉及核心行为时已有 deterministic test design，不依赖 sleep 或真实网络。

### 10.2 DoD

- 阶段退出条件全部满足，不能用后续阶段承诺替代当前缺口。
- Native replay fixture 零删除、零放宽、零未解释变化。
- PR body 与实际 diff、测试结果、未验证项、风险和回滚一致。
- 同一语义涉及的 Runtime、API/SSE、持久化、workflow、docs 和 tests 已整体检查。
- 没有第二套配置、模型、工具、Conversation、Usage、Provider trace 或错误权威。
- 对无法强制中断的工作明确标注 cooperative，不宣称停止计费。
- 文档和 tracker 更新到实际合入状态。

## 11. 维护者审批点

执行 RF-01 前需要确认：

1. 是否批准 RF-00～RF-07 的串行顺序。
2. 是否同意在 RF-06 前把现有 PydanticAI CHAT 改为 explicit unsupported。
3. 是否同意第一版 conformance 只覆盖已批准的 Single RUN 支持矩阵，其他 fixture 验证明确拒绝，而不是提前扩大 Adapter 能力。
4. 是否接受 `Native Only` 为默认最终裁决。
5. 许可证 provenance、分发与 SaaS 义务是否另立治理任务；该决定不进入 Runtime 修复 PR。

## 12. 当前推荐动作

当前只执行 RF-00：合入本计划并同步 `docs/stockpulse-work-tracker.md` 的真实状态。不要同时修改 Runtime、CI、依赖或许可证。RF-00 获批准后，下一步是 RF-01，让可选依赖安装态首次成为不可静默跳过的阻断 CI；随后再依次修复 Contract、工具权威、生命周期和 PydanticAI Single RUN。
