# -*- coding: utf-8 -*-
"""System configuration validation and configuration-mode contracts."""

from tests.system_config_service_test_support import (
    _SystemConfigServiceTestCaseBase,
    ANSPIRE_LLM_MODEL_DEFAULT,
    Config,
    ConfigValidationError,
    os,
    patch,
)


class SystemConfigServiceTestCase(_SystemConfigServiceTestCaseBase):
    def test_validate_reports_invalid_time(self) -> None:
        validation = self.service.validate(items=[{"key": "SCHEDULE_TIME", "value": "25:70"}])
        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_format" for issue in validation["issues"]))

    def test_validate_accepts_empty_schedule_times_fallback(self) -> None:
        validation = self.service.validate(items=[{"key": "SCHEDULE_TIMES", "value": ""}])
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_reports_invalid_searxng_url(self) -> None:
        validation = self.service.validate(items=[{"key": "SEARXNG_BASE_URLS", "value": "searx.local,https://ok.example"}])
        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_url" for issue in validation["issues"]))

    def test_validate_reports_invalid_public_searxng_toggle(self) -> None:
        validation = self.service.validate(
            items=[{"key": "SEARXNG_PUBLIC_INSTANCES_ENABLED", "value": "maybe"}]
        )
        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_type" for issue in validation["issues"]))

    def test_validate_reports_invalid_feishu_webhook_url(self) -> None:
        validation = self.service.validate(
            items=[{"key": "FEISHU_WEBHOOK_URL", "value": "feishu-hook-without-scheme"}]
        )
        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_url" for issue in validation["issues"]))

    def test_validate_reports_ntfy_url_without_topic(self) -> None:
        validation = self.service.validate(
            items=[{"key": "NTFY_URL", "value": "https://ntfy.sh"}]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "NTFY_URL" and issue["code"] == "invalid_ntfy_url"
                for issue in validation["issues"]
            )
        )

    def test_validate_reports_gotify_url_with_message_endpoint(self) -> None:
        validation = self.service.validate(
            items=[{"key": "GOTIFY_URL", "value": "https://gotify.example/message"}]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "GOTIFY_URL" and issue["code"] == "invalid_gotify_url"
                for issue in validation["issues"]
            )
        )

    def test_validate_reports_invalid_notification_route_channel(self) -> None:
        validation = self.service.validate(
            items=[{"key": "NOTIFICATION_REPORT_CHANNELS", "value": "wechat,not-a-channel,email"}]
        )
        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "NOTIFICATION_REPORT_CHANNELS"
                and issue["code"] == "invalid_allowed_value"
                for issue in validation["issues"]
            )
        )

    def test_validate_reports_invalid_notification_quiet_hours(self) -> None:
        validation = self.service.validate(
            items=[{"key": "NOTIFICATION_QUIET_HOURS", "value": "9:00-18:00"}]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "NOTIFICATION_QUIET_HOURS"
                and issue["code"] == "invalid_format"
                for issue in validation["issues"]
            )
        )

    def test_validate_reports_invalid_notification_timezone(self) -> None:
        validation = self.service.validate(
            items=[{"key": "NOTIFICATION_TIMEZONE", "value": "Mars/Olympus"}]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "NOTIFICATION_TIMEZONE"
                and issue["code"] == "invalid_timezone"
                for issue in validation["issues"]
            )
        )

    def test_validate_reports_invalid_notification_min_severity(self) -> None:
        validation = self.service.validate(
            items=[{"key": "NOTIFICATION_MIN_SEVERITY", "value": "notice"}]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "NOTIFICATION_MIN_SEVERITY"
                and issue["code"] == "invalid_enum"
                for issue in validation["issues"]
            )
        )

    def test_validate_warns_daily_digest_is_reserved(self) -> None:
        validation = self.service.validate(
            items=[{"key": "NOTIFICATION_DAILY_DIGEST_ENABLED", "value": "true"}]
        )

        self.assertTrue(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "NOTIFICATION_DAILY_DIGEST_ENABLED"
                and issue["code"] == "reserved_notification_daily_digest"
                and issue["severity"] == "warning"
                for issue in validation["issues"]
            )
        )

    def test_validate_warns_when_feishu_app_credentials_are_used_without_webhook(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "FEISHU_APP_ID", "value": "cli_xxx"},
                {"key": "FEISHU_APP_SECRET", "value": "secret_xxx"},
            ]
        )
        self.assertTrue(validation["valid"])
        issue = next(
            issue
            for issue in validation["issues"]
            if issue["code"] == "feishu_mode_mismatch"
            and issue["severity"] == "warning"
        )
        self.assertEqual(issue["key"], "FEISHU_CHAT_ID")
        self.assertIn("FEISHU_CHAT_ID", issue["message"])
        self.assertIn("static notification:", issue["expected"])
        self.assertIn("event subscription:", issue["expected"])

    def test_validate_no_warning_when_feishu_cloud_doc_credentials_without_webhook(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "FEISHU_APP_ID", "value": "cli_xxx"},
                {"key": "FEISHU_APP_SECRET", "value": "secret_xxx"},
                {"key": "FEISHU_FOLDER_TOKEN", "value": "folder_xxx"},
            ]
        )
        self.assertTrue(validation["valid"])
        self.assertFalse(
            any(
                issue["code"] == "feishu_mode_mismatch"
                and issue["severity"] == "warning"
                for issue in validation["issues"]
            )
        )

    def test_validate_warns_when_only_folder_token_cleared_with_app_credentials(self) -> None:
        """Clearing FEISHU_FOLDER_TOKEN while app credentials remain should trigger mismatch."""
        old_version = self.manager.get_config_version()
        self.service.update(
            config_version=old_version,
            items=[
                {"key": "FEISHU_APP_ID", "value": "cli_xxx"},
                {"key": "FEISHU_APP_SECRET", "value": "secret_xxx"},
            ],
        )
        validation = self.service.validate(
            items=[
                {"key": "FEISHU_FOLDER_TOKEN", "value": ""},
            ]
        )
        self.assertTrue(validation["valid"])
        self.assertTrue(
            any(
                issue["code"] == "feishu_mode_mismatch"
                and issue["severity"] == "warning"
                for issue in validation["issues"]
            )
        )

    def test_update_persists_public_searxng_toggle(self) -> None:
        old_version = self.manager.get_config_version()
        response = self.service.update(
            config_version=old_version,
            items=[{"key": "SEARXNG_PUBLIC_INSTANCES_ENABLED", "value": "false"}],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["SEARXNG_PUBLIC_INSTANCES_ENABLED"], "false")

    def test_validate_reports_invalid_llm_channel_definition(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_API_KEY", "value": ""},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "missing_api_key" for issue in validation["issues"]))

    def test_validate_preserves_model_based_protocol_inference_for_ollama_channel(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "lab"},
                {"key": "LLM_LAB_MODELS", "value": "ollama/llama3"},
                {"key": "LLM_LAB_API_KEY", "value": ""},
            ]
        )

        self.assertTrue(validation["valid"], validation["issues"])
        self.assertEqual(validation["issues"], [])

    def test_validate_reports_unknown_primary_model_for_channels(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LITELLM_MODEL", "value": "openai/gpt-4o"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["key"] == "LITELLM_MODEL" and issue["code"] == "unknown_model" for issue in validation["issues"]))

    def test_validate_rejects_bare_primary_when_channel_route_is_openai_canonical(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LITELLM_MODEL", "value": "gpt-4o-mini"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["key"] == "LITELLM_MODEL" and issue["code"] == "unknown_model" for issue in validation["issues"]))

    def test_validate_rejects_bare_fallback_when_channel_route_is_openai_canonical(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LITELLM_MODEL", "value": "openai/gpt-4o-mini"},
                {"key": "LITELLM_FALLBACK_MODELS", "value": "gpt-4o-mini"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "LITELLM_FALLBACK_MODELS"
                and issue["code"] == "unknown_model"
                for issue in validation["issues"]
            )
        )

    def test_validate_reports_bare_vision_when_channel_route_is_openai_canonical(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "VISION_MODEL", "value": "gpt-4o-mini"},
            ]
        )

        self.assertTrue(
            any(
                issue["key"] == "VISION_MODEL"
                and issue["code"] == "unknown_model"
                for issue in validation["issues"]
            ),
            validation["issues"],
        )

    def test_update_blocks_removing_channel_referenced_by_vision_model(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=alpha,beta",
            "LLM_ALPHA_PROTOCOL=openai",
            "LLM_ALPHA_BASE_URL=https://alpha.example.com/v1",
            "LLM_ALPHA_API_KEY=sk-alpha",
            "LLM_ALPHA_MODELS=alpha-model",
            "LLM_BETA_PROTOCOL=openai",
            "LLM_BETA_BASE_URL=https://beta.example.com/v1",
            "LLM_BETA_API_KEY=sk-beta",
            "LLM_BETA_MODELS=beta-model",
            "LITELLM_MODEL=openai/beta-model",
            "VISION_MODEL=openai/alpha-model",
        )

        with self.assertRaises(ConfigValidationError) as ctx:
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[
                    {"key": "LLM_CHANNELS", "value": "beta"},
                    {"key": "LLM_ALPHA_PROTOCOL", "value": ""},
                    {"key": "LLM_ALPHA_BASE_URL", "value": ""},
                    {"key": "LLM_ALPHA_API_KEY", "value": ""},
                    {"key": "LLM_ALPHA_MODELS", "value": ""},
                ],
            )

        issue = next(
            issue
            for issue in ctx.exception.issues
            if issue["code"] == "model_in_use"
        )
        self.assertEqual(issue["key"], "LLM_ALPHA_MODELS")
        self.assertEqual(issue["details"]["connection_ids"], ["alpha"])
        self.assertEqual(
            issue["details"]["referenced_by"],
            [{"task": "vision", "key": "VISION_MODEL"}],
        )

    def test_update_blocks_disabling_channel_referenced_by_vision_model(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=alpha,beta",
            "LLM_ALPHA_PROTOCOL=openai",
            "LLM_ALPHA_BASE_URL=https://alpha.example.com/v1",
            "LLM_ALPHA_API_KEY=sk-alpha",
            "LLM_ALPHA_MODELS=alpha-model",
            "LLM_BETA_PROTOCOL=openai",
            "LLM_BETA_BASE_URL=https://beta.example.com/v1",
            "LLM_BETA_API_KEY=sk-beta",
            "LLM_BETA_MODELS=beta-model",
            "LITELLM_MODEL=openai/beta-model",
            "VISION_MODEL=openai/alpha-model",
        )

        with self.assertRaises(ConfigValidationError) as ctx:
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "LLM_ALPHA_ENABLED", "value": "false"}],
            )

        issue = next(
            issue
            for issue in ctx.exception.issues
            if issue["code"] == "model_in_use"
        )
        self.assertEqual(issue["key"], "LLM_ALPHA_ENABLED")
        self.assertEqual(issue["details"]["connection_ids"], ["alpha"])
        self.assertEqual(
            issue["details"]["referenced_by"],
            [{"task": "vision", "key": "VISION_MODEL"}],
        )

    def test_update_allows_unrelated_save_with_stale_vision_reference(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=beta",
            "LLM_BETA_PROTOCOL=openai",
            "LLM_BETA_BASE_URL=https://beta.example.com/v1",
            "LLM_BETA_API_KEY=sk-beta",
            "LLM_BETA_MODELS=beta-model",
            "LITELLM_MODEL=openai/beta-model",
            "VISION_MODEL=openai/ghost-model",
            "STOCK_LIST=600519",
        )

        result = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "STOCK_LIST", "value": "600519,000001"}],
        )

        self.assertTrue(result["success"])
        self.assertEqual(self.manager.read_config_map()["STOCK_LIST"], "600519,000001")

    def test_update_blocks_removing_channel_referenced_by_primary_model(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=alpha,beta",
            "LLM_ALPHA_PROTOCOL=openai",
            "LLM_ALPHA_BASE_URL=https://alpha.example.com/v1",
            "LLM_ALPHA_API_KEY=sk-alpha",
            "LLM_ALPHA_MODELS=alpha-model",
            "LLM_BETA_PROTOCOL=openai",
            "LLM_BETA_BASE_URL=https://beta.example.com/v1",
            "LLM_BETA_API_KEY=sk-beta",
            "LLM_BETA_MODELS=beta-model",
            "LITELLM_MODEL=openai/alpha-model",
        )

        with self.assertRaises(ConfigValidationError) as ctx:
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[
                    {"key": "LLM_CHANNELS", "value": "beta"},
                    {"key": "LLM_ALPHA_PROTOCOL", "value": ""},
                    {"key": "LLM_ALPHA_BASE_URL", "value": ""},
                    {"key": "LLM_ALPHA_API_KEY", "value": ""},
                    {"key": "LLM_ALPHA_MODELS", "value": ""},
                ],
            )

        issue = next(
            issue
            for issue in ctx.exception.issues
            if issue["code"] == "model_in_use"
        )
        self.assertEqual(issue["key"], "LLM_ALPHA_MODELS")
        self.assertEqual(issue["details"]["connection_ids"], ["alpha"])
        self.assertEqual(
            issue["details"]["referenced_by"],
            [{"task": "report", "key": "LITELLM_MODEL"}],
        )

    def test_validate_accepts_deepseek_v4_primary_model_for_channel(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "deepseek"},
                {"key": "LLM_DEEPSEEK_PROTOCOL", "value": "deepseek"},
                {"key": "LLM_DEEPSEEK_BASE_URL", "value": "https://api.deepseek.com"},
                {"key": "LLM_DEEPSEEK_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_DEEPSEEK_MODELS", "value": "deepseek-v4-flash,deepseek-v4-pro"},
                {"key": "LITELLM_MODEL", "value": "deepseek/deepseek-v4-flash"},
            ]
        )

        self.assertTrue(validation["valid"], validation["issues"])
        self.assertEqual(validation["issues"], [])

    def test_validate_reports_unknown_agent_primary_model_for_channels(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "AGENT_LITELLM_MODEL", "value": "openai/gpt-4o"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["key"] == "AGENT_LITELLM_MODEL" and issue["code"] == "unknown_model" for issue in validation["issues"]))

    def test_validate_accepts_unprefixed_agent_model_when_channel_declares_openai_model(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_BASE_URL", "value": "https://api.openai.com/v1"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "AGENT_LITELLM_MODEL", "value": "gpt-4o-mini"},
            ]
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_update_rejects_incomplete_enabled_channel(self) -> None:
        self._rewrite_env("STOCK_LIST=600519")
        with self.assertRaises(ConfigValidationError):
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[
                    {"key": "LLM_CHANNELS", "value": "mychan"},
                    {"key": "LLM_MYCHAN_PROTOCOL", "value": "openai"},
                    {"key": "LLM_MYCHAN_BASE_URL", "value": "https://api.example.com/v1"},
                    {"key": "LLM_MYCHAN_ENABLED", "value": "true"},
                ],
            )

    def test_validate_allows_incomplete_disabled_channel_draft(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "draft1"},
                {"key": "LLM_DRAFT1_PROTOCOL", "value": "openai"},
                {"key": "LLM_DRAFT1_ENABLED", "value": "false"},
            ]
        )
        self.assertTrue(validation["valid"], validation["issues"])

    def test_unknown_contract_operator_blocks_disabled_draft_without_writing(self) -> None:
        from src.llm.provider_catalog import get_connection_field_schema

        self._rewrite_env("STOCK_LIST=600519")
        schema = get_connection_field_schema()
        base_url = next(field for field in schema if field["key"] == "base_url")
        base_url["contract"]["visible_when"] = [
            {"key": "provider_id", "operator": "futureOperator", "value": "custom"}
        ]
        items = [
            {"key": "LLM_CHANNELS", "value": "draft1"},
            {"key": "LLM_DRAFT1_PROTOCOL", "value": "openai"},
            {"key": "LLM_DRAFT1_ENABLED", "value": "false"},
        ]

        with patch(
            "src.services.system_config_service.get_connection_field_schema",
            return_value=schema,
        ):
            validation = self.service.validate(items=items)
            self.assertFalse(validation["valid"])
            self.assertTrue(
                any(issue["code"] == "unknown_contract_condition" for issue in validation["issues"]),
                validation["issues"],
            )
            with self.assertRaises(ConfigValidationError):
                self.service.update(
                    config_version=self.manager.get_config_version(),
                    items=items,
                )

        self.assertEqual(self.manager.read_config_map(), {"STOCK_LIST": "600519"})

    def test_dynamic_connection_validator_consumes_catalog_field_contract(self) -> None:
        from src.llm.provider_catalog import get_connection_field_schema

        schema = get_connection_field_schema()
        models = next(field for field in schema if field["key"] == "models")
        models["contract"].pop("required_when")
        with patch(
            "src.services.system_config_service.get_connection_field_schema",
            return_value=schema,
        ):
            validation = self.service.validate(
                items=[
                    {"key": "LLM_CHANNELS", "value": "custom_draft"},
                    {"key": "LLM_CUSTOM_DRAFT_PROVIDER", "value": "custom"},
                    {"key": "LLM_CUSTOM_DRAFT_PROTOCOL", "value": "openai"},
                    {"key": "LLM_CUSTOM_DRAFT_BASE_URL", "value": "https://api.example.com/v1"},
                    {"key": "LLM_CUSTOM_DRAFT_API_KEY", "value": "sk-test"},
                    {"key": "LLM_CUSTOM_DRAFT_ENABLED", "value": "true"},
                ]
            )

        self.assertTrue(validation["valid"], validation["issues"])

    def test_validate_allows_enabled_ollama_channel_without_api_key(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "ollama"},
                {"key": "LLM_OLLAMA_PROTOCOL", "value": "ollama"},
                {"key": "LLM_OLLAMA_BASE_URL", "value": "http://localhost:11434/v1"},
                {"key": "LLM_OLLAMA_ENABLED", "value": "true"},
                {"key": "LLM_OLLAMA_MODELS", "value": "llama3"},
            ]
        )
        self.assertTrue(validation["valid"], validation["issues"])

    def test_validate_allows_official_provider_without_base_url(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "openai"},
                {"key": "LLM_OPENAI_PROTOCOL", "value": "openai"},
                {"key": "LLM_OPENAI_ENABLED", "value": "true"},
                {"key": "LLM_OPENAI_API_KEY", "value": "sk-official"},
                {"key": "LLM_OPENAI_MODELS", "value": "gpt-4o-mini"},
            ]
        )
        self.assertTrue(validation["valid"], validation["issues"])

    def test_validate_rejects_custom_channel_missing_base_url(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "mycustom"},
                {"key": "LLM_MYCUSTOM_PROTOCOL", "value": "openai"},
                {"key": "LLM_MYCUSTOM_ENABLED", "value": "true"},
                {"key": "LLM_MYCUSTOM_API_KEY", "value": "sk-x"},
                {"key": "LLM_MYCUSTOM_MODELS", "value": "gpt-4o-mini"},
            ]
        )
        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "LLM_MYCUSTOM_BASE_URL" and issue["code"] == "missing_base_url"
                for issue in validation["issues"]
            ),
            validation["issues"],
        )

    def test_validate_recognizes_existing_saved_channel_key(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LLM_CHANNELS=aihubmix",
            "LLM_AIHUBMIX_PROTOCOL=openai",
            "LLM_AIHUBMIX_BASE_URL=https://aihubmix.com/v1",
            "LLM_AIHUBMIX_ENABLED=true",
            "LLM_AIHUBMIX_API_KEY=sk-saved-secret",
            "LLM_AIHUBMIX_MODELS=gpt-5.5",
        )
        # Editing models re-validates the channel; the saved key must not be
        # misread as missing.
        validation = self.service.validate(
            items=[{"key": "LLM_AIHUBMIX_MODELS", "value": "gpt-5.5,claude-sonnet-4-6"}]
        )
        self.assertTrue(validation["valid"], validation["issues"])

    def test_update_rejects_all_channels_when_one_incomplete(self) -> None:
        self._rewrite_env("STOCK_LIST=600519")
        with self.assertRaises(ConfigValidationError):
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[
                    {"key": "LLM_CHANNELS", "value": "good,bad"},
                    {"key": "LLM_GOOD_PROTOCOL", "value": "openai"},
                    {"key": "LLM_GOOD_BASE_URL", "value": "https://api.example.com/v1"},
                    {"key": "LLM_GOOD_ENABLED", "value": "true"},
                    {"key": "LLM_GOOD_API_KEY", "value": "sk-good"},
                    {"key": "LLM_GOOD_MODELS", "value": "gpt-4o"},
                    {"key": "LLM_BAD_PROTOCOL", "value": "openai"},
                    {"key": "LLM_BAD_BASE_URL", "value": "https://api.example.com/v1"},
                    {"key": "LLM_BAD_ENABLED", "value": "true"},
                ],
            )
        saved = self.manager.read_config_map()
        self.assertNotIn("LLM_CHANNELS", saved)
        self.assertNotIn("LLM_GOOD_API_KEY", saved)

    def test_validate_ignores_untouched_incomplete_channel(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LLM_CHANNELS=legacy",
            "LLM_LEGACY_PROTOCOL=openai",
            "LLM_LEGACY_BASE_URL=https://api.example.com/v1",
            "LLM_LEGACY_ENABLED=true",
        )
        validation = self.service.validate(items=[{"key": "LOG_LEVEL", "value": "DEBUG"}])
        self.assertTrue(validation["valid"], validation["issues"])

    def test_validate_rejects_clearing_key_on_enabled_channel(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LLM_CHANNELS=aihubmix",
            "LLM_AIHUBMIX_PROTOCOL=openai",
            "LLM_AIHUBMIX_BASE_URL=https://aihubmix.com/v1",
            "LLM_AIHUBMIX_ENABLED=true",
            "LLM_AIHUBMIX_API_KEY=sk-saved",
            "LLM_AIHUBMIX_MODELS=gpt-5.5",
        )
        validation = self.service.validate(items=[{"key": "LLM_AIHUBMIX_API_KEY", "value": ""}])
        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(issue["code"] == "missing_api_key" for issue in validation["issues"]),
            validation["issues"],
        )

    def test_validate_revalidates_channel_flipped_to_enabled(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LLM_CHANNELS=aihubmix",
            "LLM_AIHUBMIX_PROTOCOL=openai",
            "LLM_AIHUBMIX_BASE_URL=https://aihubmix.com/v1",
            "LLM_AIHUBMIX_ENABLED=false",
        )
        validation = self.service.validate(items=[{"key": "LLM_AIHUBMIX_ENABLED", "value": "true"}])
        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(issue["code"] in ("missing_api_key", "missing_models") for issue in validation["issues"]),
            validation["issues"],
        )

    def test_llm_config_mode_status_auto_channels_over_legacy(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LLM_CONFIG_MODE=auto",
            "LLM_CHANNELS=aihubmix",
            "LLM_AIHUBMIX_PROTOCOL=openai",
            "LLM_AIHUBMIX_BASE_URL=https://aihubmix.com/v1",
            "LLM_AIHUBMIX_API_KEY=sk-x",
            "LLM_AIHUBMIX_MODELS=gpt-5.5",
            "OPENAI_API_KEY=sk-legacy",
        )
        status = self.service.get_llm_config_mode_status()
        self.assertEqual(status["requested_mode"], "auto")
        self.assertEqual(status["effective_mode"], "channels")
        self.assertIn("channels", status["detected_sources"])
        self.assertIn("legacy", status["overridden_sources"])

    def test_llm_config_mode_status_forced_yaml_without_config_warns(self) -> None:
        self._rewrite_env("STOCK_LIST=600519", "LLM_CONFIG_MODE=yaml")
        status = self.service.get_llm_config_mode_status()
        self.assertEqual(status["requested_mode"], "yaml")
        self.assertEqual(status["effective_mode"], "yaml")
        self.assertTrue(
            any(issue["code"] == "forced_mode_no_config" for issue in status["issues"]),
            status["issues"],
        )

    def test_preview_legacy_channels_migration_lists_channels_redacted(self) -> None:
        self._rewrite_env("STOCK_LIST=600519", "OPENAI_API_KEY=sk-openai-secret", "OPENAI_MODEL=gpt-x")
        preview = self.service.preview_legacy_channels_migration()
        names = [channel["name"] for channel in preview["channels"]]
        self.assertIn("openai", names)
        self.assertNotIn("sk-openai-secret", str(preview))

    def test_apply_legacy_channels_migration_switches_mode_and_copies_keys(self) -> None:
        self._rewrite_env("STOCK_LIST=600519", "OPENAI_API_KEY=sk-openai-secret", "OPENAI_MODEL=gpt-x")
        # apply() reloads runtime config via setup_env(override=True); patch.dict
        # restores os.environ afterwards so migrated keys don't leak to other tests.
        with patch.dict(os.environ, {}, clear=False):
            self.service.apply_legacy_channels_migration(config_version=self.manager.get_config_version())
        saved = self.manager.read_config_map()
        self.assertEqual(saved.get("LLM_CONFIG_MODE"), "channels")
        self.assertIn("openai", saved.get("LLM_CHANNELS") or "")
        self.assertEqual(saved.get("LLM_OPENAI_PROVIDER"), "openai")
        self.assertEqual(saved.get("LLM_OPENAI_API_KEY"), "sk-openai-secret")

    def test_apply_legacy_channels_migration_without_legacy_config_raises(self) -> None:
        self._rewrite_env("STOCK_LIST=600519")
        with self.assertRaises(ConfigValidationError):
            self.service.apply_legacy_channels_migration(config_version=self.manager.get_config_version())

    def test_field_contract_required_when_enforced_and_scoped(self) -> None:
        fake_contracts = {
            "MY_CONDITIONAL_FIELD": {
                "requirement": "optional",
                "required_when": [{"key": "GENERATION_BACKEND", "operator": "equals", "value": "opencode_cli"}],
            },
        }
        with patch("src.services.system_config_service.get_contract_field_definitions", return_value=fake_contracts):
            invalid = self.service.validate(items=[{"key": "GENERATION_BACKEND", "value": "opencode_cli"}])
            self.assertFalse(invalid["valid"])
            self.assertTrue(
                any(issue["code"] == "field_required" and issue["key"] == "MY_CONDITIONAL_FIELD" for issue in invalid["issues"]),
                invalid["issues"],
            )
            valid = self.service.validate(items=[{"key": "GENERATION_BACKEND", "value": "litellm"}])
            self.assertTrue(valid["valid"], valid["issues"])

    def test_field_contract_hidden_field_not_required(self) -> None:
        fake_contracts = {
            "MY_HIDDEN_FIELD": {
                "requirement": "required",
                "visible_when": [{"key": "GENERATION_BACKEND", "operator": "equals", "value": "opencode_cli"}],
            },
        }
        with patch("src.services.system_config_service.get_contract_field_definitions", return_value=fake_contracts):
            # backend != opencode_cli -> field hidden -> not required -> save allowed.
            result = self.service.validate(items=[{"key": "GENERATION_BACKEND", "value": "litellm"}])
            self.assertTrue(result["valid"], result["issues"])

    def test_validate_rejects_explicit_hermes_only_agent_model(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "hermes"},
                {"key": "LLM_HERMES_API_KEY", "value": "sk-hermes-test-value"},
                {"key": "LLM_HERMES_MODELS", "value": "hermes-agent"},
                {"key": "AGENT_LITELLM_MODEL", "value": "openai/hermes-agent"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "AGENT_LITELLM_MODEL"
                and issue["code"] == "explicit_agent_model_no_safe_deployment"
                for issue in validation["issues"]
            )
        )

    def test_validate_allows_explicit_mixed_agent_model(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "hermes,remote"},
                {"key": "LLM_HERMES_API_KEY", "value": "sk-hermes-test-value"},
                {"key": "LLM_HERMES_MODELS", "value": "shared-route"},
                {"key": "LLM_REMOTE_PROTOCOL", "value": "openai"},
                {"key": "LLM_REMOTE_BASE_URL", "value": "https://api.example.com/v1"},
                {"key": "LLM_REMOTE_API_KEY", "value": "sk-remote-test-value"},
                {"key": "LLM_REMOTE_MODELS", "value": "shared-route"},
                {"key": "AGENT_LITELLM_MODEL", "value": "openai/shared-route"},
            ]
        )

        self.assertFalse(
            any(
                issue["key"] == "AGENT_LITELLM_MODEL"
                and issue["code"] == "explicit_agent_model_no_safe_deployment"
                for issue in validation["issues"]
            ),
            validation["issues"],
        )

    def test_validate_rejects_mixed_generation_primary_and_fallback(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "hermes,remote"},
                {"key": "LLM_HERMES_API_KEY", "value": "sk-hermes-test-value"},
                {"key": "LLM_HERMES_MODELS", "value": "shared-route"},
                {"key": "LLM_REMOTE_PROTOCOL", "value": "openai"},
                {"key": "LLM_REMOTE_BASE_URL", "value": "https://api.example.com/v1"},
                {"key": "LLM_REMOTE_API_KEY", "value": "sk-remote-test-value"},
                {"key": "LLM_REMOTE_MODELS", "value": "shared-route"},
                {"key": "LITELLM_MODEL", "value": "openai/shared-route"},
                {"key": "LITELLM_FALLBACK_MODELS", "value": "openai/shared-route"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "LITELLM_MODEL"
                and issue["code"] == "mixed_hermes_route_unsupported"
                for issue in validation["issues"]
            )
        )
        self.assertTrue(
            any(
                issue["key"] == "LITELLM_FALLBACK_MODELS"
                and issue["code"] == "mixed_hermes_route_unsupported"
                for issue in validation["issues"]
            )
        )

    def test_validate_rejects_bare_mixed_generation_primary_and_fallback(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "hermes,remote"},
                {"key": "LLM_HERMES_API_KEY", "value": "sk-hermes-test-value"},
                {"key": "LLM_HERMES_MODELS", "value": "shared-route"},
                {"key": "LLM_REMOTE_PROTOCOL", "value": "openai"},
                {"key": "LLM_REMOTE_BASE_URL", "value": "https://api.example.com/v1"},
                {"key": "LLM_REMOTE_API_KEY", "value": "sk-remote-test-value"},
                {"key": "LLM_REMOTE_MODELS", "value": "shared-route"},
                {"key": "LITELLM_MODEL", "value": "shared-route"},
                {"key": "LITELLM_FALLBACK_MODELS", "value": "shared-route"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "LITELLM_MODEL"
                and issue["code"] == "mixed_hermes_route_unsupported"
                for issue in validation["issues"]
            )
        )
        self.assertTrue(
            any(
                issue["key"] == "LITELLM_FALLBACK_MODELS"
                and issue["code"] == "mixed_hermes_route_unsupported"
                for issue in validation["issues"]
            )
        )

    def test_validate_rejects_bare_hermes_vision_model(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "hermes"},
                {"key": "LLM_HERMES_API_KEY", "value": "sk-hermes-test-value"},
                {"key": "LLM_HERMES_MODELS", "value": "hermes-agent"},
                {"key": "VISION_MODEL", "value": "hermes-agent"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "VISION_MODEL"
                and issue["code"] == "hermes_vision_unsupported"
                for issue in validation["issues"]
            )
        )

    @patch.object(
        Config,
        "_parse_litellm_yaml",
        return_value=[
            {
                "model_name": "gpt4o",
                "litellm_params": {"model": "openai/gpt-4o-mini", "api_key": "sk-test-value"},
            }
        ],
    )
    def test_validate_accepts_unprefixed_agent_model_when_yaml_declares_alias(self, _mock_parse_yaml) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LITELLM_CONFIG", "value": "/tmp/litellm.yaml"},
                {"key": "AGENT_LITELLM_MODEL", "value": "gpt4o"},
            ]
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    @patch.object(
        Config,
        "_parse_litellm_yaml",
        return_value=[{"model_name": "gemini/gemini-2.5-flash", "litellm_params": {"model": "gemini/gemini-2.5-flash"}}],
    )
    def test_validate_skips_channel_checks_when_litellm_yaml_is_active(self, _mock_parse_yaml) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LITELLM_CONFIG", "value": "/tmp/litellm.yaml"},
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_API_KEY", "value": ""},
                {"key": "LITELLM_MODEL", "value": "gemini/gemini-2.5-flash"},
            ]
        )
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_get_config_preserves_labeled_select_options_and_enum_validation(self) -> None:
        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        agent_arch_schema = items["AGENT_ARCH"]["schema"]
        self.assertEqual(agent_arch_schema["options"][0]["value"], "single")
        self.assertEqual(agent_arch_schema["options"][1]["label"], "Multi Agent (Orchestrator)")
        self.assertEqual(agent_arch_schema["validation"]["enum"], ["single", "multi"])

        report_language_schema = items["REPORT_LANGUAGE"]["schema"]
        self.assertEqual(report_language_schema["validation"]["enum"], ["zh", "en", "ko"])
        self.assertEqual(report_language_schema["options"][1]["value"], "en")
        self.assertEqual(report_language_schema["options"][2]["value"], "ko")

        self.assertEqual(items["AGENT_ORCHESTRATOR_TIMEOUT_S"]["schema"]["default_value"], "600")
        self.assertTrue(items["AGENT_DEEP_RESEARCH_BUDGET"]["schema"]["is_editable"])
        self.assertTrue(items["AGENT_EVENT_MONITOR_ENABLED"]["schema"]["is_editable"])

        context_profile_schema = items["AGENT_CONTEXT_COMPRESSION_PROFILE"]["schema"]
        self.assertEqual(
            [option["label"] for option in context_profile_schema["options"]],
            ["成本优先", "均衡推荐", "长上下文原文优先"],
        )
        self.assertEqual(
            context_profile_schema["validation"]["enum"],
            ["cost", "balanced", "long_context_raw_first"],
        )
        market_review_schema = items["MARKET_REVIEW_REGION"]["schema"]
        self.assertEqual(
            market_review_schema["validation"]["allowed_values"],
            ["cn", "hk", "us", "jp", "kr", "both"],
        )
        self.assertEqual(market_review_schema["validation"]["delimiter"], ",")
        self.assertEqual(
            items["AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS"]["schema"]["default_value"],
            "",
        )
        self.assertEqual(
            items["AGENT_CONTEXT_PROTECTED_TURNS"]["schema"]["default_value"],
            "",
        )

    def test_validate_reports_invalid_select_option(self) -> None:
        validation = self.service.validate(items=[{"key": "AGENT_ARCH", "value": "invalid-mode"}])

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_enum" for issue in validation["issues"]))

    def test_validate_reports_generation_backend_numeric_maximum(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "GENERATION_BACKEND_TIMEOUT_SECONDS", "value": "3601"},
                {"key": "GENERATION_BACKEND_MAX_OUTPUT_BYTES", "value": "33554433"},
                {"key": "GENERATION_BACKEND_MAX_CONCURRENCY", "value": "17"},
                {"key": "LOCAL_CLI_BACKEND_MAX_CONCURRENCY", "value": "5"},
            ]
        )

        self.assertFalse(validation["valid"])
        issues = {issue["key"]: issue for issue in validation["issues"]}
        self.assertEqual(issues["GENERATION_BACKEND_TIMEOUT_SECONDS"]["expected"], "<=3600")
        self.assertEqual(issues["GENERATION_BACKEND_MAX_OUTPUT_BYTES"]["expected"], "<=33554432")
        self.assertEqual(issues["GENERATION_BACKEND_MAX_CONCURRENCY"]["expected"], "<=16")
        self.assertEqual(issues["LOCAL_CLI_BACKEND_MAX_CONCURRENCY"]["expected"], "<=4")

    def test_validate_accepts_report_language_english(self) -> None:
        validation = self.service.validate(items=[{"key": "REPORT_LANGUAGE", "value": "en"}])

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_accepts_report_language_korean(self) -> None:
        validation = self.service.validate(items=[{"key": "REPORT_LANGUAGE", "value": "ko"}])

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_accepts_comma_separated_market_review_region(self) -> None:
        validation = self.service.validate(
            items=[{"key": "MARKET_REVIEW_REGION", "value": "cn,jp,us"}]
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_accepts_blank_context_compression_preset_fields(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS", "value": ""},
                {"key": "AGENT_CONTEXT_PROTECTED_TURNS", "value": ""},
            ]
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_reports_invalid_context_compression_profile(self) -> None:
        validation = self.service.validate(
            items=[{"key": "AGENT_CONTEXT_COMPRESSION_PROFILE", "value": "invalid"}]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_enum" for issue in validation["issues"]))

    def test_config_loads_context_compression_preset_when_numeric_values_are_blank(self) -> None:
        self.env_path.write_text(
            "\n".join(
                [
                    "AGENT_CONTEXT_COMPRESSION_PROFILE=cost",
                    "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS=",
                    "AGENT_CONTEXT_PROTECTED_TURNS=",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"ENV_FILE": str(self.env_path)}, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_context_compression_profile, "cost")
        self.assertEqual(config.agent_context_compression_trigger_tokens, 6000)
        self.assertEqual(config.agent_context_protected_turns, 2)

        self.env_path.write_text(
            "AGENT_CONTEXT_COMPRESSION_PROFILE=long_context_raw_first\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"ENV_FILE": str(self.env_path)}, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_context_compression_profile, "long_context_raw_first")
        self.assertEqual(config.agent_context_compression_trigger_tokens, 24000)
        self.assertEqual(config.agent_context_protected_turns, 6)

        self.env_path.write_text(
            "\n".join(
                [
                    "AGENT_CONTEXT_COMPRESSION_PROFILE=bad-profile",
                    "AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS=bad-int",
                    "AGENT_CONTEXT_PROTECTED_TURNS=0",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"ENV_FILE": str(self.env_path)}, clear=True):
            config = Config._load_from_env()

        self.assertEqual(config.agent_context_compression_profile, "balanced")
        self.assertEqual(config.agent_context_compression_trigger_tokens, 12000)
        self.assertEqual(config.agent_context_protected_turns, 4)

    def test_validate_reports_invalid_json(self) -> None:
        validation = self.service.validate(items=[{"key": "AGENT_EVENT_ALERT_RULES_JSON", "value": "[invalid"}])

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_json" for issue in validation["issues"]))

    def test_validate_accepts_blank_optional_json(self) -> None:
        validation = self.service.validate(items=[{"key": "AGENT_EVENT_ALERT_RULES_JSON", "value": ""}])

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_accepts_multiline_json(self) -> None:
        validation = self.service.validate(items=[{
            "key": "AGENT_EVENT_ALERT_RULES_JSON",
            "value": (
                "[\n"
                '  {"stock_code":"600519","alert_type":"price_cross","direction":"above","price":1800}\n'
                "]"
            ),
        }])

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_update_minifies_multiline_json_before_storage(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{
                "key": "AGENT_EVENT_ALERT_RULES_JSON",
                "value": (
                    "[\n"
                    '  {"stock_code":"600519","alert_type":"price_cross","direction":"above","price":1800}\n'
                    "]"
                ),
            }],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        current_map = self.manager.read_config_map()
        self.assertEqual(
            current_map["AGENT_EVENT_ALERT_RULES_JSON"],
            '[{"stock_code":"600519","alert_type":"price_cross","direction":"above","price":1800}]',
        )

    def test_validate_accepts_legacy_agent_orchestrator_mode_alias(self) -> None:
        validation = self.service.validate(items=[{"key": "AGENT_ORCHESTRATOR_MODE", "value": "strategy"}])

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_get_config_projects_legacy_strategy_aliases_onto_skill_fields(self) -> None:
        self._rewrite_env(
            "AGENT_STRATEGY_DIR=legacy-strategies",
            "AGENT_STRATEGY_AUTOWEIGHT=false",
            "AGENT_STRATEGY_ROUTING=manual",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["AGENT_SKILL_DIR"]["value"], "legacy-strategies")
        self.assertEqual(items["AGENT_SKILL_AUTOWEIGHT"]["value"], "false")
        self.assertEqual(items["AGENT_SKILL_ROUTING"]["value"], "manual")
        self.assertNotIn("AGENT_STRATEGY_DIR", items)
        self.assertNotIn("AGENT_STRATEGY_AUTOWEIGHT", items)
        self.assertNotIn("AGENT_STRATEGY_ROUTING", items)

    def test_get_config_respects_empty_canonical_skill_field_over_legacy_alias(self) -> None:
        self._rewrite_env(
            "AGENT_SKILL_DIR=",
            "AGENT_STRATEGY_DIR=legacy-strategies",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["AGENT_SKILL_DIR"]["value"], "")

    def test_get_config_normalizes_legacy_orchestrator_mode_for_ui(self) -> None:
        self._rewrite_env("AGENT_ORCHESTRATOR_MODE=strategy")

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["AGENT_ORCHESTRATOR_MODE"]["value"], "specialist")
        self.assertEqual(
            items["AGENT_ORCHESTRATOR_MODE"]["schema"]["validation"]["enum"],
            ["quick", "standard", "full", "specialist", "strategy", "skill"],
        )

    @patch.object(
        Config,
        "_parse_litellm_yaml",
        return_value=[{"model_name": "gemini/gemini-2.5-flash", "litellm_params": {"model": "gemini/gemini-2.5-flash"}}],
    )
    def test_validate_reports_unknown_primary_model_for_litellm_yaml(self, _mock_parse_yaml) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LITELLM_CONFIG", "value": "/tmp/litellm.yaml"},
                {"key": "LITELLM_MODEL", "value": "openai/gpt-4o-mini"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["key"] == "LITELLM_MODEL" and issue["code"] == "unknown_model" for issue in validation["issues"]))

    @patch.object(Config, "_parse_litellm_yaml", return_value=[])
    def test_validate_keeps_channel_checks_when_litellm_yaml_has_no_models(self, _mock_parse_yaml) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LITELLM_CONFIG", "value": "/tmp/litellm.yaml"},
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_API_KEY", "value": ""},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "missing_api_key" for issue in validation["issues"]))

    def test_validate_reports_stale_primary_model_when_all_channels_disabled(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_ENABLED", "value": "false"},
                {"key": "LITELLM_MODEL", "value": "openai/gpt-4o-mini"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["key"] == "LITELLM_MODEL" and issue["code"] == "missing_runtime_source" for issue in validation["issues"]))

    def test_validate_reports_stale_agent_primary_model_when_all_channels_disabled(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_ENABLED", "value": "false"},
                {"key": "AGENT_LITELLM_MODEL", "value": "openai/gpt-4o-mini"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["key"] == "AGENT_LITELLM_MODEL" and issue["code"] == "missing_runtime_source" for issue in validation["issues"]))

    def test_validate_allows_primary_model_when_all_channels_disabled_but_legacy_key_exists(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_ENABLED", "value": "false"},
                {"key": "OPENAI_API_KEY", "value": "sk-legacy-value"},
                {"key": "LITELLM_MODEL", "value": "openai/gpt-4o-mini"},
            ]
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_allows_anspire_channel_with_shared_key_defaults(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "anspire"},
                {"key": "ANSPIRE_API_KEYS", "value": "sk-anspire-test-value"},
            ]
        )

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_treats_blank_anspire_channel_enabled_as_shared_disable(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "anspire"},
                {"key": "LLM_ANSPIRE_ENABLED", "value": "   "},
                {"key": "ANSPIRE_LLM_ENABLED", "value": "false"},
            ]
        )

        self.assertTrue(validation["valid"], validation["issues"])
        self.assertEqual(validation["issues"], [])

    def test_validate_excludes_blank_disabled_anspire_channel_from_runtime_models(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "anspire"},
                {"key": "LLM_ANSPIRE_ENABLED", "value": "   "},
                {"key": "ANSPIRE_LLM_ENABLED", "value": "false"},
                {"key": "ANSPIRE_API_KEYS", "value": "sk-anspire-test-value"},
                {"key": "LITELLM_MODEL", "value": f"openai/{ANSPIRE_LLM_MODEL_DEFAULT}"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["key"] == "LITELLM_MODEL" and issue["code"] == "missing_runtime_source" for issue in validation["issues"]))

    def test_validate_excludes_disabled_anspire_channel_from_legacy_runtime_source(self) -> None:
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "anspire"},
                {"key": "LLM_ANSPIRE_ENABLED", "value": "false"},
                {"key": "ANSPIRE_API_KEYS", "value": "sk-anspire-test-value"},
                {"key": "LITELLM_MODEL", "value": f"openai/{ANSPIRE_LLM_MODEL_DEFAULT}"},
            ]
        )

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["key"] == "LITELLM_MODEL" and issue["code"] == "missing_runtime_source" for issue in validation["issues"]))
