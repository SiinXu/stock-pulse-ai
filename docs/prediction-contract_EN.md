# Prediction Contract (Structured Forecast Records)

**Status**: A1 contract only (Issue [#1101](https://github.com/SiinXu/stock-pulse-ai/issues/1101); parent Epic [#1107](https://github.com/SiinXu/stock-pulse-ai/issues/1107))

**Chinese**: [prediction-contract.md](prediction-contract.md)

## Purpose

Agent self-evolution needs **checkable predictions**, not free-form narrative. This document defines the strict `PredictionRecord` schema so later stages can resolve horizons, score claims, and write lessons without inventing verifiable content from prose.

This slice is **schema + validation only**. It does **not** extract claims, persist rows, fetch market actuals, schedule resolution, score hits/misses, or adapt Soul / ToolSurface.

## Product rules (from Epic #1107)

| Rule | Contract implication |
| --- | --- |
| System-driven loop later | Schema carries `status` / `resolve_after` for schedulers; no user “verify” button required by the contract |
| No runtime Soul / ToolSurface mutation | `model_meta.soul_version` is provenance only |
| Research / quality-ops framing | Notes and docs must not claim guaranteed alpha |
| Non-parseable prose ≠ claim | Use `status=no_verifiable_claim` + `no_verifiable_reason`; `claims` must be empty |
| Never fabricate hits | Scoring is out of scope here; the contract refuses non-finite numbers and prose-as-claim |

## Schema location

| Path | Role |
| --- | --- |
| `src/schemas/prediction_record.py` | Strict Pydantic models, builders, validators |
| `tests/schemas/test_prediction_record.py` | Unit coverage for success, failure, and boundary paths |

Schema version constant: `prediction-record-v1` (`PREDICTION_RECORD_SCHEMA_VERSION`).

## Record fields

| Field | Required | Description |
| --- | --- | --- |
| `schema_version` | yes | Literal `prediction-record-v1` |
| `prediction_id` | yes | Stable id for this forecast row |
| `run_id` | yes | Analysis / agent run linkage for later reflection |
| `symbol` | yes | Instrument code (no whitespace) |
| `market` | no | Optional market tag (e.g. `CN` / `HK` / `US`) |
| `created_at` | yes | Timezone-aware datetime (normalized to UTC) |
| `as_of` | yes | Session date the forecast is anchored to |
| `horizon` | yes | One of `1d`, `3d`, `5d`, `10d`, `20d` |
| `resolve_after` | yes | UTC-aware earliest resolution time |
| `claims` | conditional | Typed machine-checkable claims (see below) |
| `status` | yes | `pending` \| `resolving` \| `resolved` \| `expired` \| `error` \| `no_verifiable_claim` |
| `source_decision_id` | no | Upstream decision / dashboard identity |
| `model_meta` | no | `mode`, `soul_version`, `skill_ids`, `model_version`, `config_version`, `model_id` |
| `no_verifiable_reason` | when unverifiable | `unparseable_output` \| `prose_only` \| `missing_structured_fields` \| `empty_decision` \| `unsupported_shape` |
| `notes` | no | Research-only text; **never scored** |

### Status vs claims

| Status | Claims | Notes |
| --- | --- | --- |
| `pending` / `resolving` / `resolved` | **≥ 1** typed claim | Eligible for later verification pipeline |
| `no_verifiable_claim` | **must be empty** | Requires `no_verifiable_reason`; skip scoring |
| `error` / `expired` | may be empty | Terminal / fault paths without inventing claims |

Helper: `build_no_verifiable_claim_record(...)` is the supported constructor for unparseable or prose-only outputs.

## Claim types

Only **typed** claims enter the verification pipeline. Each claim has `claim_id`, `type`, `confidence` ∈ [0, 1], and a matching `payload`.

| `type` | Payload | Machine check intent (later stages) |
| --- | --- | --- |
| `direction` | `direction`: `up` \| `down` \| `sideways` | Sign of return vs `as_of` close |
| `return_bucket` | finite `low_pct` &lt; `high_pct`, optional `bucket_id` | Simple return % band |
| `level_break` | `side`, finite `level`, `reference` | Cross absolute price or % from close |
| `vol_regime` | `regime`: `low` \| `normal` \| `high` \| `elevated` | Realized-vol regime label |
| `custom` | `metric`, `operator`, machine `expected` | Explicit operator check only |

### What is rejected

- Extra unknown fields (`extra=forbid`)
- NaN / ±Infinity on any float (`allow_inf_nan=False`)
- Confidence outside `[0, 1]`
- Naive (timezone-less) `created_at` / `resolve_after`
- Free-form prose as `custom.expected` (must be a short machine token or finite number)
- `no_verifiable_claim` rows that still carry claims (would invent verifiability)
- `pending` rows with zero claims (must use `no_verifiable_claim` instead)

`notes` may hold narrative for operators; it is metadata only and must not be promoted into `claims` by A2 extractors.

## Out of scope (follow-on issues under #1107)

| Stage | Responsibility |
| --- | --- |
| A2 | Extractor from structured decision / dashboard fields (not regex on markdown prose) |
| A3 | Persistence + indexes `(status, resolve_after)`, `(symbol, created_at)` |
| A4 | Actuals fetch with `data_unavailable` / retry — never fabricated prices |
| A5–A8 | Scoring, calendar, scheduler, batch coalesce |
| A9–A10 | Post-mortem lessons, eval gate / adapters |

## Usage sketch

```python
from datetime import date, datetime, timezone
from src.schemas.prediction_record import (
    PredictionRecord,
    build_no_verifiable_claim_record,
    validate_prediction_record,
)

# Verifiable pending forecast
record = validate_prediction_record({
    "prediction_id": "pred-1",
    "run_id": "run-1",
    "symbol": "600519",
    "created_at": datetime.now(timezone.utc),
    "as_of": date.today(),
    "horizon": "5d",
    "resolve_after": datetime.now(timezone.utc),
    "status": "pending",
    "source_decision_id": "dec-1",
    "claims": [{
        "claim_id": "c1",
        "type": "direction",
        "confidence": 0.72,
        "payload": {"direction": "up"},
    }],
    "model_meta": {
        "model_version": "…",
        "config_version": "…",
    },
})

# Prose-only / unparseable decision → never invent claims
unverified = build_no_verifiable_claim_record(
    prediction_id="pred-2",
    run_id="run-2",
    symbol="AAPL",
    created_at=datetime.now(timezone.utc),
    as_of=date.today(),
    reason="prose_only",
    notes="Narrative only; left for operators, not scoring.",
)
assert unverified.is_verifiable() is False
```

## Related surfaces (do not reuse as PredictionRecord)

- Free-text `trend_prediction` on analysis dashboards — narrative display only
- Skill-opinion outcomes — per-skill signal evaluation, separate identity
- Decision-signal outcomes — DecisionSignal action windows, separate lifecycle
- Offline agent-output eval facts — benchmark harness only
