# MCP Server Integration

Status: Optional adapter (default **off**)  
Related: Issue [#244](https://github.com/SiinXu/stock-pulse-ai/issues/244), related [#138](https://github.com/SiinXu/stock-pulse-ai/issues/138)  
Chinese: [mcp-server-integration.md](mcp-server-integration.md)

This document describes the **Model Context Protocol (MCP)** adapter that exposes a **curated** subset of StockPulse capabilities to external agents (IDE copilots, Claude Desktop, custom MCP clients).

## Design principles

1. **Thin adapter only** — tools call existing services (`StockService`, `HistoryService`, `PortfolioService`, `AnalysisApiService`). No parallel business logic.
2. **Default off, zero impact** — `MCP_SERVER_ENABLED` defaults to false. The main API process (`server.py` / `main.py --serve`) never starts MCP. No listen port until you run the dedicated process.
3. **Reuse admin session auth** — when `ADMIN_AUTH_ENABLED=true`, MCP requires a valid admin session (same model as the HTTP API cookie session via `verify_session`). No second auth system.
4. **Management plane stays closed** — configuration, secrets, password admin, security audit, plugins, watchlist mutation, and portfolio trade writes are **not** MCP tools.
5. **MCP tools ≠ Agent tools** — this surface does **not** use `src.agent.tools.registry` (Agent ToolSurface).

## Capability inventory

### Exposed

| Capability | MCP tool | Risk | Reason |
| --- | --- | --- | --- |
| Realtime quote | `get_realtime_quote` | read | Market lookup via `StockService` |
| History bars | `get_stock_history` | read | OHLCV via `StockService` |
| Analysis history list | `list_analysis_history` | read | Via `HistoryService` |
| Analysis detail | `get_analysis_detail` | read | Via `HistoryService` |
| Markdown report | `get_analysis_report` | read | Via `HistoryService` |
| Portfolio accounts | `list_portfolio_accounts` | read | Via `PortfolioService` |
| Portfolio snapshot | `get_portfolio_snapshot` | read | Via `PortfolioService` (realtime off by default) |
| Analysis task status | `get_analysis_status` | read | Task queue status |
| Trigger analysis | `trigger_analysis` | write / costly | Via `AnalysisApiService`, global analysis lock, max stocks, async by default |

### Not exposed (by design)

| Capability | Reason |
| --- | --- |
| System config read/write | Management plane; can change auth, providers, secrets |
| Auth password / session admin | Dedicated auth API only; MCP reuses sessions, never manages credentials |
| API key / secret management | Secrets must not be discoverable or writable via external agents |
| Security audit admin | Admin-only operational surface |
| Plugin load/install | Process-level code execution |
| Watchlist mutation | Durable operator config; avoid silent agent drift |
| Portfolio trade / cash writes | Mutates financial state; V0 is snapshot-only |
| Agent chat / Agent ToolSurface | Separate registry and trust model |

## Configuration

See `.env.example` (MCP section). Summary:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MCP_SERVER_ENABLED` | `false` | Master switch |
| `MCP_SERVER_TRANSPORT` | `stdio` | `stdio` or `http` |
| `MCP_SERVER_HOST` | `127.0.0.1` | HTTP bind host |
| `MCP_SERVER_PORT` | `8765` | HTTP bind port |
| `MCP_SESSION_TOKEN` | empty | Admin session cookie value when auth is enabled |
| `MCP_ANALYSIS_MAX_STOCKS` | `5` | Cap for `trigger_analysis` |
| `MCP_ANALYSIS_TIMEOUT_SECONDS` | `120` | Reserved bound for costly runs |

## Start

```bash
# stdio (typical for Claude Desktop / IDE)
MCP_SERVER_ENABLED=true python -m src.mcp_server

# HTTP (localhost)
MCP_SERVER_ENABLED=true \
MCP_SERVER_TRANSPORT=http \
MCP_SERVER_HOST=127.0.0.1 \
MCP_SERVER_PORT=8765 \
python -m src.mcp_server
```

With auth enabled:

```bash
ADMIN_AUTH_ENABLED=true \
MCP_SERVER_ENABLED=true \
MCP_SESSION_TOKEN='<session cookie value from /api/v1/auth/login>' \
python -m src.mcp_server
```

HTTP clients may also send:

- `Authorization: Bearer <session>`
- `X-DSA-Session: <session>`
- `Cookie: dsa_session=<session>`

### HTTP endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` or `/mcp/health` | Liveness |
| `POST` | `/mcp`, `/mcp/jsonrpc`, or `/` | JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`) |

## Protocol surface

Supported methods:

- `initialize`
- `notifications/initialized`
- `ping`
- `tools/list`
- `tools/call`
- `stockpulse/capabilities` (extension: full exposure inventory for operators/tests)

Framing: **newline-delimited JSON-RPC** on stdio; JSON body on HTTP POST.

## Security

Aligned with [Security baseline](security-baseline.md):

- Single-administrator trust model — MCP does not create multi-tenant isolation.
- Non-local HTTP binds reuse `enforce_http_bind_security` (auth required unless emergency override).
- Prefer `127.0.0.1`. Public bind is high risk even with auth; terminate TLS at a reverse proxy.
- Disabling MCP (`MCP_SERVER_ENABLED=false`) is the immediate rollback switch.

### Public bind risk notice

Binding MCP HTTP to `0.0.0.0` or a LAN interface exposes tool invocation beyond the local machine. Combined with `ADMIN_AUTH_ENABLED=false`, startup **fails closed** (same policy as the main API). Enabling public bind with auth still means any holder of a valid admin session can trigger analysis and read portfolio/history data. Treat session tokens as secrets.

## Integration Point

This delivery is self-contained. Optional future wiring (not required for V0):

- Document Claude Desktop `mcpServers` entry pointing at `python -m src.mcp_server`.
- Do **not** auto-start MCP from `api/app.py` without an explicit product decision.

## Rollback

1. Set `MCP_SERVER_ENABLED=false` (or unset) and stop the MCP process.
2. Or revert the PR that introduced `src/mcp_server/`.
