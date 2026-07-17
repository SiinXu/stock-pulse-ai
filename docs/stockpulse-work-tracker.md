# StockPulse Work Tracker — Agent Runtime(AR)工作线

- 状态:`Living`(每个 AR 阶段合入/裁决后更新)
- 日期:2026-07-17(首版,随 AR-PY-00 创建;此前不存在,属治理文档漂移修复)
- 代码 baseline:`main@fa7a6ee1`
- 权威计划:`docs/architecture/pydanticai-runtime-development-plan.md`(`Approved`)
- 权威决策:`docs/architecture/ADR-001-agent-runtime.md`

## 1. 追踪原则

- 本 tracker 只记录 AR 工作线的阶段状态、合入证据与裁决记录;不复制计划细节(以开发计划为准)。
- 每行状态变更须附证据(PR 编号、commit、裁决日期);无证据不得标记完成。
- 首版不含历史条目:此前不存在本文档,任何"旧 baseline"或"AR-07"历史描述均无从修正,以当前主线为唯一起点。

## 2. 阶段状态总览

| 阶段 | 主题 | 状态 | 证据 |
| --- | --- | --- | --- |
| AR-01 | Replay characterization suite(36 fixtures + ReplayLLMAdapter) | **Done** | PR #11 合入主线;`tests/test_agent_runtime_compatibility.py`、`tests/agent_runtime_replay.py`、`tests/fixtures/agent_runtime/`(36 fixture:24 financial + 12 contract) |
| AR-PY-00 | 决策与基线收敛(docs-only) | **Done** | 开发计划 `Approved`;ADR-001 `Accepted`(2026-07-17,含 D2 裁决);framework comparison 与本文档首版创建 |
| AR-PY-01 | Runtime Contract + Native Adapter | **In progress(实现完成,待合入)** | `src/agent/runtime/`(contract + native adapter)+ `tests/agent/runtime/`(29 tests)+ `build_agent_runtime` 工厂;replay/executor/chat 回归绿;待 PR 合入后转 Done |
| AR-PY-02 | BoundToolSession | **In progress(实现完成,待合入)** | `src/agent/runtime/tool_session.py` + `tool_surface.py` 共享错误结构提取 + 23 项 fail-closed 测试;replay 45 项零修改通过;native runner 接线按计划留待 AR-PY-03 |
| AR-PY-03 | Lifecycle / typed events / 真实取消 | **In progress(实现完成,待合入)** | `src/agent/runtime/events.py` + `lifecycle.py`(versioned events + late-write fence + `classify_terminal_state` + `UsageRecorder`);runner/orchestrator/executor/base_agent 协作取消检查点;SSE endpoint 经 `to_public_sse_event` 单一降级点 + 断连 `request_cancel`;chat_context/native_adapter 收敛;29 项新测试;replay 45 项与冻结 SSE 测试零修改绿;native runner 工具路径仍不改线(留待 AR-PY-04) |
| AR-PY-04 | PydanticAI 隔离 POC(Spike + Adapter) | **In progress(首片实现,待合入)** | Spike 完成(隔离 venv 实测):选定**方案 B**(自定义 `Model` 包裹 `LLMToolAdapter`);依赖精化为 **`pydantic-ai-slim==2.12.0`**(避开 openai extra 的 `tiktoken>=0.12` 与 StockPulse #537 `<0.12` 冲突);`src/agent/runtime/pydantic_ai_adapter.py`(惰性 import,仅 Single Agent run,内部注入点)+ `pydantic_ai_toolset.py`(`BoundToolSession`→PydanticAI `Tool.from_schema` 单一工具桥接,经 `execute()` fail-closed 分发)+ `requirements-pydanticai.txt` 可选依赖 + 12 项测试(依赖缺失路径、fake model 跑通、工具调用经 fail-closed 门、gate 拒绝、仅暴露 allowlist 工具);未进默认/设置页,Native 零依赖;Spike 报告见 `.claude/reviews/ar-py-04-model-integration-spike.md` |
| AR-PY-05 | Conformance / benchmark / 决策门禁 | Blocked | 前置:AR-PY-04 合入 |
| AR-PY-06 | 有限产品化(条件阶段) | Blocked | 前置:AR-PY-05 通过 + 维护者再批准(审批点 6/7) |

## 3. 裁决记录

| 日期 | 事项 | 结果 |
| --- | --- | --- |
| 2026-07-17 | 开发计划批准(审批点 B3) | 维护者以"按照本计划开始开发"批准;计划状态 `Proposed` -> `Approved` |
| 2026-07-17 | 治理文档漂移处理 | 维护者确认:如实记录为漂移/Evidence gap,AR-PY-00 内创建(不虚构历史结论) |
| 2026-07-17 | ADR-001 Accepted(审批点 1) | 维护者批准"Native 永久默认 + Contract + 实验 Adapter"架构 |
| 2026-07-17 | 两个 degraded `success=true` 行为(审批点 2) | 批准 ADR-001 D2:冻结为兼容契约;未来修正走独立 ADR + versioned fixture |

## 4. 治理文档清单与状态

| 文档 | 状态 |
| --- | --- |
| `docs/architecture/pydanticai-runtime-development-plan.md` | `Approved`(2026-07-17) |
| `docs/architecture/ADR-001-agent-runtime.md` | `Accepted`(2026-07-17) |
| `docs/stockpulse-agent-runtime-framework-comparison.md` | `Living`(首版) |
| `docs/stockpulse-work-tracker.md` | `Living`(本文档) |
| `docs/agent-stream-events.md` | 既存,SSE 事件契约权威 |
| `docs/stockpulse-document-governance.md` 等其余漂移文档 | 不存在;是否创建由维护者按需决定(非 AR 工作线阻断项) |

## 5. 更新记录

| 日期 | 变更 |
| --- | --- |
| 2026-07-17 | 首版创建(AR-PY-00);登记 AR-01 Done、AR-PY-00 In progress、后续阶段 Blocked 及首批裁决记录 |
| 2026-07-17 | ADR-001 Accepted + D2 裁决批准;AR-PY-00 -> Done,AR-PY-01 -> Ready |
| 2026-07-17 | AR-PY-01 实现完成(Contract 状态机 + Native Adapter + 29 项新测试);状态 -> In progress(待合入) |
| 2026-07-17 | AR-PY-02 实现完成(BoundToolSession fail-closed 会话 + 23 项新测试);状态 -> In progress(待合入) |
| 2026-07-17 | AR-PY-03 实现完成(versioned events + late-write fence + 协作取消 + UsageRecorder/classify 收敛 + SSE 单一降级点 + 29 项新测试);状态 -> In progress(待合入) |
| 2026-07-17 | AR-PY-04 Spike 完成并定方案 B(维护者裁决审批点 3);实测 pydantic-ai-slim 绕开 tiktoken #537 冲突;首片实验 Adapter + 可选依赖 + 9 项测试落地;状态 -> In progress(首片,待合入) |
| 2026-07-17 | AR-PY-04 次片:BoundToolSession→PydanticAI 工具桥接(Tool.from_schema,经 execute() fail-closed 分发);测试增至 12 项;runtime 全套 93 项绿 |
| 2026-07-17 | AR-PY-04 event/usage 片:PydanticAI 运行 usage 收敛到单一 UsageRecorder(无第二套 usage 权威);工具桥接经 RuntimeEventEmitter 发 tool_start/tool_done;测试增至 14 项;runtime 全套 102 项绿 |
