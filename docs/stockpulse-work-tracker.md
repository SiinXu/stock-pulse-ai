# StockPulse Work Tracker — Agent Runtime(AR)工作线

- 状态:`Living`(每个 AR 阶段合入/裁决后更新)
- 日期:2026-07-17(首版,随 AR-PY-00 创建;此前不存在,属治理文档漂移修复)
- 代码 baseline:`main@30926876`(PR #18 合入 commit)
- 权威计划:`docs/architecture/pydanticai-runtime-development-plan.md`(`Approved`)
- 权威决策:`docs/architecture/ADR-001-agent-runtime.md`
- 修复计划:`docs/architecture/pydanticai-runtime-recovery-plan.md`(`Accepted`,RF-00～RF-07;RF-00～RF-05 已合入,RF-06～RF-07 待执行)

## 1. 追踪原则

- 本 tracker 只记录 AR 工作线的阶段状态、合入证据与裁决记录;不复制计划细节(以开发计划为准)。
- 每行状态变更须附证据(PR 编号、commit、裁决日期);无证据不得标记完成。
- 首版不含历史条目:此前不存在本文档,任何"旧 baseline"或"AR-07"历史描述均无从修正,以当前主线为唯一起点。

## 2. 阶段状态总览

| 阶段 | 主题 | 状态 | 证据 |
| --- | --- | --- | --- |
| AR-01 | Replay characterization suite(36 fixtures + ReplayLLMAdapter) | **Done** | PR #11 合入主线;`tests/test_agent_runtime_compatibility.py`、`tests/agent_runtime_replay.py`、`tests/fixtures/agent_runtime/`(36 fixture:24 financial + 12 contract) |
| AR-PY-00 | 决策与基线收敛(docs-only) | **Done** | 开发计划 `Approved`;ADR-001 `Accepted`(2026-07-17,含 D2 裁决);framework comparison 与本文档首版创建 |
| AR-PY-01 | Runtime Contract + Native Adapter | **Done** | 已随 PR #18 合入契约与 Native adapter;RF-02(PR #22,commit cc3a8e30)将 `execute()` 改造为运行中 `start() -> ExecutionHandle` 并深层冻结 `ExecutionContext`(`_deep_freeze`),关闭 AR-RF-01/02;缺口清零 |
| AR-PY-02 | BoundToolSession | **Done** | 已随 PR #18 合入 `tool_session.py`(allowlist/权限/预算/deadline/审计/late-result fence);RF-03(PR #23,commit 4e0e820c;deadline 绝对单调化 9f4a7882)使 Native 经同一 `BoundToolSession`(`enforce_access_policy=False`)分发,消除第二套工具权威,关闭 AR-RF-03 |
| AR-PY-03 | Lifecycle / typed events / 真实取消 | **Done** | 已随 PR #18 合入 `events.py` + `lifecycle.py`(versioned events + late-write fence + `classify_terminal_state` + `UsageRecorder`);RF-04(PR #25,commit 8ec4bdd4;changelog PR #27)以单一分类器统一全入口终态 write fence 与生命周期,关闭 AR-RF-07 |
| AR-PY-04 | PydanticAI 隔离 POC(Spike + Adapter) | **Experimental(Native Only 裁决;休眠可删)** | RF-05(PR #28,commit cb3aba8d)完成真实模型桥:工具 schema 下发、ToolCall/ToolReturn/reasoning/provider trace 无损往返、复用 `AgentExecutor.build_run_messages` prompt 权威、usage 单点记录并修字段、deadline/cancel fence、CHAT/RESEARCH -> `unsupported_capability`,关闭 AR-RF-04/05/06/10/11;RF-07 裁决 `Native Only`(见 AR-PY-06),该实验路径保持默认关闭、测试覆盖、可整体删除 |
| AR-PY-05 | Conformance / benchmark / 决策门禁 | **Done** | RF-01(PR #21)可选依赖安装态 CI 矩阵关闭 AR-RF-09;RF-06a(PR #32)离线 cross-runtime conformance 双跑(8 等价 + 3 有意差异 ADR-001 D5 + 非 RUN unsupported)关闭 AR-RF-08 的离线部分;RF-06b(PR #33)实验 Runtime 失败面泄漏扫描 + RF-07 决策证据卷宗;真实 provider benchmark / Desktop 打包证据在 RF-07 `Native Only` 裁决下不再作为阻断项(重启 Experimental 时另补) |
| AR-PY-06 | 有限产品化(条件阶段) | **Resolved(Native Only)** | RF-07 裁决 `Native Only`(2026-07-18,维护者),见 `docs/architecture/pydanticai-runtime-adoption-decision.md`(`Accepted`):Native 永久默认、零 PydanticAI 依赖;实验 Runtime 不向用户公开、可整体删除;`Continue Experimental` 因缺真实 benchmark 与 Desktop 证据未启用 |

## 3. 裁决记录

| 日期 | 事项 | 结果 |
| --- | --- | --- |
| 2026-07-17 | 开发计划批准(审批点 B3) | 维护者以"按照本计划开始开发"批准;计划状态 `Proposed` -> `Approved` |
| 2026-07-17 | 治理文档漂移处理 | 维护者确认:如实记录为漂移/Evidence gap,AR-PY-00 内创建(不虚构历史结论) |
| 2026-07-17 | ADR-001 Accepted(审批点 1) | 维护者批准"Native 永久默认 + Contract + 实验 Adapter"架构 |
| 2026-07-17 | 两个 degraded `success=true` 行为(审批点 2) | 批准 ADR-001 D2:冻结为兼容契约;未来修正走独立 ADR + versioned fixture |
| 2026-07-18 | RF-05 范围审批(recovery plan 审批点 2/3) | 维护者批准:CHAT/RESEARCH 冻结为 `unsupported_capability`、复用 native prompt 权威(`build_run_messages`)、usage 单点记录;首版 conformance 仅覆盖 Single RUN 支持矩阵 |
| 2026-07-18 | RF-07 产品化裁决 | 维护者裁决 `Native Only`(recovery plan 默认):Native 永久默认、零 PydanticAI 依赖;实验 Runtime 休眠可删;`Continue Experimental` 因缺真实 benchmark 与 Desktop 证据未启用;见 `docs/architecture/pydanticai-runtime-adoption-decision.md`(`Accepted`) |

## 4. 治理文档清单与状态

| 文档 | 状态 |
| --- | --- |
| `docs/architecture/pydanticai-runtime-development-plan.md` | `Approved`(2026-07-17) |
| `docs/architecture/ADR-001-agent-runtime.md` | `Accepted`(2026-07-17) |
| `docs/architecture/pydanticai-runtime-recovery-plan.md` | `Accepted`(2026-07-18;RF-00～RF-07 全部完成) |
| `docs/architecture/pydanticai-runtime-adoption-decision.md` | `Accepted`(2026-07-18;RF-07 裁决 `Native Only`) |
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
| 2026-07-18 | RF-01 合入(PR #21):可选依赖安装态 CI 矩阵(阻断门 `pydanticai-installed`)+ 模块级 skip 守卫;关闭 AR-RF-09;AR-PY-05 -> Partial |
| 2026-07-18 | RF-02 合入(PR #22):运行中 `ExecutionHandle`(`start()`)+ 深层冻结 `ExecutionContext`;关闭 AR-RF-01/02;AR-PY-01 -> Done |
| 2026-07-18 | RF-03 合入(PR #23):Native 统一经 `BoundToolSession` + deadline 绝对单调化;关闭 AR-RF-03;AR-PY-02 -> Done |
| 2026-07-18 | RF-04 合入(PR #25;changelog PR #27):单一分类器统一全入口终态 write fence 与生命周期;关闭 AR-RF-07;AR-PY-03 -> Done |
| 2026-07-18 | RF-05 合入(PR #28):PydanticAI Single RUN 真实模型桥(工具 schema 下发/ToolCall/ToolReturn/reasoning/provider trace 往返/prompt 复用/usage 修字段/deadline/cancel fence);CHAT/RESEARCH -> `unsupported_capability`;关闭 AR-RF-04/05/06/10/11;AR-PY-04 -> Experimental(桥完成,待 RF-06) |
| 2026-07-18 | RF-06a 合入(PR #32):离线 cross-runtime conformance 双跑(Single RUN 8 等价 + 3 有意差异 ADR-001 D5 + 非 RUN unsupported);36 fixture 只读;含 review 强化(终态精确匹配) |
| 2026-07-18 | RF-06b 合入(PR #33):实验 Runtime 失败面泄漏扫描(secret/URL/token 脱敏)+ RF-07 决策证据卷宗(`Draft`);关闭 AR-RF-08 离线部分;AR-PY-05 -> Done |
| 2026-07-18 | RF-07 裁决(本 PR):维护者裁决 `Native Only`;决策报告 `Draft` -> `Accepted`;AR-PY-06 -> Resolved(Native Only);RF-00～RF-07 修复计划收尾 |
