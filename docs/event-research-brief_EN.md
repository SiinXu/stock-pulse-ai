# Event Research Brief (earnings-first)

> 中文：[event-research-brief.md](event-research-brief.md)

Issue #1131. Structured EventBrief for managed corporate-event triggers (day one: earnings).

- Standalone path: `EVENT_RESEARCH_BRIEF_ENABLED` (default off).
- Pack: metrics_to_watch, surprise_criteria, linked_hypotheses, post_event_checklist, verify_hook.
- The service consumes only managed `intelligence_items` corporate-event triggers and labels the phase `observed_event_review`; it does not claim a future-event catalog (#153).
- Real persisted JSON diagnostics are parsed strictly; invalid/non-finite payloads are rejected instead of displayed.
- Daily brief embeds recent event context under the compatibility `event_foresight` payload key. No new Agent tools.
- Each brief is capped at 12,000 characters and combined notification output at 24,000 characters.
- Task name `event_research_brief`; notification uses the shared `report` route with per-channel failure isolation, and failed delivery remains retryable in the running process.
