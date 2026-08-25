# Agent Router Rules Library

**Status**: Issue [#1120](https://github.com/SiinXu/stock-pulse-ai/issues/1120) slices 1–3 (rules library + structured fact projection + `AgentOrchestrator.run()` apply). Chat, factory, native adapter, Analyze, API, CLI, Bot, and MCP remain **not wired**.

**Chinese**: [agent-router.md](agent-router.md)

## Honest boundary

`src/agent/runtime/agent_router.py` is a pure rules-first `AgentRouter`. It classifies analysis depth and Chat path from **already-normalized** facts. `src/agent/runtime/agent_router_facts.py` projects those facts from structured StockScope / entry_kind / symbol count / optional explicit per-run override. `AgentOrchestrator.run()` (dashboard analysis) projects facts and applies the router **once per run**. These slices:

- Do **not** parse raw prompts / user messages, provider payloads, or tool results.
- Do **not** change Settings/env `AGENT_ORCHESTRATOR_MODE`, Soul, ToolSurface, factory / native adapter, Chat/API/OpenAPI/Web/Desktop/CLI/Bot/MCP.
- Do **not** write episode / trace public metadata, EvolutionEvents, or memory admission.
- Do **not** call or expand `prefer_route`. Valid miss-rate evidence has **zero routing influence** (identity-neutral until #1091 / #1106).
- Do **not** copy process-wide Settings/env `AGENT_ORCHESTRATOR_MODE` into `user_mode_override`.
- Do **not** map `report_type` or `skills` / `selected_skill_ids` onto router mode.
- Do **not** close #1120: Chat incremental skipping `_execute_pipeline` (AC3) and decision visible in run metadata (AC4) remain later slices. Factory / Chat / Analyze / CLI / Bot / MCP remain not wired.

Dashboard `run()` is fail-closed: a rejected projection or route returns `AgentResult(success=False)` with the public execution failure message and does **not** fall back to the constructor mode. The constructor-configured mode and mode-budget limits are restored in a `finally` block on success, rejection, and every exception path. Chat still always calls `_execute_pipeline` and still uses the constructor mode.

## Input

Only bounded classification facts (`AgentRouterRequest` or a mapping of the same fields). Any unknown mapping key fails closed (`reason_code=unknown_field`). Unknown keys must **not** be dropped so routing can continue, and key names or values must **not** be echoed into `error` / `explain`.

| Field | Constraint |
| --- | --- |
| `intent_category` | `simple` \| `technical` \| `news` \| `risk` \| `compare` \| `analysis` \| `unknown` |
| `symbol_count` | Non-negative **int** (reject bool / float / string / negative) |
| `need_news` / `need_risk` | Strict `bool` (reject `0`/`1`/`"true"`) |
| `entry_kind` | `run` \| `chat` |
| `is_follow_up` / `same_symbol` / `tool_suitable` | Optional strict `bool`, default `false` |
| `user_mode_override` | Optional. Omitted / `None` means not provided |
| `miss_rate` | Optional. When present: finite number in the closed range `[0.0, 1.0]` (reject bool, NaN/Inf, strings, out-of-range) |

Illegal or missing **required** facts, unknown mapping keys, contradictory classification facts, non-strict booleans, illegal enums, illegal counts, and present-but-malformed miss-rate evidence fail closed: a typed rejected decision with `accepted=false`. They are never silently rewritten to `standard`. An `unknown_field` rejection must not echo key names or values.

## Output

| Field | Value |
| --- | --- |
| `accepted` | Whether a usable route was produced |
| `mode` | `quick` \| `standard` \| `full` \| `specialist` when accepted; `None` when rejected |
| `chat_path` | `incremental_tool` \| `full_repipeline` when accepted; `None` when rejected |
| `reason_code` | Fixed reason code (below) |
| `error` | Short English message on rejection only; never echoes raw input |
| `explain` | Whitelisted derived facts only — no prompt, message, secrets, provider/tool payload, raw override string, or raw miss-rate |

Depth modes match `src.agent.orchestrator.VALID_MODES` and `BUDGET_MODES` minus the Chat budget profile. Deprecated aliases `strategy` / `skill` are valid overrides and normalize to `specialist`. `chat` is not a router mode.

## Rules

A **valid** explicit override always wins. An **invalid / blank** explicit override returns `reason_code=invalid_override` with `mode is None`.

The one deterministic contract for contradictory facts is **fail closed** (`inconsistent_facts`), not silently raising the floor while keeping mismatched flags:

- `intent_category=risk` with `need_risk=false` is rejected; it must not route to `standard` or any mode.
- `intent_category=news` with `need_news=false` is rejected; it must not route to `quick` or below standard.
- `simple` allows only a single symbol with no news/risk; otherwise reject.
- `entry_kind=run` must not carry Chat-only flags (`is_follow_up` / `same_symbol` / `tool_suitable`); otherwise reject.
- `same_symbol=true` requires `is_follow_up=true`; otherwise reject.

After facts are consistent, depth floors without an override are:

1. `risk` with `need_risk=true`, any other `need_risk`, `compare` intent, or `symbol_count >= 2` → at least `full` (`floor_need_risk` / `floor_compare` / `floor_multi_symbol`, in that precedence).
2. Else `news` with `need_news=true`, or any other `need_news` → at least `standard` (`floor_need_news`).
3. Else a clearly simple single-symbol `simple` intent with no news/risk **may** choose `quick` (`quick_eligible`).
4. Else the default dashboard RUN is `standard` + `full_repipeline` (`default_standard`). The router **never** defaults to always-full. `specialist` is available only through a valid explicit override; this slice does not invent skill/model routing.

Chat path (independent of depth, except `full` / `specialist` overrides force a re-pipeline):

- `entry_kind=chat` and a same-symbol follow-up with no news/risk and a tool-suitable intent **may** choose `incremental_tool`.
- A valid RUN (no Chat-only flags) and Chat that does not meet the previous rule → `full_repipeline`.

Miss-rate: when present, validate a finite number in `[0.0, 1.0]` first. Two different **valid** miss rates must yield the same `mode` / `chat_path` / `reason_code`. `explain.miss_rate_applied` is always `false` in this slice. Malformed miss-rate evidence must not be swallowed.

## Reason codes

Accepted: `explicit_override`, `default_standard`, `quick_eligible`, `floor_need_risk`, `floor_compare`, `floor_multi_symbol`, `floor_need_news`.

Rejected: `invalid_override`, `invalid_intent`, `invalid_symbol_count`, `invalid_flag`, `invalid_entry_kind`, `invalid_miss_rate`, `invalid_request`, `unknown_field`, `inconsistent_facts`.

## Usage

```python
from src.agent.runtime.agent_router import AgentRouter, AgentRouterRequest

decision = AgentRouter().route(
    AgentRouterRequest(
        intent_category="simple",
        symbol_count=1,
        need_news=False,
        need_risk=False,
        entry_kind="run",
    )
)
assert decision.mode == "quick"
assert decision.chat_path == "full_repipeline"
```

## Structured fact projection (slice 2)

`project_router_request(facts)` maps **already-structured** runtime facts into a legal `AgentRouterRequest`, or a typed reject **before** `route()`. It does not call `AgentRouter.route()` as a side effect. Unknown mapping keys fail closed without echoing names or values.

| Field | Rule |
| --- | --- |
| `entry_kind` | Required. `run` or `chat` only (`ExecutionMode.RESEARCH` and any other value fail closed). |
| `scope_mode` | Optional. `maintain` / `compare` / `switch`. Unknown fails closed. |
| `allowed_stock_codes` / `symbol_codes` | Optional sequences of already-normalized nonempty strings. `symbol_count` is `len(allowed)` if nonempty, else `len(symbol_codes)`, else `0`. Strings are not treated as character sequences. |
| `expected_stock_code` | Optional string. Used only to derive Chat `maintain` same-symbol. |
| `user_mode_override` | Optional string, only when the caller already has an explicit per-run value. Omitted / `None` means not provided. Never read from `AGENT_ORCHESTRATOR_MODE`. Invalid/blank values are passed through for the router to reject; they are not rewritten to `standard`. |
| `intent_category` | Optional. If omitted: `compare` when `scope_mode=="compare"`, else `unknown`. Never emit `simple` unless the caller already supplied that enum. |
| `need_news` / `need_risk` / `tool_suitable` | Optional strict bools. If omitted: `false`. Do not infer from news blobs, risk-gate config, or tool catalogs. |
| Chat flags | Derived, not accepted as input. Chat `maintain` → follow-up, and same-symbol when `expected_stock_code` is nonempty. Chat `switch` → follow-up and not same-symbol. Chat `compare` / omitted scope → not incremental. RUN always leaves `is_follow_up` / `same_symbol` / `tool_suitable` false unless the caller supplied `tool_suitable=true`, which fails closed. |

`report_type`, `skills`, `selected_skill_ids`, prompts, `miss_rate`, and process-wide config keys are unknown mapping keys.

Default composed routes (project then `route()`, tests only):

- RUN, one symbol, omitted intent (`unknown`), no news/risk, no override → `standard` + `full_repipeline` (`default_standard`). Not `quick`.
- RUN `scope_mode=compare` or `symbol_count>=2` → `full` + `full_repipeline`.
- Chat `maintain` + same symbol + default `tool_suitable=false` → `full_repipeline` (incremental must not fire).

```python
from src.agent.runtime.agent_router import route
from src.agent.runtime.agent_router_facts import project_router_request

projection = project_router_request(
    {
        "entry_kind": "run",
        "symbol_codes": ["600519"],
    }
)
assert projection.accepted is True
decision = route(projection.request)
assert decision.mode == "standard"
assert decision.chat_path == "full_repipeline"
```

## Dashboard run apply (slice 3)

`AgentOrchestrator.run()` builds a bounded facts mapping from the already-resolved StockScope (`entry_kind=run`, `scope_mode`, codes) plus an optional explicit context `user_mode_override`. It does not read env/Settings, `report_type`, or skills. After an accepted route it sets `self.mode` (and matching mode-budget limits) for that pipeline only.

```python
from src.agent.orchestrator import AgentOrchestrator

orch = AgentOrchestrator(tool_registry=registry, llm_adapter=adapter, mode="quick")
result = orch.run("analyze", {"stock_code": "600519"})
assert orch.mode == "quick"  # constructor mode restored
```

Rejected projection/route does not call `_execute_pipeline`. Chat is unchanged.

## Remaining work (#1120 stays open)

Landed: slice 1 rules library; slice 2 structured fact projection; slice 3 dashboard `run()` apply (fail-closed, constructor mode restored).

Still remaining:

- Wire the projector + router into factory / native adapter / analysis and Chat entry points (per-run decisions, not process-wide mode).
- Chat `incremental_tool` must actually skip `_execute_pipeline` (AC3). Chat remains not wired and still always re-pipelines.
- Record the secret-free decision on run-local metadata (AC4); episode persistence must not collide with #1511.
- Outcome bias from miss rates belongs to #1091 / #1106 and must stay threshold-gated.

Rollback: revert the `run()` apply, then delete the library modules, tests, changelog fragment, and these pages. No migration and no config keys.
