# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed HTTP background.submit security-audit coverage (#1062 DAG-6)."""

from __future__ import annotations

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api import deps as api_deps
from src.api.v1.endpoints import alphasift as alphasift_endpoint
from src.api.v1.endpoints import analysis as analysis_endpoint
from src.api.v1.endpoints import candidate_discovery as discovery_endpoint
from src.api.v1.schemas.alphasift import AlphaSiftScreenRequest
from src.api.v1.schemas.analysis import MarketReviewRequest
from src.api.v1.schemas.candidate_discovery import (
    CandidateDiscoveryCriteria,
    CandidateDiscoveryRequest,
)
from src.api.v1.services.background_submit_audit import (
    BACKGROUND_SUBMIT_ACTION,
    BACKGROUND_SUBMIT_EVENT_TYPE,
    BACKGROUND_SUBMIT_TARGET_TYPE,
    KIND_ALPHASIFT_SCREEN,
    KIND_CANDIDATE_DISCOVERY,
    KIND_MARKET_REVIEW,
    background_submit_metadata,
)
from src.config import Config
from src.repositories.security_audit_repo import SecurityAuditRepository
from src.services.security_audit_service import SecurityAuditService
from src.services.task_queue import TaskStatus as QueueTaskStatus
from src.storage import DatabaseManager
from tests.security.test_security_audit_integrations import _RecordingAudit


CANARY = "background-submit-canary-secret"
CANARY_QUERY = "银行"
CANARY_CODE = "600519"
CANARY_TOKEN = f"sk-{CANARY}"


@pytest.fixture
def submit_database(tmp_path):
    DatabaseManager.reset_instance()
    Config.reset_instance()
    manager = DatabaseManager(db_url=f"sqlite:///{tmp_path / 'background-submit-audit.sqlite'}")
    try:
        yield manager
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _visible_audit_payload(audit: _RecordingAudit) -> str:
    return json.dumps(
        {"attempts": audit.attempts, "completions": audit.completions},
        ensure_ascii=False,
        default=str,
    )


def _submit_events(audit: _RecordingAudit, *, phase: str) -> list[dict]:
    source = audit.attempts if phase == "attempt" else audit.completions
    return [
        event
        for event in source
        if event.get("event_type") == BACKGROUND_SUBMIT_EVENT_TYPE
    ]


def _analysis_submit_events(audit: _RecordingAudit) -> list[dict]:
    return [
        event
        for event in (*audit.attempts, *audit.completions)
        if event.get("event_type") == "analysis.submit"
    ]


def _queued_task(task_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        task_id=task_id,
        trace_id=task_id,
        status=QueueTaskStatus.PENDING,
        message="queued",
        message_code="task.queued",
        message_params={},
    )


def _echo_queued_task(*_args, **kwargs) -> SimpleNamespace:
    task_id = kwargs.get("task_id") or "echo-task"
    return _queued_task(str(task_id))


def _market_config() -> SimpleNamespace:
    return SimpleNamespace(
        trading_day_check_enabled=False,
        market_review_region="cn",
        report_language="zh",
    )


def _http_app(router, prefix: str, audit, *, config=None):
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    app.dependency_overrides[api_deps.require_security_audit_service] = lambda: audit
    app.dependency_overrides[api_deps.get_config_dep] = lambda: config or SimpleNamespace()
    return app


def _assert_accepted_pair(audit: _RecordingAudit, *, kind: str, task_id: str) -> None:
    attempts = _submit_events(audit, phase="attempt")
    completions = _submit_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert attempts[0]["action"] == BACKGROUND_SUBMIT_ACTION
    assert attempts[0]["target_type"] == BACKGROUND_SUBMIT_TARGET_TYPE
    assert attempts[0]["target_id"] == task_id
    assert attempts[0]["actor_type"] == "api_client"
    assert attempts[0]["actor_id"] == "background_submitter"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]
    assert completions[0]["outcome"] == "accepted"
    assert completions[0]["reason_code"] == "accepted"
    assert completions[0]["metadata"]["kind"] == kind
    assert completions[0]["metadata"]["report_type"] == kind
    assert completions[0]["metadata"]["stock_code"] == kind
    assert _analysis_submit_events(audit) == []


def test_metadata_allowlist_drops_query_codes_and_secrets() -> None:
    payload = background_submit_metadata(
        KIND_CANDIDATE_DISCOVERY,
        universe="watchlist",
        page=1,
        page_size=20,
        max_results=5,
        max_provider_calls=10,
        use_llm=False,
        query=CANARY_QUERY,
        codes=[CANARY_CODE],
        criteria={"keywords": [CANARY_QUERY]},
        keywords=[CANARY_QUERY],
        account_id=42,
        cookie=CANARY,
        token=CANARY_TOKEN,
        prompt="leak me",
    )
    assert payload["kind"] == KIND_CANDIDATE_DISCOVERY
    assert payload["universe"] == "watchlist"
    assert payload["page"] == 1
    assert payload["use_llm"] is False
    for forbidden in (
        "query",
        "codes",
        "criteria",
        "keywords",
        "account_id",
        "cookie",
        "token",
        "prompt",
    ):
        assert forbidden not in payload
    dumped = json.dumps(payload, ensure_ascii=False)
    assert CANARY_QUERY not in dumped
    assert CANARY_CODE not in dumped
    assert CANARY not in dumped
    assert CANARY_TOKEN not in dumped


def test_market_review_success_records_attempt_and_accepted_completion() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    fake_queue.submit_background_task.side_effect = _echo_queued_task
    request = SimpleNamespace(send_notification=False, report_language=None, region=None)
    with patch.object(
        analysis_endpoint,
        "_try_acquire_market_review_lock",
        return_value=object(),
    ) as acquire, patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        response = analysis_endpoint.trigger_market_review(
            request=request,
            config=_market_config(),
            security_audit=audit,
        )
    assert response.status == "accepted"
    queued_id = fake_queue.submit_background_task.call_args.kwargs["task_id"]
    assert response.task_id == queued_id
    acquire.assert_called_once()
    fake_queue.submit_background_task.assert_called_once()
    _assert_accepted_pair(audit, kind=KIND_MARKET_REVIEW, task_id=queued_id)
    assert audit.completions[0]["metadata"]["region"] == "cn"
    assert audit.completions[0]["metadata"]["send_notification"] is False


def test_candidate_discovery_success_records_attempt_and_accepted_completion() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    fake_queue.submit_background_task.side_effect = _echo_queued_task
    request = CandidateDiscoveryRequest(
        query=CANARY_QUERY,
        universe="index",
        page=1,
        page_size=20,
        max_results=5,
        max_provider_calls=10,
        codes=[CANARY_CODE],
        criteria=CandidateDiscoveryCriteria(keywords=[CANARY_QUERY]),
        account_id=42,
        use_llm=True,
    )
    with patch(
        "src.api.v1.endpoints.candidate_discovery.get_task_queue",
        return_value=fake_queue,
    ):
        accepted = discovery_endpoint.start_candidate_discovery_task(
            request,
            config=SimpleNamespace(),
            security_audit=audit,
        )
    queued_id = fake_queue.submit_background_task.call_args.kwargs["task_id"]
    assert accepted.task_id == queued_id
    fake_queue.submit_background_task.assert_called_once()
    _assert_accepted_pair(audit, kind=KIND_CANDIDATE_DISCOVERY, task_id=queued_id)
    metadata = audit.completions[0]["metadata"]
    assert metadata["universe"] == "index"
    assert metadata["page"] == 1
    assert metadata["page_size"] == 20
    assert metadata["max_results"] == 5
    assert metadata["max_provider_calls"] == 10
    assert metadata["use_llm"] is True
    visible = _visible_audit_payload(audit)
    assert CANARY_QUERY not in visible
    assert CANARY_CODE not in visible
    assert "query" not in metadata
    assert "codes" not in metadata
    assert "criteria" not in metadata
    assert "keywords" not in metadata
    assert "account_id" not in metadata


def test_alphasift_success_records_attempt_and_accepted_completion() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    fake_queue.submit_background_task.side_effect = _echo_queued_task
    with patch(
        "src.api.v1.endpoints.alphasift.get_task_queue",
        return_value=fake_queue,
    ):
        accepted = alphasift_endpoint.alphasift_start_screen_task(
            AlphaSiftScreenRequest(market="cn", strategy="dual_low", max_results=3),
            http_request=MagicMock(),
            config=MagicMock(),
            security_audit=audit,
        )
    queued_id = fake_queue.submit_background_task.call_args.kwargs["task_id"]
    assert accepted.task_id == queued_id
    fake_queue.submit_background_task.assert_called_once()
    _assert_accepted_pair(audit, kind=KIND_ALPHASIFT_SCREEN, task_id=queued_id)
    metadata = audit.completions[0]["metadata"]
    assert metadata["strategy"] == "dual_low"
    assert metadata["market"] == "cn"
    assert metadata["max_results"] == 3


@pytest.mark.parametrize(
    ("kind", "call", "queue_patch", "lock_patch"),
    [
        (
            KIND_MARKET_REVIEW,
            lambda audit, queue: analysis_endpoint.trigger_market_review(
                request=SimpleNamespace(
                    send_notification=True,
                    report_language=None,
                    region=None,
                ),
                config=_market_config(),
                security_audit=audit,
            ),
            "src.api.v1.endpoints.analysis.get_task_queue",
            True,
        ),
        (
            KIND_CANDIDATE_DISCOVERY,
            lambda audit, queue: discovery_endpoint.start_candidate_discovery_task(
                CandidateDiscoveryRequest(universe="watchlist"),
                config=SimpleNamespace(),
                security_audit=audit,
            ),
            "src.api.v1.endpoints.candidate_discovery.get_task_queue",
            False,
        ),
        (
            KIND_ALPHASIFT_SCREEN,
            lambda audit, queue: alphasift_endpoint.alphasift_start_screen_task(
                AlphaSiftScreenRequest(),
                http_request=MagicMock(),
                config=MagicMock(),
                security_audit=audit,
            ),
            "src.api.v1.endpoints.alphasift.get_task_queue",
            False,
        ),
    ],
)
def test_attempt_failure_does_not_queue(kind, call, queue_patch, lock_patch) -> None:
    audit = _RecordingAudit(fail_attempt=True)
    fake_queue = MagicMock()
    fake_queue.submit_background_task.return_value = _queued_task("should-not-queue")
    acquire = MagicMock(return_value=object())
    with ExitStack() as stack:
        stack.enter_context(patch(queue_patch, return_value=fake_queue))
        if lock_patch:
            stack.enter_context(
                patch.object(
                    analysis_endpoint,
                    "_try_acquire_market_review_lock",
                    acquire,
                )
            )
        with pytest.raises(HTTPException) as caught:
            call(audit, fake_queue)
    assert caught.value.status_code == 503
    assert caught.value.detail["operation_completed"] is False
    fake_queue.submit_background_task.assert_not_called()
    if lock_patch:
        acquire.assert_not_called()
    assert audit.attempts == []
    assert audit.completions == []


@pytest.mark.parametrize(
    ("kind", "call", "queue_patch", "lock_patch"),
    [
        (
            KIND_MARKET_REVIEW,
            lambda audit: analysis_endpoint.trigger_market_review(
                request=SimpleNamespace(
                    send_notification=False,
                    report_language=None,
                    region=None,
                ),
                config=_market_config(),
                security_audit=audit,
            ),
            "src.api.v1.endpoints.analysis.get_task_queue",
            True,
        ),
        (
            KIND_CANDIDATE_DISCOVERY,
            lambda audit: discovery_endpoint.start_candidate_discovery_task(
                CandidateDiscoveryRequest(universe="watchlist"),
                config=SimpleNamespace(),
                security_audit=audit,
            ),
            "src.api.v1.endpoints.candidate_discovery.get_task_queue",
            False,
        ),
        (
            KIND_ALPHASIFT_SCREEN,
            lambda audit: alphasift_endpoint.alphasift_start_screen_task(
                AlphaSiftScreenRequest(),
                http_request=MagicMock(),
                config=MagicMock(),
                security_audit=audit,
            ),
            "src.api.v1.endpoints.alphasift.get_task_queue",
            False,
        ),
    ],
)
def test_completion_failure_after_accept_keeps_queued_task(
    kind, call, queue_patch, lock_patch
) -> None:
    audit = _RecordingAudit(fail_completion=True)
    fake_queue = MagicMock()
    fake_queue.submit_background_task.side_effect = _echo_queued_task
    acquire = MagicMock(return_value=object())
    with ExitStack() as stack:
        stack.enter_context(patch(queue_patch, return_value=fake_queue))
        if lock_patch:
            stack.enter_context(
                patch.object(
                    analysis_endpoint,
                    "_try_acquire_market_review_lock",
                    acquire,
                )
            )
        with pytest.raises(HTTPException) as caught:
            call(audit)
    queued_id = fake_queue.submit_background_task.call_args.kwargs["task_id"]
    assert caught.value.status_code == 503
    detail = caught.value.detail
    assert detail["operation_completed"] is True
    assert detail["task_id"] == queued_id
    assert detail["kind"] == kind
    assert detail["status"] == "pending"
    fake_queue.submit_background_task.assert_called_once()
    if lock_patch:
        acquire.assert_called_once()
    assert _submit_events(audit, phase="attempt")
    assert _submit_events(audit, phase="completion") == []


def test_http_attempt_failure_reports_operation_completed_false() -> None:
    audit = _RecordingAudit(fail_attempt=True)
    fake_queue = MagicMock()
    app = _http_app(
        analysis_endpoint.router,
        "/api/v1/analysis",
        audit,
        config=_market_config(),
    )
    with patch.object(
        analysis_endpoint,
        "_try_acquire_market_review_lock",
        return_value=object(),
    ) as acquire, patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post("/api/v1/analysis/market-review", json={})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "security_audit_unavailable"
    assert detail["operation_completed"] is False
    acquire.assert_not_called()
    fake_queue.submit_background_task.assert_not_called()


def test_http_completion_failure_reports_operation_completed_true() -> None:
    audit = _RecordingAudit(fail_completion=True)
    fake_queue = MagicMock()
    fake_queue.submit_background_task.side_effect = _echo_queued_task
    app = _http_app(discovery_endpoint.router, "/api/v1/discover", audit)
    with patch(
        "src.api.v1.endpoints.candidate_discovery.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/discover/screen/tasks",
                json={"universe": "watchlist"},
            )
    queued_id = fake_queue.submit_background_task.call_args.kwargs["task_id"]
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["operation_completed"] is True
    assert detail["task_id"] == queued_id
    assert detail["kind"] == KIND_CANDIDATE_DISCOVERY
    fake_queue.submit_background_task.assert_called_once()


def test_duplicate_market_review_keeps_409_and_records_rejected() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    with patch.object(
        analysis_endpoint,
        "_try_acquire_market_review_lock",
        return_value=None,
    ), patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with pytest.raises(HTTPException) as caught:
            analysis_endpoint.trigger_market_review(
                request=SimpleNamespace(
                    send_notification=True,
                    report_language=None,
                    region=None,
                ),
                config=_market_config(),
                security_audit=audit,
            )
    assert caught.value.status_code == 409
    assert caught.value.detail["error"] == "duplicate_market_review"
    fake_queue.submit_background_task.assert_not_called()
    attempts = _submit_events(audit, phase="attempt")
    completions = _submit_events(audit, phase="completion")
    assert len(attempts) == 1
    assert len(completions) == 1
    assert completions[0]["outcome"] == "rejected"
    assert completions[0]["reason_code"] == "duplicate_market_review"
    assert attempts[0]["correlation_id"] == completions[0]["correlation_id"]


def test_duplicate_reject_completion_failure_still_409() -> None:
    audit = _RecordingAudit(fail_completion=True)
    fake_queue = MagicMock()
    with patch.object(
        analysis_endpoint,
        "_try_acquire_market_review_lock",
        return_value=None,
    ), patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with pytest.raises(HTTPException) as caught:
            analysis_endpoint.trigger_market_review(
                request=SimpleNamespace(
                    send_notification=True,
                    report_language=None,
                    region=None,
                ),
                config=_market_config(),
                security_audit=audit,
            )
    assert caught.value.status_code == 409
    fake_queue.submit_background_task.assert_not_called()
    assert _submit_events(audit, phase="attempt")
    assert _submit_events(audit, phase="completion") == []


def test_submit_exception_records_failure_and_releases_lock() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    fake_queue.submit_background_task.side_effect = RuntimeError("queue boom")
    release = MagicMock()
    with patch.object(
        analysis_endpoint,
        "_try_acquire_market_review_lock",
        return_value=object(),
    ), patch.object(
        analysis_endpoint,
        "_release_market_review_lock",
        release,
    ), patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with pytest.raises(RuntimeError, match="queue boom"):
            analysis_endpoint.trigger_market_review(
                request=SimpleNamespace(
                    send_notification=False,
                    report_language=None,
                    region=None,
                ),
                config=_market_config(),
                security_audit=audit,
            )
    release.assert_called_once()
    completions = _submit_events(audit, phase="completion")
    assert len(completions) == 1
    assert completions[0]["outcome"] == "failure"
    assert completions[0]["reason_code"] == "submit_failed"


def test_invalid_region_fails_before_attempt() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    acquire = MagicMock(return_value=object())
    with patch.object(
        analysis_endpoint,
        "_try_acquire_market_review_lock",
        acquire,
    ), patch(
        "src.api.v1.endpoints.analysis.get_task_queue",
        return_value=fake_queue,
    ):
        with pytest.raises(HTTPException) as caught:
            analysis_endpoint.trigger_market_review(
                request=MarketReviewRequest(region="mars"),
                config=_market_config(),
                security_audit=audit,
            )
    assert caught.value.status_code == 422
    acquire.assert_not_called()
    fake_queue.submit_background_task.assert_not_called()
    assert audit.attempts == []
    assert audit.completions == []


def test_discovery_validation_fails_before_attempt() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    app = _http_app(discovery_endpoint.router, "/api/v1/discover", audit)
    with patch(
        "src.api.v1.endpoints.candidate_discovery.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/discover/screen/tasks",
                json={"universe": "watchlist", "page_size": 999},
            )
    assert response.status_code == 422
    fake_queue.submit_background_task.assert_not_called()
    assert audit.attempts == []
    assert audit.completions == []


def test_alphasift_validation_fails_before_attempt() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    app = _http_app(alphasift_endpoint.router, "/api/v1/alphasift", audit)
    with patch(
        "src.api.v1.endpoints.alphasift.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/alphasift/screen/tasks",
                json={"max_results": 0},
            )
    assert response.status_code == 422
    fake_queue.submit_background_task.assert_not_called()
    assert audit.attempts == []
    assert audit.completions == []


def test_discovery_http_canaries_never_reach_metadata() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    fake_queue.submit_background_task.side_effect = _echo_queued_task
    app = _http_app(discovery_endpoint.router, "/api/v1/discover", audit)
    with patch(
        "src.api.v1.endpoints.candidate_discovery.get_task_queue",
        return_value=fake_queue,
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/discover/screen/tasks",
                headers={
                    "Cookie": f"session={CANARY}",
                    "Authorization": f"Bearer {CANARY_TOKEN}",
                },
                json={
                    "query": CANARY_QUERY,
                    "universe": "watchlist",
                    "page": 1,
                    "page_size": 20,
                    "max_results": 5,
                    "max_provider_calls": 10,
                    "codes": [CANARY_CODE],
                    "criteria": {"keywords": [CANARY_QUERY]},
                    "account_id": 42,
                    "use_llm": False,
                },
            )
    assert response.status_code == 202
    visible = _visible_audit_payload(audit)
    assert CANARY not in visible
    assert CANARY_TOKEN not in visible
    assert CANARY_QUERY not in visible
    assert CANARY_CODE not in visible
    metadata = audit.completions[0]["metadata"]
    for forbidden in (
        "query",
        "codes",
        "criteria",
        "keywords",
        "account_id",
        "cookie",
        "token",
        "prompt",
        "results",
    ):
        assert forbidden not in metadata


def test_discovery_cancel_and_direct_queue_submit_do_not_emit_background_submit() -> None:
    audit = _RecordingAudit()
    fake_queue = MagicMock()
    fake_queue.get_task.return_value = SimpleNamespace(
        task_id="disc-2",
        trace_id="disc-2",
        report_type="candidate_discovery",
        status=QueueTaskStatus.PROCESSING,
        progress=40,
        message="running",
        message_code="task.status",
        message_params={},
        error=None,
        result=None,
    )
    fake_queue.cancel.return_value = SimpleNamespace(
        task_id="disc-2",
        status=QueueTaskStatus.CANCEL_REQUESTED,
        progress=40,
        message="Cancel requested",
        message_code="task.cancel_requested",
        message_params={},
    )
    with patch(
        "src.api.v1.endpoints.candidate_discovery.get_task_queue",
        return_value=fake_queue,
    ), patch(
        "src.services.security_audit_service.get_security_audit_service",
        return_value=audit,
    ):
        discovery_endpoint.cancel_candidate_discovery_task("disc-2")
        fake_queue.submit_background_task(
            lambda: None,
            stock_code="direct-queue",
            stock_name="internal",
            report_type="candidate_discovery",
        )
    assert _submit_events(audit, phase="attempt") == []
    assert _submit_events(audit, phase="completion") == []
    assert _analysis_submit_events(audit) == []


def test_background_submit_events_are_queryable_from_durable_store(submit_database) -> None:
    store = SecurityAuditService(repository=SecurityAuditRepository(submit_database))
    fake_queue = MagicMock()
    fake_queue.submit_background_task.side_effect = _echo_queued_task
    request = CandidateDiscoveryRequest(
        query=CANARY_QUERY,
        universe="watchlist",
        codes=[CANARY_CODE],
        criteria=CandidateDiscoveryCriteria(keywords=[CANARY_QUERY]),
        account_id=7,
    )
    with patch(
        "src.api.v1.endpoints.candidate_discovery.get_task_queue",
        return_value=fake_queue,
    ):
        accepted = discovery_endpoint.start_candidate_discovery_task(
            request,
            config=SimpleNamespace(),
            security_audit=store,
        )
    queued_id = fake_queue.submit_background_task.call_args.kwargs["task_id"]
    assert accepted.task_id == queued_id
    page = store.list_events(event_type=BACKGROUND_SUBMIT_EVENT_TYPE, page_size=20)
    types = {(item.phase, item.action, item.outcome) for item in page.items}
    assert ("attempt", BACKGROUND_SUBMIT_ACTION, "pending") in types
    assert ("completion", BACKGROUND_SUBMIT_ACTION, "accepted") in types
    assert page.total >= 2
    dumped = json.dumps([item.model_dump(mode="json") for item in page.items], ensure_ascii=False)
    assert CANARY_QUERY not in dumped
    assert CANARY_CODE not in dumped
    assert all(item.event_type != "analysis.submit" for item in page.items)
    assert all(item.metadata.get("kind") == KIND_CANDIDATE_DISCOVERY for item in page.items)
