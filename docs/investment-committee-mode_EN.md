# Investment Committee Analysis Mode

[中文](investment-committee-mode.md) | [English](investment-committee-mode_EN.md)

Issue [#545](https://github.com/SiinXu/stock-pulse-ai/issues/545). An optional **Investment Committee** mode that activates a curated set of persona Skills through the existing Multi-Agent **specialist** path and `StrategyEngine` synthesis — without a second strategy engine — and emits a structured committee deliberation report section.

## Default off

- Config: `AGENT_INVESTMENT_COMMITTEE_MODE` (default `false`)
- When off: Single / Multi / Chat behavior matches today (no `skills_requested` injection, no `committee_deliberation` field)
- When on: resolve the default persona pack (or request `personas`), write `ctx.meta.skills_requested`, and let the existing `SkillRouter` + `SkillAgent` path run

## How to enable

1. `AGENT_MODE=true` (or an equivalent Agent analysis entry)
2. `AGENT_ARCH=multi`
3. `AGENT_ORCHESTRATOR_MODE=specialist` (persona specialists are inserted before Decision)
4. `AGENT_INVESTMENT_COMMITTEE_MODE=true`

Optional per-request overrides on the analysis context:

| Field | Meaning |
| --- | --- |
| `committee_mode: true/false` | Per-request switch (`false` forces off) |
| `personas: ["persona_value_moat", ...]` | Override the default persona list; providing `personas` alone also activates committee mode |

## Default persona pack

Order matches `default_priority` under `strategies/personas/`:

1. `persona_value_moat` — Value & Moat  
2. `persona_mental_models` — Mental Models  
3. `persona_contrarian_deep_value` — Contrarian Deep Value  
4. `persona_disruptive_growth` — Disruptive Growth  
5. `persona_tail_risk` — Tail Risk  

## Caps and failure isolation

- **Max**: matches the existing specialist concurrent cap — **at most 3** personas actually run; extras are recorded in `personas_truncated` (explicit truncation, not silent drop).
- **Invalid ids**: when a skill catalog is available, unknown ids go to `personas_invalid` / diagnostics — not treated as successful execution.
- **One persona failure**: follows the multi-strategy contract — invalid signals go to Diagnostics; remaining valid opinions can still produce `strategy_synthesis`.
- **Synthesis**: existing `StrategyEngine` only; no parallel “Risk Manager Agent” product surface.

## Report

When the mode is active and analysis completes, the dashboard may include:

```text
dashboard.committee_deliberation  # schema_version: committee-deliberation-v1
```

The payload follows report-strata presentation conventions (gaps/conflicts, model inference, risks/counter-evidence, non-investment-advice disclaimer). Markdown / WeChat templates render it after `strategy_synthesis`. Historical reports without the field stay quiet.

## Cost and disclaimer

- Committee mode runs one SkillAgent pass per selected persona — **expect higher token use and latency**.
- Outputs are simulated research lenses only — **not investment advice**; not affiliated with or endorsed by any named individual or firm.

## Web UI

Web settings / analysis UI for this mode is **out of scope for v1** (deferred). Config and API context fields ship first; a dedicated Web control is a follow-up.

## Rollback

Set `AGENT_INVESTMENT_COMMITTEE_MODE=false` or remove it. No data migration required.
