# Offline Analysis Quality Panel Harness

**Status**: Phase A (issue [#617](https://github.com/SiinXu/stock-pulse-ai/issues/617))  
**Related broader tracker**: [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252) (financial agent evaluation framework)  
**Not this work**: Agent self-improvement epics [#215](https://github.com/SiinXu/stock-pulse-ai/issues/215) / [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252) beyond Phase A linkage

## Purpose

Provide a **network-free, fixed-input** panel that scores analysis *outputs* for:

- factual numeric consistency with frozen fixture inputs
- source / as-of presence **or** explicit gap markers
- stable public report structure (`report-v1` and content-integrity fields)
- non-empty risk surfaces and absence of traceback leakage patterns

The panel answers engineering trust questions. It does **not** claim market alpha.

## Layout

| Path | Role |
| --- | --- |
| `tests/fixtures/analysis_quality/manifest.json` | Panel catalog (3–5 cases) |
| `tests/fixtures/analysis_quality/cases/*.json` | Per-case frozen inputs, report payload, expectations |
| `tests/analysis_quality/panel_loader.py` | Manifest/case loader |
| `tests/analysis_quality/assertions.py` | Deterministic structural checks |
| `tests/analysis_quality/test_offline_panel.py` | pytest entry (`unit` + `quality_benchmark`) |
| `scripts/run_analysis_quality_panel.sh` | Local deterministic runner (when present) |

## What is asserted

| Check | Behavior |
| --- | --- |
| Schema parse | `AnalysisReportSchema` accepts the public `report` object |
| Schema version | Expects `report-v1` (additive version tag already on main) |
| Content integrity | Reuses `check_content_integrity` on projected `AnalysisResult` |
| Risk surface | Non-empty `risk_warning`; list-typed `dashboard.intelligence.risk_alerts` |
| Numeric consistency | Paths under `expectations.numeric_paths` must match report values **and** bound `frozen_inputs.market_data` fields (report+expectation collusion cannot invent prices) |
| Sources | Present sources named or as-of stamped in `data_sources` |
| Gaps | Each `expectations.required_gaps` token must appear in report text |
| Leakage | No traceback / common exception-leak patterns in string leaves |

## What is **not** claimed

- Strategy returns, ranking quality, or market alpha
- Live vendor SLA or free-data accuracy
- Subjective LLM “quality scores” as a merge gate
- Prediction-vs-actual tracking ([#449](https://github.com/SiinXu/stock-pulse-ai/issues/449) / [#466](https://github.com/SiinXu/stock-pulse-ai/issues/466))
- Report evidence strata ([#616](https://github.com/SiinXu/stock-pulse-ai/issues/616)) until that contract lands; pre-strata public fields only
- Agent self-improvement / training loops ([#215](https://github.com/SiinXu/stock-pulse-ai/issues/215), broader [#252](https://github.com/SiinXu/stock-pulse-ai/issues/252))

## How to add a panel case

1. Keep the panel **small** (prefer 3–5 cases unless a maintainer expands the budget).
2. Copy an existing file under `tests/fixtures/analysis_quality/cases/`.
3. Fill:
   - `frozen_inputs` — synthetic market/news/fundamentals and `sources` presence/gap metadata
   - `report` — public report structure only (do not edit production templates)
   - `expectations` — `numeric_paths`, `required_source_keys_present`, `required_gaps`, optional `required_substrings`
4. Register the case in `manifest.json` `cases` list with `id` + `file`.
5. Run:

```bash
./scripts/run_analysis_quality_panel.sh
# equivalent:
python -m pytest -m "not network and quality_benchmark" tests/analysis_quality -q
```

6. Prefer multi-market coverage (A / HK / US) and offline scenarios such as normal session, missing provider fields, conflicting headlines, and limited fields.



## Local runner

Use the thin wrapper for a deterministic local run:

```bash
./scripts/run_analysis_quality_panel.sh
```

Equivalent direct invocation:

```bash
python -m pytest -m "not network and quality_benchmark" tests/analysis_quality -q
```

The runner:

- selects only `quality_benchmark` tests that are also offline (`not network`)
- uses a temporary `DATABASE_PATH` so local state is not touched
- never performs live LLM or network calls
- is suitable for maintainer laptops and optional non-blocking automation

It is **not** a required live-scoring CI gate.

## pytest markers

- `quality_benchmark` — this panel only
- Included in the default offline suite via `pytest -m "not network"` (no `network` mark on these tests)

## CI policy

- **Default backend gate** may run these tests because they are offline and deterministic.
- **Do not** make live LLM quality scoring a required CI job.
- Optional local/nightly wrappers should stay non-blocking if they ever call models.

## Relation to other evaluation work

| Issue | Relationship |
| --- | --- |
| #617 | This harness (Phase A) |
| #252 | Parent / broader evaluation framework; Phase A is a linked slice, not a replacement |
| #215 | Agent self-improvement — out of scope here |
| #616 | Report strata — adapt assertions after merge; until then pre-strata only |
