# -*- coding: utf-8 -*-
"""Rendering and notification delivery stages for the stock analysis pipeline."""

import logging
import sys
import threading
from collections import defaultdict
from contextlib import ExitStack
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from data_provider.base import normalize_stock_code
from src.analyzer import AnalysisResult
from src.config import get_config as _get_config_impl
from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageResult,
    PipelineStageStatus,
)
from src.enums import ReportType
from src.notification import NotificationChannel
from src.services.run_diagnostics import (
    PipelineStageObservation,
    observe_pipeline_stage,
    record_notification_run as _record_notification_run_impl,
)
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger("src.core.pipeline")
_SINGLE_STOCK_NOTIFY_LOCK_INIT_GUARD = threading.Lock()


def get_config():
    """Resolve the legacy pipeline patch seam before falling back to config."""

    pipeline_module = sys.modules.get("src.core.pipeline")
    resolver = getattr(pipeline_module, "get_config", _get_config_impl)
    return resolver()


def record_notification_run(*args, **kwargs):
    """Resolve the legacy pipeline patch seam before recording delivery."""

    pipeline_module = sys.modules.get("src.core.pipeline")
    recorder = getattr(
        pipeline_module,
        "record_notification_run",
        _record_notification_run_impl,
    )
    return recorder(*args, **kwargs)


class _DeliveryStageMixin:
    @staticmethod
    def _delivery_stage_key(
        *,
        route: str,
        results: List[AnalysisResult],
        report_type: ReportType,
        channel: Optional[str] = None,
    ) -> Tuple[Any, ...]:
        """Build a request-stable key for render and dispatch side effects."""
        result_keys = tuple(
            sorted(
                (
                    str(getattr(item, "query_id", None) or ""),
                    str(getattr(item, "code", None) or ""),
                )
                for item in results
            )
        )
        return (
            route,
            report_type.value,
            channel or "",
            result_keys,
        )

    def _run_delivery_attempt(
        self,
        *,
        side_effect_key: Tuple[Any, ...],
        send: Callable[[], bool],
    ) -> PipelineStageResult[bool]:
        """Send once for a delivery key and reuse any confirmed success."""

        def _dispatch() -> PipelineStageResult[bool]:
            delivered = bool(send())
            if delivered:
                return PipelineStageResult.success(
                    PipelineStageName.DISPATCH,
                    True,
                    side_effect_committed=True,
                )
            return PipelineStageResult.failed(
                PipelineStageName.DISPATCH,
                value=False,
                retryable=True,
                reason="Notification delivery was not confirmed.",
            )

        return self._get_pipeline_stage_runner().run(
            PipelineStageName.DISPATCH,
            _dispatch,
            retryable=True,
            side_effect_key=side_effect_key,
        )

    def _send_single_stock_notification(
        self,
        result: AnalysisResult,
        report_type: ReportType = ReportType.SIMPLE,
        fallback_code: Optional[str] = None,
    ) -> None:
        """发送单股通知，供直接单股入口和批量串行推送共用。"""
        if not self.notifier.is_available():
            self._record_pipeline_stage_result(
                PipelineStageResult.skipped(
                    PipelineStageName.RENDER,
                    reason="notification_not_configured",
                ),
                input_summary={
                    "stock_code": getattr(result, "code", None) or fallback_code,
                    "report_type": report_type.value,
                    "result_count": 1,
                },
                output_summary={"reason": "notification_not_configured"},
            )
            self._record_pipeline_stage_result(
                PipelineStageResult.skipped(
                    PipelineStageName.DISPATCH,
                    reason="notification_not_configured",
                ),
                input_summary={
                    "stock_code": getattr(result, "code", None) or fallback_code,
                    "route": "report",
                    "result_count": 1,
                },
                output_summary={"reason": "notification_not_configured"},
            )
            notification_run = self._build_notification_run_snapshot(
                channel="report",
                status="not_configured",
                success=False,
                attempts=0,
            )
            record_notification_run(
                channel="report",
                status="not_configured",
                success=False,
                attempts=0,
            )
            self._refresh_saved_diagnostic_snapshot(
                result=result,
                fallback_code=fallback_code,
                notification_run=notification_run,
            )
            return

        stock_code = getattr(result, "code", None) or fallback_code or "unknown"
        notify_lock = getattr(self, "_single_stock_notify_lock", None)
        if notify_lock is None:
            with _SINGLE_STOCK_NOTIFY_LOCK_INIT_GUARD:
                notify_lock = getattr(self, "_single_stock_notify_lock", None)
                if notify_lock is None:
                    notify_lock = threading.Lock()
                    setattr(self, "_single_stock_notify_lock", notify_lock)

        with notify_lock:
            render_stage = observe_pipeline_stage(
                "render",
                input_summary={
                    "stock_code": stock_code,
                    "report_type": report_type.value,
                    "result_count": 1,
                },
                retryable=False,
            )
            dispatch_stage: Optional[PipelineStageObservation] = None
            try:
                if report_type == ReportType.FULL:
                    report_content = self.notifier.generate_dashboard_report([result])
                    logger.info("[%s] Using full report format", stock_code)
                elif report_type == ReportType.BRIEF:
                    report_content = self.notifier.generate_brief_report([result])
                    logger.info("[%s] Using brief report format", stock_code)
                else:
                    report_content = self.notifier.generate_single_stock_report(result)
                    logger.info("[%s] Using simple report format", stock_code)

                render_result = PipelineStageResult.success(
                    PipelineStageName.RENDER,
                    report_content,
                )
                self._finish_pipeline_stage(
                    render_stage,
                    render_result,
                    output_summary={
                        "content_length": (
                            len(report_content)
                            if isinstance(report_content, (str, bytes))
                            else None
                        ),
                        "route": "single_stock",
                    },
                )

                dispatch_stage = observe_pipeline_stage(
                    "dispatch",
                    input_summary={
                        "stock_code": stock_code,
                        "route": "report",
                        "result_count": 1,
                    },
                    retryable=True,
                )
                send_kwargs = {
                    "email_stock_codes": [stock_code],
                    "route_type": "report",
                    "severity": "info",
                    "dedup_key": (
                        f"report:single:{stock_code}:{report_type.value}"
                    ),
                    "cooldown_key": (
                        f"report:single:{stock_code}:{report_type.value}"
                    ),
                }
                notifier_type_method = getattr(
                    type(self.notifier),
                    "send_with_results",
                    None,
                )
                notifier_instance_values = getattr(
                    self.notifier,
                    "__dict__",
                    {},
                )
                send_with_results = (
                    getattr(self.notifier, "send_with_results", None)
                    if callable(notifier_type_method)
                    else notifier_instance_values.get("send_with_results")
                )

                def _dispatch_single() -> PipelineStageResult[Dict[str, Any]]:
                    dispatch_result = None
                    channel_results: List[Any] = []
                    dispatch_result_status = ""
                    dispatched = False
                    if callable(send_with_results):
                        dispatch_result = send_with_results(
                            report_content,
                            **send_kwargs,
                        )
                        raw_channel_results = getattr(
                            dispatch_result,
                            "channel_results",
                            None,
                        )
                        if isinstance(raw_channel_results, (list, tuple)):
                            channel_results = list(raw_channel_results)
                        dispatch_result_status = str(
                            getattr(dispatch_result, "status", "") or ""
                        ).strip().lower()
                        sent = bool(getattr(dispatch_result, "success", False))
                        dispatched = bool(
                            getattr(dispatch_result, "dispatched", False)
                        )
                    else:
                        sent = bool(
                            self.notifier.send(report_content, **send_kwargs)
                        )
                        dispatched = True

                    delivery_failure_count = (
                        sum(
                            not bool(getattr(item, "success", False))
                            for item in channel_results
                        )
                        if channel_results
                        else int(dispatched and not sent)
                    )
                    if (
                        dispatch_result_status == "partial_failed"
                        or (sent and delivery_failure_count)
                    ):
                        dispatch_status = PipelineStageStatus.DEGRADED
                    elif sent or dispatch_result_status == "sent":
                        dispatch_status = PipelineStageStatus.SUCCESS
                    elif dispatch_result_status in {
                        "noise_suppressed",
                        "no_channel",
                    }:
                        dispatch_status = PipelineStageStatus.SKIPPED
                    else:
                        dispatch_status = PipelineStageStatus.FAILED

                    dispatch_retryable = False
                    if dispatch_status == PipelineStageStatus.FAILED:
                        dispatch_retryable = (
                            any(
                                bool(getattr(item, "retryable", True))
                                for item in channel_results
                            )
                            if channel_results
                            else True
                        )
                    stage_value = {
                        "dispatch_result": dispatch_result,
                        "channel_results": channel_results,
                        "dispatch_result_status": dispatch_result_status,
                        "dispatched": dispatched,
                        "sent": sent,
                        "delivery_failure_count": delivery_failure_count,
                    }
                    if dispatch_status == PipelineStageStatus.SUCCESS:
                        return PipelineStageResult.success(
                            PipelineStageName.DISPATCH,
                            stage_value,
                            side_effect_committed=sent,
                        )
                    if dispatch_status == PipelineStageStatus.DEGRADED:
                        return PipelineStageResult.degraded(
                            PipelineStageName.DISPATCH,
                            stage_value,
                            reason=(
                                "Some notification deliveries failed after at "
                                "least one delivery succeeded."
                            ),
                            retryable=False,
                            side_effect_committed=True,
                        )
                    if dispatch_status == PipelineStageStatus.SKIPPED:
                        return PipelineStageResult.skipped(
                            PipelineStageName.DISPATCH,
                            value=stage_value,
                        )
                    return PipelineStageResult.failed(
                        PipelineStageName.DISPATCH,
                        value=stage_value,
                        retryable=dispatch_retryable,
                        reason="All attempted notification deliveries failed.",
                    )

                dispatch_execution = self._get_pipeline_stage_runner().run(
                    PipelineStageName.DISPATCH,
                    _dispatch_single,
                    retryable=True,
                    side_effect_key=self._delivery_stage_key(
                        route="single_stock",
                        results=[result],
                        report_type=report_type,
                        channel="report",
                    ),
                )
                dispatch_value = dispatch_execution.value or {}
                cached_dispatch = dispatch_execution.reused
                cached_failure_count = int(
                    dispatch_value.get("delivery_failure_count") or 0
                )
                self._finish_pipeline_stage(
                    dispatch_stage,
                    dispatch_execution,
                    output_summary={
                        "delivered": bool(dispatch_value.get("sent")),
                        "dispatched": bool(dispatch_value.get("dispatched")),
                        "route": "report",
                        "dispatch_status": (
                            dispatch_value.get("dispatch_result_status") or None
                        ),
                        "attempt_count": (
                            0
                            if cached_dispatch
                            else (
                                len(dispatch_value.get("channel_results") or [])
                                or int(bool(dispatch_value.get("dispatched")))
                            )
                        ),
                        "failure_count": (
                            0 if cached_dispatch else cached_failure_count
                        ),
                        "cached_failure_count": (
                            cached_failure_count if cached_dispatch else 0
                        ),
                        "reused": cached_dispatch,
                    },
                )
                dispatch_execution.unwrap()
                dispatch_result = dispatch_value.get("dispatch_result")
                channel_results = dispatch_value.get("channel_results") or []
                dispatch_result_status = str(
                    dispatch_value.get("dispatch_result_status") or ""
                )
                dispatched = bool(dispatch_value.get("dispatched"))
                sent = bool(dispatch_value.get("sent"))
                delivery_failure_count = int(
                    dispatch_value.get("delivery_failure_count") or 0
                )
                dispatch_status = dispatch_execution.status.value
                if cached_dispatch:
                    self._refresh_saved_diagnostic_snapshot(
                        result=result,
                        fallback_code=fallback_code,
                    )
                elif channel_results:
                    for channel_result in channel_results:
                        channel_label = str(
                            getattr(channel_result, "channel", None) or "report"
                        )
                        channel_success = bool(
                            getattr(channel_result, "success", False)
                        )
                        channel_error = (
                            getattr(channel_result, "diagnostics", None)
                            or getattr(channel_result, "error_code", None)
                        )
                        notification_run = self._build_notification_run_snapshot(
                            channel=channel_label,
                            status="success" if channel_success else "failed",
                            success=channel_success,
                            error_message=channel_error,
                        )
                        record_notification_run(
                            channel=channel_label,
                            status="success" if channel_success else "failed",
                            success=channel_success,
                            error_message=channel_error,
                        )
                        self._refresh_saved_diagnostic_snapshot(
                            result=result,
                            fallback_code=fallback_code,
                            notification_run=notification_run,
                        )
                else:
                    notification_status = (
                        "success"
                        if dispatch_status in {"success", "degraded"}
                        else (
                            "skipped"
                            if dispatch_status == "skipped"
                            else "failed"
                        )
                    )
                    notification_run = self._build_notification_run_snapshot(
                        channel="report",
                        status=notification_status,
                        success=sent,
                        attempts=int(dispatched),
                        error_message=(
                            getattr(dispatch_result, "message", None)
                            if dispatch_result is not None
                            else None
                        ),
                    )
                    record_notification_run(
                        channel="report",
                        status=notification_status,
                        success=sent,
                        attempts=int(dispatched),
                        error_message=(
                            getattr(dispatch_result, "message", None)
                            if dispatch_result is not None
                            else None
                        ),
                    )
                    self._refresh_saved_diagnostic_snapshot(
                        result=result,
                        fallback_code=fallback_code,
                        notification_run=notification_run,
                    )
                if cached_dispatch:
                    logger.info(
                        "[%s] Reused the confirmed single-stock dispatch outcome",
                        stock_code,
                    )
                elif sent:
                    logger.info("[%s] Single-stock notification delivered", stock_code)
                elif dispatch_status == "skipped":
                    logger.info("[%s] Single-stock notification skipped", stock_code)
                else:
                    logger.warning("[%s] Single-stock notification delivery failed", stock_code)
            except Exception as e:  # broad-exception: fallback_recorded - Notification failures are recorded and safely logged without changing analysis success.
                if not render_stage.finished:
                    self._finish_pipeline_stage(
                        render_stage,
                        PipelineStageResult.failed(
                            PipelineStageName.RENDER,
                            error=e,
                            retryable=False,
                        ),
                    )
                    self._record_pipeline_stage_result(
                        PipelineStageResult.skipped(
                            PipelineStageName.DISPATCH,
                            reason="render_failed",
                        ),
                        input_summary={
                            "stock_code": stock_code,
                            "route": "report",
                            "result_count": 1,
                        },
                        output_summary={"reason": "render_failed"},
                    )
                elif dispatch_stage is not None and not dispatch_stage.finished:
                    self._finish_pipeline_stage(
                        dispatch_stage,
                        PipelineStageResult.failed(
                            PipelineStageName.DISPATCH,
                            error=e,
                            retryable=True,
                        ),
                    )
                notification_run = self._build_notification_run_snapshot(
                    channel="report",
                    status="failed",
                    success=False,
                    error_message=e,
                )
                record_notification_run(
                    channel="report",
                    status="failed",
                    success=False,
                    error_message=e,
                )
                self._refresh_saved_diagnostic_snapshot(
                    result=result,
                    fallback_code=fallback_code,
                    notification_run=notification_run,
                )
                log_safe_exception(
                    logger,
                    "Single-stock notification failed",
                    e,
                    error_code="pipeline_single_stock_notification_failed",
                    context={"stock_code": stock_code},
                )

    def _save_local_report(
        self,
        results: List[AnalysisResult],
        report_type: ReportType = ReportType.SIMPLE,
    ) -> None:
        """保存分析报告到本地文件（与通知推送解耦）"""
        render_stage = observe_pipeline_stage(
            "render",
            input_summary={
                "report_type": report_type.value,
                "result_count": len(results),
                "route": "local_report",
            },
            retryable=False,
        )
        try:
            def _render_local_report() -> PipelineStageResult[Tuple[Any, Any]]:
                report_content = self._generate_aggregate_report(results, report_type)
                saved_path = self.notifier.save_report_to_file(report_content)
                return PipelineStageResult.success(
                    PipelineStageName.RENDER,
                    (report_content, saved_path),
                    side_effect_committed=True,
                )

            render_result = self._run_pipeline_stage(
                PipelineStageName.RENDER,
                _render_local_report,
                retryable=False,
                side_effect_key=self._delivery_stage_key(
                    route="local_report",
                    results=results,
                    report_type=report_type,
                ),
            )
            render_value = render_result.value
            self._finish_pipeline_stage(
                render_stage,
                render_result,
                output_summary={
                    "content_length": (
                        len(render_value[0])
                        if render_value is not None
                        and isinstance(render_value[0], (str, bytes))
                        else None
                    ),
                    "route": "local_report",
                    "report_saved": render_result.successful,
                    "reused": render_result.reused,
                },
            )
            _, filepath = render_result.unwrap()
            logger.info("Decision dashboard saved: %s", filepath)
        except Exception as e:  # broad-exception: fallback_recorded - Local report failures are safely logged and do not change analysis results.
            if not render_stage.finished:
                self._finish_pipeline_stage(
                    render_stage,
                    PipelineStageResult.failed(
                        PipelineStageName.RENDER,
                        error=e,
                        retryable=False,
                    ),
                )
            log_safe_exception(
                logger,
                "Local report persistence failed",
                e,
                error_code="pipeline_local_report_save_failed",
            )

    def _send_notifications(
        self,
        results: List[AnalysisResult],
        report_type: ReportType = ReportType.SIMPLE,
        skip_push: bool = False,
    ) -> None:
        (
            "\n"
            "        发送分析结果通知\n"
            "        \n"
            "        生成决策仪表盘格式的报告\n"
            "        \n"
            "        Args:\n"
            "            results: 分析结果列表\n"
            "            skip_push: 是否跳过推送（仅保存到本地，用于单股推送模式）\n"
            "        "
        )
        noise_decision = None
        noise_finalized = False
        delivery_attempt_count = 0
        delivery_failure_count = 0
        delivery_reused_count = 0
        delivery_reused_channels: set[str] = set()
        static_delivery_scope: Optional[Tuple[Any, ...]] = None
        static_delivery_confirmed = False
        static_delivery_scope_owned = False
        static_scope_guards = ExitStack()
        render_stage = observe_pipeline_stage(
            "render",
            input_summary={
                "report_type": report_type.value,
                "result_count": len(results),
                "route": "aggregate_notification",
            },
            retryable=False,
        )
        dispatch_stage: Optional[PipelineStageObservation] = None
        try:
            logger.info("Generating the decision dashboard")
            report = self._generate_aggregate_report(results, report_type)
            render_result = PipelineStageResult.success(
                PipelineStageName.RENDER,
                report,
            )
            self._finish_pipeline_stage(
                render_stage,
                render_result,
                output_summary={
                    "content_length": (
                        len(report) if isinstance(report, (str, bytes)) else None
                    ),
                    "route": "aggregate_notification",
                },
            )
            dispatch_stage = observe_pipeline_stage(
                "dispatch",
                input_summary={
                    "report_type": report_type.value,
                    "result_count": len(results),
                    "skip_push": skip_push,
                },
                retryable=True,
            )

            # 跳过推送（单股推送模式 / 合并模式：报告已由 _save_local_report 保存）
            if skip_push:
                self._finish_pipeline_stage(
                    dispatch_stage,
                    PipelineStageResult.skipped(
                        PipelineStageName.DISPATCH,
                        reason="push_deferred",
                    ),
                    output_summary={"reason": "push_deferred"},
                )
                notification_run = self._build_notification_run_snapshot(
                    channel="report",
                    status="skipped",
                    success=False,
                    attempts=0,
                )
                record_notification_run(
                    channel="report",
                    status="skipped",
                    success=False,
                    attempts=0,
                )
                self._refresh_saved_diagnostic_snapshot(
                    results=results,
                    notification_run=notification_run,
                )
                return

            # 推送通知
            if self.notifier.is_available():
                channels = self.notifier.get_available_channels()
                channels = self.notifier.get_channels_for_route("report", channels=channels)

                def _send_channel_safely(
                    channel_label: str,
                    send_func: Callable[[], bool],
                ) -> tuple[bool, Optional[Exception]]:
                    delivery_result = self._run_delivery_attempt(
                        side_effect_key=self._delivery_stage_key(
                            route="aggregate",
                            results=results,
                            report_type=report_type,
                            channel=channel_label,
                        ),
                        send=send_func,
                    )
                    if delivery_result.reused:
                        delivery_reused_channels.add(channel_label)
                    delivery_error = delivery_result.error
                    if isinstance(delivery_error, Exception):
                        log_safe_exception(
                            logger,
                            "Notification channel delivery failed; continuing with remaining channels",
                            delivery_error,
                            error_code="pipeline_notification_channel_failed",
                            context={"channel": channel_label},
                        )
                    return bool(delivery_result.value), (
                        delivery_error
                        if isinstance(delivery_error, Exception)
                        else None
                    )

                def _record_channel_result(
                    channel_label: str,
                    success: bool,
                    error_message: Optional[Exception] = None,
                    target_results: Optional[List[AnalysisResult]] = None,
                ) -> None:
                    nonlocal delivery_attempt_count, delivery_failure_count
                    nonlocal delivery_reused_count
                    nonlocal static_delivery_confirmed
                    if channel_label != "__context__" and success:
                        static_delivery_confirmed = True
                    if channel_label in delivery_reused_channels:
                        delivery_reused_count += 1
                        delivery_reused_channels.discard(channel_label)
                        return
                    delivery_attempt_count += 1
                    if not success:
                        delivery_failure_count += 1
                    notification_run = self._build_notification_run_snapshot(
                        channel=channel_label,
                        status="success" if success else "failed",
                        success=success,
                        error_message=error_message,
                    )
                    record_notification_run(
                        channel=channel_label,
                        status="success" if success else "failed",
                        success=success,
                        error_message=error_message,
                    )
                    self._refresh_saved_diagnostic_snapshot(
                        results=results if target_results is None else target_results,
                        notification_run=notification_run,
                    )

                context_route_available = False
                has_context_channel = getattr(
                    self.notifier,
                    "_has_context_channel",
                    None,
                )
                if callable(has_context_channel):
                    try:
                        context_route_available = bool(has_context_channel())
                    except Exception as e:  # broad-exception: optional_metadata - Context-route availability only refines diagnostics and cannot block delivery.
                        log_safe_exception(
                            logger,
                            "Context notification availability check failed",
                            e,
                            error_code="pipeline_context_notification_availability_failed",
                            level=logging.WARNING,
                        )

                context_delivery = self._run_delivery_attempt(
                    side_effect_key=self._delivery_stage_key(
                        route="aggregate",
                        results=results,
                        report_type=report_type,
                        channel="__context__",
                    ),
                    send=lambda: self.notifier.send_to_context(report),
                )
                send_context = bool(context_delivery.unwrap())
                if context_delivery.reused:
                    delivery_reused_channels.add("__context__")
                if send_context:
                    _record_channel_result("__context__", True)
                elif context_route_available:
                    _record_channel_result("__context__", False)

                should_broadcast_static = True
                should_broadcast_static_func = getattr(
                    self.notifier,
                    "should_broadcast_static_channels",
                    None,
                )
                if callable(should_broadcast_static_func):
                    should_broadcast_static = bool(should_broadcast_static_func())
                if not should_broadcast_static:
                    if not send_context and not context_route_available:
                        _record_channel_result("__context__", False)
                    if send_context:
                        logger.info("Decision dashboard delivered")
                    else:
                        logger.warning("Decision dashboard delivery failed")
                    logger.info(
                        "Interactive context-reply mode enabled; static notification channels skipped"
                    )
                    context_dispatch_result = (
                        PipelineStageResult.success(
                            PipelineStageName.DISPATCH,
                            True,
                            side_effect_committed=True,
                        )
                        if send_context
                        else PipelineStageResult.failed(
                            PipelineStageName.DISPATCH,
                            value=False,
                            retryable=True,
                            reason="Context-reply delivery failed.",
                        )
                    )
                    self._finish_pipeline_stage(
                        dispatch_stage,
                        context_dispatch_result,
                        output_summary={
                            "delivered": bool(send_context),
                            "route": "context_reply",
                        },
                    )
                    self._refresh_saved_diagnostic_snapshot(results=results)
                    return

                static_delivery_scope = (
                    "aggregate_static_delivery",
                    self._delivery_stage_key(
                        route="aggregate",
                        results=results,
                        report_type=report_type,
                    ),
                )
                static_delivery_entered = True
                static_delivery_reentry = False
                if channels:
                    stage_runner = self._get_pipeline_stage_runner()
                    static_scope_guards.enter_context(
                        stage_runner.scope_guard(static_delivery_scope)
                    )
                    static_delivery_reentry = stage_runner.scope_started(
                        static_delivery_scope
                    )
                    if (
                        not static_delivery_reentry
                        and hasattr(self.notifier, "evaluate_noise_control")
                    ):
                        report_type_key = (
                            report_type.value
                            if isinstance(report_type, ReportType)
                            else str(report_type)
                        )
                        codes_key = ",".join(
                            sorted(
                                str(getattr(result, "code", "") or "")
                                for result in results
                            )
                        )
                        noise_key = (
                            f"report:aggregate:{report_type_key}:{codes_key}"
                        )
                        noise_decision = self.notifier.evaluate_noise_control(
                            report,
                            route_type="report",
                            severity="info",
                            dedup_key=noise_key,
                            cooldown_key=noise_key,
                        )
                        static_delivery_entered = bool(
                            noise_decision.should_send
                        )
                    if static_delivery_entered and not static_delivery_reentry:
                        stage_runner.mark_scope_started(static_delivery_scope)
                        static_delivery_scope_owned = True

                if not static_delivery_entered:
                    if send_context:
                        suppressed_dispatch_status = "success"
                        suppressed_retryable = False
                        suppressed_reason = None
                    elif context_route_available:
                        suppressed_dispatch_status = "failed"
                        suppressed_retryable = True
                        suppressed_reason = (
                            "Context-reply delivery failed and static channels "
                            "were suppressed by noise control."
                        )
                    else:
                        suppressed_dispatch_status = "skipped"
                        suppressed_retryable = False
                        suppressed_reason = None
                    if suppressed_dispatch_status == "success":
                        suppressed_result = PipelineStageResult.success(
                            PipelineStageName.DISPATCH,
                            True,
                            side_effect_committed=bool(send_context),
                        )
                    elif suppressed_dispatch_status == "failed":
                        suppressed_result = PipelineStageResult.failed(
                            PipelineStageName.DISPATCH,
                            value=False,
                            retryable=suppressed_retryable,
                            reason=suppressed_reason,
                        )
                    else:
                        suppressed_result = PipelineStageResult.skipped(
                            PipelineStageName.DISPATCH,
                            reason="noise_control",
                            value=False,
                        )
                    self._finish_pipeline_stage(
                        dispatch_stage,
                        suppressed_result,
                        output_summary={
                            "reason": "noise_control",
                            "reason_code": noise_decision.reason_code,
                            "context_delivered": bool(send_context),
                            "context_attempted": context_route_available,
                            "static_suppressed": True,
                        },
                    )
                    notification_run = self._build_notification_run_snapshot(
                        channel="report",
                        status="skipped",
                        success=False,
                        attempts=0,
                    )
                    record_notification_run(
                        channel="report",
                        status="skipped",
                        success=False,
                        attempts=0,
                    )
                    self._refresh_saved_diagnostic_snapshot(
                        results=results,
                        notification_run=notification_run,
                    )
                    logger.info(
                        "Notification suppressed by noise control: reason_code=%s "
                        "route_type=%s severity=%s",
                        noise_decision.reason_code,
                        noise_decision.route_type,
                        noise_decision.severity,
                    )
                    return

                if static_delivery_reentry:
                    logger.debug(
                        "Aggregate delivery re-entry bypassed the first-entry "
                        "noise gate; per-channel fences remain authoritative"
                    )

                # Issue #455: Markdown 转图片（与 notification.send 逻辑一致）
                from src.md2img import markdown_to_image

                channels_needing_image = {
                    ch for ch in channels
                    if ch.value in self.notifier._markdown_to_image_channels
                    and ch not in {NotificationChannel.NTFY, NotificationChannel.GOTIFY}
                }
                non_wechat_channels_needing_image = {
                    ch for ch in channels_needing_image if ch != NotificationChannel.WECHAT
                }

                def _get_md2img_hint() -> str:
                    try:
                        engine = getattr(get_config(), "md2img_engine", "wkhtmltoimage")
                    except Exception:  # broad-exception: optional_metadata - Renderer install hints fall back to the default when optional config lookup fails.
                        engine = "wkhtmltoimage"
                    return (
                        "npm i -g markdown-to-file" if engine == "markdown-to-file"
                        else "wkhtmltopdf (apt install wkhtmltopdf / brew install wkhtmltopdf)"
                    )

                image_bytes = None
                if non_wechat_channels_needing_image:
                    image_bytes = markdown_to_image(
                        report, max_chars=self.notifier._markdown_to_image_max_chars
                    )
                    if image_bytes:
                        logger.info(
                            "Markdown converted to an image for channels: %s",
                            [ch.value for ch in non_wechat_channels_needing_image],
                        )
                    else:
                        logger.warning(
                            "Markdown-to-image conversion failed; falling back to text. "
                            "Check MARKDOWN_TO_IMAGE_CHANNELS and install %s",
                            _get_md2img_hint(),
                        )

                # 企业微信：只发精简版（平台限制）
                wechat_success = False
                if NotificationChannel.WECHAT in channels:
                    def _send_wechat_report() -> bool:
                        if report_type == ReportType.BRIEF:
                            dashboard_content = self.notifier.generate_brief_report(results)
                        else:
                            dashboard_content = self.notifier.generate_wechat_dashboard(results)
                        logger.info(
                            "WeCom dashboard prepared: character_count=%s",
                            len(dashboard_content),
                        )
                        wechat_image_bytes = None
                        if NotificationChannel.WECHAT in channels_needing_image:
                            wechat_image_bytes = markdown_to_image(
                                dashboard_content,
                                max_chars=self.notifier._markdown_to_image_max_chars,
                            )
                            if wechat_image_bytes is None:
                                logger.warning(
                                    "WeCom Markdown-to-image conversion failed; falling back to text. "
                                    "Check MARKDOWN_TO_IMAGE_CHANNELS and install %s",
                                    _get_md2img_hint(),
                                )
                        use_image = self.notifier._should_use_image_for_channel(
                            NotificationChannel.WECHAT, wechat_image_bytes
                        )
                        if use_image:
                            return self.notifier._send_wechat_image(wechat_image_bytes)
                        return self.notifier.send_to_wechat(dashboard_content)

                    wechat_success, wechat_error = _send_channel_safely(
                        NotificationChannel.WECHAT.value,
                        _send_wechat_report,
                    )
                    _record_channel_result(
                        NotificationChannel.WECHAT.value,
                        wechat_success,
                        wechat_error,
                    )

                # 其他渠道：发完整报告（避免自定义 Webhook 被 wechat 截断逻辑污染）
                non_wechat_success = False
                stock_email_groups = getattr(self.config, 'stock_email_groups', []) or []
                for channel in channels:
                    if channel == NotificationChannel.WECHAT:
                        continue
                    if channel == NotificationChannel.FEISHU:
                        def _send_feishu_report() -> bool:
                            if getattr(self.notifier, "_feishu_send_as_file", False):
                                date_str = datetime.now().strftime('%Y%m%d')
                                filepath = self.notifier.save_report_to_file(
                                    report, filename=f"dashboard_{date_str}.md"
                                )
                                return self.notifier.send_feishu_file(filepath)
                            return self.notifier.send_to_feishu(report)

                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            _send_feishu_report,
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.TELEGRAM:
                        def _send_telegram_report() -> bool:
                            use_image = self.notifier._should_use_image_for_channel(
                                channel, image_bytes
                            )
                            if use_image:
                                return self.notifier._send_telegram_photo(image_bytes)
                            return self.notifier.send_to_telegram(report)

                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            _send_telegram_report,
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.EMAIL:
                        if stock_email_groups:
                            code_to_emails: Dict[str, Optional[List[str]]] = {}
                            for r in results:
                                if r.code not in code_to_emails:
                                    canonical = normalize_stock_code(r.code)
                                    emails = []
                                    for stocks, emails_list in stock_email_groups:
                                        if canonical in stocks:
                                            emails.extend(emails_list)
                                    code_to_emails[r.code] = list(dict.fromkeys(emails)) if emails else None
                            emails_to_results: Dict[Optional[Tuple], List] = defaultdict(list)
                            for r in results:
                                recs = code_to_emails.get(r.code)
                                key = tuple(recs) if recs else None
                                emails_to_results[key].append(r)
                            for key, group_results in emails_to_results.items():
                                receivers = list(key) if key is not None else None

                                def _send_email_group(
                                    group_results=group_results,
                                    receivers=receivers,
                                ) -> bool:
                                    grp_report = self._generate_aggregate_report(group_results, report_type)
                                    grp_image_bytes = None
                                    if channel.value in self.notifier._markdown_to_image_channels:
                                        grp_image_bytes = markdown_to_image(
                                            grp_report,
                                            max_chars=self.notifier._markdown_to_image_max_chars,
                                        )
                                    use_image = self.notifier._should_use_image_for_channel(
                                        channel, grp_image_bytes
                                    )
                                    if use_image:
                                        return self.notifier._send_email_with_inline_image(
                                            grp_image_bytes, receivers=receivers
                                        )
                                    return self.notifier.send_to_email(
                                        grp_report, receivers=receivers
                                    )

                                email_label = (
                                    f"{channel.value}:{','.join(receivers)}"
                                    if receivers else f"{channel.value}:default"
                                )
                                channel_success, channel_error = _send_channel_safely(
                                    email_label,
                                    _send_email_group,
                                )
                                non_wechat_success = channel_success or non_wechat_success
                                _record_channel_result(
                                    email_label,
                                    channel_success,
                                    channel_error,
                                    target_results=group_results,
                                )
                        else:
                            def _send_email_report() -> bool:
                                use_image = self.notifier._should_use_image_for_channel(
                                    channel, image_bytes
                                )
                                if use_image:
                                    return self.notifier._send_email_with_inline_image(image_bytes)
                                return self.notifier.send_to_email(report)

                            channel_success, channel_error = _send_channel_safely(
                                channel.value,
                                _send_email_report,
                            )
                            non_wechat_success = channel_success or non_wechat_success
                            _record_channel_result(
                                channel.value,
                                channel_success,
                                channel_error,
                            )
                    elif channel == NotificationChannel.CUSTOM:
                        def _send_custom_report() -> bool:
                            use_image = self.notifier._should_use_image_for_channel(
                                channel, image_bytes
                            )
                            if use_image:
                                return self.notifier._send_custom_webhook_image(
                                    image_bytes, fallback_content=report
                                )
                            return self.notifier.send_to_custom(report)

                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            _send_custom_report,
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.PUSHPLUS:
                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            lambda: self.notifier.send_to_pushplus(report),
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.SERVERCHAN3:
                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            lambda: self.notifier.send_to_serverchan3(report),
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.DISCORD:
                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            lambda: self.notifier.send_to_discord(report),
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.PUSHOVER:
                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            lambda: self.notifier.send_to_pushover(report),
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.NTFY:
                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            lambda: self.notifier.send_to_ntfy(report),
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.GOTIFY:
                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            lambda: self.notifier.send_to_gotify(report),
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.ASTRBOT:
                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            lambda: self.notifier.send_to_astrbot(report),
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    elif channel == NotificationChannel.SLACK:
                        def _send_slack_report() -> bool:
                            use_image = self.notifier._should_use_image_for_channel(
                                channel, image_bytes
                            )
                            if use_image and self.notifier._slack_bot_token and self.notifier._slack_channel_id:
                                return self.notifier._send_slack_image(
                                    image_bytes, fallback_content=report
                                )
                            return self.notifier.send_to_slack(report)

                        channel_success, channel_error = _send_channel_safely(
                            channel.value,
                            _send_slack_report,
                        )
                        non_wechat_success = channel_success or non_wechat_success
                        _record_channel_result(
                            channel.value,
                            channel_success,
                            channel_error,
                        )
                    else:
                        logger.warning("Unknown notification channel: %s", channel)

                has_targeted_channels = bool(channels)
                success = wechat_success or non_wechat_success or send_context
                if (
                    (wechat_success or non_wechat_success)
                    and noise_decision is not None
                    and hasattr(self.notifier, "record_noise_control")
                ):
                    self.notifier.record_noise_control(noise_decision)
                    noise_finalized = True
                elif (
                    noise_decision is not None
                    and hasattr(self.notifier, "release_noise_control")
                ):
                    self.notifier.release_noise_control(noise_decision)
                    noise_finalized = True
                if (
                    static_delivery_scope is not None
                    and static_delivery_scope_owned
                    and not static_delivery_confirmed
                ):
                    self._get_pipeline_stage_runner().clear_scope_started(
                        static_delivery_scope
                    )
                if success:
                    logger.info("Decision dashboard delivered")
                else:
                    logger.warning("Decision dashboard delivery failed")
                if not has_targeted_channels and not send_context:
                    channel_label = ",".join(channel.value for channel in channels) or "report"
                    notification_run = self._build_notification_run_snapshot(
                        channel=channel_label,
                        status="success" if success else "failed",
                        success=success,
                    )
                    record_notification_run(
                        channel=channel_label,
                        status="success" if success else "failed",
                        success=success,
                    )
                    self._refresh_saved_diagnostic_snapshot(
                        results=results,
                        notification_run=notification_run,
                    )
                dispatch_status = (
                    "degraded"
                    if success and delivery_failure_count
                    else ("success" if success else "failed")
                )
                if dispatch_status == "degraded":
                    aggregate_dispatch_result = PipelineStageResult.degraded(
                        PipelineStageName.DISPATCH,
                        success,
                        reason="Some notification deliveries failed.",
                        side_effect_committed=True,
                    )
                elif dispatch_status == "success":
                    aggregate_dispatch_result = PipelineStageResult.success(
                        PipelineStageName.DISPATCH,
                        success,
                        side_effect_committed=bool(success),
                    )
                else:
                    aggregate_dispatch_result = PipelineStageResult.failed(
                        PipelineStageName.DISPATCH,
                        value=False,
                        reason="All configured notification deliveries failed.",
                        retryable=True,
                    )
                self._finish_pipeline_stage(
                    dispatch_stage,
                    aggregate_dispatch_result,
                    output_summary={
                        "delivered": bool(success),
                        "channel_count": len(channels),
                        "context_delivered": bool(send_context),
                        "attempt_count": delivery_attempt_count,
                        "failure_count": delivery_failure_count,
                        "reused_count": delivery_reused_count,
                    },
                )
                self._refresh_saved_diagnostic_snapshot(results=results)
            else:
                self._finish_pipeline_stage(
                    dispatch_stage,
                    PipelineStageResult.skipped(
                        PipelineStageName.DISPATCH,
                        reason="notification_not_configured",
                    ),
                    output_summary={"reason": "notification_not_configured"},
                )
                notification_run = self._build_notification_run_snapshot(
                    channel="report",
                    status="not_configured",
                    success=False,
                    attempts=0,
                )
                record_notification_run(
                    channel="report",
                    status="not_configured",
                    success=False,
                    attempts=0,
                )
                self._refresh_saved_diagnostic_snapshot(
                    results=results,
                    notification_run=notification_run,
                )
                logger.info("No notification channel is configured; skipping delivery")

        except Exception as e:  # broad-exception: fallback_recorded - Dispatch failures are recorded and safely logged without changing analysis results.
            if not render_stage.finished:
                self._finish_pipeline_stage(
                    render_stage,
                    PipelineStageResult.failed(
                        PipelineStageName.RENDER,
                        error=e,
                        retryable=False,
                    ),
                )
                self._record_pipeline_stage_result(
                    PipelineStageResult.skipped(
                        PipelineStageName.DISPATCH,
                        reason="render_failed",
                    ),
                    input_summary={
                        "report_type": report_type.value,
                        "result_count": len(results),
                    },
                    output_summary={"reason": "render_failed"},
                )
            elif dispatch_stage is not None and not dispatch_stage.finished:
                confirmed_delivery_count = max(
                    0,
                    delivery_attempt_count - delivery_failure_count,
                ) + delivery_reused_count
                failed_dispatch_result = (
                    PipelineStageResult.degraded(
                        PipelineStageName.DISPATCH,
                        False,
                        reason=(
                            "Dispatch failed after one or more deliveries succeeded."
                        ),
                        side_effect_committed=True,
                        error=e,
                    )
                    if confirmed_delivery_count
                    else PipelineStageResult.failed(
                        PipelineStageName.DISPATCH,
                        error=e,
                        retryable=True,
                        reason="Dispatch failed before any delivery was confirmed.",
                    )
                )
                self._finish_pipeline_stage(
                    dispatch_stage,
                    failed_dispatch_result,
                    output_summary={
                        "attempt_count": delivery_attempt_count,
                        "failure_count": delivery_failure_count,
                        "confirmed_delivery_count": confirmed_delivery_count,
                        "reused_count": delivery_reused_count,
                    },
                )
            notification_run = self._build_notification_run_snapshot(
                channel="report",
                status="failed",
                success=False,
                error_message=e,
            )
            record_notification_run(
                channel="report",
                status="failed",
                success=False,
                error_message=e,
            )
            self._refresh_saved_diagnostic_snapshot(
                results=results,
                notification_run=notification_run,
            )
            if noise_decision is not None and not noise_finalized:
                if (
                    static_delivery_confirmed
                    and hasattr(self.notifier, "record_noise_control")
                ):
                    self.notifier.record_noise_control(noise_decision)
                elif hasattr(self.notifier, "release_noise_control"):
                    self.notifier.release_noise_control(noise_decision)
            if (
                static_delivery_scope is not None
                and static_delivery_scope_owned
                and not static_delivery_confirmed
            ):
                self._get_pipeline_stage_runner().clear_scope_started(
                    static_delivery_scope
                )
            log_safe_exception(
                logger,
                "Notification delivery failed",
                e,
                error_code="pipeline_notification_delivery_failed",
            )
        finally:
            static_scope_guards.close()

    def _generate_aggregate_report(
        self,
        results: List[AnalysisResult],
        report_type: ReportType,
    ) -> str:
        """Generate aggregate report with backward-compatible notifier fallback."""
        generator = getattr(self.notifier, "generate_aggregate_report", None)
        if callable(generator):
            return generator(results, report_type)
        if report_type == ReportType.BRIEF and hasattr(self.notifier, "generate_brief_report"):
            return self.notifier.generate_brief_report(results)
        return self.notifier.generate_dashboard_report(results)
