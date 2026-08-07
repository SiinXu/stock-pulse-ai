# Agent Observability L0 (Structured Run Events)

L0 delivery for issue #222: lightweight, default-on structured events and trace/span correlation for Agent execution. Events reuse existing run-diagnostics / run-flow storage and UI instead of introducing a full metrics platform.

## Scope

- Event types: `agent.phase_start/end`, `agent.tool_start/end`, `agent.model_start/end`, `agent.decision`
- Each event carries `trace_id`, `span_id`, optional `parent_span_id`, `duration_ms`, and sanitized `attrs`
- Default path records only lightweight metadata; deep payloads (tool argument/result previews) require `AGENT_OBSERVABILITY_DEEP_PAYLOAD=true`
- Events append to `RunDiagnosticContext.agent_events` and fail-open mirror into run-flow `flow_event`
- Web continues to use the existing run-flow panel; event stream and node details show timings and tool sequence

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `AGENT_OBSERVABILITY_ENABLED` | `true` | Toggle lightweight events |
| `AGENT_OBSERVABILITY_DEEP_PAYLOAD` | `false` | Capture sanitized deep payloads |

## Privacy

- All payloads pass through `sanitize_agent_event_payload` and diagnostic redaction helpers
- Prompt, messages, API keys, tokens, authorization, and similar fields are blocked or redacted
- Deep mode still redacts sensitive keys and text

## Overhead

- Default path appends small dicts and optionally writes the flow sink; at most 200 agent events are kept per run
- Emit is a no-op without a diagnostic context; recording failures are fail-open and never change Agent control flow

## API

No new endpoint. Task and history run-flow continue to use:

- `GET /api/v1/analysis/tasks/{task_id}/flow`
- `GET /api/v1/history/{record_id}/flow`

Agent events appear in `events[]` and persist under diagnostics snapshot field `agent_events`.

## Related

- [Run diagnostics Phase 3](run-diagnostics-p3.md)
- Chinese: [agent-observability.md](agent-observability.md)
