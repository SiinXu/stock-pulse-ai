# Reasoning Trace Export

Contract for the multi-agent reasoning-trace export path (Issue #135 / T03).

## Purpose

Export a **redacted**, machine-readable audit package describing how an analysis
conclusion was produced, using only data that the pipeline **already records**.
This complements (and does not replace) the evidence-chain / security-audit
surfaces.

## Feature flag

| Variable | Default | Description |
| --- | --- | --- |
| `REASONING_TRACE_EXPORT_ENABLED` | `false` | Master switch for the export API and service gate |
| `REASONING_TRACE_EXPORT_MAX_CHARS` | `500000` | Hard JSON character budget; overflow is truncated with an explicit marker |

When the flag is off, `GET /api/v1/reasoning-trace/{record_id}` returns
`404 reasoning_trace_export_disabled` and has no side effects.

## Endpoint

```http
GET /api/v1/reasoning-trace/{record_id}?format=json|markdown&include_markdown=false
```

- **Auth**: fail-closed. Administrator authentication must be enabled, and a
  valid admin session cookie is required (same sensitivity class as security
  audit diagnostics). If auth is disabled, the endpoint returns
  `403 reasoning_trace_auth_required`.
- **`format=json`** (default): response body is the `reasoning-trace-v1` package
  (optionally with an embedded `markdown` field when `include_markdown=true`).
- **`format=markdown`**: response body is `text/markdown` with redacted content;
  headers `X-Reasoning-Trace-Schema` and `X-Reasoning-Trace-Truncated` are set.

## Schema: `reasoning-trace-v1`

```json
{
  "schema_version": "reasoning-trace-v1",
  "run": {
    "run_id": "...",
    "stock_code": "...",
    "market": "...",
    "model": "...",
    "started_at": "...",
    "config_fingerprint": "..."
  },
  "agents": [
    {
      "role": "research",
      "input_summary": "...",
      "tool_calls": [{"name": "get_quote", "status": "ok"}],
      "output_opinion": "buy",
      "events": []
    }
  ],
  "synthesis": {
    "disagreement": {},
    "consensus": {},
    "final_conclusion": {},
    "committee_deliberation": {},
    "strategy_synthesis": {}
  },
  "data_sources": {
    "provider_trace": [],
    "llm_runs": [],
    "data_quality_status": {},
    "pipeline_stage_runs": []
  },
  "coverage": {
    "recorded": [],
    "not_recorded": [],
    "notes": "..."
  },
  "truncated": false
}
```

When the size budget is exceeded, `truncated` is `true` and `truncation` lists
dropped paths. Truncation is **never silent**.

## Security

- Every package (and markdown companion) is processed with
  `src.utils.sanitize.redact_sensitive_data` — the same helper used by
  `SecurityAuditService`.
- API keys, tokens, credentialed URLs, and local filesystem paths must not
  appear in exports. Dedicated unit tests assert zero hits for injected secrets.
- This task does **not** change agent core recording (`src/agent/` is out of scope).

## Coverage inventory (current main)

### Recorded and exported when present

- Run meta from analysis history (`query_id`, stock, model, timestamps)
- `context_snapshot.diagnostics.agent_events` (L0 observability)
- Provider / LLM / pipeline stage runs from diagnostics
- `dashboard.committee_deliberation`, `dashboard.strategy_synthesis`,
  `dashboard.core_conclusion` from `raw_result`
- Context-pack data-quality overview when stored

### Not recorded by agent core today (export cannot invent them)

- Full agent prompts / system messages
- Tool arguments unless deep payload capture was enabled for that run
- Chat provider protocol thinking blocks (`provider_trace.py` is chat-roundtrip oriented)
- Ephemeral SSE `stream_events`
- Raw provider API response bodies

## Integration notes

- Config registry / Web Settings registration is intentionally **not** part of
  this change (owned by other parallel work). Operators enable export via env.
- Capture-time flag `REASONING_TRACE_ENABLED` from the original issue is not
  introduced here: L0 agent events already record under
  `AGENT_OBSERVABILITY_ENABLED` (default on). Export remains a separate opt-in.
