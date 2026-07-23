# -*- coding: utf-8 -*-
"""Batch task queue contracts for the analysis API."""

from tests.analysis_api_contract_support import (
    AnalysisTaskQueue,
    Future,
    MagicMock,
    activate_test_environment,
    deep_thaw,
    patch,
    restore_test_environment,
    unittest,
)


def setUpModule() -> None:
    activate_test_environment()


def tearDownModule() -> None:
    restore_test_environment()


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
