# ADR-002: 恢复实验 PydanticAI Runtime（Continue Experimental）

- 状态: `Accepted`（2026-07-19）
- 决策者: Maintainer（SiinXu）
- 修订对象: `docs/architecture/ADR-001-agent-runtime.md`（改判其 D1 "Native 是唯一可执行 Runtime"；D2/D3/D4/D5 不变）
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
Contract 重新接入"。本 ADR 即该审批：恢复的 Adapter 通过保留的中立 Contract
接入（`ExecutionContext` / `ExecutionHandle` / `BoundToolSession`），并已对当前
main 基线验证适配。重启条件中"补齐第 4 章证据"原本是把实验 Runtime 推向
`Continue Experimental` 收益判断的前提；维护者明确接受在证据未补齐的情况下
恢复实验资产，代价与补偿控制见 D4：证据状态不升级、Native 保持默认、默认
Runtime 升级另立 ADR。

RT-02（PR #44）已把历史 conformance 证据范围冻结为 8+3 个精确 fixture ID，并
规定重新引入 conformance 必须显式列出 case ID、未知 fixture fail closed、经新
ADR 审批。本 ADR 同时完成该审批（见 D3）。

## 2. Decision

### D1: 恢复实验 PydanticAI Runtime 为可选资产

以 RT-01 删除前基线适配当前 main 恢复以下资产：

- `src/agent/runtime/pydantic_ai_adapter.py`、`src/agent/runtime/pydantic_ai_toolset.py`
- `requirements-pydanticai.txt`（`pydantic-ai-slim` 可选清单，不进入默认 requirements）
- `src/agent/factory.build_agent_runtime()` 装配 seam 与 executor 内部注入点
- 实验测试与 conformance：`tests/agent/runtime/_pydantic_ai_dependency.py`、
  `test_pydantic_ai_adapter.py`、`test_pydantic_ai_real_bridge.py`、
  `test_conformance.py`、`test_conformance_replay.py`、`test_conformance_leak_scan.py`
- CI 阻断 job `pydanticai-installed`（安装态矩阵，`STOCKPULSE_REQUIRE_PYDANTIC_AI=1`
  下 skip 视为失败）；native gate 继续断言默认环境不存在 `pydantic_ai`

### D2: Continue Experimental 约束全部生效

- Native 永久默认：`build_agent_runtime()` 始终返回 `NativeRuntimeAdapter`，
  生产入口继续直接调用 `build_agent_executor()` / `ResearchAgent`。
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
- 3 个仅终态分类等价 fixture 的 fence 位置差异（Native 在当前 step 的工具前
  fence timeout/cancel，实验 Runtime 在其后）记录为本 ADR 认可的 intentional
  difference；两侧均不得伪造成功，dashboard 均保持为空。
- 36 个 replay fixture 保持只读，不重录、不放宽。

### D4: 证据状态不升级

- adoption decision 第 4 章缺口（真实 provider benchmark、Desktop 多平台打包、
  其余泄漏面、可复现依赖净增量）仍未收集，证据状态保持 `Historical / Partial`。
- 本 ADR 只恢复可执行资产与离线门禁，不宣称 RF-06 完成，不重写历史裁决记录。
- 若未来要把 PydanticAI 升级为默认 Runtime 或扩展到 CHAT/RESEARCH/多 Agent
  模式，需先补齐上述证据并另立 ADR。

## 3. Consequences

- 双 Runtime 维护面回归：Contract 或工具语义变更需同步 Native 与实验 Adapter，
  并保持 conformance 允许清单内全部通过。
- ADR-001 D1 的"唯一可执行 Runtime"表述与删除清单不再描述现状；ADR-001 其余
  决策（中立 Contract 与安全资产保留、单一业务权威、Native 行为兼容、未来框架
  重新提案）继续有效。
- 历史文档（recovery plan、adoption decision 第 3～5 章）保持历史记录原样。

## 4. Rollback

- 整体 revert 本次恢复提交即回到 Native Only 状态；不得只回滚 Adapter、依赖或
  CI 的一部分。
- Contract、`BoundToolSession`、生命周期、事件、sanitizer 与 Native replay 测试
  不属于实验资产，不随回滚删除。

## 5. Decision log

| 日期 | 状态 | 摘要 |
| --- | --- | --- |
| 2026-07-19 | Accepted | 维护者裁决 `Continue Experimental`：恢复实验 PydanticAI Runtime 为可选资产；Native 永久默认、conformance 显式允许清单 fail closed、证据状态不升级 |
