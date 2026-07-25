# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Fail-closed representative-path tests for security audit Phase 1."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.v1.endpoints import analysis as analysis_endpoint
from api.v1.endpoints import auth as auth_endpoint
from api.v1.endpoints import security_audit as security_audit_endpoint
from api.v1.endpoints import system_config as system_config_endpoint
from api.v1.schemas.analysis import AnalyzeRequest
from api.v1.schemas.system_config import UpdateSystemConfigRequest
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy, ToolRegistry
from src.core.config_registry import get_registered_field_keys
from src.schemas.security_audit import (
    SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS,
    SecurityAuditEvent,
    SecurityAuditEventCreate,
)
from src.services.security_audit_service import (
    SecurityAuditService,
    SecurityAuditUnavailable,
)
from src.services.task_queue import DuplicateTaskError, TaskInfo


class _RecordingAudit:
    def __init__(
        self,
        *,
        fail_attempt: bool = False,
        fail_completion: bool = False,
        fail_completion_at: int | None = None,
    ):
        self.fail_attempt = fail_attempt
        self.fail_completion = fail_completion
        self.fail_completion_at = fail_completion_at
        self.attempts = []
        self.completions = []

    def record_attempt(self, **fields):
        if self.fail_attempt:
            raise SecurityAuditUnavailable()
        self.attempts.append(fields)

    def record_completion(self, **fields):
        completion_number = len(self.completions) + 1
        if self.fail_completion or completion_number == self.fail_completion_at:
            raise SecurityAuditUnavailable()
        self.completions.append(fields)


class _SchemaValidatingAuditRepository:
    def __init__(self) -> None:
        self.events: list[SecurityAuditEvent] = []

    def apply_retention(self, *, cutoff) -> int:
        del cutoff
        return 0

    def append(self, event: SecurityAuditEventCreate) -> SecurityAuditEvent:
        validated = SecurityAuditEventCreate.model_validate(event.model_dump())
        persisted = SecurityAuditEvent(
            id=len(self.events) + 1,
            **validated.model_dump(),
        )
        self.events.append(persisted)
        return persisted


def _request():
    return SimpleNamespace(
        headers={},
        url=SimpleNamespace(scheme="http"),
        cookies={},
        client=SimpleNamespace(host="127.0.0.1"),
    )


def test_login_attempt_failure_does_not_verify_or_issue_cookie() -> None:
    audit = _RecordingAudit(fail_attempt=True)
    with patch.object(auth_endpoint, "is_auth_enabled", return_value=True), patch.object(
        auth_endpoint, "verify_password"
    ) as verify_password, patch.object(auth_endpoint, "create_session") as create_session:
        response = asyncio.run(
            auth_endpoint.auth_login(
                _request(),
                auth_endpoint.LoginRequest(password="secret-password"),
                security_audit=audit,
            )
        )

    assert response.status_code == 503
    assert b"security_audit_unavailable" in response.body
    assert "set-cookie" not in response.headers
    verify_password.assert_not_called()
    create_session.assert_not_called()


def test_login_success_uses_one_correlation_and_records_no_password() -> None:
    audit = _RecordingAudit()
    with patch.object(auth_endpoint, "is_auth_enabled", return_value=True), patch.object(
        auth_endpoint, "check_rate_limit", return_value=True
    ), patch.object(auth_endpoint, "is_password_set", return_value=True), patch.object(
        auth_endpoint, "verify_password", return_value=True
    ), patch.object(auth_endpoint, "clear_rate_limit"), patch.object(
        auth_endpoint, "create_session", return_value="session-value"
    ):
        response = asyncio.run(
            auth_endpoint.auth_login(
                _request(),
                auth_endpoint.LoginRequest(password="secret-password"),
                security_audit=audit,
            )
        )

    assert response.status_code == 200
    assert response.headers["set-cookie"].startswith("dsa_session=")
    assert audit.attempts[0]["correlation_id"] == audit.completions[0]["correlation_id"]
    assert audit.completions[0]["reason_code"] == "login_succeeded"
    assert "secret-password" not in repr((audit.attempts, audit.completions))


def test_login_completion_failure_is_surfaced_before_cookie_issue() -> None:
    audit = _RecordingAudit(fail_completion=True)
    with patch.object(auth_endpoint, "is_auth_enabled", return_value=True), patch.object(
        auth_endpoint, "check_rate_limit", return_value=True
    ), patch.object(auth_endpoint, "is_password_set", return_value=True), patch.object(
        auth_endpoint, "verify_password", return_value=True
    ), patch.object(auth_endpoint, "clear_rate_limit"), patch.object(
        auth_endpoint, "create_session", return_value="session-value"
    ):
        response = asyncio.run(
            auth_endpoint.auth_login(
                _request(),
                auth_endpoint.LoginRequest(password="secret-password"),
                security_audit=audit,
            )
        )

    assert response.status_code == 503
    assert "set-cookie" not in response.headers


def test_config_attempt_failure_prevents_service_mutation() -> None:
    audit = _RecordingAudit(fail_attempt=True)
    config_service = MagicMock()
    request = UpdateSystemConfigRequest(
        config_version="version-1",
        reload_now=False,
        items=[{"key": "GEMINI_API_KEY", "value": "must-not-persist"}],
    )

    with pytest.raises(HTTPException) as exc_info:
        system_config_endpoint.update_system_config(
            request=request,
            service=config_service,
            security_audit=audit,
        )

    assert exc_info.value.status_code == 503
    config_service.update.assert_not_called()
    assert "must-not-persist" not in repr(audit.attempts)


def test_config_success_records_keys_without_values() -> None:
    audit = _RecordingAudit()
    config_service = MagicMock()
    config_service.update.return_value = {
        "success": True,
        "config_version": "version-2",
        "applied_count": 1,
        "skipped_masked_count": 0,
        "reload_triggered": False,
        "updated_keys": ["GEMINI_API_KEY"],
        "warnings": [],
    }
    request = UpdateSystemConfigRequest(
        config_version="version-1",
        reload_now=False,
        items=[{"key": "GEMINI_API_KEY", "value": "must-not-persist"}],
    )

    response = system_config_endpoint.update_system_config(
        request=request,
        service=config_service,
        security_audit=audit,
    )

    assert response.success is True
    assert audit.completions[0]["reason_code"] == "config_updated"
    assert audit.attempts[0]["metadata"]["keys"] == ["GEMINI_API_KEY"]
    assert "must-not-persist" not in repr((audit.attempts, audit.completions))


def test_config_bulk_update_audits_every_registered_key_through_real_service() -> None:
    registered_keys = get_registered_field_keys()
    assert 64 < len(registered_keys) <= SECURITY_AUDIT_MAX_METADATA_LIST_ITEMS
    expected_keys = sorted(registered_keys)
    request = UpdateSystemConfigRequest(
        config_version="version-1",
        reload_now=False,
        items=[
            {"key": key, "value": f"bulk-value-{index}"}
            for index, key in enumerate(registered_keys)
        ],
    )
    config_service = MagicMock()
    config_service.update.return_value = {
        "success": True,
        "config_version": "version-2",
        "applied_count": len(registered_keys),
        "skipped_masked_count": 0,
        "reload_triggered": False,
        "updated_keys": registered_keys,
        "warnings": [],
    }
    repository = _SchemaValidatingAuditRepository()
    audit_service = SecurityAuditService(repository)

    with patch.object(
        system_config_endpoint,
        "_config_audit_actor",
        return_value="local_operator",
    ):
        response = system_config_endpoint.update_system_config(
            request=request,
            service=config_service,
            security_audit=audit_service,
        )

    assert response.success is True
    config_service.update.assert_called_once()
    submitted_items = config_service.update.call_args.kwargs["items"]
    assert [item["key"] for item in submitted_items] == registered_keys
    assert [event.phase for event in repository.events] == ["attempt", "completion"]
    assert repository.events[0].correlation_id == repository.events[1].correlation_id
    assert all(
        event.metadata["keys"] == expected_keys
        for event in repository.events
    )
    assert "bulk-value-" not in repr(repository.events)


def _tool_registry(calls):
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a bounded message.",
            parameters=[ToolParameter(name="message", type="string", description="Message")],
            handler=lambda message: calls.append(message) or {"message": message},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=[],
                permissions=["test:read"],
            ),
        )
    )
    return registry


def test_real_bound_tool_session_audits_allow_and_deny() -> None:
    calls = []
    audit = _RecordingAudit()
    registry = _tool_registry(calls)
    allowed = BoundToolSession(
        registry,
        execution_id="exec-allow",
        allowed_tools=["echo"],
        granted_permissions=["test:read"],
        principal="test-principal",
        security_audit=audit,
    )
    denied = BoundToolSession(
        registry,
        execution_id="exec-deny",
        allowed_tools=[],
        granted_permissions=["test:read"],
        principal="test-principal",
        security_audit=audit,
    )

    assert allowed.execute("echo", {"message": "ok"})["ok"] is True
    denied_result = denied.execute("echo", {"message": "blocked"})

    assert denied_result["error"]["code"] == "tool_not_allowed"
    assert calls == ["ok"]
    assert [item["outcome"] for item in audit.completions] == ["success", "denied"]
    assert all(
        attempt["correlation_id"] == completion["correlation_id"]
        for attempt, completion in zip(audit.attempts, audit.completions)
    )


def test_tool_attempt_failure_prevents_handler_dispatch() -> None:
    calls = []
    session = BoundToolSession(
        _tool_registry(calls),
        execution_id="exec-fail-closed",
        allowed_tools=["echo"],
        granted_permissions=["test:read"],
        security_audit=_RecordingAudit(fail_attempt=True),
    )

    result = session.execute("echo", {"message": "must-not-run"})

    assert result["error"]["code"] == "security_audit_unavailable"
    assert calls == []
    assert session.dispatched_calls == 0


def test_tool_completion_failure_surfaces_after_handler_dispatch() -> None:
    calls = []
    session = BoundToolSession(
        _tool_registry(calls),
        execution_id="exec-completion-failure",
        allowed_tools=["echo"],
        granted_permissions=["test:read"],
        security_audit=_RecordingAudit(fail_completion=True),
    )

    result = session.execute("echo", {"message": "ran-once"})

    assert result["error"]["code"] == "security_audit_unavailable"
    assert result["error"]["details"]["phase"] == "completion"
    assert calls == ["ran-once"]


def test_analysis_attempt_failure_prevents_queue_submission() -> None:
    queue = MagicMock()
    with patch.object(analysis_endpoint, "get_task_queue", return_value=queue):
        with pytest.raises(HTTPException) as exc_info:
            analysis_endpoint.trigger_analysis(
                request=AnalyzeRequest(stock_code="AAPL", async_mode=True),
                config=SimpleNamespace(),
                security_audit=_RecordingAudit(fail_attempt=True),
            )
    assert exc_info.value.status_code == 503
    queue.submit_tasks_batch.assert_not_called()


def test_analysis_accept_and_duplicate_use_correlated_completions() -> None:
    accepted_audit = _RecordingAudit()
    accepted_queue = MagicMock()
    accepted_queue.submit_tasks_batch.return_value = (
        [TaskInfo(task_id="task-1", stock_code="00700.HK")],
        [],
    )
    with patch.object(analysis_endpoint, "get_task_queue", return_value=accepted_queue):
        accepted_response = analysis_endpoint.trigger_analysis(
            request=AnalyzeRequest(stock_code="hk00700", async_mode=True),
            config=SimpleNamespace(),
            security_audit=accepted_audit,
        )

    duplicate_audit = _RecordingAudit()
    duplicate_queue = MagicMock()
    duplicate_queue.submit_tasks_batch.return_value = (
        [],
        [DuplicateTaskError("SH.600519", "task-existing")],
    )
    with patch.object(analysis_endpoint, "get_task_queue", return_value=duplicate_queue):
        duplicate_response = analysis_endpoint.trigger_analysis(
            request=AnalyzeRequest(stock_code="600519.SH", async_mode=True),
            config=SimpleNamespace(),
            security_audit=duplicate_audit,
        )

    assert accepted_response.status_code == 202
    assert accepted_audit.completions[0]["outcome"] == "accepted"
    assert accepted_audit.completions[0]["target_id"] == "HK00700"
    assert accepted_audit.attempts[0]["correlation_id"] == (
        accepted_audit.completions[0]["correlation_id"]
    )
    assert duplicate_response.status_code == 409
    assert duplicate_audit.completions[0]["outcome"] == "rejected"
    assert duplicate_audit.completions[0]["reason_code"] == "duplicate_task"


def test_analysis_queue_base_exception_is_not_wrapped_as_a_completion() -> None:
    class QueueAbort(BaseException):
        pass

    audit = _RecordingAudit()
    queue = MagicMock()
    queue.submit_tasks_batch.side_effect = QueueAbort()

    with patch.object(analysis_endpoint, "get_task_queue", return_value=queue):
        with pytest.raises(QueueAbort):
            analysis_endpoint.trigger_analysis(
                request=AnalyzeRequest(stock_code="AAPL", async_mode=True),
                config=SimpleNamespace(),
                security_audit=audit,
            )

    assert len(audit.attempts) == 1
    assert audit.completions == []


def test_analysis_partial_batch_completion_failure_is_explicit() -> None:
    audit = _RecordingAudit(fail_completion_at=2)
    queue = MagicMock()
    queue.submit_tasks_batch.return_value = (
        [
            TaskInfo(task_id="task-1", stock_code="AAPL"),
            TaskInfo(task_id="task-2", stock_code="MSFT"),
            TaskInfo(task_id="task-3", stock_code="TSLA"),
        ],
        [],
    )

    with patch.object(analysis_endpoint, "get_task_queue", return_value=queue):
        with pytest.raises(HTTPException) as exc_info:
            analysis_endpoint.trigger_analysis(
                request=AnalyzeRequest(
                    stock_codes=["AAPL", "MSFT", "TSLA"],
                    async_mode=True,
                ),
                config=SimpleNamespace(),
                security_audit=audit,
            )

    assert exc_info.value.status_code == 503
    queue.submit_tasks_batch.assert_called_once()
    assert len(audit.attempts) == 3
    assert len(audit.completions) == 1
    assert audit.completions[0]["target_id"] == "AAPL"
    assert audit.completions[0]["correlation_id"] == audit.attempts[0]["correlation_id"]
    assert {
        attempt["correlation_id"] for attempt in audit.attempts[1:]
    }.isdisjoint(
        completion["correlation_id"] for completion in audit.completions
    )


def test_query_explicitly_denies_when_auth_is_disabled() -> None:
    service = MagicMock()
    with patch.object(security_audit_endpoint, "is_auth_enabled", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            security_audit_endpoint.list_security_audit_events(
                request=SimpleNamespace(cookies={}),
                service=service,
            )
    assert exc_info.value.status_code == 403
    service.list_events.assert_not_called()
