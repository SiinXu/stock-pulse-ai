# StockPulse Work Tracker — Agent Runtime(AR)工作线

- 状态:`Living`(每个 AR 阶段合入/裁决后更新)
- 日期:2026-07-17(首版,随 AR-PY-00 创建;此前不存在,属治理文档漂移修复)
- 代码 baseline:`main@30926876`(PR #18 合入 commit)
- 权威计划:`docs/architecture/pydanticai-runtime-development-plan.md`(`Approved`)
- 权威决策:`docs/architecture/ADR-001-agent-runtime.md`
- 修复计划:`docs/architecture/pydanticai-runtime-recovery-plan.md`(`Proposed`,RF-00～RF-07)

## 1. 追踪原则

- 本 tracker 只记录 AR 工作线的阶段状态、合入证据与裁决记录;不复制计划细节(以开发计划为准)。
- 每行状态变更须附证据(PR 编号、commit、裁决日期);无证据不得标记完成。
- 首版不含历史条目:此前不存在本文档,任何"旧 baseline"或"AR-07"历史描述均无从修正,以当前主线为唯一起点。

## 2. 阶段状态总览

| 阶段 | 主题 | 状态 | 证据 |
| --- | --- | --- | --- |
| AR-01 | Replay characterization suite(36 fixtures + ReplayLLMAdapter) | **Done** | PR #11 合入主线;`tests/test_agent_runtime_compatibility.py`、`tests/agent_runtime_replay.py`、`tests/fixtures/agent_runtime/`(36 fixture:24 financial + 12 contract) |
| AR-PY-00 | 决策与基线收敛(docs-only) | **Done** | 开发计划 `Approved`;ADR-001 `Accepted`(2026-07-17,含 D2 裁决);framework comparison 与本文档首版创建 |
| AR-PY-01 | Runtime Contract + Native Adapter | **Partial** | 已随 PR #18 合入:`src/agent/runtime/`(contract + native adapter)+ `tests/agent/runtime/` + `build_agent_runtime` 工厂;缺口:`execute()` 终态后才返回 handle(非运行中控制柄)、`ExecutionContext` 输入不完整且仅浅层冻结(AR-RF-01/02);修复走 RF-02 |
| AR-PY-02 | BoundToolSession | **Partial** | 已随 PR #18 合入:`src/agent/runtime/tool_session.py`(allowlist/权限/预算/deadline/审计/late-result fence)+ fail-closed 测试;缺口:Native 仍走 legacy direct path,存在两套工具权威(AR-RF-03);修复走 RF-03 |
| AR-PY-03 | Lifecycle / typed events / 真实取消 | **Partial** | 已随 PR #18 合入:`src/agent/runtime/events.py` + `lifecycle.py`(versioned events + late-write fence + `classify_terminal_state` + `UsageRecorder`)+ 部分 runner/orchestrator 取消检查点 + Chat SSE 断连取消(`to_public_sse_event` 单一降级点);缺口:lifecycle 主要由 Chat SSE 单独持有,未形成全入口统一生命周期、终态分类与持久化 fence(AR-RF-07);修复走 RF-04 |
| AR-PY-04 | PydanticAI 隔离 POC(Spike + Adapter) | **Experimental / Incomplete** | 已随 PR #18 合入:方案 B(自定义 `Model` 包裹 `LLMToolAdapter`)+ `pydantic-ai-slim==2.12.0` 可选依赖(`requirements-pydanticai.txt`)+ `pydantic_ai_adapter.py` / `pydantic_ai_toolset.py`;Spike 结论以本行与 ADR-001 D4 记录为准,原报告为本地评审产物未入库;缺口:模型桥固定发送空工具 schema、ToolCall/ToolReturn 历史丢失、Prompt 等价未证明、timeout/cancel 未消费、CHAT 提前扩面、usage 字段与存储摘要列不匹配(AR-RF-04/05/06/10/11);修复走 RF-05;裁决前不得启用或宣传该路径 |
| AR-PY-05 | Conformance / benchmark / 决策门禁 | **Not started** | 仅有 5 个简化 fake conformance tests(`tests/agent/runtime/test_conformance.py`,AR-RF-08);无 replay 支持矩阵、benchmark 与可选依赖 CI(默认 CI 经 `importorskip` 静默跳过 PydanticAI 测试,AR-RF-09);修复走 RF-01/RF-06 |
| AR-PY-06 | 有限产品化(条件阶段) | Blocked | Native 仍默认,实验 Runtime 未向用户公开;前置:RF-06 通过 + 维护者裁决(RF-07,默认 `Native Only`) |

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
| `docs/architecture/pydanticai-runtime-recovery-plan.md` | `Proposed`(2026-07-18,PR #18 合入后修复计划,RF-00～RF-07) |
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
| 2026-07-17 | AR-PY-05 脚手架(并行,不合入前提):契约一致性 conformance 测试(Native vs PydanticAI 参数化,5 项),断言两 runtime 契约等价、失败不伪成功 |
| 2026-07-17 | AR-PY-04 第二条路径:adapter 支持单 Agent CHAT(自由文本、无 dashboard、无状态 POC);RESEARCH 仍 NotImplemented;Multi/Research/默认/设置页仍不碰;测试增至 16+5 项 |
| 2026-07-18 | PR #18 合入后审计(RF-00):创建 recovery plan 并登记 AR-RF-01～13;代码 baseline -> `main@30926876`;AR-PY-01～03 -> Partial,AR-PY-04 -> Experimental / Incomplete,AR-PY-05 -> Not started,AR-PY-06 -> Blocked;移除未入库 Spike 报告文件引用;RF-06 裁决前冻结 PydanticAI CHAT/Multi/Research 与产品入口扩展 |
