# -*- coding: utf-8 -*-
"""Shared fixtures and imports for system configuration service tests."""

import os
import json
import logging
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

import requests

from tests._llm_env_isolation import restore_ambient_llm_env, strip_ambient_llm_env
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.config import ANSPIRE_LLM_MODEL_DEFAULT, DEFAULT_ALPHASIFT_INSTALL_SPEC, Config
from src.core.config_manager import ConfigManager
from src.llm.backend_registry import GENERATION_ONLY_BACKEND_IDS
from src.services.system_config_service import ConfigConflictError, ConfigImportError, ConfigValidationError, SystemConfigService


class _SystemConfigServiceTestCaseBase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_notification_env = {
            key: os.environ[key]
            for key in SystemConfigService._NOTIFICATION_TEST_KEY_MAP
            if key in os.environ
        }
        for key in SystemConfigService._NOTIFICATION_TEST_KEY_MAP:
            os.environ.pop(key, None)
        # A developer .env leaked into os.environ (e.g. litellm's load_dotenv at
        # import) must not bleed LLM config into these tests; the temp .env below
        # is the authoritative source. Restored in tearDown.
        self._saved_llm_env = strip_ambient_llm_env()
        self._orig_env_file = os.environ.get("ENV_FILE")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519,000001",
                    "GEMINI_API_KEY=secret-key-value",
                    "SCHEDULE_TIME=18:00",
                    "LOG_LEVEL=INFO",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        Config.reset_instance()

        self.manager = ConfigManager(env_path=self.env_path)
        self.service = SystemConfigService(manager=self.manager)

    def tearDown(self) -> None:
        Config.reset_instance()
        if self._orig_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = self._orig_env_file
        for key in SystemConfigService._NOTIFICATION_TEST_KEY_MAP:
            os.environ.pop(key, None)
        os.environ.update(self._saved_notification_env)
        restore_ambient_llm_env(self._saved_llm_env)
        self.temp_dir.cleanup()

    def _rewrite_env(self, *lines: str) -> None:
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        Config.reset_instance()
        self.manager = ConfigManager(env_path=self.env_path)
        self.service = SystemConfigService(manager=self.manager)

    @staticmethod
    def _wizard_channel_items(
        *,
        name: str,
        provider_id: str,
        protocol: str,
        models: str,
        primary_route: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        existing_channels: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Mirror exactly what the first-run wizard emits for one Connection."""
        channels = list(dict.fromkeys(list(existing_channels or []) + [name]))
        up = name.upper()
        items: List[Dict[str, str]] = [
            {"key": "LLM_CONFIG_MODE", "value": "channels"},
            {"key": "GENERATION_BACKEND", "value": "litellm"},
            {"key": "LLM_CHANNELS", "value": ",".join(channels)},
            {"key": f"LLM_{up}_PROVIDER", "value": provider_id},
            {"key": f"LLM_{up}_PROTOCOL", "value": protocol},
            {"key": f"LLM_{up}_MODELS", "value": models},
            {"key": f"LLM_{up}_ENABLED", "value": "true"},
            {"key": "LITELLM_MODEL", "value": primary_route},
        ]
        if base_url:
            items.append({"key": f"LLM_{up}_BASE_URL", "value": base_url})
        if api_key:
            items.append({"key": f"LLM_{up}_API_KEY", "value": api_key})
        return items

    @staticmethod
    def _mock_completion_response(content: str = "OK", tool_calls=None):
        message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    @staticmethod
    def _mock_http_response(status_code: int, json_body: Optional[Dict[str, Any]] = None):
        response = Mock()
        response.status_code = status_code
        response.text = "ok" if status_code == 200 else "error"
        response.json.return_value = json_body or {"errcode": 0}
        return response

    def _notification_test_env(self):
        return patch.dict(os.environ, {"ENV_FILE": str(self.env_path)}, clear=True)


__all__ = (
    "_SystemConfigServiceTestCaseBase",
    "ANSPIRE_LLM_MODEL_DEFAULT",
    "Any",
    "Config",
    "ConfigConflictError",
    "ConfigImportError",
    "ConfigManager",
    "ConfigValidationError",
    "DEFAULT_ALPHASIFT_INSTALL_SPEC",
    "Dict",
    "GENERATION_ONLY_BACKEND_IDS",
    "List",
    "Mock",
    "Optional",
    "Path",
    "SimpleNamespace",
    "SystemConfigService",
    "contextmanager",
    "json",
    "logging",
    "os",
    "patch",
    "requests",
    "tempfile",
    "unittest",
)
