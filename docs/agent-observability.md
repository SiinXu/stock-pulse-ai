# Agent 可观测性 L0（结构化运行事件）

面向 Issue #222 的 L0 交付：为 Agent 执行路径提供**轻量、默认可开**的结构化事件与 trace/span 关联，并复用既有运行诊断 / 运行流存储与展示，而不是另建完整 metrics 平台。

## 范围

- 事件类型：`agent.phase_start/end`、`agent.tool_start/end`、`agent.model_start/end`、`agent.decision`
- 每个事件携带 `trace_id`、`span_id`、可选 `parent_span_id`、`duration_ms`、脱敏 `attrs`
- 默认只记录轻量元数据；深度 payload（工具参数/结果预览）由 `AGENT_OBSERVABILITY_DEEP_PAYLOAD` 控制，默认关闭
- 事件写入 `RunDiagnosticContext.agent_events`，并 fail-open 镜像到 run-flow `flow_event`
- Web 继续使用既有运行流面板；事件流与节点详情展示耗时与工具序列，并提供 Agent 决策事件回放游标

## 配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `AGENT_OBSERVABILITY_ENABLED` | `true` | 开关轻量事件 |
| `AGENT_OBSERVABILITY_DEEP_PAYLOAD` | `false` | 是否记录脱敏后的深度 payload |

## 隐私

- 所有 payload 走 `sanitize_agent_event_payload` / 诊断脱敏 helper
- 禁止 prompt、messages、API key、token、authorization 等敏感字段落地
- 深度模式仍会 redact 敏感 key 与文本

## 开销

- 默认路径只追加小字典并可选写 flow sink；单 run 最多保留 200 条 agent 事件
- 无诊断上下文时 emit 为 no-op；记录失败 fail-open，不改变 Agent 控制流

## API

不新增独立 endpoint。历史与任务运行流仍使用：

- `GET /api/v1/analysis/tasks/{task_id}/flow`
- `GET /api/v1/history/{record_id}/flow`

agent 事件会出现在 `events[]` 中，并在 diagnostics 快照的 `agent_events` 字段中持久化。

## Agent 回放 V1

任务与历史记录的既有运行流面板按 `sequence` 展示 Agent 事件，并提供上一条/下一条游标。每条回放明细包含事件 schema 版本、trace/span 关联、状态以及后端已脱敏的 `attrs`；仅在显式开启深度 payload 且后端完成脱敏后展示 `payload`。

完整性状态会校验：

- `sequence` 是否缺失、重复或存在间隙
- 事件 schema 是否为当前支持的 v1
- 事件 `trace_id` 是否与运行流快照一致
- 捕获计数是否满足 `original = returned + dropped`，以及是否发生 200 条上限截断
- 回放明细是否包含被拒绝的 NaN 或正负无穷数

`完整` 表示上述证据一致；`部分` 表示捕获计数不可用、事件缺失或因上限被截断；`无效` 表示版本、序列、trace、明细或计数互相矛盾。回放只读取现有 `/flow` 投影，不新增存储或旁路接口。

V1 不包含两个运行的比较、可导出调试包、原始 prompt/推理内容或独立的上下文/内存浏览器。这些仍由 Issue #254 跟踪。

## 相关

- [运行诊断 Phase 3](run-diagnostics-p3.md)
- English: [agent-observability_EN.md](agent-observability_EN.md)
