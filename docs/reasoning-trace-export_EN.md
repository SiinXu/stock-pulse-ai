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
- `synthesis`: bounded projections of disagreement, consensus, and the final conclusion; arbitrary nested model payloads are not copied. Containers hold only values that actually exist, so an empty source yields an empty container rather than a container of nulls.
- `data_sources`: bounded provider, LLM, pipeline-stage, and data-quality projections.
- `coverage.sources`: per-source `supported`, `present`, `absent`, `source_truncated`, `source_truncated_unknown`, `export_truncated`, `original_count`, `returned_count`, `source_dropped_count`, `dropped_count`, and stable reasons.
- `truncation`: every loss caused by source retention, projection limits, value clipping, malformed input, or the size budget.

### Identity semantics

`run.record_id` is the immutable analysis-history primary key that was actually exported. `run.lookup_key` is the value the caller requested and `run.lookup_mode` reports how it was *resolved*, not how it parses: history lookup tries the integer primary key first and falls back to latest-by-`query_id`, so a numeric lookup key that is not a primary key resolves through the fallback and is reported as `latest_by_query_id`. The security-audit attempt row is recorded against the requested lookup key, and the completion row is recorded against the resolved immutable record.

Structural correlation identities (`record_id`, `query_id`, `trace_id`, `run_id`, `lookup_key`) are validated against a strict identity charset and preserved through redaction so exports stay correlatable with runtime logs and audit rows. The charset excludes `.` and `/`, so JWT-shaped values, credential-bearing URLs, and filesystem paths never qualify and remain redacted. Evidence payloads are always redacted.

### Loss accounting

Coverage is reconciled against the payload that is actually returned on every exit path, including each size-budget step, and count/presence invariants are asserted before the response is emitted. A source that was dropped to satisfy the budget reports `present=false`, `returned_count=0`, and the full `dropped_count`; it can never keep a stale `present=true` or an original `returned_count`. Value-level clipping and unsupported or malformed items are recorded in `truncation.dropped` rather than being applied silently. `present` is derived from real projected content, so an empty or null-only source is reported absent.

Run diagnostics retain the newest 200 agent events and persist original, returned, and dropped counts in an `agent_events_capture` marker. Records written before that marker existed cannot prove whether capture loss occurred: a marker-less record holding exactly the historical 200-event cap reports `source_truncated_unknown=true` with `original_count` and `dropped_count` set to null and a `legacy_capture_loss_unknown` reason, instead of claiming zero loss. `source_dropped_count` reports capture-stage retention loss, while `dropped_count` reports the total gap between `original_count` and what the response carries. The exporter separately bounds agent events, per-agent tool calls, and provider/LLM/stage lists. Every cap is reflected in coverage and truncation.

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
