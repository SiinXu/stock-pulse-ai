# Investor Personas and Research Stances

[中文](investor-personas.md) | [English](investor-personas_EN.md)

Issues [#119](https://github.com/SiinXu/stock-pulse-ai/issues/119) and [#467](https://github.com/SiinXu/stock-pulse-ai/issues/467).

Personas are **structured data**, built on:

1. **Investment lenses** — Skill YAML under `strategies/personas/`
2. **Research stances** — optional tone presets via config / request / personal investment framework `research_stance`

Default **off**. Famous names are **style-reference labels only**.

## Investment lenses (#119)

| Skill id | Style references only |
| --- | --- |
| `persona_value_moat` | buffett-style |
| `persona_mental_models` | munger-style |
| `persona_contrarian_deep_value` | burry-style |
| `persona_disruptive_growth` | disruptive-growth-style |
| `persona_tail_risk` | tail-risk-style |

Enable via `AGENT_SKILLS`, Investment Committee mode, or request `personas`.

## Research stances (#467)

Presets: `rational_analyst`, `risk_guardian`, `long_term_compounder`.

Priority: request > active framework `research_stance` > `AGENT_RESEARCH_PERSONA` / `AGENT_RESEARCH_PERSONA_CUSTOM`.

When active: analysis/Agent prompts receive a data-rendered section; reports may label `dashboard.active_research_persona`.

## Compliance

Simulated research only. Not affiliation/endorsement. Not investment advice.

## Related

- [Personal Investment Framework](personal-investment-framework_EN.md)
- [Investment Committee Mode](investment-committee-mode_EN.md)
- [Agent Soul](agent-soul.md)
