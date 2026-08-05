# Skill Opinion Outcome Evaluation

## Scope

This feature ports the attributable strategy-skill outcome data plane from
upstream commits `85ded1d7`, `8c22263f`, and `03bae035` into StockPulse. It
records the canonical signal and confidence of each individual skill, evaluates
that immutable sample against later locally stored daily bars, and exposes
sample-sufficiency-gated performance statistics.

The first StockPulse version is deliberately offline and read-only with respect
to market data. It never fetches or refills prices, never reads the final Agent
decision as a substitute for an individual skill opinion, and does not alter
runtime aggregation weights.

## Configuration

| Key | Default | Effect |
| --- | --- | --- |
| `SKILL_OPINION_RECORDING_ENABLED` | `false` | When off, analysis never writes skill-opinion samples. When on, valid skill opinions are recorded after strategy aggregation when `analysis_history_id` is already bound on the agent context, and saved reports are materialized after analysis history is persisted. Aggregation weights and analysis output remain unchanged either way. |

The default-off gate for Bayesian feedback belongs to the separately tracked
weighting phase ([#714](https://github.com/SiinXu/stock-pulse-ai/issues/714))
rather than this recording flag.

## Runtime wiring (V0)

Production callers:

1. **Config-gated sample recording** after skill aggregation
   (`AgentOrchestrator._run_strategy_engine` →
   `_maybe_record_skill_opinion_samples`) and after analysis history save
   (`maybe_materialize_after_history_save`). Recording failures are logged with
   `broad-exception: fallback_recorded` and never fail analysis.
2. **Authenticated read/run API** under `/api/v1/skill-outcomes` (administrator
   session contract shared with neighboring `/api/v1/*` routes):
   - `POST /run` — explicit offline materialize + evaluate trigger
   - `GET /` — recent outcomes
   - `GET /stats` — sample-sufficiency-gated performance buckets
   - `GET /samples` — recent low-sensitivity samples (no reasoning/model payloads)

### Evaluation cadence (V0)

**Explicit API trigger only.** V0 does not add scheduler infrastructure or piggyback
a new background job. Operators (or follow-up automation) call
`POST /api/v1/skill-outcomes/run` when local daily bars are available. The run
endpoint materializes missing samples from saved reports and evaluates a bounded
set of outcome keys (`limit` counts keys, not samples).

## Upstream-to-StockPulse design mapping

| Upstream responsibility | StockPulse adaptation | Reason |
| --- | --- | --- |
| ORM records added directly to `src/storage.py` | Additive, ordered migration under `src/migrations/` plus SQL-backed repositories | StockPulse owns post-baseline schema changes through the explicit migration registry. |
| `SkillOpinionFact` added to agent runtime facts and written by the core pipeline | Lazy, idempotent projection of `dashboard.strategy_synthesis.supporting_skills` and `opposing_skills` from an already persisted analysis report | The agent runtime and core persistence stage are outside this port's writable boundary. Saved reports already contain the required low-sensitivity canonical signal and confidence fields. |
| Pure evaluator under `src/core/` | Pure evaluation types and rules under `src/schemas/`, orchestrated by a service | This preserves the fork's `services -> repositories -> schemas` dependency direction and adds no service-to-core back-edge. |
| Shared backtest start/window resolver | Outcome-owned exact-start resolver over persisted `market_phase_summary.effective_daily_bar_date` and local `stock_daily` rows | The port must not modify the sibling-owned backtest service/repository and must not guess an earlier bar or fetch network data. |
| Outcome repository and service | New outcome repository and service modules | Outcome identity and terminal-state immutability remain unchanged. |
| Performance statistics service | New read-only performance service | Each `skill_id + horizon + engine_version` bucket keeps its own sufficiency gate. |
| Read-only API | Authenticated `/api/v1/skill-outcomes` (stats, samples, outcomes, explicit run) | Tracked by [#713](https://github.com/SiinXu/stock-pulse-ai/issues/713). Web UI remains follow-up. |
| Bayesian outcome weights (`831ada53`) | Deferred to [#714](https://github.com/SiinXu/stock-pulse-ai/issues/714) | Runtime integration requires existing Agent aggregator and config-registry changes outside this port's writable boundary. |
| Decision-profile calibration (`aa68d45d`) | Deferred to [#715](https://github.com/SiinXu/stock-pulse-ai/issues/715) | The upstream change extends existing DecisionSignal repository/service/API contracts and Web UI, which are outside this V0 scope. |
| Reassessment persistence (`487e49e5`) | Already present on `main` | StockPulse already supports `persist_status=created/existing/refreshed`; duplicating it would create a parallel contract. |

## Data model

`skill_opinion_samples` is immutable and unique by
`(analysis_history_id, skill_id, sample_schema_version)`. It stores only the
history identifier, stock code, skill identifier, canonical signal, confidence,
optional version/horizon compatibility fields, optional data-quality level,
and timestamps. Reasoning and arbitrary model payloads are not copied.

`skill_opinion_outcomes` is unique by
`(skill_opinion_sample_id, horizon, engine_version)`. Supported horizons are
`1d`, `3d`, `5d`, and `10d`. The states are:

- `pending`: the authoritative start bar or enough future bars are not yet
  stored; the row may be retried.
- `evaluated`: a bullish or bearish opinion produced a `hit` or `miss`.
- `observational`: a `hold` opinion had a complete price window but has no
  directional correctness.
- `unable`: persisted identity or date metadata is permanently invalid.

Only `pending` rows may be updated for the same engine version. Terminal rows
are immutable. A rule change therefore requires a new engine version.

## Evaluation contract

The analysis date comes from `context_snapshot.enhanced_context.date`, falling
back to the history creation date only when it is absent. The start date must
be the persisted `market_phase_summary.effective_daily_bar_date`, must be a
valid ISO date, and cannot be later than the analysis date. The repository then
requires an exact local daily bar for that date and keeps the start and all
forward bars on one stored stock-code shape.

An explicitly present but invalid analysis date is terminal `unable`; it is not
silently replaced with the history creation date.

`strong_buy` and `buy` are bullish; `strong_sell` and `sell` are bearish.
Directional return must be strictly positive to count as a hit, so a zero
return is a miss. `hold` becomes observational only after the complete window
exists.

Candidate scheduling is bounded by outcome keys rather than samples. Missing
and pending keys are ordered by their creation or last-attempt time. Retried
pending keys therefore rotate behind other currently older candidate keys.

## Statistics contract

Statistics are grouped independently by `skill_id`, horizon, and engine
version. A bucket must contain at least 30 `evaluated` rows before rates or
average directional return are published. `pending`, `observational`, and
`unable` rows remain visible as counts but cannot unlock metrics or lend samples
to another bucket.

For a sufficient bucket, hit and miss rates use `hit + miss` as the denominator.
The unable rate uses terminal rows (`evaluated + observational + unable`) so
temporary pending rows do not dilute permanent metadata failures.

## Limitations and follow-up scope

- With `SKILL_OPINION_RECORDING_ENABLED=false` (default), analysis has no sample
  side effects; explicit `POST /skill-outcomes/run` can still materialize and
  evaluate for administrators.
- Histories saved without a structured skill synthesis create no samples.
- Structured syntheses with no valid individual opinions also create no samples;
  later bounded scans may reconsider those histories.
- Histories without an authoritative persisted effective daily-bar date are
  marked unable rather than guessed from an arbitrary local bar.
- V0 ships the authenticated API; the Web surface for buckets/thresholds remains
  open under [#713](https://github.com/SiinXu/stock-pulse-ai/issues/713).
- Bayesian runtime weighting and decision-profile outcome calibration remain
  default-neutral until [#714](https://github.com/SiinXu/stock-pulse-ai/issues/714)
  and [#715](https://github.com/SiinXu/stock-pulse-ai/issues/715) land.

The migration is additive. Code rollback does not remove either table, so
collected facts remain available if the feature is reintroduced.

