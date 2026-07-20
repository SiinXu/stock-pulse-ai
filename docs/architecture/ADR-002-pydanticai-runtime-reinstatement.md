# ADR-002: 恢复实验 PydanticAI Runtime（Continue Experimental）

- 状态: `Accepted`（2026-07-19）
- 决策者: Maintainer（SiinXu）
- 修订对象: `docs/architecture/ADR-001-agent-runtime.md`（修订 D1；为本 ADR 的测试/证据 POC 有限覆盖 D5 的直接恢复禁令；D2/D3/D4 不变）
- 关联文档:
  - `docs/architecture/pydanticai-runtime-adoption-decision.md`（第 7 章记录本次改判）
  - `docs/stockpulse-work-tracker.md`（AR 工作追踪）

## 1. Context

RF-07 的 `Native Only` 是 recovery plan 的默认规则结果，不是对 PydanticAI 方向的
否定：`Continue Experimental` 所需的真实 provider benchmark 与 Desktop 多平台打包
证据依赖维护者资源（真实 API key、多平台构建机），无人值守流程无法产出，因此
按既定默认路径收尾，并于 2026-07-19 删除实验可执行资产（PR #41）。

2026-07-19 维护者本人裁决改判：长期意图是采用 PydanticAI，实验资产应恢复为
可选项继续演进。恢复路径是干净的——RT-01 删除时完整保留了中立 Runtime
Contract、`BoundToolSession`、统一生命周期/fence 与 36 个只读 replay fixture，
实验 Adapter 本就实现于这套中立 Contract 之上。

ADR-001 D5 与 adoption decision 第 5 章的重启条件均要求"另立 ADR、从当前中立
Contract 重新接入"，并禁止在证据不足时直接恢复 Adapter、依赖、注入点或 CI。
本 ADR 不再声称 D5 不变：它明确、有限地覆盖该恢复禁令，只批准 Single RUN 的
测试/证据 POC。恢复的 Adapter 通过保留的中立 Contract 接入（`ExecutionContext` /
`ExecutionHandle` / `BoundToolSession`），接受的降低证据门槛与仍未满足的生产门槛
见 D5。证据状态不升级，Native 仍是唯一生产装配，任何产品入口或默认 Runtime
升级仍须补齐缺口并另立 ADR。

RT-02（PR #44）已把历史 conformance 证据范围冻结为 8+3 个精确 fixture ID，并
规定重新引入 conformance 必须显式列出 case ID、未知 fixture fail closed、经新
ADR 审批。本 ADR 同时完成该审批（见 D3）。

## 2. Decision

### D1: 恢复实验 PydanticAI Runtime 为测试/证据 POC

以 RT-01 删除前基线适配当前 main 恢复以下资产：

- `src/agent/runtime/pydantic_ai_adapter.py`、`src/agent/runtime/pydantic_ai_toolset.py`
- `requirements-pydanticai.txt`（`pydantic-ai-slim` 及其传递闭包的精确版本集合，不进入默认 requirements）
- `src/agent/factory.build_agent_runtime()` 装配 seam 与 executor 内部注入点
- 实验测试与 conformance：`tests/agent/runtime/_pydantic_ai_dependency.py`、
  `test_pydantic_ai_adapter.py`、`test_pydantic_ai_real_bridge.py`、
  `test_conformance.py`、`test_conformance_replay.py`、`test_conformance_leak_scan.py`
- CI 阻断 job `pydanticai-installed`（安装态矩阵，`STOCKPULSE_REQUIRE_PYDANTIC_AI=1`
  下 skip 视为失败）；native gate 继续断言默认环境不存在 `pydantic_ai`

### D2: Continue Experimental 约束全部生效

- Native 是唯一生产装配：`build_agent_runtime()` 始终返回 `NativeRuntimeAdapter`，
  生产入口继续直接调用 `build_agent_executor()` / `ResearchAgent`。
- 唯一允许的实验 opt-in 是测试或证据 harness 直接构造
  `PydanticAIRuntimeAdapter(model=...)` 或显式注入 `llm_adapter`、executor 与
  `BoundToolSession`；不提供 factory/config/env/API/Web/Desktop/Bot selector，
  也不把该路径声明为受支持的产品能力。
- `start()` 必须遵循中立 Contract：在 worker 运行时返回 live
  `ExecutionHandle`，允许观察 `RUNNING`、协作取消、订阅事件及等待终态；
  `execute()` 仅为 start + wait 的同步兼容 helper。终态解析与写入必须在
  `AgentExecution` 同一状态锁内完成，使已接受的取消与终态 first-wins 原子串行；
  direct model 与 StockPulse bridge 的工具 dispatch/result acceptance 均通过同一
  per-execution cancel/deadline fence 原子 reservation，迟到结果必须审计后丢弃。
- 零 PydanticAI 依赖可运行：默认依赖清单不含 pydantic-ai，backend-gate 在未
  安装状态下运行并保持绿色。
- Runtime fallback 默认关闭：不存在自动切换或降级到实验 Runtime 的路径。
- 本轮不新增用户设置、环境变量开关、公开 API 或持久 Agent Job。
- 实验资产保持整体可删除（见第 4 章回滚）。

### D3: conformance 采用显式 fixture ID 允许清单（fail closed）

- 双跑范围只认显式 ID，不按 mode/profile 派生。完全等价（8）：
  `a-single-run-normal`、`hk-single-run-normal`、`us-single-run-normal`、
  `a-single-run-partial`、`contract-modelref-single-mismatch`、
  `contract-fallback-provider-error`、`contract-toolscope-unknown-tool`、
  `contract-malformed-dashboard-repaired`。仅终态分类等价（3）：
  `contract-timeout-agent-wallclock`、`contract-cancelrace-single-slow-tool`、
  `contract-cancelrace-parallel-late-tool`。
- 未列入允许清单的 `single_run` fixture 会使支持矩阵测试失败（fail closed）；
  扩大允许清单必须另立 ADR。
- 3 个仅终态分类等价 fixture 的历史工具执行日志差异记录为本 ADR 认可的
  intentional difference，不据此宣称工具序列等价；live handle 的取消若在模型
  wire call 中到达，实验 Runtime 仍须在处理返回的 tool call 前 fence。两侧均不得
  伪造成功，dashboard 均保持为空。
- 36 个 replay fixture 保持只读，不重录、不放宽。

### D4: 证据状态不升级

- adoption decision 第 4 章缺口（真实 provider benchmark、Desktop 多平台打包、
  其余泄漏面、双环境可复现依赖净增量）仍未收集，证据状态保持
  `Historical / Partial`。安装兼容窗口已由 `requirements-pydanticai.txt` 的完整
  精确传递闭包和 Python 3.11 安装态 CI `pip check` 固化，但这不等同于双环境净
  增量、artifact hash 或多平台打包证据。
- 本 ADR 只恢复可执行资产与离线门禁，不宣称 RF-06 完成，不重写历史裁决记录。
- 若未来要把 PydanticAI 升级为默认 Runtime 或扩展到 CHAT/RESEARCH/多 Agent
  模式，需先补齐上述证据并另立 ADR。

### D5: 明确、有限覆盖 ADR-001 D5

本 ADR 仅为该 POC 接受以下恢复门槛：

- 中立 Contract、8 个完全等价 fixture、3 个终态分类 fixture 与未知 fixture
  fail-closed 门禁保持通过；
- PydanticAI `start()` 的 live handle、取消、订阅、等待及异常传播有直接回归，
  并覆盖 pre-terminal cancel/deadline race、direct-model tool dispatch reservation
  与 in-flight result audit fence；
- 可选依赖完整传递闭包精确锁定，安装态 CI 执行 `pip check`；
- Native 默认环境无 PydanticAI，生产 factory/config/env/API 无实验 selector；
- 已有 provider-error 脱敏回归保持通过，未收集安全面继续如实列为缺口。

这一覆盖不批准生产调用、公开 opt-in、默认 Runtime、CHAT/RESEARCH/多 Agent 或
Desktop 打包。上述扩展仍受 ADR-001 D5 完整门槛约束，并必须由新 ADR 审批。

## 3. Consequences

- 双 Runtime 维护面回归：Contract 或工具语义变更需同步 Native 与实验 Adapter，
  并保持 conformance 允许清单内全部通过。
- ADR-001 D1 的"唯一可执行 Runtime"仅在测试/证据 POC 范围内不再描述现状；
  D5 的直接恢复禁令按本 ADR 降低门槛有限覆盖，生产化门槛继续有效；D2/D3/D4
  （中立 Contract 与安全资产保留、单一业务权威、Native 行为兼容）不变。
- 历史文档（recovery plan、adoption decision 第 3～5 章）保持历史记录原样。

## 4. Rollback

- 整体 revert 本次恢复提交即回到 Native Only 状态；不得只回滚 Adapter、依赖或
  CI 的一部分。
- Contract、`BoundToolSession`、生命周期、事件、sanitizer 与 Native replay 测试
  不属于实验资产，不随回滚删除。

## 5. Decision log

| 日期 | 状态 | 摘要 |
| --- | --- | --- |
| 2026-07-19 | Accepted | 维护者裁决 `Continue Experimental`：以明确降低的 D5 证据门槛恢复 Single RUN 测试/证据 POC；Native 是唯一生产装配、conformance 显式允许清单 fail closed、live handle 与精确依赖闭包纳入阻断门、证据状态不升级 |
