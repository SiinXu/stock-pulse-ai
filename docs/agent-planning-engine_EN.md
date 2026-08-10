# Typed Agent Plan-Proposal Foundation

**Status**: proposal-only foundation referencing issue [#199](https://github.com/SiinXu/stock-pulse-ai/issues/199)

**Chinese**: [agent-planning-engine.md](agent-planning-engine.md)

## Honest boundary

`src/agent/planning/` can produce and validate a bounded plan proposal when an offline caller invokes it explicitly. It is not wired into `AgentExecutor`, Chat, Research, daily analysis, the multi-agent orchestrator, reports, diagnostics, persistence, or Web settings.

It does **not** execute plan steps, attach tool results to observations, replan from observations, enforce a shared execution budget, or provide an audit trace. Those are remaining #199 acceptance items. A proposal must never be described as a plan→act→observe engine.

## Contracts

- Callers construct `PlanningSettings` explicitly. There are no `AGENT_PLANNING_*` environment variables or parallel configuration owner.
- **One limit authority.** Every absolute bound lives in `src/agent/planning/config.py` and is imported by settings validation, payload validation, the engine, and prompt projection. No module restates a limit as a literal.
- Exact finite limits: at most 16 steps, 3 retries, 8,192 planner tokens, and 60 seconds per proposal call. Invalid explicit values raise `ValueError`; they are never clamped or silently defaulted.
- The `max_steps` argument of the public `validate_plan_payload` is a *caller cap that may only tighten* the absolute 16-step authority. Passing `max_steps=17` is rejected outright, so no caller can widen the public contract to accept a 17-step plan.
- Schema version must be exactly `agent-plan-v1`. Step ids are positive, unique, and sequential. Goals, success criteria, tool names, the available-tool set size, the input task, and the projected prompt are bounded.
- Every expected tool must be present in the caller-supplied available-tool set. An empty registry authorizes no tools; unknown tools invalidate the proposal.
- **Acceptance implies projectability.** Per-field bounds do not bound the whole payload, so validation also rejects any plan whose rendered projection would exceed the 20,000-character limit. A validated plan can therefore always be projected; `format_plan_for_prompt` never fails on an accepted plan.
- Cancellation is checked before and after an LLM call and again before acceptance, so a late response cannot be applied.
- The remaining deadline is passed into the adapter call as its transport `timeout`, so the planner call is genuinely interruptible rather than only checked after it returns. The post-return deadline check remains as a second fence.
- Provider usage is collected before JSON validation, including billed invalid responses. Metadata contains stable error codes and exception types, never raw exception text or planner output.
- **Retry evidence is truthful.** `replan_attempts` counts the retries actually performed on every exit path, including a successful one. When an `llm` attempt fails and the retry degrades to `template`, `requested_strategy` stays `llm` while `strategy` becomes `template`, so billed tokens and the recorded model remain attributable. `max_replans_exceeded` is reported only when replans were both permitted and spent; otherwise the reason is `planning_failed`.
- A stable SHA-256 `plan_id` identifies the canonical proposal.
- Prompt projection is labeled `NON_AUTHORITATIVE_PLAN_PROPOSAL`; generated fields are advisory data and cannot add tools, permissions, or instructions or override the original user/system request.
- **The advisory boundary is unforgeable by model text.** Generated goals and success criteria are rejected if they contain any spelling of the boundary marker (case-insensitive, whitespace-tolerant), so a proposal cannot close the advisory block early and have the remainder read as authoritative instructions. Every other character is carried inside a JSON string, which escapes quotes, backslashes, and control characters. `format_plan_for_prompt` additionally asserts each marker appears exactly once.

## Explicit example

```python
from src.agent.planning import PlanningEngine, PlanningSettings

engine = PlanningEngine(
    PlanningSettings(enabled=True, strategy="template", max_plan_steps=4)
)
outcome = engine.plan(
    "Analyze 600519",
    available_tools=["get_realtime_quote", "get_daily_history"],
    context={"stock_code": "600519"},
)
assert outcome.plan is not None
print(outcome.to_metadata())
```

The template strategy performs no network call. The `llm` strategy requires a caller-provided adapter and remains proposal-only.

## Privacy and retention

This foundation does not persist anything. Callers must not persist private task text, free-form model reasoning, credentials, or raw provider responses. Returned failure metadata is restricted to stable reason codes, exception type, bounded usage, model name, and the validated proposal.

## Remaining #199 scope

- mode-aware RUN/CHAT/RESEARCH/daily product policy;
- authorized step execution and typed observations;
- observation-driven replanning;
- one total planner/executor/tool deadline and token/cost/step budget;
- shared UsageRecorder, security audit, run diagnostics, tenant identity, redaction, and retention;
- deterministic multi-step real-tool acceptance evidence.

## Rollback

Revert the additive planning module, tests, and documentation. There is no runtime switch, migration, persisted data, or production integration to roll back.
