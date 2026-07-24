# Agent Soul Contract

The Agent Soul is StockPulse's owner-controlled behavioral charter. It is
always active in the Native Agent runtime and is not a user-selectable Persona,
a trading Skill, memory, or a replacement for `StrategyEngine`.

## Source And Identity

`src/agent/soul.py` is the only normative Soul source. It owns:

- `AGENT_SOUL_VERSION`: the semantic charter version.
- `AGENT_SOUL_CHARTER`: the canonical UTF-8 charter text.
- `AGENT_SOUL_HASH`: `sha256:` plus the lowercase SHA-256 digest of the exact
  UTF-8 bytes in `AGENT_SOUL_CHARTER`.
- `compose_agent_soul_prompt()`: the shared, fail-closed system-prompt composer.

Any normative change to evidence, risk, tool, authority, or refusal behavior
must update the charter and bump its semantic version. Formatting or code
changes that do not alter the canonical charter text do not require a version
bump. The content hash changes automatically with the canonical text. Historical
version/hash pairs are not rewritten or backfilled.

The composer accepts an already-composed prompt only when the exact canonical
Soul block is its prefix. A Soul boundary marker in Skill, Persona, history, or
other custom content is rejected instead of being treated as proof that the
Soul is installed.

## Assembly Surfaces

The same composer is used for every in-scope Native system prompt:

| Surface | Assembly authority |
| --- | --- |
| Single dashboard run | `AgentExecutor.build_run_messages()` |
| Multi specialists and Decision | `BaseAgent._build_messages()` |
| Single Chat | `AgentExecutor.chat()` |
| Multi-symbol Chat synthesis | `AgentOrchestrator._synthesize_multi_symbol_chat()` |

The experimental PydanticAI Single-run bridge reuses
`AgentExecutor.build_run_messages()`, so it consumes the same prompt without a
second Soul source. This contract does not enable that experimental runtime.

Each assembled system prompt contains the canonical Soul block exactly once.
Prompt assembly does not add tools, change stock scope, bypass outbound policy,
or modify model/provider routing.

## Precedence And Authority

For behavioral conflicts, precedence is:

1. Soul evidence, risk, tool, authority, and refusal rules.
2. Optional Persona tone and research stance.
3. Stage-specific task and output instructions.
4. Skill strategy criteria.

A lower layer can narrow or add requirements but cannot weaken a higher layer.
Personas remain optional and are not implemented by this contract. Skills remain
content inputs. `ToolSurface` remains the only tool permission/scope authority,
and `StrategyEngine` remains the only structured multi-strategy partition and
synthesis authority.

Future system-prompt stages, including a bounded Critic, must import
`compose_agent_soul_prompt()` rather than copy the charter or create another
precedence rule.

## Run Metadata

`AgentRuntimeFacts` records `soul_version` and `soul_hash` on Single, Multi, and
Chat results. Agent analysis runs also project those two low-sensitivity fields
to `analysis_history.context_snapshot.agent_runtime` when context snapshots are
enabled. This lets a historical analysis identify the charter used without
persisting prompts, model reasoning, secrets, or raw tool payloads.

This is additive metadata. Existing records without `agent_runtime` remain
valid and mean that the historical Soul identity was not recorded.

## Compatibility And Rollback

The Soul adds a fixed system-prompt token cost but does not add configuration,
database columns, migrations, Persona selection, tools, or runtime
self-modification. Revert the introducing change to roll it back. Existing
low-sensitivity version/hash values in historical context snapshots require no
data cleanup.
