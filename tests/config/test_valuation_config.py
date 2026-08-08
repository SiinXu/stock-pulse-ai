# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Environment and registry contracts for the valuation Agent Tool flag."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Config
from src.core.config_registry import get_field_definition, get_registered_field_keys


def test_valuation_flag_is_registered_and_documented() -> None:
    key = "VALUATION_AGENT_TOOL_ENABLED"
    assert key in set(get_registered_field_keys())
    field = get_field_definition(key)
    assert field["category"] == "agent"
    assert field["default_value"] == "false"
    assert field["data_type"] == "boolean"
    assert field.get("help_key") == "settings.agent.VALUATION_AGENT_TOOL_ENABLED"
    assert field.get("examples")
    assert field.get("docs")
    assert "restart_required" in field.get("warning_codes", [])


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_valuation_flag_defaults_off(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(os.environ, {"STOCK_LIST": "600519"}, clear=True):
        config = Config._load_from_env()
    assert config.valuation_agent_tool_enabled is False


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_valuation_flag_parses_true(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "VALUATION_AGENT_TOOL_ENABLED": "true",
        },
        clear=True,
    ):
        config = Config._load_from_env()
    assert config.valuation_agent_tool_enabled is True
