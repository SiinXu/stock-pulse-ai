# -*- coding: utf-8 -*-
"""Shared HTTP 503 mapper for SystemConfigService.update write audit."""

from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException

from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditUnavailable,
    require_security_audit_recorder,
)
from src.services.system_config_service import (
    SystemConfigWriteAuditCompletionUnavailable,
)


def system_config_write_audit_unavailable(
    exc: BaseException | None = None,
    *,
    operation_completed: bool = False,
) -> HTTPException:
    """Return the isolated TestClient 503 shape for config-write audit outages."""
    completed = operation_completed
    extra: dict[str, object] = {}
    if isinstance(exc, SystemConfigWriteAuditCompletionUnavailable):
        completed = True
        extra = {
            "config_version": exc.config_version,
            "applied_count": exc.applied_count,
            "reload_triggered": exc.reload_triggered,
        }
    elif isinstance(exc, SecurityAuditUnavailable):
        completed = False
    detail = {
        "error": "security_audit_unavailable",
        "message": (
            "Configuration was persisted, but audit completion could not be persisted"
            if completed
            else "Security audit storage is unavailable"
        ),
        "operation_completed": completed,
    }
    detail.update(extra)
    return HTTPException(status_code=503, detail=detail)


def raise_system_config_write_audit_unavailable(
    exc: BaseException | None = None,
    *,
    operation_completed: bool = False,
) -> NoReturn:
    """Raise the shared config-write 503 mapper."""
    raise system_config_write_audit_unavailable(
        exc,
        operation_completed=operation_completed,
    ) from None


def require_system_config_write_audit(value: object) -> SecurityAuditRecorder:
    """Validate a recorder at a write-capable adapter without a global 503 reshape."""
    try:
        return require_security_audit_recorder(value)
    except SecurityAuditUnavailable as exc:
        raise_system_config_write_audit_unavailable(exc)


def map_system_config_write_audit_exception(exc: BaseException) -> None:
    """Re-raise audit unavailability as HTTP 503; ignore other exceptions."""
    if isinstance(
        exc,
        (SecurityAuditUnavailable, SystemConfigWriteAuditCompletionUnavailable),
    ):
        raise_system_config_write_audit_unavailable(exc)
