# -*- coding: utf-8 -*-
"""System configuration setup, backend status, and desktop import contracts."""

from tests.system_config_service_test_support import (
    _SystemConfigServiceTestCaseBase,
    ConfigConflictError,
    ConfigImportError,
    ConfigValidationError,
    DEFAULT_ALPHASIFT_INSTALL_SPEC,
    Dict,
    Path,
    json,
    os,
    patch,
)


class SystemConfigServiceTestCase(_SystemConfigServiceTestCaseBase):
    def test_get_setup_status_reports_required_gaps_for_empty_config(self) -> None:
        self._rewrite_env("")

        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()

        self.assertFalse(status["is_complete"])
        self.assertFalse(status["ready_for_smoke"])
        self.assertEqual(status["next_step_key"], "llm_primary")
        self.assertIn("llm_primary", status["required_missing_keys"])
        self.assertIn("stock_list", status["required_missing_keys"])

    def test_get_setup_status_marks_minimal_config_complete(self) -> None:
        self._rewrite_env(
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
            "GEMINI_API_KEY=secret-key-value",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertTrue(status["is_complete"])
        self.assertTrue(status["ready_for_smoke"])
        self.assertEqual(checks["llm_primary"]["status"], "configured")
        self.assertEqual(checks["llm_agent"]["status"], "inherited")
        self.assertEqual(checks["stock_list"]["status"], "configured")
        self.assertEqual(checks["notification"]["status"], "optional")

    def test_generation_backend_status_preview_uses_draft_backend(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
            "GEMINI_API_KEY=secret-key-value",
        )

        with patch("src.llm.local_cli_backend.shutil.which", return_value=None):
            payload = self.service.preview_generation_backend_status(
                items=[
                    {"key": "GENERATION_BACKEND", "value": "codex_cli"},
                    {"key": "GENERATION_FALLBACK_BACKEND", "value": ""},
                ],
                mask_token="******",
            )

        self.assertEqual(payload["primary_backend_id"], "codex_cli")
        self.assertFalse(payload["primary"]["available"])
        self.assertEqual(payload["primary"]["health_status"], "failed")
        self.assertEqual(payload["primary"]["last_error_code"], "command_not_found")

    def test_generation_backend_status_preserves_masked_saved_secret(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
            "GEMINI_API_KEY=saved-secret-value",
        )

        payload = self.service.preview_generation_backend_status(
            items=[{"key": "GEMINI_API_KEY", "value": "******"}],
            mask_token="******",
        )

        self.assertEqual(payload["primary_backend_id"], "litellm")
        self.assertTrue(payload["primary"]["available"])

    def test_generation_backend_smoke_reuses_saved_api_key_for_unchanged_connection_identity(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "GENERATION_FALLBACK_BACKEND=",
            "LLM_CHANNELS=alpha",
            "LLM_ALPHA_PROVIDER=custom",
            "LLM_ALPHA_PROTOCOL=openai",
            "LLM_ALPHA_BASE_URL=https://saved.example/v1",
            "LLM_ALPHA_API_KEY=saved-alpha-secret",
            "LLM_ALPHA_MODELS=gpt-alpha",
            "LLM_ALPHA_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-alpha",
        )
        observed: Dict[str, str] = {}

        def dispatch(_analyzer, _model, _call_kwargs, *, config, **_kwargs):
            deployment = config.llm_model_list[0]["litellm_params"]
            observed["api_key"] = deployment["api_key"]
            observed["base_url"] = deployment["api_base"]
            return {
                "choices": [{"message": {"content": '{"ok": true, "backend_smoke": "passed"}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

        with patch("src.analyzer.GeminiAnalyzer._dispatch_litellm_completion", new=dispatch):
            payload = self.service.test_generation_backend(
                items=[
                    {"key": "LLM_ALPHA_PROVIDER", "value": "custom"},
                    {"key": "LLM_ALPHA_PROTOCOL", "value": "openai"},
                    {"key": "LLM_ALPHA_BASE_URL", "value": "https://saved.example/v1"},
                    {"key": "LLM_ALPHA_API_KEY", "value": "******"},
                ],
                mask_token="******",
            )

        self.assertTrue(payload["success"])
        self.assertEqual(observed["api_key"], "saved-alpha-secret")
        self.assertEqual(observed["base_url"], "https://saved.example/v1")

    def test_generation_backend_smoke_rejects_masked_saved_api_key_when_endpoint_changes(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "GENERATION_FALLBACK_BACKEND=",
            "LLM_CHANNELS=alpha",
            "LLM_ALPHA_PROVIDER=custom",
            "LLM_ALPHA_PROTOCOL=openai",
            "LLM_ALPHA_BASE_URL=https://saved.example/v1",
            "LLM_ALPHA_API_KEY=saved-alpha-secret",
            "LLM_ALPHA_MODELS=gpt-alpha",
            "LLM_ALPHA_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-alpha",
        )

        completion = {
            "choices": [{"message": {"content": '{"ok": true, "backend_smoke": "passed"}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        with patch(
            "src.analyzer.GeminiAnalyzer._dispatch_litellm_completion",
            return_value=completion,
        ) as dispatch:
            with self.assertRaises(ConfigValidationError) as context:
                self.service.test_generation_backend(
                    items=[
                        {"key": "LLM_ALPHA_BASE_URL", "value": "https://changed.example/v1"},
                        {"key": "LLM_ALPHA_API_KEY", "value": "******"},
                    ],
                    mask_token="******",
                )

        issue = next(
            item for item in context.exception.issues
            if item["key"] == "LLM_ALPHA_API_KEY"
        )
        self.assertEqual(issue["code"], "saved_secret_scope_mismatch")
        self.assertEqual(issue["details"]["reason"], "connection_identity_changed")
        self.assertNotIn("saved-alpha-secret", json.dumps(context.exception.issues))
        dispatch.assert_not_called()

    def test_generation_backend_preview_rejects_omitted_saved_api_keys_when_provider_changes(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "GENERATION_FALLBACK_BACKEND=",
            "LLM_CHANNELS=alpha",
            "LLM_ALPHA_PROVIDER=custom",
            "LLM_ALPHA_PROTOCOL=openai",
            "LLM_ALPHA_BASE_URL=https://saved.example/v1",
            "LLM_ALPHA_API_KEYS=saved-alpha-one,saved-alpha-two",
            "LLM_ALPHA_MODELS=gpt-alpha",
            "LLM_ALPHA_ENABLED=true",
            "LITELLM_MODEL=openai/gpt-alpha",
        )

        with self.assertRaises(ConfigValidationError) as context:
            self.service.preview_generation_backend_status(
                items=[{"key": "LLM_ALPHA_PROVIDER", "value": "openai"}],
                mask_token="******",
            )

        issue = next(
            item for item in context.exception.issues
            if item["key"] == "LLM_ALPHA_API_KEYS"
        )
        self.assertEqual(issue["code"], "saved_secret_scope_mismatch")
        self.assertEqual(issue["actual"], "omitted")
        self.assertEqual(issue["details"]["changed_fields"], ["provider"])
        rendered = json.dumps(context.exception.issues)
        self.assertNotIn("saved-alpha-one", rendered)
        self.assertNotIn("saved-alpha-two", rendered)

    def test_update_rejects_saved_connection_secret_reuse_for_each_identity_change(self) -> None:
        cases = (
            (
                "provider_masked_api_key",
                "API_KEY",
                [{"key": "LLM_ALPHA_PROVIDER", "value": "openai"},
                 {"key": "LLM_ALPHA_API_KEY", "value": "******"}],
                "provider",
            ),
            (
                "protocol_omitted_api_key",
                "API_KEY",
                [{"key": "LLM_ALPHA_PROTOCOL", "value": "anthropic"}],
                "protocol",
            ),
            (
                "base_url_masked_api_keys",
                "API_KEYS",
                [{"key": "LLM_ALPHA_BASE_URL", "value": "https://changed.example/v1"},
                 {"key": "LLM_ALPHA_API_KEYS", "value": "******"}],
                "base_url",
            ),
            (
                "provider_omitted_api_keys",
                "API_KEYS",
                [{"key": "LLM_ALPHA_PROVIDER", "value": "openai"}],
                "provider",
            ),
        )
        for name, secret_suffix, updates, changed_field in cases:
            with self.subTest(name=name):
                self._rewrite_env(
                    "GENERATION_BACKEND=litellm",
                    "GENERATION_FALLBACK_BACKEND=",
                    "LLM_CHANNELS=alpha",
                    "LLM_ALPHA_PROVIDER=custom",
                    "LLM_ALPHA_PROTOCOL=openai",
                    "LLM_ALPHA_BASE_URL=https://saved.example/v1",
                    f"LLM_ALPHA_{secret_suffix}=saved-alpha-secret",
                    "LLM_ALPHA_MODELS=gpt-alpha",
                    "LLM_ALPHA_ENABLED=true",
                    "LITELLM_MODEL=openai/gpt-alpha",
                )
                before = self.manager.read_config_map()

                with self.assertRaises(ConfigValidationError) as context:
                    self.service.update(
                        config_version=self.manager.get_config_version(),
                        items=updates,
                        mask_token="******",
                        reload_now=False,
                    )

                issue = next(
                    item for item in context.exception.issues
                    if item["key"] == f"LLM_ALPHA_{secret_suffix}"
                )
                self.assertEqual(issue["code"], "saved_secret_scope_mismatch")
                self.assertIn(changed_field, issue["details"]["changed_fields"])
                self.assertEqual(self.manager.read_config_map(), before)

    def test_update_rejects_masked_extra_headers_when_endpoint_changes(self) -> None:
        saved_headers = '{"Authorization":"Bearer saved-header-secret"}'
        self._rewrite_env(
            "LLM_CHANNELS=alpha",
            "LLM_ALPHA_PROVIDER=custom",
            "LLM_ALPHA_PROTOCOL=openai",
            "LLM_ALPHA_BASE_URL=https://saved.example/v1",
            f"LLM_ALPHA_EXTRA_HEADERS={saved_headers}",
            "LLM_ALPHA_MODELS=gpt-alpha",
            "LLM_ALPHA_ENABLED=false",
        )
        before = self.manager.read_config_map()

        with self.assertRaises(ConfigValidationError) as context:
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[
                    {"key": "LLM_ALPHA_BASE_URL", "value": "https://changed.example/v1"},
                    {"key": "LLM_ALPHA_EXTRA_HEADERS", "value": "******"},
                ],
                mask_token="******",
                reload_now=False,
            )

        issue = next(
            item for item in context.exception.issues
            if item["key"] == "LLM_ALPHA_EXTRA_HEADERS"
        )
        self.assertEqual(issue["code"], "saved_secret_scope_mismatch")
        self.assertEqual(issue["details"]["changed_fields"], ["base_url"])
        self.assertNotIn("saved-header-secret", json.dumps(context.exception.issues))
        self.assertEqual(self.manager.read_config_map(), before)

    def test_preview_rejects_masked_runtime_only_extra_headers(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "GENERATION_FALLBACK_BACKEND=",
        )
        runtime_env = {
            "LLM_CHANNELS": "runtime",
            "LLM_RUNTIME_PROVIDER": "custom",
            "LLM_RUNTIME_PROTOCOL": "openai",
            "LLM_RUNTIME_BASE_URL": "https://runtime.example/v1",
            "LLM_RUNTIME_API_KEY": "fresh-test-key",
            "LLM_RUNTIME_EXTRA_HEADERS": '{"Authorization":"Bearer runtime-header-secret"}',
            "LLM_RUNTIME_MODELS": "gpt-runtime",
            "LLM_RUNTIME_ENABLED": "true",
            "LITELLM_MODEL": "openai/gpt-runtime",
        }

        with patch.dict(os.environ, runtime_env, clear=False):
            with self.assertRaises(ConfigValidationError) as context:
                self.service.preview_generation_backend_status(
                    items=[
                        {"key": "LLM_RUNTIME_API_KEY", "value": "fresh-test-key"},
                        {"key": "LLM_RUNTIME_EXTRA_HEADERS", "value": "******"},
                    ],
                    mask_token="******",
                )

        issue = next(
            item for item in context.exception.issues
            if item["key"] == "LLM_RUNTIME_EXTRA_HEADERS"
        )
        self.assertEqual(issue["code"], "runtime_secret_not_reusable")
        self.assertNotIn("runtime-header-secret", json.dumps(context.exception.issues))

    def test_generation_backend_preview_rejects_masked_runtime_only_connection_secrets(self) -> None:
        for secret_suffix in ("API_KEY", "API_KEYS"):
            with self.subTest(secret_suffix=secret_suffix):
                self._rewrite_env(
                    "GENERATION_BACKEND=litellm",
                    "GENERATION_FALLBACK_BACKEND=",
                )
                runtime_env = {
                    "LLM_CHANNELS": "runtime",
                    "LLM_RUNTIME_PROVIDER": "custom",
                    "LLM_RUNTIME_PROTOCOL": "openai",
                    "LLM_RUNTIME_BASE_URL": "https://runtime.example/v1",
                    f"LLM_RUNTIME_{secret_suffix}": "runtime-only-secret",
                    "LLM_RUNTIME_MODELS": "gpt-runtime",
                    "LLM_RUNTIME_ENABLED": "true",
                    "LITELLM_MODEL": "openai/gpt-runtime",
                }

                with patch.dict(os.environ, runtime_env, clear=False):
                    with self.assertRaises(ConfigValidationError) as context:
                        self.service.preview_generation_backend_status(
                            items=[
                                {"key": f"LLM_RUNTIME_{secret_suffix}", "value": "******"},
                            ],
                            mask_token="******",
                        )

                issue = next(
                    item for item in context.exception.issues
                    if item["key"] == f"LLM_RUNTIME_{secret_suffix}"
                )
                self.assertEqual(issue["code"], "runtime_secret_not_reusable")
                self.assertEqual(issue["actual"], "masked")
                self.assertNotIn("runtime-only-secret", json.dumps(context.exception.issues))

    def test_generation_backend_smoke_rejects_omitted_runtime_only_connection_secrets(self) -> None:
        completion = {
            "choices": [{"message": {"content": '{"ok": true, "backend_smoke": "passed"}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        for secret_suffix in ("API_KEY", "API_KEYS"):
            with self.subTest(secret_suffix=secret_suffix):
                self._rewrite_env(
                    "GENERATION_BACKEND=litellm",
                    "GENERATION_FALLBACK_BACKEND=",
                )
                runtime_env = {
                    "LLM_CHANNELS": "runtime",
                    "LLM_RUNTIME_PROVIDER": "custom",
                    "LLM_RUNTIME_PROTOCOL": "openai",
                    "LLM_RUNTIME_BASE_URL": "https://runtime.example/v1",
                    f"LLM_RUNTIME_{secret_suffix}": "runtime-only-secret",
                    "LLM_RUNTIME_MODELS": "gpt-runtime",
                    "LLM_RUNTIME_ENABLED": "true",
                    "LITELLM_MODEL": "openai/gpt-runtime",
                }

                with patch.dict(os.environ, runtime_env, clear=False), patch(
                    "src.analyzer.GeminiAnalyzer._dispatch_litellm_completion",
                    return_value=completion,
                ) as dispatch:
                    with self.assertRaises(ConfigValidationError) as context:
                        self.service.test_generation_backend(mask_token="******")

                issue = next(
                    item for item in context.exception.issues
                    if item["key"] == f"LLM_RUNTIME_{secret_suffix}"
                )
                self.assertEqual(issue["code"], "runtime_secret_not_reusable")
                self.assertEqual(issue["actual"], "omitted")
                self.assertNotIn("runtime-only-secret", json.dumps(context.exception.issues))
                dispatch.assert_not_called()

    def test_generation_backend_smoke_rejects_saved_literal_mask_placeholder(self) -> None:
        completion = {
            "choices": [{"message": {"content": '{"ok": true, "backend_smoke": "passed"}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        for secret_suffix in ("API_KEY", "API_KEYS"):
            with self.subTest(secret_suffix=secret_suffix):
                self._rewrite_env(
                    "GENERATION_BACKEND=litellm",
                    "GENERATION_FALLBACK_BACKEND=",
                    "LLM_CHANNELS=alpha",
                    "LLM_ALPHA_PROVIDER=custom",
                    "LLM_ALPHA_PROTOCOL=openai",
                    "LLM_ALPHA_BASE_URL=https://saved.example/v1",
                    f"LLM_ALPHA_{secret_suffix}=******",
                    "LLM_ALPHA_MODELS=gpt-alpha",
                    "LLM_ALPHA_ENABLED=true",
                    "LITELLM_MODEL=openai/gpt-alpha",
                )

                with patch(
                    "src.analyzer.GeminiAnalyzer._dispatch_litellm_completion",
                    return_value=completion,
                ) as dispatch:
                    with self.assertRaises(ConfigValidationError) as context:
                        self.service.test_generation_backend(mask_token="******")

                issue = next(
                    item for item in context.exception.issues
                    if item["key"] == f"LLM_ALPHA_{secret_suffix}"
                )
                self.assertEqual(issue["code"], "saved_secret_scope_mismatch")
                self.assertEqual(issue["details"]["reason"], "invalid_saved_secret_placeholder")
                dispatch.assert_not_called()

    def test_update_rejects_masked_secret_for_renamed_connection_key(self) -> None:
        for secret_suffix in ("API_KEY", "API_KEYS"):
            with self.subTest(secret_suffix=secret_suffix):
                self._rewrite_env(
                    "GENERATION_BACKEND=litellm",
                    "GENERATION_FALLBACK_BACKEND=",
                    "LLM_CHANNELS=old",
                    "LLM_OLD_PROVIDER=custom",
                    "LLM_OLD_PROTOCOL=openai",
                    "LLM_OLD_BASE_URL=https://saved.example/v1",
                    f"LLM_OLD_{secret_suffix}=saved-old-secret",
                    "LLM_OLD_MODELS=gpt-alpha",
                    "LLM_OLD_ENABLED=true",
                )
                before = self.manager.read_config_map()

                with self.assertRaises(ConfigValidationError) as context:
                    self.service.update(
                        config_version=self.manager.get_config_version(),
                        items=[
                            {"key": "LLM_CHANNELS", "value": "new"},
                            {"key": "LLM_NEW_PROVIDER", "value": "custom"},
                            {"key": "LLM_NEW_PROTOCOL", "value": "openai"},
                            {"key": "LLM_NEW_BASE_URL", "value": "https://saved.example/v1"},
                            {"key": f"LLM_NEW_{secret_suffix}", "value": "******"},
                            {"key": "LLM_NEW_MODELS", "value": "gpt-alpha"},
                            {"key": "LLM_NEW_ENABLED", "value": "true"},
                        ],
                        mask_token="******",
                        reload_now=False,
                    )

                issue = next(
                    item for item in context.exception.issues
                    if item["key"] == f"LLM_NEW_{secret_suffix}"
                )
                self.assertEqual(issue["code"], "saved_secret_scope_mismatch")
                self.assertEqual(issue["details"]["reason"], "missing_scoped_saved_secret")
                self.assertNotIn("saved-old-secret", json.dumps(context.exception.issues))
                self.assertEqual(self.manager.read_config_map(), before)

    def test_update_accepts_fresh_connection_secret_when_endpoint_changes(self) -> None:
        for secret_suffix in ("API_KEY", "API_KEYS"):
            with self.subTest(secret_suffix=secret_suffix):
                self._rewrite_env(
                    "GENERATION_BACKEND=litellm",
                    "GENERATION_FALLBACK_BACKEND=",
                    "LLM_CHANNELS=alpha",
                    "LLM_ALPHA_PROVIDER=custom",
                    "LLM_ALPHA_PROTOCOL=openai",
                    "LLM_ALPHA_BASE_URL=https://saved.example/v1",
                    f"LLM_ALPHA_{secret_suffix}=saved-alpha-secret",
                    "LLM_ALPHA_MODELS=gpt-alpha",
                    "LLM_ALPHA_ENABLED=true",
                )

                result = self.service.update(
                    config_version=self.manager.get_config_version(),
                    items=[
                        {"key": "LLM_ALPHA_BASE_URL", "value": "https://changed.example/v1"},
                        {"key": f"LLM_ALPHA_{secret_suffix}", "value": "fresh-alpha-secret"},
                    ],
                    mask_token="******",
                    reload_now=False,
                )

                saved = self.manager.read_config_map()
                self.assertTrue(result["success"])
                self.assertEqual(saved["LLM_ALPHA_BASE_URL"], "https://changed.example/v1")
                self.assertEqual(saved[f"LLM_ALPHA_{secret_suffix}"], "fresh-alpha-secret")

    def test_update_rejects_identity_change_while_removing_connection_with_saved_secret(self) -> None:
        for submitted_secret in (None, "******"):
            with self.subTest(submitted_secret=submitted_secret):
                self._rewrite_env(
                    "LLM_CHANNELS=alpha",
                    "LLM_ALPHA_PROVIDER=custom",
                    "LLM_ALPHA_PROTOCOL=openai",
                    "LLM_ALPHA_BASE_URL=https://saved.example/v1",
                    "LLM_ALPHA_API_KEY=saved-alpha-secret",
                    "LLM_ALPHA_MODELS=gpt-alpha",
                    "LLM_ALPHA_ENABLED=true",
                )
                updates = [
                    {"key": "LLM_CHANNELS", "value": ""},
                    {"key": "LLM_ALPHA_BASE_URL", "value": "https://changed.example/v1"},
                ]
                if submitted_secret is not None:
                    updates.append({"key": "LLM_ALPHA_API_KEY", "value": submitted_secret})
                before = self.manager.read_config_map()

                with self.assertRaises(ConfigValidationError) as context:
                    self.service.update(
                        config_version=self.manager.get_config_version(),
                        items=updates,
                        mask_token="******",
                        reload_now=False,
                    )

                issue = next(
                    item for item in context.exception.issues
                    if item["key"] == "LLM_ALPHA_API_KEY"
                )
                self.assertEqual(issue["code"], "saved_secret_scope_mismatch")
                self.assertEqual(self.manager.read_config_map(), before)

    def test_update_rejects_identity_change_for_orphaned_saved_connection_secret(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=alpha",
            "LLM_ALPHA_PROVIDER=custom",
            "LLM_ALPHA_PROTOCOL=openai",
            "LLM_ALPHA_BASE_URL=https://saved.example/v1",
            "LLM_ALPHA_API_KEYS=saved-alpha-secret",
            "LLM_ALPHA_MODELS=gpt-alpha",
            "LLM_ALPHA_ENABLED=true",
        )
        self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "LLM_CHANNELS", "value": ""}],
            reload_now=False,
        )
        before = self.manager.read_config_map()

        with self.assertRaises(ConfigValidationError) as context:
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[
                    {"key": "LLM_ALPHA_PROVIDER", "value": "openai"},
                    {"key": "LLM_ALPHA_API_KEYS", "value": "******"},
                ],
                mask_token="******",
                reload_now=False,
            )

        issue = next(
            item for item in context.exception.issues
            if item["key"] == "LLM_ALPHA_API_KEYS"
        )
        self.assertEqual(issue["code"], "saved_secret_scope_mismatch")
        self.assertEqual(self.manager.read_config_map(), before)

    def test_generation_backend_status_saved_invalid_numeric_returns_failed_status(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "GENERATION_BACKEND_TIMEOUT_SECONDS=not-int",
        )

        payload = self.service.get_generation_backend_status()

        self.assertEqual(payload["primary_backend_id"], "codex_cli")
        self.assertFalse(payload["primary"]["available"])
        self.assertEqual(payload["primary"]["health_status"], "failed")
        self.assertEqual(payload["primary"]["last_error_code"], "unsafe_config")

    def test_generation_backend_preview_invalid_numeric_returns_validation_error(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "GENERATION_FALLBACK_BACKEND=",
        )

        with self.assertRaises(ConfigValidationError) as ctx:
            self.service.preview_generation_backend_status(
                items=[{"key": "GENERATION_BACKEND_TIMEOUT_SECONDS", "value": "not-int"}],
                mask_token="******",
            )

        self.assertEqual(ctx.exception.issues[0]["key"], "GENERATION_BACKEND_TIMEOUT_SECONDS")
        self.assertEqual(ctx.exception.issues[0]["severity"], "error")

    def test_generation_backend_status_saved_litellm_invalid_channel_returns_failed_status(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "LLM_CHANNELS=remote",
            "LLM_REMOTE_PROTOCOL=openai",
            "LLM_REMOTE_BASE_URL=http://169.254.169.254/v1",
            "LLM_REMOTE_API_KEY=sk-remote",
            "LLM_REMOTE_MODELS=gpt-4o-mini",
        )

        payload = self.service.get_generation_backend_status()

        self.assertEqual(payload["primary_backend_id"], "litellm")
        self.assertFalse(payload["primary"]["available"])
        self.assertEqual(payload["primary"]["health_status"], "failed")
        self.assertEqual(payload["primary"]["last_error_code"], "unsafe_config")

    def test_generation_backend_status_saved_litellm_model_without_key_returns_failed_status(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
        )

        with patch.dict(os.environ, {"ENV_FILE": str(self.env_path)}, clear=True):
            payload = self.service.get_generation_backend_status()

        self.assertEqual(payload["primary_backend_id"], "litellm")
        self.assertFalse(payload["primary"]["available"])
        self.assertEqual(payload["primary"]["health_status"], "failed")
        self.assertEqual(payload["primary"]["last_error_code"], "unsafe_config")

    def test_generation_backend_preview_litellm_model_without_key_returns_validation_error(self) -> None:
        self._rewrite_env("GENERATION_BACKEND=litellm")

        with patch.dict(os.environ, {"ENV_FILE": str(self.env_path)}, clear=True):
            with self.assertRaises(ConfigValidationError) as ctx:
                self.service.preview_generation_backend_status(
                    items=[{"key": "LITELLM_MODEL", "value": "gemini/gemini-3-flash-preview"}],
                    mask_token="******",
                )

        self.assertEqual(ctx.exception.issues[0]["key"], "LITELLM_MODEL")
        self.assertEqual(ctx.exception.issues[0]["code"], "missing_runtime_source")

    def test_generation_backend_preview_uses_openai_model_draft(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "OPENAI_API_KEY=secret-key-value",
            "OPENAI_MODEL=gpt-5.5",
        )

        with patch.dict(os.environ, {"ENV_FILE": str(self.env_path)}, clear=True):
            payload = self.service.preview_generation_backend_status(
                items=[{"key": "OPENAI_MODEL", "value": "gemini/gemini-3-flash-preview"}],
                mask_token="******",
            )

        self.assertEqual(payload["primary_backend_id"], "litellm")
        self.assertFalse(payload["primary"]["available"])
        self.assertEqual(payload["primary"]["last_error_code"], "unsafe_config")

    def test_generation_backend_preview_uses_gemini_model_draft(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "GEMINI_API_KEY=secret-key-value",
            "GEMINI_MODEL=gemini-3.1-pro-preview",
        )

        with patch.dict(os.environ, {"ENV_FILE": str(self.env_path)}, clear=True):
            payload = self.service.preview_generation_backend_status(
                items=[{"key": "GEMINI_MODEL", "value": "openai/gpt-5.5"}],
                mask_token="******",
            )

        self.assertEqual(payload["primary_backend_id"], "litellm")
        self.assertFalse(payload["primary"]["available"])
        self.assertEqual(payload["primary"]["last_error_code"], "unsafe_config")

    def test_generation_backend_status_uses_runtime_provider_key_fallback(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
        )

        with patch.dict(
            os.environ,
            {
                "ENV_FILE": str(self.env_path),
                "GEMINI_API_KEY": "runtime-secret-value",
            },
            clear=True,
        ):
            payload = self.service.get_generation_backend_status()

        self.assertEqual(payload["primary_backend_id"], "litellm")
        self.assertTrue(payload["primary"]["available"])
        self.assertIsNone(payload["primary"]["last_error_code"])

    def test_generation_backend_preview_local_cli_ignores_inactive_litellm_model_error(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
        )

        with patch("src.llm.local_cli_backend.shutil.which", return_value=None):
            payload = self.service.preview_generation_backend_status(
                items=[
                    {"key": "GENERATION_BACKEND", "value": "codex_cli"},
                    {"key": "GENERATION_FALLBACK_BACKEND", "value": ""},
                ],
                mask_token="******",
            )

        self.assertEqual(payload["primary_backend_id"], "codex_cli")
        self.assertEqual(payload["primary"]["last_error_code"], "command_not_found")

    def test_generation_backend_preview_ignores_unrelated_draft_errors(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=litellm",
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
            "GEMINI_API_KEY=secret-key-value",
        )

        payload = self.service.preview_generation_backend_status(
            items=[{"key": "WECHAT_WEBHOOK_URL", "value": "not-a-url"}],
            mask_token="******",
        )

        self.assertEqual(payload["primary_backend_id"], "litellm")
        self.assertTrue(payload["primary"]["available"])

    def test_generation_backend_status_fallback_error_does_not_fail_primary(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "GENERATION_FALLBACK_BACKEND=bad_backend",
        )

        with patch("src.llm.local_cli_backend.shutil.which", return_value="/usr/bin/codex"), \
             patch("src.llm.local_cli_backend.os.access", return_value=True):
            payload = self.service.get_generation_backend_status()

        self.assertTrue(payload["primary"]["available"])
        self.assertEqual(payload["fallback"]["backend_id"], "bad_backend")
        self.assertFalse(payload["fallback"]["available"])

    def test_get_setup_status_treats_codex_cli_as_primary_runtime_without_api_keys(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/codex"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertFalse(status["is_complete"])
        self.assertTrue(status["ready_for_smoke"])
        self.assertEqual(checks["llm_primary"]["status"], "configured")
        self.assertEqual(checks["llm_agent"]["status"], "needs_action")
        self.assertIn("Codex CLI", checks["llm_primary"]["message"])
        self.assertNotIn("llm_primary", status["required_missing_keys"])
        self.assertIn("llm_agent", status["required_missing_keys"])

    def test_get_setup_status_allows_local_cli_primary_smoke_without_agent_model(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=claude_code_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "STOCK_LIST=AAPL",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/claude"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertFalse(status["is_complete"])
        self.assertTrue(status["ready_for_smoke"])
        self.assertEqual(checks["llm_primary"]["status"], "configured")
        self.assertEqual(checks["stock_list"]["status"], "configured")
        self.assertEqual(checks["llm_agent"]["status"], "needs_action")
        self.assertIn("本机 CLI 生成方式不会被自动继承", checks["llm_agent"]["message"])
        self.assertEqual(status["required_missing_keys"], ["llm_agent"])

    def test_get_setup_status_codex_cli_missing_reports_backend_path(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value=None):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["llm_primary"]["status"], "needs_action")
        self.assertIn("StockPulse 后端进程", checks["llm_primary"]["message"])
        self.assertNotIn("DSA 后端进程", checks["llm_primary"]["message"])
        self.assertIn("后端进程当前 PATH", checks["llm_primary"]["message"])
        self.assertIn("Codex CLI 交互窗口", checks["llm_primary"]["next_step"])
        self.assertNotIn("请先安装并登录", checks["llm_primary"]["next_step"])

    def test_get_setup_status_codex_primary_agent_model_explains_litellm_split(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "AGENT_LITELLM_MODEL=openai/gpt-5.5",
            "OPENAI_API_KEY=secret-key-value",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/codex"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["llm_agent"]["status"], "configured")
        self.assertIn("普通分析使用 Codex CLI", checks["llm_agent"]["message"])
        self.assertIn("Agent 工具调用仍使用主要模型", checks["llm_agent"]["message"])

    def test_get_setup_status_codex_primary_agent_inherited_model_explains_litellm_split(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "LITELLM_MODEL=openai/gpt-5.5",
            "OPENAI_API_KEY=secret-key-value",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/codex"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["llm_agent"]["status"], "configured")
        self.assertIn(
            "普通分析使用 Codex CLI；Agent 工具调用仍使用主要模型: openai/gpt-5.5",
            checks["llm_agent"]["message"],
        )

    def test_get_setup_status_claude_cli_primary_agent_inherited_model_uses_display_name(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=claude_code_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "LITELLM_MODEL=openai/gpt-5.5",
            "OPENAI_API_KEY=secret-key-value",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/claude"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["llm_agent"]["status"], "configured")
        self.assertIn(
            "普通分析使用 Claude Code CLI；Agent 工具调用仍使用主要模型: openai/gpt-5.5",
            checks["llm_agent"]["message"],
        )
        self.assertNotIn("Codex CLI", checks["llm_agent"]["message"])

    def test_get_setup_status_codex_primary_hermes_only_agent_inheritance_needs_action(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "LLM_CHANNELS=hermes",
            "LLM_HERMES_PROTOCOL=openai",
            "LLM_HERMES_BASE_URL=http://127.0.0.1:8765/v1",
            "LLM_HERMES_API_KEY=test-key",
            "LLM_HERMES_MODELS=hermes-agent",
            "LITELLM_MODEL=openai/hermes-agent",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/codex"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["llm_primary"]["status"], "configured")
        self.assertEqual(checks["llm_agent"]["status"], "needs_action")
        self.assertIn("Hermes", checks["llm_agent"]["message"])
        self.assertIn("llm_agent", status["required_missing_keys"])
        self.assertNotIn(
            "Agent 工具调用仍使用主要模型",
            checks["llm_agent"]["message"],
        )

    def test_get_setup_status_rejects_agent_codex_cli_tool_backend(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "AGENT_GENERATION_BACKEND=codex_cli",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/codex"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["llm_agent"]["status"], "needs_action")
        self.assertIn("暂不支持 codex_cli", checks["llm_agent"]["message"])

    def test_get_setup_status_rejects_agent_claude_and_opencode_tool_backends(self) -> None:
        for backend in ("claude_code_cli", "opencode_cli"):
            with self.subTest(backend=backend):
                self._rewrite_env(
                    "GENERATION_BACKEND=litellm",
                    f"AGENT_GENERATION_BACKEND={backend}",
                    "STOCK_LIST=600519",
                )

                with patch.dict(os.environ, {}, clear=True):
                    status = self.service.get_setup_status()

                checks = {check["key"]: check for check in status["checks"]}
                self.assertEqual(checks["llm_agent"]["status"], "needs_action")
                self.assertIn(f"暂不支持 {backend}", checks["llm_agent"]["message"])

    def test_get_setup_status_accepts_opencode_without_model_override(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=opencode_cli",
            "GENERATION_FALLBACK_BACKEND=",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/opencode"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["llm_primary"]["status"], "configured")
        self.assertIn("OpenCode CLI", checks["llm_primary"]["message"])

    def test_get_setup_status_agent_litellm_without_model_reports_missing_model(self) -> None:
        self._rewrite_env(
            "GENERATION_BACKEND=codex_cli",
            "AGENT_GENERATION_BACKEND=litellm",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True), \
             patch("src.services.system_config_service.shutil.which", return_value="/usr/bin/codex"):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["llm_agent"]["status"], "needs_action")
        self.assertIn("未检测到可用模型配置", checks["llm_agent"]["message"])
        self.assertNotIn("需要 LiteLLM backend", checks["llm_agent"]["message"])

    def test_get_setup_status_accepts_anspire_one_key_llm(self) -> None:
        self._rewrite_env(
            "ANSPIRE_API_KEYS=sk-anspire-test-value",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertTrue(status["is_complete"])
        self.assertEqual(checks["llm_primary"]["status"], "configured")
        self.assertIn("openai/Doubao-Seed-2.0-lite", checks["llm_primary"]["message"])

    def test_get_setup_status_treats_blank_anspire_channel_enabled_as_shared_disable(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=anspire",
            "LLM_ANSPIRE_ENABLED=",
            "ANSPIRE_LLM_ENABLED=false",
            "ANSPIRE_API_KEYS=sk-anspire-test-value",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertFalse(status["is_complete"])
        self.assertEqual(checks["llm_primary"]["status"], "needs_action")
        self.assertIn("llm_primary", status["required_missing_keys"])

    def test_get_setup_status_respects_disabled_anspire_channel_without_legacy_fallback(self) -> None:
        self._rewrite_env(
            "LLM_CHANNELS=anspire",
            "LLM_ANSPIRE_ENABLED=false",
            "ANSPIRE_API_KEYS=sk-anspire-test-value",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertFalse(status["is_complete"])
        self.assertEqual(checks["llm_primary"]["status"], "needs_action")
        self.assertIn("llm_primary", status["required_missing_keys"])

    def test_get_setup_status_accepts_direct_env_primary_without_provider_key(self) -> None:
        self._rewrite_env(
            "LITELLM_MODEL=minimax/MiniMax-M1",
            "STOCK_LIST=600519",
        )

        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertTrue(status["is_complete"])
        self.assertEqual(checks["llm_primary"]["status"], "configured")
        self.assertEqual(checks["llm_agent"]["status"], "inherited")

    def test_get_setup_status_matches_notification_channel_requirements(self) -> None:
        base_lines = [
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
            "GEMINI_API_KEY=secret-key-value",
            "STOCK_LIST=600519",
        ]

        self._rewrite_env(*base_lines, "PUSHOVER_USER_KEY=user-key")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        pushover_partial = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(pushover_partial["status"], "optional")

        self._rewrite_env(*base_lines, "PUSHOVER_USER_KEY=user-key", "PUSHOVER_API_TOKEN=app-token")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        pushover_complete = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(pushover_complete["status"], "configured")

        self._rewrite_env(*base_lines, "SLACK_BOT_TOKEN=xoxb-test", "SLACK_CHANNEL_ID=C123")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        slack_complete = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(slack_complete["status"], "configured")

        self._rewrite_env(*base_lines, "ASTRBOT_URL=https://astrbot.example/webhook")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        astrbot_complete = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(astrbot_complete["status"], "configured")

        self._rewrite_env(*base_lines, "NTFY_URL=https://ntfy.sh/dsa-topic")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        ntfy_complete = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(ntfy_complete["status"], "configured")

        self._rewrite_env(*base_lines, "NTFY_URL=https://ntfy.sh")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        ntfy_without_topic = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(ntfy_without_topic["status"], "optional")

        self._rewrite_env(*base_lines, "GOTIFY_URL=https://gotify.example")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        gotify_partial = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(gotify_partial["status"], "optional")

        self._rewrite_env(*base_lines, "GOTIFY_URL=https://gotify.example", "GOTIFY_TOKEN=app-token")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        gotify_complete = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(gotify_complete["status"], "configured")

        self._rewrite_env(*base_lines, "GOTIFY_URL=https://gotify.example/message", "GOTIFY_TOKEN=app-token")
        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()
        gotify_with_message = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(gotify_with_message["status"], "optional")

    def test_get_setup_status_accepts_feishu_app_bot_triad(self) -> None:
        self._rewrite_env(
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
            "GEMINI_API_KEY=secret-key-value",
            "STOCK_LIST=600519",
            "FEISHU_APP_ID=cli_xxx",
            "FEISHU_APP_SECRET=secret_xxx",
            "FEISHU_CHAT_ID=oc_xxx",
        )

        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()

        notification = next(check for check in status["checks"] if check["key"] == "notification")
        self.assertEqual(notification["status"], "configured")

    def test_get_setup_status_rejects_partial_feishu_app_bot_triad(self) -> None:
        base_lines = [
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
            "GEMINI_API_KEY=secret-key-value",
            "STOCK_LIST=600519",
        ]
        partial_cases = [
            ("FEISHU_APP_ID=cli_xxx", "FEISHU_APP_SECRET=secret_xxx"),
            ("FEISHU_APP_ID=cli_xxx", "FEISHU_CHAT_ID=oc_xxx"),
            ("FEISHU_APP_SECRET=secret_xxx", "FEISHU_CHAT_ID=oc_xxx"),
        ]

        for partial in partial_cases:
            with self.subTest(partial=partial):
                self._rewrite_env(*base_lines, *partial)
                with patch.dict(os.environ, {}, clear=True):
                    status = self.service.get_setup_status()
                notification = next(check for check in status["checks"] if check["key"] == "notification")
                self.assertEqual(notification["status"], "optional")

    def test_get_setup_status_uses_runtime_env_without_reloading_singletons(self) -> None:
        self._rewrite_env("")

        with patch.dict(
            os.environ,
            {
                "LITELLM_MODEL": "gemini/gemini-3-flash-preview",
                "GEMINI_API_KEY": "runtime-secret",
                "STOCK_LIST": "600519",
            },
            clear=True,
        ), patch("src.services.system_config_service.Config.reset_instance") as mock_reset, \
             patch("src.services.system_config_service.setup_env") as mock_setup_env:
            status = self.service.get_setup_status()

        self.assertTrue(status["is_complete"])
        mock_reset.assert_not_called()
        mock_setup_env.assert_not_called()

    def test_get_setup_status_storage_check_does_not_create_database_parent(self) -> None:
        missing_parent = Path(self.temp_dir.name) / "missing-data"
        db_path = missing_parent / "stock_analysis.db"
        self._rewrite_env(
            "LITELLM_MODEL=gemini/gemini-3-flash-preview",
            "GEMINI_API_KEY=secret-key-value",
            "STOCK_LIST=600519",
            f"DATABASE_PATH={db_path}",
        )

        with patch.dict(os.environ, {}, clear=True):
            status = self.service.get_setup_status()

        storage_check = next(check for check in status["checks"] if check["key"] == "storage")
        self.assertEqual(storage_check["status"], "configured")
        self.assertFalse(missing_parent.exists())

    def test_export_desktop_env_returns_raw_text(self) -> None:
        self.env_path.write_text(
            "# Desktop config\nSTOCK_LIST=600519,000001\n\nGEMINI_API_KEY=secret-key-value\n",
            encoding="utf-8",
        )

        payload = self.service.export_desktop_env()

        self.assertEqual(
            payload["content"],
            "# Desktop config\nSTOCK_LIST=600519,000001\n\nGEMINI_API_KEY=secret-key-value\n",
        )
        self.assertEqual(payload["config_version"], self.manager.get_config_version())

    def test_export_desktop_env_preserves_hidden_web_settings_keys(self) -> None:
        self.env_path.write_text(
            "STOCK_LIST=600519\nDATABASE_PATH=./custom/stock_analysis.db\nUSE_PROXY=true\n",
            encoding="utf-8",
        )

        payload = self.service.export_desktop_env()

        self.assertIn("DATABASE_PATH=./custom/stock_analysis.db\n", payload["content"])
        self.assertIn("USE_PROXY=true\n", payload["content"])

    def test_import_desktop_env_merges_keys_without_deleting_unspecified_values(self) -> None:
        current_version = self.manager.get_config_version()

        payload = self.service.import_desktop_env(
            config_version=current_version,
            content="STOCK_LIST=300750\nCUSTOM_NOTE=desktop backup\n",
            reload_now=False,
        )

        self.assertTrue(payload["success"])
        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["STOCK_LIST"], "300750")
        self.assertEqual(current_map["CUSTOM_NOTE"], "desktop backup")
        self.assertEqual(current_map["GEMINI_API_KEY"], "secret-key-value")

    def test_import_desktop_env_preserves_hidden_web_settings_keys(self) -> None:
        current_version = self.manager.get_config_version()

        self.service.import_desktop_env(
            config_version=current_version,
            content="DATABASE_PATH=./custom/stock_analysis.db\nPROXY_HOST=127.0.0.1\n",
            reload_now=False,
        )

        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["DATABASE_PATH"], "./custom/stock_analysis.db")
        self.assertEqual(current_map["PROXY_HOST"], "127.0.0.1")

    def test_import_desktop_env_treats_mask_token_as_literal_value(self) -> None:
        current_version = self.manager.get_config_version()

        self.service.import_desktop_env(
            config_version=current_version,
            content="GEMINI_API_KEY=******\n",
            reload_now=False,
        )

        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["GEMINI_API_KEY"], "******")

    def test_import_desktop_env_uses_last_duplicate_assignment(self) -> None:
        current_version = self.manager.get_config_version()

        self.service.import_desktop_env(
            config_version=current_version,
            content="STOCK_LIST=000001\nSTOCK_LIST=300750\n",
            reload_now=False,
        )

        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["STOCK_LIST"], "300750")

    def test_import_desktop_env_allows_empty_assignment(self) -> None:
        current_version = self.manager.get_config_version()

        self.service.import_desktop_env(
            config_version=current_version,
            content="LOG_LEVEL=\n",
            reload_now=False,
        )

        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["LOG_LEVEL"], "")

    def test_import_desktop_env_preserves_exported_braced_webhook_template(self) -> None:
        template = '{"content":${content_json}}'

        save_payload = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "CUSTOM_WEBHOOK_BODY_TEMPLATE", "value": template}],
            reload_now=False,
        )
        self.assertTrue(save_payload["success"])
        backup_content = self.service.export_desktop_env()["content"]
        self.assertIn(
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$${content_json}}\n',
            backup_content,
        )

        clear_payload = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[{"key": "CUSTOM_WEBHOOK_BODY_TEMPLATE", "value": ""}],
            reload_now=False,
        )
        self.assertTrue(clear_payload["success"])

        restore_payload = self.service.import_desktop_env(
            config_version=self.manager.get_config_version(),
            content=backup_content,
            reload_now=False,
        )

        self.assertTrue(restore_payload["success"])
        self.assertEqual(
            self.manager.read_config_map()["CUSTOM_WEBHOOK_BODY_TEMPLATE"],
            template,
        )

    def test_import_desktop_env_rejects_empty_or_comment_only_content(self) -> None:
        with self.assertRaises(ConfigImportError):
            self.service.import_desktop_env(
                config_version=self.manager.get_config_version(),
                content="   \n# only comments\n\n",
                reload_now=False,
            )

    def test_import_desktop_env_raises_conflict_for_stale_version(self) -> None:
        with self.assertRaises(ConfigConflictError):
            self.service.import_desktop_env(
                config_version="stale-version",
                content="STOCK_LIST=300750\n",
                reload_now=False,
            )

    def test_update_preserves_masked_secret(self) -> None:
        old_version = self.manager.get_config_version()
        response = self.service.update(
            config_version=old_version,
            items=[
                {"key": "GEMINI_API_KEY", "value": "******"},
                {"key": "STOCK_LIST", "value": "600519,300750"},
            ],
            mask_token="******",
            reload_now=False,
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["applied_count"], 1)
        self.assertEqual(response["skipped_masked_count"], 1)
        self.assertIn("STOCK_LIST", response["updated_keys"])

        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["STOCK_LIST"], "600519,300750")
        self.assertEqual(current_map["GEMINI_API_KEY"], "secret-key-value")

    def test_update_alphasift_enable_does_not_rewrite_llm_fields(self) -> None:
        self._rewrite_env(
            "STOCK_LIST=600519,000001",
            "LITELLM_MODEL=openai/gpt-4o-mini",
            "AGENT_LITELLM_MODEL=openai/gpt-4o",
            "OPENAI_BASE_URL=https://api.openai.com/v1",
            "LLM_CHANNELS=openai",
            "LLM_OPENAI_PROTOCOL=openai",
            "LLM_OPENAI_BASE_URL=https://api.openai.com/v1",
            "LLM_OPENAI_API_KEYS=legacy-openai-secret",
            "LLM_OPENAI_MODELS=openai/gpt-4o-mini,openai/gpt-4o",
            "LITELLM_FALLBACK_MODELS=openai/gpt-4o-mini,openai/gpt-4o",
            "ALPHASIFT_ENABLED=false",
            f"ALPHASIFT_INSTALL_SPEC={DEFAULT_ALPHASIFT_INSTALL_SPEC}",
            "LLM_USAGE_HMAC_SECRET=telemetry-secret",
            "LLM_USAGE_HMAC_KEY_VERSION=test-v1",
            "GEMINI_API_KEY=legacy-secret",
        )

        response = self.service.update(
            config_version=self.manager.get_config_version(),
            items=[
                {"key": "ALPHASIFT_ENABLED", "value": "true"},
                {"key": "ALPHASIFT_INSTALL_SPEC", "value": "******"},
                {"key": "LLM_USAGE_HMAC_SECRET", "value": "******"},
                {"key": "GEMINI_API_KEY", "value": "******"},
            ],
            mask_token="******",
            reload_now=False,
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["applied_count"], 1)
        self.assertIn("ALPHASIFT_ENABLED", response["updated_keys"])
        self.assertEqual(response["skipped_masked_count"], 3)

        current_map = self.manager.read_config_map()
        self.assertEqual(current_map["ALPHASIFT_ENABLED"], "true")
        self.assertEqual(
            current_map["ALPHASIFT_INSTALL_SPEC"],
            DEFAULT_ALPHASIFT_INSTALL_SPEC,
        )
        self.assertEqual(current_map["LLM_USAGE_HMAC_SECRET"], "telemetry-secret")
        self.assertEqual(current_map["LLM_USAGE_HMAC_KEY_VERSION"], "test-v1")
        self.assertEqual(current_map["GEMINI_API_KEY"], "legacy-secret")
        self.assertEqual(current_map["LITELLM_MODEL"], "openai/gpt-4o-mini")
        self.assertEqual(current_map["AGENT_LITELLM_MODEL"], "openai/gpt-4o")
        self.assertEqual(current_map["OPENAI_BASE_URL"], "https://api.openai.com/v1")
        self.assertEqual(current_map["LLM_CHANNELS"], "openai")
        self.assertEqual(current_map["LLM_OPENAI_PROTOCOL"], "openai")
        self.assertEqual(current_map["LLM_OPENAI_BASE_URL"], "https://api.openai.com/v1")
        self.assertEqual(current_map["LLM_OPENAI_API_KEYS"], "legacy-openai-secret")
        self.assertEqual(current_map["LLM_OPENAI_MODELS"], "openai/gpt-4o-mini,openai/gpt-4o")
        self.assertEqual(current_map["LITELLM_FALLBACK_MODELS"], "openai/gpt-4o-mini,openai/gpt-4o")
