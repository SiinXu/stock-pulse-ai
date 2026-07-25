# Agent Stream Progress Events

This document records the progress-event contract used by:

- `POST /api/v1/agent/chat/stream`
- Web Ask Stock chat progress rendering
- single-agent `run_agent_loop`
- multi-agent `AgentOrchestrator`

The endpoint still streams Server-Sent Events (`text/event-stream`) where each
SSE payload is a JSON object with a top-level `type` field.

## Compatibility Boundary

The event changes are additive. Existing clients can keep consuming the legacy
top-level fields:

- `type`
- `step`
- `tool`
- `display_name`
- `success`
- `duration`
- `message`
- `content`

New clients may additionally read:

- `stage`
- `status`
- `elapsed`
- `timeout`
- `remaining`
- `minimum`
- `reason`
- `meta`
- `verdict`
- `requested_verdict`
- `reasons`
- `missing_evidence`
- `retry_target`
- `retry_targets_requested`
- `retry_targets_executed`
- `retry_budget_consumed`
- `retry_budget_remaining`
- `retry_status`
- `validation_status`
- `confidence_delta`

Unknown event types should be ignored or displayed with a generic fallback.
`done` and `error` keep their existing completion semantics.

The Critic event types below are produced only for an explicitly enabled,
non-Chat Native Multi run. `response_mode=chat` never enters the Critic stage,
so these additions do not expand the public Ask Stock Chat SSE payload.

## Event Types

| Type | Producer | Meaning | Important Fields |
| --- | --- | --- | --- |
| `stage_start` | single-agent loop, multi-agent orchestrator | An agent or pipeline stage has started. | `stage`, `message` |
| `stage_done` | single-agent loop, multi-agent orchestrator | An agent or pipeline stage has completed. | `stage`, `status`, `duration` |
| `thinking` | single-agent loop | The agent is deciding the next action. | `step`, `message` |
| `tool_start` | single-agent loop | A tool call has started. | `step`, `tool`, `display_name` |
| `tool_done` | single-agent loop | A tool call has completed or failed. | `step`, `tool`, `success`, `duration`, `display_name` |
| `generating` | single-agent loop | The final response is being generated. | `step`, `message` |
| `pipeline_timeout` | multi-agent orchestrator | The orchestrator stopped because the stage or pipeline budget expired. | `stage`, `elapsed`, `timeout` |
| `pipeline_budget_skipped` | multi-agent orchestrator | The orchestrator stopped before starting the next stage because the remaining budget was too low for useful work. | `stage`, `elapsed`, `timeout`, `remaining`, `minimum`, `reason`, `message` |
| `critic_verdict` | enabled non-Chat multi-agent orchestrator | The bounded Critic produced a validated verdict, failed closed, or could not complete. | `stage`, `verdict`, `requested_verdict`, `reasons`, `missing_evidence`, `retry_targets_requested`, `retry_targets_executed`, `retry_budget_consumed`, `retry_budget_remaining`, `retry_status`, `validation_status`, `confidence_delta` |
| `critic_retry_start` | enabled non-Chat multi-agent orchestrator | The one-shot whitelist retry has consumed its run budget and started. | `stage`, `retry_target`, Critic verdict and budget fields |
| `critic_retry_done` | enabled non-Chat multi-agent orchestrator | The whitelist retry completed or failed without opening another retry. | `stage`, `status`, `duration`, `retry_target`, Critic verdict and budget fields |
| `done` | SSE endpoint | The request completed. | `success`, `content`, `error`, `total_steps`, `session_id` |
| `error` | SSE endpoint | The request failed before normal completion. | `message` |

## Web Behavior

The Web chat UI now recognizes `stage_start`, `stage_done`,
`pipeline_timeout`, and `pipeline_budget_skipped` in addition to the existing
thinking/tool/generating events.
Critic events are not emitted on Chat runs. A non-Chat progress consumer can
render their bounded fields directly or treat them as an additive unknown type.
If a future backend event is not recognized, the UI keeps the event in the
message progress history and renders a generic fallback instead of an empty
progress row.

## Runtime And Provider Scope

This event contract does not change model routing or runtime configuration.
It does not modify:

- provider selection
- model names
- Base URL handling
- LiteLLM route resolution
- API keys or credential loading
- configuration cleanup or migration semantics

Provider/model/Base URL behavior remains governed by the existing LLM
configuration docs and runtime code. Any provider/model strings used in tests
are mock identifiers only.

## Validation

Recommended checks for changes to this contract:

```bash
python -m pytest \
  tests/test_agent_stream_events.py \
  tests/test_agent_sse_cleanup.py \
  tests/agent/test_bounded_critic.py
```

```bash
cd apps/dsa-web
npm test -- src/stores/__tests__/agentChatStore.test.ts src/pages/__tests__/ChatPage.test.tsx
```

The focused tests should confirm that:

- event helper output preserves legacy fields and drops unset fields
- stage metadata is preserved
- `run_agent_loop` emits paired `stage_start` / `stage_done` events plus
  `thinking` and `generating`
- orchestrator timeout events remain separate from budget-skip events
- Critic pass/retry/fail-soft traces expose bounded verdict and budget fields
- Critic retry/fail-soft verdicts without an explicit reason or limitation fail closed
- Critic cancellation and timeout exits finalize metadata before termination
- SSE cleanup behavior remains unchanged
- Web chat state and Chat page rendering still pass

## Rollback

To roll back this event-contract change, revert the commit that introduced:

- `src/agent/stream_events.py`
- the event-helper wiring in `src/agent/runner.py`
- the stage-event wiring in `src/agent/orchestrator.py`
- the Web `ProgressStep` and Chat page rendering updates

Because the change is additive and keeps `done` / `error` semantics unchanged,
existing clients can also ignore the new stage events without a migration step.
For the bounded Critic additions specifically, disabling
`AGENT_CRITIC_ENABLED` restores the previous event set immediately; reverting
the Critic change removes the event types without data or schema migration.
