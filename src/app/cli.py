"""Command-line parsing and mode dispatch implementation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from types import FunctionType
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from src.config import Config
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from main import (
        __coordinate_service_runtime,
        __keep_service_runtime_alive,
        __run_schedule_mode,
        __run_service_only_mode,
        _run_analysis_with_runtime_scheduler_lock,
        _run_market_review_with_shared_lock,
        logger,
        resolve_index_stock_code_for_analysis,
        split_stock_list,
    )


CLI_DESCRIPTION = (
    "StockPulse: A-share / HK / US / JP / KR / TW intelligent stock analysis "
    "/ StockPulse：A股/港股/美股/日股/韩股/台股智能分析系统"
)

# Actionable config names for the no-LLM summary line (matches existing analyzer hint).
_NO_LLM_CONFIG_HINT = (
    "LITELLM_MODEL or a provider API key "
    "(e.g. GEMINI_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY)"
)


def clone_facade_function(
    function: FunctionType,
    facade_globals: Dict[str, Any],
    *,
    module_name: str,
    qualname: str,
) -> FunctionType:
    """Clone a moved CLI function with the legacy facade globals."""

    cloned = FunctionType(
        function.__code__,
        facade_globals,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__annotations__ = dict(function.__annotations__)
    cloned.__dict__.update(function.__dict__)
    cloned.__doc__ = function.__doc__
    cloned.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    cloned.__module__ = module_name
    cloned.__qualname__ = qualname
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


@dataclass
class CliRunSummary:
    """Compact end-of-run facts for human-readable CLI output."""

    ok_count: Optional[int] = None
    failed_count: Optional[int] = None
    report_paths: List[str] = field(default_factory=list)
    notifications: List[Tuple[str, str]] = field(default_factory=list)
    dry_run: bool = False
    no_llm: bool = False


class CliRunSummaryCapture:
    """Capture report paths and per-channel dispatch outcomes from a notifier."""

    def __init__(self) -> None:
        self.report_paths: List[str] = []
        self.channel_outcomes: List[Tuple[str, str]] = []
        self._restore: List[Tuple[Any, str, Any]] = []

    def install(self, notifier: Any) -> None:
        """Wrap notifier methods so summary data is collected without re-query."""

        if notifier is None:
            return

        original_save = getattr(notifier, "save_report_to_file", None)
        if callable(original_save):

            def save_report_to_file(*args, **kwargs):
                # Preserve positional/keyword call shape for production and tests.
                path = original_save(*args, **kwargs)
                if path:
                    self.report_paths.append(str(path))
                return path

            notifier.save_report_to_file = save_report_to_file
            self._restore.append((notifier, "save_report_to_file", original_save))

        original_send_with_results = getattr(notifier, "send_with_results", None)
        if callable(original_send_with_results):

            def send_with_results(*args, **kwargs):
                result = original_send_with_results(*args, **kwargs)
                self._record_dispatch_result(result)
                return result

            notifier.send_with_results = send_with_results
            self._restore.append(
                (notifier, "send_with_results", original_send_with_results)
            )

    def restore(self) -> None:
        """Undo notifier wrappers installed by :meth:`install`."""

        for target, name, original in reversed(self._restore):
            try:
                setattr(target, name, original)
            except Exception:  # broad-exception: cleanup - Best-effort restore of temporary notifier wrappers
                pass
        self._restore.clear()

    def _record_dispatch_result(self, result: Any) -> None:
        channel_results = getattr(result, "channel_results", None) or []
        for attempt in channel_results:
            channel = str(getattr(attempt, "channel", "") or "").strip()
            if not channel or channel == "__context__":
                continue
            status = "sent" if getattr(attempt, "success", False) else "failed"
            self.channel_outcomes.append((channel, status))


def _channel_display_name(channel: Any) -> str:
    """Return a short label for a notification channel enum or id."""

    try:
        from src.notification import ChannelDetector, NotificationChannel

        if isinstance(channel, NotificationChannel):
            return ChannelDetector.get_channel_name(channel)
    except Exception:  # broad-exception: cleanup - Best-effort channel display name fallback
        pass
    if hasattr(channel, "value"):
        return str(channel.value)
    return str(channel)


def build_notification_summary_lines(
    *,
    capture: Optional[CliRunSummaryCapture],
    notifier: Any = None,
    dry_run: bool = False,
    no_notify: bool = False,
) -> List[Tuple[str, str]]:
    """Build per-channel sent/skipped lines from run capture and skip flags."""

    if capture and capture.channel_outcomes:
        ordered: List[Tuple[str, str]] = []
        seen: Dict[str, int] = {}
        for channel, status in capture.channel_outcomes:
            if channel in seen:
                index = seen[channel]
                previous = ordered[index][1]
                if status == "failed" or previous == "failed":
                    ordered[index] = (channel, "failed")
                continue
            seen[channel] = len(ordered)
            ordered.append((channel, status))
        return ordered

    skip_reason: Optional[str] = None
    if dry_run:
        skip_reason = "skipped (dry-run)"
    elif no_notify:
        skip_reason = "skipped (--no-notify)"

    channels: Sequence[Any] = ()
    if notifier is not None:
        get_available = getattr(notifier, "get_available_channels", None)
        if callable(get_available):
            try:
                channels = tuple(get_available() or ())
            except Exception:  # broad-exception: cleanup - Best-effort available channel list for summary
                channels = ()

    if skip_reason is not None:
        if not channels:
            return [("—", skip_reason)]
        return [(_channel_display_name(channel), skip_reason) for channel in channels]

    if not channels:
        return [("—", "skipped (no channel configured)")]
    return [
        (_channel_display_name(channel), "skipped (not dispatched)")
        for channel in channels
    ]


def format_cli_run_summary(summary: CliRunSummary) -> str:
    """Render a compact bilingual end-of-run summary block."""

    lines: List[str] = ["===== Run summary / 运行摘要 ====="]

    if summary.ok_count is not None or summary.failed_count is not None:
        ok_text = (
            str(summary.ok_count) if summary.ok_count is not None else "—"
        )
        failed_text = (
            str(summary.failed_count) if summary.failed_count is not None else "—"
        )
        lines.append(
            f"Stocks / 股票: OK={ok_text} failed/失败={failed_text}"
        )

    if summary.report_paths:
        lines.append("Reports / 报告:")
        for path in summary.report_paths:
            lines.append(f"  - {path}")

    if summary.notifications:
        lines.append("Notifications / 通知:")
        for channel, status in summary.notifications:
            lines.append(f"  - {channel}: {status}")

    if summary.dry_run:
        lines.append(
            "Note / 说明: data-only report, add an LLM key for AI analysis / "
            "仅数据报告，配置 LLM Key 后可进行 AI 分析"
        )
    elif summary.no_llm:
        lines.append(
            "Note / 说明: no usable LLM — set "
            f"{_NO_LLM_CONFIG_HINT} / "
            "未检测到可用 LLM，请配置 LITELLM_MODEL 或厂商 API Key"
        )

    return "\n".join(lines)


def emit_cli_run_summary(summary: CliRunSummary) -> str:
    """Print and return the summary block."""

    text = format_cli_run_summary(summary)
    print(text)
    return text


def analyzer_has_no_usable_llm(analyzer: Any) -> bool:
    """Reuse the existing analyzer availability check (same path that warns)."""

    if analyzer is None:
        return True
    is_available = getattr(analyzer, "is_available", None)
    if not callable(is_available):
        return True
    try:
        return not bool(is_available())
    except Exception:  # broad-exception: cleanup - Best-effort analyzer availability probe for summary
        return True


def parse_arguments() -> argparse.Namespace:
    """Parse CLI arguments with bilingual help text."""
    # Inline description: parse_arguments is facade-cloned onto main, so module
    # globals from this file are not visible under the clone's __globals__.
    description = (
        "StockPulse: A-share / HK / US / JP / KR / TW intelligent stock analysis "
        "/ StockPulse：A股/港股/美股/日股/韩股/台股智能分析系统"
    )
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples / 示例:
  python main.py                    # normal run / 正常运行
  python main.py --debug            # debug logging / 调试模式
  python main.py --dry-run          # data only, no AI analysis / 仅获取数据，不进行 AI 分析
  python main.py --stocks 600519,000001  # specific symbols / 指定分析特定股票
  python main.py --portfolio futu   # live Futu portfolio scope / 从 Futu OpenD 读取实盘持仓作为分析范围
  python main.py --no-notify        # skip notifications / 不发送推送通知
  python main.py --check-notify     # check notification config / 检查通知配置，不发送通知
  python main.py --single-notify    # per-stock notify / 启用单股推送模式（每分析完一只立即推送）
  python main.py --schedule         # scheduled mode / 启用定时任务模式
  python main.py --market-review    # market review only / 仅运行大盘复盘
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging / 启用调试模式，输出详细日志'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Fetch data only, skip AI analysis / 仅获取数据，不进行 AI 分析'
    )

    parser.add_argument(
        '--stocks',
        type=str,
        help='Comma-separated stock codes (overrides config) / 指定要分析的股票代码，逗号分隔（覆盖配置文件）'
    )

    from src.services.stock_list_parser import SUPPORTED_PORTFOLIO_SOURCES

    parser.add_argument(
        '--portfolio',
        choices=SUPPORTED_PORTFOLIO_SOURCES,
        default=None,
        help='Load analysis scope from a read-only live portfolio (futu) / 从只读实盘持仓加载分析股票范围（当前支持 futu）',
    )

    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='Do not send push notifications / 不发送推送通知'
    )

    parser.add_argument(
        '--check-notify',
        action='store_true',
        help='Read-only notification channel config check / 只读检查通知渠道配置，不发送通知'
    )

    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='Notify after each stock instead of aggregate / 启用单股推送模式：每分析完一只股票立即推送，而不是汇总推送'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='Worker thread count (default: config) / 并发线程数（默认使用配置值）'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='Enable daily scheduled mode / 启用定时任务模式，每日定时执行'
    )

    parser.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='Do not run once immediately when scheduling starts / 定时任务启动时不立即执行一次'
    )

    parser.add_argument(
        '--market-review',
        action='store_true',
        help='Run market review only / 仅运行大盘复盘分析'
    )

    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='Skip market review / 跳过大盘复盘分析'
    )

    parser.add_argument(
        '--force-run',
        action='store_true',
        help='Skip trading-day check; force full analysis (Issue #373) / 跳过交易日检查，强制执行全量分析（Issue #373）'
    )

    parser.add_argument(
        '--webui',
        action='store_true',
        help='Start the Web management UI / 启动 Web 管理界面'
    )

    parser.add_argument(
        '--webui-only',
        action='store_true',
        help='Start Web service only (no auto analysis) / 仅启动 Web 服务，不执行自动分析'
    )

    parser.add_argument(
        '--serve',
        action='store_true',
        help='Start FastAPI backend and run analysis / 启动 FastAPI 后端服务（同时执行分析任务）'
    )

    parser.add_argument(
        '--serve-only',
        action='store_true',
        help='Start FastAPI backend only (no auto analysis) / 仅启动 FastAPI 后端服务，不自动执行分析'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help='FastAPI port (default: WEBUI_PORT or 8000) / FastAPI 服务端口（默认使用 WEBUI_PORT，未配置时为 8000）'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=None,
        help='FastAPI bind host (default: WEBUI_HOST or 127.0.0.1) / FastAPI 服务监听地址（默认使用 WEBUI_HOST，未配置时为 127.0.0.1）'
    )

    parser.add_argument(
        '--no-context-snapshot',
        action='store_true',
        help='Do not save analysis context snapshots / 不保存分析上下文快照'
    )

    # === Backtest ===
    parser.add_argument(
        '--backtest',
        action='store_true',
        help='Run backtest on historical analysis results / 运行回测（对历史分析结果进行评估）'
    )

    parser.add_argument(
        '--backtest-code',
        type=str,
        default=None,
        help='Backtest only this stock code / 仅回测指定股票代码'
    )

    parser.add_argument(
        '--backtest-days',
        type=int,
        default=None,
        help='Backtest evaluation window in trading days (default: config) / 回测评估窗口（交易日数，默认使用配置）'
    )

    parser.add_argument(
        '--backtest-force',
        action='store_true',
        help='Force backtest even when results already exist / 强制回测（即使已有回测结果也重新计算）'
    )

    return parser.parse_args()


def _dispatch_cli(config: Config, args: argparse.Namespace) -> int:
    """Dispatch the configured CLI mode after startup bootstrap completes."""

    # Verification Configuration
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)

    if getattr(args, "check_notify", False):
        from src.application_services import get_application_services
        from src.plugins import available_notification_channel_snapshot
        from src.services.notification_diagnostics import (
            NotificationPluginChannelStatus,
            format_notification_diagnostics,
            run_notification_diagnostics,
        )

        application_services = get_application_services()
        notification_registry = (
            application_services.notification_channel_registry
        )
        with application_services.notification_dispatch():
            plugin_snapshot = (
                application_services.notification_channel_snapshot()
            )
            available_plugin_snapshot = available_notification_channel_snapshot(
                plugin_snapshot
            )
            available_plugin_ids = {
                channel.channel_id for channel in available_plugin_snapshot
            }
            enabled_plugin_ids = {
                channel.channel_id for channel in plugin_snapshot
            }

            def _plugin_channel_state(channel):
                if channel.state != "enabled":
                    return channel.state
                if channel.channel_id not in enabled_plugin_ids:
                    return "unknown"
                if channel.channel_id in available_plugin_ids:
                    return "available"
                return "enabled_unavailable"

            plugin_channel_states = tuple(
                NotificationPluginChannelStatus(
                    channel_id=channel.channel_id,
                    display_name=channel.display_name,
                    state=_plugin_channel_state(channel),
                )
                for channel in notification_registry.lifecycle_snapshot()
            )
        result = run_notification_diagnostics(
            config,
            enabled_plugin_channels=tuple(
                channel.channel_id for channel in plugin_snapshot
            ),
            available_plugin_channels=tuple(
                channel.channel_id for channel in available_plugin_snapshot
            ),
            plugin_channel_states=plugin_channel_states,
        )
        print(format_notification_diagnostics(result))
        return 0 if result.ok else 1

    # Parse stock lists (convert to uppercase - Issue #355)
    stock_codes = None
    if args.stocks:
        stock_codes = [
            resolve_index_stock_code_for_analysis(c)
            for c in split_stock_list(args.stocks)
            if (c or "").strip()
        ]
        logger.info("Using the stock list supplied on the command line: %s", stock_codes)
    if getattr(args, "portfolio", None):
        if stock_codes is not None:
            logger.warning(
                "--portfolio %s overrides the stock list supplied by --stocks",
                args.portfolio,
            )
        logger.info("Using live portfolio source for analysis scope: %s", args.portfolio)

    start_serve, service_exit_code = __coordinate_service_runtime(config, args)
    if service_exit_code is not None:
        return service_exit_code

    # === Only Web Service Mode: No automatic analysis ===
    if args.serve_only:
        return __run_service_only_mode(args)

    try:
        # Mode 0: Backtesting
        if getattr(args, 'backtest', False):
            logger.info("Mode: backtest")
            from src.services.backtest_service import BacktestService

            service = BacktestService()
            stats = service.run_backtest(
                code=getattr(args, 'backtest_code', None),
                force=getattr(args, 'backtest_force', False),
                eval_window_days=getattr(args, 'backtest_days', None),
            )
            logger.info(
                f"Backtest completed: processed={stats.get('processed')} saved={stats.get('saved')} "
                f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
            )
            return 0

        # Mode 1: Market review for major indices only
        if args.market_review:
            from src.core.market_review import run_market_review
            from src.core.market_review_runtime import build_market_review_runtime

            # Issue #373: Trading day check for market-review-only mode.
            # Do NOT use _compute_trading_day_filter here: that helper checks
            # config.market_review_enabled, which would wrongly block an
            # explicit --market-review invocation when the flag is disabled.
            effective_region = None
            if not getattr(args, 'force_run', False) and getattr(config, 'trading_day_check_enabled', True):
                from src.core.trading_calendar import get_open_markets_today, compute_effective_region as _compute_region
                open_markets = get_open_markets_today()
                effective_region = _compute_region(
                    getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
                )
                if effective_region == '':
                    logger.info(
                        "All markets relevant to the review are closed today; skipping the run. "
                        "Use --force-run to override."
                    )
                    return 0

            logger.info("Mode: market review only")
            notifier, analyzer, search_service = build_market_review_runtime(config)
            # Local imports: _dispatch_cli is facade-cloned onto main.
            from src.app.cli import (
                CliRunSummary,
                CliRunSummaryCapture,
                analyzer_has_no_usable_llm,
                build_notification_summary_lines,
                emit_cli_run_summary,
            )

            capture = CliRunSummaryCapture()
            capture.install(notifier)
            try:
                _run_market_review_with_shared_lock(
                    config,
                    run_market_review,
                    notifier=notifier,
                    analyzer=analyzer,
                    search_service=search_service,
                    send_notification=not args.no_notify,
                    override_region=effective_region,
                    trigger_source="cli",
                )
            finally:
                capture.restore()

            emit_cli_run_summary(
                CliRunSummary(
                    report_paths=list(capture.report_paths),
                    notifications=build_notification_summary_lines(
                        capture=capture,
                        notifier=notifier,
                        dry_run=False,
                        no_notify=bool(args.no_notify),
                    ),
                    dry_run=False,
                    no_llm=analyzer_has_no_usable_llm(analyzer),
                )
            )
            return 0

        # Mode 2: Scheduled task mode
        if args.schedule or config.schedule_enabled:
            return __run_schedule_mode(config, args, stock_codes, start_serve)

        # Mode 3: Normal single run
        if config.run_immediately:
            analysis_succeeded = _run_analysis_with_runtime_scheduler_lock(
                config,
                args,
                stock_codes,
            )
            if (
                analysis_succeeded is False
                and getattr(args, "portfolio", None)
                and not start_serve
            ):
                return 1
        else:
            logger.info("Immediate analysis is disabled (RUN_IMMEDIATELY=false)")

        logger.info("\nProgram execution completed")

        __keep_service_runtime_alive(start_serve, args, config)
        return 0

    except KeyboardInterrupt:
        logger.info("\nInterrupted by the user; exiting")
        return 130

    except Exception as exc:  # broad-exception: fallback_recorded - preserve the logged top-level CLI failure boundary
        log_safe_exception(
            logger,
            "Main execution failed",
            exc,
            error_code="main_execution_failed",
        )
        return 1
