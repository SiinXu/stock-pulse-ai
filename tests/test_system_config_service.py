# -*- coding: utf-8 -*-
"""System configuration event, update, import, and documented selector contracts."""

from tests.system_config_service_test_support import (
    _SystemConfigServiceTestCaseBase,
    Config,
    ConfigConflictError,
    Path,
    SystemConfigService,
    os,
    patch,
)


class SystemConfigServiceTestCase(_SystemConfigServiceTestCaseBase):
    def test_validate_accepts_minimax_model_as_direct_env_provider(self) -> None:
        """minimax is NOT a managed key provider; it uses LiteLLM direct-env routing."""
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "minimax/MiniMax-M1"},
                {"key": "LLM_PRIMARY_ENABLED", "value": "false"},
                {"key": "LITELLM_MODEL", "value": "minimax/MiniMax-M1"},
            ]
        )

        self.assertFalse(any(issue.get("key") == "LITELLM_MODEL" and issue["code"] == "missing_runtime_source" for issue in validation.get("issues", [])))

    def test_validate_accepts_cohere_model_as_direct_env_provider(self) -> None:
        """cohere is NOT a managed key provider; it also uses LiteLLM direct-env routing."""
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_ENABLED", "value": "false"},
                {"key": "LITELLM_MODEL", "value": "cohere/command-r-plus"},
            ]
        )

        self.assertFalse(any(issue.get("key") == "LITELLM_MODEL" and issue["code"] == "missing_runtime_source" for issue in validation.get("issues", [])))

    def test_validate_accepts_google_model_as_direct_env_provider(self) -> None:
        """google prefix is not managed by project key buckets and is kept as direct provider routing."""
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_ENABLED", "value": "false"},
                {"key": "LITELLM_MODEL", "value": "google/gemini-2.5-flash"},
            ]
        )

        self.assertFalse(any(issue.get("key") == "LITELLM_MODEL" and issue["code"] == "missing_runtime_source" for issue in validation.get("issues", [])))

    def test_validate_accepts_xai_model_as_direct_env_provider(self) -> None:
        """xai is not a managed provider key and is also preserved as direct runtime source."""
        validation = self.service.validate(
            items=[
                {"key": "LLM_CHANNELS", "value": "primary"},
                {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test-value"},
                {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                {"key": "LLM_PRIMARY_ENABLED", "value": "false"},
                {"key": "LITELLM_MODEL", "value": "xai/grok-beta"},
            ]
        )

        self.assertFalse(any(issue.get("key") == "LITELLM_MODEL" and issue["code"] == "missing_runtime_source" for issue in validation.get("issues", [])))

    def test_validate_reports_invalid_event_rule_semantics(self) -> None:
        validation = self.service.validate(items=[{
            "key": "AGENT_EVENT_ALERT_RULES_JSON",
            "value": '[{"stock_code":"600519","alert_type":"price_cross","status":"bad","direction":"above","price":1800}]',
        }])

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_event_rule" for issue in validation["issues"]))

    def test_validate_accepts_price_change_percent_event_rule(self) -> None:
        validation = self.service.validate(items=[{
            "key": "AGENT_EVENT_ALERT_RULES_JSON",
            "value": (
                '[{"stock_code":"300750","alert_type":"price_change_percent",'
                '"direction":"down","change_pct":3.0}]'
            ),
        }])

        self.assertTrue(validation["valid"])
        self.assertEqual(validation["issues"], [])

    def test_validate_rejects_unsupported_event_rule_type(self) -> None:
        validation = self.service.validate(items=[{
            "key": "AGENT_EVENT_ALERT_RULES_JSON",
            "value": '[{"stock_code":"600519","alert_type":"sentiment_shift"}]',
        }])

        self.assertFalse(validation["valid"])
        self.assertTrue(any(issue["code"] == "invalid_event_rule" for issue in validation["issues"]))

    @patch.object(SystemConfigService, "_reload_runtime_singletons")
    def test_update_with_reload_resets_runtime_singletons(
        self,
        mock_reload_runtime_singletons,
    ) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "STOCK_LIST", "value": "600519"}],
            reload_now=True,
        )

        self.assertTrue(response["success"])
        mock_reload_runtime_singletons.assert_called_once()

    def test_update_with_reload_applies_updated_env_file_when_process_env_is_stale(self) -> None:
        os.environ["STOCK_LIST"] = "600519,000001"

        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "STOCK_LIST", "value": "300750,TSLA"}],
            reload_now=True,
        )

        self.assertTrue(response["success"])
        self.assertEqual(Config.get_instance().stock_list, ["300750", "TSLA"])

    @patch.object(SystemConfigService, "_reload_runtime_singletons")
    def test_update_escapes_custom_webhook_template_and_runtime_reads_literals(
        self,
        _mock_reload_runtime_singletons,
    ) -> None:
        template = '{"title":$title_json,"content":$content_json}'

        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "CUSTOM_WEBHOOK_BODY_TEMPLATE", "value": template}],
            reload_now=True,
        )

        self.assertTrue(response["success"])
        self.assertIn(
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$$title_json,"content":$$content_json}\n',
            self.env_path.read_text(encoding="utf-8"),
        )
        self.assertEqual(Config.get_instance().custom_webhook_body_template, template)

        items = {
            item["key"]: item
            for item in self.service.get_config(include_schema=True)["items"]
        }
        self.assertEqual(items["CUSTOM_WEBHOOK_BODY_TEMPLATE"]["value"], template)

    @patch.object(SystemConfigService, "_reload_runtime_singletons")
    def test_update_escapes_braced_custom_webhook_template_and_runtime_reads_literals(
        self,
        _mock_reload_runtime_singletons,
    ) -> None:
        template = '{"content":${content_json}}'

        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "CUSTOM_WEBHOOK_BODY_TEMPLATE", "value": template}],
            reload_now=True,
        )

        self.assertTrue(response["success"])
        self.assertIn(
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$${content_json}}\n',
            self.env_path.read_text(encoding="utf-8"),
        )
        self.assertEqual(Config.get_instance().custom_webhook_body_template, template)

        items = {
            item["key"]: item
            for item in self.service.get_config(include_schema=True)["items"]
        }
        self.assertEqual(items["CUSTOM_WEBHOOK_BODY_TEMPLATE"]["value"], template)

    def test_update_raises_conflict_for_stale_version(self) -> None:
        with self.assertRaises(ConfigConflictError):
            self.service.update(
                config_version="stale-version",
                items=[{"key": "STOCK_LIST", "value": "600519"}],
                reload_now=False,
            )

    def test_update_appends_news_window_explainability_warning(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {"key": "NEWS_STRATEGY_PROFILE", "value": "ultra_short"},
                {"key": "NEWS_MAX_AGE_DAYS", "value": "7"},
            ],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        joined = " | ".join(response["warnings"])
        self.assertIn("effective_days=1", joined)
        self.assertIn("min(profile_days, NEWS_MAX_AGE_DAYS)", joined)

    def test_update_appends_max_workers_warning(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "MAX_WORKERS", "value": "1"}],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        joined = " | ".join(response["warnings"])
        self.assertIn("MAX_WORKERS=1", joined)
        self.assertIn("reload_now=false", joined)

    def test_update_appends_mode_specific_startup_warnings(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {"key": "RUN_IMMEDIATELY", "value": "false"},
                {"key": "SCHEDULE_ENABLED", "value": "true"},
                {"key": "SCHEDULE_RUN_IMMEDIATELY", "value": "true"},
            ],
            reload_now=True,
        )

        self.assertTrue(response["success"])
        run_warning = next(
            warning
            for warning in response["warnings"]
            if "RUN_IMMEDIATELY 已写入 .env" in warning
        )
        schedule_warning = next(
            warning
            for warning in response["warnings"]
            if "SCHEDULE_ENABLED" in warning
        )
        schedule_run_warning = next(
            warning
            for warning in response["warnings"]
            if "SCHEDULE_RUN_IMMEDIATELY" in warning
        )

        self.assertIn("非 schedule 模式", run_warning)
        self.assertNotIn("以 schedule 模式", run_warning)
        self.assertIn("runtime scheduler", schedule_warning)
        self.assertIn("CLI schedule", schedule_warning)
        self.assertIn("SCHEDULE_RUN_IMMEDIATELY", schedule_run_warning)
        self.assertIn("不会因为本次保存启动、停止或重建 scheduler", schedule_run_warning)
        self.assertIn("以 schedule 模式重新启动后生效", schedule_run_warning)
        self.assertNotIn("它属于启动期单次运行配置", schedule_run_warning)

    def test_update_appends_schedule_time_runtime_rebind_warning(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "SCHEDULE_TIME", "value": "09:30"}],
            reload_now=True,
        )

        self.assertTrue(response["success"])
        schedule_time_warning = next(
            warning
            for warning in response["warnings"]
            if "SCHEDULE_TIME=09:30 已写入 .env" in warning
        )

        self.assertIn("已经以 schedule 模式运行", schedule_time_warning)
        self.assertIn("自动重建 daily job", schedule_time_warning)
        self.assertIn("不会启动 scheduler", schedule_time_warning)
        self.assertNotIn("重启当前进程", schedule_time_warning)
        self.assertNotIn("不会因为本次保存启动、停止或重建 scheduler", schedule_time_warning)

    def test_update_schedule_time_blank_warning_reports_effective_default(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "SCHEDULE_TIME", "value": "   "}],
            reload_now=True,
        )

        self.assertTrue(response["success"])
        self.assertTrue(
            any("SCHEDULE_TIME=18:00 已写入 .env" in warning for warning in response["warnings"]),
            response["warnings"],
        )

    def test_update_appends_webui_bind_restart_warning(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {"key": "WEBUI_HOST", "value": "0.0.0.0"},
                {"key": "WEBUI_PORT", "value": "18000"},
            ],
            reload_now=True,
        )

        self.assertTrue(response["success"])
        bind_warning = next(
            warning
            for warning in response["warnings"]
            if "WEBUI_HOST" in warning and "WEBUI_PORT" in warning
        )

        self.assertIn("启动期监听配置", bind_warning)
        self.assertIn("不会因为本次保存重新绑定监听地址或端口", bind_warning)
        self.assertIn("重启当前进程、Docker 容器或服务管理器后生效", bind_warning)

    def test_update_warns_when_runtime_model_references_are_cleared(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=deepseek",
            "LLM_DEEPSEEK_PROTOCOL=deepseek",
            "LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY=sk-test-value",
            "LLM_DEEPSEEK_MODELS=deepseek-chat,deepseek-v4-flash,deepseek-v4-pro",
            "LITELLM_MODEL=deepseek/deepseek-chat",
            "AGENT_LITELLM_MODEL=deepseek/deepseek-v4-pro",
            "LITELLM_FALLBACK_MODELS=deepseek/deepseek-v4-pro,deepseek/deepseek-chat,cohere/command-r-plus",
            "VISION_MODEL=deepseek/deepseek-v4-flash",
        )

        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {"key": "LLM_DEEPSEEK_MODELS", "value": "deepseek-v4-flash,deepseek-v4-pro"},
                {"key": "LITELLM_MODEL", "value": ""},
                {"key": "AGENT_LITELLM_MODEL", "value": ""},
                {"key": "LITELLM_FALLBACK_MODELS", "value": "deepseek/deepseek-v4-pro,cohere/command-r-plus"},
                {"key": "VISION_MODEL", "value": ""},
            ],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        warning = next(
            warning
            for warning in response["warnings"]
            if "已同步清理失效的运行时模型引用" in warning
        )
        self.assertIn("主要模型 / Agent 主要模型 / Vision 模型 / 备用模型中的失效项", warning)
        self.assertIn("桌面端导出备份", warning)

    def test_update_market_review_region_does_not_trigger_runtime_model_cleanup(self) -> None:
        litellm_config_path = Path(self.temp_dir.name) / "litellm_config.yaml"
        litellm_config_path.write_text("model_list: []\n", encoding="utf-8")

        self._rewrite_env(
            "MARKET_REVIEW_REGION=cn",
            "LITELLM_MODEL=openai/gpt-4o-mini",
            "AGENT_LITELLM_MODEL=openai/gpt-4o",
            "LITELLM_FALLBACK_MODELS=openai/gpt-4o-mini,openai/gpt-4o",
            "VISION_MODEL=openai/gpt-4o",
            f"LITELLM_CONFIG={litellm_config_path}",
            "LLM_CHANNELS=openai",
            "LLM_OPENAI_PROTOCOL=openai",
            "LLM_OPENAI_BASE_URL=https://llm-openai.example.com/v1",
            "LLM_OPENAI_API_KEYS=legacy-openai-secret",
            "LLM_OPENAI_MODELS=openai/gpt-4o-mini,openai/gpt-4o",
            "OPENAI_BASE_URL=https://openai.example.com/v1",
            "OPENAI_API_KEY=sk-openai",
            "OPENAI_MODEL=gpt-4.1",
            "ANTHROPIC_MODEL=claude-sonnet-4-6",
        )

        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "MARKET_REVIEW_REGION", "value": "both"}],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        self.assertIn("MARKET_REVIEW_REGION", response["updated_keys"])
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["MARKET_REVIEW_REGION"], "both")
        self.assertEqual(current_map["LITELLM_MODEL"], "openai/gpt-4o-mini")
        self.assertEqual(current_map["AGENT_LITELLM_MODEL"], "openai/gpt-4o")
        self.assertEqual(current_map["LITELLM_FALLBACK_MODELS"], "openai/gpt-4o-mini,openai/gpt-4o")
        self.assertEqual(current_map["VISION_MODEL"], "openai/gpt-4o")
        self.assertEqual(current_map["LITELLM_CONFIG"], str(litellm_config_path))
        self.assertEqual(current_map["LLM_CHANNELS"], "openai")
        self.assertEqual(current_map["LLM_OPENAI_PROTOCOL"], "openai")
        self.assertEqual(current_map["LLM_OPENAI_BASE_URL"], "https://llm-openai.example.com/v1")
        self.assertEqual(current_map["LLM_OPENAI_API_KEYS"], "legacy-openai-secret")
        self.assertEqual(current_map["LLM_OPENAI_MODELS"], "openai/gpt-4o-mini,openai/gpt-4o")
        self.assertEqual(current_map["OPENAI_BASE_URL"], "https://openai.example.com/v1")
        self.assertEqual(current_map["OPENAI_API_KEY"], "sk-openai")
        self.assertEqual(current_map["OPENAI_MODEL"], "gpt-4.1")
        self.assertEqual(current_map["ANTHROPIC_MODEL"], "claude-sonnet-4-6")
        self.assertFalse(
            any("已同步清理失效的运行时模型引用" in warning for warning in response["warnings"]),
            response["warnings"],
        )

    def test_update_market_review_region_accepts_comma_separated_regions(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "MARKET_REVIEW_REGION", "value": "cn,jp,us"}],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        self.assertIn("MARKET_REVIEW_REGION", response["updated_keys"])
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["MARKET_REVIEW_REGION"], "cn,jp,us")

    def test_import_env_market_review_region_accepts_comma_separated_regions(self) -> None:
        response = self.service.import_env(
            config_version=self.manager.get_config_version(),
            content="MARKET_REVIEW_REGION=jp,kr\n",
            reload_now=False,
        )

        self.assertTrue(response["success"])
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["MARKET_REVIEW_REGION"], "jp,kr")

    def test_import_desktop_env_restores_runtime_models_after_cleanup(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=deepseek",
            "LLM_DEEPSEEK_PROTOCOL=deepseek",
            "LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY=sk-test-value",
            "LLM_DEEPSEEK_MODELS=deepseek-chat,deepseek-v4-flash,deepseek-v4-pro",
            "LITELLM_MODEL=deepseek/deepseek-chat",
            "AGENT_LITELLM_MODEL=deepseek/deepseek-v4-pro",
            "LITELLM_FALLBACK_MODELS=deepseek/deepseek-v4-pro,deepseek/deepseek-chat,cohere/command-r-plus",
            "VISION_MODEL=deepseek/deepseek-v4-flash",
        )

        backup_content = self.service.export_desktop_env()["content"]
        pre_clear_map = dict(self.manager.read_config_map())

        clear_response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {"key": "LLM_DEEPSEEK_MODELS", "value": "deepseek-v4-flash"},
                {"key": "LITELLM_MODEL", "value": ""},
                {"key": "AGENT_LITELLM_MODEL", "value": ""},
                {"key": "LITELLM_FALLBACK_MODELS", "value": "deepseek/deepseek-v4-flash"},
                {"key": "VISION_MODEL", "value": ""},
            ],
            reload_now=False,
        )
        self.assertTrue(clear_response["success"])

        cleared_map = self.manager.read_config_map()
        self.assertEqual(cleared_map["LITELLM_MODEL"], "")
        self.assertEqual(cleared_map["AGENT_LITELLM_MODEL"], "")
        self.assertEqual(cleared_map["VISION_MODEL"], "")
        self.assertEqual(cleared_map["LITELLM_FALLBACK_MODELS"], "deepseek/deepseek-v4-flash")

        restore_payload = self.service.import_desktop_env(
            config_version=self.manager.get_config_version(),
            content=backup_content,
            reload_now=False,
        )
        self.assertTrue(restore_payload["success"])

        restored_map = self.manager.read_config_map()
        self.assertEqual(restored_map["LITELLM_MODEL"], pre_clear_map["LITELLM_MODEL"])
        self.assertEqual(restored_map["AGENT_LITELLM_MODEL"], pre_clear_map["AGENT_LITELLM_MODEL"])
        self.assertEqual(restored_map["VISION_MODEL"], pre_clear_map["VISION_MODEL"])
        self.assertEqual(restored_map["LITELLM_FALLBACK_MODELS"], pre_clear_map["LITELLM_FALLBACK_MODELS"])

    def test_import_desktop_env_restores_provider_and_base_url_after_provider_cleanup(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LITELLM_MODEL=openai/gpt-4o-mini",
            "OPENAI_MODEL=gpt-4.1",
            "OPENAI_BASE_URL=https://openai.example.com/v1",
            "OPENAI_API_KEY=legacy-openai-key",
        )

        backup_content = self.service.export_desktop_env()["content"]
        pre_clear_map = dict(self.manager.read_config_map())

        clear_response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {"key": "LITELLM_MODEL", "value": ""},
                {"key": "OPENAI_MODEL", "value": ""},
                {"key": "OPENAI_BASE_URL", "value": ""},
                {"key": "OPENAI_API_KEY", "value": ""},
            ],
            reload_now=False,
        )
        self.assertTrue(clear_response["success"])

        cleared_map = self.manager.read_config_map()
        self.assertEqual(cleared_map["LITELLM_MODEL"], "")
        self.assertEqual(cleared_map["OPENAI_MODEL"], "")
        self.assertEqual(cleared_map["OPENAI_BASE_URL"], "")
        self.assertEqual(cleared_map["OPENAI_API_KEY"], "")

        restore_payload = self.service.import_desktop_env(
            config_version=self.manager.get_config_version(),
            content=backup_content,
            reload_now=False,
        )
        self.assertTrue(restore_payload["success"])

        restored_map = self.manager.read_config_map()
        self.assertEqual(restored_map["LITELLM_MODEL"], pre_clear_map["LITELLM_MODEL"])
        self.assertEqual(restored_map["OPENAI_MODEL"], pre_clear_map["OPENAI_MODEL"])
        self.assertEqual(restored_map["OPENAI_BASE_URL"], pre_clear_map["OPENAI_BASE_URL"])
        self.assertEqual(restored_map["OPENAI_API_KEY"], pre_clear_map["OPENAI_API_KEY"])

    def test_validate_rejects_comma_only_api_key(self) -> None:
        """Whitespace/comma-only api_key must fail validation (P2: parsed-segment check)."""
        for bad_key in (",", " , ", "  ,  ,  "):
            with self.subTest(api_key=bad_key):
                validation = self.service.validate(
                    items=[
                        {"key": "LLM_CHANNELS", "value": "primary"},
                        {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                        {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                        {"key": "LLM_PRIMARY_API_KEY", "value": bad_key},
                    ]
                )
                self.assertFalse(validation["valid"])
                self.assertTrue(
                    any(issue["code"] == "missing_api_key" for issue in validation["issues"]),
                    f"Expected missing_api_key for api_key={bad_key!r}, got: {validation['issues']}",
                )

    def test_validate_rejects_ssrf_metadata_base_url(self) -> None:
        """base_url pointing to cloud metadata service must be blocked (P1: SSRF guard)."""
        for bad_url in (
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://100.100.100.200/latest/meta-data/",
        ):
            with self.subTest(base_url=bad_url):
                validation = self.service.validate(
                    items=[
                        {"key": "LLM_CHANNELS", "value": "primary"},
                        {"key": "LLM_PRIMARY_PROTOCOL", "value": "openai"},
                        {"key": "LLM_PRIMARY_MODELS", "value": "gpt-4o-mini"},
                        {"key": "LLM_PRIMARY_API_KEY", "value": "sk-test"},
                        {"key": "LLM_PRIMARY_BASE_URL", "value": bad_url},
                    ]
                )
                self.assertFalse(validation["valid"])
                self.assertTrue(
                    any(issue["code"] == "ssrf_blocked" for issue in validation["issues"]),
                    f"Expected ssrf_blocked for base_url={bad_url!r}, got: {validation['issues']}",
                )

    def test_validate_rejects_localhost_base_url_by_default(self) -> None:
        """Local LLM targets require an explicit outbound allowlist entry."""
        with patch.dict(os.environ, {"OUTBOUND_HTTP_ALLOWLIST": ""}, clear=False):
            validation = self.service.validate(
                items=[
                    {"key": "LLM_CHANNELS", "value": "local"},
                    {"key": "LLM_LOCAL_PROTOCOL", "value": "ollama"},
                    {"key": "LLM_LOCAL_MODELS", "value": "llama3"},
                    {"key": "LLM_LOCAL_API_KEY", "value": ""},
                    {"key": "LLM_LOCAL_BASE_URL", "value": "http://localhost:11434"},
                ]
            )
        self.assertTrue(any(issue["code"] == "ssrf_blocked" for issue in validation["issues"]))

    def test_validate_allows_allowlisted_localhost_base_url(self) -> None:
        with patch.dict(os.environ, {"OUTBOUND_HTTP_ALLOWLIST": "localhost:11434"}, clear=False):
            validation = self.service.validate(
                items=[
                    {"key": "LLM_CHANNELS", "value": "local"},
                    {"key": "LLM_LOCAL_PROTOCOL", "value": "ollama"},
                    {"key": "LLM_LOCAL_MODELS", "value": "llama3"},
                    {"key": "LLM_LOCAL_API_KEY", "value": ""},
                    {"key": "LLM_LOCAL_BASE_URL", "value": "http://localhost:11434"},
                ]
            )
        self.assertFalse(any(issue["code"] == "ssrf_blocked" for issue in validation["issues"]))
