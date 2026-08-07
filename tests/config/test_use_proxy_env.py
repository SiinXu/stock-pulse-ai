# -*- coding: utf-8 -*-
"""Consumption-path and sensitivity coverage for USE_PROXY settings."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from src.config import apply_use_proxy_env
from src.core.config_registry import get_field_definition
from src.utils.sanitize import redact_sensitive_text


class TestApplyUseProxyEnv(unittest.TestCase):
    def test_applies_http_proxy_when_enabled(self) -> None:
        env = {
            "USE_PROXY": "true",
            "PROXY_HOST": "10.0.0.9",
            "PROXY_PORT": "7890",
            "GITHUB_ACTIONS": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            for key in ("http_proxy", "https_proxy"):
                os.environ.pop(key, None)
            applied = apply_use_proxy_env()
            self.assertEqual(applied, "http://10.0.0.9:7890")
            self.assertEqual(os.environ.get("http_proxy"), "http://10.0.0.9:7890")
            self.assertEqual(os.environ.get("https_proxy"), "http://10.0.0.9:7890")

    def test_skips_under_github_actions(self) -> None:
        env = {
            "USE_PROXY": "true",
            "PROXY_HOST": "10.0.0.9",
            "PROXY_PORT": "7890",
            "GITHUB_ACTIONS": "true",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("http_proxy", None)
            os.environ.pop("https_proxy", None)
            self.assertIsNone(apply_use_proxy_env())
            self.assertNotIn("http_proxy", os.environ)

    def test_disabled_does_not_clear_existing_proxy(self) -> None:
        env = {
            "USE_PROXY": "false",
            "GITHUB_ACTIONS": "false",
            "http_proxy": "http://keep.example:1",
            "https_proxy": "http://keep.example:1",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertIsNone(apply_use_proxy_env())
            self.assertEqual(os.environ.get("http_proxy"), "http://keep.example:1")


class TestProxyHostSensitivityRedaction(unittest.TestCase):
    def test_proxy_host_field_redacted_in_text(self) -> None:
        raw = "PROXY_HOST=user:s3cret@127.0.0.1 session_id=abc"
        redacted = redact_sensitive_text(raw)
        self.assertNotIn("s3cret", redacted)
        self.assertIn("session_id=abc", redacted)

    def test_registry_marks_proxy_host_sensitive(self) -> None:
        field = get_field_definition("PROXY_HOST")
        self.assertTrue(field["is_sensitive"])


if __name__ == "__main__":
    unittest.main()
