# -*- coding: utf-8 -*-
"""Thin MCP handlers over existing StockPulse services."""

from __future__ import annotations

from datetime import date
import json
from types import SimpleNamespace
from typing import Any, Callable

from src.mcp_server.config import McpServerConfig
from src.mcp_server.errors import McpBusyError
from src.services.analysis_submission_service import (
    AnalysisSubmissionResult,
    AnalysisSubmissionService,
    build_submission_command,
)
from src.services.security_audit_service import (
    SecurityAuditRecorder,
    get_security_audit_service,
    require_security_audit_recorder,
)


class McpToolHandlers:
    """Service-backed handlers with injectable dependencies for focused tests."""

    def __init__(
        self,
        *,
        config: McpServerConfig,
        stock_service: Any = None,
        history_service: Any = None,
        portfolio_service: Any = None,
        analysis_submission_service: Any = None,
        task_queue: Any = None,
        get_config: Callable[[], Any] | None = None,
        security_audit: SecurityAuditRecorder | None = None,
        run_with_lock: Callable[..., bool] | None = None,
    ) -> None:
        self.config = config
        self._stock_service = stock_service
        self._history_service = history_service
        self._portfolio_service = portfolio_service
        self._analysis_submission_service = analysis_submission_service
        self._task_queue = task_queue
        self._get_config = get_config
        self._security_audit = security_audit
        self._run_with_lock = run_with_lock

    def stock_service(self) -> Any:
        if self._stock_service is None:
            from src.services.stock_service import StockService

            self._stock_service = StockService()
        return self._stock_service

    def history_service(self) -> Any:
        if self._history_service is None:
            from src.services.history_service import HistoryService

            self._history_service = HistoryService()
        return self._history_service

    def portfolio_service(self) -> Any:
        if self._portfolio_service is None:
            from src.services.portfolio_service import PortfolioService

            self._portfolio_service = PortfolioService()
        return self._portfolio_service

    def analysis_submission_service(self) -> Any:
        if self._analysis_submission_service is None:
            self._analysis_submission_service = AnalysisSubmissionService(
                get_task_queue=self.task_queue,
            )
        return self._analysis_submission_service

    def task_queue(self) -> Any:
        if self._task_queue is None:
            from src.services.task_queue import get_task_queue

            self._task_queue = get_task_queue()
        return self._task_queue

    def app_config(self) -> Any:
        if self._get_config is not None:
            return self._get_config()
        from src.application_services import get_application_services

        return get_application_services().config

    def run_with_lock(self) -> Callable[..., bool]:
        if self._run_with_lock is None:
            from src.services.runtime_scheduler import run_with_global_analysis_lock

            self._run_with_lock = run_with_global_analysis_lock
        return self._run_with_lock

    def security_audit(self) -> SecurityAuditRecorder:
        recorder = self._security_audit or get_security_audit_service()
        return require_security_audit_recorder(recorder)

    def get_realtime_quote(self, *, stock_code: str) -> dict[str, Any]:
        quote = self.stock_service().get_realtime_quote(stock_code)
        if quote is None:
            raise ValueError(f"Quote unavailable for stock_code={stock_code}")
        return quote

    def get_stock_history(self, *, stock_code: str, period: str = "daily", days: int = 30) -> dict[str, Any]:
        return self.stock_service().get_history_data(stock_code, period=period, days=days)

    def list_analysis_history(
        self,
        *,
        stock_code: str | None = None,
        report_type: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> dict[str, Any]:
        return self.history_service().get_history_list(
            stock_code=stock_code,
            report_type=report_type,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            page=page,
            limit=limit,
        )

    def get_analysis_detail(self, *, record_id: str) -> dict[str, Any]:
        detail = self.history_service().resolve_and_get_detail(record_id)
        if detail is None:
            raise ValueError(f"Analysis record not found: {record_id}")
        return detail

    def get_analysis_report(self, *, record_id: str) -> dict[str, Any]:
        report = self.history_service().get_markdown_report(record_id)
        if report is None:
            raise ValueError(f"Markdown report not found: {record_id}")
        return {"record_id": record_id, "markdown": report}

    def list_portfolio_accounts(self, *, include_inactive: bool = False) -> dict[str, Any]:
        accounts = self.portfolio_service().list_accounts(include_inactive=include_inactive)
        return {"items": accounts, "total": len(accounts)}

    def get_portfolio_snapshot(
        self,
        *,
        account_id: int | None = None,
        as_of: date | None = None,
        cost_method: str = "fifo",
        include_realtime: bool = False,
    ) -> dict[str, Any]:
        return self.portfolio_service().get_portfolio_snapshot(
            account_id=account_id,
            as_of=as_of,
            cost_method=cost_method,
            include_realtime=include_realtime,
        )

    def get_analysis_status(self, *, task_id: str) -> dict[str, Any]:
        queue = self.task_queue()
        task = queue.get_task(task_id) if hasattr(queue, "get_task") else queue.get(task_id)
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        if hasattr(task, "to_dict"):
            return task.to_dict()
        if isinstance(task, dict):
            return task
        return {
            "task_id": task_id,
            "status": getattr(task, "status", None),
            "message": getattr(task, "message", None),
        }

    def trigger_analysis(
        self,
        *,
        stock_code: str | None = None,
        stock_codes: list[str] | None = None,
        report_type: str = "detailed",
        force_refresh: bool = False,
        async_mode: bool = True,
    ) -> dict[str, Any]:
        """Submit only durable asynchronous work; synchronous analysis is not exposed."""
        if async_mode is not True:
            raise ValueError("MCP trigger_analysis requires async_mode=true")
        codes = [stock_code] if stock_code else list(stock_codes or [])
        if len(codes) > self.config.analysis_max_stocks:
            raise ValueError(f"At most {self.config.analysis_max_stocks} stocks are allowed")
        command = build_submission_command(
            stock_codes=codes,
            report_type=report_type,
            force_refresh=force_refresh,
            analysis_phase="auto",
        )
        result_box: dict[str, Any] = {}

        def submit(config: Any, _args: Any, _stock_codes: list[str] | None) -> None:
            del config
            result_box["raw"] = self.analysis_submission_service().submit(
                command,
                security_audit=self.security_audit(),
            )

        acquired = self.run_with_lock()(
            submit,
            self.app_config(),
            SimpleNamespace(source="mcp_server"),
            codes,
            blocking=False,
        )
        if not acquired:
            raise McpBusyError("Analysis submission is busy; retry later")
        return _normalize_analysis_trigger_result(result_box.get("raw"))


def _normalize_analysis_trigger_result(raw: Any) -> dict[str, Any]:
    if isinstance(raw, AnalysisSubmissionResult):
        accepted = [
            {
                "task_id": task.task_id,
                "stock_code": task.stock_code,
                "status": "pending",
                "analysis_phase": task.analysis_phase,
            }
            for task in raw.accepted_tasks
        ]
        duplicates = [
            {
                "stock_code": duplicate.stock_code,
                "existing_task_id": duplicate.existing_task_id,
                "message": str(duplicate),
            }
            for duplicate in raw.duplicate_errors
        ]
        if len(accepted) == 1 and not duplicates:
            return accepted[0]
        return {"accepted": accepted, "duplicates": duplicates}
    if raw is None:
        return {"status": "accepted"}
    if hasattr(raw, "body") and hasattr(raw, "status_code"):
        body = raw.body
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8")
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            payload = {"status_code": getattr(raw, "status_code", None)}
        if isinstance(payload, dict):
            payload.setdefault("http_status", getattr(raw, "status_code", None))
            return payload
        return {"payload": payload, "http_status": getattr(raw, "status_code", None)}
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    if isinstance(raw, dict):
        return raw
    return {"result": str(raw)}
