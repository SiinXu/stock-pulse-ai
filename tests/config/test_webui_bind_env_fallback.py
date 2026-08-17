# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Config loading tests for the legacy WebUI bind env fallback (issue #167).

`WEBUI_HOST` / `WEBUI_PORT` were renamed from `API_HOST` / `API_PORT`, and the
old names stayed supported. The retired `webui.py` launcher resolved that
fallback itself, so retiring it in favour of `python main.py --webui-only`
moved the bind onto `Config._load_from_env()`, which had no fallback. These
tests pin the precedence so both entrypoints keep resolving the same bind.
"""

from __future__ import annotations

import os
from unittest.mock import patch

from src.config import Config


def _load(env: dict[str, str]) -> Config:
    """Load a Config from an isolated environment containing only `env`."""
    with patch.dict(os.environ, {"STOCK_LIST": "600519", **env}, clear=True):
        return Config._load_from_env()


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_legacy_api_keys_drive_bind_when_webui_keys_absent(
    _mock_groups, _mock_litellm, _mock_setup_env
) -> None:
    config = _load({"API_HOST": "0.0.0.0", "API_PORT": "8888"})

    assert config.webui_host == "0.0.0.0"
    assert config.webui_port == 8888


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_webui_keys_win_when_both_are_set(
    _mock_groups, _mock_litellm, _mock_setup_env
) -> None:
    config = _load(
        {
            "WEBUI_HOST": "10.0.0.5",
            "WEBUI_PORT": "9001",
            "API_HOST": "0.0.0.0",
            "API_PORT": "8888",
        }
    )

    assert config.webui_host == "10.0.0.5"
    assert config.webui_port == 9001


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_defaults_apply_when_no_bind_keys_are_set(
    _mock_groups, _mock_litellm, _mock_setup_env
) -> None:
    config = _load({})

    assert config.webui_host == "127.0.0.1"
    assert config.webui_port == 8000


@patch("src.config.setup_env")
@patch.object(Config, "_parse_litellm_yaml", return_value=[])
@patch.object(Config, "_parse_stock_email_groups", return_value=[])
def test_invalid_legacy_api_port_falls_back_like_invalid_webui_port(
    _mock_groups, _mock_litellm, _mock_setup_env
) -> None:
    """A bad legacy value must hit the same validation, not slip through."""
    assert _load({"API_PORT": "invalid"}).webui_port == 8000
    assert _load({"WEBUI_PORT": "invalid"}).webui_port == 8000
    # Out-of-range legacy values are clamped by the same bounds as WEBUI_PORT.
    assert _load({"API_PORT": "70000"}).webui_port == 65535
    assert _load({"API_PORT": "0"}).webui_port == 1
