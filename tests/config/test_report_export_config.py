"""Shared Config ownership for the optional report-export font path."""

import os
from unittest.mock import patch

from src.config import Config
from src.core.config_registry import get_field_definition, get_registered_field_keys


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_report_export_font_path_loads_through_shared_config(
    _mock_groups,
    _mock_yaml,
    _mock_setup,
):
    with patch.dict(
        os.environ,
        {
            "STOCK_LIST": "600519",
            "REPORT_EXPORT_PDF_FONT_PATH": "  /fonts/NotoSansCJK-Regular.otf  ",
        },
        clear=True,
    ):
        config = Config._load_from_env()
    assert config.report_export_pdf_font_path == "/fonts/NotoSansCJK-Regular.otf"


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_report_export_font_path_defaults_to_none(_mock_groups, _mock_yaml, _mock_setup):
    with patch.dict(os.environ, {"STOCK_LIST": "600519"}, clear=True):
        config = Config._load_from_env()
    assert config.report_export_pdf_font_path is None


def test_report_export_font_path_is_registered_for_system_config_api():
    assert "REPORT_EXPORT_PDF_FONT_PATH" in get_registered_field_keys()
    field = get_field_definition("REPORT_EXPORT_PDF_FONT_PATH")
    assert field["category"] == "system"
    assert field["data_type"] == "string"
    assert field["validation"]["maxLength"] == 1024
    assert "fail" in field["description"].lower()
