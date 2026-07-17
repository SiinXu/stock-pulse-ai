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
| AR-PY-02 | BoundToolSession | Blocked | 前置:AR-PY-01 合入 |
| AR-PY-03 | Lifecycle / typed events / 真实取消 | Blocked | 前置:AR-PY-02 合入 |
| AR-PY-04 | PydanticAI 隔离 POC(Spike + Adapter) | Blocked | 前置:AR-PY-03 合入 + 方案 A/B 裁决(审批点 3/4) |
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
