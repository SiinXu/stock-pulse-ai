# -*- coding: utf-8 -*-
"""
===================================
API 依赖注入模块
===================================

职责：
1. 提供数据库 Session 依赖
2. 提供配置依赖
3. 提供服务层依赖
"""

import threading
from typing import Any, Callable, Dict, Generator, Mapping, Optional, Protocol, cast

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.storage import DatabaseManager
from src.config import get_config, Config
from src.services.system_config_service import SystemConfigService
from src.services.runtime_scheduler import RuntimeSchedulerService
from src.services.local_model_service import LocalModelService, get_pullable_local_model_ids
from src.services.model_pack_import_service import ModelPackImportService
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    SecurityAuditService,
    SecurityAuditUnavailable,
    get_security_audit_service as _build_security_audit_service,
    require_security_audit_recorder,
)
from src.services.scheduled_task_service import ScheduledTaskService
from src.services.task_queue import get_task_queue


_SYSTEM_CONFIG_SERVICE_INIT_LOCK = threading.Lock()
_LOCAL_MODEL_SERVICE_INIT_LOCK = threading.RLock()


class SecurityAuditQueryService(SecurityAuditRecorder, Protocol):
    """Audit service contract required by the administrator query endpoint."""

    def list_events(self, **filters: Any) -> Any:
        """Return one bounded page of persisted audit events."""


def get_db() -> Generator[Session, None, None]:
    """
    获取数据库 Session 依赖

    使用 FastAPI 依赖注入机制，确保请求结束后自动关闭 Session

    Yields:
        Session: SQLAlchemy Session 对象

    Example:
        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            ...
    """
    db_manager = DatabaseManager.get_instance()
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


def get_config_dep() -> Config:
    """
    获取配置依赖

    Returns:
        Config: 配置单例对象
    """
    return get_config()


def get_database_manager() -> DatabaseManager:
    """
    获取数据库管理器依赖

    Returns:
        DatabaseManager: 数据库管理器单例对象
    """
    return DatabaseManager.get_instance()


def get_system_config_service(request: Request) -> SystemConfigService:
    """Get app-lifecycle shared SystemConfigService instance."""
    service = getattr(request.app.state, "system_config_service", None)
    if service is None:
        with _SYSTEM_CONFIG_SERVICE_INIT_LOCK:
            service = getattr(request.app.state, "system_config_service", None)
            if service is None:
                service = SystemConfigService()
                request.app.state.system_config_service = service
    return service


def get_runtime_scheduler_service(request: Request) -> RuntimeSchedulerService:
    """Get app-lifecycle shared RuntimeSchedulerService instance."""
    service = getattr(request.app.state, "runtime_scheduler_service", None)
    if service is None:
        service = RuntimeSchedulerService()
        request.app.state.runtime_scheduler_service = service
    return service


def get_local_model_service(request: Request) -> LocalModelService:
    """Get the app-lifecycle shared local model management service."""
    service = getattr(request.app.state, "local_model_service", None)
    if service is None:
        with _LOCAL_MODEL_SERVICE_INIT_LOCK:
            service = getattr(request.app.state, "local_model_service", None)
            if service is None:
                service = LocalModelService(
                    system_config_service=get_system_config_service(request),
                    task_queue=get_task_queue(),
                    pullable_model_ids=get_pullable_local_model_ids,
                    activation_handler=lambda normalized, **kwargs: (
                        _activate_active_local_model_pull(
                            request,
                            normalized,
                            **kwargs,
                        )
                    ),
                )
                request.app.state.local_model_service = service
    return service


def get_security_audit_service() -> SecurityAuditService:
    """Return a request-scoped lazy security-audit service."""
    return _build_security_audit_service()


def require_security_audit_service(
    service: object = Depends(get_security_audit_service),
) -> SecurityAuditRecorder:
    """Validate an overrideable audit dependency before endpoint code can run."""
    try:
        return require_security_audit_recorder(service)
    except SecurityAuditUnavailable:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_audit_unavailable",
                "message": "Security audit storage is unavailable",
            },
        ) from None


def require_security_audit_query_service(
    service: object = Depends(get_security_audit_service),
) -> SecurityAuditQueryService:
    """Validate the recorder and query surface before endpoint code can run."""
    recorder = require_security_audit_service(service)
    if not callable(getattr(recorder, "list_events", None)):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "security_audit_unavailable",
                "message": "Security audit storage is unavailable",
            },
        )
    return cast(SecurityAuditQueryService, recorder)


def _get_active_local_model_service(request: Request) -> Optional[LocalModelService]:
    """Resolve the current lifespan authority without reviving a stopped app."""
    with _LOCAL_MODEL_SERVICE_INIT_LOCK:
        if getattr(request.app.state, "local_model_services_active", True) is False:
            return None
        return get_local_model_service(request)


def _activate_active_local_model_pull(
    request: Request,
    normalized: str,
    *,
    config_version: str,
    values: Mapping[str, str],
    base_url: str,
    is_cancel_requested: Callable[[], bool],
    commit_final_result: Callable[
        [Callable[[], Any]], tuple[bool, Any]
    ],
) -> Optional[Dict[str, Any]]:
    """Linearize late pull activation with lifespan shutdown and cancellation."""
    with _LOCAL_MODEL_SERVICE_INIT_LOCK:
        if (
            getattr(request.app.state, "local_model_services_active", True) is False
            or is_cancel_requested()
        ):
            return None
        service = get_local_model_service(request)
        return service._activate_completed_pull(
            normalized,
            config_version=config_version,
            values=values,
            base_url=base_url,
            is_cancel_requested=is_cancel_requested,
            commit_final_result=commit_final_result,
        )


def begin_local_model_service_lifespan(
    app: object,
    system_config_service: SystemConfigService,
) -> None:
    """Atomically publish a new configuration authority for local-model requests."""
    with _LOCAL_MODEL_SERVICE_INIT_LOCK:
        previous = getattr(app.state, "local_model_service", None)
        if previous is not None:
            previous.retire_pull_activation()
            delattr(app.state, "local_model_service")
        app.state.system_config_service = system_config_service
        app.state.local_model_services_active = True


def end_local_model_service_lifespan(app: object) -> None:
    """Retire local-model activation before removing lifespan-owned services."""
    with _LOCAL_MODEL_SERVICE_INIT_LOCK:
        app.state.local_model_services_active = False
        service = getattr(app.state, "local_model_service", None)
        if service is not None:
            service.retire_pull_activation()
            delattr(app.state, "local_model_service")
        if hasattr(app.state, "system_config_service"):
            delattr(app.state, "system_config_service")


def get_scheduled_task_service(request: Request) -> ScheduledTaskService:
    """Get the app-lifecycle shared ScheduledTaskService instance."""
    service = getattr(request.app.state, "scheduled_task_service", None)
    if service is None:
        service = ScheduledTaskService()
        request.app.state.scheduled_task_service = service
    return service


def get_model_pack_import_service(request: Request) -> ModelPackImportService:
    """Get the app-lifecycle shared Model Pack import service."""
    service = getattr(request.app.state, "model_pack_import_service", None)
    if service is None:
        service = ModelPackImportService(
            system_config_service=get_system_config_service(request),
            task_queue=get_task_queue(),
        )
        request.app.state.model_pack_import_service = service
    return service
