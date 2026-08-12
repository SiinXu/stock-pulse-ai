# Read-only research API

[中文](research-api.md) | [English](research-api_EN.md)

## Purpose

Issue **#1143** exposes a compact, authenticated **read-only** REST surface for
**stratified analysis conclusions** so embed/portal clients can render a
conclusion plus gaps without pulling full history `raw_result` payloads.

This surface is **product workstream G** of epic [#1127](https://github.com/SiinXu/stock-pulse-ai/issues/1127)
(read-only research API). It reuses the same governance base as the MCP
read-only tool surface: session authentication, fail-closed security audit, and
per-principal sliding-window rate limits. It does **not** open a second
ungoverned listener.

## Default off

| Variable | Default | Role |
| --- | --- | --- |
| `RESEARCH_API_ENABLED` | `false` | Master switch; disabled routes return `404 not_found` |
| `RESEARCH_API_RATE_LIMIT_PER_MINUTE` | `60` | Per-principal per-action budget (60s window) |

Also editable under Web Settings → System (help key `settings.system.research_api`).

## Endpoints

Base path: `/api/v1/research` (main FastAPI app only).

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/conclusions/{record_id}` | Mode-filtered conclusion for one analysis history primary key |
| `GET` | `/conclusions?stock_code=` | Latest history row for a stock code |

### Query parameters

| Name | Values | Default |
| --- | --- | --- |
| `mode` | `brief` \| `standard` \| `research` | `standard` |
| `language` | `zh` / `en` / `ko` (optional override) | record language |
| `stock_code` | required on list-style latest endpoint | — |

### Response contract (`research-conclusion-v1`)

- `mode` — effective density
- `metadata` — `record_id`, `stock_code`, `as_of`, `confidence_level`,
  `evidence_counts`, `evidence_refs` (unique `source_id` values)
- `conclusion` — one-sentence decision, action, risks, **gaps**, optional
  mode-filtered `report_strata`, truncation notice
- `disclaimer` — non-investment-advice text when strata present

**Not included:** secrets, API keys, full `raw_result`, management-plane fields,
or any write/mutation methods.

### Mode density

Reuses `src/services/report_mode.py` limits:

| Mode | Strata | Client intent |
| --- | --- | --- |
| `brief` | omitted (`null`) | Push/embed summary; gaps still included (bounded) |
| `standard` | compact list caps | Default portal card |
| `research` | full mode caps + longer summary fields | Deep research view |

## Governance

| Concern | Behavior |
| --- | --- |
| Auth | Same `/api/v1/*` session cookie middleware (`ADMIN_AUTH_ENABLED`) |
| Audit | `event_type=research_api.request`; attempt + completion; storage failure → `503 security_audit_unavailable` |
| Rate limit | `SlidingWindowRateLimiter` keyed by principal + action (`research.conclusions.get` / `.latest`) |
| Port | Main API only — **no** dedicated research/MCP-style extra process for this surface |

## Out of scope

- Capability registry registration (#1185 and related)
- Agent deep research `POST /api/v1/agent/research` (different product path)
- Exportable audit zip / evidence package (#127)
- Write methods or analysis triggers on this surface

## Related

- Report strata contract: [report-strata-contract_EN.md](report-strata-contract_EN.md)
- Report modes (brief/standard/research): `src/services/report_mode.py`
- MCP governance reference: [mcp-server-integration_EN.md](mcp-server-integration_EN.md)
