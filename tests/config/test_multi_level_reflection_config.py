# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Environment contracts for multi-level reflection runtime settings."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.config import Config
from src.core.config_registry import get_field_definition, get_registered_field_keys


_REMOVED_KEYS = {
    "AGENT_STEP_CRITIQUE_LLM_BUDGET",
    "AGENT_REFLECTION_MAX_REVISE",
    "AGENT_META_REVIEW_LLM_BUDGET",
}


def test_reflection_registry_only_advertises_consumed_runtime_settings() -> None:
    keys = set(get_registered_field_keys())
    assert _REMOVED_KEYS.isdisjoint(keys)
    assert get_field_definition("AGENT_REFLECTION_LLM_BUDGET")["validation"] == {
        "min": 0,
        "max": 1,
    }
    assert get_field_definition("AGENT_META_REVIEW_MIN_EPISODES")[
        "validation"
    ] == {"min": 1, "max": 50000}


@pytest.mark.parametrize(
    ("key", "value", "attribute", "expected"),
    [
        ("AGENT_REFLECTION_LLM_BUDGET", "2", "agent_reflection_llm_budget", 1),
        ("AGENT_REFLECTION_LLM_BUDGET", "-1", "agent_reflection_llm_budget", 0),
        (
            "AGENT_META_REVIEW_MIN_EPISODES",
            "0",
            "agent_meta_review_min_episodes",
            1,
        ),
        (
            "AGENT_META_REVIEW_MIN_EPISODES",
            "50001",
            "agent_meta_review_min_episodes",
            50000,
        ),
    ],
)
@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_reflection_config_clamps_out_of_range_values(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
    key: str,
    value: str,
    attribute: str,
    expected: int,
) -> None:
    with patch.dict(
        os.environ,
        {"STOCK_LIST": "600519", key: value},
        clear=True,
    ):
        config = Config._load_from_env()
    assert getattr(config, attribute) == expected


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_reflection_config_parses_supported_values(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "AGENT_STEP_CRITIQUE_ENABLED": "true",
            "AGENT_REFLECTION_ENABLED": "true",
            "AGENT_REFLECTION_LLM_BUDGET": "0",
            "AGENT_META_REVIEW_ENABLED": "true",
            "AGENT_META_REVIEW_MIN_EPISODES": "50000",
        },
        clear=True,
    ):
        config = Config._load_from_env()

    assert config.agent_step_critique_enabled is True
    assert config.agent_reflection_enabled is True
    assert config.agent_reflection_llm_budget == 0
    assert config.agent_meta_review_enabled is True
    assert config.agent_meta_review_min_episodes == 50000
    for attr in (
        "agent_step_critique_llm_budget",
        "agent_reflection_max_revise",
        "agent_meta_review_llm_budget",
    ):
        assert not hasattr(config, attr)
