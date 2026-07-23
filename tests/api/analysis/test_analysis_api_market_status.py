# -*- coding: utf-8 -*-
"""Market review and status contracts for the analysis API."""

from tests.analysis_api_contract_support import (
    AnalysisService,
    AnalysisTaskQueue,
    Future,
    MagicMock,
    Path,
    QueueTaskInfo,
    SimpleNamespace,
    TaskStatus,
    _market_structure_context,
    activate_test_environment,
    analysis_endpoint_module,
    datetime,
    get_analysis_status,
    patch,
    restore_test_environment,
    tempfile,
    trigger_market_review,
    unittest,
)


def setUpModule() -> None:
    activate_test_environment()


def tearDownModule() -> None:
    restore_test_environment()


class AnalysisApiContractTestCase(unittest.TestCase):
    def test_trigger_market_review_accepts_background_task(self) -> None:
        if trigger_market_review is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")
        task_queue = MagicMock()
        task_queue.submit_background_task.return_value = SimpleNamespace(task_id="market-task-1")
        request = SimpleNamespace(send_notification=False)
        config = SimpleNamespace(trading_day_check_enabled=False)
        lock_token = object()

        with patch.object(
            analysis_endpoint_module,
            "_try_acquire_market_review_lock",
            return_value=lock_token,
        ), patch("api.v1.endpoints.analysis.get_task_queue", return_value=task_queue):
            response = trigger_market_review(
                request=request,
                config=config,
            )

        self.assertEqual(response.status, "accepted")
        self.assertFalse(response.send_notification)
        self.assertEqual(response.task_id, "market-task-1")
        task_queue.submit_background_task.assert_called_once()
        args, kwargs = task_queue.submit_background_task.call_args
        self.assertTrue(callable(args[0]))
        self.assertEqual(kwargs["stock_code"], "market_review")
        self.assertEqual(kwargs["stock_name"], "大盘复盘")
        self.assertEqual(kwargs["message"], "大盘复盘任务已提交")
        self.assertEqual(kwargs["failure_error_code"], "analysis_failed")

    def test_trigger_market_review_accepts_request_level_report_language(self) -> None:
        if trigger_market_review is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        request = SimpleNamespace(send_notification=True, report_language="en")
        config = SimpleNamespace(trading_day_check_enabled=False, report_language="zh", market_review_region="cn")
        lock_token = object()
        task_payload: dict[str, object] = {}

        runtime_notifier = MagicMock()
        runtime_search = MagicMock()
        runtime_analyzer = MagicMock()

        task_queue = MagicMock()

        def _capture_background_task(task_fn, **kwargs):
            task_payload["background_task"] = task_fn
            return SimpleNamespace(task_id="market-task-1")

        task_queue.submit_background_task.side_effect = _capture_background_task

        with patch.object(
            analysis_endpoint_module,
            "_try_acquire_market_review_lock",
            return_value=lock_token,
        ), patch.object(
            analysis_endpoint_module,
            "_build_market_review_runtime",
            return_value=(runtime_notifier, runtime_analyzer, runtime_search),
        ), patch("src.core.market_review.run_market_review") as run_market_review, patch(
            "api.v1.endpoints.analysis.get_task_queue",
            return_value=task_queue,
        ), patch.object(
            analysis_endpoint_module,
            "_release_market_review_lock",
            return_value=None,
        ):
            trigger_market_review(request=request, config=config)
            self.assertIn("background_task", task_payload)
            task_payload["background_task"]()

        call_kwargs = run_market_review.call_args.kwargs
        self.assertEqual(call_kwargs["send_notification"], True)
        self.assertIsNone(call_kwargs["override_region"])
        self.assertEqual(call_kwargs["trigger_source"], "api")
        runtime_config = call_kwargs.get("config")
        self.assertIsNotNone(runtime_config)
        self.assertEqual(getattr(runtime_config, "report_language", None), "en")
        self.assertIsNot(runtime_config, config)

    def test_trigger_market_review_accepts_camel_case_report_language_alias(self) -> None:
        if trigger_market_review is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        request = analysis_endpoint_module.MarketReviewRequest.model_validate({
            "send_notification": True,
            "reportLanguage": "en",
        })
        config = SimpleNamespace(trading_day_check_enabled=False, report_language="zh", market_review_region="cn")
        task_payload: dict[str, object] = {}

        runtime_notifier = MagicMock()
        runtime_search = MagicMock()
        runtime_analyzer = MagicMock()

        task_queue = MagicMock()

        def _capture_background_task(task_fn, **kwargs):
            task_payload["background_task"] = task_fn
            return SimpleNamespace(task_id="market-task-1")

        task_queue.submit_background_task.side_effect = _capture_background_task

        with patch.object(
            analysis_endpoint_module,
            "_try_acquire_market_review_lock",
            return_value=object(),
        ), patch.object(
            analysis_endpoint_module,
            "_build_market_review_runtime",
            return_value=(runtime_notifier, runtime_analyzer, runtime_search),
        ), patch("src.core.market_review.run_market_review") as run_market_review, patch(
            "api.v1.endpoints.analysis.get_task_queue",
            return_value=task_queue,
        ), patch.object(
            analysis_endpoint_module,
            "_release_market_review_lock",
            return_value=None,
        ):
            response = trigger_market_review(request=request, config=config)
            self.assertEqual(response.status, "accepted")
            self.assertIn("background_task", task_payload)
            task_payload["background_task"]()

        call_kwargs = run_market_review.call_args.kwargs
        runtime_config = call_kwargs.get("config")
        self.assertEqual(getattr(runtime_config, "report_language", None), "en")
        self.assertEqual(call_kwargs["trigger_source"], "api")

    def test_trigger_market_review_rejects_duplicate_submission(self) -> None:
        if trigger_market_review is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        task_queue = MagicMock()
        request = SimpleNamespace(send_notification=True)
        config = SimpleNamespace(trading_day_check_enabled=False)

        with patch.object(
            analysis_endpoint_module,
            "_try_acquire_market_review_lock",
            return_value=None,
        ), patch("api.v1.endpoints.analysis.get_task_queue", return_value=task_queue):
            with self.assertRaises(Exception) as ctx:
                trigger_market_review(
                    request=request,
                    config=config,
                )

        self.assertEqual(getattr(ctx.exception, "status_code", None), 409)
        task_queue.submit_background_task.assert_not_called()

    def test_trigger_market_review_rejects_when_shared_lock_is_held(self) -> None:
        if trigger_market_review is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        from src.core.market_review_lock import (
            release_market_review_lock,
            try_acquire_market_review_lock,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            config = SimpleNamespace(
                trading_day_check_enabled=False,
                database_path=str(Path(temp_dir) / "stock_analysis.db"),
            )
            lock_token = try_acquire_market_review_lock(config)
            self.assertIsNotNone(lock_token)

            task_queue = MagicMock()
            try:
                with patch("api.v1.endpoints.analysis.get_task_queue", return_value=task_queue):
                    with self.assertRaises(Exception) as ctx:
                        trigger_market_review(
                            request=SimpleNamespace(send_notification=True),
                            config=config,
                        )
            finally:
                release_market_review_lock(lock_token)

        self.assertEqual(getattr(ctx.exception, "status_code", None), 409)
        task_queue.submit_background_task.assert_not_called()

    def test_trigger_market_review_submits_even_when_configured_markets_closed(self) -> None:
        if trigger_market_review is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        task_queue = MagicMock()
        task_queue.submit_background_task.return_value = SimpleNamespace(task_id="market-task-manual")
        request = SimpleNamespace(send_notification=True)
        config = SimpleNamespace(trading_day_check_enabled=True, market_review_region="cn")
        lock_token = object()

        with patch(
            "src.core.trading_calendar.get_open_markets_today",
            return_value=set(),
        ) as get_open_markets_today, patch(
            "src.core.trading_calendar.compute_effective_region",
            return_value="",
        ) as compute_effective_region, patch.object(
            analysis_endpoint_module,
            "_try_acquire_market_review_lock",
            return_value=lock_token,
        ) as acquire, patch("api.v1.endpoints.analysis.get_task_queue", return_value=task_queue):
            response = trigger_market_review(
                request=request,
                config=config,
            )

        self.assertEqual(response.status, "accepted")
        self.assertEqual(response.task_id, "market-task-manual")
        get_open_markets_today.assert_not_called()
        compute_effective_region.assert_not_called()
        acquire.assert_called_once_with(config)
        task_queue.submit_background_task.assert_called_once()

    def test_run_market_review_background_uses_configured_pipeline(self) -> None:
        if analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        config = SimpleNamespace(
            has_search_capability_enabled=lambda: True,
            bocha_api_keys=["bocha"],
            tavily_api_keys=["tavily"],
            anspire_api_keys=["anspire"],
            brave_api_keys=["brave"],
            serpapi_keys=["serpapi"],
            minimax_api_keys=["minimax"],
            searxng_base_urls=["http://searxng.local"],
            searxng_public_instances_enabled=False,
            news_max_age_days=5,
            news_strategy_profile="balanced",
            gemini_api_key="gemini-key",
            openai_api_key=None,
        )

        runtime_notifier = MagicMock()
        runtime_search = MagicMock()
        runtime_analyzer = MagicMock()
        with patch.object(
            analysis_endpoint_module,
            "_build_market_review_runtime",
            return_value=(runtime_notifier, runtime_analyzer, runtime_search),
        ), patch("src.core.market_review.run_market_review") as run_market_review:
            analysis_endpoint_module._run_market_review_background(
                send_notification=False,
                override_region="cn,us",
                lock_token=None,
                config=config,
            )

        run_market_review.assert_called_once_with(
            notifier=runtime_notifier,
            analyzer=runtime_analyzer,
            search_service=runtime_search,
            config=config,
            send_notification=False,
            override_region="cn,us",
            return_structured=True,
            trigger_source="api",
        )

    def test_market_review_runtime_initializes_analyzer_for_litellm_provider(self) -> None:
        if analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        config = SimpleNamespace(
            has_search_capability_enabled=lambda: False,
            gemini_api_key=None,
            openai_api_key=None,
            litellm_model="anthropic/claude-sonnet-4-6",
            llm_model_list=[],
            anthropic_api_keys=["sk-ant-test-value"],
        )

        with patch("src.notification.NotificationService"), \
             patch("src.analyzer.GeminiAnalyzer") as analyzer_cls:
            analyzer_cls.return_value.is_available.return_value = True

            _, analyzer, search_service = analysis_endpoint_module._build_market_review_runtime(config)

        analyzer_cls.assert_called_once_with(config=config)
        self.assertIs(analyzer, analyzer_cls.return_value)
        self.assertIsNone(search_service)

    def test_market_review_api_runtime_rejects_boundary_context_passthrough(self) -> None:
        if analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        config = SimpleNamespace()
        expected = (MagicMock(), MagicMock(), MagicMock())
        with patch.object(
            analysis_endpoint_module,
            "_runtime_build_market_review_runtime",
            return_value=expected,
        ) as runtime_builder:
            result = analysis_endpoint_module._build_market_review_runtime(config)
            with self.assertRaises(TypeError):
                analysis_endpoint_module._build_market_review_runtime(config, object())

        self.assertIs(result, expected)
        runtime_builder.assert_called_once_with(config)

    def test_run_market_review_background_returns_non_empty_result_payload(self) -> None:
        if analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        runtime_notifier = MagicMock()
        runtime_search = MagicMock()
        runtime_analyzer = MagicMock()
        market_review_config = SimpleNamespace()
        with patch.object(
            analysis_endpoint_module,
            "_build_market_review_runtime",
            return_value=(runtime_notifier, runtime_analyzer, runtime_search),
        ), patch("src.core.market_review.run_market_review", return_value="report") as run_market_review:
            result = analysis_endpoint_module._run_market_review_background(
                send_notification=False,
                override_region="cn",
                lock_token=None,
                config=market_review_config,
            )

        self.assertEqual(result, {"result": "report"})
        run_market_review.assert_called_once_with(
            notifier=runtime_notifier,
            analyzer=runtime_analyzer,
            search_service=runtime_search,
            config=market_review_config,
            send_notification=False,
            override_region="cn",
            return_structured=True,
            trigger_source="api",
        )

    def test_run_market_review_uses_request_scoped_config_language(self) -> None:
        from src.core.market_review import run_market_review

        global_config = SimpleNamespace(report_language="zh", market_review_region="cn")
        scoped_config = SimpleNamespace(report_language="en", market_review_region="cn")
        notifier = MagicMock()
        notifier.save_report_to_file.return_value = "market_review.md"
        notifier.is_available.return_value = False
        review_result = SimpleNamespace(
            report="Market review body",
            market_light_snapshot={},
            structured_payload={
                "kind": "market_review",
                "language": "en",
                "sections": [{"key": "summary", "title": "Summary", "markdown": "Market review body"}],
            },
        )
        market_analyzer = MagicMock()
        market_analyzer.run_daily_review_with_snapshot.return_value = review_result

        with patch("src.core.market_review.get_config", return_value=global_config) as get_config_mock, \
             patch("src.core.market_review.MarketAnalyzer", return_value=market_analyzer) as market_analyzer_cls, \
             patch("src.core.market_review._persist_market_review_history") as persist:
            result = run_market_review(
                notifier=notifier,
                search_service=MagicMock(),
                send_notification=False,
                return_structured=True,
                config=scoped_config,
            )

        get_config_mock.assert_not_called()
        market_analyzer_cls.assert_called_once()
        self.assertIs(market_analyzer_cls.call_args.kwargs["config"], scoped_config)
        self.assertEqual(result.market_review_payload["language"], "en")
        self.assertEqual(persist.call_args.kwargs["config"].report_language, "en")

    def test_get_analysis_status_returns_market_review_report_from_queue(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        queue = MagicMock()
        queue.get_task.return_value = SimpleNamespace(
            task_id="market-task-1",
            stock_code="market_review",
            stock_name="大盘复盘",
            status=analysis_endpoint_module.TaskStatusEnum.COMPLETED,
            progress=100,
            result={
                "result": "市场复盘报告示例文本",
                "market_review_payload": {"kind": "market_review", "sections": []},
            },
            error=None,
            original_query=None,
            selection_source=None,
            analysis_phase="auto",
        )

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            status = get_analysis_status("market-task-1")

        self.assertEqual(status.status, "completed")
        self.assertEqual(status.market_review_report, "市场复盘报告示例文本")
        self.assertEqual(status.market_review_payload["kind"], "market_review")
        self.assertIsNone(status.result)

    def test_get_analysis_status_accepts_cancel_states_from_queue(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        for task_status in (
            analysis_endpoint_module.TaskStatusEnum.CANCEL_REQUESTED,
            analysis_endpoint_module.TaskStatusEnum.CANCELLED,
        ):
            with self.subTest(task_status=task_status.value):
                queue = MagicMock()
                queue.get_task.return_value = SimpleNamespace(
                    task_id=f"task-{task_status.value}",
                    trace_id=f"trace-{task_status.value}",
                    stock_code="600519",
                    stock_name="贵州茅台",
                    status=task_status,
                    progress=42,
                    result=None,
                    error=None,
                    original_query=None,
                    selection_source=None,
                    analysis_phase="auto",
                    skills=[],
                )

                with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
                    status = get_analysis_status(f"task-{task_status.value}")

                self.assertEqual(status.status, task_status.value)
                self.assertEqual(status.progress, 42)
                self.assertIsNone(status.result)

    def test_get_analysis_status_prefers_raw_result_action_over_summary_action(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        created_at = datetime(2026, 5, 21, 17, 40, 0)
        queue = MagicMock()
        queue.get_task.return_value = SimpleNamespace(
            task_id="task-queue-action-conflict",
            stock_code="600519",
            stock_name="贵州茅台",
            status=analysis_endpoint_module.TaskStatusEnum.COMPLETED,
            progress=100,
            result={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "report": {
                    "meta": {
                        "query_id": "task-queue-action-conflict",
                        "stock_code": "600519",
                        "report_type": "detailed",
                        "report_language": "zh",
                    },
                    "summary": {
                        "analysis_summary": "summary",
                        "operation_advice": "持有观察",
                        "action": "buy",
                    },
                    "details": {
                        "raw_result": {
                            "operation_advice": "持有观察",
                            "action": "watch",
                            "report_language": "zh",
                        },
                    },
                },
            },
            error=None,
            original_query=None,
            selection_source=None,
            analysis_phase="auto",
            created_at=created_at,
            completed_at=datetime(2026, 5, 21, 17, 45, 0),
        )

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            status = get_analysis_status("task-queue-action-conflict")

        self.assertEqual(status.status, "completed")
        self.assertIsNotNone(status.result)
        self.assertEqual(status.result.report["summary"]["action"], "watch")
        self.assertEqual(status.result.report["summary"]["action_label"], "观望")

    def test_get_analysis_status_preserves_zero_sentiment_score_when_aligning_action(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        created_at = datetime(2026, 5, 21, 17, 40, 0)
        queue = MagicMock()
        queue.get_task.return_value = SimpleNamespace(
            task_id="task-queue-zero-score",
            stock_code="600519",
            stock_name="贵州茅台",
            status=analysis_endpoint_module.TaskStatusEnum.COMPLETED,
            progress=100,
            result={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "report": {
                    "meta": {
                        "query_id": "task-queue-zero-score",
                        "stock_code": "600519",
                        "report_type": "detailed",
                        "report_language": "zh",
                    },
                    "summary": {
                        "analysis_summary": "趋势显著恶化",
                        "operation_advice": "持有",
                        "sentiment_score": 0,
                    },
                    "details": {
                        "raw_result": {
                            "operation_advice": "持有",
                            "report_language": "zh",
                        },
                    },
                },
            },
            error=None,
            original_query=None,
            selection_source=None,
            analysis_phase="auto",
            created_at=created_at,
            completed_at=datetime(2026, 5, 21, 17, 45, 0),
        )

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            status = get_analysis_status("task-queue-zero-score")

        self.assertEqual(status.status, "completed")
        self.assertIsNotNone(status.result)
        self.assertEqual(status.result.report["summary"]["sentiment_score"], 0)
        self.assertEqual(status.result.report["summary"]["action"], "sell")
        self.assertEqual(status.result.report["summary"]["action_label"], "卖出")

    def test_get_analysis_status_preserves_zero_sentiment_score_when_enriching_report(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        created_at = datetime(2026, 5, 21, 17, 40, 0)
        queue = MagicMock()
        queue.get_task.return_value = SimpleNamespace(
            task_id="task-queue-zero-score-enriched",
            stock_code="600519",
            stock_name="贵州茅台",
            status=analysis_endpoint_module.TaskStatusEnum.COMPLETED,
            progress=100,
            result={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "report": {
                    "meta": {
                        "query_id": "task-queue-zero-score-enriched",
                        "stock_code": "600519",
                        "report_type": "detailed",
                        "report_language": "zh",
                    },
                    "summary": {
                        "analysis_summary": "趋势显著恶化",
                        "operation_advice": "持有",
                        "sentiment_score": 0,
                    },
                    "details": {
                        "raw_result": {
                            "operation_advice": "持有",
                            "report_language": "zh",
                        },
                    },
                },
            },
            error=None,
            original_query=None,
            selection_source=None,
            analysis_phase="auto",
            created_at=created_at,
            completed_at=datetime(2026, 5, 21, 17, 45, 0),
        )

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch(
                 "api.v1.endpoints.analysis._load_sync_fundamental_sources",
                 return_value=({}, None, None),
             ):
            status = get_analysis_status("task-queue-zero-score-enriched")

        self.assertEqual(status.status, "completed")
        self.assertIsNotNone(status.result)
        self.assertEqual(status.result.report["summary"]["sentiment_score"], 0)
        self.assertEqual(status.result.report["summary"]["action"], "sell")
        self.assertEqual(status.result.report["summary"]["action_label"], "卖出")

    def test_get_analysis_status_enriches_in_memory_market_structure_from_raw_result(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        market_structure = _market_structure_context()
        created_at = datetime(2026, 5, 21, 17, 40, 0)
        queue = MagicMock()
        queue.get_task.return_value = SimpleNamespace(
            task_id="task-queue-market-structure-raw",
            stock_code="300024",
            stock_name="机器人",
            status=analysis_endpoint_module.TaskStatusEnum.COMPLETED,
            progress=100,
            result={
                "stock_code": "300024",
                "stock_name": "机器人",
                "report": {
                    "meta": {
                        "query_id": "task-queue-market-structure-raw",
                        "stock_code": "300024",
                        "report_type": "detailed",
                        "report_language": "zh",
                    },
                    "summary": {"analysis_summary": "summary"},
                    "details": {"news_summary": "news"},
                },
            },
            error=None,
            original_query=None,
            selection_source=None,
            analysis_phase="auto",
            created_at=created_at,
            completed_at=datetime(2026, 5, 21, 17, 45, 0),
        )

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch(
                 "api.v1.endpoints.analysis._load_sync_fundamental_sources",
                 return_value=(
                     None,
                     None,
                     {
                         "model_used": "test-model",
                         "report_language": "zh",
                         "market_structure_context": market_structure,
                     },
                 ),
             ) as load_sources:
            status = get_analysis_status("task-queue-market-structure-raw")

        self.assertEqual(status.status, "completed")
        self.assertIsNotNone(status.result)
        self.assertEqual(
            status.result.report["details"]["market_structure"]["market_theme_context"]["active_themes"][0]["name"],
            "机器人概念",
        )
        self.assertEqual(
            status.result.report["details"]["raw_result"]["market_structure_context"]["market_theme_context"]["active_themes"][0]["name"],
            "机器人概念",
        )
        self.assertNotIn(
            "raw_result",
            status.result.report["details"]["raw_result"],
        )
        load_sources.assert_called_once_with(
            query_id="task-queue-market-structure-raw",
            stock_code="300024",
        )

    def test_get_analysis_status_enriches_in_memory_market_structure_without_history_snapshot(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        market_structure = _market_structure_context()
        service = AnalysisService()
        task_result = service._build_analysis_response(
            SimpleNamespace(
                code="300024",
                name="机器人",
                current_price=999.9,
                change_pct=1.1,
                model_used="test-model",
                analysis_summary="summary",
                operation_advice="持有",
                trend_prediction="震荡",
                sentiment_score=80,
                news_summary="news",
                technical_analysis="tech",
                fundamental_analysis="fundamental",
                risk_warning="risk",
                market_structure_context=market_structure,
                to_dict=lambda: {
                    "analysis_summary": "summary",
                    "operation_advice": "持有",
                    "trend_prediction": "震荡",
                    "sentiment_score": 80,
                    "report_language": "zh",
                    "news_summary": "news",
                    "technical_analysis": "tech",
                    "fundamental_analysis": "fundamental",
                    "risk_warning": "risk",
                    "market_structure_context": market_structure,
                },
            ),
            "task-in-memory-no-history",
            report_type="detailed",
        )
        created_at = datetime(2026, 5, 21, 17, 40, 0)
        queue = MagicMock()
        queue.get_task.return_value = SimpleNamespace(
            task_id="task-in-memory-no-history",
            stock_code="300024",
            stock_name="机器人",
            status=analysis_endpoint_module.TaskStatusEnum.COMPLETED,
            progress=100,
            result=task_result,
            error=None,
            original_query=None,
            selection_source=None,
            analysis_phase="auto",
            created_at=created_at,
            completed_at=datetime(2026, 5, 21, 17, 45, 0),
        )

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch(
                 "api.v1.endpoints.analysis._load_sync_fundamental_sources",
                 return_value=(None, None, None),
             ):
            status = get_analysis_status("task-in-memory-no-history")

        self.assertEqual(status.status, "completed")
        self.assertIsNotNone(status.result)
        self.assertEqual(
            status.result.report["details"]["market_structure"]["market_theme_context"]["active_themes"][0]["name"],
            "机器人概念",
        )

    def test_get_analysis_status_preserves_queue_report_created_at_when_enriching(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        created_at = datetime(2026, 5, 21, 17, 40, 0)
        queue = MagicMock()
        queue.get_task.return_value = SimpleNamespace(
            task_id="task-queue-2",
            stock_code="600519",
            stock_name="贵州茅台",
            status=analysis_endpoint_module.TaskStatusEnum.COMPLETED,
            progress=100,
            result={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "report": {
                    "meta": {"query_id": "task-queue-2", "stock_code": "600519"},
                    "summary": {"analysis_summary": "summary"},
                },
            },
            error=None,
            original_query=None,
            selection_source=None,
            analysis_phase="auto",
            created_at=created_at,
            completed_at=datetime(2026, 5, 21, 17, 45, 0),
        )

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch(
                 "api.v1.endpoints.analysis._load_sync_fundamental_sources",
                 return_value=({}, None, None),
             ):
            status = get_analysis_status("task-queue-2")

        self.assertEqual(status.status, "completed")
        self.assertIsNotNone(status.result)
        self.assertEqual(status.result.created_at, created_at.isoformat())
        self.assertEqual(
            status.result.report["meta"]["created_at"],
            created_at.isoformat(),
        )

    def test_run_market_review_background_raises_when_report_is_empty(self) -> None:
        if analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        runtime_notifier = MagicMock()
        runtime_search = MagicMock()
        runtime_analyzer = MagicMock()
        with patch.object(
            analysis_endpoint_module,
            "_build_market_review_runtime",
            return_value=(runtime_notifier, runtime_analyzer, runtime_search),
        ), patch("src.core.market_review.run_market_review", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "大盘复盘未返回可持久化报告"):
                analysis_endpoint_module._run_market_review_background(
                    send_notification=False,
                    override_region="cn",
                    lock_token=None,
                    config=SimpleNamespace(),
                )

    def test_run_market_review_background_releases_lock_on_runtime_build_failure(self) -> None:
        if analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        lock_token = object()
        with patch.object(
            analysis_endpoint_module,
            "_build_market_review_runtime",
            side_effect=RuntimeError("runtime init failed"),
        ), patch.object(
            analysis_endpoint_module,
            "_release_market_review_lock",
        ) as release_market_review_lock:
            with self.assertRaises(RuntimeError):
                analysis_endpoint_module._run_market_review_background(
                    send_notification=False,
                    override_region="cn",
                    lock_token=lock_token,
                    config=SimpleNamespace(),
                )

        release_market_review_lock.assert_called_once_with(lock_token)

    def test_run_market_review_background_runtime_build_failure_marks_task_failed(self) -> None:
        if analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        class _SyncExecutor:
            def submit(self, fn, *args, **kwargs):
                future = Future()
                try:
                    future.set_result(fn(*args, **kwargs))
                except Exception as exc:  # pragma: no cover - exercised via assert below
                    future.set_exception(exc)
                return future

        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = _SyncExecutor()
        with patch.object(
            analysis_endpoint_module,
            "_build_market_review_runtime",
            side_effect=RuntimeError("runtime init failed"),
        ), patch.object(analysis_endpoint_module, "_release_market_review_lock") as release_market_review_lock:
            task = queue.submit_background_task(
                lambda: analysis_endpoint_module._run_market_review_background(
                    send_notification=False,
                    override_region="cn",
                    lock_token=object(),
                    config=SimpleNamespace(),
                ),
                stock_code="market_review",
                stock_name="大盘复盘",
                message="大盘复盘任务已提交",
            )

        task_info = queue.get_task(task.task_id)
        self.assertIsNotNone(task_info)
        self.assertEqual(task_info.status, TaskStatus.FAILED)
        self.assertEqual(task_info.error, "task_failed")
        self.assertEqual(task_info.message, "任务执行失败")
        self.assertEqual(task_info.diagnostic_error, "RuntimeError: [REDACTED]")
        release_market_review_lock.assert_called_once()

    def test_failed_task_polling_does_not_expose_legacy_diagnostic_text(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        secret_marker = "api_key=sk-polling-secret-marker"
        failed_task = QueueTaskInfo(
            task_id="failed-poll-task",
            trace_id="trace-failed-poll-task",
            stock_code="600519",
            status=TaskStatus.FAILED,
            progress=80,
            message=f"分析失败: {secret_marker}",
            message_code="task.analysis.failed",
            error=secret_marker,
            failure_error_code="analysis_failed",
        )
        mock_queue = MagicMock()
        mock_queue.get_task.return_value = failed_task

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=mock_queue):
            response = get_analysis_status(failed_task.task_id)

        self.assertEqual(response.error, "analysis_failed")
        self.assertEqual(response.message, "分析失败")
        self.assertNotIn(secret_marker, response.model_dump_json())

    def test_get_analysis_status_completed_db_snapshot_preserves_zero_change_pct(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        mock_queue = MagicMock()
        mock_queue.get_task.return_value = None
        mock_db = MagicMock()
        mock_db.get_analysis_history.return_value = [
            SimpleNamespace(
                id=1,
                code="600519",
                name="贵州茅台",
                report_type="detailed",
                raw_result={"report_language": "zh", "model_used": "test-model"},
                context_snapshot={
                    "enhanced_context": {
                        "realtime": {
                            "price": 1234.5,
                            "change_pct": 0.0,
                            "change_60d": 12.3,
                        }
                    },
                    "realtime_quote_raw": {"price": 1234.5, "change_pct": 9.9},
                },
                sentiment_score=80,
                operation_advice="持有",
                trend_prediction="看多",
                analysis_summary="summary",
                ideal_buy=None,
                secondary_buy=None,
                stop_loss=None,
                take_profit=None,
                created_at=None,
            )
        ]

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=mock_queue), \
             patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            result = get_analysis_status("task-1")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.result.report["meta"]["current_price"], 1234.5)
        self.assertEqual(result.result.report["meta"]["change_pct"], 0.0)

    def test_get_analysis_status_returns_market_review_report_from_db(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        mock_queue = MagicMock()
        mock_queue.get_task.return_value = None
        mock_db = MagicMock()
        mock_db.get_analysis_history.return_value = [
            SimpleNamespace(
                id=10,
                code="MARKET",
                name="大盘复盘",
                report_type="market_review",
                raw_result={"raw_response": "# 🎯 大盘复盘\n\n复盘正文"},
                news_content="复盘正文",
                created_at=None,
            )
        ]

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=mock_queue), \
             patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            result = get_analysis_status("market-task-1")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.market_review_report, "# 🎯 大盘复盘\n\n复盘正文")
        self.assertIsNone(result.result)

    def test_get_analysis_status_completed_db_snapshot_reads_change_pct_from_raw_when_price_present(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        mock_queue = MagicMock()
        mock_queue.get_task.return_value = None
        mock_db = MagicMock()
        mock_db.get_analysis_history.return_value = [
            SimpleNamespace(
                id=2,
                code="AAPL",
                name="Apple",
                report_type="detailed",
                raw_result={"report_language": "en", "model_used": "test-model"},
                context_snapshot={
                    "enhanced_context": {
                        "realtime": {
                            "price": 180.35,
                            "change_pct": None,
                            "change_60d": None,
                        }
                    },
                    "realtime_quote_raw": {"price": 180.35, "pct_chg": -1.25},
                },
                sentiment_score=72,
                operation_advice="Hold",
                trend_prediction="Neutral",
                analysis_summary="summary",
                ideal_buy=None,
                secondary_buy=None,
                stop_loss=None,
                take_profit=None,
                created_at=None,
            )
        ]

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=mock_queue), \
             patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            result = get_analysis_status("task-2")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.result.report["meta"]["current_price"], 180.35)
        self.assertEqual(result.result.report["meta"]["change_pct"], -1.25)

    def test_get_analysis_status_completed_db_snapshot_does_not_use_change_60d_as_intraday_change(self) -> None:
        if get_analysis_status is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        mock_queue = MagicMock()
        mock_queue.get_task.return_value = None
        mock_db = MagicMock()
        mock_db.get_analysis_history.return_value = [
            SimpleNamespace(
                id=3,
                code="MSFT",
                name="Microsoft",
                report_type="detailed",
                raw_result={"report_language": "en", "model_used": "test-model"},
                context_snapshot={
                    "enhanced_context": {
                        "realtime": {
                            "price": 412.6,
                            "change_pct": None,
                            "change_60d": 14.8,
                        }
                    },
                    "realtime_quote_raw": {"price": 412.6},
                },
                sentiment_score=70,
                operation_advice="Hold",
                trend_prediction="Neutral",
                analysis_summary="summary",
                ideal_buy=None,
                secondary_buy=None,
                stop_loss=None,
                take_profit=None,
                created_at=None,
            )
        ]

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=mock_queue), \
             patch("src.storage.DatabaseManager.get_instance", return_value=mock_db):
            result = get_analysis_status("task-3")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.result.report["meta"]["current_price"], 412.6)
        self.assertIsNone(result.result.report["meta"]["change_pct"])
