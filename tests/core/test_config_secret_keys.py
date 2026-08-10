# -*- coding: utf-8 -*-
"""Unit tests for shared config secret-key classification heuristics.

Uses real configuration key names from .env.example / registry so regressions
match production identifiers rather than synthetic placeholders.
"""

from __future__ import annotations

import unittest

from src.core.config_registry import _is_sensitive_key, get_field_definition
from src.core.config_secret_keys import (
    is_secret_config_key,
    is_sensitive_config_key_name,
)
from src.services.config_presets import is_secret_config_key as preset_is_secret
from src.services.onboarding_plan_service import (
    is_secret_config_key as onboarding_is_secret,
)
from src.utils.sanitize import is_sensitive_key as sanitize_is_sensitive_key


class TestSensitiveConfigKeyClassifier(unittest.TestCase):
    """Credential-bearing names must be classified; quantity/public names must not."""

    _MUST_BE_SENSITIVE = (
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "TUSHARE_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "FEISHU_APP_SECRET",
        "EMAIL_PASSWORD",
        "LLM_USAGE_HMAC_SECRET",
        "PUSHOVER_USER_KEY",
        "AIHUBMIX_KEY",
        "DINGTALK_APP_KEY",
        "SERVERCHAN3_SENDKEY",
        "CUSTOM_WEBHOOK_BEARER_TOKEN",
        "LLM_ALPHA_EXTRA_HEADERS",
        "ALPHASIFT_INSTALL_SPEC",
        "LITELLM_CONFIG",
        "LONGBRIDGE_ACCESS_TOKEN",
        "LONGBRIDGE_APP_KEY",
        "LONGBRIDGE_APP_SECRET",
        "LONGBRIDGE_OAUTH_TOKEN_CACHE_B64",
        "MCP_HTTP_SESSION_TOKEN_SHA256",
        "SOCIAL_SENTIMENT_API_KEY",
        "COINGECKO_API_KEY",
        "FINNHUB_API_KEY",
        "ALPHAVANTAGE_API_KEY",
        "LLM_DEEPSEEK_API_KEY",
        "LLM_OPENROUTER_API_KEY",
    )

    _MUST_NOT_BE_SENSITIVE = (
        "LLM_MAX_TOKENS",
        "ANTHROPIC_MAX_TOKENS",
        "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS",
        "LLM_USAGE_HMAC_KEY_VERSION",
        "DISCORD_INTERACTIONS_PUBLIC_KEY",
        "FEISHU_WEBHOOK_KEYWORD",
        "STOCK_LIST",
        "REPORT_LANGUAGE",
        "LOG_LEVEL",
        "ADMIN_AUTH_ENABLED",
        "USE_PROXY",
        "PROXY_PORT",
        "LLM_OLLAMA_ENABLED",
        "LLM_OLLAMA_BASE_URL",
        "GENERATION_BACKEND",
        "COINGECKO_API_BASE",
        "COINGECKO_API_PLAN",
        "MCP_SERVER_HOST",
        "MCP_SERVER_ENABLED",
        "DATA_VALIDATION_ENABLED",
        "CRYPTO_PROVIDER_ENABLED",
        "PROVIDER_MARKET_DATA_MODE",
        "REPORT_MODE",
    )

    def test_real_credential_keys_are_sensitive(self) -> None:
        for key in self._MUST_BE_SENSITIVE:
            with self.subTest(key=key):
                self.assertTrue(
                    is_sensitive_config_key_name(key),
                    f"{key} must be classified as sensitive",
                )
                self.assertTrue(_is_sensitive_key(key.upper()))
                self.assertTrue(is_secret_config_key(key))

    def test_structural_and_feature_keys_are_not_sensitive(self) -> None:
        for key in self._MUST_NOT_BE_SENSITIVE:
            with self.subTest(key=key):
                self.assertFalse(
                    is_sensitive_config_key_name(key),
                    f"{key} must not be classified as sensitive",
                )
                self.assertFalse(_is_sensitive_key(key.upper()))
                self.assertFalse(is_secret_config_key(key))

    def test_empty_name_semantics(self) -> None:
        self.assertFalse(is_sensitive_config_key_name(""))
        self.assertFalse(is_sensitive_config_key_name("   "))
        self.assertTrue(is_secret_config_key(""))
        self.assertTrue(is_secret_config_key("   "))
        self.assertTrue(is_secret_config_key(None))

    def test_call_sites_share_the_same_classifier(self) -> None:
        samples = (
            "OPENAI_API_KEY",
            "LLM_MAX_TOKENS",
            "ALPHASIFT_INSTALL_SPEC",
            "LITELLM_CONFIG",
            "STOCK_LIST",
        )
        for key in samples:
            with self.subTest(key=key):
                expected = is_secret_config_key(key)
                self.assertEqual(preset_is_secret(key), expected)
                self.assertEqual(onboarding_is_secret(key), expected)

    def test_registered_overrides_remain_authoritative_for_display(self) -> None:
        public_key = get_field_definition("DISCORD_INTERACTIONS_PUBLIC_KEY")
        self.assertFalse(public_key["is_sensitive"])
        self.assertEqual(public_key["ui_control"], "text")

        hmac_version = get_field_definition("LLM_USAGE_HMAC_KEY_VERSION")
        self.assertFalse(hmac_version["is_sensitive"])

        hmac_secret = get_field_definition("LLM_USAGE_HMAC_SECRET")
        self.assertTrue(hmac_secret["is_sensitive"])
        self.assertEqual(hmac_secret["ui_control"], "password")

        install_spec = get_field_definition("ALPHASIFT_INSTALL_SPEC")
        self.assertTrue(install_spec["is_sensitive"])
        self.assertEqual(install_spec["ui_control"], "password")

    def test_unregistered_inference_masks_password_control(self) -> None:
        field = get_field_definition("LONGBRIDGE_APP_SECRET", value_hint="opaque")
        self.assertTrue(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "password")

        tokens = get_field_definition("LLM_MAX_TOKENS", value_hint="2048")
        self.assertFalse(tokens["is_sensitive"])
        self.assertNotEqual(tokens["ui_control"], "password")


class TestSanitizeKeyAlignment(unittest.TestCase):
    """Log/diagnostic redaction must catch bare credential KEY suffixes."""

    def test_bare_credential_key_names_are_redacted_in_sanitize(self) -> None:
        for key in (
            "PUSHOVER_USER_KEY",
            "AIHUBMIX_KEY",
            "DINGTALK_APP_KEY",
            "LONGBRIDGE_APP_KEY",
            "ALPHASIFT_INSTALL_SPEC",
            "OPENAI_API_KEY",
        ):
            with self.subTest(key=key):
                self.assertTrue(sanitize_is_sensitive_key(key), key)

    def test_structural_key_names_are_not_redacted_in_sanitize(self) -> None:
        for key in (
            "cache_key",
            "CACHE_KEY",
            "sort_key",
            "primary_key",
            "public_key",
            "DISCORD_INTERACTIONS_PUBLIC_KEY",
            "key",
            "LLM_MAX_TOKENS",
            "LLM_USAGE_HMAC_KEY_VERSION",
        ):
            with self.subTest(key=key):
                self.assertFalse(sanitize_is_sensitive_key(key), key)


if __name__ == "__main__":
    unittest.main()
