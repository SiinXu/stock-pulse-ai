# Agent Soul Contract

The Agent Soul is StockPulse's owner-controlled behavioral charter. It is
always applied to the in-scope Native Single, Multi, and Chat system prompts.
It is not a user-selectable Persona, a trading Skill, memory, or a replacement
for `StrategyEngine`.

This Track does not cover `ResearchAgent` and makes no claim that its prompt is
Soul-governed. Extending the charter to Research is a separate contract change
that must define that runtime's assembly and provenance paths explicitly.

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
Soul block is its final section. A Soul boundary marker in system-prompt inputs,
including Skill, Persona, or stage content, is rejected instead of being
treated as proof that the Soul is installed. Multi-Agent assembly also rejects
non-empty string system-role conversation history before composition; malformed
or empty entries keep their prior ignored behavior. User and assistant history
remains supported and is never interpreted as Soul provenance.

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
second Soul source. Its deterministic no-executor path has no system prompt and
therefore reports no Soul identity. This contract does not enable that
experimental runtime.

Each assembled system prompt contains the canonical Soul block exactly once as
its final authoritative section. Prompt assembly does not add tools, change
stock scope, bypass outbound policy, or modify model/provider routing.

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
synthesis authority. Those two authorities are enforced by runtime code rather
than trusting the model to follow prompt text.

The optional bounded Critic uses the same `BaseAgent._build_messages()` path and
therefore imports `compose_agent_soul_prompt()` instead of copying the charter
or creating another precedence rule. It is tool-free and read-only: Critic
output can identify evidence limitations or request one whitelisted stage retry,
but cannot author `strategy_synthesis`, expand ToolSurface, or replace Decision.

## Run Metadata

`AgentRuntimeFacts` records `soul_version` and `soul_hash` only after the
canonical composer ran. Bare results and pre-composition exits do not claim a
Soul identity. Multi runs track composition on their internal `AgentContext`;
the existing runtime-facts builder projects the identity together with all
other low-sensitivity facts only when that context recorded composition.

Soul identity is module-owned rather than accepted by the public
`AgentRuntimeFacts(...)` constructor. The constructor remains available for
non-Soul runtime facts, but direct or equal-looking version/hash input cannot
create publishable identity. Canonical prompt composition and the opaque,
copy-stable Multi context proof are the only inputs accepted by the verified
facts factories. API and history projections use the same non-virtual verifier,
and aggregate cancellation can inherit only an already-verified identity.

The two identity fields have two deliberately different delivery paths:

- Successful saved analysis runs persist them at
  `analysis_history.context_snapshot.agent_runtime` when context snapshots are
  enabled.
- The non-streaming Chat API returns them in the additive
  `ChatResponse.agent_runtime` field when its Single or Multi result recorded
  composition. This response metadata is returned to the caller; it is not a
  second persistence system.

Conversation messages and provider traces do not persist this run identity and
must not be described as durable Soul audit records. Internal Single, Multi,
and Chat results continue to carry `AgentRuntimeFacts` for their immediate
callers without persisting prompts, model reasoning, secrets, or raw tool
payloads.

When the experimental PydanticAI bridge fails after canonical Native prompt
composition, its sanitized terminal result retains the verified identity.
Ordinary failures on the raw no-executor path continue to propagate without
claiming identity.

This is additive metadata. Existing records without `agent_runtime` remain
valid and mean only that the Soul identity was not recorded; callers must not
infer that composition occurred.

## Architecture Decision Boundary

This focused contract stays within [ADR-001 D3](architecture/ADR-001-agent-runtime.md#d3-stockpulse-保持单一业务权威),
which keeps Prompt/Skill, runtime facts, persistence, and public API ownership
inside StockPulse, and [ADR-001 D4](architecture/ADR-001-agent-runtime.md#d4-现有-native-行为保持兼容),
which requires compatible Native behavior. One StockPulse-owned composer and
an additive optional Chat response field strengthen those accepted authorities;
they do not introduce another runtime, composition root, provider route,
persistence schema, tool authority, or strategy engine.

The experimental PydanticAI evidence bridge still consumes the Native Single
prompt authority and remains unavailable through production configuration or
API selection. Because this change implements prompt and provenance mechanics
inside the ownership and topology already accepted by ADR-001, it does not need
a new ADR.

## Compatibility And Rollback

The Soul adds a fixed system-prompt token cost and an optional additive Chat
response field, but does not add configuration, database columns, migrations,
Persona selection, tools, or runtime self-modification. Revert the introducing
change to roll it back. Existing low-sensitivity version/hash values in
historical context snapshots require no data cleanup; clients may ignore the
additive response field.
