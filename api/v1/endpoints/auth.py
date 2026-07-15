# -*- coding: utf-8 -*-
"""Authentication endpoints for Web admin login."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from api.deps import get_system_config_service
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

logger = logging.getLogger(__name__)

router = APIRouter()


def _auth_error(status_code: int, code: str, message: str) -> JSONResponse:
    return error_json_response(status_code, code, message)


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
        except Exception as exc:
            logger.warning(
                "Failed to apply auth toggle via shared SystemConfigService, falling back: %s",
                exc,
                exc_info=True,
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
            logger.error("Failed to apply auth toggle via ConfigManager: %s", exc, exc_info=True)
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
        "currentPassword is required."
    ),
)
async def auth_update_settings(request: Request, body: AuthSettingsRequest):
    """Manage auth enablement from the settings page."""
    target_enabled = body.auth_enabled
    current_enabled = is_auth_enabled()
    stored_password_exists = has_stored_password()

    password = (body.password or "").strip()
    confirm = (body.password_confirm or "").strip()
    current_password = (body.current_password or "").strip()

    if target_enabled:
        if password or confirm:
            if stored_password_exists:
                return _auth_error(
                    400,
                    "password_already_set",
                    "An administrator password is already configured",
                )
            if not password:
                return _auth_error(
                    400,
                    "password_required",
                    "An administrator password is required",
                )
            if password != confirm:
                return _auth_error(
                    400,
                    "password_mismatch",
                    "Password confirmation does not match",
                )
            if has_stored_password():
                return _auth_error(
                    400,
                    "password_already_set",
                    "An administrator password is already configured",
                )
            err = set_initial_password(password)
            if err:
                return _auth_error(400, "invalid_password", err)
        elif not stored_password_exists:
            return _auth_error(
                400,
                "password_required",
                "Set an administrator password before enabling authentication",
            )
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
                    return _auth_error(
                        400,
                        "current_required",
                        "The current password is required to enable authentication",
                    )
                ip = get_client_ip(request)
                if not check_rate_limit(ip):
                    return _auth_error(
                        429,
                        "rate_limited",
                        "Too many failed attempts. Please try again later.",
                    )
                if not verify_stored_password(current_password):
                    record_login_failure(ip)
                    return _auth_error(401, "invalid_password", "The current password is incorrect")
                clear_rate_limit(ip)
    else:
        if current_enabled:
            cookie_val = request.cookies.get(COOKIE_NAME)
            is_valid_session = cookie_val and verify_session(cookie_val)

            if not is_valid_session:
                if not current_password:
                    return _auth_error(
                        400,
                        "current_required",
                        "The current password is required to disable authentication",
                    )
                ip = get_client_ip(request)
                if not check_rate_limit(ip):
                    return _auth_error(
                        429,
                        "rate_limited",
                        "Too many failed attempts. Please try again later.",
                    )
                if not verify_stored_password(current_password):
                    record_login_failure(ip)
                    return _auth_error(401, "invalid_password", "The current password is incorrect")
                clear_rate_limit(ip)

    if target_enabled != current_enabled:
        if not _apply_auth_enabled(target_enabled, request=request):
            return _auth_error(500, "internal_error", "Failed to update auth settings")
        if not rotate_session_secret():
            rollback_ok = _apply_auth_enabled(current_enabled, request=request)
            if not rollback_ok:
                logger.error("Failed to roll back auth state after session secret rotation failure")
            return _auth_error(500, "internal_error", "Failed to rotate session secret")
    else:
        if not _apply_auth_enabled(target_enabled, request=request):
            return _auth_error(500, "internal_error", "Failed to update auth settings")

    if target_enabled:
        session_val = create_session()
        if not session_val:
            rollback_ok = _apply_auth_enabled(current_enabled, request=request)
            if not rollback_ok:
                logger.error("Failed to roll back auth state after session creation failure")
            return _auth_error(500, "internal_error", "Failed to create session")
        # We manually set loggedIn=True because the cookie is being set in this response
        # and won't be visible in request.cookies until the NEXT request.
        content = _get_auth_status_dict(request)
        content["loggedIn"] = True
        resp = JSONResponse(content=content)
        _set_session_cookie(resp, session_val, request)
        return resp

    resp = JSONResponse(content=_get_auth_status_dict(request))
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp



@router.post(
    "/login",
    summary="Login or set initial password",
    description="Verify password and set session cookie. If password not set yet, accepts password+passwordConfirm.",
)
async def auth_login(request: Request, body: LoginRequest):
    """Verify password or set initial password, set cookie on success. Returns 401 or 429 on failure."""
    if not is_auth_enabled():
        return _auth_error(400, "auth_disabled", "Authentication is not configured")

    password = (body.password or "").strip()
    if not password:
        return _auth_error(400, "password_required", "A password is required")

    ip = get_client_ip(request)
    if not check_rate_limit(ip):
        return _auth_error(
            429,
            "rate_limited",
            "Too many failed attempts. Please try again later.",
        )

    password_set = is_password_set()

    if not password_set:
        # First-time setup: require passwordConfirm
        confirm = (body.password_confirm or "").strip()
        if password != confirm:
            record_login_failure(ip)
            return _auth_error(400, "password_mismatch", "Passwords do not match")
        err = set_initial_password(password)
        if err:
            record_login_failure(ip)
            return _auth_error(400, "invalid_password", err)
    else:
        if not verify_password(password):
            record_login_failure(ip)
            return _auth_error(401, "invalid_password", "The password is incorrect")

    clear_rate_limit(ip)
    session_val = create_session()
    if not session_val:
        return _auth_error(500, "internal_error", "Failed to create session")

    resp = JSONResponse(content={"ok": True})
    _set_session_cookie(resp, session_val, request)
    return resp


@router.post(
    "/change-password",
    summary="Change password",
    description="Change password. Requires valid session.",
)
async def auth_change_password(body: ChangePasswordRequest):
    """Change password. Requires login."""
    if not is_password_changeable():
        return _auth_error(400, "not_changeable", "Password cannot be changed via web")

    current = (body.current_password or "").strip()
    new_pwd = (body.new_password or "").strip()
    new_confirm = (body.new_password_confirm or "").strip()

    if not current:
        return _auth_error(400, "current_required", "The current password is required")
    if new_pwd != new_confirm:
        return _auth_error(400, "password_mismatch", "Password confirmation does not match")

    err = change_password(current, new_pwd)
    if err:
        return _auth_error(400, "invalid_password", err)
    return Response(status_code=204)


@router.post(
    "/logout",
    summary="Logout",
    description="Clear session cookie.",
)
async def auth_logout(request: Request):
    """Clear session cookie."""
    if is_auth_enabled() and not rotate_session_secret():
        return _auth_error(500, "internal_error", "Failed to invalidate session")
    resp = Response(status_code=204)
    resp.delete_cookie(key=COOKIE_NAME, path="/")
    return resp
