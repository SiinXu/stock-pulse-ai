# Agent Planning: Proposal Foundation and Execution Loop

**Status**: partial delivery for issue [#199](https://github.com/SiinXu/stock-pulse-ai/issues/199)

**Chinese**: [agent-planning-engine.md](agent-planning-engine.md)

## Honest boundary

`src/agent/planning/` provides:

1. **Proposal foundation** — produce and validate a bounded `AgentPlan` (`PlanningEngine`).
2. **Execution loop** — optional `execute_plan_loop` that runs plan → act → observe → replan under hard budgets.

Neither path is wired into `AgentExecutor`, Chat, Research, daily analysis, the multi-agent orchestrator, reports, Web settings, or product configuration. Callers must invoke the APIs explicitly.

A proposal alone must never be described as a complete production planning engine. The loop is the first real execution slice; product integration remains open.

## Proposal contracts

- Callers construct `PlanningSettings` explicitly. There are no `AGENT_PLANNING_*` environment variables or parallel configuration owner.
- **One limit authority.** Every absolute bound lives in `src/agent/planning/config.py` and is imported by settings validation, payload validation, the engine, prompt projection, and the execution loop. No module restates a limit as a literal.
- Exact finite proposal limits: at most 16 steps, 3 proposal retries, 8,192 planner tokens, and 60 seconds per proposal call. Invalid explicit values raise `ValueError`; they are never clamped or silently defaulted.
- The `max_steps` argument of the public `validate_plan_payload` is a *caller cap that may only tighten* the absolute 16-step authority.
- Schema version must be exactly `agent-plan-v1`. Step ids are positive, unique, and sequential.
- Every expected tool must be present in the caller-supplied available-tool set. An empty registry authorizes no tools.
- **Acceptance implies projectability.** Validated plans always fit the 20,000-character projection budget.
- Cancellation is checked before and after an LLM call and again before acceptance.
- Provider usage is collected before JSON validation, including billed invalid responses.
- Prompt projection is labeled `NON_AUTHORITATIVE_PLAN_PROPOSAL` and cannot add tools, permissions, or instructions.
- One projected-string contract (`unprojectable_reason`) covers every projected field, including tool names (marker forgery and unpaired surrogates).

## Execution loop contracts

`execute_plan_loop` is the plan → act → observe → replan entry point.

- Callers construct `PlanExecutionSettings` explicitly (no environment/Config owner in this slice).
- Absolute execution maxima: 32 tool calls, 3 observation-driven replans, 120 seconds wall clock, 500-character observation summaries. Settings may only tighten these.
- Each plan step invokes its `expected_tools` through a **caller-supplied invoker** (typically wrapping `ToolSurface.execute_tool`). The loop does not bypass tool authorization, capabilities, or the Tool Surface security contract.
- Tool results must include an exact boolean `ok`. Missing or non-bool `ok` is a failure (`invalid_tool_result`). The loop **never fail-opens** a failed or ambiguous tool result as overall success.
- Empty `expected_tools` steps are synthesis steps and succeed without inventing tool work.
- On step failure with `on_step_failure="terminate"` (or exhausted replan budget), the loop terminates with a stable `reason` / `error_code` and `success=False`.
- On step failure with `on_step_failure="replan"` and remaining budget, the loop calls the planner with `prior_observations`, records the replan in the audit trail, and restarts from the new plan. Prior observations remain visible in metadata.
- Template replan excludes hard-failed tools (non-transient error codes) when building the next proposal; authorization still comes only from the caller-supplied available-tool set.
- Cost/step upper bounds that stop the loop: `max_tool_calls_exceeded`, `execution_timeout`, `max_observation_replans_exceeded`, `cancelled`, `replan_failed`.
- Trace channel: the loop emits `plan_execution` / `plan_step` phase events, tool start/end events, and terminal decision events through the existing agent observability helpers (persisted when a diagnostic context is active). Full structured metadata is always available via `PlanExecutionResult.to_metadata()` for diagnostics and evaluation consumers.
- `success=True` only when the active plan completes every step successfully after any replans. Historical failed steps before a successful replan stay in the observation list and do not flip the terminal flag to success by themselves — the terminal flag reflects loop completion, not “every observation row is green.”

### Explicit execution example

```python
from src.agent.planning import (
    PlanningEngine,
    PlanningSettings,
    PlanExecutionSettings,
    execute_plan_loop,
)

engine = PlanningEngine(PlanningSettings(enabled=True, strategy="template"))
outcome = engine.plan(
    "Analyze 600519",
    available_tools=["get_realtime_quote", "get_daily_history"],
    context={"stock_code": "600519"},
)
assert outcome.plan is not None

def invoker(name, arguments):
    # Wrap ToolSurface.execute_tool in production callers.
    return surface.execute_tool(name, arguments, context=access_ctx)

result = execute_plan_loop(
    plan=outcome.plan,
    tool_invoker=invoker,
    available_tools=["get_realtime_quote", "get_daily_history"],
    task="Analyze 600519",
    context={"stock_code": "600519"},
    settings=PlanExecutionSettings(max_total_tool_calls=8, max_observation_replans=1),
    planning_settings=PlanningSettings(enabled=True, strategy="template"),
)
print(result.success, result.status, result.to_metadata())
```

## Privacy and retention

The library does not persist anything by itself. Observability emit is best-effort and fail-open at the emit boundary only; execution outcomes never claim success on failure. Callers must not persist private task text, free-form model reasoning, credentials, or raw provider responses. Returned metadata is restricted to stable reason codes, bounded summaries, plan ids, and observation status rows.

## Remaining #199 scope

- mode-aware RUN/CHAT/RESEARCH/daily product policy and shared tool authorization budgets across those modes;
- durable plan/action/observation audit persistence, tenant identity, redaction/retention ownership, and product UI;
- one shared UsageRecorder / security-audit / run-diagnostics configuration owner for planning;
- deterministic multi-step real-tool acceptance evidence inside production workflows.

## Rollback

Revert the additive planning module, tests, and documentation. There is no runtime switch, migration, or production integration to roll back.
