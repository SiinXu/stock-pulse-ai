# Agent ToolSurface (deny-by-default)

Status: living contract for Agent tool registration and execution.
Issue: [#1077](https://github.com/SiinXu/stock-pulse-ai/issues/1077).

**Chinese**: [agent-tool-surface_CN.md](agent-tool-surface_CN.md)

Canonical implementation: `src/agent/tools/surface.py`.
Compatibility import: `src.agent.tool_surface` (re-export only).

## Required call chain

```text
ToolRegistry.resolve / bind_definition
  → ToolSurface.execute_tool (authz, timeout, audit)
    → implementation handler
```

Production runtimes reach that chain only through `BoundToolSession.execute`:

- Native runner (`src/agent/runner_parts/tools.py`)
- AgentExecutor / `run_agent_loop`
- PydanticAI toolset (`src/agent/runtime/pydantic_ai_toolset.py`)

`ToolRegistry.execute` is permanently disabled (`direct_tool_execution_disabled`).
Unregistered names and missing capabilities fail closed before the handler starts.

## New tool checklist

Every new Agent tool must declare all four items in
`src.agent.tools.surface.NEW_TOOL_CHECKLIST`:

| Item | Requirement |
| --- | --- |
| `permission` | `ToolPolicy.declared(...)` with a non-empty subset of `SUPPORTED_AGENT_TOOL_CAPABILITIES`. Missing grants return `permission_denied`. |
| `timeout` | Honor `ToolAccessContext.timeout_seconds` / `deadline_monotonic`. Missing `deadline_monotonic` or `cancelled_check` attributes fail closed (`AttributeError`); do not getattr them into an unlimited fence. `None` still means no absolute deadline / no cancel probe. Do not add a private wait that bypasses the surface fence. |
| `audit` | Let ToolSurface emit `build_tool_audit` on success and denial. Do not log raw secrets or untrusted document bodies. |
| `hitl_need` | Tools do **not** add a parallel approval path. High-risk recommendation overrides stay on the existing HITL risk gate (`docs/human-approvals_EN.md`). Default is no tool-level HITL. |

## Registration owners

| Owner | Path | Notes |
| --- | --- | --- |
| Process registry | `src/agent/runtime_assembly.py` `get_tool_registry()` | Built-in data / analysis / market / backtest tools, then plugin flush, then optional tools |
| Plugin `agent_tool` | `src/plugins/agent_tools.py` | Registers `ToolDefinition` objects only; live calls still go through ToolSurface |
| `@tool` decorator | `src/agent/tools/registry.py` | Registers on the default registry; not a production executor path |
| Optional factories | `src/agent/tools/{search,multimodal,earnings_transcript,valuation,ocr,kronos}_tools.py` | Configuration-gated; still ToolSurface-owned |

Built-in modules remain beside the registry (`src/agent/tools/*.py`). A physical
`src/agent/tools/builtins/` move is deferred: it would rewrite
`runtime_assembly` and many import / patch targets outside this issue's file
boundary.

## Compatibility import and patch targets

Keep these working:

- `from src.agent.tool_surface import ToolSurface, build_tool_error_result, validate_tool_parameter_value`
- Logger name `src.agent.tool_surface`
- Canonical patch target for outbound URL probes: `src.agent.tools.surface.validate_outbound_url`

Prefer new code importing `src.agent.tools.surface`.

## Deferred direct-call surfaces

| Surface | Why it remains | Owner |
| --- | --- | --- |
| `ToolDefinition.handler(...)` on a registered tool | Plugin contract tests for issue #539 explicitly allow load-time handler probes and must not claim a sealed live-agent path | Plugin / #539 |
| Unregistered `build_*_tools()` handler unit tests | Implementation shape tests; not a production executor entry | Tool module tests |
| MCP tools | Separate registry by design (`src/mcp_server/`) | MCP |
| Planning-loop invoker | Caller-supplied; production callers must wrap `ToolSurface.execute_tool` | Planning |

A registered handler called without going through ToolSurface does **not** set
`tool_surface_dispatch_authorized()`. Production runner / executor dispatch does.
Do not treat a green handler unit test as proof of ToolSurface authorization.

## Related

- [Security baseline](security-baseline.md)
- [Human approvals (HITL)](human-approvals_EN.md)
- [Plugin development guide](plugin-development-guide.md)
- [Alternative-data plugin contract](alternative-data-plugin-contract.md)
- [Shared runtime session contract owners](runtime-session-contract-owners.md) — BoundToolSession / ToolAccessContext fields and test-double obligations
