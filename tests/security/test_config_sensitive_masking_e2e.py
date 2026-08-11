# -*- coding: utf-8 -*-
"""End-to-end leakage guards for sensitive configuration values.

Covers config read API masking, mask-token save preservation, diagnostics /
profile export exclusion, and log-safe redaction for real key names.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Dict
from unittest.mock import patch

from src.config import Config
from src.core.config_manager import ConfigManager
from src.services.config_profile_service import ConfigProfileService
from src.services.run_diagnostics import sanitize_diagnostic_metadata
from src.services.system_config_service import SystemConfigService
from src.utils.sanitize import redact_sensitive_data, redact_sensitive_text


class _ConfigMaskingE2EBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.env_path = Path(self._tmpdir.name) / ".env"
        self._orig_env_file = os.environ.get("ENV_FILE")
        self._write_env(
            "STOCK_LIST=600519",
            "ADMIN_AUTH_ENABLED=true",
            "GEMINI_API_KEY=gemini-live-secret-value",
            "PUSHOVER_USER_KEY=pushover-user-secret-value",
            "AIHUBMIX_KEY=aihubmix-live-secret-value",
            "LONGBRIDGE_APP_KEY=longbridge-app-key-secret",
            "LONGBRIDGE_APP_SECRET=longbridge-app-secret-value",
            "MCP_HTTP_SESSION_TOKEN_SHA256="
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "LLM_MAX_TOKENS=2048",
            "LLM_USAGE_HMAC_KEY_VERSION=local-v1",
            "SOCIAL_SENTIMENT_API_KEY=social-sentiment-secret",
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

    def _write_env(self, *lines: str) -> None:
        self.env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _item_map(self, payload: Dict) -> Dict[str, Dict]:
        return {item["key"]: item for item in payload["items"]}


class TestConfigReadApiMasksSecrets(_ConfigMaskingE2EBase):
    def test_get_config_masks_registered_secrets(self) -> None:
        payload = self.service.get_config(include_schema=True, mask_token="******")
        items = self._item_map(payload)
        mask = payload["mask_token"]

        for key in (
            "GEMINI_API_KEY",
            "PUSHOVER_USER_KEY",
            "AIHUBMIX_KEY",
        ):
            with self.subTest(key=key):
                self.assertIn(key, items)
                self.assertEqual(items[key]["value"], mask)
                self.assertTrue(items[key]["is_masked"])
                self.assertTrue(items[key]["schema"]["is_sensitive"])

        rendered = str(payload)
        for secret in (
            "gemini-live-secret-value",
            "pushover-user-secret-value",
            "aihubmix-live-secret-value",
        ):
            self.assertNotIn(secret, rendered)

    def test_get_config_without_schema_masks_inferred_env_secrets(self) -> None:
        # Unregistered keys are visible when schema expansion is skipped; the
        # name heuristic still drives is_sensitive / masking.
        payload = self.service.get_config(include_schema=False, mask_token="******")
        items = self._item_map(payload)
        mask = payload["mask_token"]

        for key in (
            "LONGBRIDGE_APP_KEY",
            "LONGBRIDGE_APP_SECRET",
            "MCP_HTTP_SESSION_TOKEN_SHA256",
            "SOCIAL_SENTIMENT_API_KEY",
        ):
            with self.subTest(key=key):
                self.assertIn(key, items)
                self.assertEqual(items[key]["value"], mask)
                self.assertTrue(items[key]["is_masked"])

        rendered = str(payload)
        for secret in (
            "longbridge-app-key-secret",
            "longbridge-app-secret-value",
            "social-sentiment-secret",
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        ):
            self.assertNotIn(secret, rendered)

    def test_get_config_does_not_mask_token_count_or_key_version(self) -> None:
        payload = self.service.get_config(include_schema=False, mask_token="******")
        items = self._item_map(payload)

        self.assertEqual(items["LLM_MAX_TOKENS"]["value"], "2048")
        self.assertFalse(items["LLM_MAX_TOKENS"]["is_masked"])

        # Registered non-secret version label remains visible with schema.
        with_schema = self.service.get_config(include_schema=True, mask_token="******")
        schema_items = self._item_map(with_schema)
        self.assertEqual(schema_items["LLM_USAGE_HMAC_KEY_VERSION"]["value"], "local-v1")
        self.assertFalse(schema_items["LLM_USAGE_HMAC_KEY_VERSION"]["is_masked"])
        self.assertFalse(schema_items["LLM_USAGE_HMAC_KEY_VERSION"]["schema"]["is_sensitive"])


class TestMaskTokenDoesNotClearSecrets(_ConfigMaskingE2EBase):
    def test_update_skips_mask_token_for_inferred_and_registered_secrets(self) -> None:
        before = self.manager.read_config_map()
        version = self.manager.get_config_version()

        response = self.service.update(
            config_version=version,
            items=[
                {"key": "GEMINI_API_KEY", "value": "******"},
                {"key": "PUSHOVER_USER_KEY", "value": "******"},
                {"key": "AIHUBMIX_KEY", "value": "******"},
                {"key": "LONGBRIDGE_APP_SECRET", "value": "******"},
                {"key": "SOCIAL_SENTIMENT_API_KEY", "value": "******"},
                {"key": "STOCK_LIST", "value": "600519,300750"},
            ],
            mask_token="******",
            reload_now=False,
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["skipped_masked_count"], 5)
        self.assertIn("STOCK_LIST", response["updated_keys"])

        after = self.manager.read_config_map()
        self.assertEqual(after["STOCK_LIST"], "600519,300750")
        for key in (
            "GEMINI_API_KEY",
            "PUSHOVER_USER_KEY",
            "AIHUBMIX_KEY",
            "LONGBRIDGE_APP_SECRET",
            "SOCIAL_SENTIMENT_API_KEY",
        ):
            with self.subTest(key=key):
                self.assertEqual(after[key], before[key])
                self.assertNotEqual(after[key], "******")


class TestDiagnosticsAndExportDoNotLeakSecrets(_ConfigMaskingE2EBase):
    def test_sanitize_diagnostic_metadata_redacts_credential_keys(self) -> None:
        raw = {
            "PUSHOVER_USER_KEY": "pushover-user-secret-value",
            "AIHUBMIX_KEY": "aihubmix-live-secret-value",
            "LONGBRIDGE_APP_KEY": "longbridge-app-key-secret",
            "LLM_MAX_TOKENS": 2048,
            "STOCK_LIST": "600519",
        }
        sanitized = sanitize_diagnostic_metadata(raw)
        self.assertEqual(sanitized.get("pushover_user_key"), "<redacted>")
        self.assertEqual(sanitized.get("aihubmix_key"), "<redacted>")
        self.assertEqual(sanitized.get("longbridge_app_key"), "<redacted>")
        self.assertEqual(sanitized.get("llm_max_tokens"), 2048)
        self.assertEqual(sanitized.get("stock_list"), "600519")
        self.assertNotIn("pushover-user-secret-value", str(sanitized))
        self.assertNotIn("aihubmix-live-secret-value", str(sanitized))

    def test_profile_export_excludes_secret_keys(self) -> None:
        profile_service = ConfigProfileService(system_config_service=self.service)
        document = profile_service.export_profile()
        config_values = document.get("config") or document.get("spec", {}).get("config") or {}
        if not config_values and isinstance(document, dict):
            for value in document.values():
                if isinstance(value, dict) and any(
                    isinstance(k, str) and k.isupper() for k in value
                ):
                    config_values = value
                    break

        rendered = str(document)
        for secret in (
            "gemini-live-secret-value",
            "pushover-user-secret-value",
            "aihubmix-live-secret-value",
            "longbridge-app-key-secret",
            "longbridge-app-secret-value",
            "social-sentiment-secret",
        ):
            self.assertNotIn(secret, rendered)

        for key in (
            "GEMINI_API_KEY",
            "PUSHOVER_USER_KEY",
            "AIHUBMIX_KEY",
            "LONGBRIDGE_APP_KEY",
            "LONGBRIDGE_APP_SECRET",
            "SOCIAL_SENTIMENT_API_KEY",
        ):
            self.assertNotIn(key, config_values)

    def test_log_redaction_masks_bare_key_suffix_values(self) -> None:
        mapping = {
            "PUSHOVER_USER_KEY": "pushover-user-secret-value",
            "AIHUBMIX_KEY": "aihubmix-live-secret-value",
            "LLM_MAX_TOKENS": "2048",
        }
        redacted = redact_sensitive_data(mapping)
        self.assertEqual(redacted["PUSHOVER_USER_KEY"], "[REDACTED]")
        self.assertEqual(redacted["AIHUBMIX_KEY"], "[REDACTED]")
        self.assertEqual(redacted["LLM_MAX_TOKENS"], "2048")

        text = redact_sensitive_text(
            "PUSHOVER_USER_KEY=pushover-user-secret-value LLM_MAX_TOKENS=2048"
        )
        self.assertNotIn("pushover-user-secret-value", text)
        self.assertIn("LLM_MAX_TOKENS=2048", text)


class TestErrorPathsDoNotEchoSecrets(_ConfigMaskingE2EBase):
    def test_notification_test_error_redacts_sensitive_effective_values(self) -> None:
        with patch.object(
            self.service,
            "_dispatch_notification_test",
            side_effect=RuntimeError("upstream failed with pushover-user-secret-value"),
        ):
            result = self.service.test_notification_channel(
                channel="pushover",
                items=[
                    {"key": "PUSHOVER_USER_KEY", "value": "pushover-user-secret-value"},
                    {"key": "PUSHOVER_API_TOKEN", "value": "pushover-api-token-secret"},
                ],
                mask_token="******",
            )

        rendered = str(result)
        self.assertNotIn("pushover-user-secret-value", rendered)
        self.assertNotIn("pushover-api-token-secret", rendered)


if __name__ == "__main__":
    unittest.main()
