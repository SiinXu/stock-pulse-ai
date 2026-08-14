# Market Regime Detection (Issue #220)

Explainable, rule-based market-regime detection and adaptive analysis focus.

## Scope

- Detect a stock-level **regime label** from existing trend / technical inputs.
- Persist a low-sensitivity `market_regime_context` artifact on the analysis snapshot.
- Inject regime + focus adjustments into ordinary analysis and multi-agent prompts.
- Drive skill routing in `AGENT_SKILL_ROUTING=auto` without black-box classifiers.
- When evidence is missing or conflicting, label **`unknown`** instead of forcing a side.

Out of scope for this slice: dashboard charts, regime-shift alerts, historical regime timelines, ML classifiers.

## Labels

| Label | Meaning | Default risk posture |
| --- | --- | --- |
| `trending_up` | Clear bullish MA / trend stack with supportive strength | `risk_on` |
| `trending_down` | Clear bearish stack with supportive strength | `risk_off` |
| `sideways` | Consolidation / range / weak structure | `neutral` |
| `volatile` | Heavy volume without a clean directional stack | `risk_off` |
| `unknown` | Missing inputs, conflicts, or blocked classification | `unknown` |

These labels align with built-in skill `market_regimes` tags (`trending_up`, `trending_down`, `sideways`, `volatile`, …).

## Artifact contract

Key: `market_regime_context`
Schema version: `market-regime-v1`
Method id: `deterministic_rules_v1`

Important fields:

- `regime`, `status`, `source` (`rules` | `override` | `unavailable`)
- `confidence`, `risk_posture`
- `rules_fired`: rule ids that contributed to the final label
- `evidence[]`: every evaluated rule with `rule_id`, `outcome`, `inputs`, optional `detail`
- `focus_hints[]`: analysis emphasis adjustments for the LLM
- `missing_inputs[]`, optional `override`, `stock_code`, `market`

Traceability rule: given only the persisted artifact, a reader can see which rules matched, which inputs they used, and why the final regime was chosen (see the `decision` evidence entry).

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `MARKET_REGIME_ENABLED` | `true` | Fail-open toggle; when false, emits explicit `unknown`/`unavailable` |
| `MARKET_REGIME_OVERRIDE` | empty | Force `trending_up` / `trending_down` / `sideways` / `volatile` / `unknown` |

Related: `AGENT_SKILL_ROUTING=auto` uses the same detector for skill selection. `unknown` does **not** force a regime-specific skill set (falls back to default skills). Soft `sector_hot` meta remains available as a skill-tag hint.

## Runtime wiring

1. After trend analysis, pipeline builds `market_regime_context` (`src/core/stages/analysis_context.py`).
2. Context is attached to `enhanced_context` / Agent `initial_context`, persisted on `context_snapshot`, and copied onto `AnalysisResult`.
3. Prompt section: `format_market_regime_prompt_section` (ordinary analyzer + agent base messages).
4. Skill router: `SkillRouter._detect_regime` calls `MarketRegimeService` and stores the artifact on `ctx.meta`.

## Source anchors

- Schema: `src/schemas/market_regime.py`
- Detector: `src/services/market_regime_service.py`
- Prompt: `src/market/regime_prompt.py`
- Tests: `tests/services/test_market_regime_service.py`
