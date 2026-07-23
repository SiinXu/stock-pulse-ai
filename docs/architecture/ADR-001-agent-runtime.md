# ADR-001: Agent Runtime 架构 - Native Only + vendor-neutral Runtime Contract

- 状态: `Accepted / Amended by ADR-002`（2026-07-19 修订并执行 Native Only 裁决；同日 ADR-002 为测试/证据 POC 明确修订 D1，并有限覆盖 D5 的恢复禁令；D2/D3/D4 不变）
- 首次批准: 2026-07-17
- 最近修订: 2026-07-19
- 决策者: Maintainer（SiinXu）
- 实施基线: `main@b8983fc7`
- 关联文档:
  - `docs/architecture/ADR-002-pydanticai-runtime-reinstatement.md`（2026-07-19 改判：恢复实验 Runtime，Native 默认不变）
  - `docs/architecture/pydanticai-runtime-adoption-decision.md`（裁决证据与实施结果）
  - `docs/architecture/pydanticai-runtime-development-plan.md`（历史计划，已停止）
  - `docs/architecture/pydanticai-runtime-recovery-plan.md`（历史恢复计划，已停止）
  - `docs/stockpulse-work-tracker.md`（AR 工作追踪）
  - `docs/agent-stream-events.md`（SSE 事件契约）

## 1. Context

StockPulse 的 Agent 执行层由 Native `AgentExecutor`、`AgentOrchestrator` 和
`ResearchAgent` 提供。AR-PY-01 至 AR-PY-03 为这套实现增加了中立 Runtime
Contract、`NativeRuntimeAdapter`、`BoundToolSession`、统一生命周期、取消、
事件和安全诊断能力。36 个只读 replay fixture 持续冻结现有 Native 行为。

2026-07-17 至 2026-07-18 期间，项目通过隔离的 PydanticAI POC 评估外部框架。
RF-07 因缺少可证明的真实 provider 收益和 Desktop 多平台证据，裁决为
`Native Only`。裁决后主线仍保留休眠 Adapter、可选依赖、内部注入函数、
cross-runtime 测试和专用 CI，导致“唯一正式运行时”和实际维护面不一致。

本修订执行已经批准的停止路径：删除 vendor-specific 可执行资产，同时保留
已经在 Native 路径证明价值的中立资产和安全回归。

## 2. Decision

### D1: Native 是唯一生产 Agent Runtime（由 ADR-002 修订）

Native 是唯一生产装配；ADR-002 另恢复了仅供测试/证据 harness 显式构造的
PydanticAI Single RUN POC。两条路径严格隔离：

```text
Production requests
  API / Web / Desktop / Bot
    -> StockPulse Agent business entrypoints
        -> build_agent_executor() -> AgentExecutor / AgentOrchestrator
        -> research entrypoints -> ResearchAgent

Contract and parity coverage
  vendor-neutral Runtime Contract and lifecycle
    -> NativeRuntimeAdapter -> the same Native implementations
    -> explicit test/evidence construction -> PydanticAIRuntimeAdapter
```

`NativeRuntimeAdapter` 是中立合同、生命周期和一致性测试的 Native 包装，不是
每个生产请求必须经过的装配层。现有生产入口继续直接调用
`build_agent_executor()` 或 `ResearchAgent`。

具体约束：

- 实验 Adapter 与显式注入点只服务测试/证据，不进入生产 factory、config、env、
  API、Web、Desktop 或 Bot，也不提供 runtime selector 或 fallback。
- `AGENT_ARCH` 继续只选择 StockPulse 的 single/multi 业务架构，不选择 vendor runtime。
- 默认依赖、Desktop 和 Docker 不安装外部 Agent runtime 依赖；专用
  `pydanticai-installed` CI 只安装并验证精确锁定的实验依赖闭包。
- `build_agent_executor()` 仍是生产装配入口；内部 `build_agent_runtime()` 存在但
  始终返回 `NativeRuntimeAdapter`，且不接受实验 selector。
- Native CI 断言默认环境不存在 `pydantic_ai`；安装态 CI 断言实验模块可导入、
  依赖一致且约定的 conformance/live-handle 测试不 skip。

### D2: 保留中立 Contract 与 Native 安全资产

以下资产属于 StockPulse，而不是历史 POC，必须保留：

- `runtime/contract.py`: execution context、handle、状态机和 terminal first-wins；
- `runtime/native_adapter.py`: Native 合同与一致性包装，不是生产必经层；
- `runtime/tool_session.py`: per-execution 工具 allowlist、权限、预算、deadline、
  取消、审计和 late-result fence；
- `runtime/lifecycle.py` 与 `runtime/events.py`: 终态分类、usage 和事件边界；
- `public_contract.py::sanitize_agent_diagnostic`: 有界、安全的公开诊断；
- `tests/agent/test_agent_runtime_compatibility.py`、`tests/agent_runtime_replay.py` 和
  全部 36 个 replay fixture。

历史实验 leak scan 中有通用价值的断言迁移到 Native 异常路径：API key、带凭据
URL 和 Bearer token 必须脱敏，公开诊断最多 300 字符；异常保持 `FAILED`，不得
生成成功结果或 dashboard。

### D3: StockPulse 保持单一业务权威

以下所有权不得让渡给任何未来框架：

- single/multi/research 拓扑和金融阶段；
- Provider Catalog、Connection、模型路由和 fallback；
- Prompt/Skill、报告 Schema 和 degraded 兼容语义；
- Conversation、Provider trace、Usage、错误契约和持久化；
- execution 生命周期、取消、事件、terminal precedence 和工具策略；
- API/SSE/Web/Desktop/Bot 公共契约。

### D4: 现有 Native 行为保持兼容

本裁决不改变公开 API、配置、数据库、SSE 或报告载荷，也不重录或放宽 replay
fixture。两个既有 degraded `success=true` 行为继续按 2026-07-17 裁决冻结：

1. 预算不足或超时但有可用阶段结果时，可以合成 partial dashboard，并在
   metadata、事件和 `error` 中标记降级；
2. Decision 阶段解析失败时，可以从 Technical/Intel 结果合成兼容报告。

取消仍优先于 degraded success，取消执行不得产出伪成功。

### D5: 未来框架必须重新提案（由 ADR-002 有限覆盖）

未来若评估任何外部 Agent 框架，必须从新的 ADR 和隔离证据开始，经本中立
Contract 接入。不得直接恢复已删除的 Adapter、依赖清单、注入点或 CI，也不得
以“默认关闭”为由永久维护第二套可执行实现。至少需要证明：

- 对当前 Native 契约和精确 replay fixture 的等价性；
- 真实 provider 的收益、失败分类、成本和延迟；
- source、Docker 与 Desktop 的依赖和打包影响；
- Secret、prompt、reasoning、tool result 和原始异常不会泄漏；
- 对单一配置、工具、Conversation、Usage 和 Provider trace 权威无侵入。

ADR-002 是对本条的一次明确、有限覆盖：仅允许恢复 PydanticAI 2.12 的
Single RUN 测试/证据 POC，不建立生产装配或用户 opt-in。维护者接受的恢复门槛是：
中立 Contract 与冻结 conformance 子集继续通过；`start()` 提供可观察、可取消、
可订阅和可等待的 live handle；可选依赖传递闭包精确锁定并由安装态 CI 执行
`pip check`；Native 默认安装零 PydanticAI 依赖且无 factory/config/env selector；
已收集的脱敏证据保持有效。真实 provider 收益、完整泄漏面、Desktop 多平台打包和
双环境净增量仍未完成，因此继续阻断生产入口、默认 Runtime 或支持矩阵扩展。除该
POC 外的新框架提案，以及把该 POC 提升为生产能力，仍须满足本条完整门槛并另立 ADR。

## 3. Consequences

正面：

- 生产代码、默认依赖和配置继续保持 Native-only，无隐式选择或 fallback；
- 实验 POC 通过同一 Contract、BoundToolSession、生命周期、取消和脱敏边界执行；
- 36 个 replay fixture、显式 8+3 conformance 范围、Native isolation guard 与安装态
  CI 共同提供确定性回归证据；
- 精确依赖闭包使当前 Python 3.11 实验安装兼容窗口可复现。

成本与限制：

- 双 Runtime 测试面、依赖升级和供应链门禁重新产生维护成本；
- 当前可执行 conformance 只证明显式 8+3 fixture 边界，不等于真实 provider
  benchmark、完整安全面、Desktop 打包或生产支持；
- 历史 benchmark 数字仍只作为决策记录，不因测试恢复而升级证据等级；
- 中立 Contract 与 `NativeRuntimeAdapter` 仍有维护和测试成本，但当前生产入口
  不经过 Adapter，因此不会增加每个生产请求的包装开销。

## 4. Compatibility and rollback

- 公共 API、Schema、配置、数据库、Web/Desktop/Bot 行为不变。
- `build_agent_runtime()` 是内部 Native-only assembly seam；生产入口
  `build_agent_executor()` 和兼容别名 `build_executor` 保持不变。
- 回滚 ADR-002 POC 必须整体移除 Adapter、toolset、可选依赖、注入点、实验测试和
  专用 CI；不得只回滚其中一部分。中立 Contract 与 Native 安全资产继续保留。

## 5. Verification

- Native Contract、Adapter、lifecycle、tool session 和 session bridge 测试；
- 36 个 replay fixture 的 compatibility suite；
- Native 异常脱敏、长度边界和 fail-closed 回归；
- 静态断言实验资产存在但只能由测试/证据显式构造，生产 factory 无 selector；
- 默认依赖环境中的 Native import isolation，以及安装态 CI 的 PydanticAI import、
  `pip check`、live-handle/cancel/event 回归和显式 cross-runtime conformance；
- repository syntax、flake8、deterministic 和 offline gates。

## 6. Decision log

| 日期 | 状态 | 说明 |
| --- | --- | --- |
| 2026-07-17 | Accepted | 批准 Native 永久默认、中立 Contract、实验 Adapter POC 和 degraded 兼容语义 |
| 2026-07-18 | Accepted | RF-07 因收益与 Desktop 证据不足裁决 `Native Only` |
| 2026-07-19 | Accepted / Implemented | 删除实验 Adapter、依赖、注入点、cross-runtime 测试和专用 CI；保留并加固 Native 中立资产 |
| 2026-07-19 | Amended | ADR-002 恢复 PydanticAI Single RUN 测试/证据 POC：修订 D1，并按 ADR-002 记录的降低门槛有限覆盖 D5 的直接恢复禁令；Native 仍是唯一生产装配，D2/D3/D4 不变，生产化仍受 D5 完整门槛约束 |
