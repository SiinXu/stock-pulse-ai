# 推理轨迹导出

本文定义多 Agent 推理轨迹导出接口（Issue #135 / T03）。导出器只读取分析历史中已经持久化的数据，不补造未记录的推理内容，也不修改 Agent 核心记录行为。

英文版本见 [reasoning-trace-export_EN.md](reasoning-trace-export_EN.md)。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `REASONING_TRACE_EXPORT_ENABLED` | `false` | 导出 API 与服务总开关 |
| `REASONING_TRACE_EXPORT_MAX_CHARS` | `500000` | 完整响应字符预算；有效范围 `10000`–`2000000`，越界时钳制 |

关闭开关时，`GET /api/v1/reasoning-trace/{record_id}` 返回 `404 reasoning_trace_export_disabled`，不会读取或导出历史内容。

## API 与身份语义

```http
GET /api/v1/reasoning-trace/{record_id}?format=json|markdown&include_markdown=false
```

- 必须启用管理员认证并提供有效会话；认证关闭时拒绝导出。
- 数字 `record_id` 按历史主键解析；非数字值按 `query_id` 选择最新记录。
- 包内分别返回不可变的历史 `record_id`、可能重复的 `query_id`、诊断 `trace_id`、稳定 `run_id`、查询键和查询模式。
- `format=json` 返回严格 JSON；`include_markdown=true` 时 Markdown 计入同一完整 JSON 响应预算。
- `format=markdown` 返回 `text/markdown`；存储或模型生成的内容只放入缩进代码块，不会被渲染为活动链接、图片或 HTML。
- 成功响应带 `Cache-Control: private, no-store`、`Pragma: no-cache`、`Content-Disposition: attachment` 和 `X-Content-Type-Options: nosniff`。
- 每次通过认证的导出在返回内容前写入持久化安全审计 attempt/completion；审计不可用时失败关闭并返回 `503`。

OpenAPI 同时声明 `application/json` 与 `text/markdown` 的 200 响应，以及 400/401/403/404/422/500/503 错误。

## `reasoning-trace-v1` 合同

响应使用严格的有类型模型：`schema_version` 固定为 `reasoning-trace-v1`，未知字段被拒绝，字符串与列表有界，所有浮点数必须有限。持久化数据中的 NaN、正负无穷、未知对象和畸形条目不会直接进入响应。

主要区段：

- `run`：`record_id`、`query_id`、`trace_id`、`run_id`、标的、市场、模型、时间和非敏感配置指纹。
- `agents`：有界的角色、输入摘要、工具调用、意见和事件摘要。
- `synthesis`：分歧、共识和最终结论的有界投影；不复制任意嵌套的原始模型对象。
- `data_sources`：provider、LLM、pipeline stage 和数据质量的有界投影。
- `coverage.sources`：逐来源的 `supported`、`present`、`absent`、`source_truncated`、`export_truncated`、原始/返回/丢弃数量与原因。
- `truncation`：来源保留、投影上限、畸形输入或体积预算导致的每一项损失。

运行时诊断保留最近 200 个 Agent 事件，并持久化原始数、返回数和丢弃数。导出器对 Agent 事件、每 Agent 工具调用、provider/LLM/stage 列表分别应用有界投影；任何上限都必须显式反映在 coverage 与 truncation 中。

体积预算在投影、脱敏、严格序列化和可选 Markdown 嵌入之后执行。每个返回路径都会再次检查完整响应；若可选证据无法容纳，则返回确定性的最小有类型包，不会仅设置标记后超出预算。

## 安全边界

导出器复用 `src.utils.sanitize.redact_sensitive_data`，并在该高风险边界启用 opaque token 处理。明确支持脱敏：

- 已标识的 API key、密码、Authorization/Bearer、cookie 和 token 字段；
- Bearer/JWT/长 opaque token 模式；
- 带凭据的 URL；
- POSIX 常见本地根路径、Windows drive 路径、UNC 路径以及 `~/`、`./`、`../` 相对路径。

模式扫描不能证明任意自然语言中的所有未知秘密都可识别，因此本文不承诺“任何秘密永不导出”。导出内容仍可能包含业务敏感上下文；必须限制管理员访问、安全存储，并按敏感数据处理下载文件。已生成文件不由服务保存或回收，回滚或停用功能不会删除外部副本。

## 当前覆盖与缺口

存在时可导出：历史运行元信息、`diagnostics.agent_events`、provider/LLM/pipeline stage 运行摘要、dashboard 合成摘要和 context-pack 数据质量摘要。

当前 Agent 核心未完整持久化，因此仍不包含：完整 system/user prompt、未启用 deep payload 时的工具参数、chat provider thinking block、临时 SSE 事件和原始 provider API 响应。Issue #135 保持开放；Web Settings 与完整捕获也不在 T03 中交付。

## 回滚

保持 `REASONING_TRACE_EXPORT_ENABLED=false` 并重启，或 revert 本变更。服务不保存导出文件；已下载或转存的副本需由操作人员单独删除。
