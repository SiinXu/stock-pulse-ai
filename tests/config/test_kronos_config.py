"""Environment and validation contracts for optional Kronos configuration."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Config
from src.core.config_registry import WEB_SETTINGS_HIDDEN_FROM_UI


def test_kronos_configuration_is_visible_in_web_settings_registry() -> None:
    """Productized Kronos settings are no longer hidden from the Web UI."""
    from src.core.config_registry import get_field_definition, get_registered_field_keys

    registered = set(get_registered_field_keys())
    for key in ("KRONOS_ENABLED", "KRONOS_MODEL_SIZE", "KRONOS_WEIGHTS_DIR"):
        assert key not in WEB_SETTINGS_HIDDEN_FROM_UI
        assert key in registered
        field = get_field_definition(key)
        assert field["category"] == "ai_model"
        assert field.get("help_key")


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_kronos_defaults_are_closed(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(os.environ, {"STOCK_LIST": "600519"}, clear=True):
        config = Config._load_from_env()

    assert config.kronos_enabled is False
    assert config.kronos_model_size == "mini"
    assert config.kronos_weights_dir is None


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_kronos_environment_values_are_normalized(
    _mock_groups,
    _mock_litellm,
    _mock_setup_env,
) -> None:
    with patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "KRONOS_ENABLED": "true",
            "KRONOS_MODEL_SIZE": " SMALL ",
            "KRONOS_WEIGHTS_DIR": " /models/kronos ",
        },
        clear=True,
    ):
        config = Config._load_from_env()

    assert config.kronos_enabled is True
    assert config.kronos_model_size == "small"
    assert config.kronos_weights_dir == "/models/kronos"


def test_enabled_kronos_reports_invalid_size_and_missing_weights() -> None:
    config = Config(
        stock_list=["600519"],
        kronos_enabled=True,
        kronos_model_size="large",
        kronos_weights_dir=None,
    )

    issues = {
        issue.field: issue
        for issue in config.validate_structured()
        if issue.field.startswith("KRONOS_")
    }

    assert issues["KRONOS_MODEL_SIZE"].code == "kronos_model_size_invalid"
    assert issues["KRONOS_MODEL_SIZE"].severity == "error"
    assert issues["KRONOS_WEIGHTS_DIR"].code == "kronos_weights_dir_missing"
    assert issues["KRONOS_WEIGHTS_DIR"].severity == "warning"
