# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for PredictionExtractor (Issue #1108 / A2)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.services.prediction_extractor import (
    PREDICTION_EXTRACTOR_VERSION,
    extract_prediction_record,
    is_prediction_extract_enabled,
    maybe_extract_prediction_on_finalize,
)


UTC = timezone.utc
CREATED = datetime(2024, 3, 15, 8, 0, 0, tzinfo=UTC)
AS_OF = date(2024, 3, 15)
RESOLVE = datetime(2024, 3, 22, 7, 0, 0, tzinfo=UTC)


class _FakeResolve:
    def __init__(self) -> None:
        self.resolve_after = RESOLVE
        self.calendar_approx = False

    def to_dict(self) -> dict:
        return {
            "resolve_after": self.resolve_after.isoformat(),
            "calendar_approx": False,
            "market": "cn",
            "horizon": "5d",
        }


@pytest.fixture()
def mock_resolve_after():
    with patch(
        "src.services.prediction_extractor._compute_resolve_after",
        return_value=(RESOLVE, _FakeResolve().to_dict(), None),
    ) as mocked:
        yield mocked


class TestStructuredExtraction:
    def test_valid_decision_type_buy_yields_pending_direction(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {
                "code": "600519",
                "decision_type": "buy",
                "confidence_level": "高",
                "analysis_summary": "散文不应单独成为声明",
            },
            run_id="run-structured-1",
            created_at=CREATED,
            as_of=AS_OF,
            mode="analysis",
            soul_version="soul-v1",
            skill_ids=["trend_follow"],
        )
        assert result.verifiable is True
        assert result.record is not None
        assert result.record.status == "pending"
        assert result.record.run_id == "run-structured-1"
        assert result.record.symbol
        assert result.record.horizon == "5d"
        assert result.record.resolve_after == RESOLVE
        assert len(result.record.claims) == 1
        claim = result.record.claims[0]
        assert claim.type == "direction"
        assert claim.payload.direction == "up"
        assert claim.confidence == 0.8
        assert result.record.model_meta.mode == "analysis"
        assert result.record.model_meta.soul_version == "soul-v1"
        assert "trend_follow" in result.record.model_meta.skill_ids
        assert result.record.model_meta.config_version == PREDICTION_EXTRACTOR_VERSION

    def test_action_enum_preferred_over_decision_type(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {
                "stock_code": "AAPL",
                "market": "us",
                "decision_type": "buy",
                "action": "sell",
                "confidence": 0.55,
            },
            run_id="run-action",
            created_at=CREATED,
            as_of=AS_OF,
        )
        assert result.verifiable is True
        assert result.record is not None
        assert result.record.claims[0].payload.direction == "down"
        assert result.record.claims[0].confidence == 0.55

    def test_explicit_prediction_claims_accepted(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {
                "code": "00700",
                "market": "hk",
                "prediction_claims": [
                    {
                        "claim_id": "rb-1",
                        "type": "return_bucket",
                        "confidence": 0.6,
                        "payload": {"low_pct": -2.0, "high_pct": 5.0},
                    },
                    {
                        "claim_id": "lb-1",
                        "type": "level_break",
                        "confidence": 0.5,
                        "payload": {
                            "side": "above",
                            "level": 400.0,
                            "reference": "absolute_price",
                        },
                    },
                ],
            },
            run_id="run-explicit",
            created_at=CREATED,
            as_of=AS_OF,
            default_horizon="1d",
        )
        assert result.verifiable is True
        assert result.record is not None
        types = {c.type for c in result.record.claims}
        assert types == {"return_bucket", "level_break"}
        assert result.record.horizon == "1d"


class TestProseAntiExamples:
    def test_narrative_only_payload_creates_no_fake_claims(
        self, mock_resolve_after
    ) -> None:
        """Hard acceptance: prose must not become a fake verifiable claim."""
        result = extract_prediction_record(
            {
                "code": "600519",
                "analysis_summary": (
                    "我们认为股价将上涨突破阻力位，短期看多，建议买入布局。"
                    "We expect the stock to rally and break resistance."
                ),
                "short_term_outlook": "1-3日偏强，上攻可期",
                "medium_term_outlook": "中期趋势向好",
                "trend_prediction": "强烈看多",
                "operation_advice": "买入",
                "buy_reason": "技术面多头排列，资金回流",
                "key_points": "突破,放量,利好催化",
            },
            run_id="run-prose-only",
            created_at=CREATED,
            as_of=AS_OF,
        )
        assert result.verifiable is False
        assert result.record is not None
        assert result.record.status == "no_verifiable_claim"
        assert result.record.claims == []
        assert result.record.no_verifiable_reason == "prose_only"
        assert result.reason == "prose_only"

    def test_chinese_operation_advice_alone_is_not_a_direction_claim(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {
                "code": "600519",
                "operation_advice": "强烈买入，建议建仓",
                "trend_prediction": "看多",
            },
            run_id="run-advice-prose",
            created_at=CREATED,
            as_of=AS_OF,
        )
        assert result.verifiable is False
        assert result.record is not None
        assert result.record.claims == []
        assert result.record.status == "no_verifiable_claim"

    def test_missing_structured_fields_not_defaulted_to_hold(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {"code": "600519", "sentiment_score": 82},
            run_id="run-score-only",
            created_at=CREATED,
            as_of=AS_OF,
        )
        assert result.verifiable is False
        assert result.record is not None
        assert result.record.claims == []
        assert result.record.status == "no_verifiable_claim"
        # Score alone must not invent a directional claim.
        assert result.record.no_verifiable_reason in {
            "missing_structured_fields",
            "prose_only",
            "empty_decision",
            "unsupported_shape",
            "unparseable_output",
        }


class TestFailureAndFlag:
    def test_extraction_records_explicit_claim_validation_errors(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {
                "code": "600519",
                "prediction_claims": [
                    {
                        "claim_id": "bad-1",
                        "type": "direction",
                        "confidence": 0.5,
                        "payload": {"direction": "to the moon"},
                    }
                ],
            },
            run_id="run-bad-claim",
            created_at=CREATED,
            as_of=AS_OF,
        )
        assert result.verifiable is False
        assert result.record is not None
        assert result.record.claims == []
        assert result.record.status == "no_verifiable_claim"
        assert result.error is not None
        assert "direction" in result.error or "payload" in result.error.lower() or "claim" in (
            result.reason or ""
        )

    def test_feature_flag_default_off_skips_hook(self) -> None:
        config = SimpleNamespace(prediction_extract_enabled=False)
        assert is_prediction_extract_enabled(config) is False
        out = maybe_extract_prediction_on_finalize(
            {"code": "600519", "decision_type": "buy"},
            config=config,
            run_id="run-flag-off",
            created_at=CREATED,
        )
        assert out is None

    def test_feature_flag_on_invokes_extract(self, mock_resolve_after) -> None:
        config = SimpleNamespace(prediction_extract_enabled=True)
        out = maybe_extract_prediction_on_finalize(
            {"code": "600519", "decision_type": "sell", "confidence_level": "low"},
            config=config,
            run_id="run-flag-on",
            created_at=CREATED,
            as_of=AS_OF,
            mode="agent",
        )
        assert out is not None
        assert out.verifiable is True
        assert out.record is not None
        assert out.record.claims[0].payload.direction == "down"
        assert out.to_dict()["verifiable"] is True

    def test_duck_typed_analysis_result_object(
        self, mock_resolve_after
    ) -> None:
        result_obj = SimpleNamespace(
            code="600519",
            name="贵州茅台",
            decision_type="hold",
            action="watch",
            confidence_level="中",
            analysis_summary="中性观察",
            dashboard={},
            model_used="test-model",
            query_id="q-1",
            success=True,
        )
        out = extract_prediction_record(
            result_obj,
            run_id="run-obj",
            created_at=CREATED,
            as_of=AS_OF,
        )
        assert out.verifiable is True
        assert out.record is not None
        assert out.record.claims[0].payload.direction == "sideways"
