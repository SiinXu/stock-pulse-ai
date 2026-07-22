# -*- coding: utf-8 -*-
"""System configuration model catalog, masking, and display contracts."""

from tests.system_config_service_test_support import (
    _SystemConfigServiceTestCaseBase,
    Any,
    Config,
    ConfigValidationError,
    Dict,
    GENERATION_ONLY_BACKEND_IDS,
    List,
    SimpleNamespace,
    SystemConfigService,
    contextmanager,
    json,
    logging,
    os,
    patch,
    requests,
)


class SystemConfigServiceTestCase(_SystemConfigServiceTestCaseBase):
    def test_available_models_returns_authoritative_routes_with_grouping(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=deepseek,openai",
            "LLM_DEEPSEEK_PROTOCOL=deepseek",
            "LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY=sk-ds",
            "LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro",
            "LLM_DEEPSEEK_ENABLED=true",
            "LLM_OPENAI_PROTOCOL=openai",
            "LLM_OPENAI_BASE_URL=https://api.openai.com/v1",
            "LLM_OPENAI_API_KEY=sk-oa",
            "LLM_OPENAI_MODELS=gpt-5.5",
            "LLM_OPENAI_ENABLED=true",
        )
        result = self.service.get_available_models()
        routes = [entry["route"] for entry in result["models"]]
        # The route set is authoritative — it matches the validator's source.
        effective = self.service._build_display_config_map(self.manager.read_config_map())
        expected = SystemConfigService._collect_llm_channel_models_from_map(effective)
        self.assertEqual(set(routes), set(expected))
        self.assertIn("deepseek/deepseek-v4-flash", routes)
        by_route = {entry["route"]: entry for entry in result["models"]}
        ds = by_route["deepseek/deepseek-v4-flash"]
        self.assertEqual(ds["connection"], "deepseek")
        self.assertEqual(ds["display"], "deepseek-v4-flash")
        self.assertEqual(by_route["openai/gpt-5.5"]["provider"], "openai")
        # Enriched authoritative fields: catalog provider id/label + connection id
        # + availability, so Web selectors group without a second provider list.
        self.assertEqual(ds["connection_id"], "deepseek")
        self.assertEqual(ds["provider_id"], "deepseek")
        self.assertEqual(ds["provider_label"], "DeepSeek 官方")
        self.assertTrue(ds["available"])

    def test_available_models_resolve_custom_connection_provider(self) -> None:
        # A connection named outside the catalog resolves to the custom provider.
        self._rewrite_env(
            "LLM_CHANNELS=my_proxy",
            "LLM_MY_PROXY_PROTOCOL=openai",
            "LLM_MY_PROXY_BASE_URL=https://proxy.example.com/v1",
            "LLM_MY_PROXY_API_KEY=sk-x",
            "LLM_MY_PROXY_MODELS=gpt-5.5",
            "LLM_MY_PROXY_ENABLED=true",
        )
        entry = self.service.get_available_models()["models"][0]
        self.assertEqual(entry["connection"], "my_proxy")
        self.assertEqual(entry["connection_id"], "my_proxy")
        self.assertEqual(entry["provider_id"], "custom")
        self.assertTrue(entry["available"])

    def test_legacy_provider_like_prefix_is_not_inferred_as_provider_identity(self) -> None:
        """A legacy Connection name prefix is insufficient evidence of Provider identity."""
        self._rewrite_env(
            "LLM_CHANNELS=openai2",
            "LLM_OPENAI2_PROTOCOL=openai",
            "LLM_OPENAI2_BASE_URL=https://proxy.example.com/v1",
            "LLM_OPENAI2_API_KEY=sk-x",
            "LLM_OPENAI2_MODELS=gpt-5.5",
            "LLM_OPENAI2_ENABLED=true",
        )

        entry = self.service.get_available_models()["models"][0]

        self.assertEqual(entry["connection_id"], "openai2")
        self.assertEqual(entry["provider_id"], "custom")

    def test_explicit_provider_identity_survives_renamed_connection_round_trip(self) -> None:
        response = self.service.update(
            config_version=self.manager.get_config_version(),
            reload_now=False,
            items=[
                {"key": "LLM_CHANNELS", "value": "openai_team"},
                {"key": "LLM_OPENAI_TEAM_PROVIDER", "value": "openai"},
                {"key": "LLM_OPENAI_TEAM_PROTOCOL", "value": "openai"},
                {"key": "LLM_OPENAI_TEAM_API_KEY", "value": "sk-team"},
                {"key": "LLM_OPENAI_TEAM_MODELS", "value": "gpt-5.5"},
                {"key": "LLM_OPENAI_TEAM_ENABLED", "value": "true"},
            ],
        )

        self.assertTrue(response["success"])
        item_map = {
            item["key"]: item
            for item in self.service.get_config(include_schema=True)["items"]
        }
        provider_item = item_map["LLM_OPENAI_TEAM_PROVIDER"]
        self.assertEqual(provider_item["value"], "openai")
        self.assertEqual(provider_item["schema"]["ui_placement"], "model_access")

        model = self.service.get_available_models()["models"][0]
        self.assertEqual(model["provider_id"], "openai")
        self.assertEqual(model["provider_label"], "OpenAI 官方")
        self.assertEqual(model["connection_id"], "openai_team")
        self.assertEqual(model["connection_name"], "openai_team")

    def test_update_rejects_unknown_explicit_provider_without_partial_write(self) -> None:
        before = self.env_path.read_bytes()

        with self.assertRaises(ConfigValidationError) as context:
            self.service.update(
                config_version=self.manager.get_config_version(),
                reload_now=False,
                items=[
                    {"key": "LLM_CHANNELS", "value": "research"},
                    {"key": "LLM_RESEARCH_PROVIDER", "value": "not-a-provider"},
                    {"key": "LLM_RESEARCH_PROTOCOL", "value": "openai"},
                    {"key": "LLM_RESEARCH_BASE_URL", "value": "https://models.example.com/v1"},
                    {"key": "LLM_RESEARCH_API_KEY", "value": "sk-research"},
                    {"key": "LLM_RESEARCH_MODELS", "value": "research-model"},
                    {"key": "LLM_RESEARCH_ENABLED", "value": "true"},
                ],
            )

        self.assertTrue(
            any(
                issue["key"] == "LLM_RESEARCH_PROVIDER"
                and issue["code"] == "invalid_provider"
                for issue in context.exception.issues
            ),
            context.exception.issues,
        )
        self.assertEqual(self.env_path.read_bytes(), before)

    def test_update_rejects_official_provider_protocol_mismatch_without_partial_write(self) -> None:
        before = self.env_path.read_bytes()

        with self.assertRaises(ConfigValidationError) as context:
            self.service.update(
                config_version=self.manager.get_config_version(),
                reload_now=False,
                items=[
                    {"key": "LLM_CHANNELS", "value": "writing_team"},
                    {"key": "LLM_WRITING_TEAM_PROVIDER", "value": "anthropic"},
                    {"key": "LLM_WRITING_TEAM_PROTOCOL", "value": "openai"},
                    {"key": "LLM_WRITING_TEAM_API_KEY", "value": "sk-writing"},
                    {"key": "LLM_WRITING_TEAM_MODELS", "value": "claude-test"},
                    {"key": "LLM_WRITING_TEAM_ENABLED", "value": "true"},
                ],
            )

        self.assertTrue(
            any(
                issue["key"] == "LLM_WRITING_TEAM_PROTOCOL"
                and issue["code"] == "provider_protocol_mismatch"
                for issue in context.exception.issues
            ),
            context.exception.issues,
        )
        self.assertEqual(self.env_path.read_bytes(), before)

    def test_multiple_connections_can_share_one_explicit_provider(self) -> None:
        items = [
            {"key": "LLM_CHANNELS", "value": "personal,work"},
            {"key": "LLM_PERSONAL_PROVIDER", "value": "openai"},
            {"key": "LLM_PERSONAL_PROTOCOL", "value": "openai"},
            {"key": "LLM_PERSONAL_API_KEY", "value": "sk-personal"},
            {"key": "LLM_PERSONAL_MODELS", "value": "gpt-personal"},
            {"key": "LLM_PERSONAL_ENABLED", "value": "true"},
            {"key": "LLM_WORK_PROVIDER", "value": "openai"},
            {"key": "LLM_WORK_PROTOCOL", "value": "openai"},
            {"key": "LLM_WORK_API_KEY", "value": "sk-work"},
            {"key": "LLM_WORK_MODELS", "value": "gpt-work"},
            {"key": "LLM_WORK_ENABLED", "value": "true"},
        ]

        validation = self.service.validate(items=items)
        self.assertTrue(validation["valid"], validation["issues"])
        self.service.update(
            config_version=self.manager.get_config_version(),
            items=items,
            reload_now=False,
        )

        models = self.service.get_available_models()["models"]
        self.assertEqual({model["provider_id"] for model in models}, {"openai"})
        self.assertEqual(
            {model["connection_name"] for model in models},
            {"personal", "work"},
        )

    def test_anthropic_and_gemini_each_support_multiple_connections(self) -> None:
        for provider_id, protocol in (
            ("anthropic", "anthropic"),
            ("gemini", "gemini"),
        ):
            with self.subTest(provider_id=provider_id):
                connection_ids = [f"{provider_id}_personal", f"{provider_id}_work"]
                items = [
                    {"key": "LLM_CHANNELS", "value": ",".join(connection_ids)},
                ]
                for index, connection_id in enumerate(connection_ids, start=1):
                    prefix = f"LLM_{connection_id.upper()}"
                    items.extend(
                        [
                            {"key": f"{prefix}_PROVIDER", "value": provider_id},
                            {"key": f"{prefix}_PROTOCOL", "value": protocol},
                            {"key": f"{prefix}_API_KEY", "value": f"sk-{provider_id}-{index}"},
                            {"key": f"{prefix}_MODELS", "value": f"model-{index}"},
                            {"key": f"{prefix}_ENABLED", "value": "true"},
                        ]
                    )

                validation = self.service.validate(items=items)
                self.assertTrue(validation["valid"], validation["issues"])
                models = self.service.get_available_models(items=items)["models"]
                self.assertEqual(
                    {model["provider_id"] for model in models},
                    {provider_id},
                )
                self.assertEqual(
                    {model["connection_name"] for model in models},
                    set(connection_ids),
                )

    def test_deleting_referenced_connection_is_rejected_by_validation(self) -> None:
        # Authoritative reference protection: a task model that references a
        # removed connection's route can no longer be resolved, so the save is
        # blocked (direct API calls cannot bypass this either).
        effective = {
            "LLM_CHANNELS": "deepseek",  # an "openai" connection was deleted
            "LLM_DEEPSEEK_PROTOCOL": "deepseek",
            "LLM_DEEPSEEK_API_KEY": "sk-ds",
            "LLM_DEEPSEEK_MODELS": "deepseek-v4-flash",
            "LLM_DEEPSEEK_ENABLED": "true",
            "LITELLM_MODEL": "openai/gpt-5.5",  # orphaned reference
        }
        issues = SystemConfigService._validate_llm_runtime_selection(effective)
        errors = {(i["key"], i["code"]) for i in issues if i["severity"] == "error"}
        self.assertIn(("LITELLM_MODEL", "unknown_model"), errors)
        # Re-assigning the task model to a still-available route clears the error.
        effective["LITELLM_MODEL"] = "deepseek/deepseek-v4-flash"
        cleared = SystemConfigService._validate_llm_runtime_selection(effective)
        self.assertFalse(
            any(i["key"] == "LITELLM_MODEL" and i["severity"] == "error" for i in cleared)
        )

    def test_update_reports_aggregated_model_in_use_without_partial_write(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=primary",
            "LLM_PRIMARY_PROVIDER=openai",
            "LLM_PRIMARY_PROTOCOL=openai",
            "LLM_PRIMARY_API_KEY=sk-primary",
            "LLM_PRIMARY_MODELS=used-model,spare-model",
            "LLM_PRIMARY_ENABLED=true",
            "LITELLM_MODEL=openai/used-model",
            "AGENT_LITELLM_MODEL=openai/used-model",
            "VISION_MODEL=openai/used-model",
            "LITELLM_FALLBACK_MODELS=openai/used-model,openai/spare-model",
        )
        before = self.env_path.read_bytes()

        with self.assertRaises(ConfigValidationError) as context:
            self.service.update(
                config_version=self.manager.get_config_version(),
                reload_now=False,
                items=[
                    {"key": "LLM_PRIMARY_MODELS", "value": "spare-model"},
                ],
            )

        in_use_issues = [
            issue for issue in context.exception.issues
            if issue["code"] == "model_in_use"
        ]
        self.assertEqual(len(in_use_issues), 1, context.exception.issues)
        issue = in_use_issues[0]
        self.assertEqual(issue["key"], "LLM_PRIMARY_MODELS")
        self.assertEqual(issue["details"]["route"], "openai/used-model")
        self.assertEqual(issue["details"]["connection_ids"], ["primary"])
        self.assertEqual(
            issue["details"]["referenced_by"],
            [
                {"task": "report", "key": "LITELLM_MODEL"},
                {"task": "agent", "key": "AGENT_LITELLM_MODEL"},
                {"task": "vision", "key": "VISION_MODEL"},
                {"task": "fallback", "key": "LITELLM_FALLBACK_MODELS"},
            ],
        )
        self.assertEqual(self.env_path.read_bytes(), before)

    def test_update_atomically_replaces_references_and_removes_model(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=primary",
            "LLM_PRIMARY_PROVIDER=openai",
            "LLM_PRIMARY_PROTOCOL=openai",
            "LLM_PRIMARY_API_KEY=sk-primary",
            "LLM_PRIMARY_MODELS=used-model,spare-model",
            "LLM_PRIMARY_ENABLED=true",
            "LITELLM_MODEL=openai/used-model",
            "AGENT_LITELLM_MODEL=openai/used-model",
            "VISION_MODEL=openai/used-model",
            "LITELLM_FALLBACK_MODELS=openai/used-model,openai/spare-model",
        )

        result = self.service.update(
            config_version=self.manager.get_config_version(),
            reload_now=False,
            items=[
                {"key": "LLM_PRIMARY_MODELS", "value": "spare-model"},
                {"key": "LITELLM_MODEL", "value": "openai/spare-model"},
                {"key": "AGENT_LITELLM_MODEL", "value": "openai/spare-model"},
                {"key": "VISION_MODEL", "value": "openai/spare-model"},
                {"key": "LITELLM_FALLBACK_MODELS", "value": "openai/spare-model"},
            ],
        )

        self.assertTrue(result["success"])
        saved = self.manager.read_config_map()
        self.assertEqual(saved["LLM_PRIMARY_MODELS"], "spare-model")
        self.assertEqual(saved["LITELLM_MODEL"], "openai/spare-model")
        self.assertEqual(saved["AGENT_LITELLM_MODEL"], "openai/spare-model")
        self.assertEqual(saved["VISION_MODEL"], "openai/spare-model")
        self.assertEqual(saved["LITELLM_FALLBACK_MODELS"], "openai/spare-model")

    def test_validate_keeps_existing_stale_model_as_unknown_model(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=primary",
            "LLM_PRIMARY_PROVIDER=openai",
            "LLM_PRIMARY_PROTOCOL=openai",
            "LLM_PRIMARY_API_KEY=sk-primary",
            "LLM_PRIMARY_MODELS=spare-model",
            "LLM_PRIMARY_ENABLED=true",
            "LITELLM_MODEL=openai/stale-model",
            "STOCK_LIST=600519",
        )

        validation = self.service.validate(
            items=[{"key": "STOCK_LIST", "value": "600519,000001"}],
        )

        self.assertTrue(
            any(
                issue["key"] == "LITELLM_MODEL"
                and issue["code"] == "unknown_model"
                for issue in validation["issues"]
            ),
            validation["issues"],
        )
        self.assertFalse(
            any(issue["code"] == "model_in_use" for issue in validation["issues"]),
            validation["issues"],
        )

    def test_known_provider_channel_names_derive_from_catalog(self) -> None:
        from src.services.system_config_service import known_llm_provider_channel_names
        from src.llm.provider_catalog import get_provider_catalog

        names = known_llm_provider_channel_names()
        expected = {
            str(entry["id"]).lower()
            for entry in get_provider_catalog()
            if not entry.get("is_custom")
        }
        self.assertEqual(names, expected)
        self.assertIn("openai", names)
        self.assertNotIn("custom", names)

    def test_available_models_excludes_disabled_connections(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=deepseek,openai",
            "LLM_DEEPSEEK_PROTOCOL=deepseek",
            "LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY=sk-ds",
            "LLM_DEEPSEEK_MODELS=deepseek-v4-flash",
            "LLM_DEEPSEEK_ENABLED=true",
            "LLM_OPENAI_PROTOCOL=openai",
            "LLM_OPENAI_MODELS=gpt-5.5",
            "LLM_OPENAI_ENABLED=false",
        )
        routes = [entry["route"] for entry in self.service.get_available_models()["models"]]
        self.assertIn("deepseek/deepseek-v4-flash", routes)
        self.assertNotIn("openai/gpt-5.5", routes)

    def test_first_run_wizard_deepseek_route_config_validates(self) -> None:
        items = self._wizard_channel_items(
            name="deepseek",
            provider_id="deepseek",
            protocol="deepseek",
            models="deepseek-v4-flash,deepseek-v4-pro",
            primary_route="deepseek/deepseek-v4-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
        )
        result = self.service.validate(items=items)
        self.assertTrue(result["valid"], result["issues"])

    def test_first_run_wizard_bare_model_name_is_rejected(self) -> None:
        # The wizard must emit a provider/model route; a bare model name is the
        # exact P1 regression that a mocked validate had hidden.
        items = self._wizard_channel_items(
            name="deepseek",
            provider_id="deepseek",
            protocol="deepseek",
            models="deepseek-v4-flash,deepseek-v4-pro",
            primary_route="deepseek-v4-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
        )
        result = self.service.validate(items=items)
        self.assertFalse(result["valid"])
        self.assertTrue(
            any(i["key"] == "LITELLM_MODEL" and i["code"] == "unknown_model" for i in result["issues"]),
            result["issues"],
        )

    def test_first_run_wizard_gemini_without_base_url_validates(self) -> None:
        items = self._wizard_channel_items(
            name="gemini",
            provider_id="gemini",
            protocol="gemini",
            models="gemini-3.1-pro-preview,gemini-3-flash-preview",
            primary_route="gemini/gemini-3.1-pro-preview",
            api_key="gm-key",
        )
        result = self.service.validate(items=items)
        self.assertTrue(result["valid"], result["issues"])

    def test_first_run_wizard_ollama_without_key_validates(self) -> None:
        items = self._wizard_channel_items(
            name="ollama",
            provider_id="ollama",
            protocol="ollama",
            models="llama3.2",
            primary_route="ollama/llama3.2",
            base_url="http://127.0.0.1:11434",
        )
        result = self.service.validate(items=items)
        self.assertTrue(result["valid"], result["issues"])

    def test_first_run_wizard_merges_existing_channels(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=openai",
            "LLM_OPENAI_PROTOCOL=openai",
            "LLM_OPENAI_BASE_URL=https://api.openai.com/v1",
            "LLM_OPENAI_API_KEY=sk-openai",
            "LLM_OPENAI_MODELS=gpt-5.5",
            "LLM_OPENAI_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-5.5",
        )
        items = self._wizard_channel_items(
            name="deepseek",
            provider_id="deepseek",
            protocol="deepseek",
            models="deepseek-v4-flash",
            primary_route="deepseek/deepseek-v4-flash",
            api_key="sk-test",
            base_url="https://api.deepseek.com",
            existing_channels=["openai"],
        )
        channels = next(i["value"] for i in items if i["key"] == "LLM_CHANNELS")
        self.assertEqual(channels, "openai,deepseek")
        result = self.service.validate(items=items)
        self.assertTrue(result["valid"], result["issues"])

    def test_first_run_wizard_adds_second_connection_with_explicit_provider(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=openai",
            "LLM_OPENAI_PROTOCOL=openai",
            "LLM_OPENAI_BASE_URL=https://api.openai.com/v1",
            "LLM_OPENAI_API_KEY=sk-openai",
            "LLM_OPENAI_MODELS=gpt-existing",
            "LLM_OPENAI_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-existing",
        )
        items = self._wizard_channel_items(
            name="openai2",
            provider_id="openai",
            protocol="openai",
            models="gpt-second",
            primary_route="openai/gpt-second",
            api_key="sk-openai-second",
            base_url="https://api.openai.com/v1",
            existing_channels=["openai"],
        )

        validation = self.service.validate(items=items)
        self.assertTrue(validation["valid"], validation["issues"])
        result = self.service.update(
            config_version=self.manager.get_config_version(),
            items=items,
            reload_now=False,
        )

        self.assertTrue(result["success"])
        saved = self.manager.read_config_map()
        self.assertEqual(saved["LLM_OPENAI2_PROVIDER"], "openai")
        model = next(
            model
            for model in self.service.get_available_models()["models"]
            if model["connection_id"] == "openai2"
        )
        self.assertEqual(model["provider_id"], "openai")
        self.assertEqual(model["connection_name"], "openai2")

    def test_get_config_masks_registered_sensitive_values(self) -> None:
        payload = self.service.get_config(include_schema=True)
        payload_without_schema = self.service.get_config(include_schema=False)
        items = {item["key"]: item for item in payload["items"]}
        items_without_schema = {
            item["key"]: item for item in payload_without_schema["items"]
        }

        self.assertIn("GEMINI_API_KEY", items)
        self.assertEqual(items["GEMINI_API_KEY"]["value"], payload["mask_token"])
        self.assertTrue(items["GEMINI_API_KEY"]["is_masked"])
        self.assertTrue(items["GEMINI_API_KEY"]["raw_value_exists"])
        self.assertTrue(items["GEMINI_API_KEY"]["schema"]["is_sensitive"])
        self.assertNotIn("secret-key-value", str(payload))
        self.assertEqual(
            items_without_schema["GEMINI_API_KEY"]["value"],
            payload_without_schema["mask_token"],
        )
        self.assertNotIn("secret-key-value", str(payload_without_schema))

    def test_get_config_notification_status_ignores_unrelated_advanced_values(self) -> None:
        self._rewrite_env(
            "WECHAT_WEBHOOK_URL=https://qyapi.example.com/hook",
            "WECHAT_MAX_BYTES=not-an-integer",
            "FEISHU_MAX_BYTES=also-not-an-integer",
        )

        payload = self.service.get_config(include_schema=False)

        self.assertEqual(payload["configured_notification_channels"], ["wechat"])

    def test_get_config_notification_status_honors_alternative_runtime_groups(self) -> None:
        self._rewrite_env(
            "FEISHU_APP_ID=cli_app",
            "FEISHU_APP_SECRET=app-secret",
            "FEISHU_CHAT_ID=oc_chat",
            "DISCORD_BOT_TOKEN=discord-token",
            "DISCORD_CHANNEL_ID=legacy-channel",
            "SLACK_BOT_TOKEN=slack-token",
            "SLACK_CHANNEL_ID=C123",
        )

        payload = self.service.get_config(include_schema=False)

        self.assertEqual(
            payload["configured_notification_channels"],
            ["feishu", "discord", "slack"],
        )

    def test_get_config_notification_status_rejects_browser_normalized_urls(self) -> None:
        self._rewrite_env(
            "NTFY_URL=https:ntfy.example.com/topic",
            "GOTIFY_URL=https:/gotify.example.com/base",
            "GOTIFY_TOKEN=gotify-token",
        )

        payload = self.service.get_config(include_schema=False)

        self.assertEqual(payload["configured_notification_channels"], [])

    def test_get_config_notification_status_uses_live_runtime_snapshot(self) -> None:
        """Saved values must not masquerade as already-reloaded runtime state."""
        self._rewrite_env(
            "DINGTALK_WEBHOOK_URL=https://saved.example.invalid/robot/send",
        )
        runtime = {"config": Config(stock_list=[])}
        self.service = SystemConfigService(
            manager=self.manager,
            runtime_config_provider=lambda: runtime["config"],
        )

        before_reload = self.service.get_config(include_schema=False)
        runtime["config"] = Config(
            stock_list=[],
            dingtalk_webhook_url="https://runtime.example.invalid/robot/send",
        )
        after_reload = self.service.get_config(include_schema=False)

        self.assertEqual(before_reload["configured_notification_channels"], [])
        self.assertEqual(after_reload["configured_notification_channels"], ["dingtalk"])

    def test_update_without_reload_keeps_previous_runtime_notification_status(self) -> None:
        runtime = {"config": Config(stock_list=[])}
        self.service = SystemConfigService(
            manager=self.manager,
            runtime_config_provider=lambda: runtime["config"],
        )

        result = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {
                    "key": "DINGTALK_WEBHOOK_URL",
                    "value": "https://saved.example.invalid/robot/send",
                }
            ],
            reload_now=False,
        )
        payload = self.service.get_config(include_schema=False)

        self.assertTrue(result["success"])
        self.assertFalse(result["reload_triggered"])
        self.assertEqual(payload["configured_notification_channels"], [])

    def test_default_runtime_provider_reads_latest_config_instance(self) -> None:
        first = Config(stock_list=[], dingtalk_webhook_url="https://first.example.invalid")
        second = Config(
            stock_list=[],
            discord_bot_token="discord-secret",
            discord_main_channel_id="legacy-channel",
        )
        self.service = SystemConfigService(manager=self.manager)

        with patch.object(Config, "_load_from_env", side_effect=[first, second]):
            Config.reset_instance()
            first_payload = self.service.get_config(include_schema=False)
            Config.reset_instance()
            second_payload = self.service.get_config(include_schema=False)

        self.assertEqual(first_payload["configured_notification_channels"], ["dingtalk"])
        self.assertEqual(second_payload["configured_notification_channels"], ["discord"])

    def test_runtime_notification_status_honors_process_only_and_legacy_config(self) -> None:
        self._rewrite_env("STOCK_LIST=600519")
        runtime_env = {
            "DINGTALK_WEBHOOK_URL": "https://process.example.invalid/robot/send",
            "DISCORD_BOT_TOKEN": "discord-secret",
            "DISCORD_CHANNEL_ID": "legacy-channel",
            "DISCORD_MAIN_CHANNEL_ID": "",
        }

        with patch.dict(os.environ, runtime_env, clear=False):
            Config.reset_instance()
            payload = self.service.get_config(include_schema=False)

        Config.reset_instance()
        self.assertEqual(
            payload["configured_notification_channels"],
            ["dingtalk", "discord"],
        )

    def test_get_config_masks_alphasift_install_spec(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "ALPHASIFT_INSTALL_SPEC=git+https://user:token@example.com/internal/alphasift.git",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["ALPHASIFT_INSTALL_SPEC"]["value"], payload["mask_token"])
        self.assertTrue(items["ALPHASIFT_INSTALL_SPEC"]["is_masked"])
        self.assertTrue(items["ALPHASIFT_INSTALL_SPEC"]["schema"]["is_sensitive"])

    def test_get_config_masks_hermes_secret_fields(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=hermes,alpha",
            "LLM_HERMES_API_KEY=sk-hermes-secret-value",
            "LLM_HERMES_API_KEYS=sk-old-secret-value",
            "LLM_HERMES_EXTRA_HEADERS={\"Authorization\":\"Bearer secret\"}",
            "LLM_ALPHA_EXTRA_HEADERS={\"Authorization\":\"Bearer alpha-secret\"}",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["LLM_HERMES_API_KEY"]["value"], payload["mask_token"])
        self.assertTrue(items["LLM_HERMES_API_KEY"]["is_masked"])
        self.assertEqual(items["LLM_HERMES_API_KEYS"]["value"], payload["mask_token"])
        self.assertTrue(items["LLM_HERMES_API_KEYS"]["is_masked"])
        self.assertEqual(items["LLM_HERMES_EXTRA_HEADERS"]["value"], payload["mask_token"])
        self.assertTrue(items["LLM_HERMES_EXTRA_HEADERS"]["is_masked"])
        self.assertEqual(items["LLM_ALPHA_EXTRA_HEADERS"]["value"], payload["mask_token"])
        self.assertTrue(items["LLM_ALPHA_EXTRA_HEADERS"]["is_masked"])
        self.assertTrue(items["LLM_ALPHA_EXTRA_HEADERS"]["schema"]["is_sensitive"])
        self.assertNotIn("alpha-secret", str(payload))

    def test_dynamic_extra_headers_require_valid_json_object_without_echoing_value(self) -> None:
        for value, expected_code in (
            ('{"Authorization":"Bearer private"', "invalid_json"),
            ('["Authorization", "Bearer private"]', "invalid_json_object"),
        ):
            with self.subTest(expected_code=expected_code):
                result = self.service.validate(
                    items=[{"key": "LLM_ALPHA_EXTRA_HEADERS", "value": value}],
                    mask_token="******",
                )

                issue = next(
                    item for item in result["issues"]
                    if item["key"] == "LLM_ALPHA_EXTRA_HEADERS"
                )
                self.assertEqual(issue["code"], expected_code)
                self.assertEqual(issue["actual"], "[REDACTED]")
                self.assertNotIn("private", str(result))

    def test_hermes_saved_secret_changed_port_does_not_send_request(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=hermes",
            "LLM_HERMES_PROTOCOL=openai",
            "LLM_HERMES_BASE_URL=http://127.0.0.1:8642/v1",
            "LLM_HERMES_API_KEY=sk-hermes-secret-value",
        )

        with patch("src.services.system_config_service.requests.Session") as session_cls:
            result = self.service.discover_llm_channel_models(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:9999/v1",
                api_key="******",
                models=["hermes-agent"],
                use_saved_secret=True,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "saved_secret_scope_mismatch")
        session_cls.assert_not_called()

    def test_hermes_saved_secret_runtime_env_cannot_rebind_endpoint(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=hermes",
            "LLM_HERMES_PROTOCOL=openai",
            "LLM_HERMES_BASE_URL=http://127.0.0.1:8642/v1",
            "LLM_HERMES_API_KEY=saved-secret-token",
        )

        with patch.dict(os.environ, {"LLM_HERMES_BASE_URL": "http://127.0.0.1:9999/v1"}, clear=False), \
             patch("src.services.system_config_service.requests.Session") as session_cls:
            result = self.service.discover_llm_channel_models(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:9999/v1",
                api_key="******",
                models=["hermes-agent"],
                use_saved_secret=True,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "saved_secret_scope_mismatch")
        self.assertNotIn("saved-secret-token", str(result))
        session_cls.assert_not_called()

    def test_hermes_model_discovery_uses_no_proxy_session(self) -> None:
        observed: Dict[str, Any] = {}

        class FakeSession:
            def __init__(self) -> None:
                self.trust_env = True

            def get(self, url: str, **kwargs: Any) -> Any:
                observed["url"] = url
                observed["trust_env"] = self.trust_env
                observed["headers"] = kwargs.get("headers") or {}
                return SimpleNamespace(
                    status_code=200,
                    ok=True,
                    json=lambda: {"data": [{"id": "hermes-agent"}]},
                )

            def close(self) -> None:
                observed["closed"] = True

        with patch("src.services.system_config_service.requests.Session", side_effect=FakeSession), \
             patch("src.services.system_config_service.requests.get") as requests_get:
            result = self.service.discover_llm_channel_models(
                name="hermes",
                protocol="openai",
                base_url="http://localhost:8642/v1",
                api_key="sk-hermes-secret-value",
                models=["hermes-agent"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(observed["url"], "http://127.0.0.1:8642/v1/models")
        self.assertFalse(observed["trust_env"])
        self.assertEqual(observed["headers"]["Authorization"], "Bearer sk-hermes-secret-value")
        self.assertTrue(observed["closed"])
        requests_get.assert_not_called()

    def test_hermes_model_discovery_invalid_url_fails_before_request(self) -> None:
        with patch("src.services.system_config_service.requests.Session") as session_cls:
            result = self.service.discover_llm_channel_models(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1?next=proxy",
                api_key="saved-secret-token",
                models=["hermes-agent"],
            )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "invalid_config")
        self.assertEqual(result["details"]["reason"], "invalid_hermes_url")
        self.assertNotIn("saved-secret-token", rendered)
        session_cls.assert_not_called()

    def test_hermes_model_discovery_http_error_redacts_non_sk_secret(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.trust_env = True

            def get(self, *_args: Any, **_kwargs: Any) -> Any:
                return SimpleNamespace(
                    status_code=500,
                    ok=False,
                    json=lambda: {"error": {"message": "upstream saw saved-secret-token"}},
                    text="upstream saw saved-secret-token",
                )

            def close(self) -> None:
                pass

        with patch("src.services.system_config_service.requests.Session", side_effect=FakeSession):
            result = self.service.discover_llm_channel_models(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key="saved-secret-token",
                models=["hermes-agent"],
            )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        self.assertFalse(result["success"])
        self.assertNotIn("saved-secret-token", rendered)
        self.assertNotIn("Bearer saved-secret-token", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_llm_result_redacts_raw_comma_secret_and_segments(self) -> None:
        raw_secret = "saved-secret-token,second-part"
        redactions = self.service._build_redaction_values(raw_secret)
        variants = [
            "Bearer saved-secret-token,second-part",
            "Bearer saved-secret-token, second-part",
            "Bearer saved-secret-token ,second-part",
            "Authorization: Bearer saved-secret-token,   second-part",
            "upstream saw saved-secret-token, second-part",
        ]

        result = self.service._build_llm_channel_result(
            success=False,
            message="; ".join(variants),
            error=" | ".join(variants),
            stage="model_discovery",
            error_code="network_error",
            retryable=False,
            details={
                "raw": raw_secret,
                "variants": variants,
                "first": "saved-secret-token",
                "second": "second-part",
            },
            capability_results={
                "json": {
                    "status": "failed",
                    "message": variants[1],
                    "details": {"echo": variants[3]},
                }
            },
            resolved_protocol="openai",
            models=[],
            latency_ms=None,
            redaction_values=redactions,
        )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        self.assertNotIn(raw_secret, rendered)
        for variant in variants:
            self.assertNotIn(variant, rendered)
        self.assertNotIn("saved-secret-token", rendered)
        self.assertNotIn("second-part", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_llm_result_recursively_redacts_models_details_and_capabilities(self) -> None:
        raw_secret = "saved-secret-token,second-part"
        redactions = self.service._build_redaction_values(raw_secret)

        details = self.service._sanitize_llm_details(
            {
                "items": [
                    {"message": "saved-secret-token"},
                    [{"nested": "Bearer saved-secret-token, second-part"}],
                ],
                "saved-secret-token": "second-part",
            },
            redaction_values=redactions,
        )
        result = self.service._build_llm_channel_result(
            success=False,
            message="upstream saw saved-secret-token, second-part",
            error="Authorization: Bearer saved-secret-token,   second-part",
            stage="model_discovery",
            error_code="network_error",
            retryable=False,
            details=details,
            resolved_protocol="openai",
            resolved_model="saved-secret-token",
            models=["saved-secret-token", ["second-part"]],
            capability_results={
                "json": {
                    "status": "failed",
                    "details": {"items": [{"message": "saved-secret-token"}]},
                }
            },
            redaction_values=redactions,
        )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        self.assertNotIn(raw_secret, rendered)
        self.assertNotIn("saved-secret-token, second-part", rendered)
        self.assertNotIn("saved-secret-token", rendered)
        self.assertNotIn("second-part", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_hermes_model_discovery_request_exception_redacts_response_and_logs(self) -> None:
        class FakeSession:
            def __init__(self) -> None:
                self.trust_env = True

            def get(self, *_args: Any, **_kwargs: Any) -> Any:
                raise requests.RequestException("proxy saw saved-secret-token")

            def close(self) -> None:
                pass

        with patch("src.services.system_config_service.requests.Session", side_effect=FakeSession), \
             self.assertLogs("src.services.system_config_service", level="WARNING") as logs:
            result = self.service.discover_llm_channel_models(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key="saved-secret-token",
                models=["hermes-agent"],
            )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        log_text = "\n".join(logs.output)
        self.assertFalse(result["success"])
        self.assertNotIn("saved-secret-token", rendered)
        self.assertNotIn("saved-secret-token", log_text)
        self.assertIn("[REDACTED]", rendered)
        self.assertIn("[REDACTED]", log_text)

    def test_hermes_request_exception_redacts_comma_secret_variants_from_logs(self) -> None:
        raw_secret = "saved-secret-token,second-part"
        variants = [
            "Bearer saved-secret-token,second-part",
            "Bearer saved-secret-token, second-part",
            "Bearer saved-secret-token ,second-part",
            "Authorization: Bearer saved-secret-token,   second-part",
            "upstream saw saved-secret-token, second-part",
        ]
        redactions = self.service._build_redaction_values(raw_secret)
        sanitized = self.service._sanitize_llm_error_text(
            " | ".join(variants),
            redaction_values=redactions,
        )
        with self.assertLogs("src.services.system_config_service", level="WARNING") as logs:
            logging.getLogger("src.services.system_config_service").warning(
                "LLM channel model discovery failed for hermes: %s",
                sanitized,
            )

        log_text = "\n".join(logs.output)
        self.assertNotIn(raw_secret, log_text)
        self.assertNotIn("saved-secret-token, second-part", log_text)
        self.assertNotIn("saved-secret-token", log_text)
        self.assertNotIn("second-part", log_text)
        for variant in variants:
            self.assertNotIn(variant, log_text)
        self.assertIn("[REDACTED]", log_text)

    def test_hermes_channel_test_invalid_url_fails_before_completion(self) -> None:
        with patch("src.services.system_config_service.open_hermes_no_proxy_client") as no_proxy_client, \
             patch("litellm.completion") as completion:
            result = self.service.test_llm_channel(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1#fragment",
                api_key="saved-secret-token",
                models=["hermes-agent"],
                capability_checks=["json"],
            )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "invalid_config")
        self.assertEqual(result["details"]["reason"], "invalid_hermes_url")
        self.assertEqual(result["capability_results"]["json"]["status"], "skipped")
        self.assertNotIn("saved-secret-token", rendered)
        no_proxy_client.assert_not_called()
        completion.assert_not_called()

    def test_hermes_runtime_only_masked_key_is_not_sent_for_channel_test(self) -> None:
        with patch("src.services.system_config_service.open_hermes_no_proxy_client") as no_proxy_client, \
             patch("litellm.completion") as completion:
            result = self.service.test_llm_channel(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key="******",
                models=["hermes-agent"],
                use_saved_secret=False,
                capability_checks=["json"],
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "runtime_secret_not_reusable")
        self.assertEqual(result["details"]["reason"], "runtime_secret_not_reusable")
        self.assertEqual(result["capability_results"]["json"]["status"], "skipped")
        no_proxy_client.assert_not_called()
        completion.assert_not_called()

    def test_hermes_masked_key_is_not_sent_for_model_discovery(self) -> None:
        with patch("src.services.system_config_service.requests.Session") as session_cls:
            result = self.service.discover_llm_channel_models(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key="******",
                models=["hermes-agent"],
                use_saved_secret=False,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "runtime_secret_not_reusable")
        self.assertEqual(result["details"]["reason"], "runtime_secret_not_reusable")
        session_cls.assert_not_called()

    def test_hermes_saved_literal_masked_key_is_not_reused(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=hermes",
            "LLM_HERMES_BASE_URL=http://127.0.0.1:8642/v1",
            "LLM_HERMES_API_KEY=******",
        )

        with patch("src.services.system_config_service.open_hermes_no_proxy_client") as no_proxy_client, \
             patch("litellm.completion") as completion:
            result = self.service.test_llm_channel(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key="******",
                models=["hermes-agent"],
                use_saved_secret=True,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "runtime_secret_not_reusable")
        no_proxy_client.assert_not_called()
        completion.assert_not_called()

    def test_hermes_channel_test_rejects_comma_api_key_before_outbound(self) -> None:
        raw_key = "key-a,key-b"
        with patch("src.services.system_config_service.open_hermes_no_proxy_client") as no_proxy_client, \
             patch("litellm.completion") as completion:
            result = self.service.test_llm_channel(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key=raw_key,
                models=["hermes-agent"],
                capability_checks=["json"],
            )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "invalid_config")
        self.assertEqual(result["details"]["reason"], "multiple_api_keys")
        self.assertNotIn(raw_key, rendered)
        self.assertNotIn("key-a", rendered)
        self.assertNotIn("key-b", rendered)
        no_proxy_client.assert_not_called()
        completion.assert_not_called()

    def test_hermes_model_discovery_rejects_comma_api_key_before_outbound(self) -> None:
        raw_key = "key-a,key-b"
        with patch("src.services.system_config_service.requests.Session") as session_cls:
            result = self.service.discover_llm_channel_models(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key=raw_key,
                models=["hermes-agent"],
            )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "invalid_config")
        self.assertEqual(result["details"]["reason"], "multiple_api_keys")
        self.assertNotIn(raw_key, rendered)
        self.assertNotIn("key-a", rendered)
        self.assertNotIn("key-b", rendered)
        session_cls.assert_not_called()

    def test_hermes_unsupported_capabilities_are_skipped_without_probe(self) -> None:
        no_proxy_calls: List[Dict[str, Any]] = []
        completion_models: List[str] = []

        @contextmanager
        def fake_no_proxy_openai_client(**kwargs: Any):
            no_proxy_calls.append(kwargs)
            yield object()

        def fake_completion(**kwargs: Any) -> Any:
            completion_models.append(str(kwargs.get("model") or ""))
            self.assertFalse(kwargs.get("stream"))
            self.assertIn("client", kwargs)
            self.assertNotIn("api_key", kwargs)
            self.assertNotIn("api_base", kwargs)
            return self._mock_completion_response("OK")

        with patch("src.services.system_config_service.open_hermes_no_proxy_client", fake_no_proxy_openai_client), \
             patch("litellm.completion", side_effect=fake_completion):
            result = self.service.test_llm_channel(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key="sk-hermes-secret-value",
                models=["hermes-agent"],
                capability_checks=["tools", "stream", "vision"],
            )

        self.assertTrue(result["success"])
        self.assertEqual(len(no_proxy_calls), 1)
        self.assertEqual(completion_models, ["openai/hermes-agent"])
        capability_results = result["capability_results"]
        self.assertEqual(set(capability_results), {"tools", "stream", "vision"})
        for capability in ("tools", "stream", "vision"):
            self.assertEqual(capability_results[capability]["status"], "skipped")
            self.assertEqual(capability_results[capability]["error_code"], "not_probed")

    def test_hermes_failure_redacts_non_sk_secret_from_response_and_logs(self) -> None:
        @contextmanager
        def fake_no_proxy_openai_client(**_kwargs: Any):
            yield object()

        def fake_completion(**_kwargs: Any) -> Any:
            raise RuntimeError("upstream echoed saved-secret-token")

        with patch("src.services.system_config_service.open_hermes_no_proxy_client", fake_no_proxy_openai_client), \
             patch("litellm.completion", side_effect=fake_completion), \
             self.assertLogs("src.services.system_config_service", level="WARNING") as logs:
            result = self.service.test_llm_channel(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key="saved-secret-token",
                models=["hermes-agent"],
            )

        self.assertFalse(result["success"])
        self.assertNotIn("saved-secret-token", str(result))
        self.assertNotIn("saved-secret-token", "\n".join(logs.output))

    def test_hermes_json_capability_exception_redacts_non_sk_secret(self) -> None:
        @contextmanager
        def fake_no_proxy_openai_client(**_kwargs: Any):
            yield object()

        completion_calls = 0

        def fake_completion(**_kwargs: Any) -> Any:
            nonlocal completion_calls
            completion_calls += 1
            if completion_calls == 1:
                return self._mock_completion_response("OK")
            raise RuntimeError("json capability saw saved-secret-token")

        with patch("src.services.system_config_service.open_hermes_no_proxy_client", fake_no_proxy_openai_client), \
             patch("litellm.completion", side_effect=fake_completion):
            result = self.service.test_llm_channel(
                name="hermes",
                protocol="openai",
                base_url="http://127.0.0.1:8642/v1",
                api_key="saved-secret-token",
                models=["hermes-agent"],
                capability_checks=["json"],
            )

        rendered = json.dumps(result, ensure_ascii=False, default=str)
        self.assertTrue(result["success"])
        self.assertEqual(result["capability_results"]["json"]["status"], "failed")
        self.assertNotIn("saved-secret-token", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_get_config_masks_llm_usage_hmac_secret(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_USAGE_HMAC_SECRET=telemetry-secret",
            "LLM_USAGE_HMAC_KEY_VERSION=test-v1",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["LLM_USAGE_HMAC_SECRET"]["value"], payload["mask_token"])
        self.assertTrue(items["LLM_USAGE_HMAC_SECRET"]["is_masked"])
        self.assertTrue(items["LLM_USAGE_HMAC_SECRET"]["schema"]["is_sensitive"])
        self.assertEqual(items["LLM_USAGE_HMAC_KEY_VERSION"]["value"], "test-v1")
        self.assertFalse(items["LLM_USAGE_HMAC_KEY_VERSION"]["is_masked"])

    def test_get_config_uses_switch_default_for_missing_report_model_toggle(self) -> None:
        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["REPORT_SHOW_LLM_MODEL"]["value"], "true")
        self.assertFalse(items["REPORT_SHOW_LLM_MODEL"]["raw_value_exists"])

        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "GEMINI_API_KEY=secret-key-value",
            "SCHEDULE_TIME=18:00",
            "LOG_LEVEL=INFO",
            "REPORT_SHOW_LLM_MODEL=false",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["REPORT_SHOW_LLM_MODEL"]["value"], "false")
        self.assertTrue(items["REPORT_SHOW_LLM_MODEL"]["raw_value_exists"])

    def test_get_config_preserves_manual_agent_codex_cli_value_without_schema_option(self) -> None:
        for backend in sorted(GENERATION_ONLY_BACKEND_IDS):
            with self.subTest(backend=backend):
                self._rewrite_env(
                    "STOCK_LIST=600519,000001",
                    f"AGENT_GENERATION_BACKEND={backend}",
                )

                payload = self.service.get_config(include_schema=True)
                items = {item["key"]: item for item in payload["items"]}
                agent_item = items["AGENT_GENERATION_BACKEND"]

                self.assertEqual(agent_item["value"], backend)
                self.assertNotIn(
                    backend,
                    {option["value"] for option in agent_item["schema"]["options"]},
                )

    def test_get_config_preserves_explicit_empty_switch_value(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "GEMINI_API_KEY=secret-key-value",
            "SCHEDULE_TIME=18:00",
            "LOG_LEVEL=INFO",
            "WEBHOOK_VERIFY_SSL=",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["WEBHOOK_VERIFY_SSL"]["value"], "")
        self.assertTrue(items["WEBHOOK_VERIFY_SSL"]["raw_value_exists"])

    def test_get_config_preserves_explicit_empty_report_show_llm_model_value(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "GEMINI_API_KEY=secret-key-value",
            "SCHEDULE_TIME=18:00",
            "LOG_LEVEL=INFO",
            "REPORT_SHOW_LLM_MODEL=",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["REPORT_SHOW_LLM_MODEL"]["value"], "")
        self.assertTrue(items["REPORT_SHOW_LLM_MODEL"]["raw_value_exists"])

    def test_get_config_uses_runtime_env_as_display_fallback(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LOG_LEVEL=INFO",
        )

        with patch.dict(
            os.environ,
            {
                "STOCK_LIST": "300750",
                "LITELLM_MODEL": "openai/gpt-5",
                "LLM_CHANNELS": "my_proxy",
                "LLM_MY_PROXY_BASE_URL": "https://proxy.example.com/v1",
                "LLM_MY_PROXY_MODELS": "gpt-5",
                "LLM_UNUSED_API_KEY": "sk-should-not-leak",
                "UNRELATED_API_KEY": "sk-should-not-leak",
            },
        ):
            payload = self.service.get_config(include_schema=True)
            raw_payload = self.service.get_config(include_schema=False)

        items = {item["key"]: item for item in payload["items"]}
        raw_items = {item["key"]: item for item in raw_payload["items"]}
        self.assertEqual(items["STOCK_LIST"]["value"], "600519")
        self.assertTrue(items["STOCK_LIST"]["raw_value_exists"])
        self.assertEqual(items["LITELLM_MODEL"]["value"], "openai/gpt-5")
        self.assertFalse(items["LITELLM_MODEL"]["raw_value_exists"])
        self.assertEqual(items["LLM_CHANNELS"]["value"], "my_proxy")
        self.assertFalse(items["LLM_CHANNELS"]["raw_value_exists"])
        self.assertEqual(items["LLM_MY_PROXY_BASE_URL"]["value"], "https://proxy.example.com/v1")
        self.assertFalse(items["LLM_MY_PROXY_BASE_URL"]["raw_value_exists"])
        self.assertEqual(items["LLM_MY_PROXY_MODELS"]["value"], "gpt-5")
        self.assertFalse(items["LLM_MY_PROXY_MODELS"]["raw_value_exists"])
        self.assertNotIn("LLM_UNUSED_API_KEY", items)
        self.assertNotIn("UNRELATED_API_KEY", items)
        self.assertNotIn("LLM_UNUSED_API_KEY", raw_items)
        self.assertNotIn("UNRELATED_API_KEY", raw_items)

    def test_get_config_runtime_env_fallback_does_not_persist_llm_fields_on_save(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LOG_LEVEL=INFO",
        )

        startup_env = {
            "LITELLM_MODEL": "openai/gpt-5",
            "LLM_CHANNELS": "my_proxy",
            "LLM_MY_PROXY_PROTOCOL": "openai",
            "LLM_MY_PROXY_BASE_URL": "https://proxy.example.com/v1",
            "LLM_MY_PROXY_API_KEYS": "sk-test-value",
            "LLM_MY_PROXY_MODELS": "openai/gpt-5",
        }
        with patch.dict(os.environ, startup_env, clear=False):
            payload_before = self.service.get_config(include_schema=True)
            items_before = {item["key"]: item for item in payload_before["items"]}
            self.assertEqual(items_before["LITELLM_MODEL"]["value"], "openai/gpt-5")
            self.assertFalse(items_before["LITELLM_MODEL"]["raw_value_exists"])
            self.assertEqual(
                items_before["LLM_MY_PROXY_BASE_URL"]["value"],
                "https://proxy.example.com/v1",
            )
            self.assertFalse(items_before["LLM_MY_PROXY_BASE_URL"]["raw_value_exists"])
            self.assertEqual(items_before["LLM_MY_PROXY_MODELS"]["value"], "openai/gpt-5")
            self.assertFalse(items_before["LLM_MY_PROXY_MODELS"]["raw_value_exists"])

            current_version = self.manager.get_config_version()
            response = self.service.update(
                config_version=current_version,
                items=[{"key": "STOCK_LIST", "value": "300750"}],
                reload_now=False,
            )
            self.assertTrue(response["success"])

            current_map = self.manager.read_config_map()
            self.assertEqual(current_map["STOCK_LIST"], "300750")
            self.assertNotIn("LITELLM_MODEL", current_map)
            self.assertNotIn("LLM_MY_PROXY_BASE_URL", current_map)
            self.assertNotIn("LLM_MY_PROXY_MODELS", current_map)

            payload_after = self.service.get_config(include_schema=True)
            items_after = {item["key"]: item for item in payload_after["items"]}
            self.assertEqual(items_after["LITELLM_MODEL"]["value"], "openai/gpt-5")
            self.assertFalse(items_after["LITELLM_MODEL"]["raw_value_exists"])
            self.assertEqual(
                items_after["LLM_MY_PROXY_BASE_URL"]["value"],
                "https://proxy.example.com/v1",
            )
            self.assertFalse(items_after["LLM_MY_PROXY_BASE_URL"]["raw_value_exists"])
            self.assertEqual(items_after["LLM_MY_PROXY_MODELS"]["value"], "openai/gpt-5")
            self.assertFalse(items_after["LLM_MY_PROXY_MODELS"]["raw_value_exists"])

    def test_runtime_env_fallback_does_not_override_saved_provider_and_base_url_settings(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LOG_LEVEL=INFO",
            "LITELLM_MODEL=openai/gpt-4o-mini",
            "OPENAI_MODEL=gpt-4.1",
        )

        with patch.dict(
            os.environ,
            {
                "OPENAI_BASE_URL": "https://runtime-openai.v1",
                "OPENAI_API_KEY": "runtime-openai-key",
            },
            clear=False,
        ):
            pre_save = self.service.get_config(include_schema=True)
            pre_save_items = {item["key"]: item for item in pre_save["items"]}

            self.assertEqual(pre_save_items["OPENAI_BASE_URL"]["value"], "https://runtime-openai.v1")
            self.assertFalse(pre_save_items["OPENAI_BASE_URL"]["raw_value_exists"])
            self.assertEqual(pre_save_items["OPENAI_API_KEY"]["value"], pre_save["mask_token"])
            self.assertTrue(pre_save_items["OPENAI_API_KEY"]["is_masked"])
            self.assertFalse(pre_save_items["OPENAI_API_KEY"]["raw_value_exists"])
            self.assertNotIn("runtime-openai-key", str(pre_save))
            self.assertEqual(pre_save_items["LITELLM_MODEL"]["value"], "openai/gpt-4o-mini")
            self.assertTrue(pre_save_items["LITELLM_MODEL"]["raw_value_exists"])
            self.assertEqual(pre_save_items["OPENAI_MODEL"]["value"], "gpt-4.1")
            self.assertTrue(pre_save_items["OPENAI_MODEL"]["raw_value_exists"])

            response = self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
                reload_now=False,
            )
            self.assertTrue(response["success"])

            current_map = self.manager.read_config_map()
            self.assertEqual(current_map["STOCK_LIST"], "300750")
            self.assertEqual(current_map["LITELLM_MODEL"], "openai/gpt-4o-mini")
            self.assertEqual(current_map["OPENAI_MODEL"], "gpt-4.1")
            self.assertNotIn("OPENAI_BASE_URL", current_map)
            self.assertNotIn("OPENAI_API_KEY", current_map)

    def test_validate_uses_runtime_injected_llm_channels_for_support_keys(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LOG_LEVEL=INFO",
        )

        with patch.dict(
            os.environ,
            {
                "LLM_CHANNELS": "my_proxy",
                "LLM_MY_PROXY_PROTOCOL": "openai",
                "LLM_MY_PROXY_API_KEYS": "sk-test-value",
                "LLM_MY_PROXY_BASE_URL": "https://proxy.example.com/v1",
                "LLM_MY_PROXY_MODELS": "openai/gpt-5",
            },
            clear=False,
        ):
            validation = self.service.validate(
                items=[{"key": "LLM_MY_PROXY_BASE_URL", "value": "not-a-url"}],
            )

        self.assertFalse(validation["valid"])
        self.assertTrue(
            any(
                issue["key"] == "LLM_MY_PROXY_BASE_URL" and issue["code"] == "invalid_url"
                for issue in validation["issues"]
            )
        )

    def test_get_config_switch_type_uses_runtime_env_display_fallback(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519",
            "LOG_LEVEL=INFO",
        )

        with patch.dict(os.environ, {"REPORT_SHOW_LLM_MODEL": "false"}, clear=False):
            payload = self.service.get_config(include_schema=True)

        items = {item["key"]: item for item in payload["items"]}
        self.assertEqual(items["REPORT_SHOW_LLM_MODEL"]["value"], "false")
        self.assertFalse(items["REPORT_SHOW_LLM_MODEL"]["raw_value_exists"])

    def test_get_config_with_schema_hides_unregistered_env_keys(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "DATABASE_PATH=./custom/stock_analysis.db",
            "SQLITE_WAL_ENABLED=true",
            "USE_PROXY=true",
            "PROXY_HOST=127.0.0.1",
            "PROXY_PORT=10809",
            "LOG_DIR=./logs",
        )

        payload = self.service.get_config(include_schema=True)
        items = {item["key"]: item for item in payload["items"]}

        self.assertNotIn("DATABASE_PATH", items)
        self.assertNotIn("SQLITE_WAL_ENABLED", items)
        self.assertNotIn("USE_PROXY", items)
        self.assertNotIn("PROXY_HOST", items)
        self.assertNotIn("PROXY_PORT", items)
        self.assertIn("LOG_DIR", items)
        self.assertEqual(items["LOG_DIR"]["schema"]["help_key"], "settings.system.LOG_DIR")

    def test_get_config_keeps_declared_llm_channel_support_keys_and_masks_secrets(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=deepseek,my_proxy",
            "LLM_DEEPSEEK_PROTOCOL=deepseek",
            "LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY=sk-test-value",
            "LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro",
            "LLM_MY_PROXY_PROTOCOL=openai",
            "LLM_MY_PROXY_API_KEYS=sk-key-1,sk-key-2",
            "LLM_MY_PROXY_MODELS=gpt-5.5",
            "LLM_UNUSED_API_KEY=sk-should-not-leak",
            "DATABASE_PATH=./custom/stock_analysis.db",
        )

        payload = self.service.get_config(include_schema=True)
        payload_without_schema = self.service.get_config(include_schema=False)
        items = {item["key"]: item for item in payload["items"]}
        items_without_schema = {
            item["key"]: item for item in payload_without_schema["items"]
        }

        self.assertIn("LLM_CHANNELS", items)
        self.assertEqual(items["LLM_DEEPSEEK_API_KEY"]["value"], payload["mask_token"])
        self.assertEqual(items["LLM_DEEPSEEK_MODELS"]["value"], "deepseek-v4-flash,deepseek-v4-pro")
        self.assertEqual(items["LLM_MY_PROXY_API_KEYS"]["value"], payload["mask_token"])
        self.assertEqual(items["LLM_MY_PROXY_MODELS"]["value"], "gpt-5.5")
        self.assertTrue(items["LLM_DEEPSEEK_API_KEY"]["is_masked"])
        self.assertTrue(items["LLM_MY_PROXY_API_KEYS"]["is_masked"])
        self.assertEqual(items["LLM_MY_PROXY_API_KEYS"]["schema"]["category"], "ai_model")
        self.assertEqual(
            items_without_schema["LLM_DEEPSEEK_API_KEY"]["value"],
            payload_without_schema["mask_token"],
        )
        self.assertEqual(
            items_without_schema["LLM_MY_PROXY_API_KEYS"]["value"],
            payload_without_schema["mask_token"],
        )
        self.assertNotIn("schema", items_without_schema["LLM_MY_PROXY_API_KEYS"])
        rendered = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("sk-test-value", rendered)
        self.assertNotIn("sk-key-1", rendered)
        self.assertNotIn("sk-key-2", rendered)
        self.assertNotIn("LLM_UNUSED_API_KEY", items)
        self.assertNotIn("DATABASE_PATH", items)

    def test_get_config_without_schema_keeps_unregistered_env_keys(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "DATABASE_PATH=./custom/stock_analysis.db",
            "SQLITE_WAL_ENABLED=true",
        )

        payload = self.service.get_config(include_schema=False)
        items = {item["key"]: item for item in payload["items"]}

        self.assertEqual(items["DATABASE_PATH"]["value"], "./custom/stock_analysis.db")
        self.assertEqual(items["SQLITE_WAL_ENABLED"]["value"], "true")
        self.assertNotIn("schema", items["DATABASE_PATH"])
