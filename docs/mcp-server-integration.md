# MCP Server 集成说明

状态：可选适配层（默认 **关闭**）  
相关：Issue [#244](https://github.com/SiinXu/stock-pulse-ai/issues/244)，关联 [#138](https://github.com/SiinXu/stock-pulse-ai/issues/138)  
English: [mcp-server-integration_EN.md](mcp-server-integration_EN.md)

本文说明如何通过 **Model Context Protocol (MCP)** 适配层，把 StockPulse **经过筛选** 的核心能力暴露给外部 agent（IDE、Claude Desktop、自定义 MCP 客户端）。

## 设计原则

1. **只做薄适配** — 工具调用既有 service（`StockService`、`HistoryService`、`PortfolioService`、`AnalysisApiService`），不在 MCP 层重写业务逻辑。
2. **默认关闭、零影响** — `MCP_SERVER_ENABLED` 默认为 false。主 API 进程（`server.py` / `main.py --serve`）**不会**自动启动 MCP；未显式运行前不会监听任何端口。
3. **复用管理员会话鉴权** — `ADMIN_AUTH_ENABLED=true` 时，MCP 要求有效管理员会话（与 HTTP Cookie 会话相同的 `verify_session`），不另建弱鉴权。
4. **管理面不开放** — 配置修改、密钥管理、密码/会话管理、安全审计、插件加载、自选股写入、组合成交写入均 **不是** MCP 工具。
5. **MCP tool ≠ Agent tool** — 不使用 `src.agent.tools.registry`（Agent ToolSurface）。

## 能力清单

### 已暴露

| 能力 | MCP 工具 | 风险 | 理由 |
| --- | --- | --- | --- |
| 实时行情 | `get_realtime_quote` | 只读 | 经 `StockService` |
| 历史 K 线 | `get_stock_history` | 只读 | 经 `StockService` |
| 分析历史列表 | `list_analysis_history` | 只读 | 经 `HistoryService` |
| 分析详情 | `get_analysis_detail` | 只读 | 经 `HistoryService` |
| Markdown 报告 | `get_analysis_report` | 只读 | 经 `HistoryService` |
| 组合账户列表 | `list_portfolio_accounts` | 只读 | 经 `PortfolioService` |
| 组合快照 | `get_portfolio_snapshot` | 只读 | 经 `PortfolioService`（默认不拉实时价） |
| 分析任务状态 | `get_analysis_status` | 只读 | 任务队列状态 |
| 触发分析 | `trigger_analysis` | 写/有成本 | 经 `AnalysisApiService`，全局分析锁 + 标的上限 + 默认异步 |

### 明确不暴露

| 能力 | 理由 |
| --- | --- |
| 系统配置读写 | 管理面；可改鉴权、数据源与密钥相关项 |
| 密码 / 会话管理 | 仅走专用鉴权 API；MCP 只复用会话，不管理凭据 |
| API Key / 密钥管理 | 不得被外部 agent 发现或写入 |
| 安全审计管理 | 管理员运维面 |
| 插件加载/安装 | 进程级代码执行 |
| 自选股变更 | 持久化运维配置，避免 agent 静默改写 |
| 组合成交/资金写入 | 变更财务状态；V0 仅快照 |
| Agent 对话 / Agent ToolSurface | 独立注册表与信任模型 |

## 配置

见 `.env.example` 中 MCP 段。摘要：

| 变量 | 默认 | 含义 |
| --- | --- | --- |
| `MCP_SERVER_ENABLED` | `false` | 总开关 |
| `MCP_SERVER_TRANSPORT` | `stdio` | `stdio` 或 `http` |
| `MCP_SERVER_HOST` | `127.0.0.1` | HTTP 绑定地址 |
| `MCP_SERVER_PORT` | `8765` | HTTP 端口 |
| `MCP_SESSION_TOKEN` | 空 | 鉴权开启时的管理员会话值 |
| `MCP_ANALYSIS_MAX_STOCKS` | `5` | `trigger_analysis` 标的上限 |
| `MCP_ANALYSIS_TIMEOUT_SECONDS` | `120` | 高成本路径保留边界 |

## 启动

```bash
# stdio（IDE / Claude Desktop 常见）
MCP_SERVER_ENABLED=true python -m src.mcp_server

# HTTP（本机）
MCP_SERVER_ENABLED=true \
MCP_SERVER_TRANSPORT=http \
MCP_SERVER_HOST=127.0.0.1 \
MCP_SERVER_PORT=8765 \
python -m src.mcp_server
```

开启鉴权时：

```bash
ADMIN_AUTH_ENABLED=true \
MCP_SERVER_ENABLED=true \
MCP_SESSION_TOKEN='<通过 /api/v1/auth/login 获得的会话 Cookie 值>' \
python -m src.mcp_server
```

HTTP 也可传：

- `Authorization: Bearer <session>`
- `X-DSA-Session: <session>`
- `Cookie: dsa_session=<session>`

### HTTP 路径

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/health` 或 `/mcp/health` | 存活检查 |
| `POST` | `/mcp`、`/mcp/jsonrpc` 或 `/` | JSON-RPC 2.0 |

## 协议

支持方法：`initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`，以及扩展方法 `stockpulse/capabilities`（完整暴露清单）。

stdio 使用**换行分隔**的 JSON-RPC；HTTP POST 使用 JSON body。

## 安全

与 [安全基线](security-baseline.md) 对齐：

- 单管理员信任模型 — MCP **不是**多租户隔离。
- 非本机 HTTP 绑定复用 `enforce_http_bind_security`（无鉴权则 fail-closed，除非紧急 override）。
- 优先 `127.0.0.1`。即使开启鉴权，公网绑定仍高风险；TLS 应由反向代理终止。
- 立即回滚：设 `MCP_SERVER_ENABLED=false` 并停止 MCP 进程。

### 公网绑定风险提示

将 MCP HTTP 绑定到 `0.0.0.0` 或局域网地址，等于把工具调用面暴露到本机之外。若同时 `ADMIN_AUTH_ENABLED=false`，启动会 **fail-closed**（与主 API 一致）。开启鉴权后的公网绑定意味着持有有效管理员会话者可触发分析并读取组合/历史。请将会话令牌视为密钥。

## 集成点（Integration Point）

本交付自包含。可选后续接线（V0 不要求）：

- 在 Claude Desktop 等客户端配置 `mcpServers` 指向 `python -m src.mcp_server`。
- **不要**在没有产品决策前，把 MCP 自动挂到 `api/app.py` 生命周期。

## 回滚

1. `MCP_SERVER_ENABLED=false`（或删除）并停止 MCP 进程。
2. 或 revert 引入 `src/mcp_server/` 的 PR。
