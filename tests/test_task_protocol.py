from concurrent.futures import Future
from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.v1.endpoints.analysis import get_analysis_status, get_task_list, trigger_analysis
from api.v1.schemas.analysis import AnalyzeRequest
from src.services.task_queue import AnalysisTaskQueue, TaskInfo, TaskStatus


class _PendingExecutor:
    def submit(self, *_args, **_kwargs):
        return Future()


class _InlineExecutor:
    def submit(self, fn, *args, **kwargs):
        future = Future()
        future.set_result(fn(*args, **kwargs))
        return future


def _fresh_queue() -> AnalysisTaskQueue:
    AnalysisTaskQueue._instance = None
    queue = AnalysisTaskQueue(max_workers=1)
    queue._executor = _PendingExecutor()
    return queue


def test_task_lifecycle_payload_uses_stable_codes_and_monotonic_revisions() -> None:
    queue = _fresh_queue()

    task = queue.submit_task("600519")
    created_payload = task.to_dict()

    assert created_payload["message_code"] == "task_queued"
    assert created_payload["message_params"] == {"stock_code": "600519"}
    assert created_payload["error_code"] is None
    assert created_payload["error_params"] == {}
    assert created_payload["revision"] == 1
    assert datetime.fromisoformat(created_payload["updated_at"])

    updated = queue.update_task_progress(
        task.task_id,
        62,
        "LLM 正在生成分析结果",
    )

    assert updated is not None
    assert updated.message_code == "task_progress"
    assert updated.message_params == {"progress": 62}
    assert updated.revision == 2
    assert updated.updated_at >= task.updated_at


def test_failed_background_task_redacts_raw_error_from_client_payload() -> None:
    queue = _fresh_queue()
    queue._executor = _InlineExecutor()

    def fail() -> None:
        raise RuntimeError("upstream secret leaked only in diagnostics")

    accepted = queue.submit_background_task(fail, stock_code="market_review")
    failed = queue.get_task(accepted.task_id)

    assert failed is not None
    assert failed.status.value == "failed"
    assert failed.message_code == "task_failed"
    assert failed.message_params == {}
    assert failed.error_code == "task_execution_failed"
    assert failed.error_params == {}
    assert failed.message == "Task failed"
    assert failed.error == "Task execution failed"
    payload = failed.to_dict()
    assert "upstream secret" not in json.dumps(payload)
    assert failed.revision == 3


def test_analysis_list_and_status_expose_the_same_versioned_task_contract() -> None:
    task = TaskInfo(
        task_id="task-1",
        trace_id="trace-1",
        stock_code="600519",
        status=TaskStatus.PROCESSING,
        progress=40,
        message="正在分析中...",
        message_code="task_started",
        message_params={"stock_code": "600519"},
        error_code=None,
        error_params={},
        revision=7,
        updated_at=datetime(2026, 7, 15, 12, 0, 0),
    )
    queue = MagicMock()
    queue.list_all_tasks.return_value = [task]
    queue.get_task_stats.return_value = {
        "total": 1,
        "pending": 0,
        "processing": 1,
    }
    queue.get_task.return_value = task

    with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
        listed = get_task_list(status=None, limit=20).tasks[0].model_dump()
        status = get_analysis_status(task.task_id).model_dump()

    for payload in (listed, status):
        assert payload["message"] == "正在分析中..."
        assert payload["message_code"] == "task_started"
        assert payload["message_params"] == {"stock_code": "600519"}
        assert payload["error_code"] is None
        assert payload["error_params"] == {}
        assert payload["revision"] == 7
        assert payload["updated_at"] == "2026-07-15T12:00:00"


def test_async_acceptance_returns_the_server_task_revision_for_immediate_upsert() -> None:
    task = TaskInfo(
        task_id="task-accepted",
        trace_id="task-accepted",
        stock_code="600519",
        message="任务已加入队列",
        message_code="task_queued",
        message_params={"stock_code": "600519"},
        revision=1,
        updated_at=datetime(2026, 7, 15, 12, 0, 0),
    )
    queue = MagicMock()
    queue.submit_tasks_batch.return_value = ([task], [])

    with patch("api.v1.endpoints.analysis.get_task_queue", return_value=queue):
        response = trigger_analysis(
            AnalyzeRequest(stock_code="600519", async_mode=True),
            config=SimpleNamespace(),
        )

    payload = json.loads(response.body)
    assert payload["task_id"] == "task-accepted"
    assert payload["message_code"] == "task_queued"
    assert payload["message_params"] == {"stock_code": "600519"}
    assert payload["revision"] == 1
    assert payload["updated_at"] == "2026-07-15T12:00:00"
