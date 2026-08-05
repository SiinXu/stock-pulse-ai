"""Dispatch methods for the public notification facade."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Protocol

from src.utils.sanitize import (
    sanitize_diagnostic_text as _sanitize_dispatch_log_value,
)

if TYPE_CHECKING:
    from src.notification import (
        ChannelAttemptResult,
        ChannelDetector,
        NotificationChannel,
        NotificationDispatchResult,
        WECHAT_IMAGE_MAX_BYTES,
        _NotificationAdapterResult,
        _NotificationChannelSnapshot,
        _NotificationRequest,
        _ROUTABLE_NOTIFICATION_CHANNELS,
        _available_notification_channel_snapshot,
        _ensure_notification_runtime,
        _normalize_notification_adapter_error_code,
        log_safe_exception,
        logger,
        sanitize_diagnostic_text,
        sanitize_exception_chain,
    )


class _ImageBuilder(Protocol):
    """Convert Markdown report content into optional PNG bytes."""

    def __call__(
        self,
        content: str,
        *,
        max_chars: int,
    ) -> Optional[bytes]:
        """Render one Markdown document to image bytes when possible."""


@dataclass(frozen=True)
class DispatchFacadePorts:
    """Public-facade symbols free functions need without import-time cycles.

    Bound once at the notification composition root after ``NotificationChannel``
    and related types exist on ``src.notification``.
    """

    NotificationChannel: Any
    ChannelAttemptResult: Any
    NotificationDispatchResult: Any
    ChannelDetector: Any
    WECHAT_IMAGE_MAX_BYTES: int
    logger: Any
    log_safe_exception: Callable[..., Any]
    sanitize_exception_chain: Callable[..., Any]
    ensure_notification_runtime: Callable[..., Any]
    ROUTABLE_NOTIFICATION_CHANNELS: Any
    available_notification_channel_snapshot: Callable[..., Any]


@dataclass(frozen=True)
class DispatchPorts:
    """Injectable dispatch dependencies derived from the deferred-import inventory.

    Port roles:
    - ``image_builder``: optional Markdown-to-image conversion (four prior sites)
    - ``normalize_stock_code``: aggregate email receiver routing by stock code
    - ``report_type_cls``: aggregate WeCom brief vs dashboard branch
    - ``facade``: cycle-avoidance symbols from the public notification facade
    """

    image_builder: _ImageBuilder
    normalize_stock_code: Callable[[str], Any]
    report_type_cls: Any
    facade: DispatchFacadePorts


_PORTS: Optional[DispatchPorts] = None


def build_default_dispatch_ports() -> DispatchPorts:
    """Build ports with the same imports dispatch previously deferred locally.

    Called at the notification facade composition point so free functions never
    re-import cycle-sensitive symbols. ``image_builder`` looks up
    ``src.md2img.markdown_to_image`` on each call so existing test patch seams
    on that attribute keep working.
    """

    from data_provider.base import normalize_stock_code
    from src.enums import ReportType
    from src.notification import (
        ChannelAttemptResult,
        ChannelDetector,
        NotificationChannel,
        NotificationDispatchResult,
        WECHAT_IMAGE_MAX_BYTES,
        _ROUTABLE_NOTIFICATION_CHANNELS,
        _available_notification_channel_snapshot,
        _ensure_notification_runtime,
        log_safe_exception,
        logger,
        sanitize_exception_chain,
    )
    import src.md2img as md2img

    def image_builder(content: str, *, max_chars: int) -> Optional[bytes]:
        """Delegate to the process-wide Markdown image converter."""

        # Attribute lookup (not a bound local) preserves patch seams.
        return md2img.markdown_to_image(content, max_chars=max_chars)

    return DispatchPorts(
        image_builder=image_builder,
        normalize_stock_code=normalize_stock_code,
        report_type_cls=ReportType,
        facade=DispatchFacadePorts(
            NotificationChannel=NotificationChannel,
            ChannelAttemptResult=ChannelAttemptResult,
            NotificationDispatchResult=NotificationDispatchResult,
            ChannelDetector=ChannelDetector,
            WECHAT_IMAGE_MAX_BYTES=WECHAT_IMAGE_MAX_BYTES,
            logger=logger,
            log_safe_exception=log_safe_exception,
            sanitize_exception_chain=sanitize_exception_chain,
            ensure_notification_runtime=_ensure_notification_runtime,
            ROUTABLE_NOTIFICATION_CHANNELS=_ROUTABLE_NOTIFICATION_CHANNELS,
            available_notification_channel_snapshot=(
                _available_notification_channel_snapshot
            ),
        ),
    )


def configure_dispatch_ports(ports: Optional[DispatchPorts] = None) -> DispatchPorts:
    """Install process-wide dispatch ports (idempotent replace)."""

    global _PORTS
    _PORTS = ports if ports is not None else build_default_dispatch_ports()
    return _PORTS


def get_dispatch_ports() -> DispatchPorts:
    """Return configured ports, building the default composition when unset."""

    if _PORTS is None:
        configure_dispatch_ports()
    assert _PORTS is not None
    return _PORTS


@dataclass
class _DispatchAttemptRecord:
    """Retain one canonical attempt plus Pipeline-only bookkeeping."""

    attempt: Any
    target_results: Optional[List[Any]] = None
    reused: bool = False


@dataclass
class _DispatchExecution:
    """Internal dispatch outcome consumed by the public facade and Pipeline."""

    result: Any
    records: List[_DispatchAttemptRecord] = field(default_factory=list)
    context_attempted: bool = False
    context_only: bool = False
    static_suppressed: bool = False
    noise_reason_code: Optional[str] = None
    target_channel_count: int = 0

    @property
    def attempt_count(self) -> int:
        """Count physical attempts executed during this dispatch."""

        return sum(not record.reused for record in self.records)

    @property
    def failure_count(self) -> int:
        """Count failed physical attempts executed during this dispatch."""

        return sum(
            not record.reused and not bool(record.attempt.success)
            for record in self.records
        )

    @property
    def reused_count(self) -> int:
        """Count attempts reused from an idempotency fence."""

        return sum(record.reused for record in self.records)


@dataclass(frozen=True)
class _ImagePreparationOutcome:
    """Retain shared image bytes or one structured preparation failure."""

    image_bytes: Optional[bytes] = None
    failed_channel_ids: frozenset[str] = frozenset()
    diagnostics: Optional[str] = None


@dataclass
class _AggregateDispatchContext:
    """Pipeline hooks needed to preserve aggregate rendering and retry fences."""

    results: List[Any]
    report_type: Any
    config: Any
    render_aggregate: Callable[[List[Any], Any], str]
    execute_attempt: Callable[[str, Callable[[], Any]], tuple[Any, bool]]
    scope_started: Callable[[], bool]
    mark_scope_started: Callable[[], None]
    clear_scope_started: Callable[[], None]


def _channel_id(channel: Any) -> str:
    """Return the canonical identifier for a built-in or plugin channel."""

    NotificationChannel = get_dispatch_ports().facade.NotificationChannel

    return (
        channel.value
        if isinstance(channel, NotificationChannel)
        else channel.channel_id
    )


def _safe_attempt_sender(
    service: Any,
    channel: Any,
    channel_id: str,
    send: Callable[[], Any],
    *,
    aggregate: bool,
) -> Callable[[], Any]:
    """Convert one sender into an exception-isolated attempt factory."""

    def _send():
        """Execute one sender and normalize its structured result."""

        facade = get_dispatch_ports().facade
        ChannelAttemptResult = facade.ChannelAttemptResult
        NotificationChannel = facade.NotificationChannel
        log_safe_exception = facade.log_safe_exception
        sanitize_exception_chain = facade.sanitize_exception_chain

        dispatch_logger = logging.getLogger(
            "src.core.pipeline" if aggregate else "src.notification"
        )
        started_at = time.monotonic()
        try:
            result = send()
            if isinstance(result, ChannelAttemptResult):
                return result
            success = bool(result)
            return ChannelAttemptResult(
                channel=channel_id,
                success=success,
                error_code=None if success else "send_failed",
                retryable=not success,
                latency_ms=int((time.monotonic() - started_at) * 1000),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - one channel failure cannot stop later channels
            log_safe_exception(
                dispatch_logger,
                "Notification channel delivery failed",
                exc,
                error_code=(
                    "pipeline_notification_channel_failed"
                    if aggregate
                    else "notification_channel_delivery_failed"
                ),
                context={"channel": channel_id},
                exception_redaction_values=(
                    ()
                    if not isinstance(channel, NotificationChannel)
                    else None
                ),
            )
            return ChannelAttemptResult(
                channel=channel_id,
                success=False,
                error_code="exception",
                retryable=True,
                latency_ms=int((time.monotonic() - started_at) * 1000),
                diagnostics=sanitize_exception_chain(
                    exc,
                    redact_diagnostics=not isinstance(
                        channel,
                        NotificationChannel,
                    ),
                ),
            )

    return _send


def _context_attempt_sender(
    channel_id: str,
    send: Callable[[], Any],
) -> Callable[[], Any]:
    """Normalize context delivery without isolating sender exceptions."""

    def _send():
        """Execute context delivery while preserving exception ordering."""

        ChannelAttemptResult = get_dispatch_ports().facade.ChannelAttemptResult

        started_at = time.monotonic()
        result = send()
        if isinstance(result, ChannelAttemptResult):
            return result
        success = bool(result)
        return ChannelAttemptResult(
            channel=channel_id,
            success=success,
            error_code=None if success else "send_failed",
            retryable=not success,
            latency_ms=int((time.monotonic() - started_at) * 1000),
        )

    return _send


def _execute_attempt(
    service: Any,
    *,
    channel: Any,
    channel_id: str,
    send: Callable[[], Any],
    aggregate: Optional[_AggregateDispatchContext],
    target_results: Optional[List[Any]] = None,
) -> _DispatchAttemptRecord:
    """Execute one channel through optional Pipeline idempotency fencing."""

    sender = (
        _context_attempt_sender(channel_id, send)
        if channel_id == "__context__"
        else _safe_attempt_sender(
            service,
            channel,
            channel_id,
            send,
            aggregate=aggregate is not None,
        )
    )
    if aggregate is None:
        attempt = sender()
        reused = False
    else:
        attempt, reused = aggregate.execute_attempt(channel_id, sender)
    return _DispatchAttemptRecord(
        attempt=attempt,
        target_results=target_results,
        reused=reused,
    )


def _get_md2img_hint(service: Any, config: Any = None) -> str:
    """Return the installation hint for the configured image engine."""

    config = config or getattr(service, "_config", None)
    engine = getattr(config, "md2img_engine", "wkhtmltoimage")
    return (
        "npm i -g markdown-to-file"
        if engine == "markdown-to-file"
        else "wkhtmltopdf (apt install wkhtmltopdf / brew install wkhtmltopdf)"
    )


def _full_report_image_channel_ids(
    service: Any,
    target_channels: List[Any],
    *,
    aggregate: bool,
) -> tuple[str, ...]:
    """Return routed channels that require the shared full-report image."""

    NotificationChannel = get_dispatch_ports().facade.NotificationChannel

    return tuple(
        channel_id
        for channel_id in (
            _channel_id(channel) for channel in target_channels
        )
        if channel_id in service._markdown_to_image_channels
        and channel_id
        not in {
            NotificationChannel.NTFY.value,
            NotificationChannel.GOTIFY.value,
            *(
                (NotificationChannel.WECHAT.value,)
                if aggregate
                else ()
            ),
        }
    )


def _prepare_full_report_image(
    service: Any,
    content: str,
    target_channels: List[Any],
    *,
    aggregate: bool,
) -> _ImagePreparationOutcome:
    """Render the shared full-report image required by routed channels."""

    ports = get_dispatch_ports()
    facade = ports.facade
    logger = facade.logger
    log_safe_exception = facade.log_safe_exception
    sanitize_exception_chain = facade.sanitize_exception_chain
    channels_needing_image = _full_report_image_channel_ids(
        service,
        target_channels,
        aggregate=aggregate,
    )
    if not channels_needing_image:
        return _ImagePreparationOutcome()

    try:
        image_bytes = ports.image_builder(
            content,
            max_chars=service._markdown_to_image_max_chars,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - affected image channels become structured failures while other completed or routable attempts remain visible
        log_safe_exception(
            logger,
            "Notification image preparation failed",
            exc,
            error_code="notification_image_preparation_failed",
            context={"channels": channels_needing_image},
        )
        return _ImagePreparationOutcome(
            failed_channel_ids=frozenset(channels_needing_image),
            diagnostics=sanitize_exception_chain(exc),
        )
    if image_bytes:
        logger.info(
            "Markdown converted to an image for channels: %s",
            _sanitize_dispatch_log_value(list(channels_needing_image)),
        )
    else:
        logger.warning(
            "Markdown-to-image conversion failed; falling back to text. "
            "Check MARKDOWN_TO_IMAGE_CHANNELS and install %s",
            _sanitize_dispatch_log_value(_get_md2img_hint(service)),
        )
    return _ImagePreparationOutcome(image_bytes=image_bytes)


def _should_use_image_for_channel(
    service: Any,
    channel: Any,
    image_bytes: Optional[bytes],
) -> bool:
    """Apply the facade image policy for real and compatibility notifiers."""

    facade = get_dispatch_ports().facade
    NotificationChannel = facade.NotificationChannel
    WECHAT_IMAGE_MAX_BYTES = facade.WECHAT_IMAGE_MAX_BYTES
    logger = facade.logger

    configured = (
        channel.value
        in getattr(service, "_markdown_to_image_channels", set())
        and image_bytes is not None
    )
    if (
        configured
        and channel == NotificationChannel.WECHAT
        and len(image_bytes) > WECHAT_IMAGE_MAX_BYTES
    ):
        logger.warning(
            "WeCom image exceeds the size limit (%s bytes); falling back "
            "to Markdown text",
            _sanitize_dispatch_log_value(len(image_bytes)),
        )
        return False
    return configured


def _use_image_for_channel(
    service: Any,
    channel: Any,
    image_bytes: Optional[bytes],
) -> bool:
    """Honor the facade patch seam with a compatibility fallback."""

    image_policy = getattr(service, "_should_use_image_for_channel", None)
    if callable(image_policy):
        return bool(image_policy(channel, image_bytes))
    return _should_use_image_for_channel(service, channel, image_bytes)


def _send_to_static_channel(
    service: Any,
    channel: Any,
    content: str,
    *,
    image_bytes: Optional[bytes],
    email_stock_codes: Optional[List[str]],
    email_send_to_all: bool,
    route_type: Optional[str],
) -> bool:
    """Send one built-in channel through the canonical static policy."""

    facade = get_dispatch_ports().facade
    NotificationChannel = facade.NotificationChannel
    logger = facade.logger

    use_image = _use_image_for_channel(
        service,
        channel,
        image_bytes,
    )
    if channel == NotificationChannel.WECHAT:
        if use_image:
            return service._send_wechat_image(image_bytes)
        return service.send_to_wechat(content)
    if channel == NotificationChannel.FEISHU:
        if getattr(service, "_feishu_send_as_file", False) and route_type == "report":
            date_str = datetime.now().strftime("%Y%m%d")
            filepath = service.save_report_to_file(
                content,
                filename=f"report_{date_str}.md",
            )
            return service.send_feishu_file(filepath)
        return service.send_to_feishu(content)
    if channel == NotificationChannel.DINGTALK:
        return service.send_to_dingtalk(content)
    if channel == NotificationChannel.TELEGRAM:
        if use_image:
            return service._send_telegram_photo(image_bytes)
        return service.send_to_telegram(content)
    if channel == NotificationChannel.EMAIL:
        receivers = None
        stock_email_groups = getattr(service, "_stock_email_groups", [])
        if email_send_to_all and stock_email_groups:
            receivers = service.get_all_email_receivers()
        elif email_stock_codes and stock_email_groups:
            receivers = service.get_receivers_for_stocks(email_stock_codes)
        if use_image:
            return service._send_email_with_inline_image(
                image_bytes,
                receivers=receivers,
            )
        return service.send_to_email(content, receivers=receivers)
    if channel == NotificationChannel.PUSHOVER:
        return service.send_to_pushover(content)
    if channel == NotificationChannel.NTFY:
        return service.send_to_ntfy(content)
    if channel == NotificationChannel.GOTIFY:
        return service.send_to_gotify(content)
    if channel == NotificationChannel.PUSHPLUS:
        return service.send_to_pushplus(content)
    if channel == NotificationChannel.SERVERCHAN3:
        return service.send_to_serverchan3(content)
    if channel == NotificationChannel.CUSTOM:
        if use_image:
            return service._send_custom_webhook_image(
                image_bytes,
                fallback_content=content,
            )
        return service.send_to_custom(content)
    if channel == NotificationChannel.DISCORD:
        return service.send_to_discord(content)
    if channel == NotificationChannel.SLACK:
        if use_image:
            return service._send_slack_image(
                image_bytes,
                fallback_content=content,
            )
        return service.send_to_slack(content)
    if channel == NotificationChannel.ASTRBOT:
        return service.send_to_astrbot(content)
    logger.warning(
        "Unsupported notification channel: %s",
        _sanitize_dispatch_log_value(channel),
    )
    return False


def _static_channel_sender(service: Any) -> Callable[..., bool]:
    """Honor the facade static-sender patch seam when it is present."""

    sender = getattr(service, "_send_to_static_channel", None)
    if callable(sender):
        return sender

    def _send(channel: Any, content: str, **kwargs: Any) -> bool:
        """Call the module static sender for compatibility notifiers."""

        return _send_to_static_channel(
            service,
            channel,
            content,
            **kwargs,
        )

    return _send


def _aggregate_static_attempts(
    service: Any,
    channel: Any,
    content: str,
    *,
    image_bytes: Optional[bytes],
    aggregate: _AggregateDispatchContext,
) -> List[tuple[str, Optional[List[Any]], Callable[[], Any]]]:
    """Build aggregate channel attempts without leaking sender policy to Pipeline."""

    ports = get_dispatch_ports()
    normalize_stock_code = ports.normalize_stock_code
    ReportType = ports.report_type_cls
    NotificationChannel = ports.facade.NotificationChannel

    channel_id = channel.value
    results = aggregate.results
    report_type = aggregate.report_type
    aggregate_logger = logging.getLogger("src.core.pipeline")

    if channel == NotificationChannel.WECHAT:
        def _send_wechat_report():
            """Send the aggregate-specific condensed WeCom report."""

            if report_type == ReportType.BRIEF:
                dashboard_content = service.generate_brief_report(results)
            else:
                dashboard_content = service.generate_wechat_dashboard(results)
            aggregate_logger.info(
                "WeCom dashboard prepared: character_count=%s",
                _sanitize_dispatch_log_value(len(dashboard_content)),
            )
            wechat_image_bytes = None
            if channel_id in service._markdown_to_image_channels:
                wechat_image_bytes = get_dispatch_ports().image_builder(
                    dashboard_content,
                    max_chars=service._markdown_to_image_max_chars,
                )
                if wechat_image_bytes is None:
                    aggregate_logger.warning(
                        "WeCom Markdown-to-image conversion failed; falling "
                        "back to text. Check MARKDOWN_TO_IMAGE_CHANNELS and "
                        "install %s",
                        _sanitize_dispatch_log_value(
                            _get_md2img_hint(service, aggregate.config)
                        ),
                    )
            if _use_image_for_channel(
                service,
                channel,
                wechat_image_bytes,
            ):
                return service._send_wechat_image(wechat_image_bytes)
            return service.send_to_wechat(dashboard_content)

        return [(channel_id, None, _send_wechat_report)]

    if channel == NotificationChannel.FEISHU:
        def _send_feishu_report():
            """Send aggregate Feishu content as text or a dashboard file."""

            if getattr(service, "_feishu_send_as_file", False):
                date_str = datetime.now().strftime("%Y%m%d")
                filepath = service.save_report_to_file(
                    content,
                    filename=f"dashboard_{date_str}.md",
                )
                return service.send_feishu_file(filepath)
            return service.send_to_feishu(content)

        return [(channel_id, None, _send_feishu_report)]

    if channel == NotificationChannel.EMAIL:
        stock_email_groups = (
            getattr(aggregate.config, "stock_email_groups", []) or []
        )
        if stock_email_groups:
            code_to_emails: dict[str, Optional[List[str]]] = {}
            for result in results:
                if result.code in code_to_emails:
                    continue
                canonical = normalize_stock_code(result.code)
                emails: List[str] = []
                for stocks, emails_list in stock_email_groups:
                    if canonical in stocks:
                        emails.extend(emails_list)
                code_to_emails[result.code] = (
                    list(dict.fromkeys(emails)) if emails else None
                )
            emails_to_results: dict[Optional[tuple[str, ...]], List[Any]] = (
                defaultdict(list)
            )
            for result in results:
                receivers = code_to_emails.get(result.code)
                key = tuple(receivers) if receivers else None
                emails_to_results[key].append(result)

            attempts = []
            for key, group_results in emails_to_results.items():
                receivers = list(key) if key is not None else None
                label = (
                    f"{channel_id}:{','.join(receivers)}"
                    if receivers
                    else f"{channel_id}:default"
                )

                def _send_email_group(
                    group_results=group_results,
                    receivers=receivers,
                ):
                    """Render and send one aggregate email receiver group."""

                    group_report = aggregate.render_aggregate(
                        group_results,
                        report_type,
                    )
                    group_image_bytes = None
                    if channel_id in service._markdown_to_image_channels:
                        group_image_bytes = get_dispatch_ports().image_builder(
                            group_report,
                            max_chars=service._markdown_to_image_max_chars,
                        )
                    if _use_image_for_channel(
                        service,
                        channel,
                        group_image_bytes,
                    ):
                        return service._send_email_with_inline_image(
                            group_image_bytes,
                            receivers=receivers,
                        )
                    return service.send_to_email(
                        group_report,
                        receivers=receivers,
                    )

                attempts.append((label, group_results, _send_email_group))
            return attempts

        def _send_email_report():
            """Send an ungrouped aggregate email report."""

            if _use_image_for_channel(service, channel, image_bytes):
                return service._send_email_with_inline_image(image_bytes)
            return service.send_to_email(content)

        return [(channel_id, None, _send_email_report)]

    if channel == NotificationChannel.SLACK:
        def _send_slack_report():
            """Send aggregate Slack content with its bot-image fallback."""

            use_image = _use_image_for_channel(
                service,
                channel,
                image_bytes,
            )
            if (
                use_image
                and service._slack_bot_token
                and service._slack_channel_id
            ):
                return service._send_slack_image(
                    image_bytes,
                    fallback_content=content,
                )
            return service.send_to_slack(content)

        return [(channel_id, None, _send_slack_report)]

    static_sender = _static_channel_sender(service)
    return [
        (
            channel_id,
            None,
            lambda: static_sender(
                channel,
                content,
                image_bytes=image_bytes,
                email_stock_codes=[str(result.code) for result in results],
                email_send_to_all=False,
                route_type="report",
            ),
        )
    ]


def _dispatch_target_attempts(
    service: Any,
    content: str,
    target_channels: List[Any],
    *,
    email_stock_codes: Optional[List[str]],
    email_send_to_all: bool,
    route_type: Optional[str],
    severity: Optional[str],
    aggregate: Optional[_AggregateDispatchContext],
) -> List[_DispatchAttemptRecord]:
    """Prepare payloads and isolate each routed target attempt."""

    facade = get_dispatch_ports().facade
    ChannelDetector = facade.ChannelDetector
    NotificationChannel = facade.NotificationChannel
    logger = facade.logger

    image_preparation = _prepare_full_report_image(
        service,
        content,
        target_channels,
        aggregate=aggregate is not None,
    )
    image_bytes = image_preparation.image_bytes
    channel_names = ", ".join(
        ChannelDetector.get_channel_name(channel)
        if isinstance(channel, NotificationChannel)
        else channel.display_name
        for channel in target_channels
    )
    logger.info(
        "Sending notification to %s channels: %s",
        _sanitize_dispatch_log_value(len(target_channels)),
        _sanitize_dispatch_log_value(channel_names),
    )

    records: List[_DispatchAttemptRecord] = []
    for channel in target_channels:
        channel_id = _channel_id(channel)
        if channel_id in image_preparation.failed_channel_ids:
            ChannelAttemptResult = facade.ChannelAttemptResult

            def _image_preparation_failure(
                channel_id=channel_id,
                diagnostics=image_preparation.diagnostics,
            ):
                """Return one retryable shared-image preparation failure."""

                return ChannelAttemptResult(
                    channel=channel_id,
                    success=False,
                    error_code="image_preparation_failed",
                    retryable=True,
                    diagnostics=diagnostics,
                )

            records.append(
                _execute_attempt(
                    service,
                    channel=channel,
                    channel_id=channel_id,
                    send=_image_preparation_failure,
                    aggregate=aggregate,
                )
            )
            continue
        if isinstance(channel, NotificationChannel):
            if aggregate is None:
                static_sender = _static_channel_sender(service)
                attempts = [
                    (
                        channel_id,
                        None,
                        lambda channel=channel: static_sender(
                            channel,
                            content,
                            image_bytes=image_bytes,
                            email_stock_codes=email_stock_codes,
                            email_send_to_all=email_send_to_all,
                            route_type=route_type,
                        ),
                    )
                ]
            else:
                try:
                    attempts = _aggregate_static_attempts(
                        service,
                        channel,
                        content,
                        image_bytes=image_bytes,
                        aggregate=aggregate,
                    )
                except Exception as exc:  # broad-exception: fallback_recorded - malformed channel preparation becomes one isolated attempt
                    ChannelAttemptResult = facade.ChannelAttemptResult
                    log_safe_exception = facade.log_safe_exception
                    sanitize_exception_chain = facade.sanitize_exception_chain

                    log_safe_exception(
                        logger,
                        "Notification channel preparation failed",
                        exc,
                        error_code="notification_channel_preparation_failed",
                        context={"channel": channel_id},
                    )
                    preparation_diagnostics = sanitize_exception_chain(exc)

                    def _preparation_failure(
                        diagnostics=preparation_diagnostics,
                    ):
                        """Return one structured channel preparation failure."""

                        return ChannelAttemptResult(
                            channel=channel_id,
                            success=False,
                            error_code="exception",
                            retryable=True,
                            diagnostics=diagnostics,
                        )

                    attempts = [
                        (
                            channel_id,
                            None,
                            _preparation_failure,
                        )
                    ]
            for label, target_results, send in attempts:
                records.append(
                    _execute_attempt(
                        service,
                        channel=channel,
                        channel_id=label,
                        send=send,
                        aggregate=aggregate,
                        target_results=target_results,
                    )
                )
        else:
            records.append(
                _execute_attempt(
                    service,
                    channel=channel,
                    channel_id=channel_id,
                    send=lambda channel=channel, channel_id=channel_id: (
                        service._send_to_plugin_channel(
                            channel,
                            content,
                            image_bytes=(
                                image_bytes
                                if channel_id
                                in service._markdown_to_image_channels
                                else None
                            ),
                            email_stock_codes=email_stock_codes,
                            route_type=route_type,
                            severity=severity,
                        )
                    ),
                    aggregate=aggregate,
                )
            )
    return records


def _release_noise_reservation(service: Any, decision: Any) -> None:
    """Best-effort release for a noise-control in-flight reservation."""

    release_noise = getattr(service, "release_noise_control", None)
    if not callable(release_noise):
        return
    try:
        release_noise(decision)
    except Exception as exc:  # broad-exception: fallback_recorded - cleanup failures are safely logged without changing the dispatch outcome
        facade = get_dispatch_ports().facade
        logger = facade.logger
        log_safe_exception = facade.log_safe_exception

        log_safe_exception(
            logger,
            "Notification noise reservation release failed",
            exc,
            error_code="notification_noise_reservation_release_failed",
            level=logging.WARNING,
        )


def _finalize_noise_control(
    service: Any,
    decision: Any,
    *,
    static_success: bool,
) -> None:
    """Finalize noise state without invalidating a completed delivery."""

    if decision is None:
        return
    if static_success:
        record_noise = getattr(service, "record_noise_control", None)
        if callable(record_noise):
            try:
                record_noise(decision)
                return
            except Exception as exc:  # broad-exception: fallback_recorded - a successful delivery remains committed when noise persistence fails
                facade = get_dispatch_ports().facade
                logger = facade.logger
                log_safe_exception = facade.log_safe_exception

                log_safe_exception(
                    logger,
                    "Notification noise finalization failed",
                    exc,
                    error_code="notification_noise_finalization_failed",
                    context={"action": "record"},
                )
    _release_noise_reservation(service, decision)


def _dispatch_with_results_under_lease(
    service: Any,
    content: str,
    *,
    email_stock_codes: Optional[List[str]],
    email_send_to_all: bool,
    route_type: Optional[str],
    severity: Optional[str],
    dedup_key: Optional[str],
    cooldown_key: Optional[str],
    aggregate: Optional[_AggregateDispatchContext] = None,
    retained_target_channels: Optional[List[Any]] = None,
    notification_available: Optional[bool] = None,
) -> _DispatchExecution:
    """Run the canonical route/noise/isolation/mapping/aggregation policy."""

    facade = get_dispatch_ports().facade
    NotificationDispatchResult = facade.NotificationDispatchResult
    _ROUTABLE_NOTIFICATION_CHANNELS = facade.ROUTABLE_NOTIFICATION_CHANNELS
    _available_notification_channel_snapshot = (
        facade.available_notification_channel_snapshot
    )
    logger = facade.logger
    log_safe_exception = facade.log_safe_exception

    if notification_available is False:
        return _DispatchExecution(
            result=NotificationDispatchResult(
                dispatched=False,
                success=False,
                status="no_channel",
                message="notification service unavailable",
            ),
        )

    records: List[_DispatchAttemptRecord] = []
    context_available = False
    has_context_channel = getattr(service, "_has_context_channel", None)
    if callable(has_context_channel):
        try:
            context_available = bool(has_context_channel())
        except Exception as exc:  # broad-exception: optional_metadata - context availability only refines diagnostics
            log_safe_exception(
                logger,
                "Context notification availability check failed",
                exc,
                error_code="notification_context_availability_failed",
            )

    context_record = _execute_attempt(
        service,
        channel="__context__",
        channel_id="__context__",
        send=lambda: service.send_to_context(content),
        aggregate=aggregate,
    )
    context_success = bool(context_record.attempt.success)
    if context_success or (aggregate is not None and context_available):
        records.append(context_record)

    should_broadcast = getattr(
        service,
        "should_broadcast_static_channels",
        None,
    )
    if callable(should_broadcast) and not should_broadcast():
        if context_success:
            logger.info(
                "Notification delivered through contextual reply; static "
                "channels skipped"
            )
            result = NotificationDispatchResult(
                dispatched=True,
                success=True,
                status="sent",
                channel_results=[context_record.attempt],
            )
        else:
            logger.warning(
                "Interactive contextual delivery failed; static channels skipped"
            )
            if not context_available:
                records.append(context_record)
            result = NotificationDispatchResult(
                dispatched=True,
                success=False,
                status="all_failed",
                channel_results=[context_record.attempt],
                message=(
                    "interactive context delivery failed; static channels skipped"
                ),
            )
        return _DispatchExecution(
            result=result,
            records=records,
            context_attempted=context_available,
            context_only=True,
        )

    if retained_target_channels is not None:
        available_channels = list(retained_target_channels)
        target_channels = list(retained_target_channels)
    else:
        application_services = getattr(service, "_application_services", None)
        plugin_snapshot = (
            application_services.notification_channel_snapshot()
            if application_services is not None
            else ()
        )
        available_plugins = _available_notification_channel_snapshot(
            plugin_snapshot
        )
        available_static = service.get_available_channels()
        available_channels = [*available_static, *available_plugins]
        allowed_channel_ids = tuple(
            dict.fromkeys(
                (
                    *_ROUTABLE_NOTIFICATION_CHANNELS,
                    *(channel.channel_id for channel in plugin_snapshot),
                )
            )
        )
        if hasattr(service, "_notification_runtime_lock"):
            target_channels = service.get_channels_for_route(
                route_type,
                channels=available_channels,
                allowed_channel_ids=allowed_channel_ids,
            )
        else:
            target_channels = service.get_channels_for_route(
                route_type,
                channels=available_channels,
            )

    if not available_channels or not target_channels:
        if context_success:
            result = NotificationDispatchResult(
                dispatched=True,
                success=True,
                status="sent",
                channel_results=[context_record.attempt],
            )
        elif aggregate is not None and context_available:
            result = NotificationDispatchResult(
                dispatched=True,
                success=False,
                status="all_failed",
                channel_results=[context_record.attempt],
                message=(
                    "context delivery failed and no static channel was routed"
                ),
            )
        else:
            message = (
                "notification service unavailable"
                if not available_channels
                else f"notification route {route_type} has no configured channel"
            )
            result = NotificationDispatchResult(
                dispatched=False,
                success=False,
                status="no_channel",
                message=message,
            )
        return _DispatchExecution(
            result=result,
            records=records,
            context_attempted=context_available,
            target_channel_count=len(target_channels),
        )

    static_scope_reentry = aggregate.scope_started() if aggregate else False
    noise_decision = None
    if not static_scope_reentry:
        evaluate_noise = getattr(service, "evaluate_noise_control", None)
        noise_decision = (
            evaluate_noise(
                content,
                route_type=route_type,
                severity=severity,
                dedup_key=dedup_key,
                cooldown_key=cooldown_key,
            )
            if callable(evaluate_noise)
            else None
        )
        if noise_decision is not None and not noise_decision.should_send:
            logger.info("Notification noise policy suppressed delivery")
            if context_success:
                result = NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="sent",
                    channel_results=[context_record.attempt],
                    message=noise_decision.message,
                )
            elif aggregate is not None and context_available:
                result = NotificationDispatchResult(
                    dispatched=True,
                    success=False,
                    status="all_failed",
                    channel_results=[context_record.attempt],
                    message=noise_decision.message,
                )
            else:
                result = NotificationDispatchResult(
                    dispatched=False,
                    success=False,
                    status="noise_suppressed",
                    message=noise_decision.message,
                )
            return _DispatchExecution(
                result=result,
                records=records,
                context_attempted=context_available,
                static_suppressed=True,
                noise_reason_code=getattr(
                    noise_decision,
                    "reason_code",
                    None,
                ),
                target_channel_count=len(target_channels),
            )
        if aggregate is not None:
            aggregate.mark_scope_started()

    try:
        records.extend(
            _dispatch_target_attempts(
                service,
                content,
                target_channels,
                email_stock_codes=email_stock_codes,
                email_send_to_all=email_send_to_all,
                route_type=route_type,
                severity=severity,
                aggregate=aggregate,
            )
        )
    except Exception:
        if not static_scope_reentry and noise_decision is not None:
            _release_noise_reservation(service, noise_decision)
        if aggregate is not None and not static_scope_reentry:
            aggregate.clear_scope_started()
        raise

    static_records = [
        record
        for record in records
        if record.attempt.channel != "__context__"
    ]
    static_success = any(record.attempt.success for record in static_records)
    if not static_scope_reentry:
        _finalize_noise_control(
            service,
            noise_decision,
            static_success=static_success,
        )

    if (
        aggregate is not None
        and not static_scope_reentry
        and not static_success
    ):
        aggregate.clear_scope_started()

    successes = sum(bool(record.attempt.success) for record in records)
    failures = sum(not bool(record.attempt.success) for record in records)
    success = successes > 0
    if (
        aggregate is not None
        and success
        and failures
    ):
        status = "partial_failed"
    elif (
        aggregate is None
        and static_success
        and any(not record.attempt.success for record in static_records)
    ):
        status = "partial_failed"
    elif success:
        status = "sent"
    else:
        status = "all_failed"
    logger.info(
        "Notification dispatch complete: success=%d failed=%d",
        successes,
        failures,
    )
    return _DispatchExecution(
        result=NotificationDispatchResult(
            dispatched=bool(records),
            success=success,
            status=status,
            channel_results=[record.attempt for record in records],
        ),
        records=records,
        context_attempted=context_available,
        target_channel_count=len(target_channels),
    )


def dispatch_aggregate_with_results(
    service: Any,
    content: str,
    *,
    results: List[Any],
    report_type: Any,
    config: Any,
    render_aggregate: Callable[[List[Any], Any], str],
    execute_attempt: Callable[[str, Callable[[], Any]], tuple[Any, bool]],
    scope_started: Callable[[], bool],
    mark_scope_started: Callable[[], None],
    clear_scope_started: Callable[[], None],
    dedup_key: str,
    cooldown_key: str,
) -> _DispatchExecution:
    """Dispatch an aggregate report through the canonical notification owner."""

    _ensure_notification_runtime = (
        get_dispatch_ports().facade.ensure_notification_runtime
    )

    application_services = None
    if hasattr(service, "_notification_runtime_lock"):
        application_services, _registry = _ensure_notification_runtime(service)
    aggregate = _AggregateDispatchContext(
        results=results,
        report_type=report_type,
        config=config,
        render_aggregate=render_aggregate,
        execute_attempt=execute_attempt,
        scope_started=scope_started,
        mark_scope_started=mark_scope_started,
        clear_scope_started=clear_scope_started,
    )
    dispatch_lease = (
        application_services.notification_dispatch()
        if application_services is not None
        else nullcontext()
    )
    with dispatch_lease:
        delivery_snapshot = getattr(
            service,
            "_notification_delivery_snapshot",
            None,
        )
        snapshot_context = (
            delivery_snapshot("report")
            if callable(delivery_snapshot)
            else nullcontext(None)
        )
        with snapshot_context as target_snapshot:
            notification_available = None
            if not callable(delivery_snapshot):
                is_available = getattr(service, "is_available", None)
                if callable(is_available):
                    notification_available = bool(is_available())
            retained_target_channels = (
                list(target_snapshot)
                if target_snapshot is not None
                else None
            )
            return _dispatch_with_results_under_lease(
                service,
                content,
                email_stock_codes=[
                    str(result.code) for result in results
                ],
                email_send_to_all=False,
                route_type="report",
                severity="info",
                dedup_key=dedup_key,
                cooldown_key=cooldown_key,
                aggregate=aggregate,
                retained_target_channels=retained_target_channels,
                notification_available=notification_available,
            )


class _DispatchMethods:
    def _should_use_image_for_channel(
        self, channel: NotificationChannel, image_bytes: Optional[bytes]
    ) -> bool:
        """
        Decide whether to send as image for the given channel (Issue #289).

        Fallback rules (send as Markdown text instead of image):
        - image_bytes is None: conversion failed / imgkit not installed / content over max_chars
        - WeChat: image exceeds ~2MB limit
        """
        if channel.value not in self._markdown_to_image_channels or image_bytes is None:
            return False
        if channel == NotificationChannel.WECHAT and len(image_bytes) > WECHAT_IMAGE_MAX_BYTES:
            logger.warning(
                "企业微信图片超限 (%d bytes)，回退为 Markdown 文本发送",
                len(image_bytes),
            )
            return False
        return True

    @staticmethod
    def _sanitize_notification_diagnostics(text: Any) -> str:
        return sanitize_diagnostic_text(text)

    def _send_to_static_channel(
        self,
        channel: NotificationChannel,
        content: str,
        *,
        image_bytes: Optional[bytes],
        email_stock_codes: Optional[List[str]],
        email_send_to_all: bool,
        route_type: Optional[str] = None,
    ) -> bool:
        use_image = self._should_use_image_for_channel(channel, image_bytes)
        if channel == NotificationChannel.WECHAT:
            if use_image:
                return self._send_wechat_image(image_bytes)
            return self.send_to_wechat(content)
        if channel == NotificationChannel.FEISHU:
            if getattr(self, "_feishu_send_as_file", False) and route_type == "report":
                date_str = datetime.now().strftime('%Y%m%d')
                filepath = self.save_report_to_file(
                    content, filename=f"report_{date_str}.md"
                )
                return self.send_feishu_file(filepath)
            return self.send_to_feishu(content)
        if channel == NotificationChannel.DINGTALK:
            return self.send_to_dingtalk(content)
        if channel == NotificationChannel.TELEGRAM:
            if use_image:
                return self._send_telegram_photo(image_bytes)
            return self.send_to_telegram(content)
        if channel == NotificationChannel.EMAIL:
            receivers = None
            if email_send_to_all and self._stock_email_groups:
                receivers = self.get_all_email_receivers()
            elif email_stock_codes and self._stock_email_groups:
                receivers = self.get_receivers_for_stocks(email_stock_codes)
            if use_image:
                return self._send_email_with_inline_image(image_bytes, receivers=receivers)
            return self.send_to_email(content, receivers=receivers)
        if channel == NotificationChannel.PUSHOVER:
            return self.send_to_pushover(content)
        if channel == NotificationChannel.NTFY:
            return self.send_to_ntfy(content)
        if channel == NotificationChannel.GOTIFY:
            return self.send_to_gotify(content)
        if channel == NotificationChannel.PUSHPLUS:
            return self.send_to_pushplus(content)
        if channel == NotificationChannel.SERVERCHAN3:
            return self.send_to_serverchan3(content)
        if channel == NotificationChannel.CUSTOM:
            if use_image:
                return self._send_custom_webhook_image(image_bytes, fallback_content=content)
            return self.send_to_custom(content)
        if channel == NotificationChannel.DISCORD:
            return self.send_to_discord(content)
        if channel == NotificationChannel.SLACK:
            if use_image:
                return self._send_slack_image(image_bytes, fallback_content=content)
            return self.send_to_slack(content)
        if channel == NotificationChannel.ASTRBOT:
            return self.send_to_astrbot(content)
        logger.warning(f"不支持的通知渠道: {channel}")
        return False

    def _send_to_plugin_channel(
        self,
        channel: _NotificationChannelSnapshot,
        content: str,
        *,
        image_bytes: Optional[bytes],
        email_stock_codes: Optional[List[str]],
        route_type: Optional[str],
        severity: Optional[str],
    ) -> ChannelAttemptResult:
        """Invoke and map one adapter into the core attempt contract."""

        started_at = time.monotonic()
        try:
            adapter_result = channel.adapter.send(
                _NotificationRequest(
                    content=content,
                    route_type=route_type,
                    severity=severity,
                    image_bytes=image_bytes,
                    stock_codes=tuple(email_stock_codes or ()),
                    metadata={},
                )
            )
            if type(adapter_result) is not _NotificationAdapterResult:
                logger.warning(
                    "Notification channel adapter returned an invalid result "
                    "error_code=notification_adapter_result_invalid channel=%s",
                    channel.channel_id,
                )
                adapter_result = _NotificationAdapterResult(
                    success=False,
                    error_code="notification_adapter_result_invalid",
                )
            success = adapter_result.success
            return ChannelAttemptResult(
                channel=channel.channel_id,
                success=success,
                error_code=_normalize_notification_adapter_error_code(
                    adapter_result.error_code,
                    success=success,
                ),
                retryable=adapter_result.retryable if not success else False,
                latency_ms=int((time.monotonic() - started_at) * 1000),
                diagnostics=(
                    sanitize_diagnostic_text(adapter_result.diagnostics) or None
                ),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - one plugin adapter failure cannot stop later channels
            log_safe_exception(
                logger,
                "Notification channel delivery failed",
                exc,
                error_code="notification_channel_delivery_failed",
                context={"channel": channel.channel_id},
                exception_redaction_values=(),
            )
            return ChannelAttemptResult(
                channel=channel.channel_id,
                success=False,
                error_code="exception",
                retryable=True,
                latency_ms=int((time.monotonic() - started_at) * 1000),
                diagnostics=sanitize_exception_chain(
                    exc,
                    redact_diagnostics=True,
                ),
            )

    def send_with_results(
        self,
        content: str,
        email_stock_codes: Optional[List[str]] = None,
        email_send_to_all: bool = False,
        route_type: Optional[str] = None,
        severity: Optional[str] = None,
        dedup_key: Optional[str] = None,
        cooldown_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        """Send once while retaining every adapter in the routed snapshot."""

        application_services, _registry = _ensure_notification_runtime(self)
        with application_services.notification_dispatch():
            return self._send_with_results_under_lease(
                content,
                email_stock_codes=email_stock_codes,
                email_send_to_all=email_send_to_all,
                route_type=route_type,
                severity=severity,
                dedup_key=dedup_key,
                cooldown_key=cooldown_key,
            )

    def _send_with_results_under_lease(
        self,
        content: str,
        email_stock_codes: Optional[List[str]] = None,
        email_send_to_all: bool = False,
        route_type: Optional[str] = None,
        severity: Optional[str] = None,
        dedup_key: Optional[str] = None,
        cooldown_key: Optional[str] = None,
    ) -> NotificationDispatchResult:
        """
        Send a notification and return per-channel diagnostics.

        ``send()`` keeps the historical bool API and delegates here.

        Fallback rules (Markdown-to-image, Issue #289):
        - When image_bytes is None (conversion failed / imgkit not installed /
          content over max_chars): all channels configured for image will send
          as Markdown text instead.
        - When WeChat image exceeds ~2MB: that channel falls back to Markdown text.

        Args:
            content: 消息内容（Markdown 格式）
            email_stock_codes: 股票代码列表（可选，用于邮件渠道路由到对应分组邮箱，Issue #268）
            email_send_to_all: 邮件是否发往所有配置邮箱（用于大盘复盘等无股票归属的内容）
            route_type: 通知路由类型；None 保持旧行为，report/alert/system_error 按配置过滤静态渠道
            severity: 通知严重级别；未设置时按路由类型推断
            dedup_key: 可选稳定去重 key；未设置时使用内容 hash
            cooldown_key: 可选冷却 key；未设置时使用路由/级别默认 key

        Returns:
            Structured dispatch diagnostics.
        """
        context_success = self.send_to_context(content)
        if not self.should_broadcast_static_channels():
            if context_success:
                logger.info("已通过上下文会话完成推送，跳过静态通知渠道")
                return NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="sent",
                    channel_results=[ChannelAttemptResult(channel="__context__", success=True)],
                )
            logger.warning("交互式上下文推送失败，已跳过静态通知渠道")
            return NotificationDispatchResult(
                dispatched=True,
                success=False,
                status="all_failed",
                channel_results=[
                    ChannelAttemptResult(
                        channel="__context__",
                        success=False,
                        error_code="send_failed",
                        retryable=True,
                    )
                ],
                message="interactive context delivery failed; static channels skipped",
            )

        plugin_channel_snapshot = (
            self._application_services.notification_channel_snapshot()
        )
        available_plugin_channels = _available_notification_channel_snapshot(
            plugin_channel_snapshot
        )
        available_channels = [
            *self._available_channels,
            *available_plugin_channels,
        ]
        allowed_channel_ids = tuple(
            dict.fromkeys(
                (
                    *_ROUTABLE_NOTIFICATION_CHANNELS,
                    *(
                        channel.channel_id
                        for channel in plugin_channel_snapshot
                    ),
                )
            )
        )
        target_channels = self.get_channels_for_route(
            route_type,
            available_channels,
            allowed_channel_ids=allowed_channel_ids,
        )

        if not available_channels:
            if context_success:
                logger.info("已通过消息上下文渠道完成推送（无其他通知渠道）")
                return NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="sent",
                    channel_results=[ChannelAttemptResult(channel="__context__", success=True)],
                )
            logger.warning("通知服务不可用，跳过推送")
            return NotificationDispatchResult(
                dispatched=False,
                success=False,
                status="no_channel",
                message="notification service unavailable",
            )

        if not target_channels:
            if context_success:
                logger.info("已通过消息上下文渠道完成推送（路由后无其他通知渠道）")
                return NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="sent",
                    channel_results=[ChannelAttemptResult(channel="__context__", success=True)],
                )
            logger.warning("通知路由 %s 未命中任何已配置渠道，跳过静态通知渠道", route_type)
            return NotificationDispatchResult(
                dispatched=False,
                success=False,
                status="no_channel",
                message=f"notification route {route_type} has no configured channel",
            )

        noise_decision = self.evaluate_noise_control(
            content,
            route_type=route_type,
            severity=severity,
            dedup_key=dedup_key,
            cooldown_key=cooldown_key,
        )
        if not noise_decision.should_send:
            logger.info(noise_decision.message)
            status = "sent" if context_success else "noise_suppressed"
            results = [ChannelAttemptResult(channel="__context__", success=True)] if context_success else []
            return NotificationDispatchResult(
                dispatched=bool(context_success),
                success=bool(context_success),
                status=status,
                channel_results=results,
                message=noise_decision.message,
            )

        # Markdown to image (Issue #289): convert once if any channel needs it.
        # Per-channel decision via _should_use_image_for_channel (see send() docstring for fallback rules).
        image_bytes = None
        target_channel_ids = tuple(
            channel.value
            if isinstance(channel, NotificationChannel)
            else channel.channel_id
            for channel in target_channels
        )
        channels_needing_image = tuple(
            channel_id
            for channel_id in target_channel_ids
            if channel_id in self._markdown_to_image_channels
            and channel_id not in {
                NotificationChannel.NTFY.value,
                NotificationChannel.GOTIFY.value,
            }
        )
        if channels_needing_image:
            # Bound methods resolve free names against notification.py globals;
            # import the ports helper explicitly to keep the call site stable.
            from src.notification_parts.dispatch import get_dispatch_ports as _get_ports

            image_bytes = _get_ports().image_builder(
                content, max_chars=self._markdown_to_image_max_chars
            )
            if image_bytes:
                logger.info("Markdown 已转换为图片，将向 %s 发送图片",
                            list(channels_needing_image))
            elif channels_needing_image:
                engine = getattr(
                    self._config,
                    "md2img_engine",
                    "wkhtmltoimage",
                )
                hint = (
                    "npm i -g markdown-to-file" if engine == "markdown-to-file"
                    else "wkhtmltopdf (apt install wkhtmltopdf / brew install wkhtmltopdf)"
                )
                logger.warning(
                    "Markdown 转图片失败，将回退为文本发送。请检查 MARKDOWN_TO_IMAGE_CHANNELS 配置并安装 %s",
                    hint,
                )

        channel_names = ', '.join(
            ChannelDetector.get_channel_name(channel)
            if isinstance(channel, NotificationChannel)
            else channel.display_name
            for channel in target_channels
        )
        logger.info(f"正在向 {len(target_channels)} 个渠道发送通知：{channel_names}")

        success_count = 0
        fail_count = 0
        channel_results: List[ChannelAttemptResult] = []

        for channel in target_channels:
            channel_id = (
                channel.value
                if isinstance(channel, NotificationChannel)
                else channel.channel_id
            )
            started_at = time.monotonic()
            plugin_attempt = None
            try:
                if isinstance(channel, NotificationChannel):
                    result = self._send_to_static_channel(
                        channel,
                        content,
                        image_bytes=image_bytes,
                        email_stock_codes=email_stock_codes,
                        email_send_to_all=email_send_to_all,
                        route_type=route_type,
                    )
                    attempt_success = bool(result)
                    error_code = None if attempt_success else "send_failed"
                    retryable = not attempt_success
                    diagnostics = None
                else:
                    plugin_attempt = self._send_to_plugin_channel(
                        channel,
                        content,
                        image_bytes=(
                            image_bytes
                            if channel_id in self._markdown_to_image_channels
                            else None
                        ),
                        email_stock_codes=email_stock_codes,
                        route_type=route_type,
                        severity=severity,
                    )
                    attempt_success = plugin_attempt.success
                    error_code = plugin_attempt.error_code
                    retryable = plugin_attempt.retryable
                    diagnostics = plugin_attempt.diagnostics
                latency_ms = (
                    plugin_attempt.latency_ms
                    if plugin_attempt is not None
                    else int((time.monotonic() - started_at) * 1000)
                )

                if attempt_success:
                    success_count += 1
                else:
                    fail_count += 1
                channel_results.append(
                    plugin_attempt
                    or ChannelAttemptResult(
                        channel=channel_id,
                        success=attempt_success,
                        error_code=error_code,
                        retryable=retryable,
                        latency_ms=latency_ms,
                        diagnostics=diagnostics,
                    )
                )

            except Exception as exc:  # broad-exception: fallback_recorded - keep other notification channels running
                log_safe_exception(
                    logger,
                    "Notification channel delivery failed",
                    exc,
                    error_code="notification_channel_delivery_failed",
                    context={"channel": channel_id},
                    exception_redaction_values=(
                        ()
                        if not isinstance(channel, NotificationChannel)
                        else None
                    ),
                )
                fail_count += 1
                channel_results.append(
                    ChannelAttemptResult(
                        channel=channel_id,
                        success=False,
                        error_code="exception",
                        retryable=True,
                        latency_ms=int((time.monotonic() - started_at) * 1000),
                        diagnostics=sanitize_exception_chain(
                            exc,
                            redact_diagnostics=not isinstance(
                                channel,
                                NotificationChannel,
                            ),
                        ),
                    )
                )

        logger.info(f"通知发送完成：成功 {success_count} 个，失败 {fail_count} 个")
        if success_count > 0:
            self.record_noise_control(noise_decision)
        else:
            self.release_noise_control(noise_decision)
        success = success_count > 0 or context_success
        if success_count > 0 and fail_count > 0:
            status = "partial_failed"
        elif success_count > 0 or context_success:
            status = "sent"
        else:
            status = "all_failed"
        if context_success:
            channel_results.insert(0, ChannelAttemptResult(channel="__context__", success=True))
        return NotificationDispatchResult(
            dispatched=True,
            success=success,
            status=status,
            channel_results=channel_results,
        )

    def send(
        self,
        content: str,
        email_stock_codes: Optional[List[str]] = None,
        email_send_to_all: bool = False,
        route_type: Optional[str] = None,
        severity: Optional[str] = None,
        dedup_key: Optional[str] = None,
        cooldown_key: Optional[str] = None,
    ) -> bool:
        """
        统一发送接口 - 向所有已配置的渠道发送。

        Returns:
            是否至少有一个渠道发送成功
        """
        result = self.send_with_results(
            content,
            email_stock_codes=email_stock_codes,
            email_send_to_all=email_send_to_all,
            route_type=route_type,
            severity=severity,
            dedup_key=dedup_key,
            cooldown_key=cooldown_key,
        )
        return bool(result.success)

    def save_report_to_file(
        self,
        content: str,
        filename: Optional[str] = None
    ) -> str:
        """
        保存日报到本地文件

        Args:
            content: 日报内容
            filename: 文件名（可选，默认按日期生成）

        Returns:
            保存的文件路径
        """
        # Bound method: local import keeps Path out of the public facade globals.
        from pathlib import Path

        if filename is None:
            date_str = datetime.now().strftime('%Y%m%d')
            filename = f"report_{date_str}.md"

        # Ensure the 'reports' directory exists (using the project root's reports)
        reports_dir = Path(__file__).parent.parent / 'reports'
        reports_dir.mkdir(parents=True, exist_ok=True)

        filepath = reports_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"日报已保存到: {filepath}")
        return str(filepath)

    def save_and_send_feishu_file(
        self,
        content: str,
        filename: Optional[str] = None,
    ) -> bool:
        """
        Save report content to a local markdown file and upload it to Feishu.

        This is a convenience wrapper around :meth:`save_report_to_file` +
        :meth:`send_feishu_file`.

        Args:
            content: Report content (Markdown).
            filename: Optional file name; auto-generated from date when omitted.

        Returns:
            Whether the Feishu file upload succeeded.
        """
        filepath = self.save_report_to_file(content, filename=filename)
        logger.info("将上传文件到飞书: %s", filepath)
        return self.send_feishu_file(filepath)
