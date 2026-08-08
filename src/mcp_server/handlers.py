# -*- coding: utf-8 -*-
"""Thin MCP tool handlers that call existing services only.

No business logic belongs here: validation bounds, auth (caller), and
concurrency wrappers only. Analysis is submitted through AnalysisApiService
and protected by ``run_with_global_analysis_lock``.
"""

from __future__ import annotations

import concurrent.futures
import logging
from datetime import date
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from src.mcp_server.config import McpServerConfig
from src.mcp_server.errors import McpBusyError

logger = logging.getLogger(__name__)


class McpToolHandlers:
    """Service-backed tool handlers (injectable for tests)."""

    def __init__(
        self,
        *,
        config: McpServerConfig,
        stock_service: Any = None,
        history_service: Any = None,
        portfolio_service: Any = None,
        analysis_api_service: Any = None,
        task_queue: Any = None,
        get_config: Optional[Callable[[], Any]] = None,
        security_audit: Any = None,
        run_with_lock: Optional[Callable[..., bool]] = None,
    ) -> None:
        self.config = config
        self._stock_service = stock_service
        self._history_service = history_service
        self._portfolio_service = portfolio_service
        self._analysis_api_service = analysis_api_service
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

    def analysis_api_service(self) -> Any:
        if self._analysis_api_service is None:
            from api.v1.services.analysis_api_service import AnalysisApiService

            self._analysis_api_service = AnalysisApiService()
        return self._analysis_api_service

    def task_queue(self) -> Any:
        if self._task_queue is None:
            from src.services.task_queue import get_task_queue

            self._task_queue = get_task_queue()
        return self._task_queue

    def app_config(self) -> Any:
        if self._get_config is not None:
            return self._get_config()
        from src.config import get_config

        return get_config()

    def run_with_lock(self) -> Callable[..., bool]:
        if self._run_with_lock is None:
            from src.services.runtime_scheduler import run_with_global_analysis_lock

            self._run_with_lock = run_with_global_analysis_lock
        return self._run_with_lock

    def security_audit(self) -> Any:
        if self._security_audit is not None:
            return self._security_audit
        return _NoopSecurityAudit()

    def get_realtime_quote(self, *, stock_code: str) -> Dict[str, Any]:
        code = _require_non_empty(stock_code, "stock_code")
        quote = self.stock_service().get_realtime_quote(code)
        if quote is None:
            raise ValueError(f"Quote unavailable for stock_code={code}")
        return quote

    def get_stock_history(
        self,
        *,
        stock_code: str,
        period: str = "daily",
        days: int = 30,
    ) -> Dict[str, Any]:
        code = _require_non_empty(stock_code, "stock_code")
        safe_days = _bounded_int(days, default=30, minimum=1, maximum=3650)
        safe_period = (period or "daily").strip() or "daily"
        return self.stock_service().get_history_data(
            code, period=safe_period, days=safe_days
        )

    def list_analysis_history(
        self,
        *,
        stock_code: Optional[str] = None,
        report_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        safe_page = _bounded_int(page, default=1, minimum=1, maximum=10000)
        safe_limit = _bounded_int(limit, default=20, minimum=1, maximum=100)
        return self.history_service().get_history_list(
            stock_code=stock_code or None,
            report_type=report_type or None,
            start_date=start_date or None,
            end_date=end_date or None,
            page=safe_page,
            limit=safe_limit,
        )

    def get_analysis_detail(self, *, record_id: str) -> Dict[str, Any]:
        rid = _require_non_empty(record_id, "record_id")
        detail = self.history_service().resolve_and_get_detail(rid)
        if detail is None:
            raise ValueError(f"Analysis record not found: {rid}")
        return detail

    def get_analysis_report(self, *, record_id: str) -> Dict[str, Any]:
        rid = _require_non_empty(record_id, "record_id")
        report = self.history_service().get_markdown_report(rid)
        if report is None:
            raise ValueError(f"Markdown report not found: {rid}")
        return {"record_id": rid, "markdown": report}

    def list_portfolio_accounts(
        self, *, include_inactive: bool = False
    ) -> Dict[str, Any]:
        accounts = self.portfolio_service().list_accounts(
            include_inactive=bool(include_inactive)
        )
        return {"items": accounts, "total": len(accounts)}

    def get_portfolio_snapshot(
        self,
        *,
        account_id: Optional[int] = None,
        as_of: Optional[str] = None,
        cost_method: str = "fifo",
        include_realtime: bool = False,
    ) -> Dict[str, Any]:
        as_of_date: Optional[date] = None
        if as_of:
            try:
                as_of_date = date.fromisoformat(str(as_of).strip())
            except ValueError as exc:
                raise ValueError("as_of must be YYYY-MM-DD") from exc
        resolved_account_id = None
        if account_id is not None and str(account_id).strip() != "":
            resolved_account_id = int(account_id)
        return self.portfolio_service().get_portfolio_snapshot(
            account_id=resolved_account_id,
            as_of=as_of_date,
            cost_method=(cost_method or "fifo").strip() or "fifo",
            include_realtime=bool(include_realtime),
        )

    def get_analysis_status(self, *, task_id: str) -> Dict[str, Any]:
        tid = _require_non_empty(task_id, "task_id")
        queue = self.task_queue()
        task = None
        if hasattr(queue, "get_task"):
            task = queue.get_task(tid)
        elif hasattr(queue, "get"):
            task = queue.get(tid)
        if task is None:
            raise ValueError(f"Task not found: {tid}")
        if hasattr(task, "to_dict"):
            return task.to_dict()
        if isinstance(task, dict):
            return task
        return {
            "task_id": tid,
            "status": getattr(task, "status", None),
            "message": getattr(task, "message", None),
        }

    def trigger_analysis(
        self,
        *,
        stock_code: Optional[str] = None,
        stock_codes: Optional[List[str]] = None,
        report_type: str = "detailed",
        force_refresh: bool = False,
        async_mode: bool = True,
    ) -> Dict[str, Any]:
        codes: List[str] = []
        if stock_code:
            codes.append(str(stock_code).strip())
        if stock_codes:
            codes.extend(str(c).strip() for c in stock_codes if str(c).strip())
        codes = [c for c in codes if c]
        if not codes:
            raise ValueError("stock_code or stock_codes is required")
        if len(codes) > self.config.analysis_max_stocks:
            raise ValueError(
                f"At most {self.config.analysis_max_stocks} stocks per MCP analysis request"
            )

        # Use a plain namespace matching AnalyzeRequest fields so the MCP adapter
        # does not import api.v1 package graphs at tool-dispatch time. Production
        # AnalysisApiService consumes attributes, not the Pydantic class identity.
        request = SimpleNamespace(
            stock_code=codes[0] if len(codes) == 1 else None,
            stock_codes=codes if len(codes) > 1 else None,
            report_type=report_type or "detailed",
            force_refresh=bool(force_refresh),
            async_mode=True if async_mode is None else bool(async_mode),
            analysis_phase="auto",
            stock_name=None,
            original_query=None,
            selection_source=None,
        )

        result_box: Dict[str, Any] = {}
        error_box: Dict[str, BaseException] = {}
        timeout_s = max(1, int(self.config.analysis_timeout_seconds))

        def _runner(config: Any, _args: Any, _stock_codes: Optional[List[str]]) -> None:
            def _call() -> None:
                service = self.analysis_api_service()
                raw = service.trigger_analysis(
                    request,
                    config=config,
                    security_audit=self.security_audit(),
                )
                result_box["raw"] = raw

            # Bound the costly path so external MCP clients cannot hold the
            # process indefinitely. Async submission usually returns quickly;
            # the timeout still protects sync/long service work.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_call)
                try:
                    future.result(timeout=timeout_s)
                except concurrent.futures.TimeoutError as exc:
                    error_box["error"] = TimeoutError(
                        f"Analysis trigger exceeded {timeout_s}s"
                    )
                    # Do not wait for the worker; lock is released when _runner returns.
                    raise error_box["error"] from exc

        lock_fn = self.run_with_lock()
        acquired = lock_fn(
            _runner,
            self.app_config(),
            SimpleNamespace(source="mcp_server"),
            codes,
            blocking=False,
        )
        if not acquired:
            raise McpBusyError("Analysis is already running; retry later")
        if "error" in error_box:
            raise error_box["error"]

        raw = result_box.get("raw")
        return _normalize_analysis_trigger_result(raw)


def _normalize_analysis_trigger_result(raw: Any) -> Dict[str, Any]:
    """Normalize AnalysisApiService return values to a plain dict."""
    if raw is None:
        return {"status": "accepted"}
    if hasattr(raw, "body") and hasattr(raw, "status_code"):
        import json

        try:
            body = raw.body
            if isinstance(body, (bytes, bytearray)):
                body = body.decode("utf-8")
            payload = json.loads(body)
        except Exception:
            payload = {"status_code": getattr(raw, "status_code", None)}
        if isinstance(payload, dict):
            payload.setdefault("http_status", getattr(raw, "status_code", None))
            return payload
        return {"payload": payload, "http_status": getattr(raw, "status_code", None)}
    if hasattr(raw, "model_dump"):
        return raw.model_dump()
    if hasattr(raw, "dict"):
        return raw.dict()
    if isinstance(raw, dict):
        return raw
    return {"result": str(raw)}


def _require_non_empty(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _bounded_int(
    value: Any, *, default: int, minimum: int, maximum: int
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


class _NoopSecurityAudit:
    """Minimal audit recorder satisfying SecurityAuditRecorder when none is injected."""

    def record_attempt(self, **fields: Any) -> None:
        return None

    def record_completion(self, **fields: Any) -> None:
        return None
