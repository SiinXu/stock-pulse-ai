# -*- coding: utf-8 -*-
"""Tests for config_registry field definitions and schema building.

Ensures every notification channel that has a sender implementation also
has its config keys registered in _FIELD_DEFINITIONS so the Web settings
page and /api/v1/system/config/schema can expose them.
"""
import re
import unittest
from pathlib import Path

from src.core.config_registry import (
    SCHEMA_VERSION,
    WEB_SETTINGS_HIDDEN_FROM_UI,
    build_schema_response,
    get_field_definition,
    get_registered_field_keys,
)


class TestSlackFieldsRegistered(unittest.TestCase):
    """Slack config keys must be present in the registry."""

    _SLACK_KEYS = ("SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID", "SLACK_WEBHOOK_URL")

    def test_field_definitions_exist(self):
        for key in self._SLACK_KEYS:
            field = get_field_definition(key)
            self.assertEqual(field["category"], "notification", f"{key} category")
            self.assertNotEqual(
                field["display_order"], 9000,
                f"{key} should be explicitly registered, not inferred",
            )

    def test_bot_token_is_sensitive(self):
        field = get_field_definition("SLACK_BOT_TOKEN")
        self.assertTrue(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "password")

    def test_webhook_url_is_sensitive(self):
        field = get_field_definition("SLACK_WEBHOOK_URL")
        self.assertTrue(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "password")

    def test_channel_id_not_sensitive(self):
        field = get_field_definition("SLACK_CHANNEL_ID")
        self.assertFalse(field["is_sensitive"])

    def test_schema_response_includes_slack(self):
        schema = build_schema_response()
        notification_cat = next(
            (c for c in schema["categories"] if c["category"] == "notification"),
            None,
        )
        self.assertIsNotNone(notification_cat, "notification category missing")
        field_keys = {f["key"] for f in notification_cat["fields"]}
        for key in self._SLACK_KEYS:
            self.assertIn(key, field_keys, f"{key} missing from schema response")

    def test_display_order_between_discord_and_pushover(self):
        discord = get_field_definition("DISCORD_MAIN_CHANNEL_ID")
        pushover = get_field_definition("PUSHOVER_USER_KEY")
        for key in self._SLACK_KEYS:
            order = get_field_definition(key)["display_order"]
            self.assertGreater(order, discord["display_order"],
                               f"{key} should appear after Discord")
            self.assertLess(order, pushover["display_order"],
                            f"{key} should appear before Pushover")


class TestFeishuWebhookFieldsRegistered(unittest.TestCase):
    """Feishu webhook security fields must be registered for the settings UI."""

    _FEISHU_KEYS = (
        "FEISHU_WEBHOOK_URL",
        "FEISHU_WEBHOOK_SECRET",
        "FEISHU_WEBHOOK_KEYWORD",
    )

    def test_field_definitions_exist(self):
        for key in self._FEISHU_KEYS:
            field = get_field_definition(key)
            self.assertEqual(field["category"], "notification", f"{key} category")
            self.assertNotEqual(
                field["display_order"], 9000,
                f"{key} should be explicitly registered, not inferred",
            )

    def test_secret_is_sensitive(self):
        field = get_field_definition("FEISHU_WEBHOOK_SECRET")
        self.assertTrue(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "password")

    def test_keyword_is_not_sensitive(self):
        field = get_field_definition("FEISHU_WEBHOOK_KEYWORD")
        self.assertFalse(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "text")

    def test_webhook_url_uses_url_validation(self):
        field = get_field_definition("FEISHU_WEBHOOK_URL")
        self.assertEqual(field["validation"]["item_type"], "url")
        self.assertIn("https", field["validation"]["allowed_schemes"])

    def test_schema_response_includes_feishu_webhook_fields(self):
        schema = build_schema_response()
        notification_cat = next(
            (c for c in schema["categories"] if c["category"] == "notification"),
            None,
        )
        self.assertIsNotNone(notification_cat, "notification category missing")
        field_keys = {f["key"] for f in notification_cat["fields"]}
        for key in self._FEISHU_KEYS:
            self.assertIn(key, field_keys, f"{key} missing from schema response")


class TestAstrBotFieldsRegistered(unittest.TestCase):
    """AstrBot config keys must be explicitly registered for settings UI."""

    _ASTRBOT_KEYS = ("ASTRBOT_URL", "ASTRBOT_TOKEN")

    def test_field_definitions_exist(self):
        for key in self._ASTRBOT_KEYS:
            field = get_field_definition(key)
            self.assertEqual(field["category"], "notification", f"{key} category")
            self.assertNotEqual(
                field["display_order"], 9000,
                f"{key} should be explicitly registered, not inferred",
            )

    def test_url_and_token_are_sensitive_password_controls(self):
        for key in self._ASTRBOT_KEYS:
            field = get_field_definition(key)
            self.assertTrue(field["is_sensitive"], f"{key} should be sensitive")
            self.assertEqual(field["ui_control"], "password")

    def test_url_uses_url_validation(self):
        field = get_field_definition("ASTRBOT_URL")
        self.assertEqual(field["validation"]["item_type"], "url")
        self.assertIn("https", field["validation"]["allowed_schemes"])

    def test_schema_response_includes_astrbot_fields(self):
        schema = build_schema_response()
        notification_cat = next(
            (c for c in schema["categories"] if c["category"] == "notification"),
            None,
        )
        self.assertIsNotNone(notification_cat, "notification category missing")
        field_keys = {f["key"] for f in notification_cat["fields"]}
        for key in self._ASTRBOT_KEYS:
            self.assertIn(key, field_keys, f"{key} missing from schema response")


class TestAlphaSiftFieldsRegistered(unittest.TestCase):
    def test_install_spec_is_sensitive(self):
        field = get_field_definition("ALPHASIFT_INSTALL_SPEC")

        self.assertTrue(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "password")
        self.assertIn("StockPulse", field["description"])
        self.assertNotIn("DSA's", field["description"])


class TestLLMUsageHMACFieldsRegistered(unittest.TestCase):
    def test_secret_is_sensitive_password_field(self):
        field = get_field_definition("LLM_USAGE_HMAC_SECRET")

        self.assertEqual(field["category"], "ai_model")
        self.assertTrue(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "password")
        self.assertEqual(field["help_key"], "settings.ai_model.LLM_USAGE_HMAC_SECRET")
        self.assertIn("high-entropy", field["description"])
        self.assertIn("version control", field["description"])
        self.assertIn("openssl rand -hex 32", field["examples"][0])
        self.assertIn("secret_value", field.get("warning_codes", []))

    def test_key_version_is_visible_non_sensitive_field(self):
        field = get_field_definition("LLM_USAGE_HMAC_KEY_VERSION")

        self.assertEqual(field["category"], "ai_model")
        self.assertFalse(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "text")
        self.assertEqual(field["default_value"], "local-v1")
        self.assertEqual(field["help_key"], "settings.ai_model.LLM_USAGE_HMAC_KEY_VERSION")


class TestGenerationBackendFieldsRegistered(unittest.TestCase):
    def test_analysis_backend_fields_are_ai_model_selects(self):
        expected = {
            "GENERATION_BACKEND": "settings.ai_model.GENERATION_BACKEND",
            "GENERATION_FALLBACK_BACKEND": "settings.ai_model.GENERATION_FALLBACK_BACKEND",
        }
        for key, help_key in expected.items():
            field = get_field_definition(key)
            self.assertEqual(field["category"], "ai_model")
            self.assertEqual(field["ui_control"], "select")
            self.assertEqual(field["default_value"], "litellm")
            if key == "GENERATION_BACKEND":
                self.assertEqual(
                    field["validation"],
                    {"enum": ["litellm", "codex_cli", "claude_code_cli", "opencode_cli"]},
                )
                self.assertIn({"label": "Default model settings", "value": "litellm"}, field["options"])
                self.assertIn({"label": "Codex CLI (experimental)", "value": "codex_cli"}, field["options"])
                self.assertIn({"label": "Claude Code CLI (experimental)", "value": "claude_code_cli"}, field["options"])
                self.assertIn({"label": "OpenCode CLI (experimental)", "value": "opencode_cli"}, field["options"])
            else:
                self.assertEqual(field["validation"], {"enum": ["", "litellm"]})
                self.assertIn({"label": "Disabled", "value": ""}, field["options"])
                self.assertIn({"label": "Default model settings", "value": "litellm"}, field["options"])
            self.assertEqual(field["help_key"], help_key)
            self.assertNotEqual(field["display_order"], 9000)

    def test_agent_generation_backend_field_is_agent_select(self):
        field = get_field_definition("AGENT_GENERATION_BACKEND")

        self.assertEqual(field["category"], "agent")
        self.assertEqual(field["ui_control"], "select")
        self.assertEqual(field["default_value"], "auto")
        self.assertEqual(field["validation"], {"enum": ["auto", "litellm"]})
        self.assertEqual(
            field["options"],
            [
                {"label": "Auto", "value": "auto"},
                {"label": "Default model settings", "value": "litellm"},
            ],
        )
        self.assertEqual(field["help_key"], "settings.agent.AGENT_GENERATION_BACKEND")
        self.assertNotEqual(field["display_order"], 9000)

    def test_generation_backend_numeric_fields_have_upper_bounds(self):
        expected = {
            "GENERATION_BACKEND_TIMEOUT_SECONDS": {"min": 1, "max": 3600},
            "GENERATION_BACKEND_MAX_OUTPUT_BYTES": {"min": 1, "max": 33554432},
            "GENERATION_BACKEND_MAX_CONCURRENCY": {"min": 1, "max": 16},
            "LOCAL_CLI_BACKEND_MAX_CONCURRENCY": {"min": 1, "max": 4},
        }

        for key, validation in expected.items():
            self.assertEqual(get_field_definition(key)["validation"], validation)

    def test_schema_response_groups_generation_backend_fields(self):
        schema = build_schema_response()
        self.assertEqual(schema["schema_version"], SCHEMA_VERSION)
        self.assertEqual(SCHEMA_VERSION, "2026-07-16-config-contract")

        categories = {
            category["category"]: {field["key"] for field in category["fields"]}
            for category in schema["categories"]
        }

        self.assertIn("GENERATION_BACKEND", categories["ai_model"])
        self.assertIn("GENERATION_FALLBACK_BACKEND", categories["ai_model"])
        self.assertIn("GENERATION_BACKEND_TIMEOUT_SECONDS", categories["ai_model"])
        self.assertIn("GENERATION_BACKEND_MAX_OUTPUT_BYTES", categories["ai_model"])
        self.assertIn("GENERATION_BACKEND_MAX_CONCURRENCY", categories["ai_model"])
        self.assertIn("LOCAL_CLI_BACKEND_MAX_CONCURRENCY", categories["ai_model"])
        self.assertIn("AGENT_GENERATION_BACKEND", categories["agent"])


class TestScheduleTimesFieldRegistered(unittest.TestCase):
    def test_schedule_times_pattern_accepts_documented_empty_fallback(self):
        field = get_field_definition("SCHEDULE_TIMES")
        pattern = re.compile(field["validation"]["pattern"])

        self.assertIsNotNone(pattern.fullmatch(""))
        self.assertIsNotNone(pattern.fullmatch("   "))
        self.assertIsNotNone(pattern.fullmatch("09:20,12:30,15:10"))
        self.assertIsNone(pattern.fullmatch("09:20,"))
        self.assertIsNone(pattern.fullmatch("25:70"))


class TestLLMPromptCacheFieldsRegistered(unittest.TestCase):
    def test_prompt_cache_telemetry_default_enabled(self):
        field = get_field_definition("LLM_PROMPT_CACHE_TELEMETRY_ENABLED")

        self.assertEqual(field["category"], "ai_model")
        self.assertEqual(field["ui_control"], "switch")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["default_value"], "true")
        self.assertEqual(field["help_key"], "settings.ai_model.LLM_PROMPT_CACHE_TELEMETRY_ENABLED")

    def test_prompt_cache_hints_default_disabled(self):
        field = get_field_definition("LLM_PROMPT_CACHE_HINTS_ENABLED")

        self.assertEqual(field["category"], "ai_model")
        self.assertEqual(field["ui_control"], "switch")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["default_value"], "false")
        self.assertEqual(field["help_key"], "settings.ai_model.LLM_PROMPT_CACHE_HINTS_ENABLED")

    def test_prompt_cache_diagnostics_is_select(self):
        field = get_field_definition("LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL")

        self.assertEqual(field["category"], "ai_model")
        self.assertEqual(field["ui_control"], "select")
        self.assertEqual(field["default_value"], "off")
        self.assertEqual(
            [option["value"] for option in field["options"]],
            ["off", "basic", "debug"],
        )
        self.assertEqual(field["validation"], {"enum": ["off", "basic", "debug"]})
        self.assertEqual(field["help_key"], "settings.ai_model.LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL")


class TestSettingsHelpMetadata(unittest.TestCase):
    """Field help metadata should be available for covered settings help slices."""

    _AI_MODEL_HIDDEN_KEYS = {
        "LLM_CHANNELS",
        "LLM_TEMPERATURE",
        "LITELLM_MODEL",
        "AGENT_LITELLM_MODEL",
        "LITELLM_FALLBACK_MODELS",
        "AIHUBMIX_KEY",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_KEYS",
        "GEMINI_API_KEY",
        "GEMINI_API_KEYS",
        "GEMINI_MODEL",
        "GEMINI_MODEL_FALLBACK",
        "GEMINI_TEMPERATURE",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEYS",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_TEMPERATURE",
        "ANTHROPIC_MAX_TOKENS",
        "OPENAI_API_KEY",
        "OPENAI_API_KEYS",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_VISION_MODEL",
        "OPENAI_TEMPERATURE",
        "VISION_MODEL",
    }
    _SYSTEM_HIDDEN_KEYS = {
        "ADMIN_AUTH_ENABLED",
    }

    _HELP_KEYS = (
        "STOCK_LIST",
        "GENERATION_BACKEND",
        "GENERATION_FALLBACK_BACKEND",
        "LITELLM_MODEL",
        "LLM_CHANNELS",
        "FEISHU_WEBHOOK_URL",
        "WEBUI_HOST",
        "AGENT_GENERATION_BACKEND",
        "AGENT_LITELLM_MODEL",
        "LITELLM_FALLBACK_MODELS",
        "TUSHARE_TOKEN",
        "REALTIME_SOURCE_PRIORITY",
        "TAVILY_API_KEYS",
        "NEWS_STRATEGY_PROFILE",
        "WECHAT_WEBHOOK_URL",
        "EMAIL_RECEIVERS",
        "SCHEDULE_TIME",
        "ADMIN_AUTH_ENABLED",
        # PR3 Phase 1: Agent + Event Alert
        "AGENT_MODE",
        "AGENT_MAX_STEPS",
        "AGENT_SKILLS",
        "AGENT_SKILL_DIR",
        "AGENT_NL_ROUTING",
        "AGENT_ARCH",
        "AGENT_ORCHESTRATOR_MODE",
        "AGENT_ORCHESTRATOR_TIMEOUT_S",
        "AGENT_RISK_OVERRIDE",
        "AGENT_DEEP_RESEARCH_BUDGET",
        "AGENT_DEEP_RESEARCH_TIMEOUT",
        "AGENT_MEMORY_ENABLED",
        "AGENT_SKILL_AUTOWEIGHT",
        "AGENT_SKILL_ROUTING",
        "AGENT_CONTEXT_COMPRESSION_ENABLED",
        "AGENT_CONTEXT_COMPRESSION_PROFILE",
        "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS",
        "AGENT_CONTEXT_PROTECTED_TURNS",
        "AGENT_EVENT_MONITOR_ENABLED",
        "AGENT_EVENT_MONITOR_INTERVAL_MINUTES",
        "AGENT_EVENT_ALERT_RULES_JSON",
        # PR3 Phase 2: Backtest
        "BACKTEST_ENABLED",
        "BACKTEST_EVAL_WINDOW_DAYS",
        "BACKTEST_MIN_AGE_DAYS",
        "BACKTEST_ENGINE_VERSION",
        "BACKTEST_NEUTRAL_BAND_PCT",
        # PR3 Phase 3: Report + Notification Route
        "REPORT_SUMMARY_ONLY",
        "REPORT_SHOW_LLM_MODEL",
        "REPORT_TEMPLATES_DIR",
        "REPORT_RENDERER_ENABLED",
        "REPORT_INTEGRITY_ENABLED",
        "REPORT_INTEGRITY_RETRY",
        "REPORT_HISTORY_COMPARE_N",
        "SINGLE_STOCK_NOTIFY",
        "MERGE_EMAIL_NOTIFICATION",
        "NOTIFICATION_REPORT_CHANNELS",
        "NOTIFICATION_ALERT_CHANNELS",
        "NOTIFICATION_SYSTEM_ERROR_CHANNELS",
        "NOTIFICATION_DEDUP_TTL_SECONDS",
        "NOTIFICATION_COOLDOWN_SECONDS",
        "NOTIFICATION_QUIET_HOURS",
        "NOTIFICATION_TIMEZONE",
        "NOTIFICATION_MIN_SEVERITY",
        "NOTIFICATION_DAILY_DIGEST_ENABLED",
        # PR3 Phase 4: System Runtime
        "LOG_LEVEL",
        "DEBUG",
        "MAX_WORKERS",
        "ANALYSIS_DELAY",
        "SAVE_CONTEXT_SNAPSHOT",
        "MARKET_REVIEW_ENABLED",
        "DAILY_MARKET_CONTEXT_ENABLED",
        "MARKET_REVIEW_REGION",
        "MARKET_REVIEW_COLOR_SCHEME",
        # Issue #1512: stream, log, and WebUI startup fields
        "DINGTALK_STREAM_ENABLED",
        "FEISHU_STREAM_ENABLED",
        "LOG_DIR",
        "WEBUI_ENABLED",
        "WEBUI_AUTO_BUILD",
    )

    def test_representative_fields_have_help_metadata(self):
        for key in self._HELP_KEYS:
            field = get_field_definition(key)
            self.assertTrue(field.get("help_key"), f"{key} missing help_key")
            self.assertTrue(field.get("examples"), f"{key} missing examples")
            self.assertTrue(field.get("docs"), f"{key} missing docs")

    def test_web_settings_visible_fields_have_help_metadata(self):
        """Every field rendered by SettingsField must have Help metadata."""

        missing = []
        for key in get_registered_field_keys():
            field = get_field_definition(key)
            if key in self._SYSTEM_HIDDEN_KEYS:
                continue
            if field.get("category") == "ai_model" and key in self._AI_MODEL_HIDDEN_KEYS:
                # These legacy fields are hidden only when channel config is active;
                # they are still visible/configurable in legacy setups.
                pass

            if not field.get("help_key") or not field.get("examples") or not field.get("docs"):
                missing.append(key)

        self.assertEqual([], missing)

    def test_webui_host_is_explicitly_registered(self):
        field = get_field_definition("WEBUI_HOST")
        self.assertEqual(field["category"], "system")
        self.assertNotEqual(field["display_order"], 9000)

    def test_save_context_snapshot_is_explicitly_registered(self):
        field = get_field_definition("SAVE_CONTEXT_SNAPSHOT")

        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertFalse(field["is_sensitive"])
        self.assertTrue(field["is_editable"])
        self.assertEqual(field["default_value"], "true")
        self.assertEqual(field["display_order"], 52)
        self.assertEqual(field["help_key"], "settings.system.SAVE_CONTEXT_SNAPSHOT")
        self.assertTrue(field.get("examples"))
        self.assertTrue(field.get("docs"))
        self.assertIn("analysis-context-pack.md#p6-", field["docs"][0]["href"])

    def test_restart_warning_codes_match_runtime_behavior(self):
        restart_required_keys = (
            "RUN_IMMEDIATELY",
            "SCHEDULE_ENABLED",
            "SCHEDULE_RUN_IMMEDIATELY",
            "WEBUI_HOST",
            "WEBUI_PORT",
            "WEBUI_ENABLED",
            "WEBUI_AUTO_BUILD",
            "LOG_DIR",
            "DINGTALK_STREAM_ENABLED",
            "FEISHU_STREAM_ENABLED",
            "LOG_LEVEL",
        )
        for key in restart_required_keys:
            field = get_field_definition(key)
            self.assertIn("restart_required", field.get("warning_codes", []))

        schedule_time = get_field_definition("SCHEDULE_TIME")
        self.assertNotIn("restart_required", schedule_time.get("warning_codes", []))

    def test_schema_response_includes_help_metadata(self):
        schema = build_schema_response()
        fields = {
            field["key"]: field
            for category in schema["categories"]
            for field in category["fields"]
        }

        self.assertEqual(fields["STOCK_LIST"]["help_key"], "settings.base.STOCK_LIST")
        self.assertIn("docs/full-guide.md", fields["STOCK_LIST"]["docs"][0]["href"])

    def test_help_links_target_the_stockpulse_repository(self):
        upstream_repository = "github.com/ZhuLinsen/daily_stock_analysis"
        for key in get_registered_field_keys():
            for doc in get_field_definition(key).get("docs", []):
                self.assertNotIn(upstream_repository, doc.get("href", ""), key)

    def test_admin_auth_help_is_read_only_in_generic_settings(self):
        field = get_field_definition("ADMIN_AUTH_ENABLED")
        self.assertFalse(field["is_editable"])
        self.assertIn("auth_settings_endpoint_required", field.get("warning_codes", []))


class TestIssue1512SettingsFields(unittest.TestCase):
    """Issue #1512 visible fields must be explicitly registered."""

    def test_stream_fields_are_registered_as_notification_switches(self) -> None:
        expected = {
            "FEISHU_STREAM_ENABLED": 17,
            "DINGTALK_STREAM_ENABLED": 35,
        }
        for key, display_order in expected.items():
            field = get_field_definition(key)
            self.assertEqual(field["category"], "notification")
            self.assertEqual(field["data_type"], "boolean")
            self.assertEqual(field["ui_control"], "switch")
            self.assertEqual(field["default_value"], "false")
            self.assertEqual(field["display_order"], display_order)
            self.assertTrue(field.get("help_key"))
            self.assertTrue(field.get("examples"))
            self.assertTrue(field.get("docs"))
            self.assertIn("not_webhook_delivery", field.get("warning_codes", []))
            self.assertIn("restart_required", field.get("warning_codes", []))

    def test_system_runtime_fields_are_registered_with_restart_boundary(self) -> None:
        expected = {
            "LOG_DIR": ("string", "text", "./logs", 31),
            "WEBUI_ENABLED": ("boolean", "switch", "false", 37),
            "WEBUI_AUTO_BUILD": ("boolean", "switch", "true", 38),
        }
        for key, (data_type, ui_control, default_value, display_order) in expected.items():
            field = get_field_definition(key)
            self.assertEqual(field["category"], "system")
            self.assertEqual(field["data_type"], data_type)
            self.assertEqual(field["ui_control"], ui_control)
            self.assertEqual(field["default_value"], default_value)
            self.assertEqual(field["display_order"], display_order)
            self.assertTrue(field.get("help_key"))
            self.assertTrue(field.get("examples"))
            self.assertTrue(field.get("docs"))
            self.assertIn("restart_required", field.get("warning_codes", []))


class TestEnvExampleWebSettingsCoverage(unittest.TestCase):
    """Active .env.example keys must be registered or intentionally hidden."""

    _ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
    _ACTIVE_ENV_ASSIGNMENT_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=")

    def test_active_env_example_keys_are_registered_or_hidden_from_web_ui(self) -> None:
        active_keys = {
            match.group(1)
            for line in self._ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
            for match in [self._ACTIVE_ENV_ASSIGNMENT_RE.match(line.strip())]
            if match
        }
        registered_keys = set(get_registered_field_keys())

        self.assertEqual(
            sorted(active_keys - registered_keys - WEB_SETTINGS_HIDDEN_FROM_UI),
            [],
        )


class TestSettingsFieldTitleContract(unittest.TestCase):
    """The Web field-title catalog must cover the backend registry exactly."""

    _FIELD_TITLE_FILE = (
        Path(__file__).resolve().parents[1]
        / "apps/dsa-web/src/utils/systemConfigI18n.ts"
    )
    _FIELD_TITLE_MAP_RE = re.compile(
        r"const fieldTitleMapZh = \{\n(?P<body>.*?)\n\} as const;",
        flags=re.DOTALL,
    )
    _FIELD_TITLE_EN_MAP_RE = re.compile(
        r"const fieldTitleMapEn = \{\n(?P<body>.*?)\n\} satisfies",
        flags=re.DOTALL,
    )
    _FIELD_TITLE_KEY_RE = re.compile(
        r"^\s{2}([A-Z][A-Z0-9_]*)\s*:",
        flags=re.MULTILINE,
    )
    _FIELD_TITLE_EN_ENTRY_RE = re.compile(
        r"^\s{2}([A-Z][A-Z0-9_]*)\s*:\s*'([^']*)',$",
        flags=re.MULTILINE,
    )

    @classmethod
    def _collect_web_field_title_keys(cls) -> set[str]:
        content = cls._FIELD_TITLE_FILE.read_text(encoding="utf-8")
        match = cls._FIELD_TITLE_MAP_RE.search(content)
        if match is None:
            raise AssertionError("Unable to locate fieldTitleMapZh in systemConfigI18n.ts")
        keys = cls._FIELD_TITLE_KEY_RE.findall(match.group("body"))
        if len(keys) != len(set(keys)):
            raise AssertionError("fieldTitleMapZh contains duplicate field keys")
        return set(keys)

    @classmethod
    def _collect_web_english_field_titles(cls) -> dict[str, str]:
        content = cls._FIELD_TITLE_FILE.read_text(encoding="utf-8")
        match = cls._FIELD_TITLE_EN_MAP_RE.search(content)
        if match is None:
            raise AssertionError("Unable to locate fieldTitleMapEn in systemConfigI18n.ts")
        entries = cls._FIELD_TITLE_EN_ENTRY_RE.findall(match.group("body"))
        titles = dict(entries)
        if len(entries) != len(titles):
            raise AssertionError("fieldTitleMapEn contains duplicate field keys")
        return titles

    def test_web_field_titles_match_registered_fields(self) -> None:
        registered_keys = set(get_registered_field_keys())
        field_title_keys = self._collect_web_field_title_keys()

        self.assertEqual(
            (
                sorted(registered_keys - field_title_keys),
                sorted(field_title_keys - registered_keys),
            ),
            ([], []),
            "Web field-title catalog differs from the backend registry "
            "(missing titles, stale titles)",
        )

    def test_web_english_field_titles_match_backend_schema_titles(self) -> None:
        web_titles = self._collect_web_english_field_titles()
        backend_titles = {
            key: get_field_definition(key)["title"]
            for key in get_registered_field_keys()
        }

        self.assertEqual(
            web_titles,
            backend_titles,
            "The English translation inventory must mirror backend schema titles",
        )


class TestSettingsHelpContract(unittest.TestCase):
    """Help keys must map to registry metadata or be editor-only.

    The LLM Channel editor uses internal field-level keys prefixed with
    ``settings.llm_channel.``. Those keys are valid for UI only and should not be
    expected in the backend registry.
    """

    _LLM_CHANNEL_HELP_PREFIX = "settings.llm_channel."
    _SETTINGS_HELP_FILE = Path(__file__).resolve().parents[1] / "apps/dsa-web/src/locales/settingsHelp.ts"

    @classmethod
    def _collect_registry_help_keys(cls) -> set[str]:
        keys = set()
        for key in get_registered_field_keys():
            definition = get_field_definition(key)
            help_key = definition.get("help_key")
            if help_key:
                keys.add(help_key)
        return keys

    @classmethod
    def _collect_locale_help_keys(cls) -> set[str]:
        content = cls._SETTINGS_HELP_FILE.read_text(encoding="utf-8")
        return set(re.findall(r"^\s*'([^']+)'\s*:\s*\{", content, flags=re.MULTILINE))

    def test_registry_help_keys_exist_in_locales(self) -> None:
        locale_keys = self._collect_locale_help_keys()
        registry_help_keys = self._collect_registry_help_keys()
        missing = sorted(registry_help_keys - locale_keys)
        self.assertEqual(missing, [], f"Registry help keys missing locale: {missing}")

    def test_locale_help_keys_are_registry_or_llm_channel_internal(self) -> None:
        registry_help_keys = self._collect_registry_help_keys()
        locale_keys = self._collect_locale_help_keys()
        external_keys = sorted(
            key
            for key in locale_keys
            if key not in registry_help_keys and not key.startswith(self._LLM_CHANNEL_HELP_PREFIX)
        )
        self.assertEqual(external_keys, [], f"Unexpected locale-only help keys: {external_keys}")


class TestSensitiveFieldsUsePasswordControl(unittest.TestCase):
    """Every is_sensitive field must use ui_control='password' to avoid
    leaking secrets in the Web settings page."""

    def test_all_sensitive_fields_use_password(self):
        schema = build_schema_response()
        violations = []
        for cat in schema["categories"]:
            for field in cat["fields"]:
                if field.get("is_sensitive") and field.get("ui_control") != "password":
                    violations.append(field["key"])
        self.assertEqual(violations, [],
                         f"Sensitive fields with non-password ui_control: {violations}")


class TestDiscordInteractionPublicKeyField(unittest.TestCase):
    def test_field_definition_exists(self):
        field = get_field_definition("DISCORD_INTERACTIONS_PUBLIC_KEY")
        self.assertEqual(field["category"], "notification")
        self.assertFalse(field["is_sensitive"])
        self.assertEqual(field["ui_control"], "text")

    def test_schema_response_includes_public_key_field(self):
        schema = build_schema_response()
        notification_cat = next(
            (c for c in schema["categories"] if c["category"] == "notification"),
            None,
        )
        self.assertIsNotNone(notification_cat, "notification category missing")
        field_keys = {f["key"] for f in notification_cat["fields"]}
        self.assertIn("DISCORD_INTERACTIONS_PUBLIC_KEY", field_keys)


class TestNotificationRouteFieldsRegistered(unittest.TestCase):
    """P3 notification route keys must be visible and validated in settings schema."""

    _ROUTE_KEYS = (
        "NOTIFICATION_REPORT_CHANNELS",
        "NOTIFICATION_ALERT_CHANNELS",
        "NOTIFICATION_SYSTEM_ERROR_CHANNELS",
    )

    def test_field_definitions_exist(self):
        for key in self._ROUTE_KEYS:
            field = get_field_definition(key)
            self.assertEqual(field["category"], "notification", f"{key} category")
            self.assertEqual(field["data_type"], "array", f"{key} data_type")
            self.assertFalse(field["is_sensitive"], f"{key} should not be sensitive")
            self.assertIn("email", field["validation"]["allowed_values"])

    def test_schema_response_includes_route_fields(self):
        schema = build_schema_response()
        notification_cat = next(
            (c for c in schema["categories"] if c["category"] == "notification"),
            None,
        )
        self.assertIsNotNone(notification_cat, "notification category missing")
        field_keys = {f["key"] for f in notification_cat["fields"]}
        for key in self._ROUTE_KEYS:
            self.assertIn(key, field_keys, f"{key} missing from schema response")


class TestAgentEventAlertRulesJsonField(unittest.TestCase):
    """Event Monitor legacy JSON config must advertise its P8 boundary."""

    def test_description_marks_legacy_and_web_api_boundaries(self):
        field = get_field_definition("AGENT_EVENT_ALERT_RULES_JSON")
        description = field["description"]

        self.assertIn("Legacy JSON supports only price_cross, price_change_percent, and volume_spike", description)
        self.assertIn("Technical indicator", description)
        self.assertIn("watchlist", description)
        self.assertIn("portfolio", description)
        self.assertIn("market light", description)
        self.assertIn("Alert API/Web center", description)


class TestAgentContextCompressionFields(unittest.TestCase):
    """Visible chat context compression config must be exposed consistently."""

    def test_profile_uses_chinese_labels_and_enum(self):
        field = get_field_definition("AGENT_CONTEXT_COMPRESSION_PROFILE")

        self.assertEqual(field["category"], "agent")
        self.assertEqual(field["ui_control"], "select")
        self.assertEqual(
            field["validation"]["enum"],
            ["cost", "balanced", "long_context_raw_first"],
        )
        self.assertEqual(
            [option["label"] for option in field["options"]],
            ["成本优先", "均衡推荐", "长上下文原文优先"],
        )

    def test_trigger_and_protected_turns_can_follow_profile_preset(self):
        trigger = get_field_definition("AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS")
        protected = get_field_definition("AGENT_CONTEXT_PROTECTED_TURNS")

        self.assertEqual(trigger["default_value"], "")
        self.assertEqual(protected["default_value"], "")
        self.assertFalse(trigger["is_required"])
        self.assertFalse(protected["is_required"])
        self.assertIn("Leave empty", trigger["description"])
        self.assertIn("Leave empty", protected["description"])


class TestNotificationNoiseFieldsRegistered(unittest.TestCase):
    """P4 notification noise-control keys must be visible in settings schema."""

    _NOISE_KEYS = (
        "NOTIFICATION_DEDUP_TTL_SECONDS",
        "NOTIFICATION_COOLDOWN_SECONDS",
        "NOTIFICATION_QUIET_HOURS",
        "NOTIFICATION_TIMEZONE",
        "NOTIFICATION_MIN_SEVERITY",
        "NOTIFICATION_DAILY_DIGEST_ENABLED",
    )

    def test_field_definitions_exist(self):
        for key in self._NOISE_KEYS:
            field = get_field_definition(key)
            self.assertEqual(field["category"], "notification", f"{key} category")
            self.assertFalse(field["is_sensitive"], f"{key} should not be sensitive")
            self.assertFalse(field["is_required"], f"{key} should not be required")

        self.assertEqual(get_field_definition("NOTIFICATION_DEDUP_TTL_SECONDS")["data_type"], "integer")
        self.assertEqual(get_field_definition("NOTIFICATION_COOLDOWN_SECONDS")["data_type"], "integer")
        self.assertEqual(get_field_definition("NOTIFICATION_DAILY_DIGEST_ENABLED")["data_type"], "boolean")
        min_severity = get_field_definition("NOTIFICATION_MIN_SEVERITY")
        self.assertEqual(min_severity["options"][0]["value"], "")
        self.assertIn("", min_severity["validation"]["enum"])
        self.assertIn("warning", min_severity["validation"]["enum"])

    def test_schema_response_includes_noise_fields(self):
        schema = build_schema_response()
        notification_cat = next(
            (c for c in schema["categories"] if c["category"] == "notification"),
            None,
        )
        self.assertIsNotNone(notification_cat, "notification category missing")
        field_keys = {f["key"] for f in notification_cat["fields"]}
        for key in self._NOISE_KEYS:
            self.assertIn(key, field_keys, f"{key} missing from schema response")

class TestReportDisplayFieldsRegistered(unittest.TestCase):
    """Report display toggles should be visible in settings schema."""

    def test_report_show_llm_model_field_definition_exists(self):
        field = get_field_definition("REPORT_SHOW_LLM_MODEL")
        self.assertEqual(field["category"], "notification")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertEqual(field["default_value"], "true")
        self.assertFalse(field["is_sensitive"])

    def test_schema_response_includes_report_show_llm_model(self):
        schema = build_schema_response()
        notification_cat = next(
            (c for c in schema["categories"] if c["category"] == "notification"),
            None,
        )
        self.assertIsNotNone(notification_cat, "notification category missing")
        field_keys = {f["key"] for f in notification_cat["fields"]}
        self.assertIn("REPORT_SHOW_LLM_MODEL", field_keys)


class TestMarketReviewFieldsRegistered(unittest.TestCase):
    """Market review behavior toggles should be visible in settings schema."""

    def test_market_review_color_scheme_field_definition_exists(self):
        field = get_field_definition("MARKET_REVIEW_COLOR_SCHEME")
        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "string")
        self.assertEqual(field["ui_control"], "select")
        self.assertEqual(field["default_value"], "green_up")
        self.assertEqual(field["validation"]["enum"], ["green_up", "red_up"])
        self.assertFalse(field["is_sensitive"])

    def test_market_review_region_field_definition_exists(self):
        field = get_field_definition("MARKET_REVIEW_REGION")
        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "string")
        self.assertEqual(field["ui_control"], "text")
        self.assertEqual(field["default_value"], "cn")
        self.assertEqual(
            field["validation"]["allowed_values"],
            ["cn", "hk", "us", "jp", "kr", "both"],
        )
        self.assertEqual(
            field["validation"]["delimiter"],
            ",",
        )
        self.assertFalse(field["is_sensitive"])

    def test_daily_market_context_field_definition_exists(self):
        field = get_field_definition("DAILY_MARKET_CONTEXT_ENABLED")
        self.assertEqual(field["category"], "system")
        self.assertEqual(field["data_type"], "boolean")
        self.assertEqual(field["ui_control"], "switch")
        self.assertEqual(field["default_value"], "true")
        self.assertFalse(field["is_sensitive"])

    def test_schema_response_includes_market_review_color_scheme(self):
        schema = build_schema_response()
        system_cat = next((c for c in schema["categories"] if c["category"] == "system"), None)
        self.assertIsNotNone(system_cat, "system category missing")
        field_keys = {f["key"] for f in system_cat["fields"]}
        self.assertIn("MARKET_REVIEW_COLOR_SCHEME", field_keys)
        self.assertIn("DAILY_MARKET_CONTEXT_ENABLED", field_keys)
        self.assertIn("MARKET_REVIEW_REGION", field_keys)


class TestRealtimeSourcePriorityField(unittest.TestCase):
    """REALTIME_SOURCE_PRIORITY is an ordered multi-enum for the settings UI."""

    def test_field_definition_offers_source_catalog(self):
        field = get_field_definition("REALTIME_SOURCE_PRIORITY")
        self.assertEqual(field["category"], "data_source")
        self.assertEqual(field["default_value"], "tencent,akshare_sina,efinance,akshare_em")
        self.assertEqual(
            [option["value"] for option in field["options"]],
            ["tencent", "akshare_sina", "efinance", "akshare_em", "tushare", "tickflow"],
        )
        self.assertTrue(field["validation"]["multi_value"])
        self.assertTrue(field["validation"]["ordered"])
        self.assertEqual(field["validation"]["delimiter"], ",")
        # No allowed_values on purpose: stored aliases (e.g. akshare_qq) and
        # custom sources must not start failing validation.
        self.assertNotIn("allowed_values", field["validation"])


class TestConfigConditions(unittest.TestCase):
    def test_evaluate_config_conditions_and_operators(self) -> None:
        from src.core.config_registry import evaluate_config_conditions

        self.assertEqual(evaluate_config_conditions(None, {}), "met")
        cond = [{"key": "GENERATION_BACKEND", "operator": "equals", "value": "opencode_cli"}]
        self.assertEqual(evaluate_config_conditions(cond, {"GENERATION_BACKEND": "opencode_cli"}), "met")
        self.assertEqual(evaluate_config_conditions(cond, {"GENERATION_BACKEND": "litellm"}), "not_met")
        self.assertEqual(
            evaluate_config_conditions([{"key": "AGENT_MODE", "operator": "in", "value": ["single", "multi"]}], {"AGENT_MODE": "multi"}),
            "met",
        )
        self.assertEqual(
            evaluate_config_conditions([{"key": "X", "operator": "notEmpty"}], {"X": ""}),
            "not_met",
        )

    def test_evaluate_config_conditions_unknown_operator_fail_safe(self) -> None:
        from src.core.config_registry import evaluate_config_conditions

        self.assertEqual(evaluate_config_conditions([{"key": "X", "operator": "regex"}], {"X": "y"}), "unknown")

    def test_evaluate_config_conditions_normalizes_missing_scalar_values(self) -> None:
        from src.core.config_registry import evaluate_config_conditions

        for value_payload in ({}, {"value": None}):
            with self.subTest(value_payload=value_payload):
                equals = {"key": "X", "operator": "equals", **value_payload}
                not_equals = {"key": "X", "operator": "notEquals", **value_payload}
                self.assertEqual(evaluate_config_conditions([equals], {"X": ""}), "met")
                self.assertEqual(evaluate_config_conditions([not_equals], {"X": ""}), "not_met")

    def test_opencode_cli_model_has_visible_when_contract(self) -> None:
        from src.core.config_registry import get_field_definition

        contract = get_field_definition("OPENCODE_CLI_MODEL").get("contract")
        self.assertIsNotNone(contract)
        self.assertEqual(
            contract["visible_when"],
            [{"key": "GENERATION_BACKEND", "operator": "equals", "value": "opencode_cli"}],
        )


class TestUiPlacement(unittest.TestCase):
    """The backend declares which UI surface owns each AI-model field so the
    Web never maintains a second provider/key list."""

    def test_every_registered_ai_field_has_an_explicit_known_placement(self):
        from src.core.config_registry import build_schema_response

        known = {
            "model_access",
            "task_routing",
            "developer_diagnostics",
            "hidden_legacy",
        }
        ai_fields = next(
            category["fields"]
            for category in build_schema_response()["categories"]
            if category["category"] == "ai_model"
        )
        self.assertTrue(ai_fields)
        for field in ai_fields:
            self.assertIn(field.get("ui_placement"), known, field["key"])

    def test_model_access_keys(self):
        from src.core.config_registry import derive_ui_placement, get_field_definition

        self.assertEqual(derive_ui_placement("LLM_CHANNELS"), "model_access")
        for key in (
            "LLM_OPENAI_PROVIDER",
            "LLM_OPENAI_DISPLAY_NAME",
            "LLM_OPENAI_PROTOCOL",
            "LLM_MY_CHANNEL_BASE_URL",
            "LLM_DEEPSEEK_API_KEY",
            "LLM_DEEPSEEK_API_KEYS",
            "LLM_OLLAMA_MODELS",
            "LLM_HERMES_EXTRA_HEADERS",
            "LLM_CUSTOM01_ENABLED",
        ):
            self.assertEqual(derive_ui_placement(key), "model_access", key)

        extra_headers = get_field_definition(
            "LLM_CUSTOM01_EXTRA_HEADERS",
            '{"Authorization":"Bearer private"}',
        )
        self.assertTrue(extra_headers["is_sensitive"])
        self.assertEqual(extra_headers["data_type"], "json")
        self.assertEqual(extra_headers["ui_control"], "textarea")

    def test_task_routing_keys(self):
        from src.core.config_registry import derive_ui_placement

        for key in (
            "LITELLM_MODEL",
            "AGENT_LITELLM_MODEL",
            "VISION_MODEL",
            "LITELLM_FALLBACK_MODELS",
            "LLM_TEMPERATURE",
        ):
            self.assertEqual(derive_ui_placement(key), "task_routing", key)

    def test_developer_diagnostics_keys(self):
        from src.core.config_registry import derive_ui_placement

        for key in (
            "LLM_CONFIG_MODE",
            "LITELLM_CONFIG",
            "GENERATION_BACKEND",
            "GENERATION_FALLBACK_BACKEND",
            "GENERATION_BACKEND_MAX_CONCURRENCY",
            "GENERATION_BACKEND_MAX_OUTPUT_BYTES",
            "GENERATION_BACKEND_TIMEOUT_SECONDS",
            "LOCAL_CLI_BACKEND_MAX_CONCURRENCY",
            "OPENCODE_CLI_MODEL",
            "LLM_PROMPT_CACHE_HINTS_ENABLED",
            "LLM_PROMPT_CACHE_TELEMETRY_ENABLED",
            "LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL",
            "LLM_USAGE_HMAC_SECRET",
            "LLM_USAGE_HMAC_KEY_VERSION",
        ):
            self.assertEqual(derive_ui_placement(key), "developer_diagnostics", key)

    def test_prompt_cache_enabled_is_diagnostics_not_a_channel_field(self):
        # LLM_PROMPT_CACHE_HINTS_ENABLED also matches the LLM_<NAME>_ENABLED
        # shape; the diagnostics prefix must win over the channel pattern.
        from src.core.config_registry import derive_ui_placement

        self.assertEqual(
            derive_ui_placement("LLM_PROMPT_CACHE_HINTS_ENABLED"),
            "developer_diagnostics",
        )

    def test_hidden_legacy_keys(self):
        from src.core.config_registry import derive_ui_placement

        for key in (
            "OPENAI_API_KEY",
            "OPENAI_API_KEYS",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "OPENAI_VISION_MODEL",
            "OPENAI_TEMPERATURE",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL",
            "ANTHROPIC_MAX_TOKENS",
            "ANTHROPIC_TEMPERATURE",
            "GEMINI_API_KEY",
            "GEMINI_MODEL",
            "GEMINI_MODEL_FALLBACK",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_API_KEYS",
            "AIHUBMIX_KEY",
            "OLLAMA_API_BASE",
            "OLLAMA_MODEL",
            "ANSPIRE_LLM_BASE_URL",
            "ANSPIRE_LLM_MODEL",
            "ANSPIRE_LLM_ENABLED",
        ):
            self.assertEqual(derive_ui_placement(key), "hidden_legacy", key)

    def test_regular_fields_have_no_placement(self):
        from src.core.config_registry import derive_ui_placement

        for key in ("STOCK_LIST", "LOG_LEVEL", "TAVILY_API_KEYS", "ANSPIRE_API_KEYS"):
            self.assertIsNone(derive_ui_placement(key), key)

    def test_every_registered_ai_model_field_declares_a_placement(self):
        # A None placement on an ai_model field would fall back to the generic
        # category page and silently recreate a second edit entry.
        from src.core.config_registry import build_schema_response

        schema = build_schema_response()
        ai_model = next(c for c in schema["categories"] if c["category"] == "ai_model")
        self.assertTrue(ai_model["fields"])
        for field in ai_model["fields"]:
            self.assertIn(
                field.get("ui_placement"),
                {"model_access", "task_routing", "developer_diagnostics", "hidden_legacy"},
                f"{field['key']} has no ui_placement",
            )

    def test_field_definition_exposes_placement_for_dynamic_keys(self):
        from src.core.config_registry import get_field_definition

        self.assertEqual(get_field_definition("LLM_MY_LOCAL_API_KEY")["ui_placement"], "model_access")
        self.assertEqual(get_field_definition("LITELLM_MODEL")["ui_placement"], "task_routing")
        self.assertEqual(get_field_definition("STOCK_LIST")["ui_placement"], None)


if __name__ == "__main__":
    unittest.main()
