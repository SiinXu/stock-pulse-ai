# -*- coding: utf-8 -*-
"""Rendering and notification delivery stages for the stock analysis pipeline."""

import logging
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.analyzer import AnalysisResult
from src.config import get_config as _get_config_impl
from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageResult,
    PipelineStageStatus,
)
from src.enums import ReportType
from src.notification import (
    ChannelAttemptResult as _ChannelAttemptResult,
)
from src.services.run_diagnostics import (
    PipelineStageObservation,
    observe_pipeline_stage,
    record_notification_run as _record_notification_run_impl,
)
from src.utils.sanitize import (
    log_safe_exception,
)


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


def _run_plugin_delivery_attempt(
    pipeline: Any,
    *,
    side_effect_key: Tuple[Any, ...],
    send: Callable[[], _ChannelAttemptResult],
) -> PipelineStageResult[_ChannelAttemptResult]:
    """Fence one structured channel attempt with its retry decision."""

    def _dispatch() -> PipelineStageResult[_ChannelAttemptResult]:
        attempt = send()
        if not isinstance(attempt, _ChannelAttemptResult):
            raise TypeError("notification attempt is invalid")
        if attempt.success:
            return PipelineStageResult.success(
                PipelineStageName.DISPATCH,
                attempt,
                side_effect_committed=True,
            )
        return PipelineStageResult.failed(
            PipelineStageName.DISPATCH,
            value=attempt,
            retryable=attempt.retryable,
            side_effect_committed=not attempt.retryable,
            reason=(
                attempt.diagnostics
                or attempt.error_code
                or "Notification delivery was not confirmed."
            ),
        )

    return pipeline._get_pipeline_stage_runner().run(
        PipelineStageName.DISPATCH,
        _dispatch,
        retryable=True,
        side_effect_key=side_effect_key,
    )

class _DeliveryStageMixin:
    """Provide rendering and notification delivery stages for the pipeline."""

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
        """Render an aggregate report, then dispatch through NotificationService."""

        from src.notification_parts.dispatch import (
            dispatch_aggregate_with_results,
        )

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
        execution = None
        static_delivery_scope: Optional[Tuple[Any, ...]] = None
        static_delivery_scope_was_started = False
        try:
            logger.info("Generating the decision dashboard")
            report = self._generate_aggregate_report(results, report_type)
            self._finish_pipeline_stage(
                render_stage,
                PipelineStageResult.success(
                    PipelineStageName.RENDER,
                    report,
                ),
                output_summary={
                    "content_length": (
                        len(report)
                        if isinstance(report, (str, bytes))
                        else None
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

            stage_runner = self._get_pipeline_stage_runner()
            delivery_key = self._delivery_stage_key(
                route="aggregate",
                results=results,
                report_type=report_type,
            )
            static_delivery_scope = (
                "aggregate_static_delivery",
                delivery_key,
            )
            static_delivery_scope_was_started = stage_runner.scope_started(
                static_delivery_scope
            )
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
            noise_key = f"report:aggregate:{report_type_key}:{codes_key}"

            def _execute_attempt(
                channel_label: str,
                send: Callable[[], _ChannelAttemptResult],
            ) -> tuple[_ChannelAttemptResult, bool]:
                """Fence one canonical dispatch attempt by channel label."""

                delivery_result = _run_plugin_delivery_attempt(
                    self,
                    side_effect_key=self._delivery_stage_key(
                        route="aggregate",
                        results=results,
                        report_type=report_type,
                        channel=channel_label,
                    ),
                    send=send,
                )
                attempt = delivery_result.value
                if not isinstance(attempt, _ChannelAttemptResult):
                    delivery_result.unwrap()
                    raise TypeError("notification attempt is unavailable")
                return attempt, delivery_result.reused

            with stage_runner.scope_guard(static_delivery_scope):
                execution = dispatch_aggregate_with_results(
                    self.notifier,
                    report,
                    results=results,
                    report_type=report_type,
                    config=self.config,
                    render_aggregate=self._generate_aggregate_report,
                    execute_attempt=_execute_attempt,
                    scope_started=lambda: stage_runner.scope_started(
                        static_delivery_scope
                    ),
                    mark_scope_started=lambda: stage_runner.mark_scope_started(
                        static_delivery_scope
                    ),
                    clear_scope_started=lambda: stage_runner.clear_scope_started(
                        static_delivery_scope
                    ),
                    dedup_key=noise_key,
                    cooldown_key=noise_key,
                )

            dispatch_result = execution.result
            channel_results = list(dispatch_result.channel_results)
            failed_attempts = [
                attempt for attempt in channel_results if not attempt.success
            ]
            for record in execution.records:
                if record.reused:
                    continue
                attempt = record.attempt
                error_message = " | ".join(
                    value
                    for value in (
                        attempt.error_code,
                        attempt.diagnostics,
                    )
                    if value
                ) or None
                notification_run = self._build_notification_run_snapshot(
                    channel=attempt.channel,
                    status="success" if attempt.success else "failed",
                    success=bool(attempt.success),
                    error_message=error_message,
                )
                record_notification_run(
                    channel=attempt.channel,
                    status="success" if attempt.success else "failed",
                    success=bool(attempt.success),
                    error_message=error_message,
                )
                self._refresh_saved_diagnostic_snapshot(
                    results=(
                        results
                        if record.target_results is None
                        else record.target_results
                    ),
                    notification_run=notification_run,
                )

            if dispatch_result.status == "partial_failed":
                stage_result = PipelineStageResult.degraded(
                    PipelineStageName.DISPATCH,
                    bool(dispatch_result.success),
                    reason="Some notification deliveries failed.",
                    retryable=any(
                        bool(attempt.retryable)
                        for attempt in failed_attempts
                    ),
                    side_effect_committed=True,
                )
            elif dispatch_result.status == "sent":
                stage_result = PipelineStageResult.success(
                    PipelineStageName.DISPATCH,
                    True,
                    side_effect_committed=True,
                )
            elif dispatch_result.status in {
                "noise_suppressed",
                "no_channel",
            }:
                stage_result = PipelineStageResult.skipped(
                    PipelineStageName.DISPATCH,
                    value=False,
                    reason=dispatch_result.status,
                )
            else:
                stage_result = PipelineStageResult.failed(
                    PipelineStageName.DISPATCH,
                    value=False,
                    reason=(
                        dispatch_result.message
                        or "All configured notification deliveries failed."
                    ),
                    retryable=(
                        any(
                            bool(attempt.retryable)
                            for attempt in failed_attempts
                        )
                        if failed_attempts
                        else True
                    ),
                )

            if execution.context_only:
                output_summary = {
                    "delivered": bool(dispatch_result.success),
                    "route": "context_reply",
                }
            elif execution.static_suppressed:
                output_summary = {
                    "reason": "noise_control",
                    "reason_code": execution.noise_reason_code,
                    "context_delivered": any(
                        attempt.channel == "__context__"
                        and bool(attempt.success)
                        for attempt in channel_results
                    ),
                    "context_attempted": execution.context_attempted,
                    "static_suppressed": True,
                }
            elif dispatch_result.status == "no_channel":
                output_summary = {
                    "reason": "notification_not_configured",
                }
            else:
                output_summary = {
                    "delivered": bool(dispatch_result.success),
                    "channel_count": execution.target_channel_count,
                    "context_delivered": any(
                        attempt.channel == "__context__"
                        and bool(attempt.success)
                        for attempt in channel_results
                    ),
                    "attempt_count": execution.attempt_count,
                    "failure_count": execution.failure_count,
                    "reused_count": execution.reused_count,
                }

            self._finish_pipeline_stage(
                dispatch_stage,
                stage_result,
                output_summary=output_summary,
            )

            if not execution.records:
                notification_status = (
                    "skipped"
                    if dispatch_result.status == "noise_suppressed"
                    else "not_configured"
                )
                notification_run = self._build_notification_run_snapshot(
                    channel="report",
                    status=notification_status,
                    success=False,
                    attempts=0,
                )
                record_notification_run(
                    channel="report",
                    status=notification_status,
                    success=False,
                    attempts=0,
                )
                self._refresh_saved_diagnostic_snapshot(
                    results=results,
                    notification_run=notification_run,
                )
            else:
                self._refresh_saved_diagnostic_snapshot(results=results)

            if dispatch_result.success:
                logger.info("Decision dashboard delivered")
            elif dispatch_result.status in {
                "noise_suppressed",
                "no_channel",
            }:
                logger.info("Decision dashboard delivery skipped")
            else:
                logger.warning("Decision dashboard delivery failed")

        except Exception as exc:  # broad-exception: fallback_recorded - notification failures do not change analysis success
            if (
                static_delivery_scope is not None
                and execution is None
                and not static_delivery_scope_was_started
            ):
                self._get_pipeline_stage_runner().clear_scope_started(
                    static_delivery_scope
                )
            if not render_stage.finished:
                self._finish_pipeline_stage(
                    render_stage,
                    PipelineStageResult.failed(
                        PipelineStageName.RENDER,
                        error=exc,
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
                confirmed_delivery_count = (
                    sum(
                        bool(record.attempt.success)
                        for record in execution.records
                    )
                    if execution is not None
                    else 0
                )
                failed_result = (
                    PipelineStageResult.degraded(
                        PipelineStageName.DISPATCH,
                        False,
                        reason=(
                            "Dispatch failed after one or more deliveries "
                            "succeeded."
                        ),
                        side_effect_committed=True,
                        error=exc,
                    )
                    if confirmed_delivery_count
                    else PipelineStageResult.failed(
                        PipelineStageName.DISPATCH,
                        error=exc,
                        retryable=True,
                        reason=(
                            "Dispatch failed before any delivery was confirmed."
                        ),
                    )
                )
                self._finish_pipeline_stage(
                    dispatch_stage,
                    failed_result,
                    output_summary={
                        "attempt_count": (
                            execution.attempt_count
                            if execution is not None
                            else 0
                        ),
                        "failure_count": (
                            execution.failure_count
                            if execution is not None
                            else 0
                        ),
                        "confirmed_delivery_count": confirmed_delivery_count,
                        "reused_count": (
                            execution.reused_count
                            if execution is not None
                            else 0
                        ),
                    },
                )
            notification_run = self._build_notification_run_snapshot(
                channel="report",
                status="failed",
                success=False,
                error_message=exc,
            )
            record_notification_run(
                channel="report",
                status="failed",
                success=False,
                error_message=exc,
            )
            self._refresh_saved_diagnostic_snapshot(
                results=results,
                notification_run=notification_run,
            )
            log_safe_exception(
                logger,
                "Notification delivery failed",
                exc,
                error_code="pipeline_notification_delivery_failed",
            )
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
