# Reasoning Trace Export

This document defines the multi-agent reasoning-trace export contract (Issue #135 / T03). The exporter reads only data already persisted in analysis history. It does not invent missing reasoning or change agent-core recording.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `REASONING_TRACE_EXPORT_ENABLED` | `false` | Master switch for the export API and service gate |
| `REASONING_TRACE_EXPORT_MAX_CHARS` | `500000` | Complete-response character budget, clamped to `10000`–`2000000` |

When disabled, `GET /api/v1/reasoning-trace/{record_id}` returns `404 reasoning_trace_export_disabled` without reading or exporting history content.

## API and identity semantics

```http
GET /api/v1/reasoning-trace/{record_id}?format=json|markdown&include_markdown=false
```

- Administrator authentication must be enabled and the request must carry a valid session. Export fails closed when authentication is disabled.
- A numeric `record_id` resolves the history primary key. A non-numeric value selects the latest record for that `query_id`.
- The package carries immutable history `record_id`, potentially non-unique `query_id`, diagnostic `trace_id`, stable `run_id`, lookup key, and lookup mode separately.
- `format=json` returns strict JSON. With `include_markdown=true`, Markdown is included in the same complete JSON response budget.
- `format=markdown` returns `text/markdown`. Stored and model-originated values appear only in an indented code block, so they do not become active links, images, or HTML.
- Successful responses include `Cache-Control: private, no-store`, `Pragma: no-cache`, attachment disposition, and `X-Content-Type-Options: nosniff`.
- Every authenticated export persists security-audit attempt and completion events before content is returned. Audit unavailability fails closed with `503`.

OpenAPI declares both `application/json` and `text/markdown` success representations and the 400/401/403/404/422/500/503 error contracts.

## `reasoning-trace-v1` contract

The response uses strict typed models: `schema_version` is the literal `reasoning-trace-v1`, unknown fields are rejected, strings and lists are bounded, and all floating-point values must be finite. NaN, infinities, unknown objects, and malformed persisted entries do not flow directly into the response.

Main sections:

- `run`: record/query/trace/run identities, stock, market, model, timestamps, and a non-secret configuration fingerprint.
- `agents`: bounded roles, input summaries, tool calls, opinions, and event summaries.
- `synthesis`: bounded projections of disagreement, consensus, and the final conclusion; arbitrary nested model payloads are not copied.
- `data_sources`: bounded provider, LLM, pipeline-stage, and data-quality projections.
- `coverage.sources`: per-source `supported`, `present`, `absent`, `source_truncated`, `export_truncated`, original/returned/dropped counts, and stable reasons.
- `truncation`: every loss caused by source retention, projection limits, malformed input, or the size budget.

Run diagnostics retain the newest 200 agent events and persist original, returned, and dropped counts. The exporter separately bounds agent events, per-agent tool calls, and provider/LLM/stage lists. Every cap is reflected in coverage and truncation.

The size budget is enforced after projection, redaction, strict serialization, and optional Markdown embedding. Every return path rechecks the complete negotiated response. If optional evidence cannot fit, a deterministic typed minimal envelope is returned instead of an oversized marked response.

## Security boundary

The exporter reuses `src.utils.sanitize.redact_sensitive_data` and enables opaque-token handling at this high-risk boundary. Supported redaction classes are:

- identified API-key, password, Authorization/Bearer, cookie, and token fields;
- Bearer/JWT/long opaque-token patterns;
- credential-bearing URLs;
- common POSIX local roots, Windows drive paths, UNC paths, and `~/`, `./`, or `../` relative paths.

Pattern scanning cannot prove that every unknown secret embedded in arbitrary natural-language text will be recognized, so this contract does not claim that no possible secret can ever be exported. Exports can still contain business-sensitive context. Restrict administrator access, store downloads securely, and treat them as sensitive data. The service does not persist or reclaim generated files; disabling or reverting the feature does not delete external copies.

## Current coverage and gaps

When present, the exporter covers history run metadata, `diagnostics.agent_events`, provider/LLM/pipeline-stage summaries, dashboard synthesis summaries, and context-pack data-quality summaries.

Agent core does not yet persist complete system/user prompts, tool arguments without deep payload, chat-provider thinking blocks, ephemeral SSE events, or raw provider API responses. Issue #135 remains open; Web Settings and complete capture are also outside T03.

## Rollback

Keep `REASONING_TRACE_EXPORT_ENABLED=false` and restart, or revert this change. The service does not store export files; operators must separately delete downloaded or copied artifacts.
