# -*- coding: utf-8 -*-
"""System configuration notification, probe, update, and documented selector contracts."""

from tests.system_config_service_test_support import (
    _SystemConfigServiceTestCaseBase,
    Any,
    Config,
    ConfigConflictError,
    Dict,
    Mock,
    Path,
    SimpleNamespace,
    SystemConfigService,
    json,
    os,
    patch,
    requests,
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

    @patch("src.notification_sender.wechat_sender.requests.post")
    def test_test_notification_channel_uses_temporary_items_without_persisting(self, mock_post) -> None:
        mock_post.return_value = self._mock_http_response(200, {"errcode": 0})

        with self._notification_test_env():
            before_instance = Config.get_instance()
            payload = self.service.test_notification_channel(
                channel="wechat",
                items=[{"key": "WECHAT_WEBHOOK_URL", "value": "https://qyapi.example.com/cgi-bin/webhook/send?key=secret"}],
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )
            self.assertIs(Config.get_instance(), before_instance)

        self.assertTrue(payload["success"])
        self.assertEqual(payload["attempts"][0]["latency_ms"] >= 0, True)
        self.assertIn("key=***", payload["attempts"][0]["target"])
        self.assertNotIn("WECHAT_WEBHOOK_URL", self.env_path.read_text(encoding="utf-8"))
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 3)

    def test_test_notification_channel_reports_missing_config(self) -> None:
        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="telegram",
                items=[{"key": "TELEGRAM_BOT_TOKEN", "value": "token"}],
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "config_missing")
        self.assertIn("TELEGRAM_CHAT_ID", payload["message"])

    def test_test_notification_channel_reports_nearest_feishu_app_bot_missing_key(self) -> None:
        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="feishu",
                items=[
                    {"key": "FEISHU_APP_ID", "value": "cli_xxx"},
                    {"key": "FEISHU_APP_SECRET", "value": "secret_xxx"},
                ],
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "config_missing")
        self.assertIn("FEISHU_CHAT_ID", payload["message"])
        self.assertNotIn("FEISHU_WEBHOOK_URL", payload["message"])

    def test_test_notification_channel_feishu_domain_draft_builds_isolated_config(self) -> None:
        captured: Dict[str, Any] = {}

        def fake_dispatch(**kwargs):
            captured.update(kwargs)
            return {
                "success": True,
                "message": "ok",
                "error_code": None,
                "stage": "notification_send",
                "retryable": False,
                "latency_ms": 0,
                "attempts": [],
            }

        with self._notification_test_env(), patch.object(
            SystemConfigService,
            "_dispatch_notification_test",
            side_effect=fake_dispatch,
        ):
            payload = self.service.test_notification_channel(
                channel="feishu",
                items=[
                    {"key": "FEISHU_APP_ID", "value": "cli_xxx"},
                    {"key": "FEISHU_APP_SECRET", "value": "secret_xxx"},
                    {"key": "FEISHU_CHAT_ID", "value": "oc_xxx"},
                    {"key": "FEISHU_DOMAIN", "value": "lark"},
                ],
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(captured["config"].feishu_domain, "lark")

    @patch("src.notification_sender.wechat_sender.requests.post")
    def test_test_notification_channel_skips_masked_secret_overwrite(self, mock_post) -> None:
        self._rewrite_env("WECHAT_WEBHOOK_URL=https://saved.example.com/hook?key=savedsecret")
        mock_post.return_value = self._mock_http_response(200, {"errcode": 0})

        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="wechat",
                items=[{"key": "WECHAT_WEBHOOK_URL", "value": "******"}],
                mask_token="******",
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(mock_post.call_args[0][0], "https://saved.example.com/hook?key=savedsecret")

    @patch("src.notification_sender.custom_webhook_sender.requests.post")
    def test_test_notification_channel_returns_custom_webhook_attempts(self, mock_post) -> None:
        mock_post.side_effect = [
            self._mock_http_response(500),
            self._mock_http_response(200),
        ]

        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="custom",
                items=[
                    {
                        "key": "CUSTOM_WEBHOOK_URLS",
                        "value": (
                            "https://example.com/robot/send?access_token=first,"
                            "https://example.com/verylongsecrettoken1234567890"
                        ),
                    }
                ],
                title="Test title",
                content="hello",
                timeout_seconds=4,
            )

        self.assertTrue(payload["success"])
        self.assertIn("部分成功", payload["message"])
        self.assertIn("1/2", payload["message"])
        self.assertEqual(len(payload["attempts"]), 2)
        self.assertFalse(payload["attempts"][0]["success"])
        self.assertTrue(payload["attempts"][1]["success"])
        self.assertIn("access_token=***", payload["attempts"][0]["target"])
        self.assertNotIn("verylongsecrettoken1234567890", payload["attempts"][1]["target"])
        self.assertNotIn("access_token=first", str(payload))
        self.assertEqual(mock_post.call_args_list[0].kwargs["timeout"], 4)

    @patch("src.notification_sender.custom_webhook_sender.requests.post")
    def test_test_notification_channel_custom_webhook_all_failures_are_retryable(self, mock_post) -> None:
        mock_post.side_effect = [
            self._mock_http_response(500),
            self._mock_http_response(429),
        ]

        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="custom",
                items=[
                    {
                        "key": "CUSTOM_WEBHOOK_URLS",
                        "value": (
                            "https://example.com/robot/send?access_token=first,"
                            "https://example.com/robot/send?token=second"
                        ),
                    }
                ],
                title="Test title",
                content="hello",
                timeout_seconds=4,
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "send_failed")
        self.assertTrue(payload["retryable"])
        self.assertIn("失败", payload["message"])
        self.assertIn("0/2", payload["message"])
        self.assertEqual(len(payload["attempts"]), 2)
        self.assertTrue(all(attempt["retryable"] for attempt in payload["attempts"]))
        self.assertNotIn("access_token=first", str(payload))
        self.assertNotIn("token=second", str(payload))

    @patch("src.notification_sender.ntfy_sender.requests.post")
    def test_test_notification_channel_supports_ntfy_and_masks_topic_target(self, mock_post) -> None:
        mock_post.return_value = self._mock_http_response(200)

        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="ntfy",
                items=[
                    {"key": "NTFY_URL", "value": "https://ntfy.sh/private-topic"},
                    {"key": "NTFY_TOKEN", "value": "secret-token"},
                ],
                title="Test title",
                content="hello",
                timeout_seconds=4,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(mock_post.call_args.args[0], "https://ntfy.sh")
        self.assertEqual(mock_post.call_args.kwargs["json"]["topic"], "private-topic")
        self.assertEqual(mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 4)
        self.assertIn("https://ntfy.sh/***", payload["attempts"][0]["target"])
        self.assertNotIn("private-topic", str(payload))
        self.assertNotIn("NTFY_URL", self.env_path.read_text(encoding="utf-8"))

    @patch("src.notification_sender.ntfy_sender.requests.post")
    def test_test_notification_channel_rejects_ntfy_url_without_topic(self, mock_post) -> None:
        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="ntfy",
                items=[{"key": "NTFY_URL", "value": "https://ntfy.sh"}],
                title="Test title",
                content="hello",
                timeout_seconds=4,
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "config_invalid")
        self.assertEqual(payload["stage"], "config_validation")
        self.assertIn("NTFY_URL", payload["message"])
        mock_post.assert_not_called()

    @patch("src.notification_sender.gotify_sender.requests.post")
    def test_test_notification_channel_supports_gotify_and_keeps_token_out_of_url(self, mock_post) -> None:
        mock_post.return_value = self._mock_http_response(200)

        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="gotify",
                items=[
                    {"key": "GOTIFY_URL", "value": "https://gotify.example"},
                    {"key": "GOTIFY_TOKEN", "value": "secret-token"},
                ],
                title="Test title",
                content="hello",
                timeout_seconds=4,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(mock_post.call_args.args[0], "https://gotify.example/message")
        self.assertEqual(mock_post.call_args.kwargs["headers"]["X-Gotify-Key"], "secret-token")
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 4)
        self.assertEqual(payload["attempts"][0]["target"], "https://gotify.example")
        self.assertNotIn("secret-token", str(payload))
        self.assertNotIn("GOTIFY_URL", self.env_path.read_text(encoding="utf-8"))

    @patch("src.notification_sender.gotify_sender.requests.post")
    def test_test_notification_channel_rejects_gotify_message_endpoint(self, mock_post) -> None:
        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="gotify",
                items=[
                    {"key": "GOTIFY_URL", "value": "https://gotify.example/message"},
                    {"key": "GOTIFY_TOKEN", "value": "secret-token"},
                ],
                title="Test title",
                content="hello",
                timeout_seconds=4,
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "config_invalid")
        self.assertEqual(payload["stage"], "config_validation")
        self.assertIn("GOTIFY_URL", payload["message"])
        mock_post.assert_not_called()

    @patch(
        "src.notification_sender.WechatSender.send_to_wechat",
        side_effect=requests.exceptions.Timeout(
            "timeout for https://qyapi.example.com/cgi-bin/webhook/send?key=secret token=abc123"
        ),
    )
    def test_test_notification_channel_classifies_escaped_timeout(self, _mock_send) -> None:
        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="wechat",
                items=[
                    {
                        "key": "WECHAT_WEBHOOK_URL",
                        "value": "https://qyapi.example.com/cgi-bin/webhook/send?key=secret",
                    }
                ],
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "timeout")
        self.assertTrue(payload["retryable"])
        self.assertEqual(payload["attempts"][0]["error_code"], "timeout")
        self.assertIn("key=***", payload["attempts"][0]["target"])
        self.assertNotIn("key=secret", str(payload))
        self.assertNotIn("abc123", str(payload))

    @patch("src.notification_sender.telegram_sender.requests.post")
    def test_test_notification_channel_masks_short_sensitive_target(self, mock_post) -> None:
        mock_post.return_value = self._mock_http_response(200, {"ok": True})

        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="telegram",
                items=[
                    {"key": "TELEGRAM_BOT_TOKEN", "value": "tok123"},
                    {"key": "TELEGRAM_CHAT_ID", "value": "chat-id"},
                ],
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["attempts"][0]["target"], "***")
        self.assertNotIn("tok123", str(payload))

    @patch("src.notification_sender.wechat_sender.requests.post")
    def test_test_notification_channel_rejects_url_userinfo(self, mock_post) -> None:
        mock_post.return_value = self._mock_http_response(200, {"errcode": 0})

        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="wechat",
                items=[
                    {
                        "key": "WECHAT_WEBHOOK_URL",
                        "value": "https://user:password@example.com/cgi-bin/webhook/send?key=secret",
                    }
                ],
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )

        self.assertFalse(payload["success"])
        mock_post.assert_not_called()
        self.assertNotIn("user", str(payload))
        self.assertNotIn("password", str(payload))
        self.assertNotIn("key=secret", str(payload))

    @patch("src.notification_sender.discord_sender.requests.post")
    def test_test_notification_channel_prefers_discord_main_channel_alias(self, mock_post) -> None:
        mock_post.return_value = self._mock_http_response(200)

        with self._notification_test_env():
            payload = self.service.test_notification_channel(
                channel="discord",
                items=[
                    {"key": "DISCORD_BOT_TOKEN", "value": "bot-token"},
                    {"key": "DISCORD_MAIN_CHANNEL_ID", "value": "main-channel"},
                    {"key": "DISCORD_CHANNEL_ID", "value": "legacy-channel"},
                ],
                title="Test title",
                content="hello",
                timeout_seconds=3,
            )

        self.assertTrue(payload["success"])
        self.assertIn("/channels/main-channel/messages", mock_post.call_args[0][0])

    @patch("litellm.completion")
    def test_test_llm_channel_returns_success_payload(self, mock_completion) -> None:
        mock_completion.return_value = type(
            "MockResponse",
            (),
            {
                "choices": [type("Choice", (), {"message": type("Message", (), {"content": "OK"})()})()],
            },
        )()

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.deepseek.com/v1",
            api_key="sk-test-value",
            models=["deepseek-chat"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_protocol"], "openai")
        self.assertEqual(payload["resolved_model"], "openai/deepseek-chat")
        self.assertEqual(payload["capability_results"], {})
        self.assertEqual(mock_completion.call_count, 1)

    @patch("litellm.completion")
    def test_test_llm_channel_falls_back_to_message_content_when_content_blocks_empty(
        self,
        mock_completion,
    ) -> None:
        mock_completion.return_value = type(
            "MockResponse",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "content_blocks": [],
                            "message": type("Message", (), {"content": "OK"})(),
                        },
                    )(),
                ]
            },
        )()

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.deepseek.com/v1",
            api_key="sk-test-value",
            models=["deepseek-chat"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_model"], "openai/deepseek-chat")

    @patch("litellm.completion")
    def test_test_llm_channel_allows_ollama_prefix_without_explicit_protocol(self, mock_completion) -> None:
        mock_completion.return_value = type(
            "MockResponse",
            (),
            {
                "choices": [type("Choice", (), {"message": type("Message", (), {"content": "OK"})()})()],
            },
        )()

        payload = self.service.test_llm_channel(
            name="lab",
            protocol="",
            base_url="http://localhost:11434/v1",
            api_key="",
            models=["ollama/llama3"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_protocol"], "ollama")
        self.assertEqual(payload["resolved_model"], "ollama/llama3")

    @patch("litellm.completion")
    def test_test_llm_channel_normalizes_kimi_temperature(self, mock_completion) -> None:
        mock_completion.return_value = type(
            "MockResponse",
            (),
            {
                "choices": [type("Choice", (), {"message": type("Message", (), {"content": "OK"})()})()],
            },
        )()

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.moonshot.cn/v1",
            api_key="sk-test-value",
            models=["kimi-k2.6"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_model"], "openai/kimi-k2.6")
        self.assertEqual(mock_completion.call_args.kwargs["temperature"], 1.0)

    def test_update_switching_to_kimi_does_not_rewrite_saved_llm_temperature(self) -> None:
        self._rewrite_env(
            "LITELLM_MODEL=openai/gpt-4o-mini",
            "LLM_TEMPERATURE=0.42",
        )

        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "LITELLM_MODEL", "value": "openai/kimi-k2.6"}],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["LITELLM_MODEL"], "openai/kimi-k2.6")
        self.assertEqual(current_map["LLM_TEMPERATURE"], "0.42")

    def test_update_runtime_model_cleanup_does_not_rewrite_temperature(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=deepseek",
            "LLM_DEEPSEEK_PROTOCOL=deepseek",
            "LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com",
            "LLM_DEEPSEEK_API_KEY=sk-test-value",
            "LLM_DEEPSEEK_MODELS=deepseek-chat,deepseek-v4-flash",
            "LITELLM_MODEL=deepseek/deepseek-chat",
            "AGENT_LITELLM_MODEL=deepseek/deepseek-v4-flash",
            "LLM_TEMPERATURE=0.42",
            "LITELLM_FALLBACK_MODELS=deepseek/deepseek-v4-flash,cohere/command-r-plus",
            "VISION_MODEL=deepseek/deepseek-chat",
        )

        response = self.service.update(
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

        self.assertTrue(response["success"])
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["LLM_TEMPERATURE"], "0.42")
        self.assertEqual(current_map["LITELLM_MODEL"], "")
        self.assertEqual(current_map["AGENT_LITELLM_MODEL"], "")
        self.assertEqual(current_map["VISION_MODEL"], "")
        self.assertEqual(
            current_map["LITELLM_FALLBACK_MODELS"],
            "deepseek/deepseek-v4-flash",
        )

    def test_update_warns_when_clearing_unsupported_hermes_keys(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LLM_CHANNELS=hermes",
            "LLM_HERMES_PROTOCOL=openai",
            "LLM_HERMES_BASE_URL=http://127.0.0.1:8642/v1",
            "LLM_HERMES_API_KEY=sk-hermes-test-value",
            "LLM_HERMES_API_KEYS=sk-old-a,sk-old-b",
            'LLM_HERMES_EXTRA_HEADERS={"X":"Y"}',
            "LLM_HERMES_MODELS=hermes-agent",
        )

        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {"key": "LLM_HERMES_API_KEYS", "value": ""},
                {"key": "LLM_HERMES_EXTRA_HEADERS", "value": ""},
            ],
            reload_now=False,
        )

        self.assertTrue(response["success"])
        joined = " | ".join(response["warnings"])
        self.assertIn("Hermes Phase 3 不支持", joined)
        self.assertIn("LLM_HERMES_API_KEYS", joined)
        self.assertIn("LLM_HERMES_EXTRA_HEADERS", joined)
        self.assertIn("LLM_HERMES_API_KEY", joined)
        self.assertIn(".env 备份", joined)
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["LLM_HERMES_API_KEYS"], "")
        self.assertEqual(current_map["LLM_HERMES_EXTRA_HEADERS"], "")

    @patch("litellm.completion")
    def test_test_llm_channel_does_not_persist_normalized_kimi_temperature(self, mock_completion) -> None:
        self._rewrite_env("LLM_TEMPERATURE=0.42")
        mock_completion.return_value = type(
            "MockResponse",
            (),
            {
                "choices": [type("Choice", (), {"message": type("Message", (), {"content": "OK"})()})()],
            },
        )()

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.moonshot.cn/v1",
            api_key="sk-test-value",
            models=["kimi-k2.6"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(mock_completion.call_args.kwargs["temperature"], 1.0)
        self.assertEqual(self.manager.read_config_map()["LLM_TEMPERATURE"], "0.42")

    @patch("litellm.completion")
    def test_test_llm_channel_omits_temperature_for_gpt5_family(self, mock_completion) -> None:
        mock_completion.return_value = type(
            "MockResponse",
            (),
            {
                "choices": [type("Choice", (), {"message": type("Message", (), {"content": "OK"})()})()],
            },
        )()

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-test-value",
            models=["gpt5.5-ferr"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_model"], "openai/gpt5.5-ferr")
        self.assertNotIn("temperature", mock_completion.call_args.kwargs)

    @patch("litellm.completion")
    @patch("src.services.system_config_service.Config._load_from_env")
    def test_test_llm_channel_recovers_from_unsupported_temperature(
        self,
        mock_load_config,
        mock_completion,
    ) -> None:
        from src.llm.generation_params import clear_litellm_generation_param_recovery_cache

        clear_litellm_generation_param_recovery_cache()
        mock_load_config.return_value = SimpleNamespace(llm_temperature=0.42)
        mock_completion.side_effect = [
            RuntimeError("Unsupported parameter: temperature is not supported"),
            type(
                "MockResponse",
                (),
                {
                    "choices": [type("Choice", (), {"message": type("Message", (), {"content": "OK"})()})()],
                },
            )(),
        ]

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-test-value",
            models=["custom-temp-locked-settings"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(mock_completion.call_args_list[0].kwargs["temperature"], 0.42)
        self.assertNotIn("temperature", mock_completion.call_args_list[1].kwargs)

    @patch("litellm.completion")
    @patch("src.services.system_config_service.Config._load_from_env")
    def test_test_llm_channel_uses_runtime_temperature_for_non_kimi_models(
        self,
        mock_load_config,
        mock_completion,
    ) -> None:
        mock_load_config.return_value = SimpleNamespace(llm_temperature=0.42)
        mock_completion.return_value = type(
            "MockResponse",
            (),
            {
                "choices": [type("Choice", (), {"message": type("Message", (), {"content": "OK"})()})()],
            },
        )()

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-test-value",
            models=["gpt-4o-mini"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_model"], "openai/gpt-4o-mini")
        self.assertEqual(mock_completion.call_args.kwargs["temperature"], 0.42)

    @patch("litellm.completion")
    def test_test_llm_channel_classifies_common_failure_scenarios(self, mock_completion) -> None:
        cases = [
            (PermissionError("401 Unauthorized Bearer sk-secret-value"), "auth", "chat_completion", False),
            (TimeoutError("request timed out"), "timeout", "chat_completion", True),
            (Exception("404 model not found: gpt-4o-mini"), "model_not_found", "chat_completion", False),
            (Exception("The model `gpt-4o-mini` does not exist"), "model_not_found", "chat_completion", False),
            (Exception("404 Not Found: page not found"), "network_error", "chat_completion", False),
            (
                type("MockResponse", (), {"choices": [type("Choice", (), {"message": type("Message", (), {"content": ""})()})()]})(),
                "empty_response",
                "response_parse",
                False,
            ),
            (object(), "format_error", "response_parse", False),
        ]

        for response_or_exc, error_code, stage, retryable in cases:
            with self.subTest(error_code=error_code):
                mock_completion.reset_mock()
                if isinstance(response_or_exc, Exception):
                    mock_completion.side_effect = response_or_exc
                    mock_completion.return_value = None
                else:
                    mock_completion.side_effect = None
                    mock_completion.return_value = response_or_exc

                payload = self.service.test_llm_channel(
                    name="primary",
                    protocol="openai",
                    base_url="https://api.example.com/v1",
                    api_key="sk-secret-value",
                    models=["gpt-4o-mini"],
                )

                self.assertFalse(payload["success"])
                self.assertEqual(payload["error_code"], error_code)
                self.assertEqual(payload["stage"], stage)
                self.assertEqual(payload["retryable"], retryable)
                if error_code == "auth":
                    self.assertNotIn("sk-secret-value", payload["error"])
                if error_code == "format_error":
                    self.assertIn("choices", payload["error"])

    @patch("litellm.completion")
    def test_test_llm_channel_marks_requested_capabilities_skipped_when_base_fails(self, mock_completion) -> None:
        mock_completion.side_effect = PermissionError("401 Unauthorized Bearer sk-secret-value")

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-secret-value",
            models=["gpt-4o-mini"],
            capability_checks=["json", "tools"],
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "auth")
        self.assertEqual(payload["details"]["reason"], "api_key_rejected")
        self.assertEqual(payload["capability_results"]["json"]["status"], "skipped")
        self.assertEqual(payload["capability_results"]["tools"]["details"]["reason"], "base_test_failed")
        self.assertEqual(mock_completion.call_count, 1)

    @patch("litellm.completion")
    def test_test_llm_channel_runs_json_and_tools_capability_checks(self, mock_completion) -> None:
        tool_call = SimpleNamespace(function=SimpleNamespace(name="dsa_probe_echo"))
        mock_completion.side_effect = [
            self._mock_completion_response("OK"),
            self._mock_completion_response('{"status":"ok"}'),
            self._mock_completion_response("", tool_calls=[tool_call]),
        ]

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-test-value",
            models=["gpt-4o-mini"],
            capability_checks=["tools", "json", "tools"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(list(payload["capability_results"].keys()), ["json", "tools"])
        self.assertEqual(payload["capability_results"]["json"]["status"], "passed")
        self.assertEqual(payload["capability_results"]["tools"]["status"], "passed")
        self.assertEqual(mock_completion.call_count, 3)
        self.assertEqual(mock_completion.call_args_list[1].kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(mock_completion.call_args_list[2].kwargs["tool_choice"]["function"]["name"], "dsa_probe_echo")

    @patch("litellm.completion")
    def test_test_llm_channel_reports_json_capability_failures(self, mock_completion) -> None:
        mock_completion.side_effect = [
            self._mock_completion_response("OK"),
            self._mock_completion_response("not json"),
        ]

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-test-value",
            models=["gpt-4o-mini"],
            capability_checks=["json"],
        )

        self.assertTrue(payload["success"])
        result = payload["capability_results"]["json"]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "format_error")
        self.assertEqual(result["details"]["reason"], "non_json")

    @patch("litellm.completion")
    def test_test_llm_channel_runs_stream_capability_check_and_closes_stream(self, mock_completion) -> None:
        class _Stream:
            def __init__(self):
                self.closed = False

            def __iter__(self):
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="OK"))])

            def close(self):
                self.closed = True

        stream = _Stream()
        mock_completion.side_effect = [
            self._mock_completion_response("OK"),
            stream,
        ]

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-test-value",
            models=["gpt-4o-mini"],
            capability_checks=["stream"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["capability_results"]["stream"]["status"], "passed")
        self.assertTrue(stream.closed)
        self.assertTrue(mock_completion.call_args_list[1].kwargs["stream"])

    @patch("litellm.completion")
    def test_test_llm_channel_ignores_stream_close_failures(self, mock_completion) -> None:
        api_key = "submitted-stream-secret"

        class _Stream:
            def __init__(self):
                self.close_attempted = False

            def __iter__(self):
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="OK"))])

            def close(self):
                self.close_attempted = True
                raise RuntimeError(f"transport already closed for {api_key}")

        stream = _Stream()
        mock_completion.side_effect = [
            self._mock_completion_response("OK"),
            stream,
        ]

        with self.assertLogs("src.services.system_config_service", level="DEBUG") as logs:
            payload = self.service.test_llm_channel(
                name="primary",
                protocol="openai",
                base_url="https://api.example.com/v1",
                api_key=api_key,
                models=["gpt-4o-mini"],
                capability_checks=["stream"],
            )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["capability_results"]["stream"]["status"], "passed")
        self.assertTrue(stream.close_attempted)
        rendered_logs = "\n".join(logs.output)
        self.assertNotIn(api_key, rendered_logs)
        self.assertIn("[REDACTED]", rendered_logs)

    @patch("litellm.completion")
    def test_test_llm_channel_runs_vision_capability_check(self, mock_completion) -> None:
        mock_completion.side_effect = [
            self._mock_completion_response("OK"),
            self._mock_completion_response("OK"),
        ]

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-test-value",
            models=["gpt-4o-mini"],
            capability_checks=["vision"],
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["capability_results"]["vision"]["status"], "passed")
        vision_content = mock_completion.call_args_list[1].kwargs["messages"][0]["content"]
        self.assertEqual(vision_content[1]["type"], "image_url")
        self.assertTrue(vision_content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    @patch("litellm.completion")
    def test_test_llm_channel_classifies_capability_unsupported(self, mock_completion) -> None:
        mock_completion.side_effect = [
            self._mock_completion_response("OK"),
            Exception("response_format is not supported"),
        ]

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="sk-test-value",
            models=["gpt-4o-mini"],
            capability_checks=["json"],
        )

        result = payload["capability_results"]["json"]
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error_code"], "capability_unsupported")
        self.assertEqual(result["details"]["reason"], "capability_unsupported")

    @patch("litellm.completion")
    def test_test_llm_channel_adds_focused_diagnostic_reasons(self, mock_completion) -> None:
        class RateLimitError(Exception):
            pass

        cases = [
            (Exception("account balance insufficient"), "quota", "insufficient_balance"),
            (RateLimitError("account balance insufficient"), "quota", "insufficient_balance"),
            (RateLimitError("insufficient_quota"), "quota", "quota_exceeded"),
            (Exception("account balance insufficient; your request was blocked"), "quota", "insufficient_balance"),
            (RateLimitError("rate limit: your request was blocked by policy"), "quota", "rate_limit"),
            (Exception("DNS lookup failed"), "network_error", "dns_error"),
            (Exception("TLS certificate verify failed"), "network_error", "tls_error"),
            (Exception("Connection refused"), "network_error", "connection_refused"),
            (Exception("connection request was blocked by firewall"), "network_error", "network_error"),
            (Exception("connection blocked by policy"), "network_error", "network_error"),
            (Exception("request blocked by firewall"), "network_error", "network_error"),
            (Exception("blocked"), "network_error", "unknown_error"),
            (Exception("model gpt-4o is not authorized for this account"), "model_not_found", "model_access_denied"),
            (Exception("litellm.APIError: APIError: OpenAIException - Model disabled."), "model_not_found", "model_access_denied"),
            (Exception("Model is disabled for this account"), "model_not_found", "model_access_denied"),
            (
                Exception("litellm.APIError: APIError: OpenAIException - Your request was blocked."),
                "request_blocked",
                "provider_blocked",
            ),
            (Exception("Forbidden: your request was blocked by content policy"), "request_blocked", "provider_blocked"),
            (Exception("blocked by policy"), "request_blocked", "provider_blocked"),
            (Exception("moderation_blocked"), "request_blocked", "provider_blocked"),
            (Exception("LLM Provider NOT provided for model foo"), "model_not_found", "provider_prefix_mismatch"),
        ]

        for exc, error_code, reason in cases:
            with self.subTest(reason=reason):
                mock_completion.reset_mock()
                mock_completion.side_effect = exc
                payload = self.service.test_llm_channel(
                    name="primary",
                    protocol="openai",
                    base_url="https://api.example.com/v1",
                    api_key="sk-test-value",
                    models=["gpt-4o-mini"],
                )

                self.assertFalse(payload["success"])
                self.assertEqual(payload["error_code"], error_code)
                self.assertEqual(payload["details"]["reason"], reason)
                if reason in {"model_access_denied", "provider_blocked"}:
                    self.assertFalse(payload["retryable"])
                    self.assertEqual(payload["details"]["model"], "openai/gpt-4o-mini")
                    self.assertEqual(payload["resolved_model"], "openai/gpt-4o-mini")

    @patch("litellm.completion")
    def test_test_llm_channel_redacts_unsubmitted_secrets_and_urls(self, mock_completion) -> None:
        mock_completion.side_effect = RuntimeError(
            "provider failed token=super-secret at https://private.example/internal"
        )

        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="submitted-key",
            models=["gpt-4o-mini"],
            capability_checks=["json"],
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(payload["success"])
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("private.example", serialized)

    @patch("src.services.system_config_service.requests.get")
    def test_discover_llm_channel_models_redacts_unsubmitted_secrets_and_urls(self, mock_get) -> None:
        mock_get.side_effect = requests.ConnectionError(
            "provider failed token=super-secret at https://private.example/internal"
        )

        payload = self.service.discover_llm_channel_models(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key="submitted-key",
        )

        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertFalse(payload["success"])
        self.assertNotIn("super-secret", serialized)
        self.assertNotIn("private.example", serialized)

    def test_test_llm_channel_reports_comma_only_api_key_as_missing(self) -> None:
        payload = self.service.test_llm_channel(
            name="primary",
            protocol="openai",
            base_url="https://api.example.com/v1",
            api_key=", ,",
            models=["gpt-4o-mini"],
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "invalid_config")
        self.assertEqual(payload["details"]["reason"], "missing_api_key")

    @patch("litellm.completion")
    def test_local_openai_compatible_empty_key_still_runs_completion(
        self,
        mock_completion,
    ) -> None:
        mock_completion.return_value = self._mock_completion_response("OK")

        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            payload = self.service.test_llm_channel(
                name="local_proxy",
                provider_id="custom",
                protocol="openai",
                base_url="http://127.0.0.1:18000/v1",
                api_key="",
                models=["local-model"],
            )

        self.assertTrue(payload["success"], payload)
        self.assertEqual(
            mock_completion.call_args.kwargs["api_base"],
            "http://127.0.0.1:18000/v1",
        )
        self.assertTrue(mock_completion.call_args.kwargs["api_key"])

    @patch("src.services.system_config_service.requests.get")
    @patch("litellm.completion")
    def test_test_and_discovery_reject_unknown_explicit_provider(
        self,
        mock_completion,
        mock_get,
    ) -> None:
        test_payload = self.service.test_llm_channel(
            name="research",
            provider_id="not-a-provider",
            protocol="openai",
            base_url="https://models.example.com/v1",
            api_key="sk-test-value",
            models=["research-model"],
        )
        discovery_payload = self.service.discover_llm_channel_models(
            name="research",
            provider_id="not-a-provider",
            protocol="openai",
            base_url="https://models.example.com/v1",
            api_key="sk-test-value",
        )

        for payload in (test_payload, discovery_payload):
            self.assertFalse(payload["success"])
            self.assertEqual(payload["error_code"], "invalid_config")
            self.assertEqual(payload["details"]["issue_key"], "provider_id")
            self.assertEqual(payload["details"]["reason"], "invalid_provider")
        mock_completion.assert_not_called()
        mock_get.assert_not_called()

    @patch("litellm.completion")
    def test_test_channel_uses_explicit_provider_for_renamed_connection(
        self,
        mock_completion,
    ) -> None:
        mock_completion.return_value = self._mock_completion_response("OK")

        payload = self.service.test_llm_channel(
            name="writing_team",
            provider_id="anthropic",
            protocol="openai",
            base_url="",
            api_key="sk-anthropic",
            models=["claude-test"],
        )

        self.assertTrue(payload["success"], payload)
        self.assertEqual(payload["resolved_protocol"], "anthropic")
        self.assertEqual(payload["resolved_model"], "anthropic/claude-test")
        self.assertEqual(mock_completion.call_args.kwargs["model"], "anthropic/claude-test")
        self.assertNotIn("api_base", mock_completion.call_args.kwargs)

    @patch("litellm.completion")
    def test_explicit_custom_provider_requires_base_url_for_official_looking_name(
        self,
        mock_completion,
    ) -> None:
        payload = self.service.test_llm_channel(
            name="openai",
            provider_id="custom",
            protocol="openai",
            base_url="",
            api_key="sk-custom",
            models=["custom-model"],
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["error_code"], "invalid_config")
        self.assertEqual(payload["details"]["reason"], "missing_base_url")
        mock_completion.assert_not_called()

    @patch("src.services.system_config_service.requests.get")
    def test_discover_llm_channel_models_returns_deduped_ids(self, mock_get) -> None:
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "qwen-plus"},
                {"id": "qwen-plus"},
                {"id": "qwen-turbo"},
            ]
        }
        mock_get.return_value = mock_response

        payload = self.service.discover_llm_channel_models(
            name="dashscope",
            protocol="openai",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="sk-test-value",
        )

        self.assertTrue(payload["success"])
        self.assertEqual(payload["resolved_protocol"], "openai")
        self.assertEqual(payload["models"], ["qwen-plus", "qwen-turbo"])
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        )
        self.assertEqual(
            mock_get.call_args.kwargs["headers"]["Authorization"],
            "Bearer sk-test-value",
        )
        self.assertFalse(mock_get.call_args.kwargs["allow_redirects"])

    @patch("src.services.system_config_service.requests.get")
    def test_discover_ollama_models_uses_api_tags_without_authorization(
        self,
        mock_get,
    ) -> None:
        mock_response = Mock(ok=True, status_code=200)
        mock_response.json.return_value = {
            "models": [{"name": "llama3.2:latest"}],
        }
        mock_get.return_value = mock_response

        payload = self.service.discover_llm_channel_models(
            name="local_lab",
            provider_id="ollama",
            protocol="ollama",
            base_url="http://127.0.0.1:11434",
            api_key="",
        )

        self.assertTrue(payload["success"], payload)
        self.assertEqual(payload["resolved_protocol"], "ollama")
        self.assertEqual(payload["models"], ["llama3.2:latest"])
        mock_get.assert_called_once()
        self.assertEqual(
            mock_get.call_args.args[0],
            "http://127.0.0.1:11434/api/tags",
        )
        self.assertNotIn("Authorization", mock_get.call_args.kwargs["headers"])

    @patch("src.services.system_config_service.requests.get")
    def test_discover_llm_channel_models_classifies_error_scenarios(self, mock_get) -> None:
        auth_response = Mock(ok=False, status_code=401, text="invalid api key sk-secret-value")
        auth_response.json.return_value = {"error": {"message": "invalid api key sk-secret-value"}}
        not_found_response = Mock(ok=False, status_code=404, text="not found")
        not_found_response.json.return_value = {"error": {"message": "not found"}}
        billing_response = Mock(ok=False, status_code=402, text="account balance insufficient")
        billing_response.json.return_value = {"error": {"message": "account balance insufficient"}}
        billing_rate_limit_response = Mock(ok=False, status_code=429, text="account balance insufficient")
        billing_rate_limit_response.json.return_value = {"error": {"message": "account balance insufficient"}}
        quota_exceeded_response = Mock(ok=False, status_code=429, text="insufficient_quota")
        quota_exceeded_response.json.return_value = {"error": {"message": "insufficient_quota"}}
        quota_blocked_response = Mock(ok=False, status_code=403, text="account balance insufficient; your request was blocked")
        quota_blocked_response.json.return_value = {"error": {"message": "account balance insufficient; your request was blocked"}}
        rate_limit_response = Mock(ok=False, status_code=429, text="too many requests")
        rate_limit_response.json.return_value = {"error": {"message": "too many requests"}}
        blocked_response = Mock(ok=False, status_code=403, text="Forbidden: your request was blocked by content policy")
        blocked_response.json.return_value = {"error": {"message": "Forbidden: your request was blocked by content policy"}}
        connection_blocked_response = Mock(ok=False, status_code=403, text="connection blocked by policy")
        connection_blocked_response.json.return_value = {"error": {"message": "connection blocked by policy"}}
        invalid_json_response = Mock(ok=True, status_code=200, text="<html>bad gateway</html>")
        invalid_json_response.json.side_effect = ValueError("invalid json")

        for response, error_code, stage, retryable, reason in [
            (auth_response, "auth", "model_discovery", False, "api_key_rejected"),
            (not_found_response, "network_error", "model_discovery", False, "endpoint_not_found"),
            (billing_response, "quota", "model_discovery", True, "insufficient_balance"),
            (billing_rate_limit_response, "quota", "model_discovery", True, "insufficient_balance"),
            (quota_exceeded_response, "quota", "model_discovery", True, "quota_exceeded"),
            (quota_blocked_response, "quota", "model_discovery", True, "insufficient_balance"),
            (rate_limit_response, "quota", "model_discovery", True, "rate_limit"),
            (blocked_response, "request_blocked", "model_discovery", False, "provider_blocked"),
            (connection_blocked_response, "network_error", "model_discovery", True, "network_error"),
            (invalid_json_response, "format_error", "response_parse", False, "non_json"),
        ]:
            with self.subTest(error_code=error_code):
                mock_get.return_value = response
                payload = self.service.discover_llm_channel_models(
                    name="dashscope",
                    protocol="openai",
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    api_key="sk-secret-value",
                )

                self.assertFalse(payload["success"])
                self.assertEqual(payload["error_code"], error_code)
                self.assertEqual(payload["stage"], stage)
                self.assertEqual(payload["retryable"], retryable)
                self.assertEqual(payload["details"]["reason"], reason)
                if error_code == "auth":
                    self.assertNotIn("sk-secret-value", payload["error"])

    @patch("src.services.system_config_service.requests.get")
    def test_discover_llm_channel_models_rejects_redirect_responses(self, mock_get) -> None:
        mock_response = Mock()
        mock_response.ok = True
        mock_response.status_code = 302
        mock_get.return_value = mock_response

        payload = self.service.discover_llm_channel_models(
            name="dashscope",
            protocol="openai",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="sk-test-value",
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["message"], "Model discovery request was redirected")
        self.assertIn("Redirect responses are not allowed", payload["error"])
        self.assertFalse(mock_get.call_args.kwargs["allow_redirects"])

    def test_discover_llm_channel_models_requires_base_url(self) -> None:
        payload = self.service.discover_llm_channel_models(
            name="primary",
            protocol="openai",
            base_url="",
            api_key="sk-test-value",
        )

        self.assertFalse(payload["success"])
        self.assertIn("base URL", payload["error"])
        self.assertEqual(payload["models"], [])

    def test_discover_llm_channel_models_rejects_unsupported_protocol(self) -> None:
        payload = self.service.discover_llm_channel_models(
            name="gemini",
            protocol="gemini",
            base_url="https://example.com/v1",
            api_key="sk-test-value",
        )

        self.assertFalse(payload["success"])
        self.assertEqual(payload["resolved_protocol"], "gemini")
        self.assertIn("does not support /models discovery yet", payload["error"])

    def test_build_llm_models_url_strips_query_and_fragment(self) -> None:
        models_url = SystemConfigService._build_llm_models_url(
            "https://example.com/v1/chat/completions?api-version=1#frag"
        )

        self.assertEqual(models_url, "https://example.com/v1/models")

    def test_build_llm_models_url_supports_deepseek_root_base_url(self) -> None:
        models_url = SystemConfigService._build_llm_models_url("https://api.deepseek.com")

        self.assertEqual(models_url, "https://api.deepseek.com/models")

    def test_build_llm_models_url_normalizes_ollama_inputs(self) -> None:
        for base_url in (
            "http://127.0.0.1:11434",
            "http://127.0.0.1:11434/v1",
            "http://127.0.0.1:11434/api/tags?refresh=true#models",
        ):
            with self.subTest(base_url=base_url):
                self.assertEqual(
                    SystemConfigService._build_llm_models_url(
                        base_url,
                        protocol="ollama",
                    ),
                    "http://127.0.0.1:11434/api/tags",
                )

    def test_provider_catalog_discovery_contract_is_consistent_and_immutable(self) -> None:
        from src.llm.provider_catalog import (
            get_provider,
            get_provider_catalog,
            supports_model_discovery,
        )

        catalog = get_provider_catalog()
        for provider in catalog:
            self.assertEqual(
                provider["supports_discovery"],
                supports_model_discovery(provider_id=provider["id"]),
                provider["id"],
            )

        ollama = get_provider("ollama")
        self.assertIsNotNone(ollama)
        ollama["label"] = "mutated"
        ollama["capabilities"].append("mutated")
        fresh_ollama = get_provider("ollama")
        self.assertNotEqual(fresh_ollama["label"], "mutated")
        self.assertNotIn("mutated", fresh_ollama["capabilities"])

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
