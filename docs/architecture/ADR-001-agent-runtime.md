# ADR-001: Agent Runtime 架构 - Native Only + vendor-neutral Runtime Contract

- 状态: `Accepted`（2026-07-19 修订并执行 Native Only 裁决）
- 首次批准: 2026-07-17
- 最近修订: 2026-07-19
- 决策者: Maintainer（SiinXu）
- 实施基线: `main@b8983fc7`
- 关联文档:
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

### D1: Native 是唯一可执行 Agent Runtime

当前只有 Native 可执行实现。生产调用路径与保留的合同一致性路径分别为：

```text
Production requests
  API / Web / Desktop / Bot
    -> StockPulse Agent business entrypoints
        -> build_agent_executor() -> AgentExecutor / AgentOrchestrator
        -> research entrypoints -> ResearchAgent

Contract and parity coverage
  vendor-neutral Runtime Contract and lifecycle
    -> NativeRuntimeAdapter -> the same Native implementations
```

`NativeRuntimeAdapter` 是中立合同、生命周期和一致性测试的 Native 包装，不是
每个生产请求必须经过的装配层。现有生产入口继续直接调用
`build_agent_executor()` 或 `ResearchAgent`。

具体约束：

- 不保留第二套 Runtime Adapter、runtime selector、fallback 或内部实验注入点。
- `AGENT_ARCH` 继续只选择 StockPulse 的 single/multi 业务架构，不选择 vendor runtime。
- 默认依赖、Desktop、Docker 和 CI 均不安装或测试外部 Agent runtime 依赖。
- `build_agent_executor()` 仍是生产装配入口；删除无生产调用方的
  `build_agent_runtime()` 不构成公共 API 变更。
- Native-only CI 同时断言外部依赖、实验模块和实验注入函数均不存在。

### D2: 保留中立 Contract 与 Native 安全资产

以下资产属于 StockPulse，而不是历史 POC，必须保留：

- `runtime/contract.py`: execution context、handle、状态机和 terminal first-wins；
- `runtime/native_adapter.py`: Native 合同与一致性包装，不是生产必经层；
- `runtime/tool_session.py`: per-execution 工具 allowlist、权限、预算、deadline、
  取消、审计和 late-result fence；
- `runtime/lifecycle.py` 与 `runtime/events.py`: 终态分类、usage 和事件边界；
- `public_contract.py::sanitize_agent_diagnostic`: 有界、安全的公开诊断；
- `tests/test_agent_runtime_compatibility.py`、`tests/agent_runtime_replay.py` 和
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

### D5: 未来框架必须重新提案

未来若评估任何外部 Agent 框架，必须从新的 ADR 和隔离证据开始，经本中立
Contract 接入。不得直接恢复已删除的 Adapter、依赖清单、注入点或 CI，也不得
以“默认关闭”为由永久维护第二套可执行实现。至少需要证明：

- 对当前 Native 契约和精确 replay fixture 的等价性；
- 真实 provider 的收益、失败分类、成本和延迟；
- source、Docker 与 Desktop 的依赖和打包影响；
- Secret、prompt、reasoning、tool result 和原始异常不会泄漏；
- 对单一配置、工具、Conversation、Usage 和 Provider trace 权威无侵入。

## 3. Consequences

正面：

- 代码、依赖、CI、文档与 `Native Only` 裁决一致；
- 不再为不可执行实验路径承担升级、供应链和双 runtime conformance 成本；
- Contract、BoundToolSession、生命周期、取消和脱敏收益继续服务 Native；
- 36 个 replay fixture 和 Native isolation guard 继续提供确定性回归证据。

成本与限制：

- 历史 cross-runtime benchmark 不能作为当前可执行能力；仅保留为决策记录；
- 若未来重新评估框架，需要新建适配实现和验证矩阵，不能复活历史耦合；
- 中立 Contract 与 `NativeRuntimeAdapter` 仍有维护和测试成本，但当前生产入口
  不经过 Adapter，因此不会增加每个生产请求的包装开销。

## 4. Compatibility and rollback

- 公共 API、Schema、配置、数据库、Web/Desktop/Bot 行为不变。
- 删除的 `build_agent_runtime()` 是无生产调用方的内部实验装配函数；生产入口
  `build_agent_executor()` 和兼容别名 `build_executor` 保持不变。
- 回滚应整体 revert 实施 Native Only 的提交；不得只恢复 Adapter 或 CI 的一部分，
  以免重新形成未受支持的半套 runtime。

## 5. Verification

- Native Contract、Adapter、lifecycle、tool session 和 session bridge 测试；
- 36 个 replay fixture 的 compatibility suite；
- Native 异常脱敏、长度边界和 fail-closed 回归；
- 静态断言实验模块、依赖清单和注入函数不存在；
- 默认依赖环境中的 Native import isolation；
- repository syntax、flake8、deterministic 和 offline gates。

## 6. Decision log

| 日期 | 状态 | 说明 |
| --- | --- | --- |
| 2026-07-17 | Accepted | 批准 Native 永久默认、中立 Contract、实验 Adapter POC 和 degraded 兼容语义 |
| 2026-07-18 | Accepted | RF-07 因收益与 Desktop 证据不足裁决 `Native Only` |
| 2026-07-19 | Accepted / Implemented | 删除实验 Adapter、依赖、注入点、cross-runtime 测试和专用 CI；保留并加固 Native 中立资产 |
