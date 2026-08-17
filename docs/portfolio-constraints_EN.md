# Portfolio constraint engine for research proposals

Backend V1 for issue [#1132](https://github.com/SiinXu/stock-pulse-ai/issues/1132).

Proposed research actions and rebalancing scenarios pass through a **deterministic rules engine** before they are labeled constraint-feasible. The engine does **not** execute trades, write the ledger, or replace broker, exchange, or regulatory compliance.

**Research aid only — not investment advice and not broker compliance.**

## What it checks

| Constraint | Blocking when |
| --- | --- |
| Per-name cap | Target weight, or an unsized increase already at the cap, exceeds `max_single_name_weight_pct` |
| Sector cap | Projected sector weight after an increasing action exceeds `max_sector_weight_pct` |
| Blacklist | An increasing action (`buy` / `add`) targets a blacklisted symbol |
| Simple risk flags | An increasing action targets a symbol that carries a configured blocking flag |

Numeric comparisons run in `src/services/portfolio/constraints.py`. LLMs must not compute the caps.

## Verdicts

`evaluate_research_scenario(...)` (and `PortfolioAgent.post_process`) attach:

| Field | Meaning |
| --- | --- |
| `status` | `allow` / `reject` / `hints` |
| `label` / `scenario_label` | `constraint_feasible` or `research_only` |
| `executable` / `is_executable_scenario` / `auto_execute` | Always `false` |
| `not_broker_compliance` | Always `true` |
| `passthrough` | `true` only when no constraints are configured, or no proposed actions exist |
| `constraint_passthrough` / `constraint_passthrough_reason` | Copied onto the live assessment so consumers do not treat a default `constraint_feasible` label as a policy check |

A `constraint_feasible` label means the configured **research** constraints did not block the proposal. It is not permission to send an order.

Violating proposals are labeled `research_only` and are not presented as executable scenarios. `PortfolioAgent` prefixes overwritten suggestion strings with `[research_only]`.

## Configuration

Config is a mapping passed into the gate (tests, `AgentContext.data["portfolio_constraint_config"]`, or `meta`). There is no new environment key in this delivery.

```json
{
  "max_single_name_weight_pct": 25.0,
  "max_sector_weight_pct": 40.0,
  "blacklist": ["XYZ"],
  "blocking_risk_flags": ["halt"]
}
```

- Omitted / empty mapping → explicit pass-through (`passthrough_reason=no_constraints_configured`). The live `PortfolioAgent` path does not load a Settings/env policy in this V1; unless a caller injects `portfolio_constraint_config`, the assessment is labeled `constraint_feasible` with `constraint_passthrough=true`.
- Rebalancing suggestions are the authoritative action source. Position bands are used only when suggestions are empty, so a later band midpoint cannot mask a higher user-visible suggestion target.
- Candidate rows that cannot be normalized (`signal`/`action` missing after aliases) → fail-closed `reject` / `research_only` (`unparseable_proposal`). A truly empty action list remains `allow` with `no_proposed_actions`.
- Malformed values → fail-closed `reject` / `research_only` (`engine_error`), never treated as “no constraints”.
- Missing sector, incomplete sector tags on other holdings, or unavailable current weights on an increasing action → `hints`, not a silent pass. Holdings without a sector tag are not counted as being inside the named sector.
- The default rebalancing payload has no sector map. Sector-cap **blocks** only when sectors are supplied on `portfolio_view`, action rows, or the rebalancing base; otherwise the gate emits a `sector_cap` hint.

## Production wiring

The live research path is `PortfolioAgent.post_process` → `apply_constraints_to_research_assessment` → `evaluate_research_scenario` → `check_proposal_fail_closed`.

The agent may polish narrative text only. Constraint arithmetic stays in the rules engine.

This V1 does **not** change the global portfolio / rebalancing HTTP schema. Web and Desktop consumers keep the existing suggestion-only contract.

## Non-goals

- Broker, exchange, or regulatory compliance
- Auto-execution or ledger mutation
- Settings UI / environment-variable registration (follow-up)
- Changing `GET /api/v1/portfolio/rebalancing-recommendations` response fields

## Rollback

Revert the implementation PR (engine + agent wiring + tests + these docs + changelog fragment). No database migration.
