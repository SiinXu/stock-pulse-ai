# -*- coding: utf-8 -*-
"""Guard: every documented .env.example key must be in the config registry.

Background: Settings UI metadata is driven by ``src.core.config_registry``.
Keys that appear in ``.env.example`` but are never registered fall into the
uncategorized bucket with wrong controls (boolean/enum rendered as free text)
or stay invisible until a value is saved. Backend runtime tests do not catch
this presentation contract gap.

This module freezes the unregistered stock at introduction as a **historical
baseline** and fails closed when debt grows:

- Live unregistered keys must be a subset of the baseline (no new debt keys).
- Live unregistered count must be ``<= TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_MAX_COUNT``.
- ``MAX_COUNT`` must stay ``<= HARD_CEILING`` (never raise the ceiling).
- Baseline membership is pinned by SHA-256; expanding the baseline requires
  deliberately rewriting the pinned hash (review blocker — do not do this to
  green CI; register the key instead).

Registration tasks (issue #1023 tasks 2/3/4) only need to **register** keys —
the live unregistered set is derived at test time, so this file does not need
a second parallel key list that drifts.

See: https://github.com/SiinXu/stock-pulse-ai/issues/1023
"""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

from src.core.config_registry import (
    _infer_data_type,
    _infer_ui_control,
    get_field_definition,
    get_registered_field_keys,
)

_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"
_DOCUMENTED_ENV_ASSIGNMENT_RE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=")

# ---------------------------------------------------------------------------
# Temporary debt baseline (issue #1023). CLEANUP PLAN:
#   - Tasks 2/3/4: register keys in config_registry_parts/*; live unregistered
#     shrinks automatically. Optionally remove retired keys from BASELINE and
#     recompute BASELINE_SHA256; lower MAX_COUNT when acknowledging progress.
#   - Tasks 5-10: long-tail cleanup until unregistered is empty and MAX is 0.
# DO NOT expand BASELINE / raise HARD_CEILING / rewrite BASELINE_SHA256 to make
# CI green for a new key — register the key instead.
# ---------------------------------------------------------------------------
TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE = frozenset({
    "AGENT_DECISION_AGENT_TIMEOUT_S",
    "AGENT_INTEL_AGENT_TIMEOUT_S",
    "AGENT_MAX_IDENTICAL_TOOL_CALLS",
    "AGENT_MAX_STAGE_ENTRIES",
    "AGENT_PORTFOLIO_AGENT_TIMEOUT_S",
    "AGENT_RISK_AGENT_TIMEOUT_S",
    "AGENT_SKILL_AGENT_TIMEOUT_S",
    "AGENT_STAGE_FAILURE_POLICY",
    "AGENT_TECHNICAL_AGENT_TIMEOUT_S",
    "AGENT_TOOL_TIMEOUT_S",
    "AKSHARE_PRIORITY",
    "ALLOW_INSECURE_PUBLIC_BIND",
    "ALPHASIFT_DAILY_CALL_TIMEOUT_SEC",
    "ALPHASIFT_DAILY_HISTORY_CACHE_DIR",
    "ALPHASIFT_DATA_DIR",
    "ALPHASIFT_EASTMONEY_JITTER_SEC",
    "ALPHASIFT_EASTMONEY_MIN_INTERVAL_SEC",
    "ALPHASIFT_FALLBACK_SNAPSHOT_PATH",
    "ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR",
    "ALPHASIFT_SNAPSHOT_CALL_TIMEOUT_SEC",
    "ALPHASIFT_SOURCE_CALL_TIMEOUT_SEC",
    "ALPHAVANTAGE_API_KEY",
    "BAOSTOCK_PRIORITY",
    "COINGECKO_API_BASE",
    "COINGECKO_API_KEY",
    "COINGECKO_API_PLAN",
    "CRYPTO_COINGECKO_PRIORITY",
    "CRYPTO_PROVIDER_ENABLED",
    "DATABASE_PATH",
    "DATA_VALIDATION_ENABLED",
    "DATA_VALIDATION_INSTRUMENT_OVERRIDES",
    "DATA_VALIDATION_STRICT",
    "DATA_VALIDATION_STRICT_SCOPES",
    "DATA_VALIDATION_UPPER_LAYER_MODE",
    "DECISION_MEMORY_ENABLED",
    "DECISION_MEMORY_LOOKBACK",
    "DECISION_MEMORY_MIN_AGE_DAYS",
    "DECISION_MEMORY_MIN_SAMPLES",
    "DISCORD_CHANNEL_ID",
    "DISCORD_MAX_WORDS",
    "DSA_WEB_DEV_API_PROXY",
    "EFINANCE_CALL_TIMEOUT",
    "EFINANCE_PRIORITY",
    "EMAIL_GROUP_1",
    "EMAIL_GROUP_2",
    "ENABLE_EASTMONEY_PATCH",
    "FEISHU_MAX_BYTES",
    "FEISHU_SEND_AS_FILE",
    "FINNHUB_API_KEY",
    "INDUSTRY_PROVIDER",
    "INDUSTRY_PROVIDER_MAX_BOARDS",
    "LITELLM_LOG_LEVEL",
    "LLM_AIHUBMIX_API_KEY",
    "LLM_AIHUBMIX_BASE_URL",
    "LLM_AIHUBMIX_MODELS",
    "LLM_AIHUBMIX_PROTOCOL",
    "LLM_AIHUBMIX_PROVIDER",
    "LLM_ANSPIRE_API_KEY",
    "LLM_ANSPIRE_BASE_URL",
    "LLM_ANSPIRE_MODELS",
    "LLM_ANSPIRE_PROTOCOL",
    "LLM_ANSPIRE_PROVIDER",
    "LLM_ANTHROPIC_API_KEY",
    "LLM_ANTHROPIC_MODELS",
    "LLM_ANTHROPIC_PROTOCOL",
    "LLM_ANTHROPIC_PROVIDER",
    "LLM_DASHSCOPE_API_KEY",
    "LLM_DASHSCOPE_BASE_URL",
    "LLM_DASHSCOPE_MODELS",
    "LLM_DASHSCOPE_PROTOCOL",
    "LLM_DASHSCOPE_PROVIDER",
    "LLM_DEEPSEEK_API_KEY",
    "LLM_DEEPSEEK_BASE_URL",
    "LLM_DEEPSEEK_MODELS",
    "LLM_DEEPSEEK_PROTOCOL",
    "LLM_DEEPSEEK_PROVIDER",
    "LLM_GEMINI_API_KEY",
    "LLM_GEMINI_API_KEYS",
    "LLM_GEMINI_MODELS",
    "LLM_GEMINI_PROTOCOL",
    "LLM_GEMINI_PROVIDER",
    "LLM_HERMES_API_KEY",
    "LLM_HERMES_BASE_URL",
    "LLM_HERMES_MODELS",
    "LLM_HERMES_PROTOCOL",
    "LLM_HERMES_PROVIDER",
    "LLM_MIMO_API_KEY",
    "LLM_MIMO_BASE_URL",
    "LLM_MIMO_MODELS",
    "LLM_MIMO_PROTOCOL",
    "LLM_MIMO_PROVIDER",
    "LLM_MINIMAX_API_KEY",
    "LLM_MINIMAX_BASE_URL",
    "LLM_MINIMAX_MODELS",
    "LLM_MINIMAX_PROTOCOL",
    "LLM_MINIMAX_PROVIDER",
    "LLM_MOONSHOT_API_KEY",
    "LLM_MOONSHOT_BASE_URL",
    "LLM_MOONSHOT_MODELS",
    "LLM_MOONSHOT_PROTOCOL",
    "LLM_MOONSHOT_PROVIDER",
    "LLM_MY_PROXY_API_KEY",
    "LLM_MY_PROXY_BASE_URL",
    "LLM_MY_PROXY_MODELS",
    "LLM_MY_PROXY_PROTOCOL",
    "LLM_MY_PROXY_PROVIDER",
    "LLM_OLLAMA_BASE_URL",
    "LLM_OLLAMA_MODELS",
    "LLM_OLLAMA_PROVIDER",
    "LLM_OPENAI_API_KEY",
    "LLM_OPENAI_BASE_URL",
    "LLM_OPENAI_MODELS",
    "LLM_OPENAI_PROTOCOL",
    "LLM_OPENAI_PROVIDER",
    "LLM_OPENROUTER_API_KEY",
    "LLM_OPENROUTER_BASE_URL",
    "LLM_OPENROUTER_MODELS",
    "LLM_OPENROUTER_PROTOCOL",
    "LLM_OPENROUTER_PROVIDER",
    "LLM_SILICONFLOW_API_KEY",
    "LLM_SILICONFLOW_BASE_URL",
    "LLM_SILICONFLOW_MODELS",
    "LLM_SILICONFLOW_PROTOCOL",
    "LLM_SILICONFLOW_PROVIDER",
    "LLM_VOLCENGINE_API_KEY",
    "LLM_VOLCENGINE_BASE_URL",
    "LLM_VOLCENGINE_MODELS",
    "LLM_VOLCENGINE_PROTOCOL",
    "LLM_VOLCENGINE_PROVIDER",
    "LLM_ZHIPU_API_KEY",
    "LLM_ZHIPU_BASE_URL",
    "LLM_ZHIPU_MODELS",
    "LLM_ZHIPU_PROTOCOL",
    "LLM_ZHIPU_PROVIDER",
    "LONGBRIDGE_ACCESS_TOKEN",
    "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET",
    "LONGBRIDGE_CONNECTION_COOLDOWN_SECONDS",
    "LONGBRIDGE_ENABLE_OVERNIGHT",
    "LONGBRIDGE_HTTP_URL",
    "LONGBRIDGE_OAUTH_CLIENT_ID",
    "LONGBRIDGE_OAUTH_TOKEN_CACHE_B64",
    "LONGBRIDGE_PRINT_QUOTE_PACKAGES",
    "LONGBRIDGE_PRIORITY",
    "LONGBRIDGE_PUSH_CANDLESTICK_MODE",
    "LONGBRIDGE_QUOTE_WS_URL",
    "LONGBRIDGE_REGION",
    "LONGBRIDGE_STATIC_INFO_TTL_SECONDS",
    "LONGBRIDGE_TRADE_WS_URL",
    "MARKDOWN_TO_IMAGE_CHANNELS",
    "MARKDOWN_TO_IMAGE_MAX_CHARS",
    "MCP_ANALYSIS_MAX_STOCKS",
    "MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE",
    "MCP_HTTP_ALLOWED_HOSTS",
    "MCP_HTTP_ALLOWED_ORIGINS",
    "MCP_HTTP_BACKLOG",
    "MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS",
    "MCP_HTTP_MAX_BODY_BYTES",
    "MCP_HTTP_MAX_CONNECTIONS",
    "MCP_HTTP_MAX_HEADER_BYTES",
    "MCP_HTTP_READ_TIMEOUT_SECONDS",
    "MCP_HTTP_RESOURCE",
    "MCP_HTTP_SCOPES",
    "MCP_HTTP_SESSION_TOKEN_SHA256",
    "MCP_MAX_CONCURRENT_TOOLS",
    "MCP_RATE_LIMIT_PER_MINUTE",
    "MCP_SERVER_ENABLED",
    "MCP_SERVER_HOST",
    "MCP_SERVER_PORT",
    "MCP_SERVER_TRANSPORT",
    "MCP_STDIO_PRINCIPAL",
    "MCP_STDIO_SCOPES",
    "MD2IMG_ENGINE",
    "OLLAMA_API_BASE",
    "PLUGINS_DIR",
    "PLUGIN_STATE_PATH",
    "PREFETCH_REALTIME_QUOTES",
    "PROVIDER_ADAPTIVE_PRIORITY_ENABLED",
    "PROVIDER_ADAPTIVE_PRIORITY_MIN_SAMPLES",
    "PROVIDER_CIRCUIT_BREAKER_ENABLED",
    "PROVIDER_CIRCUIT_COOLDOWN_SECONDS",
    "PROVIDER_CIRCUIT_FAILURE_THRESHOLD",
    "PROVIDER_DAILY_CACHE_DIR",
    "PROVIDER_DAILY_CACHE_ENABLED",
    "PROVIDER_DAILY_CACHE_LOCAL_ONLY_MAX_AGE_SECONDS",
    "PROVIDER_DAILY_CACHE_MEMORY_MAX_ENTRIES",
    "PROVIDER_DAILY_CACHE_MEMORY_TTL_SECONDS",
    "PROVIDER_DAILY_CACHE_PERSISTENT_MAX_AGE_SECONDS",
    "PROVIDER_DAILY_CACHE_PERSISTENT_MAX_ENTRIES",
    "PROVIDER_DAILY_CACHE_PERSISTENT_TTL_SECONDS",
    "PROVIDER_DAILY_CACHE_ROLLOVER_GRACE_DAYS",
    "PROVIDER_DAILY_CACHE_STALE_IF_ERROR_SECONDS",
    "PROVIDER_HEALTH_WINDOW_SIZE",
    "PROVIDER_MARKET_DATA_MODE",
    "PYTDX_PRIORITY",
    "REPORT_MODE",
    "SHARE_IMAGE_XIAOHONGSHU_HANDLE",
    "SHARE_IMAGE_XIAOHONGSHU_ID",
    "SHARE_IMAGE_XIAOHONGSHU_QR_PATH",
    "SHARE_IMAGE_XIAOHONGSHU_URL",
    "SNAPSHOT_SOURCE_PRIORITY",
    "SOCIAL_SENTIMENT_API_KEY",
    "SOCIAL_SENTIMENT_API_URL",
    "SQLITE_BUSY_TIMEOUT_MS",
    "SQLITE_WAL_ENABLED",
    "SQLITE_WRITE_RETRY_BASE_DELAY",
    "SQLITE_WRITE_RETRY_MAX",
    "STOCK_GROUP_1",
    "STOCK_GROUP_2",
    "TUSHARE_PRIORITY",
    "WECHAT_MAX_BYTES",
    "YFINANCE_PRIORITY",
})

# sha256("\n".join(sorted(BASELINE))).hexdigest() — pin membership; only shrink
# BASELINE (and recompute this digest) when retiring historical entries.
TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE_SHA256 = (
    "4a2bda1521cd588184240f1d7cbf33d3cd1f1dfc4da7a3e7134fd80bb436ac6f"
)

# Absolute ceiling introduced with this guard. Never increase.
TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_HARD_CEILING = 243

# Recorded max for current debt length. Only decrease when debt is retired.
TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_MAX_COUNT = 212


def _documented_env_example_keys() -> set[str]:
    return {
        match.group(1)
        for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        for match in [_DOCUMENTED_ENV_ASSIGNMENT_RE.match(line)]
        if match
    }


def _baseline_membership_sha256(baseline: frozenset[str]) -> str:
    payload = "\n".join(sorted(baseline)).encode()
    return hashlib.sha256(payload).hexdigest()


class TestEnvExampleConfigRegistryGuard(unittest.TestCase):
    """Fail closed when .env.example keys skip registry registration."""

    def test_debt_baseline_membership_is_pinned(self) -> None:
        self.assertEqual(
            _baseline_membership_sha256(
                TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE
            ),
            TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE_SHA256,
            "Debt baseline membership changed without updating the pinned "
            "SHA-256. Expanding the baseline to green CI is forbidden — "
            "register new keys instead. Shrinking requires recomputing the "
            "digest after removing retired keys.",
        )
        self.assertLessEqual(
            len(TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE),
            TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_HARD_CEILING,
            "Baseline size exceeds the hard ceiling introduced with this guard.",
        )
        self.assertLessEqual(
            TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_MAX_COUNT,
            TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_HARD_CEILING,
            "MAX_COUNT must never exceed HARD_CEILING (do not raise the ceiling).",
        )
        self.assertGreaterEqual(
            TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_MAX_COUNT,
            0,
        )

    def test_every_documented_env_example_key_is_registered_or_in_baseline(
        self,
    ) -> None:
        documented = _documented_env_example_keys()
        registered = set(get_registered_field_keys())
        unregistered = documented - registered

        unexpected = sorted(
            unregistered - TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE
        )
        self.assertEqual(
            unexpected,
            [],
            "New .env.example keys are missing from the config registry and "
            "are not in the historical debt baseline. Register them in "
            "src/core/config_registry_parts/ (do not expand the baseline or "
            f"rewrite its SHA-256): {unexpected}",
        )
        self.assertLessEqual(
            len(unregistered),
            TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_MAX_COUNT,
            "Unregistered documented key count grew past the recorded max. "
            "Register the new keys; do not raise MAX_COUNT to green CI.",
        )
        self.assertLessEqual(
            len(unregistered),
            TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_HARD_CEILING,
        )
        # Live debt stays within the historical membership ceiling.
        self.assertTrue(
            unregistered <= TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_BASELINE
        )


class TestConfigRegistryTypeInferenceFallback(unittest.TestCase):
    """Inference is a presentation fallback; registration remains required."""

    def test_boolean_named_keys_infer_boolean_without_value_hint(self) -> None:
        samples = (
            "CRYPTO_PROVIDER_ENABLED",
            "MCP_SERVER_ENABLED",
            "DATA_VALIDATION_ENABLED",
            "DATA_VALIDATION_STRICT",
            "ENABLE_FUNDAMENTAL_PIPELINE",
            "SQLITE_WAL_ENABLED",
            "FAILURE_NOTIFY_ENABLED",
        )
        for key in samples:
            with self.subTest(key=key):
                self.assertEqual(_infer_data_type(key, None), "boolean")
                self.assertEqual(_infer_ui_control("boolean", key), "switch")
                field = get_field_definition(key)
                if key not in set(get_registered_field_keys()):
                    self.assertEqual(field["data_type"], "boolean")
                    self.assertEqual(field["ui_control"], "switch")

    def test_boolean_value_hint_with_inline_comment(self) -> None:
        hint = "true          # Global toggle; per-request override via use_memory"
        self.assertEqual(_infer_data_type("DECISION_MEMORY_ENABLED", hint), "boolean")
        self.assertEqual(
            _infer_data_type(
                "PROVIDER_ADAPTIVE_PRIORITY_ENABLED",
                "true # Reorder sufficiently sampled peers",
            ),
            "boolean",
        )
        self.assertEqual(_infer_data_type("SOME_FLAG", "false # off"), "boolean")

    def test_numeric_value_hint_with_inline_comment(self) -> None:
        self.assertEqual(_infer_data_type("SOME_TIMEOUT", "30 # seconds"), "integer")
        self.assertEqual(_infer_data_type("SOME_RATIO", "1.5 # ratio"), "number")

    def test_enum_options_infer_select_control(self) -> None:
        options = [
            {"label": "Brief", "value": "brief"},
            {"label": "Standard", "value": "standard"},
            {"label": "Research", "value": "research"},
        ]
        self.assertEqual(
            _infer_ui_control("string", "REPORT_MODE", options=options),
            "select",
        )
        self.assertEqual(
            _infer_ui_control(
                "string", "MCP_SERVER_TRANSPORT", options=["stdio", "sse"]
            ),
            "select",
        )
        # Without options, enum-named keys stay text — registration owns choices.
        self.assertEqual(
            _infer_ui_control("string", "PROVIDER_MARKET_DATA_MODE"),
            "text",
        )
        self.assertEqual(_infer_data_type("REPORT_MODE", "standard"), "string")

    def test_registered_boolean_fields_unchanged_by_inference_fallback(self) -> None:
        field = get_field_definition("WEBUI_ENABLED")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertNotEqual(field["display_order"], 9000)


if __name__ == "__main__":
    unittest.main()
