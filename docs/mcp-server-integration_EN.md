# MCP Server Integration

Status: optional, default-off dedicated process

Related: [#244](https://github.com/SiinXu/stock-pulse-ai/issues/244); [#138](https://github.com/SiinXu/stock-pulse-ai/issues/138) remains reference-only

Chinese: [mcp-server-integration.md](mcp-server-integration.md)

StockPulse uses the official Python MCP SDK `mcp==2.0.0`. The selected compatibility line implements MCP `2026-07-28` and earlier negotiated revisions. Authoritative references: [MCP 2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28) and [official Python SDK](https://github.com/modelcontextprotocol/python-sdk).

The MCP process is a thin adapter over existing services. It is never started by `server.py`, `main.py --serve`, Web, or Desktop.

## Transports and lifecycle

| Config value | Standard transport | Authentication | Connection state |
| --- | --- | --- | --- |
| `stdio` | SDK stdio JSON-RPC | Local process boundary plus explicit `MCP_STDIO_SCOPES` | One SDK lifecycle per spawned process; stdout is protocol-only and logs use stderr |
| `streamable-http` (`http` is an explicit alias) | Standard Streamable HTTP at `/mcp`, including JSON/SSE negotiation | Required pinned administrator bearer session | SDK-managed session ID, initialization gate, version negotiation, cancellation, and DELETE shutdown |

Calls before initialization, invalid protocol transitions, missing/wrong Streamable HTTP headers, and stale sessions are rejected by the SDK. The HTTP implementation is not the historical custom JSON POST endpoint and does not advertise legacy HTTP+SSE.

## Capability and scope inventory

| Scope | Tools | Boundary |
| --- | --- | --- |
| `market.read` | `get_realtime_quote`, `get_stock_history` | One bounded identifier; daily history only; 1–3650 days |
| `history.read` | `list_analysis_history`, `get_analysis_detail`, `get_analysis_report`, `get_analysis_status` | Strict dates, page/result caps, bounded IDs |
| `portfolio.read` | `list_portfolio_accounts`, `get_portfolio_snapshot` | Read-only; `fifo`/`avg`; realtime quotes require an explicit boolean |
| `analysis.trigger` | `trigger_analysis` | Async submission only, global submission lock, stock cap, and separate rate budget |

`tools/list` is filtered to the principal's scopes. Every advertised input schema is enforced with strict Pydantic models: extra fields, string booleans, invalid enums/dates/ranges, duplicate stocks, and synchronous analysis are rejected before a service call.

The following management-plane or durable mutation capabilities are intentionally not registered: system configuration, provider/API secrets, password/session administration, security-audit administration, plugin loading, watchlist writes, portfolio trades/cash/corporate actions, and the internal Agent ToolSurface registry.

## Required configuration

All explicit invalid booleans, integers, transports, scopes, hosts, URLs, and bounds fail startup; values are never silently clamped or switched to another transport.

### stdio

```bash
MCP_SERVER_ENABLED=true \
MCP_SERVER_TRANSPORT=stdio \
MCP_STDIO_SCOPES=market.read,history.read \
MCP_STDIO_PRINCIPAL=local-operator \
python -m src.mcp_server
```

Example client entry:

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

Any process that can spawn the command receives the configured scopes. Use the smallest scope set and a dedicated OS account where local users are not equally trusted.

### Streamable HTTP

HTTP never treats loopback as authorization. It requires `ADMIN_AUTH_ENABLED=true`, a valid administrator session in `Authorization: Bearer ...`, explicit scopes, and a SHA-256 pin for the one session accepted by this MCP audience.

```bash
# Obtain SESSION through the normal /api/v1/auth/login flow. Do not put it in shell history.
printf '%s' "$SESSION" | shasum -a 256

ADMIN_AUTH_ENABLED=true \
MCP_SERVER_ENABLED=true \
MCP_SERVER_TRANSPORT=streamable-http \
MCP_SERVER_HOST=127.0.0.1 \
MCP_SERVER_PORT=8765 \
MCP_HTTP_SCOPES=market.read,history.read \
MCP_HTTP_SESSION_TOKEN_SHA256='<64-character digest>' \
MCP_HTTP_RESOURCE=http://127.0.0.1:8765/mcp \
python -m src.mcp_server
```

The bearer session remains an administrator credential. The digest pin gives the MCP process an explicit accepted credential/audience and enables rotation without storing the raw token in its environment; it does not make the underlying browser session usable by multiple tenants. Rotate by creating a new session, replacing the digest, and restarting MCP. Password changes or session-secret rotation revoke it through the existing auth model.

## HTTP security and resource bounds

| Control | Default | Configuration |
| --- | --- | --- |
| Trusted Host | loopback host patterns | `MCP_HTTP_ALLOWED_HOSTS` |
| Trusted Origin | loopback HTTP origins | `MCP_HTTP_ALLOWED_ORIGINS` |
| Body | JSON only, 1,000,000 bytes | `MCP_HTTP_MAX_BODY_BYTES` |
| Headers | 32,768-byte incomplete-event cap | `MCP_HTTP_MAX_HEADER_BYTES` |
| Body read | 10 seconds per body chunk | `MCP_HTTP_READ_TIMEOUT_SECONDS` |
| Connections / backlog | 32 / 16 | `MCP_HTTP_MAX_CONNECTIONS`, `MCP_HTTP_BACKLOG` |
| Keep-alive | 5 seconds | `MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS` |
| Tool concurrency | 8 owned workers | `MCP_MAX_CONCURRENT_TOOLS` |
| Principal/tool rate | 60/minute | `MCP_RATE_LIMIT_PER_MINUTE` |
| Analysis rate | 2/minute | `MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE` |
| Analysis stock cost | 5 stocks/request | `MCP_ANALYSIS_MAX_STOCKS` |

Every HTTP request validates `Host`; supplied `Origin` must match the allowlist. Invalid Origin is rejected with 403, invalid Host with 421, non-JSON POST with 400, and incompatible `Accept` with 406 before tool dispatch. Browser preflight is not enabled as a cross-origin integration path.

For non-loopback deployment, list exact proxy-facing hosts/origins, keep `ALLOW_INSECURE_PUBLIC_BIND=false`, and terminate HTTPS at a trusted reverse proxy. Strip client-supplied forwarding headers, preserve `Authorization`, restrict source networks, set request/header/body timeouts at least as strict as the process, and never publish `/mcp` over cleartext Internet links.

## Audit and failure behavior

The adapter uses the durable `SecurityAuditService` and fails closed if the audit store is unavailable. It records bounded actor/action/target/correlation data for:

- HTTP authentication success/denial;
- protected tool discovery;
- each tool attempt and success/accepted/denied/rejected/failure result;
- insufficient scope, strict validation, rate/capacity rejection, busy analysis submission, cancellation, and internal failures;
- analysis submission's existing attempt/completion audit inside `AnalysisApiService`.

Arguments, bearer tokens, portfolio values, report bodies, and secrets are never audit target IDs or metadata. Per-principal rate state is in-process and intentionally single-worker; it is not a distributed quota. Multi-replica HTTP deployment requires an external limiter/audit architecture and is outside this delivery.

Costly analysis is never executed synchronously by MCP. The call owns the bounded queue-submission operation under the global analysis lock and returns task identifiers for `get_analysis_status`; ongoing analysis belongs to the existing task queue. Worker calls are not abandoned on client cancellation, so capacity/ownership is retained until the service call returns.

## Threat mapping

| ID | Threat | Control |
| --- | --- | --- |
| `MCP-01` | Cross-origin localhost invocation / DNS rebinding | Strict Origin + Host + JSON/Accept validation |
| `MCP-02` | Stolen or over-broad credential | Existing session verification, SHA-256 audience pin, explicit scopes, expiry/revocation guidance |
| `MCP-03` | Tool/cost exhaustion | Per-principal/tool rate, analysis rate/stock cap, bounded connections/backlog/concurrency |
| `MCP-04` | Schema coercion broadens network/cost behavior | Strict typed projections and extra-field rejection |
| `MCP-05` | Unowned mutation after timeout/cancel | Async task submission only; no executor timeout; non-abandoned service ownership |
| `MCP-06` | Untraceable protected access | Durable fail-closed acceptance-boundary audit |

## Verification and residual limits

Repository tests use the official client against a real stdio subprocess and a real Streamable HTTP server. They cover negotiation/listing plus malicious Origin, rebinding Host, plaintext content type, incompatible Accept, preflight, unauthenticated access, missing scopes, rate limits, audit outage, strict schemas, and pre-initialize calls.

This remains the repository's single-administrator model, not tenant isolation. The HTTP bearer compatibility credential is not an OAuth authorization server and the process does not publish false OAuth metadata. No management-plane capability, webhook/connector implementation, multi-node limiter, or automatic main-process startup is included; therefore #244 and #138 are referenced rather than closed.

## Rollback

Stop the dedicated process and unset or set `MCP_SERVER_ENABLED=false`. Rotate the admin session secret if a bearer may have leaked. Reverting the MCP adapter and dependency lock removes the feature; there is no MCP data migration.
