# Agent Observability L0 (Structured Run Events)

L0 delivery for issue #222: lightweight, default-on structured events and trace/span correlation for Agent execution. Events reuse existing run-diagnostics / run-flow storage and UI instead of introducing a full metrics platform.

## Scope

- Event types: `agent.phase_start/end`, `agent.tool_start/end`, `agent.model_start/end`, `agent.decision`
- Each event carries `trace_id`, `span_id`, optional `parent_span_id`, `duration_ms`, and sanitized `attrs`
- Default path records only lightweight metadata; deep payloads (tool argument/result previews) require `AGENT_OBSERVABILITY_DEEP_PAYLOAD=true`
- Events append to `RunDiagnosticContext.agent_events` and fail-open mirror into run-flow `flow_event`
- Web continues to use the existing run-flow panel; event stream and node details show timings and tool sequence, with an Agent decision-event replay cursor

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

## Agent Replay V1

The existing task and history run-flow panel presents Agent events by `sequence` and provides previous/next cursor controls. Each replay detail includes its event schema version, trace/span correlation, status, and server-sanitized `attrs`; `payload` is shown only when deep payload capture is explicitly enabled and the server has sanitized it.

The integrity state checks:

- missing, duplicate, or gapped `sequence` values
- whether the event schema is the currently supported v1
- whether event `trace_id` values match the run-flow snapshot
- whether capture counts satisfy `original = returned + dropped`, including truncation at the 200-event cap
- whether replay detail contained rejected NaN or positive/negative infinity values

`Complete` means those evidence contracts agree. `Partial` means capture counts are unavailable, events are missing, or the cap truncated the stream. `Invalid` means version, sequence, trace, detail, or counts contradict one another. Replay reads the existing `/flow` projection and adds no store or side-channel endpoint.

V1 does not include two-run comparison, exportable debug packages, raw prompts/reasoning, or a separate context/memory browser. Issue #254 continues to track that remaining scope.

## Related

- [Run diagnostics Phase 3](run-diagnostics-p3.md)
- Chinese: [agent-observability.md](agent-observability.md)
