# A-share specialist roles (Refs #192)

Default-off research Skills for China A-share policy, capital flow, and
microstructure. They reuse the existing Skill / Multi-Agent specialist path and
report synthesis; they do not add a second analysis engine.

## Framework choice (W17 / Persona)

**Decision: ship on the existing Skill mechanism first.**

| Option | Choice |
| --- | --- |
| Wait for a separate Persona runtime (W17 / broader #119 surface) | **No** — would block delivery while investment personas already ship as YAML Skills |
| Use current Skill YAML + specialist path, leave migration hooks | **Yes** |

Migration hooks if a later Persona host arrives:

1. Keep stable Skill ids: `ashare_policy_catalyst`, `ashare_capital_flow`,
   `ashare_microstructure`.
2. Re-wrap only the host/UI surface; do not rename ids or break
   `AGENT_SKILLS` / request `skills` lists.
3. Optional later move under `strategies/personas/` is content packaging only;
   runtime authority remains `SkillManager` + `StrategyEngine` + `ToolSurface`.

## Skills

| Id | Display name | Role |
| --- | --- | --- |
| `ashare_policy_catalyst` | A-share Policy & Catalyst | Policy / regulation / event catalysts |
| `ashare_capital_flow` | A-share Capital Flow | Main-force flow, volume confirmation, chip context |
| `ashare_microstructure` | A-share Microstructure Rules | T+1, limit bands, auction and tradability caveats |

Each Skill declares:

- `default_active: false` / `default_router: false` (empty `AGENT_SKILLS` → no change)
- `required_tools` limited to **existing** Agent tools
- Explicit **data dependency** tables and **fail-soft** degradation copy
- A-share-only scope; non A-share → `out of scope`
- Evidence vs interpretation separation in the output contract

## Enablement

```bash
# Manual skill list (example)
AGENT_SKILL_ROUTING=manual
AGENT_SKILLS=ashare_policy_catalyst,ashare_capital_flow,ashare_microstructure

# Specialist path so skill opinions can enter multi-agent synthesis
AGENT_ARCH=multi
AGENT_ORCHESTRATOR_MODE=specialist
```

Request fields that already accept `skills` can pass the same stable ids.
Activation puts Skills into the resolved active catalog; routing still applies
the existing max-three specialist cap.

## Report path

No new report schema is introduced. When Multi / specialist analysis runs with
these Skills selected, opinions enter the existing Skill opinion /
`strategy_synthesis` report section used by other strategies and personas.

## Data honesty

| Feed | Typical tool | Missing behavior |
| --- | --- | --- |
| Policy / news | `search_comprehensive_intel`, `search_stock_news` | `evidence: unavailable`; no invented agencies or dates |
| Capital flow | `get_capital_flow` | `not_supported` / error → flow unavailable; no invented northbound or dragon-tiger seats |
| Chip | `get_chip_distribution` | Skip chip health claims |
| Quote / history | `get_realtime_quote`, `get_daily_history` | Cannot score limit proximity or multi-day ladders |

## Non-goals

- New data providers or dragon-tiger / northbound APIs
- Auto-enable on every A-share run
- Replacing DecisionAgent or Risk override authority
- Applying A-share limit/T+1 language to HK/US/crypto

## Rollback

Remove or disable the three YAML files / revert the introducing PR, or leave
them unloaded by keeping `AGENT_SKILLS` empty (default). No persistent store.

## Related

- Issue [#192](https://github.com/SiinXu/stock-pulse-ai/issues/192)
- Related personas / committee: [#119](https://github.com/SiinXu/stock-pulse-ai/issues/119),
  [Investment Committee Mode](investment-committee-mode_EN.md)
- Crypto specialist precedent: [crypto-market-support.md](crypto-market-support.md)
- Strategy authoring: [strategies/README.md](../strategies/README.md)
