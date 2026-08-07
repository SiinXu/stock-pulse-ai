# Agent 可观测性 L0（结构化运行事件）

面向 Issue #222 的 L0 交付：为 Agent 执行路径提供**轻量、默认可开**的结构化事件与 trace/span 关联，并复用既有运行诊断 / 运行流存储与展示，而不是另建完整 metrics 平台。

## 范围

- 事件类型：`agent.phase_start/end`、`agent.tool_start/end`、`agent.model_start/end`、`agent.decision`
- 每个事件携带 `trace_id`、`span_id`、可选 `parent_span_id`、`duration_ms`、脱敏 `attrs`
- 默认只记录轻量元数据；深度 payload（工具参数/结果预览）由 `AGENT_OBSERVABILITY_DEEP_PAYLOAD` 控制，默认关闭
- 事件写入 `RunDiagnosticContext.agent_events`，并 fail-open 镜像到 run-flow `flow_event`
- Web 继续使用既有运行流面板；事件流与节点详情展示耗时与工具序列

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

## 相关

- [运行诊断 Phase 3](run-diagnostics-p3.md)
- English: [agent-observability_EN.md](agent-observability_EN.md)
