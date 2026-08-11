# Agent Planning: Proposal Foundation and Execution Loop

**Status**: partial delivery for issue [#199](https://github.com/SiinXu/stock-pulse-ai/issues/199)

**Chinese**: [agent-planning-engine.md](agent-planning-engine.md)

## Honest boundary

`src/agent/planning/` provides:

1. **Proposal foundation** — produce and validate a bounded `AgentPlan` (`PlanningEngine`).
2. **Execution loop** — optional `execute_plan_loop` that runs plan → act → observe → replan under hard budgets.
3. **Production RUN path** — when `AGENT_PLANNING_ENABLED=true`, `AgentExecutor.run` (used by agent-mode analysis orchestration) calls `try_run_with_planning` so plan → act → observe really runs with `BoundToolSession` tool dispatch, then LLM synthesis for the decision dashboard.

Default remains **off**: classic ReAct RUN is byte-stable when the switch is false. Chat, Research, multi-agent orchestrator, and durable product UI are still not fully mode-aware in this slice.

## Proposal contracts

- Shared Config owns product knobs via `AGENT_PLANNING_*` (registered in the Settings registry). Library callers may still construct `PlanningSettings` / `PlanExecutionSettings` explicitly.
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

- Product path builds `PlanExecutionSettings` from Config; library callers may still construct settings explicitly.
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

## Production RUN integration

| Env / Config field | Default | Role |
| --- | --- | --- |
| `AGENT_PLANNING_ENABLED` | `false` | Master switch for `AgentExecutor.run` |
| `AGENT_PLANNING_STRATEGY` | `template` | `template` or `llm` |
| `AGENT_PLANNING_MAX_PLAN_STEPS` | `8` | Proposal step cap (1–16) |
| `AGENT_PLANNING_MAX_REPLANS` | `1` | Proposal retries (0–3) |
| `AGENT_PLANNING_MAX_TOKENS` | `1500` | LLM planner token budget (1–8192) |
| `AGENT_PLANNING_PROPOSAL_TIMEOUT_SECONDS` | `30` | Proposal wall clock (0.1–60) |
| `AGENT_PLANNING_MAX_TOTAL_TOOL_CALLS` | `16` | Execution tool-call cap (1–32) |
| `AGENT_PLANNING_MAX_OBSERVATION_REPLANS` | `1` | Observation replans (0–3) |
| `AGENT_PLANNING_EXEC_TIMEOUT_SECONDS` | `60` | Execution wall clock (0.1–120) |
| `AGENT_PLANNING_ON_STEP_FAILURE` | `replan` | `replan` or `terminate` |

Flow when enabled:

1. `PlanningEngine.plan` with tools from the executor registry.
2. `execute_plan_loop` with a `BoundToolSession` invoker (same security authority as the native runner).
3. On success, inject observation evidence into the user message and run dashboard synthesis via `_run_loop`.
4. On proposal or execution failure, return `AgentResult(success=False)` with `planning_metadata` (never fail-open success).
5. Traces: existing agent observability phase/tool/decision events; `AgentResult.planning_metadata` / `tool_calls_log` for diagnostics.

## Remaining #199 scope

- mode-aware Chat / Research / multi-agent policy (RUN is wired; Chat/Research still classic paths);
- durable plan/action/observation audit persistence, tenant identity, redaction/retention ownership, and richer product UI beyond Settings knobs;
- deeper shared UsageRecorder ownership beyond BoundToolSession security audit + observability emit;
- broader real-network multi-step acceptance evidence beyond focused offline production-path tests.

## Rollback

Set `AGENT_PLANNING_ENABLED=false` (default) or revert this integration PR. No data migration.
