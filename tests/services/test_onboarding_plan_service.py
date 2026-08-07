# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic unit tests for agent-guided onboarding plan generation and apply."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from src.services.onboarding_plan_service import (
    OnboardingPlanService,
    OnboardingProfileValidationError,
    OnboardingSecretRejectedError,
    is_secret_config_key,
    normalize_profile,
    resolve_feature_stage,
    resolve_preset_id,
)


def _profile(**overrides: Any) -> Dict[str, Any]:
    base = {
        "schema_version": 1,
        "experience_stage": "beginner",
        "markets": ["cn"],
        "goals": ["pre_post_market"],
        "holdings": "none",
        "interaction": "web",
        "risk_tone": "balanced",
        "infrastructure": "cloud_key",
        "report_language": "zh",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("OPENAI_API_KEY", True),
        ("TELEGRAM_BOT_TOKEN", True),
        ("LITELLM_CONFIG", True),
        ("STOCK_LIST", False),
        ("REPORT_LANGUAGE", False),
        ("LLM_OLLAMA_ENABLED", False),
    ],
)
def test_is_secret_config_key(key: str, expected: bool) -> None:
    assert is_secret_config_key(key) is expected


def test_normalize_profile_defaults_and_rejects_bad_market() -> None:
    profile = normalize_profile({"markets": ["cn", "us"], "experience_stage": "beginner"})
    assert profile["schema_version"] == 1
    assert profile["markets"] == ["cn", "us"]
    assert profile["infrastructure"] == "cloud_key"
    with pytest.raises(OnboardingProfileValidationError):
        normalize_profile({"markets": ["mars"]})


@pytest.mark.parametrize(
    ("profile", "stage"),
    [
        (_profile(experience_stage="beginner"), "L0"),
        (_profile(experience_stage="report_reader", holdings="watchlist"), "L1"),
        (_profile(experience_stage="report_reader", holdings="bookkeeping"), "L2"),
        (
            _profile(
                experience_stage="has_system",
                interaction="chat",
                goals=["strategy_validation"],
            ),
            "L3",
        ),
    ],
)
def test_resolve_feature_stage(profile: Dict[str, Any], stage: str) -> None:
    assert resolve_feature_stage(profile) == stage


@pytest.mark.parametrize(
    ("profile", "preset_id"),
    [
        (_profile(infrastructure="local_models"), "local-first"),
        (_profile(infrastructure="free_only"), "cli-backends"),
        (_profile(infrastructure="cloud_key", experience_stage="beginner"), "cloud-balanced"),
        (_profile(infrastructure="cloud_key", experience_stage="has_system"), "power-user"),
    ],
)
def test_resolve_preset_id(profile: Dict[str, Any], preset_id: str) -> None:
    assert resolve_preset_id(profile) == preset_id


def _service(tmp_path: Path, current: Dict[str, str] | None = None) -> OnboardingPlanService:
    manager = MagicMock()
    manager.env_path = tmp_path / ".env"
    manager.read_config_map.return_value = dict(current or {})
    scs = MagicMock()
    scs._manager = manager
    scs.update.return_value = {
        "success": True,
        "config_version": "v2",
        "applied_count": 1,
        "updated_keys": ["REPORT_LANGUAGE"],
        "skipped_masked_count": 0,
        "reload_triggered": True,
        "warnings": [],
    }
    return OnboardingPlanService(system_config_service=scs, state_path=tmp_path / "onboarding_state.json")


def test_build_plan_rule_engine_without_model_is_honest(tmp_path: Path) -> None:
    service = _service(tmp_path, current={})
    plan = service.build_plan(
        _profile(markets=["cn", "hk"], infrastructure="cloud_key"),
        model_available=False,
        prefer_llm=True,
    )
    assert plan["engine"] == "rules"
    assert "No model" in plan["llm_note"] or "no model" in plan["llm_note"].lower()
    assert plan["recommended_preset_id"] == "cloud-balanced"
    assert plan["feature_stage"] == "L0"
    keys = {item["key"] for item in plan["config_items"]}
    assert "REPORT_LANGUAGE" in keys
    assert "STOCK_LIST" in keys
    assert "MARKET_REVIEW_ENABLED" in keys
    assert all(not is_secret_config_key(k) for k in keys)
    assert any(todo["id"] == "paste_cloud_key" for todo in plan["todos"])
    assert plan["today_plan"]
    assert plan["week_plan"]
    assert "buy" not in plan["disclaimer"].lower() or "never" in plan["disclaimer"].lower()


def test_build_plan_local_models_seeds_local_preset(tmp_path: Path) -> None:
    service = _service(tmp_path, current={"STOCK_LIST": "600519"})
    plan = service.build_plan(
        _profile(infrastructure="local_models", markets=["us"]),
        model_available=False,
        prefer_llm=False,
    )
    assert plan["recommended_preset_id"] == "local-first"
    keys = {item["key"] for item in plan["config_items"]}
    # Existing watchlist must not be overwritten.
    assert "STOCK_LIST" not in keys
    assert "LLM_OLLAMA_ENABLED" in keys or "GENERATION_BACKEND" in keys


def test_apply_plan_round_trip_persists_state(tmp_path: Path) -> None:
    service = _service(tmp_path, current={})
    result = service.apply_plan(
        _profile(markets=["cn"], report_language="en"),
        config_version="v1",
        confirm=True,
    )
    assert result["success"] is True
    assert result["config_version"] == "v2"
    assert "REPORT_LANGUAGE" in result["applied_keys"]
    service._system_config.update.assert_called_once()
    call_kwargs = service._system_config.update.call_args.kwargs
    assert call_kwargs["config_version"] == "v1"
    assert call_kwargs["reload_now"] is True
    for item in call_kwargs["items"]:
        assert not is_secret_config_key(item["key"])

    state = service.get_state()
    assert state is not None
    assert state["status"] == "applied"
    assert state["profile"]["report_language"] == "en"
    assert state["plan"]["engine"] == "rules"

    reset = service.reset_state()
    assert reset["reset"] is True
    assert service.get_state() is None


def test_apply_requires_confirm(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(OnboardingProfileValidationError):
        service.apply_plan(_profile(), config_version="v1", confirm=False)


def test_apply_rejects_secret_items_if_injected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(tmp_path)

    def _poison_plan(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        plan = {
            "schema_version": 1,
            "engine": "rules",
            "llm_note": "test",
            "model_available": False,
            "prefer_llm": False,
            "profile": normalize_profile(_profile()),
            "feature_stage": "L0",
            "feature_path": {"stage": "L0", "label": "x", "primary_path": [], "emphasize": [], "defer": []},
            "recommended_preset_id": "cloud-balanced",
            "recommended_preset_name": "Cloud",
            "beginner_mode_recommended": True,
            "config_changes": [],
            "config_items": [{"key": "OPENAI_API_KEY", "value": "sk-fake"}],
            "todos": [],
            "today_plan": [],
            "week_plan": [],
            "disclaimer": "x",
            "generated_at": "2026-01-01T00:00:00Z",
        }
        return plan

    monkeypatch.setattr(service, "build_plan", _poison_plan)
    with pytest.raises(OnboardingSecretRejectedError):
        service.apply_plan(_profile(), config_version="v1", confirm=True)
    service._system_config.update.assert_not_called()
