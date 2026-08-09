# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Config loading tests for offline OCR agent tool flags (issue #196)."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Config


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_ocr_config_defaults_off(_mock_groups, _mock_litellm, _mock_setup_env) -> None:
    with patch.dict(os.environ, {"STOCK_LIST": "600519"}, clear=True):
        config = Config._load_from_env()
    assert config.ocr_agent_tool_enabled is False
    assert config.ocr_file_root is None
    assert config.ocr_langs == "chi_sim+eng"
    assert config.ocr_timeout_seconds == 30


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_ocr_config_enabled_with_root(_mock_groups, _mock_litellm, _mock_setup_env) -> None:
    with patch.dict(
        os.environ,
        {"STOCK_LIST": "600519", "OCR_AGENT_TOOL_ENABLED": "true", "OCR_FILE_ROOT": "/tmp/ocr-root", "OCR_LANGS": "eng", "OCR_TIMEOUT_SECONDS": "45"},
        clear=True,
    ):
        config = Config._load_from_env()
    assert config.ocr_agent_tool_enabled is True
    assert config.ocr_file_root == "/tmp/ocr-root"
    assert config.ocr_langs == "eng"
    assert config.ocr_timeout_seconds == 45
