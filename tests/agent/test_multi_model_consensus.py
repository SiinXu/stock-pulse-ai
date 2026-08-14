# -*- coding: utf-8 -*-
"""Tests for multi-model consensus comparison (#154)."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from src.config import Config
from src.agent.multi_model_consensus import (
    VERDICT_SPLIT,
    build_model_stance,
    build_multi_model_comparison,
    fingerprint_shared_snapshot,
    is_multi_model_consensus_enabled,
    public_multi_model_comparison_payload,
    resolve_consensus_models,
    resolve_consensus_models_for_run,
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


def test_budget_zero_closes_multi_model_fanout():
    config = SimpleNamespace(
        multi_model_consensus_models=["a", "b", "c"],
        multi_model_consensus_max_models=3,
        multi_model_consensus_preset="",
        multi_model_consensus_max_cost_usd=0.0,
        litellm_model="a",
        litellm_fallback_models=["b"],
    )
    models, meta = resolve_consensus_models_for_run(config)
    assert models == []
    assert meta["budget_enforced"] is True
    assert meta["budget_reason"] == "budget_closed"
    assert meta["skipped_for_budget"] == ["a", "b", "c"]


def test_positive_budget_hard_caps_to_two_models():
    config = SimpleNamespace(
        multi_model_consensus_models=["a", "b", "c"],
        multi_model_consensus_max_models=3,
        multi_model_consensus_preset="",
        multi_model_consensus_max_cost_usd=0.05,
        litellm_model="a",
        litellm_fallback_models=["b", "c"],
    )
    models, meta = resolve_consensus_models_for_run(config)
    assert models == ["a", "b"]
    assert meta["budget_enforced"] is True
    assert meta["budget_reason"] == "max_cost_usd_budget_mode_cap"
    assert meta["skipped_for_budget"] == ["c"]


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_runtime_budget_is_rejected(non_finite):
    config = SimpleNamespace(
        multi_model_consensus_models=["a", "b"],
        multi_model_consensus_max_models=2,
        multi_model_consensus_preset="",
        multi_model_consensus_max_cost_usd=non_finite,
    )
    with pytest.raises(ValueError, match="must be finite"):
        resolve_consensus_models_for_run(config)


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
def test_non_finite_budget_stops_config_loading(raw):
    with patch("src.config.setup_env"), patch.object(
        Config, "_parse_litellm_yaml", return_value=[]
    ), patch.object(
        Config, "_parse_stock_email_groups", return_value=[]
    ), patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "MULTI_MODEL_CONSENSUS_MAX_COST_USD": raw,
        },
        clear=True,
    ):
        with pytest.raises(
            ValueError,
            match="MULTI_MODEL_CONSENSUS_MAX_COST_USD must be a finite number",
        ):
            Config._load_from_env()


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


@pytest.mark.parametrize(
    "label, expected",
    [
        ("高", 0.85),
        ("中", 0.55),
        ("低", 0.3),
        ("high", 0.85),
        ("medium", 0.55),
        ("low", 0.3),
        ("높음", 0.85),
        ("보통", 0.55),
        ("낮음", 0.3),
    ],
)
def test_localized_confidence_labels_map_to_unit(label, expected):
    stance = build_model_stance(
        _result(confidence=label, model="m1"),
        requested_model="m1",
    )
    assert stance["confidence"] == expected
    assert stance["confidence_level"] == label


def test_korean_confidence_labels_feed_agreement_and_dispersion():
    comparison = build_multi_model_comparison(
        [
            build_model_stance(
                _result(signal="buy", score=70, confidence="높음", model="m1"),
                requested_model="m1",
            ),
            build_model_stance(
                _result(signal="buy", score=68, confidence="낮음", model="m2"),
                requested_model="m2",
            ),
        ],
        requested_models=["m1", "m2"],
    )
    by_model = {row["model_id"]: row for row in comparison["agreement_table"]}
    assert by_model["m1"]["confidence"] == 0.85
    assert by_model["m2"]["confidence"] == 0.3
    assert any(
        point["kind"] == "confidence_dispersion"
        for point in comparison["disagreement_handling"]["points"]
    )


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


def test_missing_model_conclusions_are_not_evaluated_without_numeric_score():
    missing = build_model_stance(
        _result(signal="", score=50, model="m1"),
        requested_model="m1",
    )
    comparison = build_multi_model_comparison(
        [missing],
        requested_models=["m1", "m2"],
    )

    assert missing["signal"] is None
    assert missing["status"] == "unassessed"
    assert missing["error_type"] == "missing_decision_signal"
    assert comparison["status"] == "insufficient"
    assert comparison["degradation"]["failed_models"] == ["m1"]
    assert comparison["consensus_score"] is None
    assert comparison["disagreement_handling"]["policy"]["applied_final_signal"] is None


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_model_metrics_and_snapshot_are_rejected(non_finite):
    with pytest.raises(ValueError, match="confidence must be finite"):
        build_model_stance(
            _result(confidence=non_finite, model="m1"),
            requested_model="m1",
        )
    with pytest.raises(ValueError, match="integer metric must be finite"):
        build_model_stance(
            _result(score=non_finite, model="m1"),
            requested_model="m1",
        )
    stance = build_model_stance(
        _result(confidence="high", model="m1"),
        requested_model="m1",
    )
    stance["confidence"] = non_finite
    with pytest.raises(ValueError, match="must not contain NaN or infinity"):
        build_multi_model_comparison([stance], requested_models=["m1"])
    with pytest.raises(ValueError, match="must not contain NaN or infinity"):
        fingerprint_shared_snapshot({"code": "AAPL", "realtime": {"price": non_finite}})


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
    )
    assert result is None
    assert comparison is not None
    assert comparison["status"] == "insufficient"
    assert comparison["consensus_score"] is None
    assert comparison["disagreement_handling"]["policy"]["applied_final_signal"] is None
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


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_public_payload_rejects_non_finite_persisted_metrics(invalid):
    comparison = build_multi_model_comparison(
        [
            build_model_stance(_result(signal="buy", model="m1"), requested_model="m1"),
            build_model_stance(_result(signal="buy", model="m2"), requested_model="m2"),
        ],
        requested_models=["m1", "m2"],
    )
    comparison["agreement_table"][0]["confidence"] = invalid

    with pytest.raises(ValueError, match="must not contain NaN or infinity"):
        public_multi_model_comparison_payload(comparison)


def test_append_multi_model_comparison_lines_renders_enabled_payload():
    from src.report_language import append_multi_model_comparison_lines

    lines: list[str] = []
    append_multi_model_comparison_lines(
        lines,
        {
            "multi_model_comparison": {
                "enabled": True,
                "status": "completed",
                "consensus_level": "high",
                "consensus_score": 0.9,
                "disagreement_handling": {
                    "high_disagreement": True,
                    "points": [
                        {
                            "severity": "high",
                            "kind": "direction",
                            "participants": ["m1", "m2"],
                        }
                    ],
                },
                "agreement_table": [
                    {"model_id": "m1", "status": "ok", "signal": "buy", "score_band": "A"},
                ],
                "degradation": {"annotation": "single_model_fallback"},
            }
        },
        {},
        "en",
    )
    joined = "\n".join(lines)
    assert "Multi-Model Consensus" in joined
    assert "single_model_fallback" in joined
    assert "`m1`" in joined
    assert "direction" in joined

    skipped: list[str] = []
    append_multi_model_comparison_lines(
        skipped, {"multi_model_comparison": {"enabled": False}}, {}, "en"
    )
    assert skipped == []
