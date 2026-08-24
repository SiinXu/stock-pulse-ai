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
            {
                "code": "600519",
                "action": "sell",
                "confidence_level": "low",
            },
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


class TestReviewConvergence:
    """Regressions for PR review: no invented confidence; agent path discipline."""

    def test_missing_confidence_does_not_invent_default(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {"code": "600519", "decision_type": "buy"},
            run_id="run-no-conf",
            created_at=CREATED,
            as_of=AS_OF,
            mode="analysis",
        )
        assert result.verifiable is False
        assert result.record is not None
        assert result.record.claims == []
        assert result.record.status == "no_verifiable_claim"
        assert result.error is None or "confidence" in (result.error or "")
        # Reason may be missing_structured_fields after direction skip.
        assert result.record.no_verifiable_reason in {
            "missing_structured_fields",
            "unparseable_output",
            "prose_only",
            "empty_decision",
            "unsupported_shape",
        }

    def test_agent_mode_ignores_decision_type_without_action(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {
                "code": "600519",
                "decision_type": "buy",
                "confidence_level": "高",
            },
            run_id="run-agent-synth",
            created_at=CREATED,
            as_of=AS_OF,
            mode="agent",
        )
        assert result.verifiable is False
        assert result.record is not None
        assert result.record.claims == []
        assert result.record.status == "no_verifiable_claim"

    def test_agent_mode_accepts_explicit_action(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {
                "code": "600519",
                "action": "buy",
                "decision_type": "hold",
                "confidence": 0.7,
            },
            run_id="run-agent-action",
            created_at=CREATED,
            as_of=AS_OF,
            mode="agent",
        )
        assert result.verifiable is True
        assert result.record is not None
        assert result.record.claims[0].payload.direction == "up"
        assert result.record.claims[0].confidence == 0.7
        assert "horizon_source=" in (result.record.notes or "")

    def test_policy_default_horizon_recorded_in_notes(
        self, mock_resolve_after
    ) -> None:
        result = extract_prediction_record(
            {
                "code": "600519",
                "decision_type": "sell",
                "confidence_level": "中",
            },
            run_id="run-horizon-policy",
            created_at=CREATED,
            as_of=AS_OF,
            mode="analysis",
        )
        assert result.verifiable is True
        assert result.record is not None
        assert result.record.horizon == "5d"
        assert "horizon_source=policy_default:5d" in (result.record.notes or "")

    def test_real_analysis_parser_defaults_do_not_become_claims(self) -> None:
        """Normalized hold/medium/action defaults are presentation, not provenance."""
        import json

        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer()
        analyzer._get_runtime_config = lambda: SimpleNamespace(report_language="en")
        parsed = analyzer._parse_response(
            json.dumps({"analysis_summary": "Narrative only; no forecast fields."}),
            "AAPL",
            "Apple",
        )

        assert parsed.success is True
        assert parsed.decision_type == "hold"
        assert parsed.action == "hold"
        assert parsed.confidence_level.lower() == "medium"
        assert parsed.prediction_source == {
            "analysis_summary": "Narrative only; no forecast fields."
        }

        extraction = extract_prediction_record(
            parsed,
            run_id="run-real-parser-defaults",
            created_at=CREATED,
            as_of=AS_OF,
            mode="analysis",
        )
        assert extraction.verifiable is False
        assert extraction.record is not None
        assert extraction.record.status == "no_verifiable_claim"
        assert extraction.record.claims == []

    def test_real_analysis_parser_preserves_explicit_prediction_fields(
        self, mock_resolve_after
    ) -> None:
        import json

        from src.analyzer import GeminiAnalyzer

        analyzer = GeminiAnalyzer()
        analyzer._get_runtime_config = lambda: SimpleNamespace(report_language="en")
        parsed = analyzer._parse_response(
            json.dumps(
                {
                    "analysis_summary": "Structured forecast.",
                    "decision_type": "buy",
                    "confidence": 0.7,
                }
            ),
            "AAPL",
            "Apple",
        )

        extraction = extract_prediction_record(
            parsed,
            run_id="run-real-parser-explicit",
            created_at=CREATED,
            as_of=AS_OF,
            mode="analysis",
        )
        assert extraction.verifiable is True
        assert extraction.record is not None
        assert extraction.record.claims[0].payload.direction == "up"
        assert extraction.record.claims[0].confidence == 0.7

    def test_agent_finalize_hook_rejects_synthesized_dashboard_defaults(self) -> None:
        from src.agent.orchestrator_parts.dashboard import _DashboardMethods
        from src.agent.protocols import AgentContext

        orchestrator = _DashboardMethods()
        orchestrator.config = SimpleNamespace(prediction_extract_enabled=True)
        ctx = AgentContext(
            stock_code="600519",
            stock_name="Test",
            session_id="agent-session",
            meta={"response_mode": "dashboard"},
        )

        orchestrator._maybe_extract_prediction_on_finalize(
            {
                "decision_type": "hold",
                "confidence_level": "medium",
                "analysis_summary": "Finalizer fallback",
            },
            ctx,
        )

        extraction = ctx.meta["prediction_extraction"]
        assert extraction["verifiable"] is False
        assert extraction["record"]["status"] == "no_verifiable_claim"
        assert extraction["record"]["claims"] == []

    def test_presentation_confidence_flag_does_not_mint_agent_action_claim(
        self, mock_resolve_after
    ) -> None:
        from src.services.prediction_extractor import PRESENTATION_CONFIDENCE_FLAG

        result = extract_prediction_record(
            {
                "code": "600519",
                "action": "buy",
                "decision_type": "hold",
                "confidence_level": "中",
                PRESENTATION_CONFIDENCE_FLAG: True,
            },
            run_id="run-presentation-flag",
            created_at=CREATED,
            as_of=AS_OF,
            mode="agent",
        )
        assert result.verifiable is False
        assert result.record is not None
        assert result.record.claims == []
        assert result.record.status == "no_verifiable_claim"

    def test_history_save_hook_strips_presentation_confidence(
        self, mock_resolve_after
    ) -> None:
        from src.core.stages.persistence import _PersistenceStageMixin
        from src.services.prediction_extractor import PRESENTATION_CONFIDENCE_FLAG

        pipeline = _PersistenceStageMixin()
        pipeline.config = SimpleNamespace(prediction_extract_enabled=True)
        result = SimpleNamespace(
            code="600519",
            name="Test",
            model_used="test-model",
            prediction_source={
                "code": "600519",
                "action": "buy",
                "decision_type": "hold",
                "confidence_level": "中",
                PRESENTATION_CONFIDENCE_FLAG: True,
            },
            dashboard={"core_conclusion": {"one_sentence": "display only"}},
        )

        pipeline._extract_prediction_after_history_save(
            result=result,
            query_id="query-presentation",
            source_report_id=41,
            mode="agent",
        )

        extraction = result.prediction_extraction
        assert extraction["verifiable"] is False
        assert extraction["record"]["status"] == "no_verifiable_claim"
        assert extraction["record"]["claims"] == []

    def test_history_save_hook_keeps_real_structured_confidence(
        self, mock_resolve_after
    ) -> None:
        from src.core.stages.persistence import _PersistenceStageMixin

        pipeline = _PersistenceStageMixin()
        pipeline.config = SimpleNamespace(prediction_extract_enabled=True)
        result = SimpleNamespace(
            code="600519",
            name="Test",
            model_used="test-model",
            prediction_source={
                "code": "600519",
                "action": "buy",
                "confidence": 0.8,
            },
            dashboard={},
        )

        with patch(
            "src.services.prediction_persist.persist_verifiable_prediction_draft",
            return_value=None,
        ):
            pipeline._extract_prediction_after_history_save(
                result=result,
                query_id="query-real-confidence",
                source_report_id=41,
                mode="agent",
            )

        extraction = result.prediction_extraction
        assert extraction["verifiable"] is True
        assert extraction["record"]["claims"][0]["payload"]["direction"] == "up"
        assert extraction["record"]["claims"][0]["confidence"] == 0.8

    def test_agent_finalize_sets_presentation_flag_without_base_opinion(self) -> None:
        from unittest.mock import MagicMock

        from src.agent.orchestrator import AgentOrchestrator
        from src.agent.orchestrator_parts.dashboard import _dashboard_content_json
        from src.agent.protocols import AgentContext
        from src.services.prediction_extractor import PRESENTATION_CONFIDENCE_FLAG

        orchestrator = AgentOrchestrator(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
        )
        ctx = AgentContext(query="test", stock_code="600519", stock_name="Test")
        dashboard = orchestrator._finalize_dashboard_payload(
            {"action": "buy", "analysis_summary": "No opinions"},
            ctx,
        )

        assert dashboard is not None
        assert dashboard[PRESENTATION_CONFIDENCE_FLAG] is True
        assert dashboard["confidence_level"] == "中"
        content = _dashboard_content_json(dashboard)
        assert PRESENTATION_CONFIDENCE_FLAG not in content

    def test_agent_finalize_does_not_mark_real_opinion_confidence(self) -> None:
        from unittest.mock import MagicMock

        from src.agent.orchestrator import AgentOrchestrator
        from src.agent.protocols import AgentContext, AgentOpinion
        from src.services.prediction_extractor import PRESENTATION_CONFIDENCE_FLAG

        orchestrator = AgentOrchestrator(
            tool_registry=MagicMock(),
            llm_adapter=MagicMock(),
        )
        ctx = AgentContext(query="test", stock_code="600519", stock_name="Test")
        ctx.add_opinion(AgentOpinion(agent_name="decision", signal="buy", confidence=0.8))
        dashboard = orchestrator._finalize_dashboard_payload(
            {"action": "buy", "analysis_summary": "Has opinion"},
            ctx,
        )

        assert dashboard is not None
        assert PRESENTATION_CONFIDENCE_FLAG not in dashboard
        assert dashboard["confidence_level"] == "高"

    def test_agent_finalize_hook_rejects_action_with_presentation_confidence(
        self,
    ) -> None:
        from src.agent.orchestrator_parts.dashboard import _DashboardMethods
        from src.agent.protocols import AgentContext

        orchestrator = _DashboardMethods()
        orchestrator.config = SimpleNamespace(prediction_extract_enabled=True)
        ctx = AgentContext(
            stock_code="600519",
            stock_name="Test",
            session_id="agent-session-action",
        )

        orchestrator._maybe_extract_prediction_on_finalize(
            {
                "action": "buy",
                "confidence_level": "中",
                "analysis_summary": "Finalizer fallback",
            },
            ctx,
        )

        extraction = ctx.meta["prediction_extraction"]
        assert extraction["verifiable"] is False
        assert extraction["record"]["status"] == "no_verifiable_claim"
        assert extraction["record"]["claims"] == []

    def test_agent_finalize_hook_does_not_truncate_overlong_run_id(self) -> None:
        from src.agent.orchestrator_parts.dashboard import _DashboardMethods
        from src.agent.protocols import AgentContext

        orchestrator = _DashboardMethods()
        orchestrator.config = SimpleNamespace(prediction_extract_enabled=True)
        ctx = AgentContext(
            stock_code="600519",
            stock_name="Test",
            session_id="r" * 129,
        )

        orchestrator._maybe_extract_prediction_on_finalize(
            {"action": "buy", "confidence": 0.7},
            ctx,
        )

        extraction = ctx.meta["prediction_extraction"]
        assert extraction["verifiable"] is False
        assert "record" not in extraction
        assert extraction["reason"] == "extraction_exception"
        assert extraction["error"] == "identifier must contain at most 128 characters"

    def test_mixed_valid_and_invalid_claims_fail_closed(
        self, mock_resolve_after
    ) -> None:
        extraction = extract_prediction_record(
            {
                "code": "600519",
                "prediction_claims": [
                    {
                        "claim_id": "valid-direction",
                        "type": "direction",
                        "confidence": 0.7,
                        "payload": {"direction": "up"},
                    },
                    {
                        "claim_id": "invalid-direction",
                        "type": "direction",
                        "confidence": 0.8,
                        "payload": {"direction": "moon"},
                    },
                ],
            },
            run_id="run-partial-claims",
            created_at=CREATED,
            as_of=AS_OF,
        )

        assert extraction.verifiable is False
        assert extraction.reason == "claim_validation_failed"
        assert extraction.error is not None
        assert extraction.record is not None
        assert extraction.record.status == "error"
        assert [claim.claim_id for claim in extraction.record.claims] == [
            "valid-direction"
        ]
        assert "claim_errors=" in (extraction.record.notes or "")

    def test_overlong_run_id_is_rejected_instead_of_truncated(self) -> None:
        extraction = extract_prediction_record(
            {
                "code": "600519",
                "decision_type": "buy",
                "confidence": 0.7,
            },
            run_id="r" * 129,
            created_at=CREATED,
            as_of=AS_OF,
        )

        assert extraction.record is None
        assert extraction.verifiable is False
        assert extraction.reason == "extraction_exception"
        assert extraction.error == "identifier must contain at most 128 characters"
