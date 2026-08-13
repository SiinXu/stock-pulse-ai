# Report sensitivity scenario library

Versioned scenario packs for report sensitivity analysis (Issue [#1136](https://github.com/SiinXu/stock-pulse-ai/issues/1136), epic [#1127](https://github.com/SiinXu/stock-pulse-ai/issues/1127)).

## Purpose

Users need reusable macro / industry paths (rate, FX, sector shocks) without hand-editing each what-if turn or the Agent Soul. The library:

1. Ships built-in presets plus user-saved custom scenarios.
2. **Reuses the existing Chat what-if execution channel** (`context.what_if`) — it does not invent a second agent path.
3. Projects **deterministic risk framing** so tests can assert that switching scenarios changes expected emphasis.
4. Always labels outputs as **hypothetical**; they must not mix with baseline report conclusions.
5. **Cannot weaken Soul** evidence / refusal / risk rules.

## Catalog identity

| Field | Source |
| --- | --- |
| `catalog_version` | `SCENARIO_LIBRARY_VERSION` in `src/agent/scenario_library.py` |
| `catalog_hash` | SHA-256 over built-in scenario hashes + catalog version |
| `scenario_hash` | SHA-256 of one normalized scenario payload |
| `soul_version` / `soul_hash` | Live values from `src/agent/soul.py` (read-only) |

Catalog version is visible in Chat UI and in the report-sensitivity markdown appendix.

## Built-in presets

| Id | Category | Assumptions |
| --- | --- | --- |
| `rate_hike_100bp` | rate | interest_rate up 100 bp |
| `rate_cut_50bp` | rate | interest_rate down 50 bp |
| `fx_usd_cny_up_5` | fx | FX USD/CNY +5% |
| `fx_usd_cny_down_5` | fx | FX USD/CNY -5% |
| `industry_shock_down_15` | industry | sector_shock down 15% |
| `market_down_10` | market | index_move down 10% |

## Execution channel

Applying a library scenario builds the same `what_if` payload used by Issue #130 / PR #952:

```json
{
  "enabled": true,
  "turn_index": 1,
  "max_turns": 5,
  "assumptions": [{ "dimension": "interest_rate", "direction": "up", "magnitude": 100 }],
  "scenario_id": "rate_hike_100bp",
  "catalog_version": "1.0.0",
  "scenario_hash": "…"
}
```

Isolation matches what-if:

- `preview_only`
- no `AnalysisHistory` / `DecisionSignal` / Agent memory writes
- answers must start with `[HYPOTHETICAL SCENARIO]`

When `scenario_id` is present, the prompt also injects the library risk-framing appendix (emphasis + tighter constraints) and the catalog version.

## Report sensitivity projection

`project_report_sensitivity(scenario_id)` returns a structured projection:

- `mode: hypothetical_preview`
- markers + disclaimer
- `risk_framing` (uncertainty, position sizing, section deltas)
- `report_diff.summary` containing `[HYPOTHETICAL SCENARIO]`
- `baseline_isolation.mix_with_baseline_conclusions: false`
- `soul_charter_unchanged: true`

`format_report_sensitivity_markdown()` renders an appendix section for reports or copy/export. The Web `ReportScenarioSensitivityPanel` shows the same framing in Chat when a library scenario is selected.

### Jinja report wiring

When `report_renderer.render(..., extra_context=...)` includes either:

```json
{ "report_sensitivity": { "scenario_id": "rate_hike_100bp" } }
```

or top-level `"scenario_id": "rate_hike_100bp"`, the renderer resolves a **hypothetical appendix** into `scenario_sensitivity_markdown` for `report_markdown.j2` / `report_brief.j2` / `report_wechat.j2`.

- Absent request → baseline report unchanged.
- Appendix is always marked `[HYPOTHETICAL SCENARIO]` and must not rewrite Decision Card / baseline conclusions.
- Unknown ids yield no appendix (fail soft).

### Catalog SSOT

Built-in scenarios live in `src/agent/scenario_library_builtins.json`. The Web mirror `apps/dsa-web/src/components/chat/scenarioLibraryBuiltins.json` must stay **byte-identical** (`assert_builtin_catalog_sync`).

### Custom scenarios

- Web localStorage customs send **assumptions only** (no `scenario_id`) so the server never receives an unknown library id.
- Server process-memory customs via `save_custom_scenario` remain available to Python callers only in this delivery.

## Custom scenarios

- **Backend process memory**: `save_custom_scenario` / `delete_custom_scenario` (bounded, cannot overwrite built-ins).
- **Web localStorage**: key `dsa.scenarioLibrary.custom.v1` for browser-side save/reuse of the current what-if draft.

Custom payloads that attempt Soul-weakening keys or text (`weaken_soul`, `skip_refusal`, `ignore_evidence`, looser risk posture, …) are rejected.

## Soul precedence

Soul remains authoritative (see [agent-soul.md](agent-soul.md)). Scenarios may only **add** assumptions and **tighten** risk framing. They never:

- edit `AGENT_SOUL_CHARTER`
- disable refusals or evidence honesty
- present hypothetical paths as baseline recommendations

## Related

- Chat what-if mode: Issue #130 / PR #952
- DCF sensitivity panel: PR #1021 (valuation matrix; orthogonal to macro scenario packs)
- Portfolio stress catalog: [portfolio-stress-test_EN.md](portfolio-stress-test_EN.md) (deterministic portfolio PnL; separate product surface)
