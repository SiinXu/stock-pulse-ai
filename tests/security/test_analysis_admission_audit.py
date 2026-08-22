# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed analysis.submit coverage for DAG-1 admission paths."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.v1.endpoints import analysis as analysis_endpoint
from src.api.v1.endpoints import portfolio as portfolio_endpoint
from src.api.v1.schemas.analysis import AnalyzeRequest
from src.api.v1.schemas.portfolio import PortfolioPositionAnalysisRequest
from src.bot.commands.analyze import AnalyzeCommand
from src.bot.models import BotMessage, ChatType
from src.config import Config
from src.services.task_queue import DuplicateTaskError, TaskInfo
from src.storage import DatabaseManager
from tests.security.test_security_audit_integrations import _RecordingAudit
from tests.services.test_scheduled_task_service import (
    DUE,
    NOW,
    FakeTaskQueue,
    RejectingSubmitQueue,
    build_service,
    research_contract,
    task_contract,
)


@pytest.fixture
def scheduled_database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'scheduled-audit.sqlite'}")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


CANARY = "admission-audit-canary-secret"
PII_USER = "user-canary-42"
PII_CHAT = "chat-canary-99"


def _feishu_message(content: str) -> BotMessage:
    return BotMessage(
        platform="feishu",
        message_id="m-canary",
        user_id=PII_USER,
        user_name="Alice Canary",
        chat_id=PII_CHAT,
        chat_type=ChatType.PRIVATE,
        content=content,
        raw_content=content,
        mentioned=True,
        timestamp=datetime.now(),
    )


def _visible_audit_payload(audit: _RecordingAudit) -> str:
    return json.dumps(
        {"attempts": audit.attempts, "completions": audit.completions},
        ensure_ascii=False,
        default=str,
    )


def _analysis_attempts(audit: _RecordingAudit) -> list[dict]:
    return [event for event in audit.attempts if event.get("event_type") == "analysis.submit"]


def _analysis_completions(audit: _RecordingAudit) -> list[dict]:
    return [
        event
        for event in audit.completions
        if event.get("event_type") == "analysis.submit"
    ]


def test_bot_attempt_failure_prevents_queue_submission() -> None:
    audit = _RecordingAudit(fail_attempt=True)
    queue = MagicMock()
    with patch(
        "src.services.task_queue.get_task_queue",
        return_value=queue,
    ), patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        response = AnalyzeCommand().execute(
            _feishu_message("/analyze 600519"),
            ["600519"],
        )

    assert "分析失败" in response.text
    queue.submit_tasks_batch.assert_not_called()
    queue.submit_task.assert_not_called()
    assert audit.attempts == []
    assert audit.completions == []


def test_bot_accepts_with_bot_actor_and_redacts_request_pii() -> None:
    audit = _RecordingAudit()
    accepted = SimpleNamespace(task_id="bot-task-1", stock_code="600519")
    queue = MagicMock()
    queue.submit_tasks_batch.return_value = ([accepted], [])

    with patch(
        "src.services.task_queue.get_task_queue",
        return_value=queue,
    ), patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        response = AnalyzeCommand().execute(
            _feishu_message("/analyze 600519"),
            ["600519"],
        )

    assert "分析任务已提交" in response.text
    kwargs = queue.submit_tasks_batch.call_args.kwargs
    assert kwargs["query_source"] == "bot"
    assert kwargs["request_context"].requester_user_id == PII_USER
    assert kwargs["request_context"].requester_chat_id == PII_CHAT
    assert len(audit.attempts) == 1
    assert len(audit.completions) == 1
    assert audit.attempts[0]["event_type"] == "analysis.submit"
    assert audit.attempts[0]["actor_type"] == "bot"
    assert audit.attempts[0]["actor_id"] == "bot"
    assert audit.attempts[0]["target_id"] == "600519"
    assert audit.completions[0]["outcome"] == "accepted"
    assert audit.attempts[0]["correlation_id"] == audit.completions[0]["correlation_id"]
    assert audit.attempts[0]["metadata"]["query_source"] == "bot"
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible
    assert PII_USER not in visible
    assert PII_CHAT not in visible
    assert "Alice Canary" not in visible


def test_bot_duplicate_records_rejected_completion() -> None:
    audit = _RecordingAudit()
    queue = MagicMock()
    queue.submit_tasks_batch.return_value = (
        [],
        [DuplicateTaskError("600519", "existing-task-id")],
    )

    with patch(
        "src.services.task_queue.get_task_queue",
        return_value=queue,
    ), patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        response = AnalyzeCommand().execute(
            _feishu_message("/analyze 600519"),
            ["600519"],
        )

    assert "正在分析中" in response.text
    assert audit.completions[0]["outcome"] == "rejected"
    assert audit.completions[0]["reason_code"] == "duplicate_task"


def test_portfolio_attempt_failure_prevents_queue_and_returns_503() -> None:
    audit = _RecordingAudit(fail_attempt=True)
    queue = MagicMock()
    context = {
        "symbol": "600519",
        "account_id": 7,
        "quantity": 10.0,
        "cost_method": "fifo",
        "api_key": CANARY,
    }
    with patch(
        "src.api.v1.endpoints.portfolio.PortfolioService",
        return_value=MagicMock(),
    ), patch(
        "src.api.v1.endpoints.portfolio._resolve_position_analysis_context",
        return_value=context,
    ), patch(
        "src.api.v1.endpoints.portfolio.get_task_queue",
        return_value=queue,
    ):
        with pytest.raises(HTTPException) as exc_info:
            portfolio_endpoint.analyze_position(
                "600519",
                PortfolioPositionAnalysisRequest(account_id=7),
                security_audit=audit,
            )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "security_audit_unavailable"
    queue.submit_tasks_batch.assert_not_called()


@pytest.mark.parametrize("override", [None, object()])
def test_portfolio_dependency_override_rejects_before_queue_submission(override) -> None:
    queue = MagicMock()
    app = FastAPI()
    app.include_router(portfolio_endpoint.router, prefix="/api/v1/portfolio")
    app.dependency_overrides[api_deps.get_security_audit_service] = lambda: override

    with patch(
        "src.api.v1.endpoints.portfolio.PortfolioService",
        return_value=MagicMock(),
    ), patch(
        "src.api.v1.endpoints.portfolio._resolve_position_analysis_context",
        return_value={"symbol": "600519", "account_id": 1, "quantity": 1.0},
    ), patch(
        "src.api.v1.endpoints.portfolio.get_task_queue",
        return_value=queue,
    ):
        response = TestClient(app).post(
            "/api/v1/portfolio/positions/600519/analysis",
            json={"account_id": 1},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "security_audit_unavailable"
    queue.submit_tasks_batch.assert_not_called()


def test_portfolio_accept_uses_portfolio_actor_and_omits_holding_pii() -> None:
    audit = _RecordingAudit()
    queue = MagicMock()
    queue.submit_tasks_batch.return_value = (
        [SimpleNamespace(
            task_id="task-portfolio-1",
            trace_id="trace-portfolio-1",
            stock_code="600519",
            analysis_phase="intraday",
            message_code="task.queued",
            message_params={"stock_code": "600519"},
        )],
        [],
    )
    context = {
        "symbol": "600519",
        "account_id": 7,
        "quantity": 10.0,
        "cost_method": "fifo",
        "api_key": CANARY,
    }
    with patch(
        "src.api.v1.endpoints.portfolio.PortfolioService",
        return_value=MagicMock(),
    ), patch(
        "src.api.v1.endpoints.portfolio._resolve_position_analysis_context",
        return_value=context,
    ), patch(
        "src.api.v1.endpoints.portfolio.get_task_queue",
        return_value=queue,
    ):
        response = portfolio_endpoint.analyze_position(
            "600519",
            PortfolioPositionAnalysisRequest(account_id=7, analysis_phase="intraday"),
            security_audit=audit,
        )

    assert response.task_id == "task-portfolio-1"
    kwargs = queue.submit_tasks_batch.call_args.kwargs
    assert kwargs["query_source"] == "portfolio"
    assert kwargs["portfolio_context"]["quantity"] == 10.0
    assert audit.attempts[0]["actor_id"] == "portfolio_submitter"
    assert audit.attempts[0]["metadata"]["query_source"] == "portfolio"
    assert audit.completions[0]["outcome"] == "accepted"
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible
    assert "10.0" not in visible
    assert "quantity" not in visible
    assert "account_id" not in visible


def test_sync_analyze_attempt_failure_prevents_analysis_and_returns_503() -> None:
    audit = _RecordingAudit(fail_attempt=True)
    service = MagicMock()
    with patch(
        "src.services.analysis_service.AnalysisService",
        return_value=service,
    ):
        with pytest.raises(HTTPException) as exc_info:
            analysis_endpoint.trigger_analysis(
                request=AnalyzeRequest(stock_code="AAPL", async_mode=False),
                config=SimpleNamespace(),
                security_audit=audit,
            )

    assert exc_info.value.status_code == 503
    service.analyze_stock.assert_not_called()
    assert audit.completions == []


def test_sync_analyze_success_and_failure_use_correlated_completions() -> None:
    success_audit = _RecordingAudit()
    success_service = MagicMock()
    success_service.analyze_stock.return_value = {
        "stock_code": "AAPL",
        "stock_name": "Apple",
        "report": {},
        "trace_id": "trace-sync",
    }
    with patch(
        "src.services.analysis_service.AnalysisService",
        return_value=success_service,
    ), patch.object(
        analysis_endpoint,
        "_load_sync_fundamental_sources",
        return_value=(None, None, None),
    ), patch.object(
        analysis_endpoint,
        "_build_analysis_report",
        return_value=SimpleNamespace(model_dump=lambda: {"ok": True}),
    ):
        response = analysis_endpoint.trigger_analysis(
            request=AnalyzeRequest(stock_code="AAPL", async_mode=False),
            config=SimpleNamespace(),
            security_audit=success_audit,
        )

    assert response.stock_code == "AAPL"
    assert success_audit.attempts[0]["metadata"]["execution_mode"] == "sync"
    assert success_audit.attempts[0]["actor_id"] == "analysis_submitter"
    assert success_audit.completions[0]["outcome"] == "success"
    assert success_audit.completions[0]["reason_code"] == "analysis_completed"
    assert (
        success_audit.attempts[0]["correlation_id"]
        == success_audit.completions[0]["correlation_id"]
    )

    failure_audit = _RecordingAudit()
    failure_service = MagicMock()
    failure_service.analyze_stock.return_value = None
    failure_service.last_error = f"upstream leaked {CANARY}"
    failure_service.last_error_code = None
    with patch(
        "src.services.analysis_service.AnalysisService",
        return_value=failure_service,
    ):
        with pytest.raises(HTTPException) as exc_info:
            analysis_endpoint.trigger_analysis(
                request=AnalyzeRequest(stock_code="AAPL", async_mode=False),
                config=SimpleNamespace(),
                security_audit=failure_audit,
            )

    assert exc_info.value.status_code == 500
    assert failure_audit.completions[0]["outcome"] == "failure"
    assert failure_audit.completions[0]["reason_code"] == "analysis_failed"
    visible = _visible_audit_payload(failure_audit)
    assert CANARY not in visible


def test_scheduled_attempt_failure_prevents_dispatch(scheduled_database) -> None:
    queue = FakeTaskQueue()
    audit = _RecordingAudit()
    service = build_service(
        scheduled_database,
        queue,
        security_audit_factory=lambda: audit,
    )
    task = service.create_task(task_contract(), now=NOW)
    audit.fail_attempt = True

    result = service.tick(now=DUE)

    assert result["claimed"] == 1
    assert queue.submit_calls == []
    run = service.list_runs(task["id"])["items"][0]
    assert run["error_code"] == "security_audit_unavailable"
    assert _analysis_attempts(audit) == []
    assert _analysis_completions(audit) == []


def test_scheduled_dispatch_records_scheduler_actor_without_payload_secrets(
    scheduled_database,
) -> None:
    queue = FakeTaskQueue()
    audit = _RecordingAudit()
    service = build_service(
        scheduled_database,
        queue,
        security_audit_factory=lambda: audit,
    )
    service.create_task(task_contract(), now=NOW)

    service.tick(now=DUE)

    assert len(queue.submit_calls) == 1
    assert queue.submit_calls[0]["query_source"] == "scheduled_task"
    attempts = _analysis_attempts(audit)
    completions = _analysis_completions(audit)
    assert attempts[0]["event_type"] == "analysis.submit"
    assert attempts[0]["actor_type"] == "scheduler"
    assert attempts[0]["actor_id"] == "scheduled_task"
    assert attempts[0]["target_id"] == "600519"
    assert completions[0]["outcome"] == "accepted"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert attempts[0]["metadata"]["query_source"] == "scheduled_task"
    visible = _visible_audit_payload(audit)
    assert "password" not in visible
    assert CANARY not in visible


def _analysis_contract_with_report_type(report_type: str) -> dict:
    contract = task_contract()
    contract["payload"]["report_type"] = report_type
    return contract


@pytest.mark.parametrize(
    ("contract", "expected_report_type"),
    [
        (_analysis_contract_with_report_type("simple"), "simple"),
        (_analysis_contract_with_report_type("full"), "full"),
        (_analysis_contract_with_report_type("brief"), "brief"),
        (research_contract("research_brief"), "brief"),
        (research_contract("risk_check"), "detailed"),
    ],
)
def test_scheduled_audit_records_admitted_report_type(
    scheduled_database,
    contract,
    expected_report_type,
) -> None:
    queue = FakeTaskQueue()
    audit = _RecordingAudit()
    service = build_service(
        scheduled_database,
        queue,
        security_audit_factory=lambda: audit,
    )
    service.create_task(contract, now=NOW)

    service.tick(now=DUE)

    assert queue.submit_calls[0]["report_type"] == expected_report_type
    attempts = _analysis_attempts(audit)
    completions = _analysis_completions(audit)
    assert attempts[0]["metadata"]["report_type"] == expected_report_type
    assert completions[0]["metadata"]["report_type"] == expected_report_type
    assert completions[0]["outcome"] == "accepted"


def test_scheduled_invalid_execution_id_does_not_audit_as_accepted(
    scheduled_database,
) -> None:
    class EmptyExecutionIdQueue(FakeTaskQueue):
        def submit_tasks_batch(self, **kwargs):
            self.submit_calls.append(kwargs)
            return [SimpleNamespace(task_id="")], []

    queue = EmptyExecutionIdQueue()
    audit = _RecordingAudit()
    service = build_service(
        scheduled_database,
        queue,
        security_audit_factory=lambda: audit,
    )
    task = service.create_task(task_contract(), now=NOW)

    service.tick(now=DUE)

    run = service.list_runs(task["id"])["items"][0]
    assert run["status"] == "interrupted"
    assert run["error_code"] == "scheduled_task_dispatch_state_lost"
    completions = _analysis_completions(audit)
    assert completions[0]["outcome"] == "failure"
    assert completions[0]["reason_code"] == "submission_not_resolved"


def test_scheduled_queue_rejection_completes_as_failure(scheduled_database) -> None:
    queue = RejectingSubmitQueue()
    audit = _RecordingAudit()
    service = build_service(
        scheduled_database,
        queue,
        security_audit_factory=lambda: audit,
    )
    service.create_task(task_contract(), now=NOW)

    service.tick(now=DUE)

    assert len(queue.submit_calls) == 1
    attempts = _analysis_attempts(audit)
    completions = _analysis_completions(audit)
    assert completions[0]["outcome"] == "failure"
    assert completions[0]["reason_code"] == "task_submission_failed"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]


def test_existing_async_http_analysis_submit_contract_is_unchanged() -> None:
    audit = _RecordingAudit()
    queue = MagicMock()
    queue.submit_tasks_batch.return_value = (
        [TaskInfo(task_id="task-1", stock_code="AAPL")],
        [],
    )
    with patch.object(analysis_endpoint, "get_task_queue", return_value=queue):
        response = analysis_endpoint.trigger_analysis(
            request=AnalyzeRequest(stock_code="AAPL", async_mode=True),
            config=SimpleNamespace(),
            security_audit=audit,
        )

    assert response.status_code == 202
    assert audit.attempts[0]["actor_type"] == "api_client"
    assert audit.attempts[0]["actor_id"] == "analysis_submitter"
    assert "query_source" not in audit.attempts[0]["metadata"]
    assert "execution_mode" not in audit.attempts[0]["metadata"]
