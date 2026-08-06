# -*- coding: utf-8 -*-
"""Authentication endpoints for Web admin login."""

from __future__ import annotations

import hashlib
import logging
import os

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from api.deps import (
    get_system_config_service,
    require_security_audit_service,
)
from api.v1.errors import error_json_response
from src.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE_HOURS_DEFAULT,
    change_password,
    check_rate_limit,
    clear_rate_limit,
    create_session,
    get_client_ip,
    has_stored_password,
    is_auth_enabled,
    is_password_changeable,
    is_password_set,
    record_login_failure,
    refresh_auth_state,
    rotate_session_secret,
    set_initial_password,
    verify_password,
    verify_stored_password,
    verify_session,
)
from src.config import Config, setup_env
from src.core.config_manager import ConfigManager
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
    require_security_audit_recorder,
)
from src.services.system_config_service import ConfigConflictError
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

router = APIRouter()


def _auth_error(status_code: int, error: str, message: str) -> JSONResponse:
    """Return one stable envelope for every auth failure path."""
    safe_message = "Internal server error" if status_code >= 500 else message
    return error_json_response(status_code, error, safe_message)


def _security_audit_error() -> JSONResponse:
    return _auth_error(
        503,
        "security_audit_unavailable",
        "Security audit storage is unavailable",
    )


def _auth_client_actor_id(request: Request) -> str:
    """Return a stable, non-PII remote actor id derived from the client IP hash."""
    ip = get_client_ip(request)
    return f"client:{hashlib.sha256(ip.encode('utf-8')).hexdigest()[:16]}"


def _record_auth_attempt(
    service: SecurityAuditRecorder,
    *,
    event_type: str,
    action: str,
    correlation_id: str,
    actor_id: str,
    target_type: str = "admin_session",
    target_id: str = "primary",
    metadata: dict | None = None,
) -> JSONResponse | None:
    try:
        service.record_attempt(
            event_type=event_type,
            actor_type="remote_client",
            actor_id=actor_id,
            execution_id=correlation_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )
    except SecurityAuditUnavailable:
        return _security_audit_error()
    return None


def _record_auth_completion(
    service: SecurityAuditRecorder,
    *,
    event_type: str,
    action: str,
    correlation_id: str,
    actor_id: str,
    outcome: str,
    reason_code: str,
    target_type: str = "admin_session",
    target_id: str = "primary",
    metadata: dict | None = None,
) -> JSONResponse | None:
    try:
        service.record_completion(
            event_type=event_type,
            actor_type="remote_client",
            actor_id=actor_id,
            execution_id=correlation_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            reason_code=reason_code,
            correlation_id=correlation_id,
            metadata=metadata or {},
        )
    except SecurityAuditUnavailable:
        return _security_audit_error()
    return None


def _record_login_completion(
    service: SecurityAuditRecorder,
    *,
    correlation_id: str,
    actor_id: str,
    outcome: str,
    reason_code: str,
) -> JSONResponse | None:
    return _record_auth_completion(
        service,
        event_type="auth.login",
        action="auth.login",
        correlation_id=correlation_id,
        actor_id=actor_id,
        outcome=outcome,
        reason_code=reason_code,
    )


class LoginRequest(BaseModel):
    """Login request body. For first-time setup use password + password_confirm."""

    model_config = {"populate_by_name": True}

    password: str = Field(default="", description="Admin password")
    password_confirm: str | None = Field(default=None, alias="passwordConfirm", description="Confirm (first-time)")


class ChangePasswordRequest(BaseModel):
    """Change password request body."""

    model_config = {"populate_by_name": True}

    current_password: str = Field(default="", alias="currentPassword")
    new_password: str = Field(default="", alias="newPassword")
    new_password_confirm: str = Field(default="", alias="newPasswordConfirm")


class AuthSettingsRequest(BaseModel):
    """Update auth enablement and initial password settings."""

    model_config = {"populate_by_name": True}

    auth_enabled: bool = Field(alias="authEnabled")
    password: str = Field(default="")
    password_confirm: str | None = Field(default=None, alias="passwordConfirm")
    current_password: str = Field(default="", alias="currentPassword")


def _cookie_params(request: Request) -> dict:
    """Build cookie params including Secure based on request."""
    secure = False
    if os.getenv("TRUST_X_FORWARDED_FOR", "false").lower() == "true":
        proto = request.headers.get("X-Forwarded-Proto", "").lower()
        secure = proto == "https"
    else:
        # Check URL scheme when not behind proxy
        secure = request.url.scheme == "https"

    try:
        max_age_hours = int(os.getenv("ADMIN_SESSION_MAX_AGE_HOURS", str(SESSION_MAX_AGE_HOURS_DEFAULT)))
    except ValueError:
        max_age_hours = SESSION_MAX_AGE_HOURS_DEFAULT
    max_age = max_age_hours * 3600

    return {
        "httponly": True,
        "samesite": "lax",
        "secure": secure,
        "path": "/",
        "max_age": max_age,
    }


def _apply_auth_enabled(enabled: bool, request: Request | None = None) -> bool:
    """Persist auth toggle to .env and reload runtime config."""
    manager_applied = False
    if request is not None:
        try:
            service = get_system_config_service(request)
            service.apply_simple_updates(
                updates=[("ADMIN_AUTH_ENABLED", "true" if enabled else "false")],
                mask_token="******",
            )
            manager_applied = True
        except ConfigConflictError:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - keep legacy direct-manager fallback
            log_safe_exception(
                logger,
                "Auth toggle via shared SystemConfigService failed; falling back",
                exc,
                error_code="auth_toggle_service_failed",
                level=logging.WARNING,
                context={"enabled": enabled},
            )
            manager_applied = False

    if not manager_applied:
        try:
            manager = ConfigManager()
            manager.apply_updates(
                updates=[("ADMIN_AUTH_ENABLED", "true" if enabled else "false")],
                sensitive_keys=set(),
                mask_token="******",
            )
            manager_applied = True
        except Exception as exc:
            log_safe_exception(
                logger,
                "Auth toggle via ConfigManager failed",
                exc,
                error_code="auth_toggle_config_manager_failed",
                context={"enabled": enabled},
            )
            manager_applied = False

    if not manager_applied:
        return False

    Config.reset_instance()
    setup_env(override=True)
    refresh_auth_state()
    return True


def _password_set_for_response(auth_enabled: bool) -> bool:
    """Avoid exposing stored-password state when auth is disabled."""
    return is_password_set() if auth_enabled else False


def _set_session_cookie(response: Response, session_value: str, request: Request) -> None:
    """Attach the admin session cookie to a response."""
    params = _cookie_params(request)
    response.set_cookie(
        key=COOKIE_NAME,
        value=session_value,
        httponly=params["httponly"],
        samesite=params["samesite"],
        secure=params["secure"],
        path=params["path"],
        max_age=params["max_age"],
    )


def _get_auth_status_dict(request: Request | None = None) -> dict:
    """Helper to build consistent auth status response body."""
    auth_enabled = is_auth_enabled()
    logged_in = False
    if auth_enabled and request:
        cookie_val = request.cookies.get(COOKIE_NAME)
        logged_in = verify_session(cookie_val) if cookie_val else False

    # setupState determination:
    # - enabled: auth is active
    # - password_retained: auth disabled but password exists
    # - no_password: auth disabled and no password exists
    if auth_enabled:
        setup_state = "enabled"
    elif has_stored_password():
        setup_state = "password_retained"
    else:
        setup_state = "no_password"

    return {
        "authEnabled": auth_enabled,
        "loggedIn": logged_in,
        "passwordSet": _password_set_for_response(auth_enabled),
        "passwordChangeable": is_password_changeable() if auth_enabled else False,
        "setupState": setup_state,
    }


@router.get(
    "/status",
    summary="Get auth status",
    description="Returns whether auth is enabled and if the current request is logged in.",
)
async def auth_status(request: Request):
    """Return authEnabled, loggedIn, passwordSet, passwordChangeable, setupState without requiring auth."""
    return _get_auth_status_dict(request)


@router.post(
    "/settings",
    summary="Update auth settings",
    description=(
        "Enable or disable password login. When enabling without an existing password, "
        "password + passwordConfirm are required. When re-enabling with a stored password, "
        "currentPassword is required. Disabling authentication always requires currentPassword, "
        "even when the request has a valid session cookie."
    ),
)
async def auth_update_settings(
    request: Request,
    body: AuthSettingsRequest,
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
):
    """Manage auth enablement from the settings page."""
    try:
        audit_service = require_security_audit_recorder(security_audit)
    except SecurityAuditUnavailable:
        return _security_audit_error()

    target_enabled = body.auth_enabled
    current_enabled = is_auth_enabled()
    stored_password_exists = has_stored_password()
    correlation_id = SecurityAuditService.new_correlation_id()
    actor_id = _auth_client_actor_id(request)
    policy_metadata = {
        "target_enabled": target_enabled,
        "previous_enabled": current_enabled,
        "stored_password_exists": stored_password_exists,
    }
    audit_error = _record_auth_attempt(
        audit_service,
        event_type="auth.policy",
        action="auth.policy.update",
        correlation_id=correlation_id,
        actor_id=actor_id,
        target_type="auth_policy",
        target_id="admin_auth",
        metadata=policy_metadata,
    )
    if audit_error is not None:
        return audit_error

    def _deny(status_code: int, error: str, message: str) -> JSONResponse:
        completion_error = _record_auth_completion(
            audit_service,
            event_type="auth.policy",
            action="auth.policy.update",
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="denied",
            reason_code=error,
            target_type="auth_policy",
            target_id="admin_auth",
            metadata=policy_metadata,
        )
        if completion_error is not None:
            return completion_error
        return _auth_error(status_code, error, message)

    def _fail(status_code: int, error: str, message: str) -> JSONResponse:
        completion_error = _record_auth_completion(
            audit_service,
            event_type="auth.policy",
            action="auth.policy.update",
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="failure",
            reason_code=error,
            target_type="auth_policy",
            target_id="admin_auth",
            metadata=policy_metadata,
        )
        if completion_error is not None:
            return completion_error
        return _auth_error(status_code, error, message)

    password = (body.password or "").strip()
    confirm = (body.password_confirm or "").strip()
    current_password = (body.current_password or "").strip()

    if target_enabled:
        if password or confirm:
            if stored_password_exists:
                return _deny(
                    400,
                    "password_already_set",
                    "已存在管理员密码，请启用认证后通过修改密码功能更新",
                )
            if not password:
                return _deny(400, "password_required", "请输入要设置的管理员密码")
            if password != confirm:
                return _deny(400, "password_mismatch", "两次输入的密码不一致")
            if has_stored_password():
                return _deny(
                    400,
                    "password_already_set",
                    "已存在管理员密码，请启用认证后通过修改密码功能更新",
                )
            err = set_initial_password(password)
            if err:
                return _deny(400, "invalid_password", err)
        elif not stored_password_exists:
            return _deny(400, "password_required", "开启密码登录前请先设置密码")
        else:
            # P1 Vulnerability Fix: Enforce current-password check independent of global cached flag
            # We must verify they actually possess a valid admin session, otherwise an attacker
            # could hit a race condition when auth becomes enabled mid-flight.
            # This triggers whenever trying to enable/keep enabled an existing auth setup.
            cookie_val = request.cookies.get(COOKIE_NAME)
            # if target_enabled is True here, they are requesting to enable or keep auth enabled
            is_valid_session = cookie_val and verify_session(cookie_val)

            if not is_valid_session:
                if not current_password:
                    return _deny(400, "current_required", "重新开启认证前请输入当前密码")
                ip = get_client_ip(request)
                if not check_rate_limit(ip):
                    return _deny(429, "rate_limited", "Too many failed attempts. Please try again later.")
                if not verify_stored_password(current_password):
                    record_login_failure(ip)
                    return _deny(401, "invalid_password", "当前密码错误")
                clear_rate_limit(ip)
    else:
        if current_enabled:
            if not current_password:
                return _deny(400, "current_required", "关闭认证前请输入当前密码")
            ip = get_client_ip(request)
            if not check_rate_limit(ip):
                return _deny(429, "rate_limited", "Too many failed attempts. Please try again later.")
            if not verify_stored_password(current_password):
                record_login_failure(ip)
                return _deny(401, "invalid_password", "当前密码错误")
            clear_rate_limit(ip)

    try:
        auth_applied = _apply_auth_enabled(target_enabled, request=request)
    except ConfigConflictError as exc:
        completion_error = _record_auth_completion(
            audit_service,
            event_type="auth.policy",
            action="auth.policy.update",
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="rejected",
            reason_code="config_conflict",
            target_type="auth_policy",
            target_id="admin_auth",
            metadata=policy_metadata,
        )
        if completion_error is not None:
            return completion_error
        return error_json_response(
            409,
            "config_conflict",
            "Configuration has changed, please reload and retry",
            params={"current_config_version": exc.current_version},
        )
    if not auth_applied:
        return _fail(500, "internal_error", "Failed to update auth settings")

    if target_enabled != current_enabled:
        if not rotate_session_secret():
            try:
                rollback_ok = _apply_auth_enabled(current_enabled, request=request)
            except ConfigConflictError:
                rollback_ok = False
            if not rollback_ok:
                logger.error("Failed to roll back auth state after session secret rotation failure")
            return _fail(500, "internal_error", "Failed to rotate session secret")

    if target_enabled:
        session_val = create_session()
        if not session_val:
            try:
                rollback_ok = _apply_auth_enabled(current_enabled, request=request)
            except ConfigConflictError:
                rollback_ok = False
            if not rollback_ok:
                logger.error("Failed to roll back auth state after session creation failure")
            return _fail(500, "internal_error", "Failed to create session")
        completion_error = _record_auth_completion(
            audit_service,
            event_type="auth.policy",
            action="auth.policy.update",
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="success",
            reason_code="auth_policy_updated",
            target_type="auth_policy",
            target_id="admin_auth",
            metadata=policy_metadata,
        )
        if completion_error is not None:
            return completion_error
        # We manually set loggedIn=True because the cookie is being set in this response
        # and won't be visible in request.cookies until the NEXT request.
        content = _get_auth_status_dict(request)
        content["loggedIn"] = True
        resp = JSONResponse(content=content)
        _set_session_cookie(resp, session_val, request)
        return resp

    completion_error = _record_auth_completion(
        audit_service,
        event_type="auth.policy",
        action="auth.policy.update",
        correlation_id=correlation_id,
        actor_id=actor_id,
        outcome="success",
        reason_code="auth_policy_updated",
        target_type="auth_policy",
        target_id="admin_auth",
        metadata=policy_metadata,
    )
    if completion_error is not None:
        return completion_error
    resp = JSONResponse(content=_get_auth_status_dict(request))
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp


@router.post(
    "/login",
    summary="Login or set initial password",
    description="Verify password and set session cookie. If password not set yet, accepts password+passwordConfirm.",
)
async def auth_login(
    request: Request,
    body: LoginRequest,
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
):
    """Verify password or set initial password, set cookie on success. Returns 401 or 429 on failure."""
    try:
        audit_service = require_security_audit_recorder(security_audit)
    except SecurityAuditUnavailable:
        return _security_audit_error()
    correlation_id = SecurityAuditService.new_correlation_id()
    ip = get_client_ip(request)
    actor_id = _auth_client_actor_id(request)
    audit_error = _record_auth_attempt(
        audit_service,
        event_type="auth.login",
        action="auth.login",
        correlation_id=correlation_id,
        actor_id=actor_id,
    )
    if audit_error is not None:
        return audit_error

    if not is_auth_enabled():
        audit_error = _record_login_completion(
            audit_service,
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="denied",
            reason_code="auth_disabled",
        )
        if audit_error is not None:
            return audit_error
        return _auth_error(400, "auth_disabled", "Authentication is not configured")

    password = (body.password or "").strip()
    if not password:
        audit_error = _record_login_completion(
            audit_service,
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="denied",
            reason_code="password_required",
        )
        if audit_error is not None:
            return audit_error
        return _auth_error(400, "password_required", "请输入密码")

    if not check_rate_limit(ip):
        audit_error = _record_login_completion(
            audit_service,
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="denied",
            reason_code="rate_limited",
        )
        if audit_error is not None:
            return audit_error
        return _auth_error(429, "rate_limited", "Too many failed attempts. Please try again later.")

    password_set = is_password_set()

    if not password_set:
        # First-time setup: require passwordConfirm
        confirm = (body.password_confirm or "").strip()
        if password != confirm:
            record_login_failure(ip)
            audit_error = _record_login_completion(
                audit_service,
                correlation_id=correlation_id,
                actor_id=actor_id,
                outcome="denied",
                reason_code="password_mismatch",
            )
            if audit_error is not None:
                return audit_error
            return _auth_error(400, "password_mismatch", "Passwords do not match")
        err = set_initial_password(password)
        if err:
            record_login_failure(ip)
            audit_error = _record_login_completion(
                audit_service,
                correlation_id=correlation_id,
                actor_id=actor_id,
                outcome="denied",
                reason_code="invalid_password",
            )
            if audit_error is not None:
                return audit_error
            return _auth_error(400, "invalid_password", err)
    else:
        if not verify_password(password):
            record_login_failure(ip)
            audit_error = _record_login_completion(
                audit_service,
                correlation_id=correlation_id,
                actor_id=actor_id,
                outcome="denied",
                reason_code="invalid_password",
            )
            if audit_error is not None:
                return audit_error
            return _auth_error(401, "invalid_password", "密码错误")

    clear_rate_limit(ip)
    session_val = create_session()
    if not session_val:
        audit_error = _record_login_completion(
            audit_service,
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="failure",
            reason_code="session_creation_failed",
        )
        if audit_error is not None:
            return audit_error
        return _auth_error(500, "internal_error", "Failed to create session")

    audit_error = _record_login_completion(
        audit_service,
        correlation_id=correlation_id,
        actor_id=actor_id,
        outcome="success",
        reason_code="login_succeeded",
    )
    if audit_error is not None:
        return audit_error
    resp = JSONResponse(content={"ok": True})
    _set_session_cookie(resp, session_val, request)
    return resp


@router.post(
    "/change-password",
    summary="Change password",
    description="Change password. Requires valid session.",
)
async def auth_change_password(
    request: Request,
    body: ChangePasswordRequest,
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
):
    """Change password. Requires login."""
    try:
        audit_service = require_security_audit_recorder(security_audit)
    except SecurityAuditUnavailable:
        return _security_audit_error()
    correlation_id = SecurityAuditService.new_correlation_id()
    actor_id = _auth_client_actor_id(request)
    audit_error = _record_auth_attempt(
        audit_service,
        event_type="auth.password_change",
        action="auth.password.change",
        correlation_id=correlation_id,
        actor_id=actor_id,
        target_type="admin_credential",
        target_id="primary",
    )
    if audit_error is not None:
        return audit_error

    def _deny(status_code: int, error: str, message: str) -> JSONResponse:
        completion_error = _record_auth_completion(
            audit_service,
            event_type="auth.password_change",
            action="auth.password.change",
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="denied",
            reason_code=error,
            target_type="admin_credential",
            target_id="primary",
        )
        if completion_error is not None:
            return completion_error
        return _auth_error(status_code, error, message)

    if not is_password_changeable():
        return _deny(400, "not_changeable", "Password cannot be changed via web")

    current = (body.current_password or "").strip()
    new_pwd = (body.new_password or "").strip()
    new_confirm = (body.new_password_confirm or "").strip()

    if not current:
        return _deny(400, "current_required", "请输入当前密码")
    if new_pwd != new_confirm:
        return _deny(400, "password_mismatch", "两次输入的新密码不一致")

    err = change_password(current, new_pwd)
    if err:
        return _deny(400, "invalid_password", err)

    completion_error = _record_auth_completion(
        audit_service,
        event_type="auth.password_change",
        action="auth.password.change",
        correlation_id=correlation_id,
        actor_id=actor_id,
        outcome="success",
        reason_code="password_changed",
        target_type="admin_credential",
        target_id="primary",
    )
    if completion_error is not None:
        return completion_error
    return Response(status_code=204)


@router.post(
    "/logout",
    summary="Logout",
    description="Clear session cookie.",
)
async def auth_logout(
    request: Request,
    security_audit: SecurityAuditRecorder = Depends(require_security_audit_service),
):
    """Clear session cookie and invalidate the shared session secret when auth is enabled."""
    try:
        audit_service = require_security_audit_recorder(security_audit)
    except SecurityAuditUnavailable:
        return _security_audit_error()
    correlation_id = SecurityAuditService.new_correlation_id()
    actor_id = _auth_client_actor_id(request)
    audit_error = _record_auth_attempt(
        audit_service,
        event_type="auth.logout",
        action="auth.session.invalidate",
        correlation_id=correlation_id,
        actor_id=actor_id,
    )
    if audit_error is not None:
        return audit_error

    if is_auth_enabled() and not rotate_session_secret():
        completion_error = _record_auth_completion(
            audit_service,
            event_type="auth.logout",
            action="auth.session.invalidate",
            correlation_id=correlation_id,
            actor_id=actor_id,
            outcome="failure",
            reason_code="session_invalidation_failed",
        )
        if completion_error is not None:
            return completion_error
        return _auth_error(500, "internal_error", "Failed to invalidate session")

    completion_error = _record_auth_completion(
        audit_service,
        event_type="auth.logout",
        action="auth.session.invalidate",
        correlation_id=correlation_id,
        actor_id=actor_id,
        outcome="success",
        reason_code="session_invalidated",
    )
    if completion_error is not None:
        return completion_error
    resp = Response(status_code=204)
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp
