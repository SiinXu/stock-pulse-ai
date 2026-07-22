# -*- coding: utf-8 -*-
"""
===================================
全局异常处理中间件
===================================

职责：
1. 捕获未处理的异常
2. 统一错误响应格式
3. 记录错误日志
"""

import logging
import re
import uuid
from typing import Any, Callable, Dict, Iterable, List

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.v1.errors import error_body, normalize_error_body
from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)

_TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _request_trace_id(request: Request) -> str:
    candidate = (request.headers.get("x-trace-id") or "").strip()
    if candidate and _TRACE_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def _normalized_request_path(request: Request) -> str:
    """Return the matched route template without query or path credentials."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path.startswith("/"):
        return route_path
    return "<unmatched>"


def _public_validation_issues(errors: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop request values and exception context from Pydantic validation details."""
    issues: List[Dict[str, Any]] = []
    for error in errors:
        location = []
        for segment in error.get("loc") or ():
            if isinstance(segment, int):
                location.append(segment)
            else:
                location.append(
                    sanitize_diagnostic_text(segment, max_length=120) or "field"
                )
        has_private_context = bool(error.get("ctx"))
        message = (
            "Value validation failed"
            if has_private_context
            else sanitize_diagnostic_text(error.get("msg"), max_length=200)
        )
        issues.append(
            {
                "type": sanitize_diagnostic_text(error.get("type"), max_length=120)
                or "validation_error",
                "loc": location,
                "msg": message or "Request value is invalid",
            }
        )
    return issues


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    全局异常处理中间件
    
    捕获所有未处理的异常，返回统一格式的错误响应
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        """
        处理请求，捕获异常
        
        Args:
            request: 请求对象
            call_next: 下一个处理器
            
        Returns:
            Response: 响应对象
        """
        try:
            response = await call_next(request)
            return response
            
        except Exception as exc:
            trace_id = _request_trace_id(request)
            log_safe_exception(
                logger,
                "Unhandled middleware exception",
                exc,
                error_code="internal_error",
                trace_id=trace_id,
                method=request.method,
                path=_normalized_request_path(request),
            )
            
            return JSONResponse(
                status_code=500,
                content=error_body(
                    "internal_error",
                    "Internal server error",
                    trace_id=trace_id,
                ),
                headers={"X-Trace-ID": trace_id},
            )


def add_error_handlers(app) -> None:
    """
    添加全局异常处理器
    
    为 FastAPI 应用添加各类异常的处理器
    
    Args:
        app: FastAPI 应用实例
    """
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """处理 HTTP 异常"""
        trace_id = _request_trace_id(request)
        if exc.status_code >= 500:
            safe_log_exception = HTTPException(
                status_code=exc.status_code,
                detail="Server error detail redacted",
            )
            log_safe_exception(
                logger,
                "HTTP exception returned a server error",
                safe_log_exception,
                error_code="internal_error",
                trace_id=trace_id,
                method=request.method,
                path=_normalized_request_path(request),
                context={"status_code": exc.status_code},
            )
            content = error_body(
                "internal_error",
                "Internal server error",
                trace_id=trace_id,
            )
            response_headers = {"X-Trace-ID": trace_id}
        else:
            content = normalize_error_body(
                exc.detail,
                default_error="http_error",
                default_message="Request failed",
                trace_id=trace_id,
            )
            response_headers = {
                **(exc.headers or {}),
                "X-Trace-ID": str(content["trace_id"]),
            }
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=response_headers,
        )
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """处理请求验证异常"""
        trace_id = _request_trace_id(request)
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_error",
                "Request validation failed",
                details={"issues": _public_validation_issues(exc.errors())},
                trace_id=trace_id,
            ),
            headers={"X-Trace-ID": trace_id},
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """处理通用异常"""
        trace_id = _request_trace_id(request)
        log_safe_exception(
            logger,
            "Unhandled API exception",
            exc,
            error_code="internal_error",
            trace_id=trace_id,
            method=request.method,
            path=_normalized_request_path(request),
        )
        return JSONResponse(
            status_code=500,
            content=error_body(
                "internal_error",
                "Internal server error",
                trace_id=trace_id,
            ),
            headers={"X-Trace-ID": trace_id},
        )
