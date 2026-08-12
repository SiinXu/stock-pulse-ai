# -*- coding: utf-8 -*-
"""Tests for multi-model consensus comparison (#154)."""

from __future__ import annotations

from types import SimpleNamespace

from src.agent.multi_model_consensus import (
    VERDICT_SPLIT,
    build_model_stance,
    build_multi_model_comparison,
    fingerprint_shared_snapshot,
    is_multi_model_consensus_enabled,
    public_multi_model_comparison_payload,
    resolve_consensus_models,
    run_multi_model_consensus_analysis,
)


def _result(
    *,
    signal: str = "buy",
    score: int = 70,
    confidence: str = "高",
    success: bool = True,
    model: str = "provider/model-a",
    risks: str = "risk-a",
) -> SimpleNamespace:
    return SimpleNamespace(
        success=success,
        decision_type=signal,
        action=signal,
        operation_advice=signal,
        sentiment_score=score,
        confidence_level=confidence,
        risk_warning=risks,
        key_points="catalyst-a; catalyst-b",
        buy_reason="reason",
        model_used=model,
        error_message=None,
        error_code=None,
        dashboard={
            "intelligence": {
                "risk_alerts": [risks],
            }
        },
    )


def test_default_off():
    assert is_multi_model_consensus_enabled(None) is False
    assert is_multi_model_consensus_enabled(SimpleNamespace()) is False
    assert is_multi_model_consensus_enabled(
        SimpleNamespace(multi_model_consensus_enabled=False)
    ) is False
    assert is_multi_model_consensus_enabled(
        SimpleNamespace(multi_model_consensus_enabled=True)
    ) is True


def test_resolve_models_explicit_and_preset():
    config = SimpleNamespace(
        multi_model_consensus_models=["a", "b", "c", "d"],
        multi_model_consensus_max_models=3,
        multi_model_consensus_preset="fast",
        litellm_model="primary",
        litellm_fallback_models=["fb1", "fb2"],
    )
    assert resolve_consensus_models(config) == ["a", "b", "c"]

    config.multi_model_consensus_models = []
    config.multi_model_consensus_preset = "fast"
    assert resolve_consensus_models(config) == ["primary", "fb1"]

    config.multi_model_consensus_preset = "quality"
    assert resolve_consensus_models(config) == ["primary", "fb1", "fb2"]


def test_directional_opposition_not_averaged():
    stances = [
        build_model_stance(_result(signal="buy", score=80, model="m1"), requested_model="m1"),
        build_model_stance(_result(signal="sell", score=25, model="m2"), requested_model="m2"),
    ]
    comparison = build_multi_model_comparison(
        stances,
        requested_models=["m1", "m2"],
        shared_snapshot_fingerprint="abc",
    )
    handling = comparison["disagreement_handling"]
    assert handling["high_disagreement"] is True
    assert handling["verdict_mode"] == VERDICT_SPLIT
    assert handling["policy"]["majority_vote_used"] is False
    assert handling["policy"]["averaging_used"] is False
    assert handling["policy"]["applied_final_signal"] == "hold"
    assert handling["policy"]["pre_escalation_final_signal"] == "buy"
    assert comparison["consensus_level"] == "low"
    assert any(p["kind"] == "directional_opposition" for p in handling["points"])
    assert all(p.get("source") == "model" for p in handling["points"])


def test_aligned_models_high_consensus():
    stances = [
        build_model_stance(_result(signal="buy", score=72, model="m1"), requested_model="m1"),
        build_model_stance(_result(signal="buy", score=68, model="m2"), requested_model="m2"),
    ]
    comparison = build_multi_model_comparison(
        stances,
        requested_models=["m1", "m2"],
    )
    handling = comparison["disagreement_handling"]
    assert handling["high_disagreement"] is False
    assert comparison["consensus_level"] in {"high", "medium"}
    assert handling["policy"]["applied_final_signal"] == "buy"
    assert handling["policy"]["majority_vote_used"] is False


def test_single_model_failure_degrades_with_annotation():
    stances = [
        build_model_stance(_result(signal="hold", score=50, model="m1"), requested_model="m1"),
        {
            "model_id": "m2",
            "model_version": "m2",
            "provider": "x",
            "status": "failed",
            "signal": None,
            "decision_type": None,
            "action": None,
            "operation_advice": None,
            "sentiment_score": None,
            "score_band": None,
            "confidence_level": None,
            "confidence": None,
            "key_risks": [],
            "key_catalysts": [],
            "error_type": "TimeoutError",
        },
    ]
    comparison = build_multi_model_comparison(
        stances,
        requested_models=["m1", "m2"],
    )
    assert comparison["status"] == "degraded_single"
    assert comparison["degradation"]["annotation"] == "single_model_fallback"
    assert comparison["primary_result_model"] == "m1"
    assert comparison["consensus_level"] == "insufficient"
    public = public_multi_model_comparison_payload(comparison)
    assert public is not None
    assert public["status"] == "degraded_single"
    assert public["disagreement_handling"]["policy"]["majority_vote_used"] is False


def test_shared_snapshot_fingerprint_stable():
    context = {
        "code": "600519",
        "stock_name": "Moutai",
        "realtime": {"price": 1700.0, "change_pct": 1.2, "volume": 1, "time": "t"},
        "trend": {"signal": "buy", "score": 1, "summary": "up"},
    }
    a = fingerprint_shared_snapshot(context, news_context="news")
    b = fingerprint_shared_snapshot(context, news_context="news")
    c = fingerprint_shared_snapshot(context, news_context="other")
    assert a == b
    assert a != c


def test_run_multi_model_attaches_dashboard_and_trace_identities():
    class FakeAnalyzer:
        def __init__(self):
            self.calls = []

        def analyze(self, context, **kwargs):
            model = kwargs.get("model_override") or "default"
            self.calls.append((model, kwargs.get("disable_model_fallback"), context.get("code")))
            if model == "fail-model":
                return _result(success=False, model=model)
            signal = "buy" if model == "model-a" else "sell"
            score = 80 if signal == "buy" else 20
            return _result(signal=signal, score=score, model=model, confidence="高")

    analyzer = FakeAnalyzer()
    config = SimpleNamespace(
        multi_model_consensus_enabled=True,
        multi_model_consensus_models=["model-a", "model-b"],
        multi_model_consensus_max_models=3,
        multi_model_consensus_preset="",
        multi_model_consensus_max_cost_usd=None,
        litellm_model="model-a",
        litellm_fallback_models=["model-b"],
    )
    result, comparison = run_multi_model_consensus_analysis(
        analyzer=analyzer,
        config=config,
        context={"code": "600519", "realtime": {"price": 1}},
        news_context="shared-news",
        parallel=False,
    )
    assert result is not None
    assert comparison is not None
    assert result.dashboard["multi_model_comparison"]["enabled"] is True
    assert result.dashboard["multi_model_comparison"]["disagreement_handling"]["high_disagreement"] is True
    assert result.dashboard.get("multi_model_high_disagreement") is True
    # Product honesty: confidence is capped; direction is not averaged.
    assert result.confidence_level == "低"
    assert result.decision_type == "buy"
    assert "多模型高分歧" in (result.risk_warning or "")
    identities = comparison["trace"]["model_identities"]
    assert len(identities) == 2
    assert {item["model_id"] for item in identities} == {"model-a", "model-b"}
    # Shared snapshot: both calls saw the same code.
    assert all(code == "600519" for _, _, code in analyzer.calls)
    assert all(disable is True for _, disable, _ in analyzer.calls)


def test_partial_failure_attaches_degradation_dashboard_flag():
    class FakeAnalyzer:
        def analyze(self, context, **kwargs):
            model = kwargs.get("model_override")
            if model == "model-b":
                raise RuntimeError("down")
            return _result(signal="buy", score=70, model=model)

    result, comparison = run_multi_model_consensus_analysis(
        analyzer=FakeAnalyzer(),
        config=SimpleNamespace(
            multi_model_consensus_enabled=True,
            multi_model_consensus_models=["model-a", "model-b"],
            multi_model_consensus_max_models=3,
            multi_model_consensus_preset="",
            multi_model_consensus_max_cost_usd=None,
            litellm_model="model-a",
            litellm_fallback_models=[],
        ),
        context={"code": "600519"},
        parallel=False,
    )
    assert result is not None
    assert comparison["status"] == "degraded_single"
    assert result.dashboard["multi_model_degradation"]["annotation"] == "single_model_fallback"


def test_run_multi_model_partial_failure_keeps_single_success():
    class FakeAnalyzer:
        def analyze(self, context, **kwargs):
            model = kwargs.get("model_override")
            if model == "model-b":
                raise RuntimeError("provider down")
            return _result(signal="hold", score=50, model=model)

    result, comparison = run_multi_model_consensus_analysis(
        analyzer=FakeAnalyzer(),
        config=SimpleNamespace(
            multi_model_consensus_enabled=True,
            multi_model_consensus_models=["model-a", "model-b"],
            multi_model_consensus_max_models=3,
            multi_model_consensus_preset="",
            multi_model_consensus_max_cost_usd=None,
            litellm_model="model-a",
            litellm_fallback_models=[],
        ),
        context={"code": "AAPL"},
        parallel=False,
    )
    assert result is not None
    assert comparison["status"] == "degraded_single"
    assert comparison["degradation"]["annotation"] == "single_model_fallback"
    assert comparison["primary_result_model"] == "model-a"
    public = result.dashboard["multi_model_comparison"]
    assert public["degradation"]["annotation"] == "single_model_fallback"


def test_all_models_failed_returns_no_primary_result():
    class FakeAnalyzer:
        def analyze(self, context, **kwargs):
            raise RuntimeError("all down")

    result, comparison = run_multi_model_consensus_analysis(
        analyzer=FakeAnalyzer(),
        config=SimpleNamespace(
            multi_model_consensus_enabled=True,
            multi_model_consensus_models=["model-a", "model-b"],
            multi_model_consensus_max_models=3,
            multi_model_consensus_preset="",
            multi_model_consensus_max_cost_usd=None,
            litellm_model="model-a",
            litellm_fallback_models=[],
        ),
        context={"code": "600519"},
        parallel=False,
    )
    assert result is None
    assert comparison is not None
    assert comparison["status"] == "insufficient"
    assert comparison["degradation"]["annotation"] == "no_usable_model_result"


def test_public_payload_keeps_disagreement_points_for_products():
    comparison = build_multi_model_comparison(
        [
            build_model_stance(_result(signal="buy", model="m1"), requested_model="m1"),
            build_model_stance(_result(signal="sell", model="m2"), requested_model="m2"),
        ],
        requested_models=["m1", "m2"],
    )
    public = public_multi_model_comparison_payload(comparison)
    assert public is not None
    assert public["disagreement_handling"]["high_disagreement"] is True
    assert public["disagreement_handling"]["points"]
    assert public["disagreement_handling"]["policy"]["majority_vote_used"] is False
    assert public["disagreement_handling"]["policy"]["averaging_used"] is False
    assert public["agreement_table"]
    assert public["trace"]["model_identities"]
