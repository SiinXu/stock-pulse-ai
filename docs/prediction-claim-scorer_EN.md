# Deterministic Prediction Claim Scorer

**Status**: Forecasting track A5 (Issues [#1111](https://github.com/SiinXu/stock-pulse-ai/issues/1111) / [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107))

**Chinese**: [prediction-claim-scorer.md](prediction-claim-scorer.md)

**Depends on**: A1 prediction contract ([prediction-contract_EN.md](prediction-contract_EN.md))

## Purpose

Given fixed structured claims and market actuals, produce **deterministic** per-claim outcomes and aggregates for agent quality operations (research / calibration). This is **not** a returns-guarantee product surface.

```text
ClaimScorer.score(claims, actuals, config) → claim_results + aggregate
```

* No I/O, wall-clock, or randomness inside the scorer.
* Same inputs always yield the same `to_dict()` payload.
* Provider / actuals gaps → `data_unavailable` with `score=None` — never a fabricated hit.

## Module map

| Path | Role |
| --- | --- |
| `src/schemas/prediction_record.py` | A1 claim types (`PredictionClaim` + payloads) |
| `src/schemas/prediction_claim_scoring.py` | Actuals / config / outcome / aggregate records |
| `src/services/claim_scorer.py` | Pure `ClaimScorer` |
| `tests/services/test_claim_scorer.py` | Table-driven + determinism tests |

Persistence, extraction, actuals fetch, and the resolver job are separate issues. Those components project into A1 claims + `ClaimActuals` before calling the scorer.

## Supported claim types (A1)

| `type` | Payload (A1) | Actuals required |
| --- | --- | --- |
| `direction` | `direction`: `up` \| `down` \| `sideways` | `start_price`, `end_price` |
| `return_bucket` | `low_pct` &lt; `high_pct`, inclusive flags | `start_price`, `end_price` |
| `level_break` | `side`, `level`, `reference` | path high/low required to prove a miss; `end_price` may prove a hit/near-touch (+ `start_price` for pct reference) |
| `vol_regime` | `regime` label | `vol_regime` |
| `custom` | `metric`, `operator`, machine `expected` | `metrics[metric]` |

`price_range` from early product notes is expressed as `custom` with `operator=in_range` over a price metric (typically `end_price`).

Optional A1 `confidence` ∈ [0, 1] participates in aggregate calibration only; it never changes the hard hit/partial/miss label.

## Outcomes and scores

| Outcome | Numeric score | Meaning |
| --- | --- | --- |
| `hit` | `1.0` | Claim matched under the type rules |
| `partial` | `0.5` | Near-miss / sideways boundary / adjacent magnitude or vol |
| `miss` | `0.0` | Valid claim clearly missed |
| `data_unavailable` | `None` (excluded from rates) | Missing/invalid actuals, provider failure, or invalid claim payload |

### Boundary rules (stable)

* **Direction sideways band**: `|return_fraction| <= sideways_epsilon` is sideways (inclusive; default `0.001` = 0.1%). Config key `flat_epsilon` is an accepted alias. Predicting sideways vs a non-sideways move (or the reverse) is `partial`; opposite directions are `miss`.
* **Return bucket**: honors payload `inclusive_low` / `inclusive_high` (A1 default half-open `[low, high)`). Distance to the interval within `bucket_partial_margin_pct` (default `1.0` percentage point) is `partial`. Bound value `0.0` is a valid finite bound.
  * **Exclusive bound under default margin**: a realized return *exactly* on an exclusive edge has distance `0`. With the default `bucket_partial_margin_pct=1.0` that scores **`partial`**; it is **`miss` only when the margin is `0`**.
* **Level break**: absolute price or `pct_from_as_of_close`. `high >= level` (above) or `low <= level` (below) is `hit`. Near-touch within `level_touch_epsilon * |level|` is `partial`. When the side-specific path extreme is absent, an end close can prove a hit/near-touch, but cannot prove a miss; that case is `missing_path_extreme` / `data_unavailable`.
* **Vol regime**: exact canonical label match is `hit`; adjacent pair among `low`↔`normal`↔`high`↔`elevated` is `partial`. Missing label → `missing_vol_regime`. Non-canonical garbage label (e.g. fetcher typo) → `invalid_vol_regime` / `data_unavailable` — **not** miss.
* **Custom**: deterministic operators `eq|ne|gt|gte|lt|lte|in_range` over `actuals.metrics`. `in_range` is half-open `[expected, expected_high)`.

Invalid claim payloads (A1 validation failure) are `data_unavailable` with `reason=invalid_claim` and a truncated `details.validation_error` string. They are excluded from model hit-rate and calibration rather than being misattributed as model misses.

A4-style actuals mappings are fail-closed: any non-`ok` `status`, `data_unavailable=true`, or `ok=false` is authoritative even if stale price fields are also present. Invalid config (including NaN/Infinity, invalid bin counts, unknown keys, or attempts to override the code-owned scorer version) is rejected before scoring.

## Aggregate + confidence calibration

Over scored claims (`hit`/`partial`/`miss` only):

* `mean_score`, `hit_rate`
* When confidence is present: **soft-label** `brier_score` against targets `{hit:1, partial:0.5, miss:0}` (not classical binary Brier), plus `expected_calibration_error` (equal-width bins on `[0,1]`), and mean confidence on hit vs miss

`data_unavailable` rows never inflate hit rate or calibration denominators.

## Explicit non-goals

* Does not mutate Agent Soul charter or ToolSurface denials.
* Does not invent claims from free-form prose.
* Does not call market providers (see ActualsFetcher / PredictionResolver).
* Does not share labels with offline agent-output eval (`agent_eval_service`) or skill-opinion signal evaluation.

## Config defaults

| Key | Default | Notes |
| --- | --- | --- |
| `sideways_epsilon` | `0.001` | Return fraction sideways band |
| `flat_epsilon` | unset | Alias that overrides `sideways_epsilon` when set |
| `bucket_partial_margin_pct` | `1.0` | Percentage points |
| `level_touch_epsilon` | `0.002` | Relative to absolute resolved level |
| `calibration_bin_count` | `10` | ECE bins |

The code-owned `scorer_version` is `claim-scorer-v1` and is reported on every report; it is not a caller configuration key.

## Verification

```bash
python -m pytest tests/services/test_claim_scorer.py -q
```
