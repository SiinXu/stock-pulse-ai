# 只读研究 API

[中文](research-api.md) | [English](research-api_EN.md)

## 目的

Issue **#1143** 提供紧凑、需鉴权的 **只读** REST 面，暴露 **分层分析结论**，
让嵌入/门户客户端仅凭 API 即可渲染结论与缺口，而无需拉取完整历史
`raw_result`。

该能力属于 epic [#1127](https://github.com/SiinXu/stock-pulse-ai/issues/1127)
产品工作流 G（只读研究 API）。它复用与 MCP 只读工具面相同的治理基座：会话鉴权、
fail-closed 安全审计、每主体滑动窗口限流；**不**另开无治理监听端口。

## 默认关闭

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `RESEARCH_API_ENABLED` | `false` | 总开关；关闭时路由返回 `404 not_found` |
| `RESEARCH_API_RATE_LIMIT_PER_MINUTE` | `60` | 每主体、每动作 60 秒窗口预算 |

也可在 Web 设置 → 系统 中编辑（帮助键 `settings.system.research_api`）。

## 端点

基路径：`/api/v1/research`（仅主 FastAPI 应用）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/conclusions/{record_id}` | 按历史主键返回模式过滤后的分层结论 |
| `GET` | `/conclusions?stock_code=` | 返回某股票最新历史行 |

### 查询参数

| 名称 | 取值 | 默认 |
| --- | --- | --- |
| `mode` | `brief` \| `standard` \| `research` | `standard` |
| `language` | 可选 `zh` / `en` / `ko` | 记录语言 |
| `stock_code` | 最新接口必填 | — |

### 响应契约（`research-conclusion-v1`）

- `mode` — 有效密度
- `metadata` — `record_id`、`stock_code`、`as_of`、`confidence_level`、
  `evidence_counts`、`evidence_refs`（去重后的 `source_id`）
- `conclusion` — 一句话结论、动作、风险、**缺口**、可选按模式裁剪的
  `report_strata`、截断说明
- `disclaimer` — 有 strata 时的非投资建议声明

**不包含：** 密钥、完整 `raw_result`、管理面字段，以及任何写方法。

### 模式密度

复用 `src/services/report_mode.py` 限额：

| 模式 | Strata | 用途 |
| --- | --- | --- |
| `brief` | 省略（`null`） | 推送/嵌入摘要；仍返回有界 gaps |
| `standard` | compact 上限 | 默认门户卡片 |
| `research` | full 上限 + 更长摘要字段 | 深度研究视图 |

## 治理

| 关注点 | 行为 |
| --- | --- |
| 鉴权 | 与 `/api/v1/*` 相同的会话 Cookie 中间件（`ADMIN_AUTH_ENABLED`） |
| 审计 | `event_type=research_api.request`；attempt + completion；存储失败 → `503 security_audit_unavailable` |
| 限流 | `SlidingWindowRateLimiter`，键为 principal + action |
| 端口 | 仅主 API — **不**为本能力另开进程 |

## 范围外

- 能力注册表登记（#1185 等）
- Agent 深度研究 `POST /api/v1/agent/research`（另一产品路径）
- 可导出审计包 / 证据链（#127）
- 本面上的写方法或触发分析

## 相关文档

- 报告分层契约：[report-strata-contract.md](report-strata-contract.md)
- 报告模式：`src/services/report_mode.py`
- MCP 治理参考：[mcp-server-integration.md](mcp-server-integration.md)（若有中文版）
