# -*- coding: utf-8 -*-
"""Endpoint, queue, and extractor contracts for the analysis API."""

from tests.analysis_api_contract_support import (
    AnalysisTaskQueue,
    Future,
    MagicMock,
    Path,
    SimpleNamespace,
    TaskStatus,
    _call_litellm_vision,
    activate_test_environment,
    analysis_endpoint_module,
    asyncio,
    create_app,
    datetime,
    deep_thaw,
    get_analysis_status,
    get_task_list,
    json,
    patch,
    restore_test_environment,
    tempfile,
    trigger_analysis,
    trigger_market_review,
    unittest,
)


def setUpModule() -> None:
    activate_test_environment()


def tearDownModule() -> None:
    restore_test_environment()


class AnalysisApiContractTestCase(unittest.TestCase):
    def test_get_analysis_status_normalizes_completed_queue_result_contract(self) -> None:
        if get_analysis_status is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        created_at = datetime(2026, 5, 21, 17, 40, 0)
        queue = MagicMock()
        queue.get_task.return_value = SimpleNamespace(
            task_id="task-queue-1",
            stock_code="600519",
            stock_name="贵州茅台",
            status=analysis_endpoint_module.TaskStatusEnum.COMPLETED,
            progress=100,
            result={
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "report": {
                    "meta": {"query_id": "task-queue-1", "stock_code": "600519"},
                    "summary": {"analysis_summary": "summary", "operation_advice": "不建议买入"},
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
            status = get_analysis_status("task-queue-1")

        self.assertEqual(status.status, "completed")
        self.assertIsNotNone(status.result)
        self.assertEqual(status.result.query_id, "task-queue-1")
        self.assertEqual(status.result.stock_code, "600519")
        self.assertEqual(status.result.stock_name, "贵州茅台")
        self.assertEqual(status.result.created_at, created_at.isoformat())
        self.assertEqual(
            status.result.report["summary"]["analysis_summary"],
            "summary",
        )
        self.assertEqual(status.result.report["summary"]["operation_advice"], "不建议买入")
        self.assertEqual(status.result.report["summary"]["action"], "avoid")
        self.assertEqual(status.result.report["summary"]["action_label"], "回避")

    def test_openapi_declares_single_and_batch_async_202_payloads(self) -> None:
        if create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(static_dir=Path(temp_dir))
            schema = app.openapi()["paths"]["/api/v1/analysis/analyze"]["post"]["responses"]["202"][
                "content"
            ]["application/json"]["schema"]

        refs = {item["$ref"] for item in schema["anyOf"]}
        self.assertEqual(
            refs,
            {
                "#/components/schemas/TaskAccepted",
                "#/components/schemas/BatchTaskAcceptedResponse",
            },
        )

    def test_openapi_uses_canonical_task_status_components(self) -> None:
        if create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        openapi_schema = create_app().openapi()
        schemas = openapi_schema["components"]["schemas"]

        self.assertIn("TaskStatus", schemas)
        self.assertEqual(
            schemas["TaskStatusEnum"]["enum"],
            [
                "pending",
                "processing",
                "cancel_requested",
                "completed",
                "failed",
                "cancelled",
                "interrupted",
            ],
        )
        self.assertEqual(
            schemas["TaskStatus"]["properties"]["status"]["$ref"],
            "#/components/schemas/TaskStatusEnum",
        )
        self.assertEqual(
            schemas["TaskInfo"]["properties"]["status"]["$ref"],
            "#/components/schemas/TaskStatusEnum",
        )
        task_list_parameters = openapi_schema["paths"]["/api/v1/analysis/tasks"]["get"][
            "parameters"
        ]
        status_parameter = next(
            parameter for parameter in task_list_parameters if parameter["name"] == "status"
        )
        self.assertIn("interrupted", status_parameter["description"])

        static_spec_path = (
            Path(__file__).resolve().parents[1] / "docs/architecture/api_spec.json"
        )
        static_spec = json.loads(static_spec_path.read_text(encoding="utf-8"))
        expected_statuses = schemas["TaskStatusEnum"]["enum"]
        for schema_name in ("TaskStatus", "TaskInfo"):
            self.assertEqual(
                static_spec["components"]["schemas"][schema_name]["properties"][
                    "status"
                ]["enum"],
                expected_statuses,
            )
        static_status_parameter = next(
            parameter
            for parameter in static_spec["paths"]["/api/v1/analysis/tasks"]["get"][
                "parameters"
            ]
            if parameter["name"] == "status"
        )
        self.assertIn("interrupted", static_status_parameter["description"])

    def test_openapi_declares_backtest_phase_filter_enum_and_400(self) -> None:
        if create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(static_dir=Path(temp_dir))
            paths = app.openapi()["paths"]

        for path in (
            "/api/v1/backtest/results",
            "/api/v1/backtest/performance",
            "/api/v1/backtest/performance/{code}",
        ):
            operation = paths[path]["get"]
            self.assertIn("400", operation["responses"])
            params = {param["name"]: param for param in operation["parameters"]}
            schema = params["analysis_phase"]["schema"]
            enum_values = set()
            stack = [schema]
            while stack:
                current = stack.pop()
                if not isinstance(current, dict):
                    continue
                enum_values.update(current.get("enum") or [])
                stack.extend(current.get("anyOf") or [])
                stack.extend(current.get("oneOf") or [])

            self.assertEqual(enum_values, {"premarket", "intraday", "postmarket", "unknown"})

    def test_market_review_endpoint_accepts_omitted_body(self) -> None:
        if create_app is None or analysis_endpoint_module is None:
            self.skipTest("fastapi is not installed in this test environment")

        config = SimpleNamespace(trading_day_check_enabled=True, market_review_region="cn")

        with tempfile.TemporaryDirectory() as temp_dir:
            app = create_app(static_dir=Path(temp_dir))
            request_body = app.openapi()["paths"]["/api/v1/analysis/market-review"]["post"][
                "requestBody"
            ]

        self.assertNotIn("required", request_body)

        task_queue = MagicMock()
        task_queue.submit_background_task.return_value = SimpleNamespace(task_id="market-task-omitted")

        with patch.object(
            analysis_endpoint_module,
            "_try_acquire_market_review_lock",
            return_value=object(),
        ), patch("api.v1.endpoints.analysis.get_task_queue", return_value=task_queue):
            response = trigger_market_review(
                request=None,
                config=config,
            )

        self.assertTrue(response.send_notification)
        self.assertEqual(response.task_id, "market-task-omitted")
        task_queue.submit_background_task.assert_called_once()

    def test_trigger_analysis_rejects_blank_only_stock_inputs(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        with self.assertRaises(Exception) as ctx:
            trigger_analysis(
                request=SimpleNamespace(
                    stock_code="   ",
                    stock_codes=None,
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=False,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(
            ctx.exception.detail["message"],
            "股票代码不能为空或仅包含空白字符",
        )

    def test_trigger_analysis_rejects_obviously_invalid_mixed_input_before_resolution(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        with patch("api.v1.endpoints.analysis.resolve_name_to_code") as resolve_mock:
            with self.assertRaises(Exception) as ctx:
                trigger_analysis(
                    request=SimpleNamespace(
                        stock_code="00AAAAA",
                        stock_codes=None,
                        report_type="detailed",
                        force_refresh=False,
                        async_mode=True,
                        analysis_phase="auto",
                    ),
                    config=SimpleNamespace(),
                )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["message"], "请输入有效的股票代码或股票名称")
        resolve_mock.assert_not_called()

    def test_trigger_analysis_rejects_unresolvable_alpha_garbage(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        with patch("api.v1.endpoints.analysis.resolve_name_to_code", return_value=None), \
             patch("api.v1.endpoints.analysis.get_task_queue") as queue_mock:
            with self.assertRaises(Exception) as ctx:
                trigger_analysis(
                    request=SimpleNamespace(
                        stock_code="aaaaaaa",
                        stock_codes=None,
                        report_type="detailed",
                        force_refresh=False,
                        async_mode=True,
                        analysis_phase="auto",
                    ),
                    config=SimpleNamespace(),
                )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["message"], "请输入有效的股票代码或股票名称")
        queue_mock.assert_not_called()

    def test_trigger_analysis_accepts_us_suffix_code(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch("api.v1.endpoints.analysis.resolve_name_to_code") as resolve_mock:
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="AAPL.US",
                    stock_codes=None,
                    stock_name=None,
                    original_query="AAPL.US",
                    selection_source="manual",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        resolve_mock.assert_not_called()
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["AAPL.US"],
            stock_name=None,
            original_query="AAPL.US",
            selection_source="manual",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_resolves_bare_code_from_stock_index_before_default_market(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch("api.v1.endpoints.analysis.resolve_index_stock_code", return_value="005930.KS"), \
             patch("api.v1.endpoints.analysis.resolve_name_to_code") as resolve_mock:
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="005930",
                    stock_codes=None,
                    stock_name=None,
                    original_query="005930",
                    selection_source="manual",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        resolve_mock.assert_not_called()
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["005930.KS"],
            stock_name=None,
            original_query="005930",
            selection_source="manual",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_resolves_bare_4_digit_jp_code_before_name_resolution(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch("api.v1.endpoints.analysis.resolve_index_stock_code_for_analysis", return_value="7203.T") as resolve_index_mock, \
             patch("api.v1.endpoints.analysis.resolve_name_to_code") as resolve_mock:
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="7203",
                    stock_codes=None,
                    stock_name=None,
                    original_query="7203",
                    selection_source="manual",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        resolve_index_mock.assert_called_once_with("7203")
        resolve_mock.assert_not_called()
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["7203.T"],
            stock_name=None,
            original_query="7203",
            selection_source="manual",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_accepts_camel_case_report_language_alias(self) -> None:
        if trigger_analysis is None or analysis_endpoint_module is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        task = SimpleNamespace(
            task_id="task-report-language-1",
            trace_id="trace-report-language-1",
            stock_code="600519",
            analysis_phase="auto",
        )
        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([task], [])

        request = analysis_endpoint_module.AnalyzeRequest.model_validate({
            "stock_code": "600519",
            "async_mode": True,
            "reportLanguage": "en",
        })

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            response = trigger_analysis(request=request, config=SimpleNamespace())

        self.assertEqual(response.status_code, 202)
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["600519"],
            stock_name=None,
            original_query=None,
            selection_source=None,
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
            report_language="en",
        )

    def test_trigger_analysis_async_passes_and_returns_analysis_phase(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        task = SimpleNamespace(
            task_id="task-phase-1",
            trace_id="trace-phase-1",
            stock_code="600519",
            analysis_phase="intraday",
        )
        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([task], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="600519",
                    stock_codes=None,
                    stock_name=None,
                    original_query=None,
                    selection_source=None,
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="intraday",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(json.loads(response.body)["analysis_phase"], "intraday")
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["600519"],
            stock_name=None,
            original_query=None,
            selection_source=None,
            report_type="detailed",
            analysis_phase="intraday",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_accepts_hk_suffix_code_from_autocomplete(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch("api.v1.endpoints.analysis.resolve_name_to_code") as resolve_mock:
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="00700.HK",
                    stock_codes=None,
                    stock_name="腾讯控股",
                    original_query="00700",
                    selection_source="autocomplete",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        resolve_mock.assert_not_called()
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["00700.HK"],
            stock_name="腾讯控股",
            original_query="00700",
            selection_source="autocomplete",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_accepts_bse_suffix_code_from_autocomplete(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch("api.v1.endpoints.analysis.resolve_name_to_code") as resolve_mock:
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="920493.BJ",
                    stock_codes=None,
                    stock_name="示例北交所股票",
                    original_query="920493",
                    selection_source="autocomplete",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        resolve_mock.assert_not_called()
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["920493.BJ"],
            stock_name="示例北交所股票",
            original_query="920493",
            selection_source="autocomplete",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_rejects_non_bse_code_with_bj_exchange_hint(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        for bad_code in ("600519.BJ", "BJ600519"):
            with self.subTest(bad_code=bad_code):
                queue = MagicMock()

                with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
                     patch("api.v1.endpoints.analysis.resolve_name_to_code") as resolve_mock:
                    with self.assertRaises(Exception) as exc:
                        trigger_analysis(
                            request=SimpleNamespace(
                                stock_code=bad_code,
                                stock_codes=None,
                                stock_name=None,
                                original_query=bad_code,
                                selection_source="manual",
                                report_type="detailed",
                                force_refresh=False,
                                async_mode=True,
                                notify=True,
                                analysis_phase="auto",
                            ),
                            config=SimpleNamespace(),
                        )

                self.assertEqual(exc.exception.status_code, 400)
                self.assertEqual(exc.exception.detail["error"], "validation_error")
                resolve_mock.assert_not_called()
                queue.submit_tasks_batch.assert_not_called()

    def test_trigger_analysis_accepts_hk_prefixed_code(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue), \
             patch("api.v1.endpoints.analysis.resolve_name_to_code") as resolve_mock:
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="HK00700",
                    stock_codes=None,
                    stock_name=None,
                    original_query="HK00700",
                    selection_source="manual",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        resolve_mock.assert_not_called()
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["HK00700"],
            stock_name=None,
            original_query="HK00700",
            selection_source="manual",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_allows_stock_names_with_star_and_hyphen(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.resolve_name_to_code", return_value="688783"), \
             patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="西安奕材-U",
                    stock_codes=None,
                    stock_name=None,
                    original_query="西安奕材-U",
                    selection_source="manual",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["688783"],
            stock_name=None,
            original_query="西安奕材-U",
            selection_source="manual",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_accepts_resolvable_free_text_input(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.resolve_name_to_code", return_value="600519"), \
             patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code="贵州茅台",
                    stock_codes=None,
                    stock_name=None,
                    original_query="贵州茅台",
                    selection_source="manual",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["600519"],
            stock_name=None,
            original_query="贵州茅台",
            selection_source="manual",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_preserves_batch_metadata(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code=None,
                    stock_codes=["600519", "000001"],
                    stock_name=None,
                    original_query="uploaded.csv",
                    selection_source="import",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["600519", "000001"],
            stock_name=None,
            original_query="uploaded.csv",
            selection_source="import",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_trigger_analysis_rejects_cross_request_duplicate_for_equivalent_code_shapes(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        original_instance = AnalysisTaskQueue._instance
        AnalysisTaskQueue._instance = None
        try:
            queue = AnalysisTaskQueue(max_workers=1)
            queue._executor = type("ExecutorStub", (), {"submit": lambda self, *args, **kwargs: Future()})()

            with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
                first = trigger_analysis(
                    request=SimpleNamespace(
                        stock_code="600519",
                        stock_codes=None,
                        stock_name=None,
                        original_query=None,
                        selection_source=None,
                        report_type="detailed",
                        force_refresh=False,
                        async_mode=True,
                        notify=True,
                        analysis_phase="auto",
                    ),
                    config=SimpleNamespace(),
                )
                second = trigger_analysis(
                    request=SimpleNamespace(
                        stock_code="600519.SH",
                        stock_codes=None,
                        stock_name=None,
                        original_query=None,
                        selection_source=None,
                        report_type="detailed",
                        force_refresh=False,
                        async_mode=True,
                        notify=True,
                        analysis_phase="auto",
                    ),
                    config=SimpleNamespace(),
                )

            self.assertEqual(first.status_code, 202)
            self.assertEqual(second.status_code, 409)
            self.assertEqual(json.loads(second.body)["error"], "duplicate_task")
            self.assertEqual(json.loads(second.body)["params"]["stock_code"], "600519.SH")
            self.assertEqual(
                json.loads(second.body)["params"]["existing_task_id"],
                json.loads(first.body)["task_id"],
            )
        finally:
            queue = AnalysisTaskQueue._instance
            if queue is not None and queue is not original_instance:
                executor = getattr(queue, "_executor", None)
                if executor is not None and hasattr(executor, "shutdown"):
                    executor.shutdown(wait=False, cancel_futures=True)
            AnalysisTaskQueue._instance = original_instance

    def test_trigger_analysis_batch_does_not_apply_single_stock_name_to_all_tasks(self) -> None:
        if trigger_analysis is None:
            self.skipTest("fastapi is not installed in this test environment")

        queue = MagicMock()
        queue.submit_tasks_batch.return_value = ([], [])

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            response = trigger_analysis(
                request=SimpleNamespace(
                    stock_code=None,
                    stock_codes=["600519", "000001"],
                    stock_name="贵州茅台",
                    original_query="茅台,平安银行",
                    selection_source="import",
                    report_type="detailed",
                    force_refresh=False,
                    async_mode=True,
                    notify=True,
                    analysis_phase="auto",
                ),
                config=SimpleNamespace(),
            )

        self.assertEqual(response.status_code, 202)
        queue.submit_tasks_batch.assert_called_once_with(
            stock_codes=["600519", "000001"],
            stock_name=None,
            original_query="茅台,平安银行",
            selection_source="import",
            report_type="detailed",
            analysis_phase="auto",
            force_refresh=False,
            notify=True,
        )

    def test_spa_fallback_returns_json_404_for_bare_api_path(self) -> None:
        if create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        with tempfile.TemporaryDirectory() as temp_dir:
            static_dir = Path(temp_dir)
            (static_dir / "index.html").write_text("<html>spa</html>", encoding="utf-8")
            app = create_app(static_dir=static_dir)

            serve_spa = next(
                route.endpoint for route in app.routes
                if getattr(route, "path", None) == "/{full_path:path}"
            )

            response = asyncio.run(serve_spa(None, "api"))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            json.loads(response.body),
            {"error": "not_found", "message": "API endpoint /api not found"},
        )

    def test_spa_fallback_blocks_path_traversal(self) -> None:
        """SPA fallback must not serve files outside static_dir.

        Starlette's :path converter does not normalize `..` segments, so
        without an explicit containment check `static_dir / full_path` can
        resolve to arbitrary files on disk (CVE-class path traversal).
        """
        if create_app is None:
            self.skipTest("fastapi is not installed in this test environment")

        from fastapi.responses import FileResponse

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            static_dir = root / "static"
            static_dir.mkdir()
            (static_dir / "index.html").write_text("<html>spa</html>", encoding="utf-8")
            secret = root / "secret.txt"
            secret.write_text("TOPSECRET", encoding="utf-8")

            app = create_app(static_dir=static_dir)
            serve_spa = next(
                route.endpoint for route in app.routes
                if getattr(route, "path", None) == "/{full_path:path}"
            )

            for traversal in ("../secret.txt", "../../secret.txt", "foo/../../secret.txt"):
                with self.subTest(traversal=traversal):
                    response = asyncio.run(serve_spa(None, traversal))
                    self.assertIsInstance(response, FileResponse)
                    self.assertEqual(Path(response.path).resolve(), (static_dir / "index.html").resolve())

    def test_sse_generator_reraises_cancelled_error(self) -> None:
        """CancelledError must propagate (not be swallowed) from the SSE event generator."""
        try:
            from api.v1.endpoints.analysis import task_stream
        except Exception:  # pragma: no cover - optional dependency environments
            self.skipTest("api.v1.endpoints.analysis not importable")

        class _NeverStream:
            """Stream that never returns from receive(), used to exercise cancellation."""

            def __init__(self) -> None:
                self.close_count = 0

            async def receive(self, timeout=None):
                del timeout
                await asyncio.sleep(3600)

            async def aclose(self):
                self.close_count += 1

        never_stream = _NeverStream()
        mock_task_queue = MagicMock()
        mock_task_queue.subscribe_all.return_value = never_stream

        async def run():
            with patch("api.v1.endpoints.analysis.get_task_queue", return_value=mock_task_queue):
                response = await task_stream()
                gen = response.body_iterator

                async def consume():
                    async for _ in gen:
                        pass

                task = asyncio.create_task(consume())
                await asyncio.sleep(0)  # let generator start and reach wait_for
                task.cancel()
                await task  # should re-raise CancelledError

        with self.assertRaises(asyncio.CancelledError):
            asyncio.run(run())

        mock_task_queue.subscribe_all.assert_called_once_with()
        self.assertEqual(never_stream.close_count, 1)

    def test_sse_maps_canonical_events_to_legacy_event_names(self) -> None:
        try:
            from api.v1.endpoints.analysis import TaskEventType, task_stream
        except Exception:  # pragma: no cover - optional dependency environments
            self.skipTest("api.v1.endpoints.analysis not importable")

        canonical_types = list(TaskEventType)
        expected_names = [
            "task_created",
            "task_created",
            "task_started",
            "task_progress",
            "task_progress",
            "task_completed",
            "task_failed",
            "task_failed",
            "task_failed",
        ]

        class _FiniteStream:
            def __init__(self) -> None:
                self.events = [
                    SimpleNamespace(type=event_type, data={"index": index})
                    for index, event_type in enumerate(canonical_types)
                ]
                self.closed = False

            async def receive(self, timeout=None):
                del timeout
                if not self.events:
                    raise StopAsyncIteration
                return self.events.pop(0)

            async def aclose(self):
                self.closed = True

        stream = _FiniteStream()
        queue = MagicMock()
        queue.subscribe_all.return_value = stream

        async def consume():
            with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
                response = await task_stream()
                return [chunk async for chunk in response.body_iterator]

        chunks = asyncio.run(consume())
        event_names = [chunk.splitlines()[0].removeprefix("event: ") for chunk in chunks]

        self.assertEqual(event_names, ["connected", *expected_names])
        self.assertTrue(stream.closed)

    def test_get_task_list_includes_analysis_phase_and_skills(self) -> None:
        if get_task_list is None:
            self.skipTest("analysis endpoint helpers unavailable in this environment")

        task = SimpleNamespace(
            task_id="task-list-phase",
            trace_id="trace-list-phase",
            stock_code="600519",
            stock_name="贵州茅台",
            status=TaskStatus.PROCESSING,
            progress=42,
            message="running",
            report_type="detailed",
            created_at=datetime(2026, 4, 10, 12, 0, 0),
            started_at=datetime(2026, 4, 10, 12, 0, 1),
            completed_at=None,
            error=None,
            original_query="茅台",
            selection_source="manual",
            analysis_phase="postmarket",
            skills=["growth_quality"],
        )
        queue = MagicMock()
        queue.list_all_tasks.return_value = [task]
        queue.get_task_stats.return_value = {
            "total": 1,
            "pending": 0,
            "processing": 1,
            "completed": 0,
            "failed": 0,
        }

        with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
            response = get_task_list(status=None, limit=20)

        self.assertEqual(response.tasks[0].analysis_phase, "postmarket")
        self.assertEqual(response.tasks[0].skills, ["growth_quality"])


class BatchTaskQueueContractTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._original_instance = AnalysisTaskQueue._instance
        AnalysisTaskQueue._instance = None

    def tearDown(self) -> None:
        queue = AnalysisTaskQueue._instance
        if queue is not None and queue is not self._original_instance:
            executor = getattr(queue, "_executor", None)
            if executor is not None and hasattr(executor, "shutdown"):
                executor.shutdown(wait=False, cancel_futures=True)
        AnalysisTaskQueue._instance = self._original_instance

    def test_batch_submit_rolls_back_when_executor_submit_fails(self) -> None:
        class FailingExecutor:
            def __init__(self) -> None:
                self.submit_count = 0

            def submit(self, *args, **kwargs):
                self.submit_count += 1
                if self.submit_count == 2:
                    raise RuntimeError("executor down")
                return Future()

        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = FailingExecutor()

        with self.assertRaisesRegex(RuntimeError, "executor down"):
            queue.submit_tasks_batch(["600519", "000858"], report_type="detailed")

        self.assertEqual(queue._tasks, {})
        self.assertEqual(queue._analyzing_stocks, {})
        self.assertEqual(queue._futures, {})

    def test_batch_submit_ignores_blank_stock_codes(self) -> None:
        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = type("ExecutorStub", (), {"submit": lambda self, *args, **kwargs: Future()})()

        accepted, duplicates = queue.submit_tasks_batch(["600519", "   "], report_type="detailed")

        self.assertEqual([task.stock_code for task in accepted], ["600519"])
        self.assertEqual(duplicates, [])
        self.assertEqual(sorted(task.stock_code for task in queue._tasks.values()), ["600519"])

    def test_batch_submit_and_worker_use_copied_request_skills(self) -> None:
        class CapturingExecutor:
            def __init__(self) -> None:
                self.calls = []

            def submit(self, fn, *args, **kwargs):
                self.calls.append((fn, args, kwargs))
                return Future()

        queue = AnalysisTaskQueue(max_workers=1)
        executor = CapturingExecutor()
        queue._executor = executor
        broadcast_events = []
        queue._broadcast_event = lambda event_type, data: broadcast_events.append((event_type, data))
        request_skills = ["growth_quality"]
        portfolio_context = {
            "account_id": 7,
            "account_name": "Main",
            "symbol": "600519",
            "quantity": 100,
        }

        accepted, duplicates = queue.submit_tasks_batch(
            ["600519"],
            report_type="detailed",
            analysis_phase="intraday",
            query_source="portfolio",
            portfolio_context=portfolio_context,
            skills=request_skills,
        )
        request_skills.append("mutated_after_submit")
        portfolio_context["quantity"] = 999

        self.assertEqual(duplicates, [])
        self.assertEqual(accepted[0].analysis_phase, "intraday")
        self.assertEqual(accepted[0].to_dict()["analysis_phase"], "intraday")
        self.assertNotIn("portfolio_context", accepted[0].to_dict())
        self.assertNotIn("query_source", accepted[0].to_dict())
        self.assertNotIn("portfolio_context", broadcast_events[0][1])
        self.assertNotIn("query_source", broadcast_events[0][1])
        self.assertEqual(accepted[0].copy().analysis_phase, "intraday")
        self.assertEqual(accepted[0].query_source, "portfolio")
        self.assertEqual(accepted[0].portfolio_context["quantity"], 100)
        self.assertEqual(accepted[0].copy().portfolio_context["quantity"], 100)
        self.assertEqual(accepted[0].skills, ["growth_quality"])
        submitted_command = queue._commands[accepted[0].task_id]
        submitted_metadata = deep_thaw(submitted_command.metadata)
        self.assertEqual(submitted_metadata["skills"], ["growth_quality"])
        self.assertEqual(submitted_metadata["portfolio_context"]["quantity"], 100)

        service_instance = MagicMock()
        service_instance.analyze_stock.return_value = {"stock_name": "贵州茅台"}
        with patch("src.services.analysis_service.AnalysisService", return_value=service_instance):
            executor.calls[0][0](*executor.calls[0][1])

        self.assertEqual(service_instance.analyze_stock.call_args.kwargs["skills"], ["growth_quality"])
        self.assertIsNot(service_instance.analyze_stock.call_args.kwargs["skills"], request_skills)
        self.assertEqual(service_instance.analyze_stock.call_args.kwargs["analysis_phase"], "intraday")
        self.assertEqual(service_instance.analyze_stock.call_args.kwargs["query_source"], "portfolio")
        self.assertEqual(
            service_instance.analyze_stock.call_args.kwargs["portfolio_context"]["quantity"],
            100,
        )

    def test_batch_submit_deduplicates_equivalent_stock_code_shapes(self) -> None:
        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = type("ExecutorStub", (), {"submit": lambda self, *args, **kwargs: Future()})()

        accepted, duplicates = queue.submit_tasks_batch(["600519"], report_type="detailed")

        self.assertEqual(len(accepted), 1)
        self.assertEqual(duplicates, [])
        self.assertTrue(queue.is_analyzing("600519.SH"))
        self.assertEqual(queue.get_analyzing_task_id("600519.SH"), accepted[0].task_id)

        accepted_again, duplicates_again = queue.submit_tasks_batch(
            ["600519.SH"],
            report_type="detailed",
            analysis_phase="intraday",
        )

        self.assertEqual(accepted_again, [])
        self.assertEqual(len(duplicates_again), 1)
        self.assertEqual(duplicates_again[0].stock_code, "600519.SH")
        self.assertEqual(duplicates_again[0].existing_task_id, accepted[0].task_id)

    def test_submit_task_rejects_blank_stock_code(self) -> None:
        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = type("ExecutorStub", (), {"submit": lambda self, *args, **kwargs: Future()})()

        with self.assertRaisesRegex(ValueError, "股票代码不能为空或仅包含空白字符"):
            queue.submit_task("   ", report_type="detailed")

        self.assertEqual(queue._tasks, {})
        self.assertEqual(queue._analyzing_stocks, {})
        self.assertEqual(queue._futures, {})

    def test_batch_submit_broadcasts_task_created_while_queue_lock_is_held(self) -> None:
        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = type("ExecutorStub", (), {"submit": lambda self, *args, **kwargs: Future()})()
        lock_states = []

        def record_broadcast(event_type, data):
            if event_type == "task_created":
                lock_states.append(queue._data_lock._is_owned())

        queue._broadcast_event = record_broadcast

        accepted, duplicates = queue.submit_tasks_batch(["600519", "000858"], report_type="detailed")

        self.assertEqual(len(accepted), 2)
        self.assertEqual(duplicates, [])
        self.assertEqual(lock_states, [True, True])

    def test_update_task_progress_broadcasts_task_progress_event(self) -> None:
        queue = AnalysisTaskQueue(max_workers=1)
        queue._executor = type("ExecutorStub", (), {"submit": lambda self, *args, **kwargs: Future()})()
        accepted, _ = queue.submit_tasks_batch(["600519"], report_type="detailed")

        events = []
        queue._broadcast_event = lambda event_type, data: events.append((event_type, data))

        updated = queue.update_task_progress(
            accepted[0].task_id,
            62,
            "LLM 正在生成分析结果",
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.progress, 62)
        self.assertEqual(updated.message, "LLM 正在生成分析结果")
        self.assertEqual(events, [("task_progress", updated.to_dict())])


class ImageStockExtractorContractTestCase(unittest.TestCase):
    def test_litellm_completion_patch_target_remains_available(self) -> None:
        cfg = SimpleNamespace(
            vision_model="",
            openai_vision_model=None,
            litellm_model="",
            gemini_api_keys=["sk-gemini-testkey-1234"],
            gemini_model="gemini-2.0-flash",
            anthropic_api_keys=[],
            anthropic_model="claude-3-5-sonnet-20241022",
            openai_api_keys=[],
            openai_model="gpt-4o-mini",
            openai_base_url=None,
        )
        msg = MagicMock()
        msg.content = '["600519"]'
        choice = MagicMock()
        choice.message = msg
        response = MagicMock()
        response.choices = [choice]

        with patch("src.services.image_stock_extractor.get_config", return_value=cfg), \
             patch("src.services.image_stock_extractor.litellm.completion", return_value=response) as mock_completion:
            result = _call_litellm_vision("base64data", "image/jpeg")

        self.assertEqual(result, '["600519"]')
        mock_completion.assert_called_once()


if __name__ == "__main__":
    unittest.main()
