# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Configuration contracts for information-quality grading (Issue #123)."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Config
from src.core.config_registry import get_field_definition


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_info_quality_config_defaults_and_explicit_false(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(os.environ, {"STOCK_LIST": "600519"}, clear=True):
        defaults = Config._load_from_env()
    with patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "INFO_QUALITY_GRADING_ENABLED": "false",
            "FORCED_CONCLUSION_ENABLED": "false",
        },
        clear=True,
    ):
        disabled = Config._load_from_env()

    assert defaults.info_quality_grading_enabled is True
    assert defaults.forced_conclusion_enabled is True
    assert disabled.info_quality_grading_enabled is False
    assert disabled.forced_conclusion_enabled is False


def test_info_quality_config_keys_are_registered_as_boolean_switches() -> None:
    for key in ("INFO_QUALITY_GRADING_ENABLED", "FORCED_CONCLUSION_ENABLED"):
        field = get_field_definition(key)
        assert field["data_type"] == "boolean"
        assert field["ui_control"] == "switch"
        assert field["default_value"] == "true"
        assert field["help_key"] == f"settings.data_source.{key}"
