# MCP Server 集成说明

状态：独立可选进程，默认关闭

相关：[#244](https://github.com/SiinXu/stock-pulse-ai/issues/244)；[#138](https://github.com/SiinXu/stock-pulse-ai/issues/138) 仅作关联

English: [mcp-server-integration_EN.md](mcp-server-integration_EN.md)

StockPulse 固定使用官方 Python MCP SDK `mcp==2.0.0`，兼容线覆盖 MCP `2026-07-28` 以及由 SDK 协商的更早修订。权威资料：[MCP 2026-07-28 规范](https://modelcontextprotocol.io/specification/2026-07-28)、[官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk)。

MCP 只是既有 service 的薄适配层，`server.py`、`main.py --serve`、Web 和 Desktop 都不会自动启动它。

## 传输与生命周期

| 配置值 | 标准传输 | 鉴权 | 状态边界 |
| --- | --- | --- | --- |
| `stdio` | SDK stdio JSON-RPC | 本机进程边界 + 显式 `MCP_STDIO_SCOPES` | 每个子进程独立生命周期；stdout 只写协议，日志走 stderr |
| `streamable-http`（`http` 是显式别名） | `/mcp` 上的标准 Streamable HTTP（含 JSON/SSE 协商） | 必须使用被摘要 pin 的管理员 Bearer 会话 | SDK 管理 session ID、初始化闸门、版本协商、取消与 DELETE 关闭 |

初始化前调用、错误协议转换、缺失/错误的 HTTP 协议头和过期 session 均由官方 SDK 拒绝。这里不再提供自定义 JSON POST，也不宣称实现历史 HTTP+SSE。

## 能力、scope 与严格输入

| Scope | 工具 | 边界 |
| --- | --- | --- |
| `market.read` | `get_realtime_quote`、`get_stock_history` | 单个有界标识；仅 daily；1–3650 天 |
| `history.read` | `list_analysis_history`、`get_analysis_detail`、`get_analysis_report`、`get_analysis_status` | 严格日期、分页/结果上限、有界 ID |
| `portfolio.read` | `list_portfolio_accounts`、`get_portfolio_snapshot` | 只读；`fifo`/`avg`；实时行情必须传真实布尔值 |
| `analysis.trigger` | `trigger_analysis` | 仅异步提交；全局提交锁、标的上限、独立速率预算 |

`tools/list` 只返回 principal scope 允许的工具。所有发布的 input schema 都由严格 Pydantic 模型执行；额外字段、字符串布尔值、非法枚举/日期/范围、重复标的以及同步分析都会在调用 service 前被拒绝。

以下管理面或持久写入能力明确不注册：系统配置、Provider/API 密钥、密码/会话管理、安全审计管理、插件加载、自选股写入、组合成交/资金/公司行动，以及内部 Agent ToolSurface 注册表。

## 启动配置

显式填写的非法布尔值、整数、transport、scope、host、URL 和边界都会令启动失败，不会静默 clamp 或切换 transport。

### stdio

```bash
MCP_SERVER_ENABLED=true \
MCP_SERVER_TRANSPORT=stdio \
MCP_STDIO_SCOPES=market.read,history.read \
MCP_STDIO_PRINCIPAL=local-operator \
python -m src.mcp_server
```

客户端示例：

```json
{
  "mcpServers": {
    "stockpulse": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "env": {
        "MCP_SERVER_ENABLED": "true",
        "MCP_SERVER_TRANSPORT": "stdio",
        "MCP_STDIO_SCOPES": "market.read,history.read"
      }
    }
  }
}
```

能启动该命令的进程将获得配置的 scope。本机用户不是同等信任时，应使用最小 scope 和独立 OS 账号。

### Streamable HTTP

HTTP 不把 loopback 当作授权。必须同时启用 `ADMIN_AUTH_ENABLED=true`，通过 `Authorization: Bearer ...` 提交有效管理员 session，配置显式 scope，并用 SHA-256 摘要 pin 唯一允许进入 MCP audience 的 session。

```bash
# SESSION 必须经正常 /api/v1/auth/login 获得；不要把原文写进 shell history。
printf '%s' "$SESSION" | shasum -a 256

ADMIN_AUTH_ENABLED=true \
MCP_SERVER_ENABLED=true \
MCP_SERVER_TRANSPORT=streamable-http \
MCP_SERVER_HOST=127.0.0.1 \
MCP_SERVER_PORT=8765 \
MCP_HTTP_SCOPES=market.read,history.read \
MCP_HTTP_SESSION_TOKEN_SHA256='<64 位摘要>' \
MCP_HTTP_RESOURCE=http://127.0.0.1:8765/mcp \
python -m src.mcp_server
```

Bearer 仍是管理员凭据。摘要 pin 让 MCP 只接受一个明确凭据，并避免在环境变量中保存 token 原文；它不会把单管理员 session 变成多租户凭据。轮换时创建新 session、替换摘要并重启 MCP；改密或轮换 session secret 会沿用现有鉴权语义撤销它。

## HTTP 与资源边界

| 控制 | 默认 | 配置 |
| --- | --- | --- |
| Trusted Host | loopback host pattern | `MCP_HTTP_ALLOWED_HOSTS` |
| Trusted Origin | loopback HTTP origin | `MCP_HTTP_ALLOWED_ORIGINS` |
| Body | 仅 JSON，1,000,000 bytes | `MCP_HTTP_MAX_BODY_BYTES` |
| Header | 32,768 bytes 未完整事件上限 | `MCP_HTTP_MAX_HEADER_BYTES` |
| Body 读取 | 每个 body chunk 10 秒 | `MCP_HTTP_READ_TIMEOUT_SECONDS` |
| 连接 / backlog | 32 / 16 | `MCP_HTTP_MAX_CONNECTIONS`、`MCP_HTTP_BACKLOG` |
| Keep-alive | 5 秒 | `MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS` |
| 工具并发 | 8 个归属明确的 worker | `MCP_MAX_CONCURRENT_TOOLS` |
| Principal/tool 速率 | 60/分钟 | `MCP_RATE_LIMIT_PER_MINUTE` |
| 分析速率 | 2/分钟 | `MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE` |
| 单次分析成本 | 5 个标的 | `MCP_ANALYSIS_MAX_STOCKS` |

每个 HTTP 请求都检查 `Host`；带 `Origin` 时必须命中 allowlist。非法 Origin 返回 403、非法 Host 返回 421、非 JSON POST 返回 400、不兼容 Accept 返回 406，且均在工具分发前完成。浏览器跨域 preflight 不是支持的集成方式。

非 loopback 部署必须配置精确的代理 Host/Origin，保持 `ALLOW_INSECURE_PUBLIC_BIND=false`，在可信反向代理终止 HTTPS；代理应删除客户端伪造的 forwarding header、保留 `Authorization`、限制来源网络，并设置不宽于 MCP 进程的 header/body/读取超时。不得通过明文公网链路发布 `/mcp`。

## 审计与失败语义

适配层使用耐久 `SecurityAuditService`，审计存储不可用时 fail-closed。它以有界 actor/action/target/correlation 记录：

- HTTP 鉴权成功/拒绝；
- 受保护的工具发现；
- 每次工具 attempt 及 success/accepted/denied/rejected/failure；
- scope 不足、严格校验、速率/容量拒绝、分析 busy、取消和内部失败；
- `AnalysisApiService` 内已有的分析提交 attempt/completion。

参数、Bearer、组合数值、报告正文和密钥不会进入审计 target ID 或 metadata。限流是单进程、单 worker 设计，不是分布式 quota；多副本部署需要外部限流/审计架构，不在本交付范围。

MCP 不同步执行高成本分析。调用只在全局分析锁下完成有界的任务队列提交，并返回供 `get_analysis_status` 查询的 task ID；后续分析归既有任务队列所有。客户端取消时不会 abandon 正在运行的 service call，容量与所有权会保留到该调用结束。

## 威胁映射

| ID | 威胁 | 控制 |
| --- | --- | --- |
| `MCP-01` | 跨站调用 localhost / DNS rebinding | Origin + Host + JSON/Accept 严格校验 |
| `MCP-02` | session 泄露或权限过宽 | 既有 session 校验、SHA-256 audience pin、显式 scope、过期/撤销指引 |
| `MCP-03` | 工具/成本耗尽 | principal/tool 速率、分析速率/标的上限、有界连接/backlog/并发 |
| `MCP-04` | 类型 coercion 扩大联网或成本 | 严格 typed projection、拒绝额外字段 |
| `MCP-05` | timeout/cancel 后出现无归属写入 | 仅异步队列提交；无 executor timeout；service 不被 abandon |
| `MCP-06` | 受保护访问不可追溯 | 接受边界耐久 fail-closed 审计 |

## 验证、限制与回滚

仓库测试使用官方 client 连接真实 stdio 子进程和真实 Streamable HTTP server，并覆盖版本协商/工具发现、恶意 Origin、rebind Host、明文 content type、不兼容 Accept、preflight、未鉴权、scope 不足、速率、审计不可用、严格 schema 和初始化前调用。

本功能仍属于单管理员部署，不是租户隔离。HTTP Bearer 兼容凭据不是 OAuth authorization server，因此进程不会发布虚假的 OAuth metadata。本次不包含管理面、webhook/connector、多节点限流或主进程自动启动，所以只关联、不关闭 #244/#138。

回滚：停止独立进程并删除或设 `MCP_SERVER_ENABLED=false`；若 Bearer 可能泄露，轮换管理员 session secret。Revert MCP 适配层与依赖锁即可移除功能，不涉及 MCP 数据迁移。
