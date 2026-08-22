# -*- coding: utf-8 -*-
"""Kind-scoped analysis HTTP cancel and cooperative runner checks (#1448)."""

from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from src.api.middlewares.auth import EXEMPT_PATHS, _path_exempt
from src.api.v1.endpoints import analysis as endpoint
from src.api.v1.services.analysis_api_service import STOCK_ANALYSIS_TASK_KIND
from src.task_execution import TaskNotFoundError, TaskStatusEnum


def _stock_analysis_task(**overrides: object) -> SimpleNamespace:
    payload = {
        "task_id": "task-analysis-1",
        "trace_id": "trace-analysis-1",
        "kind": STOCK_ANALYSIS_TASK_KIND,
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "status": TaskStatusEnum.PROCESSING,
        "progress": 40,
        "result": None,
        "error": None,
        "original_query": None,
        "selection_source": None,
        "analysis_phase": "auto",
        "skills": [],
        "report_type": "detailed",
        "message": "正在分析中...",
        "message_code": "task.analysis.processing",
        "message_params": {"stock_code": "600519"},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class AnalysisTaskCancelHttpTests(unittest.TestCase):
    def test_cancel_route_is_registered_with_kind_scoped_operation(self) -> None:
        route = next(
            item
            for item in endpoint.router.routes
            if getattr(item, "path", None) == "/tasks/{task_id}/cancel"
            and "POST" in getattr(item, "methods", set())
        )
        self.assertIs(route.endpoint, endpoint.cancel_analysis_task)
        self.assertEqual(route.operation_id, "cancelAnalysisTask")

    def test_cancel_route_is_not_auth_exempt(self) -> None:
        self.assertFalse(_path_exempt("/api/v1/analysis/tasks/task-analysis-1/cancel"))
        self.assertNotIn("/api/v1/analysis/tasks/{task_id}/cancel", EXEMPT_PATHS)
        self.assertNotIn("/api/v1/analysis/tasks/task-analysis-1/cancel", EXEMPT_PATHS)

    def test_unknown_task_returns_404_without_calling_cancel(self) -> None:
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = None
        with patch("src.api.v1.endpoints.analysis.get_task_queue", return_value=fake_queue):
            with self.assertRaises(HTTPException) as caught:
                endpoint.cancel_analysis_task("missing-1")
        self.assertEqual(caught.exception.status_code, 404)
        fake_queue.cancel.assert_not_called()

    def test_wrong_kind_returns_404_without_calling_cancel(self) -> None:
        for kind, stock_code, report_type in (
            ("candidate_discovery", "candidate_discovery", "candidate_discovery"),
            ("detailed", "market_review", "detailed"),
            ("local_model_pull", "local_model", "local_model_pull"),
        ):
            with self.subTest(kind=kind):
                fake_queue = MagicMock()
                fake_queue.get_task.return_value = _stock_analysis_task(
                    task_id=f"other-{kind}",
                    kind=kind,
                    stock_code=stock_code,
                    report_type=report_type,
                )
                with patch(
                    "src.api.v1.endpoints.analysis.get_task_queue",
                    return_value=fake_queue,
                ):
                    with self.assertRaises(HTTPException) as caught:
                        endpoint.cancel_analysis_task(f"other-{kind}")
                self.assertEqual(caught.exception.status_code, 404)
                fake_queue.cancel.assert_not_called()

    def test_stock_analysis_cancel_calls_queue_and_returns_snapshot(self) -> None:
        task = _stock_analysis_task()

        def fake_cancel(task_id: str):
            task.status = TaskStatusEnum.CANCEL_REQUESTED
            task.message = "任务请求取消"
            task.message_code = "task.cancel_requested"
            task.message_params = {}
            return SimpleNamespace(
                task_id=task_id,
                status=TaskStatusEnum.CANCEL_REQUESTED,
                progress=40,
            )

        fake_queue = MagicMock()
        fake_queue.get_task.return_value = task
        fake_queue.cancel.side_effect = fake_cancel
        with patch("src.api.v1.endpoints.analysis.get_task_queue", return_value=fake_queue):
            payload = endpoint.cancel_analysis_task("task-analysis-1")
        fake_queue.cancel.assert_called_once_with("task-analysis-1")
        self.assertEqual(payload.status, "cancel_requested")
        self.assertEqual(payload.task_id, "task-analysis-1")
        self.assertEqual(payload.message_code, "task.cancel_requested")

    def test_cancel_maps_task_not_found_to_404(self) -> None:
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = _stock_analysis_task()
        fake_queue.cancel.side_effect = TaskNotFoundError("task-analysis-1")
        with patch("src.api.v1.endpoints.analysis.get_task_queue", return_value=fake_queue):
            with self.assertRaises(HTTPException) as caught:
                endpoint.cancel_analysis_task("task-analysis-1")
        self.assertEqual(caught.exception.status_code, 404)


class AnalysisTaskCancelQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        from src.services.task_queue import AnalysisTaskQueue

        self._original = AnalysisTaskQueue._instance
        AnalysisTaskQueue._instance = None
        self.queue = AnalysisTaskQueue(max_workers=1)

    def tearDown(self) -> None:
        from src.services.task_queue import AnalysisTaskQueue

        self.queue.shutdown()
        AnalysisTaskQueue._instance = self._original

    def _wait_status(self, task_id: str, expected, timeout: float = 3.0):
        from src.services.task_queue import TaskStatus

        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            last = self.queue.get_task(task_id)
            if last is not None and last.status == expected:
                return last
            if last is not None and last.status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.INTERRUPTED,
            }:
                return last
            time.sleep(0.01)
        return last

    def test_pending_cancel_reaches_cancelled_without_running_analysis(self) -> None:
        from src.services.task_queue import TaskStatus

        blocker_started = threading.Event()
        blocker_release = threading.Event()
        analyze_calls: list[str] = []

        def blocker() -> dict:
            blocker_started.set()
            self.assertTrue(blocker_release.wait(timeout=2))
            return {"ok": True}

        self.queue.submit_background_task(
            blocker,
            stock_code="blocker",
            report_type="background",
        )
        self.assertTrue(blocker_started.wait(timeout=2))

        with (
            patch("src.api.v1.endpoints.analysis.get_task_queue", return_value=self.queue),
            patch(
                "src.services.analysis_service.AnalysisService.analyze_stock",
                side_effect=lambda **kwargs: analyze_calls.append(str(kwargs.get("stock_code") or "")),
            ),
        ):
            pending = self.queue.submit_task("600519")
            self.assertEqual(pending.status, TaskStatus.PENDING)
            payload = endpoint.cancel_analysis_task(pending.task_id)
            self.assertEqual(payload.status, "cancelled")
            repeated = endpoint.cancel_analysis_task(pending.task_id)
            self.assertEqual(repeated.status, "cancelled")

        blocker_release.set()
        future = self.queue._futures.get(pending.task_id)
        if future is not None and not future.cancelled():
            future.result(timeout=3)
        final = self._wait_status(pending.task_id, TaskStatus.CANCELLED)
        self.assertIsNotNone(final)
        self.assertEqual(final.status, TaskStatus.CANCELLED)
        self.assertEqual(analyze_calls, [])

    def test_processing_cancel_reaches_cancelled_without_undoing_persist(self) -> None:
        from src.services.task_queue import TaskStatus

        started = threading.Event()
        release = threading.Event()
        persisted = {"report": False, "notify": False}

        def slow_analyze(**kwargs):
            persisted["report"] = True
            persisted["notify"] = True
            started.set()
            self.assertTrue(release.wait(timeout=2))
            return {
                "query_id": kwargs.get("query_id"),
                "stock_code": kwargs.get("stock_code"),
                "stock_name": "贵州茅台",
            }

        with (
            patch("src.api.v1.endpoints.analysis.get_task_queue", return_value=self.queue),
            patch(
                "src.services.analysis_service.AnalysisService.analyze_stock",
                side_effect=slow_analyze,
            ),
        ):
            accepted = self.queue.submit_task("600519")
            self.assertTrue(started.wait(timeout=2))
            first = endpoint.cancel_analysis_task(accepted.task_id)
            self.assertIn(first.status, {"cancel_requested", "cancelled"})
            second = endpoint.cancel_analysis_task(accepted.task_id)
            self.assertIn(second.status, {"cancel_requested", "cancelled"})
            release.set()
            future = self.queue._futures.get(accepted.task_id)
            if future is not None:
                future.result(timeout=3)
            final = self._wait_status(accepted.task_id, TaskStatus.CANCELLED)
            self.assertIsNotNone(final)
            self.assertEqual(final.status, TaskStatus.CANCELLED)
            self.assertNotEqual(final.status, TaskStatus.FAILED)
            self.assertTrue(persisted["report"])
            self.assertTrue(persisted["notify"])

    def test_completed_cancel_is_idempotent_and_keeps_completed(self) -> None:
        from src.services.task_queue import TaskStatus

        with (
            patch("src.api.v1.endpoints.analysis.get_task_queue", return_value=self.queue),
            patch(
                "src.services.analysis_service.AnalysisService.analyze_stock",
                return_value={
                    "query_id": "done-1",
                    "stock_code": "600519",
                    "stock_name": "贵州茅台",
                },
            ),
        ):
            accepted = self.queue.submit_task("600519")
            future = self.queue._futures.get(accepted.task_id)
            if future is not None:
                future.result(timeout=3)
            done = self._wait_status(accepted.task_id, TaskStatus.COMPLETED)
            self.assertIsNotNone(done)
            self.assertEqual(done.status, TaskStatus.COMPLETED)
            payload = endpoint.cancel_analysis_task(accepted.task_id)
            self.assertEqual(payload.status, "completed")
            again = endpoint.cancel_analysis_task(accepted.task_id)
            self.assertEqual(again.status, "completed")

    def test_wrong_kind_on_real_queue_does_not_cancel(self) -> None:
        from src.services.task_queue import TaskStatus

        started = threading.Event()
        release = threading.Event()

        def slow_background() -> dict:
            started.set()
            self.assertTrue(release.wait(timeout=2))
            return {"ok": True}

        with patch("src.api.v1.endpoints.analysis.get_task_queue", return_value=self.queue):
            background = self.queue.submit_background_task(
                slow_background,
                stock_code="market_review",
                report_type="detailed",
            )
            self.assertTrue(started.wait(timeout=2))
            with self.assertRaises(HTTPException) as caught:
                endpoint.cancel_analysis_task(background.task_id)
            self.assertEqual(caught.exception.status_code, 404)
            live = self.queue.get_task(background.task_id)
            self.assertIsNotNone(live)
            self.assertIn(live.status, {TaskStatus.PROCESSING, TaskStatus.PENDING})
            release.set()
            future = self.queue._futures.get(background.task_id)
            if future is not None:
                future.result(timeout=3)


if __name__ == "__main__":
    unittest.main()
