# -*- coding: utf-8 -*-
"""AlphaSift install, task, and screening API contracts."""

from __future__ import annotations

from tests.alphasift_api_test_support import (
    os,
    sys,
    ModuleType,
    SimpleNamespace,
    Any,
    Dict,
    ANY,
    MagicMock,
    patch,
    threading,
    HTTPException,
    alphasift_endpoint,
    Config,
    OutboundPolicyError,
    alphasift_service,
    TaskInfo,
    QueueTaskStatus,
    DEFAULT_ALPHASIFT_TEST_SPEC,
    PUBLIC_DIAGNOSTIC_SECRET,
    _make_adapter_module,
    _missing_alphasift_module_diagnostics,
    _AlphaSiftApiTestCaseBase,
)


class AlphaSiftOpportunitiesApiTestCase(_AlphaSiftApiTestCaseBase):
    def test_strategies_rejects_when_enabled_but_adapter_missing(self) -> None:
        config = self._config(enabled=True)

        with (
            patch(
                "src.services.alphasift_service._get_alphasift_status_snapshot",
                return_value=({}, False, _missing_alphasift_module_diagnostics()),
            ),
            patch("src.services.alphasift_service._install_alphasift") as install_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._strategies(config=config)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_unavailable")
        self.assertEqual(caught.exception.detail.get("diagnostics", {}).get("reason"), "missing_module")
        install_mock.assert_not_called()

    def test_screen_rejects_when_disabled(self) -> None:
        config = self._config(enabled=False)

        with self.assertRaises(HTTPException) as caught:
            self._screen(config)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["error"], "alphasift_disabled")

    def test_screen_rejects_when_alphasift_unavailable(self) -> None:
        config = self._config(enabled=True)

        with (
            patch(
                "src.services.alphasift_service._get_alphasift_status_snapshot",
                return_value=({}, False, _missing_alphasift_module_diagnostics()),
            ),
            patch("src.services.alphasift_service._install_alphasift") as install_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_unavailable")
        self.assertEqual(caught.exception.detail.get("diagnostics", {}).get("reason"), "missing_module")
        self.assertIn("pip install -r requirements.txt", caught.exception.detail["message"])
        install_mock.assert_not_called()

    def test_start_screen_task_submits_background_work(self) -> None:
        config = self._config(enabled=True)
        fake_queue = MagicMock()
        fake_queue.submit_background_task.return_value = SimpleNamespace(
            task_id="screen-task-1",
            trace_id="screen-task-1",
            status=QueueTaskStatus.PENDING,
            message="AlphaSift 选股任务已提交",
        )

        with (
            patch("api.v1.endpoints.alphasift.get_task_queue", return_value=fake_queue),
            patch("api.v1.endpoints.alphasift.uuid.uuid4", return_value=SimpleNamespace(hex="screen-task-1")),
            patch.object(
                alphasift_endpoint.AlphaSiftService,
                "screen",
                return_value={"enabled": True, "candidates": [], "candidate_count": 0},
            ) as screen_mock,
        ):
            payload = alphasift_endpoint.alphasift_start_screen_task(
                alphasift_endpoint.AlphaSiftScreenRequest(market="cn", strategy="dual_low", max_results=3),
                http_request=self._request(),
                config=config,
            )
            run_task = fake_queue.submit_background_task.call_args.args[0]
            result = run_task()

        self.assertEqual(payload.task_id, "screen-task-1")
        self.assertEqual(payload.max_results, 3)
        fake_queue.submit_background_task.assert_called_once()
        self.assertEqual(fake_queue.submit_background_task.call_args.kwargs["report_type"], "alphasift_screen")
        self.assertEqual(
            fake_queue.submit_background_task.call_args.kwargs["failure_error_code"],
            "alphasift_screen_failed",
        )
        screen_mock.assert_called_once_with(strategy="dual_low", market="cn", max_results=3)
        self.assertEqual(result["candidate_count"], 0)
        fake_queue.update_task_progress.assert_any_call(
            "screen-task-1",
            20,
            "正在执行 AlphaSift 选股，外部数据源较慢时会持续后台运行",
        )

    def test_screen_task_status_returns_alphasift_result(self) -> None:
        task = TaskInfo(
            task_id="screen-task-1",
            trace_id="screen-task-1",
            stock_code="alphasift_screen",
            status=QueueTaskStatus.COMPLETED,
            progress=100,
            message="任务执行完成",
            result={"enabled": True, "candidates": [], "candidate_count": 0},
            report_type="alphasift_screen",
        )
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = task

        with patch("api.v1.endpoints.alphasift.get_task_queue", return_value=fake_queue):
            payload = alphasift_endpoint.alphasift_screen_task_status("screen-task-1")

        self.assertEqual(payload.status, "completed")
        self.assertEqual(payload.result["candidate_count"], 0)

    def test_screen_task_status_does_not_expose_legacy_diagnostic_text(self) -> None:
        secret_marker = "Authorization: Bearer sk-alphasift-secret-marker"
        task = TaskInfo(
            task_id="screen-task-failed",
            trace_id="trace-screen-task-failed",
            stock_code="alphasift_screen",
            status=QueueTaskStatus.FAILED,
            progress=40,
            message=f"任务失败: {secret_marker}",
            message_code="task.failed",
            error=secret_marker,
            diagnostic_error=secret_marker,
            failure_error_code="alphasift_screen_failed",
            report_type="alphasift_screen",
        )
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = task

        with patch("api.v1.endpoints.alphasift.get_task_queue", return_value=fake_queue):
            payload = alphasift_endpoint.alphasift_screen_task_status(task.task_id)

        self.assertEqual(payload.error, "alphasift_screen_failed")
        self.assertEqual(payload.message, "任务执行失败")
        self.assertNotIn(secret_marker, payload.model_dump_json())

    def test_screen_task_status_rejects_non_alphasift_task(self) -> None:
        task = TaskInfo(
            task_id="analysis-task-1",
            stock_code="600519",
            status=QueueTaskStatus.COMPLETED,
            report_type="detailed",
        )
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = task

        with patch("api.v1.endpoints.alphasift.get_task_queue", return_value=fake_queue):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_screen_task_status("analysis-task-1")

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail["error"], "alphasift_screen_task_not_found")

    def test_screen_does_not_auto_install_when_adapter_runtime_unavailable(self) -> None:
        config = self._config(enabled=True)

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch(
                "src.services.alphasift_service._get_alphasift_status_snapshot",
                return_value=(
                    {},
                    False,
                    {"reason": "unexpected_exception", "stage": "get_status", "error_type": "RuntimeError"},
                ),
            ),
            patch("src.services.alphasift_service._install_alphasift") as install_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_unavailable")
        self.assertEqual(caught.exception.detail.get("diagnostics", {}).get("resolution"), "no_auto_install")
        self.assertEqual(
            caught.exception.detail.get("diagnostics", {}).get("message"),
            "请先检查后端日志并修复运行时异常，当前未触发修复安装。",
        )
        install_mock.assert_not_called()

    def test_install_rejects_spoofed_localhost_without_admin_session(self) -> None:
        config = self._config(enabled=True)
        request = SimpleNamespace(
            cookies={alphasift_service.COOKIE_NAME: "invalid-session"},
            url=SimpleNamespace(hostname="localhost"),
            client=SimpleNamespace(host="127.0.0.1"),
        )

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "false"}, clear=False),
            patch("src.services.alphasift_service.refresh_auth_state") as refresh_mock,
            patch("src.services.alphasift_service.is_auth_enabled", return_value=True),
            patch("src.services.alphasift_service.verify_session", return_value=False) as verify_session_mock,
            patch("src.services.alphasift_service.subprocess.run") as run_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=request, config=config)

        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.detail["error"], "alphasift_install_access_denied")
        refresh_mock.assert_called_once()
        verify_session_mock.assert_called_once_with("invalid-session")
        run_mock.assert_not_called()

    def test_install_allows_valid_admin_session_outside_desktop_mode(self) -> None:
        config = self._config(enabled=True)
        request = self._request({alphasift_service.COOKIE_NAME: "valid-session"})

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "false"}, clear=False),
            patch("src.services.alphasift_service.refresh_auth_state") as refresh_mock,
            patch("src.services.alphasift_service.is_auth_enabled", return_value=True),
            patch("src.services.alphasift_service.verify_session", return_value=True) as verify_session_mock,
            patch("src.services.alphasift_service._install_alphasift", return_value={"installed": True}) as install_mock,
        ):
            payload = alphasift_endpoint.alphasift_install(request=request, config=config)

        self.assertEqual(payload["installed"], True)
        refresh_mock.assert_called_once()
        verify_session_mock.assert_called_once_with("valid-session")
        install_mock.assert_called_once_with(config)

    def test_install_rejects_when_disabled_without_side_effects(self) -> None:
        config = self._config(enabled=False)

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service.subprocess.run") as run_mock,
            patch("src.services.alphasift_service._import_alphasift") as import_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["error"], "alphasift_disabled")
        import_mock.assert_not_called()
        run_mock.assert_not_called()

    def test_install_invokes_pip_when_enabled_and_missing(self) -> None:
        config = self._config(enabled=True)
        completed = SimpleNamespace(returncode=0, stdout="installed", stderr="")

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", side_effect=[False, True]),
            patch(
                "src.services.alphasift_service._call_alphasift_status",
                return_value={"available": True, "supported_markets": ["cn"], "contract_version": "1", "version": "0.2.0", "strategy_count": 1},
            ),
            patch("src.services.alphasift_service.subprocess.run", return_value=completed) as run_mock,
            patch("src.services.alphasift_service._get_dsa_adapter", return_value=_make_adapter_module()),
        ):
            payload = alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(payload["installed"], True)
        self.assertEqual(payload["already_installed"], False)
        self.assertEqual(payload["install_spec_is_default"], True)
        self.assertNotIn("install_spec", payload)
        run_mock.assert_called_once()
        install_command = run_mock.call_args.args[0]
        self.assertIn("--upgrade", install_command)
        self.assertIn("--force-reinstall", install_command)
        self.assertIn(DEFAULT_ALPHASIFT_TEST_SPEC, install_command)

    def test_install_start_failure_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", return_value=False),
            patch("src.services.alphasift_service.subprocess.run", side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET)),
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.detail["error"], "alphasift_install_failed")
        self.assertEqual(caught.exception.detail["message"], "修复安装 AlphaSift 失败，请检查后端日志。")
        self.assert_public_payload_is_private(caught.exception.detail)

    def test_install_command_failure_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)
        completed = SimpleNamespace(returncode=1, stdout="", stderr=PUBLIC_DIAGNOSTIC_SECRET)

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", return_value=False),
            patch("src.services.alphasift_service.subprocess.run", return_value=completed),
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.detail["error"], "alphasift_install_failed")
        self.assertEqual(caught.exception.detail["message"], "修复安装 AlphaSift 失败，请检查后端日志。")
        self.assert_public_payload_is_private(caught.exception.detail)

    def test_install_rejects_when_alphasift_adapter_reports_unavailable(self) -> None:
        config = self._config(enabled=True)
        completed = SimpleNamespace(returncode=0, stdout="installed", stderr="")

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch(
                "src.services.alphasift_service._call_alphasift_status",
                side_effect=[
                    {"available": False},
                    {"available": False},
                ],
            ),
            patch("src.services.alphasift_service.subprocess.run", return_value=completed) as run_mock,
            patch("src.services.alphasift_service._get_dsa_adapter") as get_adapter_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_unavailable")
        run_mock.assert_called_once()
        get_adapter_mock.assert_not_called()

    def test_install_rejects_untrusted_spec(self) -> None:
        config = self._config(enabled=True, install_spec="git+https://example.com/private/alphasift.git")

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", return_value=False),
            patch("src.services.alphasift_service.subprocess.run") as run_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["error"], "alphasift_install_spec_not_allowed")
        run_mock.assert_not_called()

    def test_screen_calls_dsa_adapter_and_normalizes_llm_fields(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "run_id": "run123",
                    "strategy": "dual_low",
                    "market": "cn",
                    "snapshot_count": 100,
                    "snapshot_source": "em_datacenter",
                    "after_filter_count": 5,
                    "llm_ranked": True,
                    "llm_coverage": 1.0,
                    "warnings": "fallback",
                    "source_errors": "sina timeout",
                    "llm_parse_errors": "retry parsed partial JSON",
                    "deep_analysis_requested": False,
                    "post_analyzers": ["scorecard"],
                    "daily_enriched": True,
                    "daily_enrich_count": 12,
                    "risk_enabled": True,
                    "portfolio_diversity_enabled": True,
                    "portfolio_concentration_notes": ["sector concentration adjusted"],
                    "candidates": [
                        {
                            "code": "600519",
                            "name": "Kweichow Moutai",
                            "score": 88.5,
                            "llm_score": 90.0,
                            "llm_thesis": "LLM likes the setup",
                            "risk_level": "medium",
                            "risk_flags": ["valuation"],
                            "price": 1688.0,
                            "industry": "Baijiu",
                            "factor_scores": {"value": 88.0},
                        }
                    ],
                }
            ),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        fake_module.screen.assert_called_once_with(
            "dual_low",
            market="cn",
            max_results=5,
            use_llm=True,
            context=ANY,
        )
        self.assertEqual(fake_module.screen.call_args.kwargs["context"]["llm"]["model"], "")
        self.assertEqual(payload["run_id"], "run123")
        self.assertEqual(payload["snapshot_count"], 100)
        self.assertEqual(payload["snapshot_source"], "em_datacenter")
        self.assertEqual(payload["after_filter_count"], 5)
        self.assertEqual(payload["llm_ranked"], True)
        self.assertEqual(payload["llm_coverage"], 1.0)
        self.assertEqual(payload["warnings"], ["alphasift_warning"])
        self.assertEqual(payload["source_errors"], ["alphasift_source_error"])
        self.assertEqual(payload["llm_parse_errors"], ["alphasift_llm_parse_error"])
        self.assertEqual(payload["candidate_count"], 1)
        self.assertEqual(payload["post_analyzers"], ["scorecard"])
        self.assertEqual(payload["daily_enriched"], True)
        self.assertEqual(payload["daily_enrich_count"], 12)
        self.assertEqual(payload["portfolio_concentration_notes"], ["sector concentration adjusted"])
        self.assertEqual(payload["candidates"][0]["code"], "600519")
        self.assertEqual(payload["candidates"][0]["llm_score"], 90.0)
        self.assertEqual(payload["candidates"][0]["llm_thesis"], "LLM likes the setup")
        self.assertEqual(payload["candidates"][0]["risk_level"], "medium")
        self.assertEqual(payload["candidates"][0]["price"], 1688.0)
        self.assertEqual(payload["candidates"][0]["industry"], "Baijiu")

    def test_screen_success_hides_raw_adapter_diagnostics_recursively(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(return_value={
                "warnings": [PUBLIC_DIAGNOSTIC_SECRET],
                "source_errors": [PUBLIC_DIAGNOSTIC_SECRET],
                "llm_parse_errors": [PUBLIC_DIAGNOSTIC_SECRET],
                "candidates": [{
                    "code": "600519",
                    "warnings": [PUBLIC_DIAGNOSTIC_SECRET],
                    "source_errors": [PUBLIC_DIAGNOSTIC_SECRET],
                    "exception": PUBLIC_DIAGNOSTIC_SECRET,
                    "error": PUBLIC_DIAGNOSTIC_SECRET,
                    "error_message": PUBLIC_DIAGNOSTIC_SECRET,
                    "errorMessage": PUBLIC_DIAGNOSTIC_SECRET,
                    "error_msg": PUBLIC_DIAGNOSTIC_SECRET,
                    "errorMsg": PUBLIC_DIAGNOSTIC_SECRET,
                    "error_code": PUBLIC_DIAGNOSTIC_SECRET,
                    "errorReason": PUBLIC_DIAGNOSTIC_SECRET,
                    "last_error": PUBLIC_DIAGNOSTIC_SECRET,
                    "lastError": PUBLIC_DIAGNOSTIC_SECRET,
                    "last_error_message": PUBLIC_DIAGNOSTIC_SECRET,
                    "last_error_code": "stock_news_failed",
                    "diagnostic_error": PUBLIC_DIAGNOSTIC_SECRET,
                    "response_error": PUBLIC_DIAGNOSTIC_SECRET,
                    "raw_error": PUBLIC_DIAGNOSTIC_SECRET,
                    "errors": [PUBLIC_DIAGNOSTIC_SECRET],
                    "error_messages": [PUBLIC_DIAGNOSTIC_SECRET],
                    "responseErrors": [PUBLIC_DIAGNOSTIC_SECRET],
                    "nested": {
                        "error": "stock_news_unavailable",
                        "errors": ["stock_news_failed", PUBLIC_DIAGNOSTIC_SECRET],
                    },
                    "diagnostics": {
                        "endpoint": PUBLIC_DIAGNOSTIC_SECRET,
                        "note": "provider returned a partial business payload",
                        "public_url": "https://docs.example.invalid/alphasift",
                        PUBLIC_DIAGNOSTIC_SECRET: "failed",
                    },
                    "debug_message": PUBLIC_DIAGNOSTIC_SECRET,
                }],
            }),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=1)

        self.assertEqual(payload["warnings"], ["alphasift_warning"])
        self.assertEqual(payload["source_errors"], ["alphasift_source_error"])
        self.assertEqual(payload["llm_parse_errors"], ["alphasift_llm_parse_error"])
        raw = payload["candidates"][0]["raw"]
        self.assertEqual(raw["exception"], "alphasift_internal_error")
        for key in (
            "error",
            "error_message",
            "errorMessage",
            "error_msg",
            "errorMsg",
            "error_code",
            "errorReason",
            "last_error",
            "lastError",
            "last_error_message",
            "diagnostic_error",
            "response_error",
            "raw_error",
        ):
            self.assertEqual(raw[key], "alphasift_error")
            self.assertIsInstance(raw[key], str)
        self.assertEqual(raw["errors"], ["alphasift_error"])
        self.assertEqual(raw["error_messages"], ["alphasift_error"])
        self.assertEqual(raw["responseErrors"], ["alphasift_error"])
        self.assertEqual(raw["last_error_code"], "stock_news_failed")
        self.assertEqual(raw["nested"]["error"], "stock_news_unavailable")
        self.assertEqual(raw["nested"]["errors"], ["stock_news_failed", "alphasift_error"])
        self.assertNotIn(PUBLIC_DIAGNOSTIC_SECRET, raw["diagnostics"]["endpoint"])
        self.assertIn("[REDACTED]", raw["diagnostics"]["endpoint"])
        self.assertIn("[REDACTED_URL]", raw["diagnostics"]["endpoint"])
        self.assertEqual(
            raw["diagnostics"]["note"],
            "provider returned a partial business payload",
        )
        self.assertEqual(
            raw["diagnostics"]["public_url"],
            "https://docs.example.invalid/alphasift",
        )
        diagnostic_keys = list(raw["diagnostics"])
        self.assertIn("Authorization: [REDACTED] [REDACTED_URL]", diagnostic_keys)
        self.assertNotIn(PUBLIC_DIAGNOSTIC_SECRET, diagnostic_keys)
        self.assertNotIn(PUBLIC_DIAGNOSTIC_SECRET, raw["debug_message"])
        self.assertIn("[REDACTED]", raw["debug_message"])
        self.assertIn("[REDACTED_URL]", raw["debug_message"])
        self.assert_public_payload_is_private(payload)

    def test_screen_news_enrichment_exception_hides_raw_error_field(self) -> None:
        config = self._config(enabled=True)
        fake_manager = SimpleNamespace(get_stock_name=MagicMock(return_value="贵州茅台"))
        fake_module = _make_adapter_module(
            screen=MagicMock(return_value={
                "candidates": [{"code": "600519", "score": 88.5}],
            }),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service._get_dsa_fetcher_manager", return_value=fake_manager),
            patch("src.services.alphasift_service.get_dsa_realtime_quote", return_value={}),
            patch("src.services.alphasift_service.get_dsa_fundamental_context", return_value={}),
            patch(
                "src.services.alphasift_service.search_dsa_stock_news",
                side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET),
            ),
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=1,
                mock_enrichment=False,
            )

        news = payload["candidates"][0]["dsa_context"]["news"]
        self.assertEqual(news["error"], "stock_news_failed")
        self.assertIsInstance(news["error"], str)
        self.assertEqual(
            payload["dsa_enrichment"]["warnings"],
            ["dsa_realtime_quote_missing", "stock_news_failed"],
        )
        self.assert_public_payload_is_private(payload)

    def test_screen_prefers_dsa_daily_history_for_alphasift_enrichment(self) -> None:
        config = self._config(enabled=True)
        parent_module = ModuleType("alphasift")
        daily_module = ModuleType("alphasift.daily")
        original_daily_fetch = MagicMock(side_effect=AssertionError("AlphaSift daily fetch should not run first"))
        daily_module.fetch_daily_history = original_daily_fetch
        parent_module.daily = daily_module
        captured: Dict[str, Any] = {}

        def screen_with_daily_fetch(strategy: str, **kwargs: Any) -> Dict[str, Any]:
            daily_df = daily_module.fetch_daily_history(
                "600519",
                lookback_days=20,
                source="akshare",
                retries=1,
            )
            captured["daily_df"] = daily_df
            captured["context"] = kwargs.get("context")
            return {
                "strategy": strategy,
                "candidates": [{"code": "600519", "score": 88.0}],
            }

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_with_daily_fetch))

        with (
            patch.dict(sys.modules, {"alphasift": parent_module, "alphasift.daily": daily_module}),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch(
                "src.services.alphasift_service.get_dsa_daily_history",
                return_value=(
                    [
                        {
                            "trade_date": "20260603",
                            "close": "10.5",
                            "vol": "123400",
                        }
                    ],
                    "EfinanceFetcher",
                ),
            ) as dsa_history_mock,
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        daily_df = captured["daily_df"]
        self.assertEqual(daily_df.attrs["source"], "dsa:EfinanceFetcher")
        self.assertEqual(daily_df.loc[0, "date"], "2026-06-03")
        self.assertEqual(daily_df.loc[0, "volume"], 123400)
        self.assertEqual(daily_df.loc[0, "open"], 10.5)
        self.assertEqual(payload["candidate_count"], 1)
        self.assertIn("daily_history", captured["context"]["dsa"]["capabilities"])
        self.assertIs(captured["context"]["dsa"]["get_daily_history"], dsa_history_mock)
        dsa_history_mock.assert_called_once_with("600519", lookback_days=20)
        original_daily_fetch.assert_not_called()
        self.assertIs(daily_module.fetch_daily_history, original_daily_fetch)

    def test_screen_enriches_top_candidates_with_dsa_context(self) -> None:
        config = self._config(enabled=True)
        fake_manager = SimpleNamespace(get_stock_name=MagicMock(return_value="贵州茅台"))
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "candidates": [
                        {
                            "code": "600519",
                            "score": 88.5,
                            "reason": "AlphaSift pick",
                        }
                    ]
                }
            ),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service._get_dsa_fetcher_manager", return_value=fake_manager),
            patch(
                "src.services.alphasift_service.get_dsa_realtime_quote",
                return_value={"price": 1688.0, "change_pct": 1.2, "amount": 100000000.0},
            ),
            patch(
                "src.services.alphasift_service.get_dsa_fundamental_context",
                return_value={"market": "cn", "coverage": {"valuation": "available"}},
            ),
            patch(
                "src.services.alphasift_service.search_dsa_stock_news",
                return_value={
                    "success": True,
                    "provider": "test",
                    "results": [{"title": "贵州茅台最新公告", "source": "测试源"}],
                },
            ),
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=5,
                mock_enrichment=False,
            )

        candidate = payload["candidates"][0]
        self.assertEqual(candidate["name"], "贵州茅台")
        self.assertEqual(candidate["price"], 1688.0)
        self.assertTrue(candidate["dsa_context"]["enriched"])
        self.assertEqual(candidate["dsa_news"][0]["title"], "贵州茅台最新公告")
        self.assertIn("StockPulse 行情", candidate["dsa_analysis_summary"])
        self.assertNotIn("DSA行情", candidate["dsa_analysis_summary"])
        self.assertEqual(payload["dsa_enrichment"]["enriched_count"], 1)

    def test_screen_reuses_alphasift_dsa_context_without_refetch(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "candidates": [
                        {
                            "code": "600519",
                            "name": "贵州茅台",
                            "score": 88.5,
                            "dsa_context": {
                                "enriched": True,
                                "quote": {"price": 1688.0, "change_pct": 1.2},
                                "warnings": ["from_alphasift_provider"],
                            },
                            "dsa_news": [{"title": "贵州茅台最新公告", "source": "测试源"}],
                            "dsa_analysis_summary": "DSA新闻: 贵州茅台最新公告",
                        }
                    ]
                }
            ),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service.get_dsa_realtime_quote") as quote_mock,
            patch("src.services.alphasift_service.get_dsa_fundamental_context") as fundamentals_mock,
            patch("src.services.alphasift_service.search_dsa_stock_news") as news_mock,
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=5,
                mock_enrichment=False,
            )

        candidate = payload["candidates"][0]
        self.assertTrue(candidate["dsa_context"]["enriched"])
        self.assertEqual(candidate["dsa_news"][0]["title"], "贵州茅台最新公告")
        self.assertEqual(candidate["dsa_analysis_summary"], "DSA新闻: 贵州茅台最新公告")
        self.assertEqual(payload["dsa_enrichment"]["enriched_count"], 1)
        self.assertEqual(payload["dsa_enrichment"]["warnings"], ["alphasift_warning"])
        quote_mock.assert_not_called()
        fundamentals_mock.assert_not_called()
        news_mock.assert_not_called()

    def test_screen_reuses_context_news_results_without_refetch(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "candidates": [
                        {
                            "code": "600519",
                            "name": "贵州茅台",
                            "score": 88.5,
                            "dsa_context": {
                                "enriched": True,
                                "quote": {"price": 1688.0, "change_pct": 1.2},
                                "news": {
                                    "success": True,
                                    "summary": "DSA新闻：贵州茅台最新公告",
                                    "results": [{"title": "贵州茅台最新公告", "source": "测试源"}],
                                },
                                "warnings": ["from_alphasift_provider"],
                            },
                            "dsa_news": [],
                        }
                    ]
                }
            ),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service.get_dsa_realtime_quote") as quote_mock,
            patch("src.services.alphasift_service.get_dsa_fundamental_context") as fundamentals_mock,
            patch("src.services.alphasift_service.search_dsa_stock_news") as news_mock,
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=5,
                mock_enrichment=False,
            )

        candidate = payload["candidates"][0]
        self.assertEqual(candidate["dsa_news"][0]["title"], "贵州茅台最新公告")
        self.assertEqual(candidate["dsa_analysis_summary"], "DSA新闻：贵州茅台最新公告")
        self.assertEqual(payload["dsa_enrichment"]["enriched_count"], 1)
        self.assertEqual(payload["dsa_enrichment"]["warnings"], ["alphasift_warning"])
        quote_mock.assert_not_called()
        fundamentals_mock.assert_not_called()
        news_mock.assert_not_called()

    def test_screen_completes_light_alphasift_context_with_news_only(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "candidates": [
                        {
                            "code": "600519",
                            "name": "贵州茅台",
                            "score": 88.5,
                            "dsa_context": {
                                "enriched": True,
                                "profile": "pre_rank_light",
                                "news_included": False,
                                "quote": {"price": 1688.0, "change_pct": 1.2},
                                "fundamentals": {"coverage": {"valuation": "available"}},
                                "news": {
                                    "success": False,
                                    "skipped": True,
                                    "reason": "pre_rank_light_context",
                                    "results": [],
                                },
                            },
                            "dsa_news": [],
                            "dsa_analysis_summary": "DSA行情: 现价 1688.0",
                        }
                    ]
                }
            ),
        )
        fake_manager = SimpleNamespace(get_stock_name=MagicMock(return_value="贵州茅台"))

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            patch("src.services.alphasift_service._get_dsa_fetcher_manager", return_value=fake_manager),
            patch("src.services.alphasift_service.get_dsa_realtime_quote") as quote_mock,
            patch("src.services.alphasift_service.get_dsa_fundamental_context") as fundamentals_mock,
            patch(
                "src.services.alphasift_service.search_dsa_stock_news",
                return_value={
                    "success": True,
                    "provider": "test",
                    "results": [{"title": "贵州茅台最新公告", "source": "测试源"}],
                },
            ) as news_mock,
        ):
            payload = self._screen(
                config,
                market="cn",
                strategy="dual_low",
                max_results=5,
                mock_enrichment=False,
            )

        candidate = payload["candidates"][0]
        self.assertEqual(candidate["dsa_context"]["profile"], "post_rank_full")
        self.assertTrue(candidate["dsa_context"]["news_included"])
        self.assertEqual(candidate["dsa_context"]["quote"]["price"], 1688.0)
        self.assertEqual(candidate["dsa_context"]["fundamentals"]["coverage"]["valuation"], "available")
        self.assertEqual(candidate["dsa_news"][0]["title"], "贵州茅台最新公告")
        quote_mock.assert_not_called()
        fundamentals_mock.assert_not_called()
        news_mock.assert_called_once()

    def test_dsa_pre_rank_candidate_context_omits_news(self) -> None:
        fake_manager = SimpleNamespace(get_stock_name=MagicMock(return_value="贵州茅台"))

        with (
            patch("src.services.alphasift_service._get_dsa_fetcher_manager", return_value=fake_manager),
            patch(
                "src.services.alphasift_service.get_dsa_realtime_quote",
                return_value={"price": 1688.0, "change_pct": 1.2, "amount": 100000000.0},
            ),
            patch(
                "src.services.alphasift_service.get_dsa_fundamental_context",
                return_value={"market": "cn", "coverage": {"valuation": "available"}},
            ),
            patch("src.services.alphasift_service.search_dsa_stock_news") as news_mock,
        ):
            context = alphasift_service.get_dsa_candidate_context("600519", "贵州茅台")

        self.assertEqual(context["profile"], "pre_rank_light")
        self.assertFalse(context["news_included"])
        self.assertTrue(context["news"]["skipped"])
        self.assertEqual(context["quote"]["price"], 1688.0)
        self.assertEqual(context["fundamentals"]["coverage"]["valuation"], "available")
        news_mock.assert_not_called()

    def test_screen_bridges_dsa_llm_config_into_alphasift_runtime(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-2.5-flash",
            litellm_fallback_models=["deepseek/deepseek-chat"],
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "base_url": "",
                    "api_keys": ["dsa-gemini-key"],
                    "models": ["gemini/gemini-2.5-flash"],
                    "extra_headers": {"x-tenant": "dsa"},
                }
            ],
        )
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **kwargs):
            captured["env"] = {
                "LITELLM_MODEL": alphasift_service.os.environ.get("LITELLM_MODEL"),
                "LITELLM_FALLBACK_MODELS": alphasift_service.os.environ.get("LITELLM_FALLBACK_MODELS"),
                "LLM_CHANNELS": alphasift_service.os.environ.get("LLM_CHANNELS"),
                "LLM_GEMINI_PROTOCOL": alphasift_service.os.environ.get("LLM_GEMINI_PROTOCOL"),
                "LLM_GEMINI_API_KEYS": alphasift_service.os.environ.get("LLM_GEMINI_API_KEYS"),
                "LLM_GEMINI_EXTRA_HEADERS": alphasift_service.os.environ.get("LLM_GEMINI_EXTRA_HEADERS"),
                "GEMINI_API_KEY": alphasift_service.os.environ.get("GEMINI_API_KEY"),
                "LLM_CANDIDATE_CONTEXT_ENABLED": alphasift_service.os.environ.get("LLM_CANDIDATE_CONTEXT_ENABLED"),
                "LLM_CANDIDATE_CONTEXT_PROVIDERS": alphasift_service.os.environ.get("LLM_CANDIDATE_CONTEXT_PROVIDERS"),
                "LLM_CANDIDATE_MULTIPLIER": alphasift_service.os.environ.get("LLM_CANDIDATE_MULTIPLIER"),
                "LLM_MAX_CANDIDATES": alphasift_service.os.environ.get("LLM_MAX_CANDIDATES"),
                "DAILY_SOURCE": alphasift_service.os.environ.get("DAILY_SOURCE"),
                "DAILY_FETCH_RETRIES": alphasift_service.os.environ.get("DAILY_FETCH_RETRIES"),
                "DAILY_FETCH_MAX_WORKERS": alphasift_service.os.environ.get("DAILY_FETCH_MAX_WORKERS"),
                "SNAPSHOT_SOURCE_PRIORITY": alphasift_service.os.environ.get("SNAPSHOT_SOURCE_PRIORITY"),
                "ALPHASIFT_DATA_DIR": alphasift_service.os.environ.get("ALPHASIFT_DATA_DIR"),
                "ALPHASIFT_FALLBACK_SNAPSHOT_PATH": alphasift_service.os.environ.get("ALPHASIFT_FALLBACK_SNAPSHOT_PATH"),
                "ALPHASIFT_DAILY_HISTORY_CACHE_DIR": alphasift_service.os.environ.get("ALPHASIFT_DAILY_HISTORY_CACHE_DIR"),
                "ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR": alphasift_service.os.environ.get("ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR"),
            }
            captured["context"] = kwargs.get("context")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(
                alphasift_service.os.environ,
                {
                    "GEMINI_API_KEY": "outer-key",
                    "SNAPSHOT_SOURCE_PRIORITY": "",
                    "LLM_CANDIDATE_CONTEXT_ENABLED": "true",
                    "LLM_CANDIDATE_MULTIPLIER": "",
                    "LLM_MAX_CANDIDATES": "",
                    "DAILY_FETCH_RETRIES": "",
                    "DAILY_FETCH_MAX_WORKERS": "",
                },
                clear=False,
            ),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)
            self.assertEqual(alphasift_service.os.environ.get("GEMINI_API_KEY"), "outer-key")

        runtime_env = captured["env"]
        self.assertIsInstance(runtime_env, dict)
        self.assertEqual(runtime_env["LITELLM_MODEL"], "gemini/gemini-2.5-flash")
        self.assertEqual(runtime_env["LITELLM_FALLBACK_MODELS"], "deepseek/deepseek-chat")
        self.assertEqual(runtime_env["LLM_CHANNELS"], "gemini")
        self.assertEqual(runtime_env["LLM_GEMINI_PROTOCOL"], "gemini")
        self.assertEqual(runtime_env["LLM_GEMINI_API_KEYS"], "dsa-gemini-key")
        self.assertEqual(runtime_env["LLM_GEMINI_EXTRA_HEADERS"], '{"x-tenant": "dsa"}')
        self.assertEqual(runtime_env["GEMINI_API_KEY"], "dsa-gemini-key")
        self.assertEqual(runtime_env["LLM_CANDIDATE_CONTEXT_ENABLED"], "false")
        self.assertEqual(runtime_env["LLM_CANDIDATE_CONTEXT_PROVIDERS"], "news,fund_flow,announcement,quote")
        self.assertEqual(runtime_env["LLM_CANDIDATE_MULTIPLIER"], "2")
        self.assertEqual(runtime_env["LLM_MAX_CANDIDATES"], "10")
        self.assertEqual(runtime_env["DAILY_SOURCE"], "auto")
        self.assertEqual(runtime_env["DAILY_FETCH_RETRIES"], "3")
        self.assertEqual(runtime_env["DAILY_FETCH_MAX_WORKERS"], "1")
        self.assertEqual(runtime_env["SNAPSHOT_SOURCE_PRIORITY"], "sina,efinance,akshare_em,em_datacenter")
        self.assertEqual(runtime_env["ALPHASIFT_DATA_DIR"], str(alphasift_service.DSA_ALPHASIFT_DATA_DIR))
        self.assertEqual(
            runtime_env["ALPHASIFT_FALLBACK_SNAPSHOT_PATH"],
            str(alphasift_service.DSA_ALPHASIFT_DATA_DIR / "snapshot.last_good.json"),
        )
        self.assertEqual(
            runtime_env["ALPHASIFT_DAILY_HISTORY_CACHE_DIR"],
            str(alphasift_service.DSA_ALPHASIFT_DATA_DIR / "daily_history"),
        )
        self.assertEqual(
            runtime_env["ALPHASIFT_INDUSTRY_PROVIDER_CACHE_DIR"],
            str(alphasift_service.DSA_ALPHASIFT_DATA_DIR / "industry_provider_cache"),
        )
        context = captured["context"]
        self.assertIsInstance(context, dict)
        self.assertEqual(context["llm"]["model"], "gemini/gemini-2.5-flash")
        self.assertFalse(context["llm"]["candidate_context_enabled"])
        self.assertEqual(context["llm"]["candidate_multiplier"], 2)
        self.assertEqual(context["llm"]["max_candidates"], 10)
        self.assertEqual(context["llm"]["channels"][0]["api_keys"], ["dsa-gemini-key"])
        self.assertEqual(context["llm"]["channels"][0]["extra_headers"], {"x-tenant": "dsa"})
        self.assertEqual(context["llm"]["model_list"][0]["litellm_params"]["extra_headers"], {"x-tenant": "dsa"})
        self.assertIn("get_candidate_context", context["dsa"])
        self.assertEqual(context["dsa"]["mode"], "pre_rank_light")
        self.assertEqual(context["dsa"]["max_candidates"], 3)
        self.assertFalse(context["dsa"]["include_news"])
        self.assertNotIn("search_stock_news", context["dsa"])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_injects_dsa_channel_headers_into_alphasift_litellm_calls(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-2.5-flash",
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "api_keys": ["dsa-gemini-key"],
                    "models": ["gemini/gemini-2.5-flash"],
                    "extra_headers": {"x-tenant": "dsa"},
                }
            ],
        )
        completion_calls: list[dict[str, object]] = []

        def completion_impl(**kwargs):
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **_kwargs):
            fake_litellm.completion(
                model="gemini/gemini-2.5-flash",
                api_key="dsa-gemini-key",
                messages=[{"role": "user", "content": "rank"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(payload["candidate_count"], 0)
        self.assertEqual(completion_calls[0]["extra_headers"], {"x-tenant": "dsa"})
        self.assertIsNot(fake_litellm.completion, completion_impl)
        self.assertTrue(
            getattr(fake_litellm.completion, "_alphasift_litellm_completion_bridge", False),
        )

    def test_screen_bridges_legacy_openai_fields_into_alphasift_runtime_env(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            openai_api_keys=["dsa-openai-key"],
            openai_base_url="https://openai-compatible.example/v1",
        )
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **kwargs):
            captured["env"] = {
                "OPENAI_API_KEY": alphasift_service.os.environ.get("OPENAI_API_KEY"),
                "OPENAI_API_KEYS": alphasift_service.os.environ.get("OPENAI_API_KEYS"),
                "OPENAI_BASE_URL": alphasift_service.os.environ.get("OPENAI_BASE_URL"),
                "LITELLM_MODEL": alphasift_service.os.environ.get("LITELLM_MODEL"),
            }
            captured["context"] = kwargs.get("context")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(
                alphasift_service.os.environ,
                {
                    "OPENAI_API_KEY": "outer-openai-key",
                    "OPENAI_BASE_URL": "https://outer-openai.example/v1",
                },
                clear=False,
            ),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)
            self.assertEqual(alphasift_service.os.environ.get("OPENAI_API_KEY"), "outer-openai-key")
            self.assertEqual(alphasift_service.os.environ.get("OPENAI_BASE_URL"), "https://outer-openai.example/v1")

        runtime_env = captured["env"]
        self.assertIsInstance(runtime_env, dict)
        self.assertEqual(runtime_env["OPENAI_API_KEY"], "dsa-openai-key")
        self.assertEqual(runtime_env["OPENAI_API_KEYS"], "dsa-openai-key")
        self.assertEqual(runtime_env["OPENAI_BASE_URL"], "https://openai-compatible.example/v1")
        self.assertEqual(runtime_env["LITELLM_MODEL"], "openai/gpt-4o-mini")

        context = captured["context"]
        self.assertIsInstance(context, dict)
        self.assertEqual(context["llm"]["channels"], [])
        self.assertEqual(context["llm"]["model_list"], [])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_rejects_private_legacy_openai_base_before_litellm_call(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            openai_api_keys=["dsa-openai-key"],
            openai_base_url="http://127.0.0.1:8080/v1",
        )
        completion_calls: list[Dict[str, Any]] = []

        def completion_impl(**kwargs: Any) -> Any:
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **_kwargs):
            fake_litellm.completion(
                model="openai/gpt-4o-mini",
                api_key="dsa-openai-key",
                messages=[{"role": "user", "content": "rank"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))
        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertRaises(HTTPException) as caught,
        ):
            self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertIsInstance(caught.exception.__cause__, OutboundPolicyError)
        self.assertEqual(completion_calls, [])

    def test_screen_injects_openai_compatible_model_headers_into_alphasift_litellm_calls(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=["openai/gpt-4o-mini"],
            llm_model_list=[
                {
                    "model_name": "openai/gpt-4o-mini",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "dsa-openai-key",
                        "api_base": "https://openai-compatible.example/v1",
                        "extra_headers": {"x-tenant": "dsa"},
                    },
                },
            ],
        )
        completion_calls: list[dict[str, object]] = []

        def completion_impl(**kwargs):
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **_kwargs):
            fake_litellm.completion(
                model="openai/gpt-4o-mini",
                api_key="dsa-openai-key",
                api_base="https://openai-compatible.example/v1",
                messages=[{"role": "user", "content": "rank"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(payload["candidate_count"], 0)
        self.assertEqual(completion_calls[0]["extra_headers"], {"x-tenant": "dsa"})
        self.assertEqual(
            completion_calls[0]["api_base"],
            "https://openai-compatible.example/v1",
        )
        self.assertIsNot(fake_litellm.completion, completion_impl)
        self.assertTrue(
            getattr(fake_litellm.completion, "_alphasift_litellm_completion_bridge", False),
        )

    def test_screen_bridges_openai_channel_base_url_and_headers(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=["openai/gpt-4.1"],
            llm_channels=[
                {
                    "name": "openai",
                    "protocol": "openai",
                    "enabled": True,
                    "base_url": "https://primary-openai.example/v1",
                    "api_keys": ["dsa-openai-primary"],
                    "models": ["openai/gpt-4o-mini", "openai/gpt-4.1"],
                    "extra_headers": {"x-route": "primary", "x-tenant": "dsa"},
                }
            ],
        )
        completion_calls: list[Dict[str, object]] = []

        def completion_impl(**kwargs: Any) -> Any:
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **kwargs: Dict[str, Any]) -> dict[str, object]:
            captured["env"] = {
                "OPENAI_BASE_URL": alphasift_service.os.environ.get("OPENAI_BASE_URL"),
                "OPENAI_API_KEY": alphasift_service.os.environ.get("OPENAI_API_KEY"),
                "OPENAI_API_KEYS": alphasift_service.os.environ.get("OPENAI_API_KEYS"),
                "LLM_CHANNELS": alphasift_service.os.environ.get("LLM_CHANNELS"),
                "LLM_OPENAI_BASE_URL": alphasift_service.os.environ.get("LLM_OPENAI_BASE_URL"),
                "LLM_OPENAI_API_KEYS": alphasift_service.os.environ.get("LLM_OPENAI_API_KEYS"),
            }
            captured["context"] = kwargs.get("context")
            fake_litellm.completion(
                model="openai/gpt-4o-mini",
                api_key="dsa-openai-primary",
                api_base="https://primary-openai.example/v1",
                messages=[{"role": "user", "content": "primary"}],
            )
            fake_litellm.completion(
                model="openai/gpt-4.1",
                api_key="dsa-openai-primary",
                api_base="https://primary-openai.example/v1",
                messages=[{"role": "user", "content": "fallback"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(payload["candidate_count"], 0)
        self.assertEqual(len(completion_calls), 2)
        self.assertEqual(captured["env"]["OPENAI_BASE_URL"], "https://primary-openai.example/v1")
        self.assertEqual(captured["env"]["OPENAI_API_KEYS"], "dsa-openai-primary")
        self.assertEqual(captured["env"]["OPENAI_API_KEY"], "dsa-openai-primary")
        self.assertEqual(captured["env"]["LLM_CHANNELS"], "openai")
        self.assertEqual(captured["env"]["LLM_OPENAI_BASE_URL"], "https://primary-openai.example/v1")
        self.assertEqual(captured["env"]["LLM_OPENAI_API_KEYS"], "dsa-openai-primary")
        self.assertEqual(completion_calls[0]["extra_headers"], {"x-route": "primary", "x-tenant": "dsa"})
        self.assertEqual(completion_calls[1]["extra_headers"], {"x-route": "primary", "x-tenant": "dsa"})
        context = captured["context"]
        self.assertIsInstance(context, dict)
        self.assertEqual(context["llm"]["channels"][0]["base_url"], "https://primary-openai.example/v1")
        self.assertEqual(context["llm"]["channels"][0]["extra_headers"], {"x-route": "primary", "x-tenant": "dsa"})
        self.assertEqual(context["llm"]["model_list"][0]["litellm_params"]["api_base"], "https://primary-openai.example/v1")
        self.assertEqual(context["llm"]["fallback_models"], ["openai/gpt-4.1"])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_injects_openai_compatible_fallback_headers_for_multiple_models(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="openai/gpt-4o-mini",
            litellm_fallback_models=["openai/gpt-4.1"],
            llm_model_list=[
                {
                    "model_name": "openai/gpt-4o-mini",
                    "litellm_params": {
                        "model": "openai/gpt-4o-mini",
                        "api_key": "dsa-openai-primary",
                        "api_base": "https://primary.openai.example/v1",
                        "extra_headers": {"x-route": "primary", "x-tenant": "dsa"},
                    },
                },
                {
                    "model_name": "openai/gpt-4.1",
                    "litellm_params": {
                        "model": "openai/gpt-4.1",
                        "api_key": "dsa-openai-fallback",
                        "api_base": "https://fallback.openai.example/v1",
                        "extra_headers": {"x-route": "fallback", "x-tenant": "dsa"},
                    },
                },
            ],
        )
        completion_calls: list[Dict[str, object]] = []

        def completion_impl(**kwargs: Any) -> Any:
            completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **_kwargs) -> dict[str, object]:
            fake_litellm.completion(
                model="openai/gpt-4o-mini",
                api_key="dsa-openai-primary",
                api_base="https://primary.openai.example/v1",
                messages=[{"role": "user", "content": "rank-1"}],
            )
            fake_litellm.completion(
                model="openai/gpt-4.1",
                api_key="dsa-openai-fallback",
                api_base="https://fallback.openai.example/v1",
                messages=[{"role": "user", "content": "rank-2"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(payload["candidate_count"], 0)
        primary_call = next(
            call for call in completion_calls if call["model"] == "openai/gpt-4o-mini"
        )
        fallback_call = next(
            call for call in completion_calls if call["model"] == "openai/gpt-4.1"
        )
        self.assertEqual(primary_call["extra_headers"], {"x-route": "primary", "x-tenant": "dsa"})
        self.assertEqual(
            fallback_call["extra_headers"],
            {"x-route": "fallback", "x-tenant": "dsa"},
        )
        self.assertEqual(primary_call["api_base"], "https://primary.openai.example/v1")
        self.assertEqual(fallback_call["api_base"], "https://fallback.openai.example/v1")
        self.assertTrue(getattr(fake_litellm.completion, "_alphasift_litellm_completion_bridge", False))

    def test_screen_handles_concurrent_requests_without_litellm_header_cross_pollution(self) -> None:
        config_a = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-2.5-flash",
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "api_keys": ["dsa-gemini-key-a"],
                    "models": ["gemini/gemini-2.5-flash"],
                    "extra_headers": {"x-tenant": "tenant-a"},
                }
            ],
        )
        config_b = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-2.5-flash",
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "api_keys": ["dsa-gemini-key-b"],
                    "models": ["gemini/gemini-2.5-flash"],
                    "extra_headers": {"x-tenant": "tenant-b"},
                }
            ],
        )

        completion_calls: list[Dict[str, Any]] = []
        thread_b_ready = threading.Event()
        completion_lock = threading.Lock()

        def completion_impl(**kwargs: Any) -> Any:
            with completion_lock:
                completion_calls.append(kwargs)
            return SimpleNamespace(choices=[])

        fake_litellm = SimpleNamespace(completion=completion_impl)

        def screen_impl(_strategy: str, **kwargs: Any) -> Dict[str, Any]:
            context = kwargs.get("context") or {}
            llm = context.get("llm", {})
            channels = llm.get("channels") or []
            headers = (channels[0] if channels else {}).get("extra_headers", {})
            tenant = headers.get("x-tenant")
            if tenant == "tenant-a":
                thread_b_ready.wait(timeout=2)
            else:
                thread_b_ready.set()
            fake_litellm.completion(
                model="gemini/gemini-2.5-flash",
                api_key=(channels[0].get("api_keys") or [""])[0],
                messages=[{"role": "user", "content": "rank"}],
            )
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        def _run_screen(config: Config) -> None:
            self._screen(config, market="cn", strategy="dual_low", max_results=5, mock_enrichment=False)

        with (
            patch.dict(sys.modules, {"litellm": fake_litellm}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            thread_a = threading.Thread(target=_run_screen, args=(config_a,))
            thread_b = threading.Thread(target=_run_screen, args=(config_b,))
            thread_a.start()
            thread_b.start()
            thread_a.join()
            thread_b.join()

        self.assertEqual(len(completion_calls), 2)
        self.assertCountEqual(
            [call.get("extra_headers", {}).get("x-tenant") for call in completion_calls],
            ["tenant-a", "tenant-b"],
        )
        self.assertTrue(
            thread_a.is_alive() is False and thread_b.is_alive() is False,
        )

    def test_screen_disabled_preserves_existing_llm_env_state(self) -> None:
        config = self._config(enabled=False)
        baseline_env = {
            "OPENAI_API_KEY": "legacy-openai-key",
            "OPENAI_BASE_URL": "https://outer.example.com/v1",
            "LITELLM_MODEL": "openai/gpt-4o-mini",
        }
        original_env = {key: alphasift_service.os.environ.get(key) for key in baseline_env}

        with (
            patch.dict(alphasift_service.os.environ, baseline_env, clear=False),
            patch("src.services.alphasift_service._build_alphasift_runtime_env") as runtime_env_mock,
            self.assertRaises(HTTPException) as caught,
        ):
            self._screen(config, market="cn", strategy="dual_low", max_results=5)
            for key, value in baseline_env.items():
                self.assertEqual(alphasift_service.os.environ.get(key), value)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["error"], "alphasift_disabled")
        runtime_env_mock.assert_not_called()
        for key, value in baseline_env.items():
            self.assertEqual(alphasift_service.os.environ.get(key), original_env[key])

    def test_screen_preserves_explicit_alphasift_snapshot_source_priority(self) -> None:
        config = self._config(enabled=True)
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **_kwargs):
            captured["snapshot_priority"] = alphasift_service.os.environ.get("SNAPSHOT_SOURCE_PRIORITY")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(alphasift_service.os.environ, {"SNAPSHOT_SOURCE_PRIORITY": "tushare,em_datacenter"}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(captured["snapshot_priority"], "tushare,em_datacenter")
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_preserves_explicit_daily_source(self) -> None:
        config = self._config(enabled=True)
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **_kwargs):
            captured["daily_source"] = alphasift_service.os.environ.get("DAILY_SOURCE")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(alphasift_service.os.environ, {"DAILY_SOURCE": "akshare"}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(captured["daily_source"], "akshare")
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_preserves_explicit_openai_base_url_without_openai_channel(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="deepseek/deepseek-chat",
            llm_channels=[
                {
                    "name": "deepseek",
                    "protocol": "deepseek",
                    "enabled": True,
                    "base_url": "https://api.deepseek.example/v1",
                    "api_keys": ["runtime-deepseek-key"],
                    "models": ["deepseek/deepseek-chat"],
                }
            ],
        )
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **_kwargs):
            captured["openai_base_url"] = alphasift_service.os.environ.get("OPENAI_BASE_URL")
            captured["llm_openai_base_url"] = alphasift_service.os.environ.get("LLM_OPENAI_BASE_URL")
            captured["openai_api_key"] = alphasift_service.os.environ.get("OPENAI_API_KEY")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(
                alphasift_service.os.environ,
                {
                    "OPENAI_BASE_URL": "https://outer-openai.example/v1",
                    "LLM_OPENAI_BASE_URL": "https://outer-openai-channel.example/v1",
                    "OPENAI_API_KEY": "outer-openai-key",
                },
                clear=False,
            ),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(captured["openai_base_url"], "https://outer-openai.example/v1")
        self.assertEqual(captured["llm_openai_base_url"], "https://outer-openai-channel.example/v1")
        self.assertEqual(captured["openai_api_key"], "outer-openai-key")
        self.assertEqual(payload["candidate_count"], 0)

    def test_alphasift_runtime_priority_puts_tushare_before_sina_when_token_exists(self) -> None:
        config = self._config(enabled=True)
        config.tushare_token = "token-1"

        with patch.dict(alphasift_service.os.environ, {"SNAPSHOT_SOURCE_PRIORITY": ""}, clear=False):
            env = alphasift_service._build_alphasift_runtime_env(config)

        self.assertEqual(env["SNAPSHOT_SOURCE_PRIORITY"], "tushare,sina,efinance,akshare_em,em_datacenter")

    def test_screen_preserves_explicit_candidate_context_provider_override(self) -> None:
        config = self._config(enabled=True)
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **_kwargs):
            captured["providers"] = alphasift_service.os.environ.get("LLM_CANDIDATE_CONTEXT_PROVIDERS")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with (
            patch.dict(alphasift_service.os.environ, {"LLM_CANDIDATE_CONTEXT_PROVIDERS": "news,announcement"}, clear=False),
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(captured["providers"], "news,announcement")
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_filters_undeclared_managed_fallbacks_for_dsa_routes(self) -> None:
        config = Config(
            alphasift_enabled=True,
            alphasift_install_spec=DEFAULT_ALPHASIFT_TEST_SPEC,
            litellm_model="gemini/gemini-3-flash-preview",
            litellm_fallback_models=["gemini/gemini-2.5-flash"],
            llm_channels=[
                {
                    "name": "gemini",
                    "protocol": "gemini",
                    "enabled": True,
                    "base_url": "",
                    "api_keys": ["dsa-gemini-key"],
                    "models": ["gemini/gemini-3-flash-preview"],
                },
                {
                    "name": "deepseek",
                    "protocol": "deepseek",
                    "enabled": True,
                    "base_url": "https://api.deepseek.com",
                    "api_keys": ["dsa-deepseek-key"],
                    "models": ["deepseek/deepseek-chat"],
                },
            ],
            llm_model_list=[
                {
                    "model_name": "gemini/gemini-3-flash-preview",
                    "litellm_params": {
                        "model": "gemini/gemini-3-flash-preview",
                        "api_key": "dsa-gemini-key",
                    },
                },
                {
                    "model_name": "deepseek/deepseek-chat",
                    "litellm_params": {
                        "model": "deepseek/deepseek-chat",
                        "api_key": "dsa-deepseek-key",
                        "api_base": "https://api.deepseek.com",
                    },
                },
            ],
        )
        captured: dict[str, object] = {}

        def screen_impl(_strategy: str, **kwargs):
            captured["env"] = {
                "LITELLM_MODEL": alphasift_service.os.environ.get("LITELLM_MODEL"),
                "LITELLM_FALLBACK_MODELS": alphasift_service.os.environ.get("LITELLM_FALLBACK_MODELS"),
                "LLM_CHANNELS": alphasift_service.os.environ.get("LLM_CHANNELS"),
            }
            captured["context"] = kwargs.get("context")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        runtime_env = captured["env"]
        self.assertIsInstance(runtime_env, dict)
        self.assertEqual(runtime_env["LITELLM_MODEL"], "gemini/gemini-3-flash-preview")
        self.assertEqual(runtime_env["LITELLM_FALLBACK_MODELS"], "deepseek/deepseek-chat")
        self.assertEqual(runtime_env["LLM_CHANNELS"], "gemini,deepseek")
        context = captured["context"]
        self.assertIsInstance(context, dict)
        self.assertEqual(context["llm"]["fallback_models"], ["deepseek/deepseek-chat"])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_retries_without_context_for_older_adapter_kwargs_wrappers(self) -> None:
        config = self._config(enabled=True)

        def screen_impl(_strategy: str, **kwargs):
            if "context" in kwargs:
                raise TypeError("unexpected keyword argument 'context'")
            return {"candidates": []}

        fake_module = _make_adapter_module(screen=MagicMock(side_effect=screen_impl))

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(fake_module.screen.call_count, 2)
        first_kwargs = fake_module.screen.call_args_list[0].kwargs
        second_kwargs = fake_module.screen.call_args_list[1].kwargs
        self.assertIn("context", first_kwargs)
        self.assertNotIn("context", second_kwargs)
        self.assertEqual(second_kwargs["market"], "cn")
        self.assertEqual(second_kwargs["max_results"], 5)
        self.assertEqual(second_kwargs["use_llm"], True)
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_does_not_install_when_enabled_but_adapter_missing(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(screen=MagicMock(return_value={"candidates": []}))

        with (
            patch(
                "src.services.alphasift_service._get_alphasift_status_snapshot",
                return_value=({}, False, _missing_alphasift_module_diagnostics()),
            ),
            patch("src.services.alphasift_service._install_alphasift") as install_mock,
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail.get("diagnostics", {}).get("reason"), "missing_module")
        install_mock.assert_not_called()
        fake_module.screen.assert_not_called()

    def test_screen_normalizes_non_finite_values(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(
                return_value={
                    "picks": [
                        {
                            "code": "600519",
                            "name": "Kweichow Moutai",
                            "score": float("nan"),
                            "ranking_reason": "AlphaSift pick",
                            "nested": {"pe": float("inf"), "pb": float("-inf"), "eps": 20.5},
                        },
                    ],
                }
            ),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertIsNone(payload["candidates"][0]["score"])
        self.assertIsNone(payload["candidates"][0]["raw"]["score"])
        self.assertIsNone(payload["candidates"][0]["raw"]["nested"]["pe"])
        self.assertIsNone(payload["candidates"][0]["raw"]["nested"]["pb"])

    def test_screen_allows_non_listed_strategy_as_custom(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            list_strategies=lambda: [{"id": "dual_low", "name": "双低选股"}],
            screen=MagicMock(return_value={"candidates": []}),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._screen(config, market="cn", strategy="custom_alpha", max_results=5)

        fake_module.screen.assert_called_once_with(
            "custom_alpha",
            market="cn",
            max_results=5,
            use_llm=True,
            context=ANY,
        )
        self.assertEqual(payload["candidates"], [])
        self.assertEqual(payload["candidate_count"], 0)

    def test_screen_rejects_unsupported_market(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            get_status=lambda: {"supported_markets": ["hk", "us"]},
            screen=MagicMock(return_value=[]),
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail["error"], "alphasift_invalid_market")

    def test_screen_maps_adapter_value_error_to_bad_request(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(side_effect=ValueError(PUBLIC_DIAGNOSTIC_SECRET)),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail["error"], "alphasift_screen_rejected")
        rendered_logs = "\n".join(captured.output)
        self.assertNotIn("sk-alphasift-secret-marker", rendered_logs)
        self.assertNotIn("user:password", rendered_logs)
        self.assertIn("error_code=alphasift_screen_rejected", rendered_logs)
        self.assertIn("exception_type=ValueError", rendered_logs)
        self.assertTrue(all(record.exc_info is None for record in captured.records))

    def test_screen_runtime_exception_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            screen=MagicMock(side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET)),
        )

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config, market="cn", strategy="dual_low", max_results=5)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_screen_failed")
        self.assertEqual(caught.exception.detail["message"], "AlphaSift 选股运行失败，请稍后重试。")
        self.assert_public_payload_is_private(caught.exception.detail)
        rendered_logs = "\n".join(captured.output)
        self.assertNotIn("sk-alphasift-secret-marker", rendered_logs)
        self.assertNotIn("user:password", rendered_logs)
        self.assertIn("error_code=alphasift_screen_failed", rendered_logs)
        self.assertIn("exception_type=RuntimeError", rendered_logs)
        self.assertTrue(all(record.exc_info is None for record in captured.records))
