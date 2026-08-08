# Agent Planning Engine (plan-and-execute pre-step)

[中文](agent-planning-engine.md) | [English](agent-planning-engine_EN.md)

Issue [#199](https://github.com/SiinXu/stock-pulse-ai/issues/199). An optional **planning pre-step** for the single-agent `AgentExecutor` path. It produces a structured step list (goal, expected tools, success criteria) before the existing ReAct loop runs.

## Relation to existing orchestration (前置, not 替代)

| Component | Role |
| --- | --- |
| `AgentExecutor` + `run_agent_loop` | Existing single-agent ReAct tool loop (unchanged core) |
| `AgentOrchestrator` | Multi-agent stage pipeline (untouched by this feature) |
| Multi-strategy deliberation | Opinion mediation under `AGENT_MULTI_STRATEGY_DELIBERATION` (untouched) |
| Deep research planner | Query decomposition inside `research.py` (separate path) |
| **Planning engine (this doc)** | **Pre-step** that may inject plan guidance into the user message, then hands off to the existing ReAct loop |

Conclusion: the planner is a **prefix** to single-agent execution, not a second orchestration runtime. Multi-agent daily pipelines stay on the orchestrator path.

## Default off

- Config: `AGENT_PLANNING_ENABLED` (default `false`)
- When off: `AgentExecutor.run` behavior matches the previous direct path; `result.planning` records `{enabled: false, applied: false}`
- When on: build a structured plan, inject it into the task/user message, run the same ReAct loop

## How to enable

```bash
AGENT_MODE=true
AGENT_PLANNING_ENABLED=true
# optional:
# AGENT_PLANNING_STRATEGY=auto   # auto | template | llm
# AGENT_PLANNING_MAX_STEPS=8
# AGENT_PLANNING_MAX_REPLANS=1
# AGENT_PLANNING_MAX_TOKENS=1500
# AGENT_PLANNING_TIMEOUT_S=30
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `AGENT_PLANNING_ENABLED` | `false` | Master gate |
| `AGENT_PLANNING_STRATEGY` | `auto` | `template` = deterministic tool-stage plan; `llm` = model JSON plan; `auto` = llm when adapter present else template |
| `AGENT_PLANNING_MAX_STEPS` | `8` | Max plan steps (hard) |
| `AGENT_PLANNING_MAX_REPLANS` | `1` | Extra planning attempts after failure |
| `AGENT_PLANNING_MAX_TOKENS` | `1500` | Planner completion token request cap |
| `AGENT_PLANNING_TIMEOUT_S` | `30` | Planner completion timeout seconds |

## Structured plan schema

```json
{
  "version": "agent-plan-v1",
  "goal": "Analyze stock and produce a decision dashboard",
  "max_steps": 8,
  "steps": [
    {
      "id": 1,
      "goal": "Fetch market quote and price history",
      "expected_tools": ["get_realtime_quote", "get_daily_history"],
      "success_criteria": "Realtime quote and/or daily history returned"
    }
  ]
}
```

Trace metadata is attached on `AgentResult.planning` (not inserted into the dashboard / report JSON schema).

## Failure and cost bounds

- Invalid plan structure → replan until `AGENT_PLANNING_MAX_REPLANS`, then **degrade to direct execution** (no hard fail)
- LLM planner failure → may fall back to template within remaining attempts; otherwise direct execution
- Exceeding plan step cap → degrade / reject plan
- Cancellation during planning → direct path with `fallback_reason=cancelled`

## What does not change

- Final report / dashboard schema
- `runner.py` tool-call log write format
- Multi-agent orchestrator stages
- Default production behavior when the gate is off

## Integration Point (config registry UI)

Runtime reads env vars directly from `src/agent/planning/config.py` so this feature does not edit `src/core/config_registry_parts/` (parallel-task ownership). To surface switches in Web Settings later, register the keys above in the agent config registry (Integration Point for the config-registry owner).

## Rollback

Set `AGENT_PLANNING_ENABLED=false` or unset it. No data migration; no release required for runtime rollback.
