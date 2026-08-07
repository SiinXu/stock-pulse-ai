# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Config registry and loading tests for multimodal agent tools flags."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Config
from src.core.config_registry import get_field_definition


def test_multimodal_flags_registered() -> None:
    enabled = get_field_definition("MULTIMODAL_AGENT_TOOLS_ENABLED")
    assert enabled is not None
    assert enabled.get("default_value") == "false"
    assert enabled.get("help_key") == "settings.agent.MULTIMODAL_AGENT_TOOLS_ENABLED"
    assert enabled.get("contract", {}).get("restart_required") is True

    root = get_field_definition("MULTIMODAL_FILE_ROOT")
    assert root is not None
    assert root.get("help_key") == "settings.agent.MULTIMODAL_FILE_ROOT"


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_multimodal_config_defaults_off(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(os.environ, {"STOCK_LIST": "600519"}, clear=True):
        config = Config._load_from_env()

    assert config.multimodal_agent_tools_enabled is False
    assert config.multimodal_file_root is None


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_multimodal_config_enabled_with_root(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "MULTIMODAL_AGENT_TOOLS_ENABLED": "true",
            "MULTIMODAL_FILE_ROOT": "/tmp/multimodal-root",
        },
        clear=True,
    ):
        config = Config._load_from_env()

    assert config.multimodal_agent_tools_enabled is True
    assert config.multimodal_file_root == "/tmp/multimodal-root"
