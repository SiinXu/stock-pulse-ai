# -*- coding: utf-8 -*-
"""Endpoint contracts for the analysis API."""

from tests.analysis_api_contract_support import (
    AnalysisTaskQueue,
    Future,
    MagicMock,
    Path,
    SimpleNamespace,
    TaskStatus,
    activate_test_environment,
    analysis_endpoint_module,
    asyncio,
    create_app,
    datetime,
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


if __name__ == "__main__":
    unittest.main()
