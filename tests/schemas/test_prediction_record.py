# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for PredictionRecord contract (Issue #1101 / A1)."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from src.schemas.prediction_record import (
    PREDICTION_HORIZON_TOKENS,
    PREDICTION_RECORD_SCHEMA_VERSION,
    CustomClaimPayload,
    DirectionPayload,
    LevelBreakPayload,
    PredictionClaim,
    PredictionModelMeta,
    PredictionRecord,
    ReturnBucketPayload,
    VolRegimePayload,
    build_no_verifiable_claim_record,
    try_validate_prediction_record,
    validate_prediction_record,
)

UTC = timezone.utc
AS_OF = date(2026, 3, 15)
CREATED = datetime(2026, 3, 15, 8, 0, 0, tzinfo=UTC)
RESOLVE = datetime(2026, 3, 16, 8, 0, 0, tzinfo=UTC)


def _direction_claim(
    claim_id: str = "c1",
    *,
    direction: str = "up",
    confidence: float = 0.7,
) -> dict:
    return {
        "claim_id": claim_id,
        "type": "direction",
        "confidence": confidence,
        "payload": {"direction": direction},
    }


def _pending_record(**overrides):
    base = {
        "prediction_id": "pred-1",
        "run_id": "run-1",
        "symbol": "600519",
        "market": "CN",
        "created_at": CREATED,
        "as_of": AS_OF,
        "horizon": "5d",
        "resolve_after": RESOLVE,
        "claims": [_direction_claim()],
        "status": "pending",
        "source_decision_id": "dec-1",
        "model_meta": {
            "mode": "agent",
            "model_version": "m-1",
            "config_version": "cfg-1",
            "soul_version": "soul-1",
            "skill_ids": ["trend_follow"],
        },
    }
    base.update(overrides)
    return base


class TestValidRecords:
    def test_schema_version_constant(self) -> None:
        assert PREDICTION_RECORD_SCHEMA_VERSION == "prediction-record-v1"
        rec = validate_prediction_record(_pending_record())
        assert rec.schema_version == PREDICTION_RECORD_SCHEMA_VERSION

    def test_pending_direction_roundtrip(self) -> None:
        rec = validate_prediction_record(_pending_record())
        assert rec.is_verifiable() is True
        assert rec.claims[0].type == "direction"
        assert isinstance(rec.claims[0].payload, DirectionPayload)
        assert rec.claims[0].payload.direction == "up"
        assert rec.source_decision_id == "dec-1"
        assert rec.model_meta.model_version == "m-1"
        assert rec.model_meta.config_version == "cfg-1"
        dumped = rec.to_persistence_dict()
        again = validate_prediction_record(dumped)
        assert again.prediction_id == rec.prediction_id
        assert again.claims[0].payload.direction == "up"

    def test_all_claim_types_accepted(self) -> None:
        claims = [
            _direction_claim("d1", direction="down"),
            {
                "claim_id": "r1",
                "type": "return_bucket",
                "confidence": 0.5,
                "payload": {
                    "low_pct": 0.0,
                    "high_pct": 5.0,
                    "bucket_id": "0_to_5",
                },
            },
            {
                "claim_id": "l1",
                "type": "level_break",
                "confidence": 0.4,
                "payload": {"side": "above", "level": 1800.0},
            },
            {
                "claim_id": "v1",
                "type": "vol_regime",
                "confidence": 0.3,
                "payload": {"regime": "high"},
            },
            {
                "claim_id": "x1",
                "type": "custom",
                "confidence": 0.2,
                "payload": {
                    "metric": "rsi_14",
                    "operator": "lt",
                    "expected": 30.0,
                    "unit": "index",
                },
            },
        ]
        rec = validate_prediction_record(_pending_record(claims=claims))
        assert len(rec.claims) == 5
        assert isinstance(rec.claims[1].payload, ReturnBucketPayload)
        assert isinstance(rec.claims[2].payload, LevelBreakPayload)
        assert isinstance(rec.claims[3].payload, VolRegimePayload)
        assert isinstance(rec.claims[4].payload, CustomClaimPayload)

    def test_horizon_token_set(self) -> None:
        assert PREDICTION_HORIZON_TOKENS == frozenset({"1d", "3d", "5d", "10d", "20d"})
        for token in sorted(PREDICTION_HORIZON_TOKENS):
            rec = validate_prediction_record(_pending_record(horizon=token))
            assert rec.horizon == token

    def test_timezone_normalized_to_utc(self) -> None:
        eastern = timezone(timedelta(hours=-4))
        created = datetime(2026, 3, 15, 4, 0, 0, tzinfo=eastern)
        resolve = datetime(2026, 3, 16, 4, 0, 0, tzinfo=eastern)
        rec = validate_prediction_record(
            _pending_record(created_at=created, resolve_after=resolve)
        )
        assert rec.created_at.tzinfo == UTC
        assert rec.created_at.hour == 8


class TestNoVerifiableClaim:
    def test_builder_marks_unverifiable_without_claims(self) -> None:
        rec = build_no_verifiable_claim_record(
            prediction_id="pred-u1",
            run_id="run-u1",
            symbol="AAPL",
            created_at=CREATED,
            as_of=AS_OF,
            reason="prose_only",
            notes="Model wrote only narrative; no structured forecast fields.",
        )
        assert rec.status == "no_verifiable_claim"
        assert rec.claims == []
        assert rec.no_verifiable_reason == "prose_only"
        assert rec.is_verifiable() is False

    def test_prose_notes_are_not_claims(self) -> None:
        rec = build_no_verifiable_claim_record(
            prediction_id="pred-u2",
            run_id="run-u2",
            symbol="hk00700",
            created_at=CREATED,
            as_of=AS_OF,
            reason="prose_only",
            notes="强烈看多，预计大幅上涨，建议买入。",
        )
        assert rec.is_verifiable() is False
        assert rec.claims == []
        # notes remain research-only metadata
        assert "看多" in (rec.notes or "")

    def test_no_verifiable_with_claims_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_prediction_record(
                _pending_record(
                    status="no_verifiable_claim",
                    no_verifiable_reason="unparseable_output",
                    claims=[_direction_claim()],
                )
            )
        assert "must not carry claims" in str(exc.value)

    def test_no_verifiable_requires_reason(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_prediction_record(
                _pending_record(
                    status="no_verifiable_claim",
                    claims=[],
                    no_verifiable_reason=None,
                )
            )
        assert "no_verifiable_reason" in str(exc.value)

    def test_pending_empty_claims_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_prediction_record(_pending_record(claims=[]))
        assert "at least one typed claim" in str(exc.value)

    def test_reason_forbidden_on_pending(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_prediction_record(
                _pending_record(no_verifiable_reason="prose_only")
            )
        assert "no_verifiable_reason" in str(exc.value)


class TestNumericBoundaries:
    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_confidence_rejects_non_finite(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            PredictionClaim.model_validate(
                {
                    "claim_id": "c1",
                    "type": "direction",
                    "confidence": bad,
                    "payload": {"direction": "up"},
                }
            )

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_return_bucket_rejects_non_finite(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            ReturnBucketPayload.model_validate(
                {"low_pct": bad, "high_pct": 5.0}
            )
        with pytest.raises(ValidationError):
            ReturnBucketPayload.model_validate(
                {"low_pct": 0.0, "high_pct": bad}
            )

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_level_break_rejects_non_finite(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            LevelBreakPayload.model_validate(
                {"side": "above", "level": bad}
            )

    def test_confidence_out_of_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            PredictionClaim.model_validate(_direction_claim(confidence=1.01))
        with pytest.raises(ValidationError):
            PredictionClaim.model_validate(_direction_claim(confidence=-0.01))

    def test_return_bucket_requires_ordered_bounds(self) -> None:
        with pytest.raises(ValidationError) as exc:
            ReturnBucketPayload.model_validate(
                {"low_pct": 5.0, "high_pct": 5.0}
            )
        assert "strictly less" in str(exc.value)


class TestCustomClaimNotProse:
    def test_custom_prose_expected_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            CustomClaimPayload.model_validate(
                {
                    "metric": "narrative",
                    "operator": "eq",
                    "expected": "stock will probably go up a lot tomorrow",
                }
            )
        assert "machine token" in str(exc.value)

    def test_custom_token_and_range_ok(self) -> None:
        token = CustomClaimPayload.model_validate(
            {
                "metric": "label",
                "operator": "eq",
                "expected": "breakout_ok",
            }
        )
        assert token.expected == "breakout_ok"
        ranged = CustomClaimPayload.model_validate(
            {
                "metric": "return_pct",
                "operator": "in_range",
                "expected": -2.0,
                "expected_high": 2.0,
            }
        )
        assert ranged.expected_high == 2.0

    def test_in_range_requires_high(self) -> None:
        with pytest.raises(ValidationError):
            CustomClaimPayload.model_validate(
                {
                    "metric": "return_pct",
                    "operator": "in_range",
                    "expected": 0.0,
                }
            )


class TestStructuralGuards:
    def test_extra_field_forbidden(self) -> None:
        payload = _pending_record()
        payload["invented_hit"] = True
        with pytest.raises(ValidationError):
            validate_prediction_record(payload)

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_prediction_record(
                _pending_record(
                    created_at=datetime(2026, 3, 15, 8, 0, 0),
                )
            )
        assert "timezone-aware" in str(exc.value)

    def test_duplicate_claim_ids_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            validate_prediction_record(
                _pending_record(
                    claims=[
                        _direction_claim("same"),
                        _direction_claim("same", direction="down"),
                    ]
                )
            )
        assert "unique" in str(exc.value)

    def test_payload_type_mismatch_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PredictionClaim.model_validate(
                {
                    "claim_id": "c1",
                    "type": "direction",
                    "confidence": 0.5,
                    "payload": {"low_pct": 0.0, "high_pct": 1.0},
                }
            )

    def test_invalid_horizon_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_prediction_record(_pending_record(horizon="1w"))

    def test_symbol_whitespace_rejected(self) -> None:
        with pytest.raises(ValidationError):
            validate_prediction_record(_pending_record(symbol="600 519"))

    def test_try_validate_surfaces_error(self) -> None:
        ok, err = try_validate_prediction_record(_pending_record())
        assert ok is not None and err is None
        bad, err2 = try_validate_prediction_record(_pending_record(claims=[]))
        assert bad is None and err2 is not None

    def test_model_meta_dedupes_skill_ids(self) -> None:
        meta = PredictionModelMeta.model_validate(
            {"skill_ids": ["a", "a", "b"]}
        )
        assert meta.skill_ids == ["a", "b"]

    def test_error_status_allows_empty_claims(self) -> None:
        # error/expired may be intermediate; empty claims allowed only for error/expired
        rec = validate_prediction_record(
            _pending_record(status="error", claims=[])
        )
        assert rec.status == "error"
        assert rec.is_verifiable() is False
