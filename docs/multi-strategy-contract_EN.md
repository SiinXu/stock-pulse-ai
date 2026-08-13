# Multi-strategy contract (EN)

See `docs/multi-strategy-contract.md`.

Default-off flag: `AGENT_MULTI_STRATEGY_DELIBERATION`.

## Structured disagreement handling (#246 / #193)

Default-off flag: `AGENT_DISAGREEMENT_HANDLING`.

When enabled, StrategyEngine and the Decision pre-stage build a structured `disagreement_handling` record that:

1. **Records disagreement points** from role-layer summaries and strategy conflicts (never drops them).
2. **Cross-validates** across role and strategy layers when material conflict is detected (not majority vote).
3. **Escalates** high disagreement to a **split verdict**: forced conservative `hold`, capped confidence, `high_disagreement=true`, `resolution_status=unresolved`.
4. **Surfaces** the record on `dashboard.disagreement_handling` and `strategy_synthesis.disagreement_handling`, rendered in Markdown / WeChat / Notification / History.

The authoritative public record uses `schema_version=disagreement-handling-v1`.
Every public `points[]` item has the same bounded fields across report and alert
consumers: `source`, `kind`, `severity`, `participants`, and `summary_key`.
Consumers must reject missing or unknown schema versions instead of inferring a
record from similarly named raw fields.

Product honesty: unresolved disagreement is a legitimate reported outcome. Escalation must not invent artificial consensus.
