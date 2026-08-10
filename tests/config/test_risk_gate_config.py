# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Mandatory Risk Manager profile loading and registry contracts."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.config import Config
from src.config_parts.parsers import parse_risk_gate_profile
from src.core.config_registry import get_field_definition


def test_risk_gate_profile_registry_contract() -> None:
    field = get_field_definition("RISK_GATE_PROFILE")

    assert field["default_value"] == "balanced"
    assert field["ui_control"] == "select"
    assert field["validation"]["enum"] == [
        "conservative",
        "balanced",
        "aggressive",
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, "balanced"),
        ("CONSERVATIVE", "conservative"),
        (" aggressive ", "aggressive"),
    ],
)
def test_parse_risk_gate_profile(raw, expected) -> None:
    assert parse_risk_gate_profile(raw) == expected


def test_invalid_risk_gate_profile_is_not_silently_disabled() -> None:
    with pytest.raises(ValueError, match="RISK_GATE_PROFILE"):
        parse_risk_gate_profile("off")


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_invalid_risk_gate_profile_stops_config_loading(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(
        os.environ,
        {"STOCK_LIST": "600519", "RISK_GATE_PROFILE": "disabled"},
        clear=True,
    ):
        with pytest.raises(ValueError, match="RISK_GATE_PROFILE"):
            Config._load_from_env()
